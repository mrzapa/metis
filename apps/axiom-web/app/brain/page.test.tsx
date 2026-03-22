import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";

vi.mock("next/dynamic", () => ({
  default: () =>
    function MockBrainGraph3D(props: {
      renderMode?: string;
      selectedNodeId?: string | null;
      onSelectedNodeIdChange?: (nodeId: string | null) => void;
      onModelLoadError?: (message: string) => void;
    }) {
      return (
        <div
          data-testid="brain-graph-3d"
          data-render-mode={props.renderMode}
          data-selected-node-id={props.selectedNodeId ?? ""}
        >
          <button
            type="button"
            onClick={() => props.onSelectedNodeIdChange?.("workspace-1")}
          >
            Select workspace node
          </button>
          <button
            type="button"
            onClick={() => props.onModelLoadError?.("brain model missing")}
          >
            Trigger model failure
          </button>
        </div>
      );
    },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/brain",
}));

vi.mock("@/lib/api", () => ({
  fetchBrainGraph: vi.fn(),
  fetchAssistantStatus: vi.fn(),
  subscribeCompanionActivity: vi.fn(() => () => {}),
}));

const { fetchAssistantStatus, fetchBrainGraph } = await import("@/lib/api");
const { default: BrainPage } = await import("./page");

const graphData = {
  nodes: [
    {
      node_id: "workspace-1",
      node_type: "index" as const,
      label: "Workspace Index",
      x: 0,
      y: 0,
      metadata: {},
    },
    {
      node_id: "assistant-1",
      node_type: "assistant" as const,
      label: "Companion Self",
      x: 120,
      y: 40,
      metadata: { scope: "assistant_self" },
    },
  ],
  edges: [],
};

describe("BrainPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchBrainGraph).mockResolvedValue(graphData);
    vi.mocked(fetchAssistantStatus).mockResolvedValue({
      state: "idle",
      paused: false,
      runtime_ready: true,
      runtime_source: "settings",
      runtime_provider: "openai",
      runtime_model: "gpt-5.3-codex",
      bootstrap_state: "ready",
      bootstrap_message: "",
      recommended_model_name: "",
      recommended_quant: "",
      recommended_use_case: "",
      last_reflection_at: "",
      last_reflection_trigger: "manual",
      latest_summary: "",
      latest_why: "",
    });
  });

  it("switches render modes and falls back to raw mode after a model error", async () => {
    render(<BrainPage />);

    const graph = await screen.findByTestId("brain-graph-3d");
    expect(graph).toHaveAttribute("data-render-mode", "hybrid");

    fireEvent.click(screen.getByRole("button", { name: "Graph only" }));
    expect(screen.getByTestId("brain-graph-3d")).toHaveAttribute("data-render-mode", "raw");

    fireEvent.click(screen.getByRole("button", { name: "Hybrid" }));
    expect(screen.getByTestId("brain-graph-3d")).toHaveAttribute("data-render-mode", "hybrid");

    fireEvent.click(screen.getByRole("button", { name: "Trigger model failure" }));

    expect(screen.getByTestId("brain-graph-3d")).toHaveAttribute("data-render-mode", "raw");
    expect(
      screen.getByText(/Hybrid mode fell back to the raw graph: brain model missing/i),
    ).toBeInTheDocument();
  });

  it("pins a selected node and clears it when that scope becomes hidden", async () => {
    render(<BrainPage />);

    const graphs = await screen.findAllByTestId("brain-graph-3d");
    fireEvent.click(within(graphs[0]!).getByRole("button", { name: "Select workspace node" }));

    expect((await screen.findAllByText("Workspace Index")).length).toBeGreaterThan(0);
    expect(graphs[0]).toHaveAttribute(
      "data-selected-node-id",
      "workspace-1",
    );

    fireEvent.click(screen.getAllByRole("button", { name: "Workspace" })[0]!);

    await waitFor(() => {
      expect(screen.getAllByText("Select a node to inspect its metadata").length).toBeGreaterThan(0);
      expect(graphs[0]).toHaveAttribute("data-selected-node-id", "");
    });
  });
});
