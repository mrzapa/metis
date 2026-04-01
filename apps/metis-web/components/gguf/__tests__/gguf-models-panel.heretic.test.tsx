import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchGgufCatalog,
  fetchGgufHardware,
  fetchGgufInstalled,
  fetchHereticPreflight,
} from "@/lib/api";
import { GgufModelsPanel } from "../gguf-models-panel";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchGgufCatalog: vi.fn(),
    fetchGgufHardware: vi.fn(),
    fetchGgufInstalled: vi.fn(),
    fetchHereticPreflight: vi.fn(),
    validateGgufModel: vi.fn(),
    refreshGgufCatalog: vi.fn(),
    registerGgufModel: vi.fn(),
    unregisterGgufModel: vi.fn(),
    runHereticAbliterateStream: vi.fn(),
  };
});

describe("GgufModelsPanel Heretic", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(fetchGgufHardware).mockResolvedValue({
      total_ram_gb: 32,
      available_ram_gb: 24,
      total_cpu_cores: 12,
      cpu_name: "CPU",
      has_gpu: false,
      gpu_vram_gb: null,
      total_gpu_vram_gb: null,
      gpu_name: "",
      gpu_count: 0,
      unified_memory: false,
      backend: "llama.cpp",
      detected: true,
      override_enabled: false,
      notes: [],
    });
    vi.mocked(fetchGgufCatalog).mockResolvedValue([]);
    vi.mocked(fetchGgufInstalled).mockResolvedValue([]);
    vi.mocked(fetchHereticPreflight).mockResolvedValue({
      ready: true,
      heretic_available: true,
      convert_script: "/opt/llama.cpp/convert_hf_to_gguf.py",
      errors: [],
    });
  });

  it("supports deep-linked Heretic tab and prefilled model id", async () => {
    render(
      <GgufModelsPanel
        initialModelsTab="heretic"
        initialHereticModelId="meta-llama/Llama-3.1-8B-Instruct"
      />,
    );

    await screen.findByText("Heretic Abliteration");
    expect(fetchHereticPreflight).toHaveBeenCalledTimes(1);

    await waitFor(() => {
      expect(screen.getByPlaceholderText("meta-llama/Llama-3.1-8B-Instruct")).toHaveValue(
        "meta-llama/Llama-3.1-8B-Instruct",
      );
    });

    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start pipeline" })).toBeEnabled();
  });
});
