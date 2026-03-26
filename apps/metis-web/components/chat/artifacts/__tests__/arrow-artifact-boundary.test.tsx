/**
 * @vitest-environment happy-dom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { ArrowArtifactBoundary } from "@/components/chat/artifacts/arrow-artifact-boundary";

const { emitArtifactTelemetry } = vi.hoisted(() => ({
  emitArtifactTelemetry: vi.fn(),
}));

const { sandbox } = vi.hoisted(() => ({
  sandbox: vi.fn((props: { source?: Record<string, string> }) => {
    return (parent: ParentNode) => {
      const host = parent as HTMLElement;
      const source = props.source?.["main.ts"] ?? "";
      const title = source.includes("Timeline") ? "Timeline" : source.includes("Metrics") ? "Metrics" : "Artifact";
      const labelMatch = source.match(/\"label\":\"([^\"]+)\"/);

      const container = document.createElement("div");
      const titleNode = document.createElement("p");
      titleNode.textContent = title;
      const labelNode = document.createElement("p");
      labelNode.textContent = labelMatch?.[1] ?? "";
      container.append(titleNode, labelNode);

      host.replaceChildren(container);
      return parent;
    };
  }),
}));

vi.mock("@/lib/telemetry/ui-telemetry", async () => {
  const actual = await vi.importActual<typeof import("@/lib/telemetry/ui-telemetry")>(
    "@/lib/telemetry/ui-telemetry",
  );
  return {
    ...actual,
    emitArtifactTelemetry,
  };
});

vi.mock("@arrow-js/sandbox", () => ({ sandbox }));

describe("ArrowArtifactBoundary", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    emitArtifactTelemetry.mockReset();
  });

  it("falls back to markdown when there are no artifacts", () => {
    render(<ArrowArtifactBoundary content="Plain markdown response" />);

    expect(screen.getByText("Plain markdown response")).toBeInTheDocument();
  });

  it("renders artifact content when payload is valid", () => {
    render(
      <ArrowArtifactBoundary
        content="Should not be shown"
        artifacts={[
          {
            type: "timeline",
            summary: "Milestones",
            payload: {
              items: [{ label: "Kickoff", detail: "Project started", occurred_at: "2026-03-01T00:00:00Z" }],
            },
          },
        ]}
        runId="run-1"
        sessionId="session-1"
        messageId="message-1"
      />,
    );

    return waitFor(() => {
      expect(screen.getByText("Timeline")).toBeInTheDocument();
      expect(screen.getByText("Kickoff")).toBeInTheDocument();
      expect(screen.queryByText("Should not be shown")).not.toBeInTheDocument();
    });
  });

  it("emits runtime success lifecycle telemetry for supported artifacts", async () => {
    render(
      <ArrowArtifactBoundary
        content="Should not be shown"
        artifacts={[
          {
            id: "artifact-runtime-1",
            type: "timeline",
            payload: { items: [{ label: "Kickoff", occurred_at: "2026-03-01T00:00:00Z" }] },
          },
        ]}
        runId="run-runtime-success"
      />,
    );

    await waitFor(() => {
      expect(emitArtifactTelemetry).toHaveBeenCalledWith(
        expect.objectContaining({
          event_name: "artifact_runtime_success",
          payload: expect.objectContaining({
            artifact_index: 0,
            artifact_id: "artifact-runtime-1",
            artifact_type: "timeline",
          }),
        }),
      );
    });
  });

  it("emits runtime skipped telemetry for unsupported and runtime-disabled artifacts", async () => {
    render(
      <ArrowArtifactBoundary
        content="Should not be shown"
        artifacts={[{ type: "unknown_type", summary: "Fallback card" }]}
        runId="run-runtime-skip-unsupported"
      />,
    );

    await waitFor(() => {
      expect(emitArtifactTelemetry).toHaveBeenCalledWith(
        expect.objectContaining({
          event_name: "artifact_runtime_skipped",
          payload: expect.objectContaining({
            artifact_index: 0,
            artifact_type: "unknown_type",
            reason: "unsupported_type",
          }),
        }),
      );
    });

    emitArtifactTelemetry.mockReset();

    render(
      <ArrowArtifactBoundary
        content="Should not be shown"
        artifacts={[
          {
            type: "timeline",
            summary: "Fallback card when runtime off",
            payload: { items: [{ label: "Kickoff", occurred_at: "2026-03-01T00:00:00Z" }] },
          },
        ]}
        artifactsEnabled={true}
        artifactRuntimeEnabled={false}
        runId="run-runtime-skip-disabled"
      />,
    );

    await waitFor(() => {
      expect(emitArtifactTelemetry).toHaveBeenCalledWith(
        expect.objectContaining({
          event_name: "artifact_runtime_skipped",
          payload: expect.objectContaining({
            artifact_type: "timeline",
            reason: "runtime_disabled",
          }),
        }),
      );
    });
  });

  it("falls back per artifact and emits runtime failure telemetry when runtime render throws", async () => {
    render(
      <ArrowArtifactBoundary
        content="Should not be shown"
        artifacts={[
          {
            type: "timeline",
            summary: "Fallback timeline",
            payload: {
              items: [{ label: "Broken Date", occurred_at: "not-a-date" }],
            },
          },
        ]}
        runId="run-runtime-failure"
      />,
    );

    expect(screen.getByText("Fallback timeline")).toBeInTheDocument();

    await waitFor(() => {
      expect(emitArtifactTelemetry).toHaveBeenCalledWith(
        expect.objectContaining({
          event_name: "artifact_runtime_failure",
          payload: expect.objectContaining({
            artifact_index: 0,
            artifact_type: "timeline",
            error_name: "RangeError",
          }),
        }),
      );
    });
  });

  it("falls back to markdown when artifacts are malformed", async () => {
    render(
      <ArrowArtifactBoundary
        content="Fallback markdown"
        artifacts={[{ summary: "missing type" }]}
        runId="run-2"
      />,
    );

    expect(screen.getByText("Fallback markdown")).toBeInTheDocument();
    expect(screen.queryByTestId("arrow-artifact-card")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(emitArtifactTelemetry).toHaveBeenCalledWith(
        expect.objectContaining({
          event_name: "artifact_render_fallback_markdown",
          payload: { reason: "invalid_payload" },
        }),
      );
    });
  });

  it("falls back to markdown when feature is disabled", async () => {
    render(
      <ArrowArtifactBoundary
        content="Feature off markdown"
        artifacts={[{ type: "timeline", summary: "Milestones" }]}
        artifactsEnabled={false}
        runId="run-3"
      />,
    );

    expect(screen.getByText("Feature off markdown")).toBeInTheDocument();
    expect(screen.queryByTestId("arrow-artifact-card")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(emitArtifactTelemetry).toHaveBeenCalledWith(
        expect.objectContaining({
          event_name: "artifact_boundary_flag_state",
          payload: { state: "disabled" },
        }),
      );
    });
  });

  it("falls back to markdown when artifact renderer throws", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(
      <ArrowArtifactBoundary
        content="Recovered markdown"
        artifacts={[{ type: "timeline", summary: "Milestones" }]}
        runId="run-4"
        renderArtifacts={() => {
          throw new Error("renderer failed");
        }}
      />,
    );

    expect(screen.getByText("Recovered markdown")).toBeInTheDocument();
    expect(screen.queryByTestId("arrow-artifact-card")).not.toBeInTheDocument();
    expect(consoleError).toHaveBeenCalled();
    await waitFor(() => {
      expect(emitArtifactTelemetry).toHaveBeenCalledWith(
        expect.objectContaining({
          event_name: "artifact_render_failure",
          payload: expect.objectContaining({ error_name: "Error", renderer: "custom" }),
        }),
      );
    });
  });

  it("emits interaction telemetry when an artifact card is clicked", async () => {
    render(
      <ArrowArtifactBoundary
        content="Should not be shown"
        artifacts={[{ id: "artifact-1", type: "timeline", summary: "Milestones" }]}
        runId="run-5"
        sessionId="session-5"
        messageId="message-5"
      />,
    );

    fireEvent.click(screen.getByTestId("arrow-artifact-card"));

    await waitFor(() => {
      expect(emitArtifactTelemetry).toHaveBeenCalledWith(
        expect.objectContaining({
          event_name: "artifact_interaction",
          payload: expect.objectContaining({
            interaction_type: "card_click",
            artifact_id: "artifact-1",
            artifact_type: "timeline",
          }),
        }),
      );
    });
  });

  it("emits interaction telemetry when an artifact card is activated with Enter", async () => {
    render(
      <ArrowArtifactBoundary
        content="Should not be shown"
        artifacts={[{ id: "artifact-2", type: "timeline", summary: "Milestones" }]}
        runId="run-6"
        sessionId="session-6"
        messageId="message-6"
      />,
    );

    const card = screen.getByRole("button", { name: /Artifact 1:/i });
    card.focus();
    fireEvent.keyDown(card, { key: "Enter" });

    await waitFor(() => {
      expect(emitArtifactTelemetry).toHaveBeenCalledWith(
        expect.objectContaining({
          event_name: "artifact_interaction",
          payload: expect.objectContaining({
            interaction_type: "card_click",
            artifact_id: "artifact-2",
            artifact_type: "timeline",
          }),
        }),
      );
    });
  });
});
