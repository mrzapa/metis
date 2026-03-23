import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";

vi.mock("next/navigation", () => ({
  usePathname: () => "/gguf",
}));

vi.mock("@/components/shell/page-chrome", () => ({
  PageChrome: ({ title, actions, heroAside, children }: React.PropsWithChildren<{ title: string; actions?: React.ReactNode; heroAside?: React.ReactNode }>) => (
    <div>
      <h1>{title}</h1>
      {actions}
      {heroAside}
      {children}
    </div>
  ),
}));

vi.mock("@/components/ui/animated-lucide-icon", () => ({
  AnimatedLucideIcon: () => <span data-testid="mock-icon" />,
}));

vi.mock("@/lib/api", () => ({
  fetchGgufCatalog: vi.fn(),
  fetchGgufHardware: vi.fn(),
  fetchGgufInstalled: vi.fn(),
  validateGgufModel: vi.fn(),
  refreshGgufCatalog: vi.fn(),
  registerGgufModel: vi.fn(),
  unregisterGgufModel: vi.fn(),
}));

const {
  fetchGgufCatalog,
  fetchGgufHardware,
  fetchGgufInstalled,
  refreshGgufCatalog,
} = await import("@/lib/api");
const { default: GgufPage } = await import("./page");

describe("GgufPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchGgufHardware).mockResolvedValue({
      total_ram_gb: 32,
      available_ram_gb: 24,
      total_cpu_cores: 12,
      cpu_name: "AMD Ryzen",
      has_gpu: true,
      gpu_vram_gb: 12,
      total_gpu_vram_gb: 12,
      gpu_name: "RTX 4070",
      gpu_count: 1,
      unified_memory: false,
      backend: "cuda",
      detected: true,
      override_enabled: false,
      notes: [],
    });
    vi.mocked(fetchGgufInstalled).mockResolvedValue([]);
    vi.mocked(refreshGgufCatalog).mockResolvedValue({
      status: "refreshed",
      use_case: "general",
      advisory_only: false,
    });
    vi.mocked(fetchGgufCatalog).mockResolvedValue([
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
        notes: ["GPU: model loaded into VRAM.", "Baseline estimated speed: 42.5 tok/s."],
        caveats: [],
        score_components: { quality: 82, speed: 100, fit: 100, context: 100 },
        source_repo: "Qwen/Qwen2.5-7B-Instruct-GGUF",
        source_provider: "bartowski",
      },
      {
        model_name: "Llama 3.1 8B",
        provider: "bartowski",
        parameter_count: "8B",
        architecture: "llama",
        use_case: "chat",
        fit_level: "marginal",
        run_mode: "cpu_offload",
        best_quant: "Q4_K_M",
        estimated_tps: 14.2,
        memory_required_gb: 7.8,
        memory_available_gb: 24,
        recommended_context_length: 8192,
        score: 68.1,
        recommendation_summary: "Marginal fit on cpu offload with Q4_K_M at 8,192-token context.",
        notes: [
          "GPU: insufficient VRAM, spilling to system RAM.",
          "Performance will be significantly reduced.",
        ],
        caveats: [
          "GPU: insufficient VRAM, spilling to system RAM.",
          "Performance will be significantly reduced.",
        ],
        score_components: { quality: 84, speed: 35, fit: 70, context: 100 },
        source_repo: "meta-llama/Llama-3.1-8B-Instruct-GGUF",
        source_provider: "bartowski",
      },
    ]);
  });

  it("shows fit diagnostics for the selected model and updates when another card is chosen", async () => {
    render(<GgufPage />);

    const fitPanel = await screen.findByTestId("gguf-fit-panel");
    expect(fitPanel).toBeInTheDocument();
    expect(within(fitPanel).getByText("Good fit on gpu with Q4_K_M at 4,096-token context.")).toBeInTheDocument();
    expect(within(fitPanel).getByText("Weighted recommendation score.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Llama 3.1 8B/i }));

    await waitFor(() => {
      expect(within(fitPanel).getByText("Marginal fit on cpu offload with Q4_K_M at 8,192-token context.")).toBeInTheDocument();
    });
    expect(within(fitPanel).getByText("Performance will be significantly reduced.")).toBeInTheDocument();
    expect(within(fitPanel).getByText("Nearby alternatives")).toBeInTheDocument();
  });
});