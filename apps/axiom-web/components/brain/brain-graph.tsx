/**
 * BrainGraph shared types and helpers.
 *
 * The actual 3D visualisation lives in ./brain-graph-3d.tsx and is loaded
 * with next/dynamic (ssr: false) by the brain page because it depends on
 * WebGL / Three.js which are unavailable during server-side rendering.
 */

// -- Types ---------------------------------------------------------------

export interface BrainNode {
  node_id: string;
  node_type: "category" | "index" | "session" | "assistant" | "memory" | "playbook";
  label: string;
  x: number;
  y: number;
  metadata: Record<string, unknown>;
}

export interface BrainEdge {
  source_id: string;
  target_id: string;
  edge_type: string;
  metadata: Record<string, unknown>;
}

export interface BrainGraphData {
  nodes: BrainNode[];
  edges: BrainEdge[];
}

export type BrainScope = "workspace" | "assistant_self" | "assistant_learned";
export type BrainRenderMode = "hybrid" | "raw";

export const ALL_BRAIN_SCOPES: BrainScope[] = [
  "workspace",
  "assistant_self",
  "assistant_learned",
];

// -- Helpers -------------------------------------------------------------

export function scopeFromMetadata(metadata: Record<string, unknown>): BrainScope {
  const raw = metadata.scope;
  return raw === "assistant_self" || raw === "assistant_learned" ? raw : "workspace";
}

// -- Visual constants (shared between the 3D renderer and the page) ------

export const NODE_COLOR_HEX: Record<BrainNode["node_type"], string> = {
  category: "#6366f1",
  index: "#0969da",
  session: "#2da44e",
  assistant: "#e3b341",
  memory: "#a371f7",
  playbook: "#db61a2",
};

export const NODE_RADIUS_3D: Record<BrainNode["node_type"], number> = {
  category: 7,
  index: 5,
  session: 4,
  assistant: 6,
  memory: 4.5,
  playbook: 4.5,
};

export const SCOPE_LINK_COLOR: Record<BrainScope, string> = {
  workspace: "rgba(255,255,255,0.18)",
  assistant_self: "rgba(227,179,65,0.4)",
  assistant_learned: "rgba(163,113,247,0.5)",
};
