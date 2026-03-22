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
  /** Fixed x position – prevents force simulation from moving the node. */
  fx?: number;
  /** Fixed y position – prevents force simulation from moving the node. */
  fy?: number;
  /** Fixed z position – prevents force simulation from moving the node. */
  fz?: number;
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

/**
 * Map node types to anatomically-inspired brain regions.
 *
 * Each region is defined by a centre (x,y,z) and a spread radius.  Nodes of
 * a given type are scattered within their designated region so that the
 * force-directed layout seeds them in a meaningful location:
 *
 *  - category  → Prefrontal cortex (front-top): executive/organisational
 *  - index     → Temporal lobes (sides): information storage & retrieval
 *  - session   → Hippocampus (center-lower): recent memory / conversation
 *  - assistant → Thalamus (center): core identity relay
 *  - memory    → Parietal lobe (upper-back): long-term memory
 *  - playbook  → Cerebellum (lower-back): procedural / learned routines
 */
const BRAIN_REGION: Record<BrainNode["node_type"], { cx: number; cy: number; cz: number; spread: number }> = {
  category:  { cx:  0,   cy:  35,  cz:  40,  spread: 25 },
  index:     { cx:  0,   cy: -5,   cz:  0,   spread: 30 },
  session:   { cx:  0,   cy: -15,  cz:  10,  spread: 20 },
  assistant: { cx:  0,   cy:  5,   cz:  0,   spread: 15 },
  memory:    { cx:  0,   cy:  25,  cz: -30,  spread: 25 },
  playbook:  { cx:  0,   cy: -35,  cz: -25,  spread: 20 },
};

/** Simple seeded deterministic hash for consistent per-node jitter. */
function simpleHash(str: string): number {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  }
  return h;
}

/** Map a node to an initial position inside its brain-region. */
function brainRegionPosition(
  node: BrainNode,
  typeIndex: number,
): { x: number; y: number; z: number } {
  const region = BRAIN_REGION[node.node_type] ?? BRAIN_REGION.index;
  const h = simpleHash(node.node_id);

  // Deterministic but varied offset based on node id and type index
  const angle = ((h & 0xffff) / 0xffff) * Math.PI * 2;
  const r = region.spread * (0.3 + 0.7 * (((h >>> 16) & 0xffff) / 0xffff));
  const verticalJitter = ((typeIndex * 7 + (h & 0xff)) % 17 - 8) * 1.5;

  // For indexes, alternate left/right hemisphere placement
  const sideSign = node.node_type === "index" ? (typeIndex % 2 === 0 ? 1 : -1) : 1;

  return {
    x: region.cx + Math.cos(angle) * r * sideSign,
    y: region.cy + verticalJitter,
    z: region.cz + Math.sin(angle) * r,
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

  // Track per-type index for position variation
  const typeCounters: Record<string, number> = {};

  for (const node of data.nodes) {
    const scope = scopeFromMetadata(node.metadata);
    if (!activeScopeSet.has(scope)) continue;

    const dimmed = filterLower.length > 0 && !node.label.toLowerCase().includes(filterLower);
    visibleNodeIds.add(node.node_id);
    visibleNodeById.set(node.node_id, node);

    const typeIdx = typeCounters[node.node_type] ?? 0;
    typeCounters[node.node_type] = typeIdx + 1;

    const pos = brainRegionPosition(node, typeIdx);

    nodes.push({
      id: node.node_id,
      brain: node,
      color: NODE_COLOR_HEX[node.node_type] ?? "#888888",
      radius: NODE_RADIUS_3D[node.node_type] ?? 4,
      dimmed,
      x: pos.x,
      y: pos.y,
      z: pos.z,
      fx: pos.x,
      fy: pos.y,
      fz: pos.z,
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
