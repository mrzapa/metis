import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock the Tauri detection so getApiBase() falls back to env/default
vi.stubGlobal("window", { ...globalThis.window });

// Dynamically import after mocks are in place
const {
  fetchNyxCatalog,
  fetchNyxComponentDetail,
  previewLearningRoute,
  fetchSessions,
  fetchSettings,
  fetchForecastPreflight,
  fetchForecastSchema,
  fetchUiTelemetrySummary,
  fetchApiVersion,
  fetchGgufCatalog,
  fetchHereticPreflight,
  queryForecast,
  queryKnowledgeSearch,
  normalizeForecastStreamEvent,
  normalizeRagStreamEvent,
  runHereticAbliterateStream,
  submitRunAction,
  fetchNetworkAuditEvents,
  fetchNetworkAuditProviders,
  fetchNetworkAuditRecentCount,
  fetchSeedlingStatus,
  recordCompanionReflection,
  subscribeCompanionActivity,
  runNetworkAuditSyntheticPass,
} = await import(
  "../api"
);

describe("fetchSessions", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed session list on success", async () => {
    const mockSessions = [
      { session_id: "abc", title: "Test", created_at: "2026-01-01T00:00:00Z" },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockSessions),
      })
    );

    const result = await fetchSessions();
    expect(result).toEqual(mockSessions);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("throws on non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: () => Promise.resolve("Internal Server Error"),
      })
    );

    await expect(fetchSessions()).rejects.toThrow();
  });
});

describe("fetchSettings", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed settings object", async () => {
    const mockSettings = { llm_provider: "anthropic", chunk_size: 1000 };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockSettings),
      })
    );

    const result = await fetchSettings();
    expect(result).toEqual(mockSettings);
  });
});

describe("fetchSeedlingStatus", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("filters lifecycle heartbeat events from the companion bus", async () => {
    // Phase 2's tick emits ``state: "running"`` / ``trigger: "lifecycle"``
    // with summary "Seedling heartbeat" every cycle for boot_id tracking.
    // These are not user-facing — the dock's sigil-pulse already skips
    // them, and the thought log should too. Filter at the bridge so
    // every subscriber inherits the rule.
    const events: unknown[] = [];
    const unsubscribe = subscribeCompanionActivity((event) => events.push(event));
    const payload = {
      running: true,
      last_tick_at: "2026-04-24T20:00:00+00:00",
      current_stage: "seedling",
      next_action_at: "2026-04-24T20:01:00+00:00",
      queue_depth: 0,
      activity_events: [
        {
          source: "seedling",
          state: "running",
          trigger: "lifecycle",
          summary: "Seedling heartbeat",
          timestamp: 1770000000000,
          payload: { event_id: "seedling-heartbeat-1", boot_id: "test-heartbeat" },
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(payload),
      }),
    );

    await fetchSeedlingStatus();
    unsubscribe();

    expect(events).toEqual([]);
  });

  it("emits non-heartbeat Seedling activity through the companion bus once", async () => {
    // Real activity (anything not matching the lifecycle-heartbeat
    // signature) must still reach subscribers, and the boot_id dedup
    // machinery must still ensure each event_id only fires once.
    const events: unknown[] = [];
    const unsubscribe = subscribeCompanionActivity((event) => events.push(event));
    const payload = {
      running: true,
      last_tick_at: "2026-04-24T20:00:00+00:00",
      current_stage: "seedling",
      next_action_at: "2026-04-24T20:01:00+00:00",
      queue_depth: 0,
      activity_events: [
        {
          source: "seedling",
          state: "completed",
          trigger: "comet_absorbed",
          summary: "Absorbed news comet: GPU prices drop",
          timestamp: 1770000000000,
          payload: { event_id: "seedling-real-1", boot_id: "test-emit-once" },
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(payload),
      }),
    );

    await fetchSeedlingStatus();
    await fetchSeedlingStatus();
    unsubscribe();

    expect(events).toEqual([
      expect.objectContaining({
        source: "seedling",
        state: "completed",
        summary: "Absorbed news comet: GPU prices drop",
      }),
    ]);
  });

  it("re-emits replayed sequence numbers when the worker boot_id changes", async () => {
    const events: unknown[] = [];
    const unsubscribe = subscribeCompanionActivity((event) => events.push(event));

    function buildPayload(bootId: string, summary: string) {
      return {
        running: true,
        last_tick_at: "2026-04-24T20:00:00+00:00",
        current_stage: "seedling",
        next_action_at: "2026-04-24T20:01:00+00:00",
        queue_depth: 0,
        activity_events: [
          {
            source: "seedling",
            state: "running",
            trigger: "lifecycle",
            summary,
            timestamp: 1770000000000,
            payload: { event_id: `seedling-${bootId}-1`, boot_id: bootId },
          },
        ],
      };
    }

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(buildPayload("test-restart-A", "before restart")) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(buildPayload("test-restart-B", "after restart")) });
    vi.stubGlobal("fetch", fetchMock);

    await fetchSeedlingStatus();
    await fetchSeedlingStatus();
    unsubscribe();

    expect(events).toEqual([
      expect.objectContaining({ summary: "before restart" }),
      expect.objectContaining({ summary: "after restart" }),
    ]);
  });
});

