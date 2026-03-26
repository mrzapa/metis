import {
  ALL_BRAIN_SCOPES,
  NODE_COLOR_HEX,
  NODE_RADIUS_3D,
  SCOPE_LINK_COLOR,
  scopeFromMetadata,
  type BrainEdge,
  type BrainGraphData,
  type BrainNode,
  type BrainScope,
} from "./brain-graph";

export interface BrainSceneNode {
  id: string;
  brain: BrainNode;
  color: string;
  radius: number;
  dimmed: boolean;
  x?: number;
  y?: number;
  z?: number;
}

export interface BrainSceneLink {
  source: string;
  target: string;
  edge: BrainEdge;
  color: string;
  width: number;
}

export interface BrainSceneGraph {
  nodes: BrainSceneNode[];
  links: BrainSceneLink[];
  visibleNodeIds: Set<string>;
  visibleNodeById: Map<string, BrainNode>;
}

interface BuildBrainSceneGraphOptions {
  filter?: string;
  activeScopes?: BrainScope[];
}

export function createActiveScopeSet(activeScopes: BrainScope[] = ALL_BRAIN_SCOPES): Set<BrainScope> {
  return new Set<BrainScope>(activeScopes.length > 0 ? activeScopes : ALL_BRAIN_SCOPES);
}

/** Simple seeded deterministic hash for consistent per-node jitter. */
function simpleHash(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  }
  return h;
}

/**
 * Deterministic neutral seed for force-layout startup.
 *
 * This intentionally avoids anatomy-inspired regions so final topology is
 * driven by links and force simulation rather than fixed semantic buckets.
 */
function initialNodePosition(node: BrainNode, index: number): { x: number; y: number; z: number } {
  const h = simpleHash(node.node_id);
  const azimuth = ((h & 0xffff) / 0xffff) * Math.PI * 2;
  const elevation = ((((h >>> 8) & 0xffff) / 0xffff) - 0.5) * Math.PI;
  const radial = 28 + ((((h >>> 16) & 0xffff) / 0xffff) * 34) + (index % 5) * 1.2;

  const cosEl = Math.cos(elevation);
  return {
    x: Math.cos(azimuth) * cosEl * radial,
    y: Math.sin(elevation) * radial * 0.7,
    z: Math.sin(azimuth) * cosEl * radial,
  };
}

export function buildBrainSceneGraph(
  data: BrainGraphData,
  { filter = "", activeScopes = ALL_BRAIN_SCOPES }: BuildBrainSceneGraphOptions = {},
): BrainSceneGraph {
  const filterLower = filter.trim().toLowerCase();
  const activeScopeSet = createActiveScopeSet(activeScopes);
  const nodes: BrainSceneNode[] = [];
  const visibleNodeIds = new Set<string>();
  const visibleNodeById = new Map<string, BrainNode>();

  for (const node of data.nodes) {
    const scope = scopeFromMetadata(node.metadata);
    if (!activeScopeSet.has(scope)) continue;

    const dimmed = filterLower.length > 0 && !node.label.toLowerCase().includes(filterLower);
    visibleNodeIds.add(node.node_id);
    visibleNodeById.set(node.node_id, node);

    const pos = initialNodePosition(node, nodes.length);

    nodes.push({
      id: node.node_id,
      brain: node,
      color: NODE_COLOR_HEX[node.node_type] ?? "#888888",
      radius: NODE_RADIUS_3D[node.node_type] ?? 4,
      dimmed,
      x: pos.x,
      y: pos.y,
      z: pos.z,
    });
  }

  const links: BrainSceneLink[] = [];
  for (const edge of data.edges) {
    const scope = scopeFromMetadata(edge.metadata);
    if (!activeScopeSet.has(scope)) continue;
    if (!visibleNodeIds.has(edge.source_id) || !visibleNodeIds.has(edge.target_id)) continue;

    links.push({
      source: edge.source_id,
      target: edge.target_id,
      edge,
      color: SCOPE_LINK_COLOR[scope] ?? "rgba(255,255,255,0.15)",
      width: scope === "assistant_learned" ? 1.4 : scope === "assistant_self" ? 1.0 : 0.6,
    });
  }

  return { nodes, links, visibleNodeIds, visibleNodeById };
}
