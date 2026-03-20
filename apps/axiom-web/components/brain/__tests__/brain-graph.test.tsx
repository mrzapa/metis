import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { BrainGraph, type BrainGraphData, type BrainScope } from "../brain-graph";

const graphData: BrainGraphData = {
  nodes: [
    {
      node_id: "workspace-1",
      node_type: "index",
      label: "Workspace Index",
      x: 0,
      y: 0,
      metadata: {},
    },
    {
      node_id: "assistant-1",
      node_type: "assistant",
      label: "Companion Memory",
      x: 160,
      y: 0,
      metadata: { scope: "assistant_self" },
    },
    {
      node_id: "learned-1",
      node_type: "playbook",
      label: "Learned Playbook",
      x: 320,
      y: 0,
      metadata: { scope: "assistant_learned" },
    },
  ],
  edges: [],
};

describe("BrainGraph scope filtering", () => {
  it("shows only the requested companion scope", () => {
    const assistantOnlyScopes: BrainScope[] = ["assistant_self"];

    render(<BrainGraph data={graphData} activeScopes={assistantOnlyScopes} />);

    expect(screen.queryByText("Workspace Index")).not.toBeInTheDocument();
    expect(screen.getByText("Companion Memory")).toBeInTheDocument();
    expect(screen.queryByText("Learned Playbook")).not.toBeInTheDocument();
  });
});