describe("forecast api helpers", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches forecast preflight", async () => {
    const mockPreflight = {
      ready: true,
      timesfm_available: true,
      covariates_available: true,
      model_id: "google/timesfm-2.5-200m-pytorch",
      max_context: 15360,
      max_horizon: 1000,
      xreg_mode: "xreg + timesfm",
      force_xreg_cpu: true,
      warnings: [],
      install_guidance: [],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockPreflight),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchForecastPreflight();

    expect(result).toEqual(mockPreflight);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/v1/forecast/preflight");
  });

  it("posts forecast schema requests", async () => {
    const mockSchema = {
      file_path: "/tmp/revenue.csv",
      file_name: "revenue.csv",
      delimiter: ",",
      row_count: 12,
      column_count: 3,
      columns: [],
      timestamp_candidates: ["ds"],
      numeric_target_candidates: ["y"],
      suggested_mapping: {
        timestamp_column: "ds",
        target_column: "y",
        dynamic_covariates: ["promo"],
        static_covariates: [],
      },
      validation: {
        valid: true,
        errors: [],
        warnings: [],
        history_row_count: 10,
        future_row_count: 2,
        inferred_horizon: 2,
        resolved_horizon: 2,
        inferred_frequency: "daily",
      },
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockSchema),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchForecastSchema("/tmp/revenue.csv", {
      mapping: {
        timestamp_column: "ds",
        target_column: "y",
        dynamic_covariates: ["promo"],
        static_covariates: [],
      },
      horizon: 2,
    });

    expect(result).toEqual(mockSchema);
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/v1/forecast/schema");
    expect(String(fetchMock.mock.calls[0]?.[1]?.body)).toContain("\"file_path\":\"/tmp/revenue.csv\"");
    expect(String(fetchMock.mock.calls[0]?.[1]?.body)).toContain("\"horizon\":2");
  });

  it("posts forecast queries", async () => {
    const mockResult = {
      run_id: "forecast-run-1",
      answer_text: "The next value is likely to rise.",
      selected_mode: "Forecast",
      query_mode: "forecast",
      model_backend: "timesfm-2.5-torch",
      model_id: "google/timesfm-2.5-200m-pytorch",
      horizon: 3,
      context_used: 24,
      warnings: [],
      artifacts: [],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResult),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await queryForecast(
      "/tmp/revenue.csv",
      "Forecast the next three periods.",
      {
        timestamp_column: "ds",
        target_column: "y",
        dynamic_covariates: ["promo"],
        static_covariates: [],
      },
      { selected_mode: "Forecast" },
      { horizon: 3, sessionId: "session-1" },
    );

    expect(result).toEqual(mockResult);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/v1/query/forecast");
    expect(String(fetchMock.mock.calls[0]?.[1]?.body)).toContain("\"session_id\":\"session-1\"");
  });
});

