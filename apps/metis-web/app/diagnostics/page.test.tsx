import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("motion/react", () => ({
  motion: {
    div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  },
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
  checkApiCompatibility: vi.fn(),
  fetchApiVersion: vi.fn(),
  fetchLogTail: vi.fn(),
  fetchSettings: vi.fn(),
  fetchUiTelemetrySummary: vi.fn(),
  updateSettings: vi.fn(),
}));

const {
  checkApiCompatibility,
  fetchApiVersion,
  fetchLogTail,
  fetchSettings,
  fetchUiTelemetrySummary,
  updateSettings,
} = await import("@/lib/api");
const { default: DiagnosticsPage } = await import("./page");

function makeSummary(windowHours: 24 | 168, recommendation: "go" | "hold" | "rollback_runtime" | "rollback_artifacts") {
  return {
    window_hours: windowHours,
    generated_at: "2026-03-23T12:00:00+00:00",
    sampled_event_count: 100,
    metrics: {
      exposure_count: windowHours === 24 ? 120 : 420,
      render_attempt_count: windowHours === 24 ? 120 : 420,
      render_success_rate: 0.995,
      render_failure_rate: recommendation === "rollback_artifacts" ? 0.02 : 0.005,
      fallback_rate_by_reason: {},
      interaction_rate: 0.1,
      runtime_attempt_rate: 0.5,
      runtime_success_rate: recommendation === "rollback_runtime" ? 0.97 : 0.995,
      runtime_failure_rate: recommendation === "rollback_runtime" ? 0.02 : 0.001,
      runtime_skip_mix: {},
      data_quality: {
        events_with_run_id_pct: 99,
        events_with_source_boundary_pct: 100,
        events_with_client_timestamp_pct: 98,
      },
    },
    thresholds: {
      per_metric: {},
      overall_recommendation: recommendation,
      failed_conditions:
        recommendation === "rollback_runtime"
          ? ["runtime_failure_rate > 1.0%"]
          : recommendation === "rollback_artifacts"
            ? ["render_failure_rate > 1.0%"]
            : [],
      sample: {
        exposure_count: windowHours === 24 ? 120 : 420,
        payload_detected_count: windowHours === 24 ? 120 : 420,
        render_attempt_count: windowHours === 24 ? 120 : 420,
        runtime_attempt_count: windowHours === 24 ? 60 : 210,
        minimum_exposure_count_for_go: 300,
      },
    },
  };
}

describe("DiagnosticsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("confirm", vi.fn(() => true));
    vi.mocked(fetchSettings).mockResolvedValue({
      enable_arrow_artifacts: true,
      enable_arrow_artifact_runtime: true,
      basic_wizard_completed: true,
    });
    vi.mocked(fetchLogTail).mockResolvedValue({
      log_path: "metis.log",
      lines: ["line 1"],
      total_lines: 1,
      missing: false,
    });
    vi.mocked(fetchApiVersion).mockResolvedValue("1.0.0");
    vi.mocked(checkApiCompatibility).mockResolvedValue({ compatible: true, warning: null });
  });

  it("renders independent 24h and 168h rollout recommendations", async () => {
    vi.mocked(fetchUiTelemetrySummary)
      .mockResolvedValueOnce(makeSummary(24, "rollback_runtime"))
      .mockResolvedValueOnce(makeSummary(168, "go"));

    render(<DiagnosticsPage />);

    expect(await screen.findByText(/Artifact rollout console/i)).toBeInTheDocument();
    expect(await screen.findByText(/Recommendation: rollback runtime/i)).toBeInTheDocument();
    expect(await screen.findByText(/Recommendation: go/i)).toBeInTheDocument();
    expect(
      screen.getAllByText((_, element) => element?.textContent === "Artifacts: true")[0],
    ).toBeInTheDocument();
    expect(
      screen.getAllByText((_, element) => element?.textContent === "Runtime: true")[0],
    ).toBeInTheDocument();
    expect(screen.getByText("runtime_failure_rate > 1.0%")).toBeInTheDocument();
  });

  it("isolates summary failures and keeps the rest of diagnostics available", async () => {
    vi.mocked(fetchUiTelemetrySummary)
      .mockRejectedValueOnce(new Error("24h unavailable"))
      .mockResolvedValueOnce(makeSummary(168, "hold"));

    render(<DiagnosticsPage />);

    expect(await screen.findByText(/Failed to load 24h summary/i)).toBeInTheDocument();
    expect(screen.getByText(/24h unavailable/i)).toBeInTheDocument();
    expect(await screen.findByText(/Recommendation: hold/i)).toBeInTheDocument();
    expect(screen.getAllByText(/^Safe settings$/i)[0]).toBeInTheDocument();
  });

  it("sends the runtime-only rollback payload and refreshes summaries after success", async () => {
    vi.mocked(fetchUiTelemetrySummary)
      .mockResolvedValueOnce(makeSummary(24, "rollback_runtime"))
      .mockResolvedValueOnce(makeSummary(168, "hold"))
      .mockResolvedValueOnce(makeSummary(24, "hold"))
      .mockResolvedValueOnce(makeSummary(168, "hold"));
    vi.mocked(fetchSettings)
      .mockResolvedValueOnce({
        enable_arrow_artifacts: true,
        enable_arrow_artifact_runtime: true,
        basic_wizard_completed: true,
      })
      .mockResolvedValueOnce({
        enable_arrow_artifacts: true,
        enable_arrow_artifact_runtime: false,
        basic_wizard_completed: true,
      });
    vi.mocked(updateSettings).mockResolvedValue({
      enable_arrow_artifacts: true,
      enable_arrow_artifact_runtime: false,
    });

    render(<DiagnosticsPage />);

    const button = await screen.findByRole("button", { name: /Disable artifact runtime/i });
    fireEvent.click(button);

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({ enable_arrow_artifact_runtime: false });
    });
    expect(updateSettings).not.toHaveBeenCalledWith({ enable_arrow_artifacts: false });
    expect(fetchSettings).toHaveBeenCalledTimes(2);
    expect(fetchUiTelemetrySummary).toHaveBeenCalledTimes(4);
    expect(vi.mocked(globalThis.confirm)).toHaveBeenCalledTimes(1);
  });

  it("sends the global artifact rollback payload without touching the runtime flag", async () => {
    vi.mocked(fetchUiTelemetrySummary)
      .mockResolvedValueOnce(makeSummary(24, "rollback_artifacts"))
      .mockResolvedValueOnce(makeSummary(168, "hold"))
      .mockResolvedValueOnce(makeSummary(24, "hold"))
      .mockResolvedValueOnce(makeSummary(168, "hold"));
    vi.mocked(fetchSettings)
      .mockResolvedValueOnce({
        enable_arrow_artifacts: true,
        enable_arrow_artifact_runtime: true,
        basic_wizard_completed: true,
      })
      .mockResolvedValueOnce({
        enable_arrow_artifacts: false,
        enable_arrow_artifact_runtime: true,
        basic_wizard_completed: true,
      });
    vi.mocked(updateSettings).mockResolvedValue({
      enable_arrow_artifacts: false,
      enable_arrow_artifact_runtime: true,
    });

    render(<DiagnosticsPage />);

    const button = await screen.findByRole("button", { name: /Disable artifacts/i });
    fireEvent.click(button);

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({ enable_arrow_artifacts: false });
    });
    expect(updateSettings).not.toHaveBeenCalledWith({ enable_arrow_artifact_runtime: false });
    expect(fetchSettings).toHaveBeenCalledTimes(2);
    expect(fetchUiTelemetrySummary).toHaveBeenCalledTimes(4);
  });
});