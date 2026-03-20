"use client";

/**
 * BrainGraph - interactive SVG graph visualisation of indexes, sessions,
 * and categories. Supports zoom/pan, node drag, tooltip on hover, and
 * click-to-select with a detail side-panel.
 *
 * Data is fetched from GET /v1/brain/graph and rendered as an SVG force
 * layout (positions are computed by the backend's apply_force_layout()).
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";

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

// -- Visual constants ----------------------------------------------------

const NODE_RADIUS: Record<BrainNode["node_type"], number> = {
  category: 26,
  index: 18,
  session: 14,
  assistant: 22,
  memory: 17,
  playbook: 17,
};

const NODE_COLOR: Record<BrainNode["node_type"], string> = {
  category: "var(--color-accent)",
  index: "var(--color-primary)",
  session: "var(--color-chart-2)",
  assistant: "var(--color-chart-3)",
  memory: "var(--color-chart-4)",
  playbook: "var(--color-chart-5)",
};

const NODE_SCOPE_STROKE: Record<BrainScope, string> = {
  workspace: "var(--color-border)",
  assistant_self: "var(--color-chart-3)",
  assistant_learned: "var(--color-chart-4)",
};

const SCOPE_LABEL: Record<BrainScope, string> = {
  workspace: "Workspace",
  assistant_self: "Axiom Self",
  assistant_learned: "Assistant-Learned",
};

const SCOPE_EDGE_STYLE: Record<
  BrainScope,
  { stroke: string; width: number; opacity: number; dash?: string; marker?: string }
> = {
  workspace: {
    stroke: "var(--color-border)",
    width: 1,
    opacity: 0.55,
  },
  assistant_self: {
    stroke: "var(--color-chart-3)",
    width: 1.25,
    opacity: 0.75,
  },
  assistant_learned: {
    stroke: "var(--color-chart-4)",
    width: 1.7,
    opacity: 0.9,
    dash: "7 5",
    marker: "url(#arrow-learned)",
  },
};

const ALL_SCOPES: BrainScope[] = ["workspace", "assistant_self", "assistant_learned"];
const GRAPH_PADDING = 72;
const GRAPH_SCALE_CAP_DESKTOP = 2.25;
const GRAPH_SCALE_CAP_MOBILE = 1.85;

// -- Extracted inline styles (avoid object allocation per render) ---------

const STYLE_OPACITY_TRANSITION: React.CSSProperties = { transition: "opacity 0.2s" };
const STYLE_CIRCLE: React.CSSProperties = {
  transition: "r 0.15s, fill-opacity 0.15s",
  cursor: "pointer",
};
const STYLE_LABEL: React.CSSProperties = { pointerEvents: "none", userSelect: "none" };
const STYLE_TOOLTIP_TEXT: React.CSSProperties = { pointerEvents: "none" };

// -- Helpers -------------------------------------------------------------

function worldBounds(nodes: BrainNode[]): {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
} {
  if (nodes.length === 0) return { minX: -200, minY: -200, maxX: 200, maxY: 200 };
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const n of nodes) {
    if (n.x < minX) minX = n.x;
    if (n.y < minY) minY = n.y;
    if (n.x > maxX) maxX = n.x;
    if (n.y > maxY) maxY = n.y;
  }
  return { minX, minY, maxX, maxY };
}

function scopeFromMetadata(metadata: Record<string, unknown>): BrainScope {
  const raw = metadata.scope;
  return raw === "assistant_self" || raw === "assistant_learned" ? raw : "workspace";
}

// -- Component -----------------------------------------------------------

interface BrainGraphProps {
  data: BrainGraphData;
  /** Text filter - nodes whose labels don't match are dimmed. */
  filter?: string;
  activeScopes?: BrainScope[];
  onNodeSelect?: (node: BrainNode | null) => void;
  className?: string;
}