describe("previewLearningRoute", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("posts the compact star and index snapshot to the preview endpoint", async () => {
    const preview = {
      route_id: "learning-route-1",
      title: "Route Through the Stars: Graph Thinking",
      origin_star_id: "star-1",
      created_at: "2026-03-31T10:00:00+00:00",
      updated_at: "2026-03-31T10:00:00+00:00",
      steps: [
        {
          id: "step-1",
          kind: "orient",
          title: "Orient Around Graph Thinking",
          objective: "Get a quick map.",
          rationale: "Start broad.",
          manifest_path: "/indexes/atlas-a.json",
          source_star_id: null,
          tutor_prompt: "Tutor me through the overview.",
          estimated_minutes: 12,
        },
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(preview),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await previewLearningRoute({
      origin_star: {
        id: "star-1",
        label: "Graph Thinking",
        active_manifest_path: "/indexes/atlas-a.json",
        linked_manifest_paths: ["/indexes/atlas-a.json"],
      },
      connected_stars: [],
      indexes: [
        {
          index_id: "Atlas A",
          manifest_path: "/indexes/atlas-a.json",
          document_count: 4,
          chunk_count: 16,
          created_at: "2026-03-31T10:00:00+00:00",
          embedding_signature: "embed-a",
          brain_pass: { provider: "fallback" },
        },
      ],
    });

    expect(result).toEqual(preview);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/v1/learning-routes/preview");
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
  });
});

describe("fetchNyxCatalog", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("calls the local Nyx catalog endpoint with search params", async () => {
    const mockCatalog = {
      query: "glow",
      total: 2,
      matched: 1,
      curated_only: true,
      source: "nyx_registry",
      items: [
        {
          component_name: "glow-card",
          title: "Glow Card",
          description: "A glow card.",
          curated_description: "Interactive card with glow-based accent effects.",
          component_type: "registry:ui",
          install_target: "@nyx/glow-card",
          registry_url: "https://nyxui.com/r/glow-card.json",
          schema_url: "https://ui.shadcn.com/schema/registry-item.json",
          source: "nyx_registry",
          source_repo: "https://github.com/MihirJaiswal/nyxui",
          required_dependencies: ["clsx"],
          dependencies: ["clsx"],
          dev_dependencies: [],
          registry_dependencies: [],
          file_count: 1,
          targets: ["components/ui/glow-card.tsx"],
        },
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockCatalog),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchNyxCatalog("glow", { limit: 5 });

    expect(result).toEqual(mockCatalog);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      "/v1/nyx/catalog?q=glow&limit=5",
    );
  });
});

describe("fetchNyxComponentDetail", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("calls the local Nyx component detail endpoint", async () => {
    const mockDetail = {
      component_name: "glow-card",
      title: "Glow Card",
      description: "A glow card.",
      curated_description: "Interactive card with glow-based accent effects.",
      component_type: "registry:ui",
      install_target: "@nyx/glow-card",
      registry_url: "https://nyxui.com/r/glow-card.json",
      schema_url: "https://ui.shadcn.com/schema/registry-item.json",
      source: "nyx_registry",
      source_repo: "https://github.com/MihirJaiswal/nyxui",
      required_dependencies: ["clsx", "tailwind-merge"],
      dependencies: ["clsx", "tailwind-merge"],
      dev_dependencies: [],
      registry_dependencies: [],
      file_count: 1,
      targets: ["components/ui/glow-card.tsx"],
      files: [
        {
          path: "registry/ui/glow-card.tsx",
          file_type: "registry:ui",
          target: "components/ui/glow-card.tsx",
          content_bytes: 128,
        },
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockDetail),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchNyxComponentDetail("glow-card");

    expect(result).toEqual(mockDetail);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      "/v1/nyx/catalog/glow-card",
    );
  });
});

