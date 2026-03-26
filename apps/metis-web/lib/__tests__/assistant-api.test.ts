import { describe, it, expect, vi, beforeEach } from "vitest";

const {
  fetchAssistant,
  updateAssistant,
  reflectAssistant,
  bootstrapAssistant,
  clearAssistantMemory,
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
});
