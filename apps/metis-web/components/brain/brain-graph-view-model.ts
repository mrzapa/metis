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
import { CONSTELLATION_FACULTIES, getFacultyColor } from "@/lib/constellation-home";
import {
  DEFAULT_BRAIN_GRAPH_HIGHLIGHT_TTL_MS,
  type BrainGraphRagActivity,
} from "@/lib/brain-graph-rag-activity";

export interface BrainSceneNode {
  id: string;
  brain: BrainNode;
  color: string;
  baseColor: string;
  radius: number;
  dimmed: boolean;
  facultyId?: string;
  facultyLabel?: string;
  activeStrength: number;
  x?: number;
  y?: number;
  z?: number;
}

export interface BrainSceneLink {
  source: string;
  target: string;
  edge: BrainEdge;
  edgeKey: string;
  color: string;
  width: number;
  weight: number;
  activeStrength: number;
}

export interface BrainSceneGraph {
  nodes: BrainSceneNode[];
  links: BrainSceneLink[];
  visibleNodeIds: Set<string>;
  visibleNodeById: Map<string, BrainNode>;
}

export interface BrainGraphHighlightState {
  nodeIds: Set<string>;
  edgeKeys: Set<string>;
  startedAt: number;
  expiresAt: number;
  ttlMs: number;
}

interface BuildBrainSceneGraphOptions {
  filter?: string;
  activeScopes?: BrainScope[];
  highlight?: BrainGraphHighlightState | null;
  nowMs?: number;
}

export function createActiveScopeSet(activeScopes: BrainScope[] = ALL_BRAIN_SCOPES): Set<BrainScope> {
  return new Set<BrainScope>(activeScopes.length > 0 ? activeScopes : ALL_BRAIN_SCOPES);
}

const FACULTY_LABEL_BY_ID = new Map(
  CONSTELLATION_FACULTIES.map((faculty) => [faculty.id, faculty.label]),
);
const FACULTY_INDEX_BY_ID = new Map(
  CONSTELLATION_FACULTIES.map((faculty, index) => [faculty.id, index]),
);

function getRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function getText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function getStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => String(item || "").trim()).filter(Boolean);
}

function toFacultyHex(facultyId: string): string {
  const [r, g, b] = getFacultyColor(facultyId);
  return `#${[r, g, b]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("")}`;
}

function getBrainEdgeKey(sourceId: string, targetId: string, edgeType: string): string {
  return `${sourceId}::${targetId}::${edgeType}`;
}

function findNodeFacultyId(node: BrainNode): string | undefined {
  const metadata = getRecord(node.metadata);
  const brainPass = getRecord(metadata.brain_pass);
  const brainPassPlacement = getRecord(brainPass.placement);
  const directPlacement = getRecord(metadata.placement);

  const candidates = [
    getText(metadata.faculty_id),
    getText(metadata.primary_domain_id),
    getText(brainPassPlacement.faculty_id),
    getText(directPlacement.faculty_id),
  ];

  for (const candidate of candidates) {
    if (candidate && FACULTY_LABEL_BY_ID.has(candidate)) {
      return candidate;
    }
  }

  return undefined;
}

function getHighlightStrength(
  highlight: BrainGraphHighlightState | null | undefined,
  nowMs: number,
): number {
  if (!highlight) {
    return 0;
  }

  if (nowMs >= highlight.expiresAt) {
    return 0;
  }

  const ttlMs = Math.max(1, highlight.ttlMs);
  const remaining = Math.max(0, highlight.expiresAt - nowMs);
  const decay = remaining / ttlMs;
  const pulse = 0.85 + 0.15 * Math.sin(nowMs / 170);
  return Math.max(0, Math.min(1, decay * pulse));
}

function resolveIndexNodeId(data: BrainGraphData, source: Record<string, unknown>): string | null {
  const metadata = getRecord(source.metadata);
  const relatedNodeIds = getStringArray(metadata.related_node_ids);
  for (const relatedNodeId of relatedNodeIds) {
    if (data.nodes.some((node) => node.node_id === relatedNodeId)) {
      return relatedNodeId;
    }
  }

  const indexIds = [
    getText(metadata.index_id),
    getText(metadata.collection_name),
    getText(source.source),
  ].filter(Boolean);

  for (const indexId of indexIds) {
    const wantedNodeId = `index:${indexId}`;
    if (data.nodes.some((node) => node.node_id === wantedNodeId)) {
      return wantedNodeId;
    }
  }

  const manifestPath = getText(metadata.manifest_path);
  if (manifestPath) {
    const manifestNode = data.nodes.find(
      (node) => getText(getRecord(node.metadata).manifest_path) === manifestPath,
    );
    if (manifestNode) {
      return manifestNode.node_id;
    }
  }

  return null;
}