describe("fetchUiTelemetrySummary", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed telemetry summary and forwards query params", async () => {
    const mockSummary = {
      window_hours: 168,
      generated_at: "2026-03-23T12:00:00+00:00",
      sampled_event_count: 42,
      metrics: {
        exposure_count: 12,
        render_attempt_count: 12,
        render_success_rate: 1,
        render_failure_rate: 0,
        fallback_rate_by_reason: {},
        interaction_rate: 0.25,
        runtime_attempt_rate: 0.5,
        runtime_success_rate: 1,
        runtime_failure_rate: 0,
        runtime_skip_mix: {},
        data_quality: {
          events_with_run_id_pct: 100,
          events_with_source_boundary_pct: 100,
          events_with_client_timestamp_pct: 100,
        },
      },
      thresholds: {
        per_metric: {},
        overall_recommendation: "go",
        failed_conditions: [],
        sample: {
          exposure_count: 12,
          payload_detected_count: 12,
          render_attempt_count: 12,
          runtime_attempt_count: 6,
          minimum_exposure_count_for_go: 300,
        },
      },
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockSummary),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchUiTelemetrySummary(168, 999);

    expect(result).toEqual(mockSummary);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/v1/telemetry/ui/summary?window_hours=168&limit=999");
  });

  it("supports the 24h window without an explicit limit", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          window_hours: 24,
          generated_at: "2026-03-23T12:00:00+00:00",
          sampled_event_count: 0,
          metrics: {
            exposure_count: 0,
            render_attempt_count: 0,
            render_success_rate: null,
            render_failure_rate: null,
            fallback_rate_by_reason: {},
            interaction_rate: null,
            runtime_attempt_rate: null,
            runtime_success_rate: null,
            runtime_failure_rate: null,
            runtime_skip_mix: {},
            data_quality: {
              events_with_run_id_pct: null,
              events_with_source_boundary_pct: null,
              events_with_client_timestamp_pct: null,
            },
          },
          thresholds: {
            per_metric: {},
            overall_recommendation: "hold",
            failed_conditions: [],
            sample: {
              exposure_count: 0,
              payload_detected_count: 0,
              render_attempt_count: 0,
              runtime_attempt_count: 0,
              minimum_exposure_count_for_go: 300,
            },
          },
        }),
      }),
    );

    await fetchUiTelemetrySummary(24);

    expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).toContain("window_hours=24");
    expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).not.toContain("limit=");
  });

  it("throws a descriptive error on non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        text: () => Promise.resolve("service unavailable"),
      }),
    );

    await expect(fetchUiTelemetrySummary(24)).rejects.toThrow(
      "Failed to fetch UI telemetry summary (24h): service unavailable",
    );
  });
});

describe("fetchApiVersion", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns version string", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ version: "1.0.0" }),
      })
    );

    const result = await fetchApiVersion();
    expect(result).toBe("1.0.0");
  });
});

describe("queryKnowledgeSearch", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("posts to the knowledge search endpoint with run and session ids", async () => {
    const mockResult = {
      run_id: "run-1",
      summary_text: "Found 2 relevant passages.",
      sources: [{ sid: "S1", source: "doc", snippet: "evidence" }],
      context_block: "context",
      top_score: 0.92,
      selected_mode: "Knowledge Search",
      retrieval_plan: { stages: [] },
      fallback: { triggered: false, strategy: "synthesize_anyway" },
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResult),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await queryKnowledgeSearch(
      "/tmp/index.json",
      "What does this say?",
      { selected_mode: "Knowledge Search" },
      { runId: "run-1", sessionId: "session-1" },
    );

    expect(result).toEqual(mockResult);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toContain("/v1/search/knowledge");
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      manifest_path: "/tmp/index.json",
      question: "What does this say?",
      settings: { selected_mode: "Knowledge Search" },
      run_id: "run-1",
      session_id: "session-1",
    });
  });
});

describe("fetchGgufCatalog", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns explainable GGUF catalogue entries", async () => {
    const mockCatalog = [
      {
        model_name: "Qwen2.5-7B",
        provider: "bartowski",
        parameter_count: "7B",
        architecture: "qwen2",
        use_case: "chat",
        fit_level: "good",
        run_mode: "gpu",
        best_quant: "Q4_K_M",
        estimated_tps: 42.5,
        memory_required_gb: 4.6,
        memory_available_gb: 24,
        recommended_context_length: 4096,
        score: 87.5,
        recommendation_summary: "Good fit on gpu with Q4_K_M at 4,096-token context.",
        notes: ["GPU: model loaded into VRAM."],
        caveats: [],
        score_components: { quality: 82, speed: 100, fit: 100, context: 100 },
        source_repo: "Qwen/Qwen2.5-7B-Instruct-GGUF",
        source_provider: "bartowski",
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockCatalog),
      }),
    );

    const result = await fetchGgufCatalog("chat");

    expect(result).toEqual(mockCatalog);
  });
});

