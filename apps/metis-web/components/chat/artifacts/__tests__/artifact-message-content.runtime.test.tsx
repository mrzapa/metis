import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { NormalizedArrowArtifact } from "@/lib/artifacts/extract-arrow-artifacts";
import { ArtifactMessageContent } from "@/components/chat/artifacts/artifact-message-content";

const { sandbox } = vi.hoisted(() => ({
  sandbox: vi.fn((props: { source?: Record<string, string> }) => {
    return (parent: ParentNode) => {
      const host = parent as HTMLElement;
      const source = props.source?.["main.ts"] ?? "";

      const container = document.createElement("div");
      container.setAttribute("data-testid", "mock-arrow-sandbox");
      container.textContent = source.includes("Timeline") ? "Timeline" : "Artifact";

      host.replaceChildren(container);
      return parent;
    };
  }),
}));

vi.mock("@arrow-js/sandbox", () => ({ sandbox }));

describe("ArtifactMessageContent runtime integration", () => {
  it("executes the runtime sandbox path for timeline artifacts", async () => {
    const lifecycleEvents: Array<{ lifecycle: string }> = [];
    const artifact: NormalizedArrowArtifact = {
      id: "artifact-runtime-e2e-1",
      type: "timeline",
      summary: "Timeline fallback summary",
      path: "",
      mime_type: "application/json",
      payload: {
        items: [
          {
            label: "Kickoff",
            detail: "Project started",
            occurred_at: "2026-03-01T00:00:00Z",
          },
        ],
      },
      payload_bytes: 0,
      payload_truncated: false,
      render_kind: "runtime",
      runtime_eligible: true,
      runtime_skip_reason: undefined,
    };

    render(
      <ArtifactMessageContent
        artifacts={[artifact]}
        runtimeEnabled={true}
        onRuntimeLifecycleEvent={(event) => {
          lifecycleEvents.push({ lifecycle: event.lifecycle });
        }}
      />,
    );

    await waitFor(() => {
      expect(lifecycleEvents.some((event) => event.lifecycle === "attempt")).toBe(true);
      expect(lifecycleEvents.some((event) => event.lifecycle === "success")).toBe(true);
    });

    const runtimeHost = screen.getByTestId("arrow-artifact-runtime-host");
    expect(runtimeHost).toHaveClass("block");

    const sandboxHost = runtimeHost.querySelector('[data-testid="mock-arrow-sandbox"]');
    expect(sandboxHost).toBeTruthy();
    expect(sandboxHost).toHaveTextContent("Timeline");

    expect(screen.queryByText("Timeline fallback summary")).not.toBeInTheDocument();
  });

  it("renders workspace mode for multiple artifacts and supports keyboard interaction", async () => {
    const onArtifactInteraction = vi.fn();
    const artifacts: NormalizedArrowArtifact[] = [
      {
        id: "artifact-runtime-e2e-2",
        type: "timeline",
        summary: "Release timeline",
        path: "",
        mime_type: "application/json",
        payload: {
          items: [{ label: "Kickoff", occurred_at: "2026-03-01T00:00:00Z" }],
        },
        payload_bytes: 0,
        payload_truncated: false,
        render_kind: "runtime",
        runtime_eligible: true,
        runtime_skip_reason: undefined,
      },
      {
        id: "artifact-runtime-e2e-3",
        type: "metric_cards",
        summary: "Quarterly metrics",
        path: "",
        mime_type: "application/json",
        payload: {
          metrics: [{ label: "ARR", value: "$1.2M", delta: "+12%" }],
        },
        payload_bytes: 0,
        payload_truncated: false,
        render_kind: "runtime",
        runtime_eligible: true,
        runtime_skip_reason: undefined,
      },
    ];

    render(
      <ArtifactMessageContent
        artifacts={artifacts}
        runtimeEnabled={true}
        onArtifactInteraction={onArtifactInteraction}
      />,
    );

    const navigator = screen.getByTestId("arrow-artifact-navigator");
    expect(navigator).toBeInTheDocument();
    expect(within(navigator).getByRole("button", { name: /Select artifact 1:/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    const secondArtifactButton = screen.getByRole("button", { name: /Select artifact 2:/i });
    fireEvent.click(secondArtifactButton);

    expect(onArtifactInteraction).not.toHaveBeenCalled();

    await waitFor(() => {
      expect(within(navigator).getByRole("button", { name: /Select artifact 2:/i })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    });

    const artifactCard = screen.getByTestId("arrow-artifact-card");
    artifactCard.focus();
    fireEvent.keyDown(artifactCard, { key: "Enter" });

    expect(onArtifactInteraction).toHaveBeenCalledTimes(1);
    expect(onArtifactInteraction).toHaveBeenCalledWith(artifacts[1], 1);
  });

  it("shows lifecycle badges and polite runtime live region updates", async () => {
    const skippedArtifact: NormalizedArrowArtifact = {
      id: "artifact-runtime-skip-1",
      type: "timeline",
      summary: "Fallback timeline",
      path: "",
      mime_type: "application/json",
      payload: {
        items: [{ label: "Kickoff", occurred_at: "2026-03-01T00:00:00Z" }],
      },
      payload_bytes: 0,
      payload_truncated: false,
      render_kind: "runtime",
      runtime_eligible: true,
      runtime_skip_reason: undefined,
    };

    render(
      <ArtifactMessageContent
        artifacts={[skippedArtifact]}
        runtimeEnabled={false}
      />,
    );

    expect(screen.getByTestId("arrow-artifact-runtime-badge-0")).toHaveTextContent("Runtime skipped: Runtime disabled");

    await waitFor(() => {
      expect(screen.getByTestId("arrow-artifact-runtime-live-region")).toHaveTextContent(
        "Artifact 1 runtime skipped: Runtime disabled",
      );
    });
  });

  it("renders structured Nyx artifacts without the runtime sandbox", async () => {
    sandbox.mockClear();

    const artifact: NormalizedArrowArtifact = {
      id: "nyx_component_selection",
      type: "nyx_component_selection",
      summary: "Nyx selection",
      path: "nyx/component-selection",
      mime_type: "application/vnd.metis.nyx+json",
      payload: {
        query: "Use Glow Card in a hero",
        intent_type: "ui_layout_request",
        confidence: 0.92,
        selection_reason: "NyxUI candidates were resolved from the live prompt.",
        matched_signals: ["explicit_nyx", "pattern:card"],
        selected_components: [
          {
            component_name: "glow-card",
            title: "Glow Card",
            description: "Interactive card with glow effects.",
            curated_description: "Accent-heavy card chrome for calls to action.",
            component_type: "registry:ui",
            install_target: "@nyx/glow-card",
            registry_url: "https://nyxui.com/r/glow-card.json",
            source_repo: "https://github.com/MihirJaiswal/nyxui",
            match_score: 42,
            match_reason: "query hint: glow",
            match_reasons: ["query hint: glow"],
            preview_targets: ["components/ui/glow-card.tsx"],
            targets: ["components/ui/glow-card.tsx"],
            file_count: 1,
            required_dependencies: ["clsx"],
            dependencies: ["tailwind-merge"],
            dev_dependencies: [],
            registry_dependencies: [],
          },
        ],
      },
      payload_bytes: 0,
      payload_truncated: false,
      render_kind: "structured",
      runtime_eligible: false,
      runtime_skip_reason: undefined,
    };

    render(<ArtifactMessageContent artifacts={[artifact]} runtimeEnabled={true} />);

    await waitFor(() => {
      expect(screen.getByTestId("nyx-component-selection-artifact")).toBeInTheDocument();
      expect(screen.getByTestId("arrow-artifact-runtime-badge-0")).toHaveTextContent("Structured render");
      expect(screen.getByText("Glow Card")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Open detail" })).toHaveAttribute("href", "/library/glow-card");
      expect(screen.getByRole("link", { name: "Registry JSON" })).toHaveAttribute(
        "href",
        "https://nyxui.com/r/glow-card.json",
      );
    });

    expect(sandbox).not.toHaveBeenCalled();
  });

  it("renders structured forecast artifacts without the runtime sandbox", async () => {
    sandbox.mockClear();

    const artifact: NormalizedArrowArtifact = {
      id: "forecast_report",
      type: "forecast_report",
      summary: "Revenue forecast",
      path: "forecast/revenue.json",
      mime_type: "application/vnd.metis.forecast+json",
      payload: {
        mapping: {
          file_path: "/tmp/revenue.csv",
          file_name: "revenue.csv",
          timestamp_column: "ds",
          target_column: "y",
          dynamic_covariates: ["promo"],
          static_covariates: ["region"],
        },
        metadata: {
          horizon: 4,
          context_used: 24,
          model_backend: "timesfm-2.5-torch",
          model_id: "google/timesfm-2.5-200m-pytorch",
          xreg_mode: "xreg + timesfm",
          frequency: "daily",
        },
        history_points: [
          { timestamp: "2026-03-01T00:00:00", value: 100 },
          { timestamp: "2026-03-02T00:00:00", value: 101 },
        ],
        forecast_points: [
          { timestamp: "2026-03-03T00:00:00", value: 102 },
          { timestamp: "2026-03-04T00:00:00", value: 103 },
        ],
        quantiles: {
          p10: [
            { timestamp: "2026-03-03T00:00:00", value: 98 },
            { timestamp: "2026-03-04T00:00:00", value: 99 },
          ],
          p90: [
            { timestamp: "2026-03-03T00:00:00", value: 106 },
            { timestamp: "2026-03-04T00:00:00", value: 107 },
          ],
        },
        warnings: ["Promo covariate values were forward-filled for one step."],
      },
      payload_bytes: 0,
      payload_truncated: false,
      render_kind: "structured",
      runtime_eligible: false,
      runtime_skip_reason: undefined,
    };

    render(<ArtifactMessageContent artifacts={[artifact]} runtimeEnabled={true} />);

    await waitFor(() => {
      expect(screen.getByTestId("forecast-report-artifact")).toBeInTheDocument();
      expect(screen.getByTestId("arrow-artifact-runtime-badge-0")).toHaveTextContent("Structured render");
      expect(screen.getByText("revenue.csv · ds → y")).toBeInTheDocument();
      expect(screen.getByText("Promo covariate values were forward-filled for one step.")).toBeInTheDocument();
    });

    expect(screen.getByText("promo")).toBeInTheDocument();
    expect(screen.getByText("region")).toBeInTheDocument();
    expect(sandbox).not.toHaveBeenCalled();
  });

  it("omits Nyx detail links when a component has no exported preview route", async () => {
    sandbox.mockClear();

    const artifact: NormalizedArrowArtifact = {
      id: "nyx_component_selection_non_featured",
      type: "nyx_component_selection",
      summary: "Nyx selection",
      path: "nyx/component-selection",
      mime_type: "application/vnd.metis.nyx+json",
      payload: {
        query: "Use Scanner in a capture flow",
        intent_type: "ui_layout_request",
        confidence: 0.74,
        selection_reason: "NyxUI candidates were resolved from the live prompt.",
        matched_signals: ["explicit_nyx", "pattern:capture"],
        selected_components: [
          {
            component_name: "scanner",
            title: "Scanner",
            description: "A scanner component.",
            curated_description: "Compact scanning interface for capture-heavy flows.",
            component_type: "registry:ui",
            install_target: "@nyx/scanner",
            registry_url: "https://nyxui.com/r/scanner.json",
            source_repo: "https://github.com/MihirJaiswal/nyxui",
            match_score: 28,
            match_reason: "query hint: scan",
            match_reasons: ["query hint: scan"],
            preview_targets: ["components/ui/scanner.tsx"],
            targets: ["components/ui/scanner.tsx"],
            file_count: 1,
            required_dependencies: ["react-aria-components"],
            dependencies: ["react-aria-components"],
            dev_dependencies: [],
            registry_dependencies: [],
          },
        ],
      },
      payload_bytes: 0,
      payload_truncated: false,
      render_kind: "structured",
      runtime_eligible: false,
      runtime_skip_reason: undefined,
    };

    render(<ArtifactMessageContent artifacts={[artifact]} runtimeEnabled={true} />);

    await waitFor(() => {
      expect(screen.getByTestId("nyx-component-selection-artifact")).toBeInTheDocument();
      expect(screen.getByText("Scanner")).toBeInTheDocument();
      expect(screen.queryByRole("link", { name: "Open detail" })).not.toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Registry JSON" })).toHaveAttribute(
        "href",
        "https://nyxui.com/r/scanner.json",
      );
    });

    expect(sandbox).not.toHaveBeenCalled();
  });
});
