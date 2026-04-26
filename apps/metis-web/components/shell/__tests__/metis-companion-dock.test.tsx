import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { MetisCompanionDock } from "../metis-companion-dock";
import type { AssistantSnapshot, CompanionActivityEvent } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  fetchAssistant: vi.fn(),
  fetchAtlasCandidate: vi.fn(),
  saveAtlasEntry: vi.fn(),
  decideAtlasCandidate: vi.fn(),
  updateAssistant: vi.fn(),
  reflectAssistant: vi.fn(),
  bootstrapAssistant: vi.fn(),
  clearAssistantMemory: vi.fn(),
  fetchAutonomousStatus: vi.fn().mockResolvedValue({ enabled: false }),
  fetchSeedlingStatus: vi.fn().mockResolvedValue({
    running: false,
    last_tick_at: null,
    current_stage: "seedling",
    next_action_at: null,
    queue_depth: 0,
  }),
  recordCompanionReflection: vi.fn().mockResolvedValue({ ok: true }),
  updateSettings: vi.fn().mockResolvedValue({}),
  triggerAutonomousResearchStream: vi.fn().mockResolvedValue(undefined),
  subscribeCompanionActivity: vi.fn().mockReturnValue(() => {}),
}));

// Mutable WebGPU stub so individual tests can drive status/output edges
// — Phase 4a's POST wiring fires on the "generating" → "ready" edge.
const webgpuStub = {
  status: "idle" as
    | "idle"
    | "loading"
    | "ready"
    | "generating"
    | "unsupported"
    | "oom"
    | "error",
  output: "",
  progress: null as null | { loadedBytes: number; totalBytes: number; pct: number },
  error: null as string | null,
  load: vi.fn(),
  send: vi.fn(),
  stop: vi.fn(),
  reset: vi.fn(),
};

vi.mock("@/lib/webgpu-companion/webgpu-companion-context", () => ({
  useWebGPUCompanionContext: () => webgpuStub,
}));

const {
  fetchAssistant,
  fetchAtlasCandidate,
  saveAtlasEntry,
  decideAtlasCandidate,
  fetchSeedlingStatus,
  recordCompanionReflection,
  subscribeCompanionActivity,
} = await import("@/lib/api");

function buildSnapshot(overrides: Partial<AssistantSnapshot> = {}): AssistantSnapshot {
  return {
    identity: {
      assistant_id: "companion-1",
      name: "METIS Companion",
      archetype: "guide",
      companion_enabled: true,
      greeting: "Ready when you are.",
      prompt_seed: "Stay grounded and helpful.",
      docked: true,
      minimized: true,
      ...overrides.identity,
    },
    runtime: {
      provider: "local",
      model: "llama",
      local_gguf_model_path: "/models/companion.gguf",
      local_gguf_context_length: 4096,
      local_gguf_gpu_layers: 0,
      local_gguf_threads: 4,
      fallback_to_primary: true,
      auto_bootstrap: false,
      auto_install: false,
      bootstrap_state: "ready",
      recommended_model_name: "",
      recommended_quant: "",
      recommended_use_case: "",
      ...overrides.runtime,
    },
    policy: {
      reflection_enabled: true,
      reflection_backend: "local",
      reflection_cooldown_seconds: 600,
      max_memory_entries: 24,
      max_playbooks: 8,
      max_brain_links: 16,
      trigger_on_onboarding: true,
      trigger_on_index_build: true,
      trigger_on_completed_run: true,
      allow_automatic_writes: false,
      ...overrides.policy,
    },
    status: {
      state: "ready",
      paused: false,
      runtime_ready: true,
      runtime_source: "dedicated_local",
      runtime_provider: "local",
      runtime_model: "llama",
      bootstrap_state: "ready",
      bootstrap_message: "The companion is ready.",
      recommended_model_name: "",
      recommended_quant: "",
      recommended_use_case: "",
      last_reflection_at: "",
      last_reflection_trigger: "",
      latest_summary: "The companion stays minimized but persistent.",
      latest_why: "",
      ...overrides.status,
    },
    memory: overrides.memory ?? [],
    playbooks: overrides.playbooks ?? [],
    brain_links: overrides.brain_links ?? [],
  };
}