describe("normalizeForecastStreamEvent", () => {
  it("normalizes final forecast stream payloads", () => {
    const normalized = normalizeForecastStreamEvent({
      event_type: "final",
      payload: {
        run_id: "forecast-run-1",
        answer_text: "The series trends upward.",
        selected_mode: "Forecast",
        query_mode: "forecast",
        model_backend: "timesfm-2.5-torch",
        model_id: "google/timesfm-2.5-200m-pytorch",
        horizon: 6,
        context_used: 32,
        warnings: ["One covariate was clipped."],
        artifacts: [],
      },
    });

    expect(normalized).toMatchObject({
      type: "final",
      run_id: "forecast-run-1",
      answer_text: "The series trends upward.",
      selected_mode: "Forecast",
      query_mode: "forecast",
      model_backend: "timesfm-2.5-torch",
      model_id: "google/timesfm-2.5-200m-pytorch",
      horizon: 6,
      context_used: 32,
      warnings: ["One covariate was clipped."],
      artifacts: [],
      event_id: undefined,
      event_type: "final",
      status: undefined,
      lifecycle: undefined,
      timestamp: undefined,
      payload: {
        run_id: "forecast-run-1",
        answer_text: "The series trends upward.",
        selected_mode: "Forecast",
        query_mode: "forecast",
        model_backend: "timesfm-2.5-torch",
        model_id: "google/timesfm-2.5-200m-pytorch",
        horizon: 6,
        context_used: 32,
        warnings: ["One covariate was clipped."],
        artifacts: [],
      },
    });
  });
});

describe("normalizeRagStreamEvent", () => {
  it("uses normalized envelope fields when present", () => {
    const normalized = normalizeRagStreamEvent({
      event_type: "token",
      run_id: "run-1",
      event_id: "run-1:2",
      status: "in_progress",
      lifecycle: "generation",
      timestamp: "2026-03-23T10:00:00+00:00",
      payload: { text: "hello" },
    });

    expect(normalized.type).toBe("token");
    expect(normalized.run_id).toBe("run-1");
    if (normalized.type === "token") {
      expect(normalized.text).toBe("hello");
    }
    expect(normalized.event_type).toBe("token");
    expect(normalized.event_id).toBe("run-1:2");
    expect(normalized.status).toBe("in_progress");
    expect(normalized.lifecycle).toBe("generation");
    expect(normalized.timestamp).toBe("2026-03-23T10:00:00+00:00");
  });

  it("preserves Nyx actions on final events", () => {
    const normalized = normalizeRagStreamEvent({
      event_type: "final",
      run_id: "run-nyx",
      payload: {
        answer_text: "Ready to install.",
        sources: [],
        actions: [
          {
            action_id: "action-1",
            action_type: "nyx_install",
            label: "Install Nyx components",
            summary: "Install glow-card",
            requires_approval: true,
            run_action_endpoint: "/v1/runs/run-nyx/actions",
            payload: {
              action_id: "action-1",
              action_type: "nyx_install",
              proposal_token: "proposal-1",
              component_count: 1,
              component_names: ["glow-card"],
            },
            proposal: {
              schema_version: "1.0",
              proposal_token: "proposal-1",
              component_names: ["glow-card"],
              component_count: 1,
              components: [
                {
                  component_name: "glow-card",
                  title: "Glow Card",
                },
              ],
            },
          },
        ],
      },
    });

    expect(normalized.type).toBe("final");
    if (normalized.type === "final") {
      expect(normalized.actions).toEqual([
        expect.objectContaining({
          action_id: "action-1",
          action_type: "nyx_install",
          proposal: expect.objectContaining({
            proposal_token: "proposal-1",
            component_names: ["glow-card"],
          }),
        }),
      ]);
    }
  });

  it("keeps legacy flat events working", () => {
    const legacy = normalizeRagStreamEvent({
      type: "final",
      run_id: "run-2",
      answer_text: "done",
      sources: [],
    });

    expect(legacy.type).toBe("final");
    expect(legacy.run_id).toBe("run-2");
    if (legacy.type === "final") {
      expect(legacy.answer_text).toBe("done");
      expect(legacy.sources).toEqual([]);
    }
  });
});

describe("submitRunAction", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed Nyx action results from the backend response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            run_id: "run-nyx",
            approved: true,
            status: "success",
            action_id: "action-1",
            action_type: "nyx_install",
            proposal_token: "proposal-1",
            component_names: ["glow-card"],
            component_count: 1,
            execution_status: "completed",
            installer: {
              command: ["pnpm", "dlx", "shadcn@latest", "add", "@nyx/glow-card"],
              cwd: "/workspace",
              package_script: "ui:add:nyx",
              returncode: 0,
              stdout_excerpt: "installed",
            },
          }),
      }),
    );

    const result = await submitRunAction("run-nyx", {
      approved: true,
      action_id: "action-1",
      action_type: "nyx_install",
      proposal_token: "proposal-1",
    });

    expect(result).toEqual(
      expect.objectContaining({
        run_id: "run-nyx",
        action_type: "nyx_install",
        execution_status: "completed",
        installer: expect.objectContaining({
          returncode: 0,
          stdout_excerpt: "installed",
        }),
      }),
    );
  });
});