export function BrainGraph({
  data,
  filter = "",
  activeScopes = ALL_SCOPES,
  onNodeSelect,
  className = "",
}: BrainGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  // View transform (pan + zoom)
  const [transform, setTransform] = useState({ tx: 0, ty: 0, scale: 1 });

  // Node positions (may be overridden by drag)
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }>>(new Map());

  // Interaction state
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  // -- Refs mirroring state so callbacks stay stable -----------------------
  const transformRef = useRef(transform);
  useEffect(() => { transformRef.current = transform; }, [transform]);

  const positionsRef = useRef(positions);
  useEffect(() => { positionsRef.current = positions; }, [positions]);

  const selectedIdRef = useRef(selectedId);
  useEffect(() => { selectedIdRef.current = selectedId; }, [selectedId]);

  // Drag state stored in a ref so pointer-move handlers are always current
  const dragRef = useRef<{
    nodeId: string;
    startPx: number;
    startPy: number;
    startNx: number;
    startNy: number;
  } | null>(null);

  // Pan state
  const panRef = useRef<{
    startPx: number;
    startPy: number;
    startTx: number;
    startTy: number;
  } | null>(null);

  // RAF handle for pointer-move throttling
  const rafRef = useRef<number>(0);

  // Seed positions from graph data whenever data changes
  useEffect(() => {
    const map = new Map<string, { x: number; y: number }>();
    for (const n of data.nodes) {
      map.set(n.node_id, { x: n.x, y: n.y });
    }
    const frame = requestAnimationFrame(() => {
      setPositions(map);
    });
    return () => cancelAnimationFrame(frame);
  }, [data]);

  // Fit the graph to the viewport on initial load / data change
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || data.nodes.length === 0) return;
    const { minX, minY, maxX, maxY } = worldBounds(data.nodes);
    const w = svg.clientWidth || 800;
    const h = svg.clientHeight || 600;
    const padding = Math.max(GRAPH_PADDING, Math.min(104, Math.min(w, h) * 0.1));
    const gw = maxX - minX + padding * 2;
    const gh = maxY - minY + padding * 2;
    const scaleCap = w > 1280 || h > 860 ? GRAPH_SCALE_CAP_DESKTOP : GRAPH_SCALE_CAP_MOBILE;
    const scale = Math.min(w / gw, h / gh, scaleCap);
    const tx = w / 2 - ((minX + maxX) / 2) * scale;
    const ty = h / 2 - ((minY + maxY) / 2) * scale;
    const frame = requestAnimationFrame(() => {
      setTransform({ tx, ty, scale });
    });
    return () => cancelAnimationFrame(frame);
  }, [data]);

  // -- Wheel zoom --------------------------------------------------------
  const handleWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.1 : 0.91;
    setTransform((prev) => {
      const newScale = Math.max(0.15, Math.min(8, prev.scale * factor));
      const ratio = newScale / prev.scale;
      return {
        scale: newScale,
        tx: e.offsetX - ratio * (e.offsetX - prev.tx),
        ty: e.offsetY - ratio * (e.offsetY - prev.ty),
      };
    });
  }, []);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    svg.addEventListener("wheel", handleWheel, { passive: false });
    return () => svg.removeEventListener("wheel", handleWheel);
  }, [handleWheel]);

  // -- SVG background pan -----------------------------------------------
  const onBgPointerDown = useCallback(
    (e: ReactPointerEvent<SVGElement>) => {
      if (e.button !== 0) return;
      const t = transformRef.current;
      panRef.current = {
        startPx: e.clientX,
        startPy: e.clientY,
        startTx: t.tx,
        startTy: t.ty,
      };
      (e.target as SVGElement).setPointerCapture(e.pointerId);
    },
    [],
  );

  const onBgPointerMove = useCallback((e: ReactPointerEvent<SVGElement>) => {
    if (!panRef.current) return;
    const dx = e.clientX - panRef.current.startPx;
    const dy = e.clientY - panRef.current.startPy;
    const stx = panRef.current.startTx;
    const sty = panRef.current.startTy;
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      setTransform((prev) => ({ ...prev, tx: stx + dx, ty: sty + dy }));
    });
  }, []);

  const onBgPointerUp = useCallback(() => {
    panRef.current = null;
  }, []);

  // -- Node drag ---------------------------------------------------------
  const onNodePointerDown = useCallback(
    (e: ReactPointerEvent<SVGCircleElement>, nodeId: string) => {
      e.stopPropagation();
      const pos = positionsRef.current.get(nodeId) ?? { x: 0, y: 0 };
      dragRef.current = {
        nodeId,
        startPx: e.clientX,
        startPy: e.clientY,
        startNx: pos.x,
        startNy: pos.y,
      };
      (e.target as SVGElement).setPointerCapture(e.pointerId);
    },
    [],
  );

  const onNodePointerMove = useCallback(
    (e: ReactPointerEvent<SVGCircleElement>) => {
      if (!dragRef.current) return;
      const s = transformRef.current.scale;
      const dx = (e.clientX - dragRef.current.startPx) / s;
      const dy = (e.clientY - dragRef.current.startPy) / s;
      const nid = dragRef.current.nodeId;
      const snx = dragRef.current.startNx;
      const sny = dragRef.current.startNy;
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        setPositions((prev) => {
          const next = new Map(prev);
          next.set(nid, { x: snx + dx, y: sny + dy });
          return next;
        });
      });
    },
    [],
  );

  const onNodePointerUp = useCallback(
    (e: ReactPointerEvent<SVGCircleElement>, nodeId: string) => {
      e.stopPropagation();
      const wasDrag =
        dragRef.current &&
        (Math.abs(e.clientX - dragRef.current.startPx) > 4 ||
          Math.abs(e.clientY - dragRef.current.startPy) > 4);
      dragRef.current = null;
      if (!wasDrag) {
        const node = data.nodes.find((n) => n.node_id === nodeId) ?? null;
        const nextSelectedId = selectedIdRef.current === nodeId ? null : nodeId;
        setSelectedId(nextSelectedId);
        onNodeSelect?.(nextSelectedId ? node : null);
      }
    },
    [data.nodes, onNodeSelect],
  );

  // -- Filtering (memoised) ---------------------------------------------
  const filterLower = useMemo(() => filter.trim().toLowerCase(), [filter]);

  const activeScopeSet = useMemo(
    () => new Set(activeScopes.length > 0 ? activeScopes : ALL_SCOPES),
    [activeScopes],
  );

  const nodeById = useMemo(
    () => new Map(data.nodes.map((node) => [node.node_id, node] as const)),
    [data.nodes],
  );

  const matchNode = useCallback(
    (n: BrainNode) => !filterLower || n.label.toLowerCase().includes(filterLower),
    [filterLower],
  );

  const isVisibleNode = useCallback(
    (node: BrainNode) => activeScopeSet.has(scopeFromMetadata(node.metadata)),
    [activeScopeSet],
  );

  const isVisibleEdge = useCallback(
    (edge: BrainEdge) => activeScopeSet.has(scopeFromMetadata(edge.metadata)),
    [activeScopeSet],
  );

  useEffect(() => {
    if (!selectedId) return;
    const selectedNode = data.nodes.find((node) => node.node_id === selectedId) ?? null;
    const visibleScopes = new Set(activeScopes.length > 0 ? activeScopes : ALL_SCOPES);
    const selectedScope = selectedNode ? scopeFromMetadata(selectedNode.metadata) : null;
    if (!selectedNode || !selectedScope || !visibleScopes.has(selectedScope)) {
      const frame = requestAnimationFrame(() => {
        setSelectedId(null);
        onNodeSelect?.(null);
      });
      return () => cancelAnimationFrame(frame);
    }
  }, [activeScopes, data.nodes, onNodeSelect, selectedId]);

  // Clean up pending RAF on unmount
  useEffect(() => {
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  // -- Render ------------------------------------------------------------
  const { tx, ty, scale } = transform;

  return (
    <svg
      ref={svgRef}
      className={`h-full w-full select-none cursor-grab active:cursor-grabbing ${className}`}
      onPointerDown={onBgPointerDown}
      onPointerMove={onBgPointerMove}
      onPointerUp={onBgPointerUp}
      onPointerCancel={onBgPointerUp}
      aria-label="Brain graph"
      shapeRendering="geometricPrecision"
    >
      <defs>
        <radialGradient id="brain-canvas-glow" cx="50%" cy="42%" r="65%">
          <stop offset="0%" stopColor="rgba(9,105,218,0.24)" />
          <stop offset="35%" stopColor="rgba(9,105,218,0.1)" />
          <stop offset="72%" stopColor="rgba(0,0,0,0)" />
        </radialGradient>
        <radialGradient id="brain-canvas-vignette" cx="50%" cy="50%" r="65%">
          <stop offset="0%" stopColor="rgba(255,255,255,0.02)" />
          <stop offset="100%" stopColor="rgba(0,0,0,0.42)" />
        </radialGradient>
        <pattern id="brain-canvas-grid" width="72" height="72" patternUnits="userSpaceOnUse">
          <path
            d="M 72 0 L 0 0 0 72"
            fill="none"
            stroke="rgba(255,255,255,0.12)"
            strokeWidth="1"
          />
        </pattern>
        <filter id="brain-node-glow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="5" result="blur" />
          <feColorMatrix
            in="blur"
            type="matrix"
            values="1 0 0 0 0.08  0 1 0 0 0.36  0 0 1 0 0.78  0 0 0 0.45 0"
            result="glow"
          />
          <feMerge>
            <feMergeNode in="glow" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <marker id="arrow-uses" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L0,6 L8,3 z" fill="var(--color-primary)" opacity="0.75" />
        </marker>
        <marker
          id="arrow-learned"
          markerWidth="8"
          markerHeight="8"
          refX="6"
          refY="3"
          orient="auto"
        >
          <path d="M0,0 L0,6 L8,3 z" fill="var(--color-chart-4)" opacity="0.9" />
        </marker>
      </defs>

      <rect width="100%" height="100%" fill="rgba(5,7,10,0.82)" />
      <rect width="100%" height="100%" fill="url(#brain-canvas-grid)" opacity="0.45" />
      <rect width="100%" height="100%" fill="url(#brain-canvas-glow)" />
      <rect width="100%" height="100%" fill="url(#brain-canvas-vignette)" />

      <g transform={`translate(${tx},${ty}) scale(${scale})`}>
        {/* Edges */}
        {data.edges.map((edge, i) => {
          if (!isVisibleEdge(edge)) return null;
          const src = positions.get(edge.source_id);
          const tgt = positions.get(edge.target_id);
          if (!src || !tgt) return null;
          const sourceNode = nodeById.get(edge.source_id) ?? null;
          const targetNode = nodeById.get(edge.target_id) ?? null;
          const scope = scopeFromMetadata(edge.metadata);
          const style = SCOPE_EDGE_STYLE[scope];
          const usesIndex = scope === "workspace" && edge.edge_type === "uses_index";
          const dimmed =
            filterLower && (!(sourceNode && matchNode(sourceNode)) || !(targetNode && matchNode(targetNode)));

          return (
            <line
              key={i}
              x1={src.x}
              y1={src.y}
              x2={tgt.x}
              y2={tgt.y}
              stroke={style.stroke}
              strokeWidth={usesIndex ? 1.6 : style.width}
              strokeOpacity={dimmed ? 0.2 : style.opacity}
              strokeDasharray={style.dash}
              markerEnd={usesIndex ? "url(#arrow-uses)" : style.marker}
            />
          );
        })}

        {/* Nodes */}
        {data.nodes.map((node) => {
          if (!isVisibleNode(node)) return null;
          const pos = positions.get(node.node_id) ?? { x: node.x, y: node.y };
          const r = NODE_RADIUS[node.node_type] ?? 14;
          const fill = NODE_COLOR[node.node_type] ?? "var(--color-muted)";
          const scope = scopeFromMetadata(node.metadata);
          const stroke = NODE_SCOPE_STROKE[scope];
          const isSelected = selectedId === node.node_id;
          const isHovered = hoveredId === node.node_id;
          const dimmed = filterLower && !matchNode(node);
          const labelFontSize =
            node.node_type === "category" ? 9.5 : node.node_type === "assistant" ? 8.5 : 7.8;

          return (
            <g
              key={node.node_id}
              opacity={dimmed ? 0.2 : 1}
              style={STYLE_OPACITY_TRANSITION}
            >
              <circle
                cx={pos.x}
                cy={pos.y}
                r={r + (isSelected ? 15 : isHovered ? 12 : 9)}
                fill={fill}
                fillOpacity={isSelected ? 0.12 : isHovered ? 0.1 : 0.06}
                filter="url(#brain-node-glow)"
                pointerEvents="none"
              />
              <circle
                cx={pos.x}
                cy={pos.y}
                r={r + (isSelected ? 3 : isHovered ? 1 : 0)}
                fill={fill}
                fillOpacity={isSelected ? 0.98 : isHovered ? 0.9 : 0.8}
                stroke={isSelected ? "var(--color-ring)" : stroke}
                strokeWidth={isSelected ? 2.5 : scope === "assistant_self" ? 1.25 : 1}
                style={STYLE_CIRCLE}
                onPointerDown={(e) => onNodePointerDown(e, node.node_id)}
                onPointerMove={onNodePointerMove}
                onPointerUp={(e) => onNodePointerUp(e, node.node_id)}
                onPointerEnter={() => setHoveredId(node.node_id)}
                onPointerLeave={() => setHoveredId(null)}
              />
              <text
                x={pos.x}
                y={pos.y + r + 11}
                textAnchor="middle"
                fontSize={labelFontSize}
                fill="var(--color-foreground)"
                fillOpacity={0.85}
                style={STYLE_LABEL}
              >
                {node.label.length > 18 ? `${node.label.slice(0, 17)}…` : node.label}
              </text>

              {/* Tooltip */}
              {isHovered && (
                <g>
                  <rect
                    x={pos.x + r + 4}
                    y={pos.y - 14}
                    width={Math.min(node.label.length * 6 + 24, 200)}
                    height={22}
                    rx={4}
                    fill="var(--color-popover)"
                    stroke="var(--color-border)"
                    strokeWidth={0.8}
                  />
                  <text
                    x={pos.x + r + 12}
                    y={pos.y + 3}
                    fontSize={9}
                    fill="var(--color-popover-foreground)"
                    style={STYLE_TOOLTIP_TEXT}
                  >
                    {`[${SCOPE_LABEL[scope]} · ${node.node_type}] ${node.label}`}
                  </text>
                </g>
              )}
            </g>
          );
        })}
      </g>
    </svg>
  );
}