describe("MetisCompanionDock", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchAtlasCandidate).mockReset();
    vi.mocked(fetchAtlasCandidate).mockResolvedValue(null);
    vi.mocked(fetchSeedlingStatus).mockReset();
    vi.mocked(fetchSeedlingStatus).mockResolvedValue({
      running: false,
      last_tick_at: null,
      current_stage: "seedling",
      next_action_at: null,
      queue_depth: 0,
    });
    vi.mocked(recordCompanionReflection).mockReset();
    vi.mocked(recordCompanionReflection).mockResolvedValue({ ok: true });
    vi.mocked(subscribeCompanionActivity).mockReset();
    vi.mocked(subscribeCompanionActivity).mockReturnValue(() => {});
    // Reset WebGPU stub between tests.
    webgpuStub.status = "idle";
    webgpuStub.output = "";
    webgpuStub.send.mockReset();
    webgpuStub.load.mockReset();
    webgpuStub.stop.mockReset();
    webgpuStub.reset.mockReset();
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("metis:bonsai-always-on");
    }
  });

  it("renders the minimized companion state from the assistant snapshot", async () => {
    vi.mocked(fetchAssistant).mockResolvedValueOnce(buildSnapshot());
    vi.mocked(fetchAtlasCandidate).mockResolvedValueOnce(null);

    render(<MetisCompanionDock />);

    await waitFor(() => {
      expect(fetchAssistant).toHaveBeenCalledTimes(1);
    });

    expect(
      await screen.findByText("METIS Companion"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand companion" })).toBeInTheDocument();
    // Subtitle and summary are hidden in the compact minimized pill
    expect(screen.queryByText("Dedicated local companion")).not.toBeInTheDocument();
    expect(screen.queryByText("The companion stays minimized but persistent.")).not.toBeInTheDocument();
  });

  it("shows the Seedling liveness indicator when the worker is running", async () => {
    vi.mocked(fetchAssistant).mockResolvedValueOnce(buildSnapshot());
    vi.mocked(fetchAtlasCandidate).mockResolvedValueOnce(null);
    vi.mocked(fetchSeedlingStatus).mockResolvedValueOnce({
      running: true,
      last_tick_at: "2026-04-24T20:00:00+00:00",
      current_stage: "seedling",
      next_action_at: "2026-04-24T20:01:00+00:00",
      queue_depth: 0,
    });

    render(<MetisCompanionDock />);

    // Default frontend-only label.
    expect(
      await screen.findByLabelText(/Seedling awake · while-you-work/i),
    ).toBeInTheDocument();
  });

  it("surfaces backend_configured model_status in the indicator tooltip (Phase 4b)", async () => {
    vi.mocked(fetchAssistant).mockResolvedValueOnce(buildSnapshot());
    vi.mocked(fetchAtlasCandidate).mockResolvedValueOnce(null);
    vi.mocked(fetchSeedlingStatus).mockResolvedValueOnce({
      running: true,
      last_tick_at: "2026-04-25T20:00:00+00:00",
      current_stage: "seedling",
      next_action_at: "2026-04-25T20:01:00+00:00",
      queue_depth: 0,
      model_status: "backend_configured",
    });

    render(<MetisCompanionDock />);

    expect(
      await screen.findByLabelText(/backend reflection configured/i),
    ).toBeInTheDocument();
  });

  it("surfaces backend_unavailable model_status in the indicator tooltip", async () => {
    vi.mocked(fetchAssistant).mockResolvedValueOnce(buildSnapshot());
    vi.mocked(fetchAtlasCandidate).mockResolvedValueOnce(null);
    vi.mocked(fetchSeedlingStatus).mockResolvedValueOnce({
      running: true,
      last_tick_at: "2026-04-25T20:00:00+00:00",
      current_stage: "seedling",
      next_action_at: "2026-04-25T20:01:00+00:00",
      queue_depth: 0,
      model_status: "backend_unavailable",
    });

    render(<MetisCompanionDock />);

    expect(
      await screen.findByLabelText(/cannot load/i),
    ).toBeInTheDocument();
  });

  it("shows the Atlas popup and lets the user save or dismiss it", async () => {
    vi.mocked(fetchAssistant).mockResolvedValueOnce(buildSnapshot());
    vi.mocked(fetchAtlasCandidate).mockResolvedValue({
      entry_id: "atlas-1",
      created_at: "2026-04-06T20:00:00Z",
      updated_at: "2026-04-06T20:05:00Z",
      session_id: "session-1",
      run_id: "run-1",
      title: "How does METIS stay grounded?",
      summary: "METIS keeps grounded evidence attached to the answer.",
      body_md: "METIS keeps grounded evidence attached to the answer.",
      sources: [],
      mode: "Research",
      index_id: "idx-1",
      top_score: 0.88,
      source_count: 2,
      confidence: 0.77,
      rationale: "2 grounded sources, top score 0.88, mode Research.",
      slug: "how-does-metis-stay-grounded",
      status: "candidate",
      saved_at: "",
      markdown_path: "",
    });
    vi.mocked(saveAtlasEntry).mockResolvedValueOnce({
      entry_id: "atlas-1",
      created_at: "2026-04-06T20:00:00Z",
      updated_at: "2026-04-06T20:05:00Z",
      session_id: "session-1",
      run_id: "run-1",
      title: "How does METIS stay grounded?",
      summary: "METIS keeps grounded evidence attached to the answer.",
      body_md: "METIS keeps grounded evidence attached to the answer.",
      sources: [],
      mode: "Research",
      index_id: "idx-1",
      top_score: 0.88,
      source_count: 2,
      confidence: 0.77,
      rationale: "2 grounded sources, top score 0.88, mode Research.",
      slug: "how-does-metis-stay-grounded",
      status: "saved",
      saved_at: "2026-04-06T20:05:00Z",
      markdown_path: "C:/atlas/entries/how-does-metis-stay-grounded.md",
    });

    render(<MetisCompanionDock sessionId="session-1" runId="run-1" />);

    expect(await screen.findByText("Atlas Suggestion")).toBeInTheDocument();
    expect(screen.getByText("This answer looks worth keeping. Save it to Atlas?")).toBeInTheDocument();

    await screen.getByRole("button", { name: "Save to Atlas" }).click();

    await waitFor(() => {
      expect(saveAtlasEntry).toHaveBeenCalledWith({
        session_id: "session-1",
        run_id: "run-1",
        title: "How does METIS stay grounded?",
        summary: "METIS keeps grounded evidence attached to the answer.",
      });
    });
    expect(await screen.findByText("Saved to Atlas · entries/how-does-metis-stay-grounded.md")).toBeInTheDocument();
  });

  it("dismisses the Atlas popup when the user snoozes it", async () => {
    vi.mocked(fetchAssistant).mockResolvedValueOnce(buildSnapshot());
    vi.mocked(fetchAtlasCandidate).mockResolvedValue({
      entry_id: "atlas-1",
      created_at: "2026-04-06T20:00:00Z",
      updated_at: "2026-04-06T20:05:00Z",
      session_id: "session-1",
      run_id: "run-1",
      title: "How does METIS stay grounded?",
      summary: "METIS keeps grounded evidence attached to the answer.",
      body_md: "METIS keeps grounded evidence attached to the answer.",
      sources: [],
      mode: "Research",
      index_id: "idx-1",
      top_score: 0.88,
      source_count: 2,
      confidence: 0.77,
      rationale: "2 grounded sources, top score 0.88, mode Research.",
      slug: "how-does-metis-stay-grounded",
      status: "candidate",
      saved_at: "",
      markdown_path: "",
    });
    vi.mocked(decideAtlasCandidate).mockResolvedValueOnce({
      entry_id: "atlas-1",
      created_at: "2026-04-06T20:00:00Z",
      updated_at: "2026-04-06T20:05:00Z",
      session_id: "session-1",
      run_id: "run-1",
      title: "How does METIS stay grounded?",
      summary: "METIS keeps grounded evidence attached to the answer.",
      body_md: "METIS keeps grounded evidence attached to the answer.",
      sources: [],
      mode: "Research",
      index_id: "idx-1",
      top_score: 0.88,
      source_count: 2,
      confidence: 0.77,
      rationale: "2 grounded sources, top score 0.88, mode Research.",
      slug: "how-does-metis-stay-grounded",
      status: "snoozed",
      saved_at: "",
      markdown_path: "",
    });

    render(<MetisCompanionDock sessionId="session-1" runId="run-1" />);

    expect(await screen.findByText("Atlas Suggestion")).toBeInTheDocument();

    await screen.getByRole("button", { name: "Not now" }).click();

    await waitFor(() => {
      expect(decideAtlasCandidate).toHaveBeenCalledWith({
        session_id: "session-1",
        run_id: "run-1",
        decision: "snoozed",
      });
    });
    await waitFor(() => {
      expect(screen.queryByText("Atlas Suggestion")).not.toBeInTheDocument();
    });
  });
  it("renders the thought log when companion activity events arrive", async () => {
    // Capture the subscribeCompanionActivity listener so the test can fire
    // simulated activity events into the dock's useEffect hook.
    const listeners: Array<(event: CompanionActivityEvent) => void> = [];
    vi.mocked(subscribeCompanionActivity).mockImplementation((listener) => {
      listeners.push(listener);
      return () => {
        const idx = listeners.indexOf(listener);
        if (idx >= 0) listeners.splice(idx, 1);
      };
    });

    // Render expanded so the Recent activity section is visible.
    vi.mocked(fetchAssistant).mockResolvedValueOnce(
      buildSnapshot({ identity: { minimized: false } as AssistantSnapshot["identity"] }),
    );
    vi.mocked(fetchAtlasCandidate).mockResolvedValueOnce(null);

    render(<MetisCompanionDock />);

    await waitFor(() => expect(fetchAssistant).toHaveBeenCalled());
    await waitFor(() => expect(listeners.length).toBeGreaterThan(0));

    const fire = (event: CompanionActivityEvent) =>
      act(() => {
        for (const listener of listeners) listener(event);
      });

    fire({
      source: "autonomous_research",
      state: "running",
      trigger: "manual",
      summary: "Searching the web…",
      timestamp: Date.now(),
    });
    fire({
      source: "autonomous_research",
      state: "completed",
      trigger: "manual",
      summary: "New star added to constellation",
      timestamp: Date.now(),
    });

    expect(await screen.findByText("Recent activity")).toBeInTheDocument();
    expect(screen.getByText("Searching the web…")).toBeInTheDocument();
    expect(
      screen.getAllByText("New star added to constellation").length,
    ).toBeGreaterThan(0);
  });

  it("posts Bonsai's response to record-reflection on the generating→ready edge (Phase 4a)", async () => {
    // Capture the listener the dock registers so we can fire a completed
    // CompanionActivityEvent into it deterministically.
    const listeners: Array<(event: CompanionActivityEvent) => void> = [];
    vi.mocked(subscribeCompanionActivity).mockImplementation((listener) => {
      listeners.push(listener);
      return () => {
        const idx = listeners.indexOf(listener);
        if (idx >= 0) listeners.splice(idx, 1);
      };
    });

    // User has opted into always-on Bonsai reflection AND Bonsai is loaded.
    window.localStorage.setItem("metis:bonsai-always-on", "1");
    webgpuStub.status = "ready";
    webgpuStub.output = "";

    vi.mocked(fetchAssistant).mockResolvedValueOnce(
      buildSnapshot({ identity: { minimized: false } as AssistantSnapshot["identity"] }),
    );
    vi.mocked(fetchAtlasCandidate).mockResolvedValueOnce(null);

    const { rerender } = render(<MetisCompanionDock />);
    await waitFor(() => expect(listeners.length).toBeGreaterThan(0));

    // Fire the trigger event. The dock asks Bonsai to generate and parks
    // the source-event in alwaysOnPendingRef while it waits.
    act(() => {
      for (const listener of listeners) {
        listener({
          source: "news_comet",
          state: "completed",
          trigger: "absorb",
          summary: "User absorbed comet ABC",
          timestamp: 1_700_000_000_000,
          payload: { comet_id: "comet_abc" },
        });
      }
    });
    expect(webgpuStub.send).toHaveBeenCalledOnce();

    // Bonsai finishes — drive the status edge generating → ready with the
    // generated text on the stub. The dock effect runs on the next render.
    webgpuStub.status = "generating";
    rerender(<MetisCompanionDock />);
    webgpuStub.status = "ready";
    webgpuStub.output = "Skim the abstract before bed.";
    rerender(<MetisCompanionDock />);

    await waitFor(() => {
      expect(recordCompanionReflection).toHaveBeenCalledOnce();
    });
    const arg = vi.mocked(recordCompanionReflection).mock.calls[0][0];
    expect(arg.summary).toBe("Skim the abstract before bed.");
    expect(arg.kind).toBe("while_you_work");
    expect(arg.trigger).toBe("news_comet");
    expect(arg.source_event).toEqual(
      expect.objectContaining({
        source: "news_comet",
        state: "completed",
        comet_id: "comet_abc",
      }),
    );
  });

  it("does not POST when always-on is off, even if Bonsai is ready", async () => {
    const listeners: Array<(event: CompanionActivityEvent) => void> = [];
    vi.mocked(subscribeCompanionActivity).mockImplementation((listener) => {
      listeners.push(listener);
      return () => {
        const idx = listeners.indexOf(listener);
        if (idx >= 0) listeners.splice(idx, 1);
      };
    });

    // Bonsai is ready but the user has not opted in.
    webgpuStub.status = "ready";
    webgpuStub.output = "";

    vi.mocked(fetchAssistant).mockResolvedValueOnce(
      buildSnapshot({ identity: { minimized: false } as AssistantSnapshot["identity"] }),
    );
    vi.mocked(fetchAtlasCandidate).mockResolvedValueOnce(null);

    render(<MetisCompanionDock />);
    await waitFor(() => expect(listeners.length).toBeGreaterThan(0));

    act(() => {
      for (const listener of listeners) {
        listener({
          source: "news_comet",
          state: "completed",
          trigger: "absorb",
          summary: "another comet",
          timestamp: 1,
        });
      }
    });

    expect(webgpuStub.send).not.toHaveBeenCalled();
    expect(recordCompanionReflection).not.toHaveBeenCalled();
  });

  it("ignores reflection-source events to prevent self-triggering loops", async () => {
    const listeners: Array<(event: CompanionActivityEvent) => void> = [];
    vi.mocked(subscribeCompanionActivity).mockImplementation((listener) => {
      listeners.push(listener);
      return () => {
        const idx = listeners.indexOf(listener);
        if (idx >= 0) listeners.splice(idx, 1);
      };
    });

    window.localStorage.setItem("metis:bonsai-always-on", "1");
    webgpuStub.status = "ready";

    vi.mocked(fetchAssistant).mockResolvedValueOnce(
      buildSnapshot({ identity: { minimized: false } as AssistantSnapshot["identity"] }),
    );
    vi.mocked(fetchAtlasCandidate).mockResolvedValueOnce(null);

    render(<MetisCompanionDock />);
    await waitFor(() => expect(listeners.length).toBeGreaterThan(0));

    // A reflection-completed event must NOT trigger another reflection.
    act(() => {
      for (const listener of listeners) {
        listener({
          source: "reflection",
          state: "completed",
          trigger: "while_you_work",
          summary: "Persisted note.",
          timestamp: 2,
          kind: "while_you_work",
        });
      }
    });

    expect(webgpuStub.send).not.toHaveBeenCalled();
  });
});