describe("fetchHereticPreflight", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed Heretic preflight data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            ready: true,
            heretic_available: true,
            convert_script: "/opt/llama.cpp/convert_hf_to_gguf.py",
            errors: [],
          }),
      }),
    );

    const result = await fetchHereticPreflight();
    expect(result).toEqual({
      ready: true,
      heretic_available: true,
      convert_script: "/opt/llama.cpp/convert_hf_to_gguf.py",
      errors: [],
    });
  });
});

describe("runHereticAbliterateStream", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("streams started/progress/complete events", async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder();
        controller.enqueue(
          encoder.encode(
            [
              'event: message\ndata: {"type":"started","message":"Starting"}\n\n',
              'event: message\ndata: {"type":"progress","message":"Converting"}\n\n',
              'event: message\ndata: {"type":"complete","message":"Done","gguf_path":"/tmp/model.gguf"}\n\n',
            ].join(""),
          ),
        );
        controller.close();
      },
    });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: stream,
      }),
    );

    const events: Array<{ type: string; message: string; gguf_path?: string }> = [];
    await runHereticAbliterateStream(
      {
        model_id: "meta-llama/Llama-3.1-8B-Instruct",
      },
      {
        onEvent: (event) => {
          events.push(event);
        },
      },
    );

    expect(events).toEqual([
      { type: "started", message: "Starting" },
      { type: "progress", message: "Converting" },
      { type: "complete", message: "Done", gguf_path: "/tmp/model.gguf" },
    ]);
  });

  it("normalizes unknown events to progress", async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder();
        controller.enqueue(
          encoder.encode('event: message\ndata: {"message":"line output"}\n\n'),
        );
        controller.close();
      },
    });

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: stream,
      }),
    );

    const messages: string[] = [];
    await runHereticAbliterateStream(
      {
        model_id: "meta-llama/Llama-3.1-8B-Instruct",
      },
      {
        onEvent: (event) => {
          messages.push(`${event.type}:${event.message}`);
        },
      },
    );

    expect(messages).toEqual(["progress:line output"]);
  });
});

describe("fetchNetworkAuditEvents", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed events array on success", async () => {
    const mockEvents = [
      {
        id: "ev-1",
        timestamp: "2026-04-19T12:00:00Z",
        method: "POST",
        url_host: "api.openai.com",
        url_path_prefix: "/v1/chat/completions",
        query_params_stored: false,
        provider_key: "openai",
        trigger_feature: "chat.direct",
        size_bytes_in: 1024,
        size_bytes_out: 256,
        latency_ms: 300,
        status_code: 200,
        user_initiated: true,
        blocked: false,
        source: "sdk_invocation",
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockEvents),
      }),
    );

    const result = await fetchNetworkAuditEvents({ limit: 10 });
    expect(result).toEqual(mockEvents);
    const calledUrl = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(calledUrl).toContain("/v1/network-audit/events");
    expect(calledUrl).toContain("limit=10");
  });

  it("threads provider param into the query string", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) }),
    );
    await fetchNetworkAuditEvents({ provider: "openai" });
    const calledUrl = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(calledUrl).toContain("provider=openai");
  });

  it("returns [] when the backend returns a non-array body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ error: "nope" }),
      }),
    );
    const result = await fetchNetworkAuditEvents();
    expect(result).toEqual([]);
  });

  it("throws on non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: () => Promise.resolve(""),
      }),
    );
    await expect(fetchNetworkAuditEvents()).rejects.toThrow();
  });
});

describe("fetchNetworkAuditProviders", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed provider array on success", async () => {
    const mockProviders = [
      {
        key: "openai",
        display_name: "OpenAI",
        category: "llm",
        kill_switch_setting_key: "provider_block_llm",
        blocked: false,
        events_7d: 3,
        last_call_at: "2026-04-19T11:00:00Z",
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockProviders),
      }),
    );
    const result = await fetchNetworkAuditProviders();
    expect(result).toEqual(mockProviders);
    const calledUrl = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(calledUrl).toContain("/v1/network-audit/providers");
  });
});

