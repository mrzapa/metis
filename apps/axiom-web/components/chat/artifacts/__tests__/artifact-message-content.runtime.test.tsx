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
});
