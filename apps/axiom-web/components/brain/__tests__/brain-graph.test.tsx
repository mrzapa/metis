import { describe, it, expect } from "vitest";
import "@testing-library/jest-dom/vitest";

import {
  ALL_BRAIN_SCOPES,
  scopeFromMetadata,
  type BrainRenderMode,
  type BrainGraphData,
  type BrainNode,
  type BrainScope,
  NODE_COLOR_HEX,
  NODE_RADIUS_3D,
  SCOPE_LINK_COLOR,
} from "../brain-graph";
import { buildBrainSceneGraph } from "../brain-graph-view-model";

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
  it("exports every supported brain scope and render mode", () => {
    const renderModes: BrainRenderMode[] = ["hybrid", "raw"];

    expect(ALL_BRAIN_SCOPES).toEqual(["workspace", "assistant_self", "assistant_learned"]);
    expect(renderModes).toEqual(["hybrid", "raw"]);
  });

  it("returns workspace scope for nodes without explicit scope metadata", () => {
    expect(scopeFromMetadata(graphData.nodes[0].metadata)).toBe("workspace");
  });

  it("returns assistant_self for nodes with that scope", () => {
    expect(scopeFromMetadata(graphData.nodes[1].metadata)).toBe("assistant_self");
  });

  it("returns assistant_learned for nodes with that scope", () => {
    expect(scopeFromMetadata(graphData.nodes[2].metadata)).toBe("assistant_learned");
  });

  it("filters nodes by active scopes correctly", () => {
    const activeScopes: BrainScope[] = ["assistant_self"];
    const activeScopeSet = new Set<BrainScope>(activeScopes);

    const visible = graphData.nodes.filter((node: BrainNode) =>
      activeScopeSet.has(scopeFromMetadata(node.metadata)),
    );

    expect(visible).toHaveLength(1);
    expect(visible[0].label).toBe("Companion Memory");
  });

  it("provides color and radius mappings for all node types", () => {
    const types: BrainNode["node_type"][] = [
      "category", "index", "session", "assistant", "memory", "playbook",
    ];
    for (const t of types) {
      expect(NODE_COLOR_HEX[t]).toBeDefined();
      expect(NODE_RADIUS_3D[t]).toBeGreaterThan(0);
    }
  });

  it("provides link color mappings for all scopes", () => {
    const scopes: BrainScope[] = ["workspace", "assistant_self", "assistant_learned"];
    for (const s of scopes) {
      expect(SCOPE_LINK_COLOR[s]).toBeDefined();
    }
  });

  it("builds a scene graph that filters by scope without hiding dimmed label mismatches", () => {
    const sceneGraph = buildBrainSceneGraph(graphData, {
      filter: "workspace",
      activeScopes: ["workspace", "assistant_self"],
    });

    expect(sceneGraph.nodes).toHaveLength(2);
    expect(sceneGraph.visibleNodeIds.has("workspace-1")).toBe(true);
    expect(sceneGraph.visibleNodeIds.has("assistant-1")).toBe(true);
    expect(sceneGraph.visibleNodeIds.has("learned-1")).toBe(false);
    expect(sceneGraph.nodes.find((node) => node.id === "workspace-1")?.dimmed).toBe(false);
    expect(sceneGraph.nodes.find((node) => node.id === "assistant-1")?.dimmed).toBe(true);
  });
});