describe("fetchNetworkAuditRecentCount", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("passes the window seconds as a query param and returns the parsed shape", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ count: 2, window_seconds: 300 }),
      }),
    );
    const result = await fetchNetworkAuditRecentCount(300);
    expect(result).toEqual({ count: 2, window_seconds: 300 });
    const calledUrl = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(calledUrl).toContain("window=300");
  });

  it("coerces missing fields to safe defaults", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      }),
    );
    const result = await fetchNetworkAuditRecentCount(300);
    expect(result.count).toBe(0);
    expect(result.window_seconds).toBe(300);
  });
});

describe("subscribeNetworkAuditStream — parser + reconnect semantics", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  /** Build a ReadableStream that yields the given utf-8 string chunks. */
  const streamOf = (...chunks: string[]): ReadableStream<Uint8Array> => {
    const encoder = new TextEncoder();
    let i = 0;
    return new ReadableStream<Uint8Array>({
      pull(controller) {
        if (i >= chunks.length) {
          controller.close();
          return;
        }
        controller.enqueue(encoder.encode(chunks[i]));
        i += 1;
      },
    });
  };

  it("validates audit_event shape and drops malformed frames", async () => {
    const { subscribeNetworkAuditStream } = await import("@/lib/api");

    // First frame: missing required "provider_key" — guard must drop it.
    // Second frame: valid — guard must admit it.
    const malformed = JSON.stringify({ type: "audit_event", id: "01ABC", timestamp: "2026-04-20T00:00:00Z" });
    const good = JSON.stringify({
      type: "audit_event",
      id: "01DEF",
      timestamp: "2026-04-20T00:00:01Z",
      method: "GET",
      url_host: "api.openai.com",
      url_path_prefix: "/v1",
      query_params_stored: false,
      provider_key: "openai",
      trigger_feature: "llm_invoke",
      size_bytes_in: null,
      size_bytes_out: null,
      latency_ms: 12,
      status_code: 200,
      user_initiated: false,
      blocked: false,
      source: "sdk_invocation",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: streamOf(`data: ${malformed}\n\n`, `data: ${good}\n\n`),
      }),
    );

    const frames: unknown[] = [];
    const unsubscribe = subscribeNetworkAuditStream((frame) => frames.push(frame));
    // Drain microtasks so the reader loop runs.
    await vi.runOnlyPendingTimersAsync();
    // Let the async fetch + stream drain.
    for (let i = 0; i < 5; i += 1) {
      await Promise.resolve();
    }

    expect(frames).toHaveLength(1);
    expect((frames[0] as { type: string }).type).toBe("audit_event");
    expect(((frames[0] as { event: { provider_key: string } }).event).provider_key).toBe("openai");
    unsubscribe();
  });

  it("rejects frames that claim query_params_stored=true (privacy invariant)", async () => {
    const { subscribeNetworkAuditStream } = await import("@/lib/api");

    const invariantViolation = JSON.stringify({
      type: "audit_event",
      id: "01XYZ",
      timestamp: "2026-04-20T00:00:00Z",
      method: "GET",
      url_host: "api.openai.com",
      url_path_prefix: "/v1",
      query_params_stored: true, // must be rejected
      provider_key: "openai",
      trigger_feature: "llm_invoke",
      size_bytes_in: null,
      size_bytes_out: null,
      latency_ms: 12,
      status_code: 200,
      user_initiated: false,
      blocked: false,
      source: "sdk_invocation",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: streamOf(`data: ${invariantViolation}\n\n`),
      }),
    );

    const frames: unknown[] = [];
    const unsubscribe = subscribeNetworkAuditStream((frame) => frames.push(frame));
    await vi.runOnlyPendingTimersAsync();
    for (let i = 0; i < 5; i += 1) {
      await Promise.resolve();
    }

    expect(frames).toHaveLength(0);
    unsubscribe();
  });

  it("no_store frame latches — no further reconnects scheduled", async () => {
    const { subscribeNetworkAuditStream } = await import("@/lib/api");

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: streamOf('data: {"type":"no_store"}\n\n'),
    });
    vi.stubGlobal("fetch", fetchMock);

    const frames: unknown[] = [];
    const unsubscribe = subscribeNetworkAuditStream((frame) => frames.push(frame));

    // Let the first connection drain (one no_store frame, then stream ends).
    await vi.runOnlyPendingTimersAsync();
    for (let i = 0; i < 5; i += 1) {
      await Promise.resolve();
    }

    expect(frames).toHaveLength(1);
    expect((frames[0] as { type: string }).type).toBe("no_store");

    // Advance time past any possible backoff — if the latch is broken,
    // the subscriber would have scheduled a reconnect and called
    // fetch again. It must NOT.
    const initialCalls = fetchMock.mock.calls.length;
    await vi.advanceTimersByTimeAsync(60_000);
    expect(fetchMock.mock.calls.length).toBe(initialCalls);

    unsubscribe();
  });
});

