import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { MetisCompanionDock } from "../metis-companion-dock";
import type { AssistantSnapshot } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  fetchAssistant: vi.fn(),
  updateAssistant: vi.fn(),
  reflectAssistant: vi.fn(),
  bootstrapAssistant: vi.fn(),
  clearAssistantMemory: vi.fn(),
}));

const { fetchAssistant } = await import("@/lib/api");

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
});
