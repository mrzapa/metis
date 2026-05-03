import { describe, it, expect, vi, beforeEach } from "vitest";

const {
  fetchAssistant,
  updateAssistant,
  reflectAssistant,
  bootstrapAssistant,
  clearAssistantMemory,
  deleteAssistantMemoryEntry,
  deleteAssistantMemoryByKind,
  deleteAssistantPlaybook,
  fetchAtlasCandidate,
  saveAtlasEntry,
  decideAtlasCandidate,
} = await import("../api");

function mockJsonResponse<T>(data: T) {
  return {
    ok: true,
    json: () => Promise.resolve(data),
  };
}

describe("assistant API helpers", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("fetchAssistant reads the full assistant snapshot", async () => {
    const snapshot = {
      identity: {
        assistant_id: "companion-1",
        name: "METIS",
        archetype: "guide",
        companion_enabled: true,
        greeting: "Ready when you are.",
        prompt_seed: "Be concise and helpful.",
        docked: true,
        minimized: false,
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
      },
      status: {
        state: "ready",
        paused: false,
        runtime_ready: true,
        runtime_source: "dedicated_local",
        runtime_provider: "local",
        runtime_model: "llama",
        bootstrap_state: "ready",
        bootstrap_message: "Companion ready.",
        recommended_model_name: "",
        recommended_quant: "",
        recommended_use_case: "",
        last_reflection_at: "",
        last_reflection_trigger: "",
        latest_summary: "The companion is settled.",
        latest_why: "Recent activity was captured.",
      },
      memory: [],
      playbooks: [],
      brain_links: [],
    };

    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse(snapshot));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchAssistant()).resolves.toEqual(snapshot);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/assistant",
      undefined,
    );
  });

  it("updateAssistant posts the requested partial assistant state", async () => {
    const snapshot = {
      identity: { docked: true, minimized: true },
      runtime: {},
      policy: {},
      status: {},
      memory: [],
      playbooks: [],
      brain_links: [],
    };

    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse(snapshot));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      updateAssistant({
        status: { paused: true },
        identity: { minimized: true },
      }),
    ).resolves.toEqual(snapshot);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/assistant",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: { paused: true },
          identity: { minimized: true },
        }),
      }),
    );
  });

  it("reflectAssistant normalizes the request payload", async () => {
    const response = { ok: true };
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse(response));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      reflectAssistant({
        session_id: "session-1",
        run_id: "run-2",
      }),
    ).resolves.toEqual(response);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/assistant/reflect",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trigger: "manual",
          context_id: "",
          session_id: "session-1",
          run_id: "run-2",
          force: false,
        }),
      }),
    );
  });

  it("bootstrapAssistant and clearAssistantMemory target the companion maintenance endpoints", async () => {
    const snapshot = {
      identity: { docked: true, minimized: false },
      runtime: {},
      policy: {},
      status: {},
      memory: [],
      playbooks: [],
      brain_links: [],
    };
    const clearResult = { cleared: true };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mockJsonResponse(snapshot))
      .mockResolvedValueOnce(mockJsonResponse(clearResult));
    vi.stubGlobal("fetch", fetchMock);

    await expect(bootstrapAssistant(true)).resolves.toEqual(snapshot);
    await expect(clearAssistantMemory(7)).resolves.toEqual(clearResult);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8000/v1/assistant/bootstrap",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ install_local_model: true }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8000/v1/assistant/memory?limit=7",
      expect.objectContaining({
        method: "DELETE",
      }),
    );
  });

  it("deleteAssistantMemoryEntry calls DELETE /v1/assistant/memory/:id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await deleteAssistantMemoryEntry("abc-123");
    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/assistant/memory/abc-123",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("deleteAssistantMemoryByKind calls DELETE /v1/assistant/memory/by-kind?kind=X", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(mockJsonResponse({ ok: true, deleted_count: 4 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await deleteAssistantMemoryByKind("skill");
    expect(result).toEqual({ ok: true, deleted_count: 4 });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/assistant/memory/by-kind?kind=skill",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("deleteAssistantPlaybook calls DELETE /v1/assistant/playbooks/:id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await deleteAssistantPlaybook("pb-1");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/assistant/playbooks/pb-1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("Atlas helpers read, save, and dismiss candidate prompts", async () => {
    const candidate = {
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
    };
    const saved = { ...candidate, status: "saved", markdown_path: "C:/atlas/entries/how-does-metis-stay-grounded.md" };
    const snoozed = { ...candidate, status: "snoozed" };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mockJsonResponse(candidate))
      .mockResolvedValueOnce(mockJsonResponse(saved))
      .mockResolvedValueOnce(mockJsonResponse(snoozed));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchAtlasCandidate("session-1", "run-1")).resolves.toEqual(candidate);
    await expect(
      saveAtlasEntry({ session_id: "session-1", run_id: "run-1", title: "Keep this", summary: "Atlas summary" }),
    ).resolves.toEqual(saved);
    await expect(
      decideAtlasCandidate({ session_id: "session-1", run_id: "run-1", decision: "snoozed" }),
    ).resolves.toEqual(snoozed);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8000/v1/atlas/candidate?session_id=session-1&run_id=run-1",
      undefined,
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8000/v1/atlas/save",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: "session-1",
          run_id: "run-1",
          title: "Keep this",
          summary: "Atlas summary",
        }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://127.0.0.1:8000/v1/atlas/decision",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: "session-1",
          run_id: "run-1",
          decision: "snoozed",
        }),
      }),
    );
  });
});