describe("runNetworkAuditSyntheticPass", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("POSTs to /v1/network-audit/synthetic-pass", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          duration_ms: 12,
          airplane_mode: false,
          providers: [],
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await runNetworkAuditSyntheticPass();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
    expect(calledUrl).toContain("/v1/network-audit/synthetic-pass");
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init?.method).toBe("POST");
  });

  it("returns the parsed response shape", async () => {
    const mockResponse = {
      duration_ms: 73,
      airplane_mode: true,
      providers: [
        {
          provider_key: "openai",
          display_name: "OpenAI",
          category: "llm",
          attempted: false,
          blocked: true,
          actual_calls: 0,
          error: null,
        },
        {
          provider_key: "anthropic",
          display_name: "Anthropic",
          category: "llm",
          attempted: false,
          blocked: true,
          actual_calls: 0,
          error: null,
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResponse),
      }),
    );

    const result = await runNetworkAuditSyntheticPass();
    expect(result.duration_ms).toBe(73);
    expect(result.airplane_mode).toBe(true);
    expect(result.providers).toHaveLength(2);
    expect(result.providers[0]?.provider_key).toBe("openai");
    expect(result.providers[0]?.blocked).toBe(true);
  });

  it("throws on non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: () => Promise.resolve("boom"),
      }),
    );
    await expect(runNetworkAuditSyntheticPass()).rejects.toThrow(/boom/);
  });
});

describe("recordCompanionReflection (M13 Phase 4a)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("posts the Bonsai reflection with kind, source_event, and defaults", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          ok: true,
          kind: "while_you_work",
          status: { latest_summary: "ok" },
          memory_entry: { summary: "ok" },
        }),
    });
    vi.stubGlobal("fetch", fetchSpy);

    const result = await recordCompanionReflection({
      summary: "Lead with the next step.",
      trigger: "news_comet",
      source_event: { source: "news_comet", comet_id: "comet_abc" },
    });

    expect(result.ok).toBe(true);
    expect(fetchSpy).toHaveBeenCalledOnce();
    const call = fetchSpy.mock.calls[0];
    const url = call[0] as string;
    expect(url.endsWith("/v1/assistant/record-reflection")).toBe(true);
    const body = JSON.parse((call[1] as RequestInit).body as string);
    expect(body.summary).toBe("Lead with the next step.");
    expect(body.trigger).toBe("news_comet");
    expect(body.kind).toBe("while_you_work");
    // Default confidence still threaded through.
    expect(body.confidence).toBeCloseTo(0.55);
    expect(body.source_event).toEqual({ source: "news_comet", comet_id: "comet_abc" });
  });

  it("emits a CompanionActivityEvent with kind=while_you_work on success", async () => {
    const events: unknown[] = [];
    const unsubscribe = subscribeCompanionActivity((event) => events.push(event));
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ ok: true }),
      }),
    );

    await recordCompanionReflection({ summary: "Persisted." });
    unsubscribe();

    expect(events).toEqual([
      expect.objectContaining({
        source: "reflection",
        state: "completed",
        kind: "while_you_work",
        summary: "Persisted.",
      }),
    ]);
  });

  it("does NOT emit a CompanionActivityEvent when the backend returns ok=false", async () => {
    const events: unknown[] = [];
    const unsubscribe = subscribeCompanionActivity((event) => events.push(event));
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ ok: false, reason: "cooldown" }),
      }),
    );

    const result = await recordCompanionReflection({ summary: "Skipped." });
    unsubscribe();

    expect(result.ok).toBe(false);
    expect(result.reason).toBe("cooldown");
    expect(events).toEqual([]);
  });

  it("throws on HTTP error so the caller can decide whether to surface", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: () => Promise.resolve("boom"),
      }),
    );
    await expect(
      recordCompanionReflection({ summary: "irrelevant" }),
    ).rejects.toThrow(/boom/);
  });
});