export function buildHighlightStateFromRagActivity(
  data: BrainGraphData,
  activity: BrainGraphRagActivity,
): BrainGraphHighlightState | null {
  const timestamp = Number.isFinite(activity.timestamp) ? activity.timestamp : Date.now();
  const ttlMs = Math.max(1500, Math.round(activity.ttlMs ?? DEFAULT_BRAIN_GRAPH_HIGHLIGHT_TTL_MS));
  const sources = Array.isArray(activity.sources) ? activity.sources : [];

  const nodeIds = new Set<string>();
  const edgeKeys = new Set<string>();

  const sessionId = String(activity.sessionId || "").trim();
  if (sessionId) {
    nodeIds.add(`session:${sessionId}`);
  }

  const manifestPath = String(activity.manifestPath || "").trim();
  if (manifestPath) {
    const manifestNode = data.nodes.find(
      (node) => getText(getRecord(node.metadata).manifest_path) === manifestPath,
    );
    if (manifestNode) {
      nodeIds.add(manifestNode.node_id);
    }
  }

  for (const source of sources) {
    const resolvedNodeId = resolveIndexNodeId(data, source as unknown as Record<string, unknown>);
    if (resolvedNodeId) {
      nodeIds.add(resolvedNodeId);
    }
  }

  if (nodeIds.size === 0) {
    return null;
  }

  // Add one-hop category trail so retrieval paths visibly connect into the graph hierarchy.
  let addedTrailNode = true;
  while (addedTrailNode) {
    addedTrailNode = false;
    for (const edge of data.edges) {
      if (edge.edge_type !== "category_member") {
        continue;
      }
      if (nodeIds.has(edge.source_id) && !nodeIds.has(edge.target_id)) {
        nodeIds.add(edge.target_id);
        addedTrailNode = true;
      }
    }
  }

  for (const edge of data.edges) {
    if (nodeIds.has(edge.source_id) && nodeIds.has(edge.target_id)) {
      edgeKeys.add(getBrainEdgeKey(edge.source_id, edge.target_id, edge.edge_type));
    }
  }

  return {
    nodeIds,
    edgeKeys,
    startedAt: timestamp,
    expiresAt: timestamp + ttlMs,
    ttlMs,
  };
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

  const facultyId = findNodeFacultyId(node);
  if (facultyId) {
    const facultyIndex = FACULTY_INDEX_BY_ID.get(facultyId) ?? 0;
    const sectors = Math.max(1, CONSTELLATION_FACULTIES.length);
    const baseAngle = (facultyIndex / sectors) * Math.PI * 2;
    const angleJitter = ((((h >>> 5) & 0xffff) / 0xffff) - 0.5) * 0.5;
    const ringJitter = (((h >>> 21) & 0xff) / 0xff) * 16;
    const radial = 48 + ringJitter + (index % 3) * 2.5;
    const y = ((((h >>> 13) & 0xffff) / 0xffff) - 0.5) * 22;
    const azimuth = baseAngle + angleJitter;

    return {
      x: Math.cos(azimuth) * radial,
      y,
      z: Math.sin(azimuth) * radial,
    };
  }

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
  {
    filter = "",
    activeScopes = ALL_BRAIN_SCOPES,
    highlight = null,
    nowMs = Date.now(),
  }: BuildBrainSceneGraphOptions = {},
): BrainSceneGraph {
  const filterLower = filter.trim().toLowerCase();
  const activeScopeSet = createActiveScopeSet(activeScopes);
  const highlightStrength = getHighlightStrength(highlight, nowMs);
  const nodes: BrainSceneNode[] = [];
  const visibleNodeIds = new Set<string>();
  const visibleNodeById = new Map<string, BrainNode>();

  for (const node of data.nodes) {
    const scope = scopeFromMetadata(node.metadata);
    if (!activeScopeSet.has(scope)) continue;

    const dimmed = filterLower.length > 0 && !node.label.toLowerCase().includes(filterLower);
    const facultyId = findNodeFacultyId(node);
    const facultyColor = facultyId ? toFacultyHex(facultyId) : undefined;
    const baseColor = facultyColor ?? NODE_COLOR_HEX[node.node_type] ?? "#888888";
    const activeStrength =
      highlightStrength > 0 && highlight?.nodeIds.has(node.node_id)
        ? highlightStrength
        : 0;
    visibleNodeIds.add(node.node_id);
    visibleNodeById.set(node.node_id, node);

    const pos = initialNodePosition(node, nodes.length);

    nodes.push({
      id: node.node_id,
      brain: node,
      color: baseColor,
      baseColor,
      radius: NODE_RADIUS_3D[node.node_type] ?? 4,
      dimmed,
      facultyId,
      facultyLabel: facultyId ? FACULTY_LABEL_BY_ID.get(facultyId) : undefined,
      activeStrength,
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

    const edgeKey = getBrainEdgeKey(edge.source_id, edge.target_id, edge.edge_type);
    const edgeActiveStrength =
      highlightStrength > 0 && highlight?.edgeKeys.has(edgeKey)
        ? highlightStrength
        : 0;

    const baseWidth =
      (scope === "assistant_learned" ? 1.4 : scope === "assistant_self" ? 1.0 : 0.6) *
      Math.sqrt(Math.max(0.05, edge.weight || 1.0));

    const baseColor = SCOPE_LINK_COLOR[scope] ?? "rgba(255,255,255,0.15)";
    const activeColor = `rgba(255, 229, 138, ${0.35 + edgeActiveStrength * 0.55})`;

    links.push({
      source: edge.source_id,
      target: edge.target_id,
      edge,
      edgeKey,
      color: edgeActiveStrength > 0 ? activeColor : baseColor,
      weight: edge.weight,
      width: baseWidth * (edgeActiveStrength > 0 ? 1.7 + edgeActiveStrength : 1),
      activeStrength: edgeActiveStrength,
    });
  }

  return { nodes, links, visibleNodeIds, visibleNodeById };
}
