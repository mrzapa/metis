import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the Tauri detection so getApiBase() falls back to env/default
vi.stubGlobal("window", { ...globalThis.window });

// Dynamically import after mocks are in place
const {
  fetchSessions,
  fetchSettings,
  fetchApiVersion,
  fetchGgufCatalog,
  queryKnowledgeSearch,
  normalizeRagStreamEvent,
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
