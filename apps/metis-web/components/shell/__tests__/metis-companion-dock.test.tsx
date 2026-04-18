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
  updateSettings: vi.fn().mockResolvedValue({}),
  triggerAutonomousResearchStream: vi.fn().mockResolvedValue(undefined),
  subscribeCompanionActivity: vi.fn().mockReturnValue(() => {}),
}));

vi.mock("@/lib/webgpu-companion/webgpu-companion-context", () => ({
  useWebGPUCompanionContext: () => ({ status: "idle", load: vi.fn(), send: vi.fn(), stop: vi.fn(), reset: vi.fn(), output: null, progress: null, error: null }),
}));

const {
  fetchAssistant,
  fetchAtlasCandidate,
  saveAtlasEntry,
  decideAtlasCandidate,
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
});
