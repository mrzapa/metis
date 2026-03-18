"use client";

/**
 * BrainGraph — interactive SVG graph visualisation of indexes, sessions,
 * and categories.  Supports zoom/pan, node drag, tooltip on hover, and
 * click-to-select with a detail side-panel.
 *
 * Data is fetched from GET /v1/brain/graph and rendered as an SVG force
 * layout (positions are computed by the backend's apply_force_layout()).
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";

// ── Types ─────────────────────────────────────────────────────────────────

export interface BrainNode {
  node_id: string;
  node_type: "category" | "index" | "session";
  label: string;
  x: number;
  y: number;
  metadata: Record<string, unknown>;
}

export interface BrainEdge {
  source_id: string;
  target_id: string;
  edge_type: string;
}

export interface BrainGraphData {
  nodes: BrainNode[];
  edges: BrainEdge[];
}

// ── Visual constants ───────────────────────────────────────────────────────

const NODE_RADIUS: Record<string, number> = {
  category: 26,
  index: 18,
  session: 14,
};

const NODE_COLOR: Record<string, string> = {
  category: "var(--color-accent)",
  index: "var(--color-primary)",
  session: "var(--color-chart-2)",
};

const EDGE_COLOR: Record<string, string> = {
  category_member: "var(--color-border)",
  uses_index: "var(--color-primary)",
};

// ── Helpers ────────────────────────────────────────────────────────────────

function worldBounds(nodes: BrainNode[]): {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
} {
  if (nodes.length === 0) return { minX: -200, minY: -200, maxX: 200, maxY: 200 };
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of nodes) {
    if (n.x < minX) minX = n.x;
    if (n.y < minY) minY = n.y;
    if (n.x > maxX) maxX = n.x;
    if (n.y > maxY) maxY = n.y;
  }
  return { minX, minY, maxX, maxY };
}

// ── Component ──────────────────────────────────────────────────────────────

interface BrainGraphProps {
  data: BrainGraphData;
  /** Text filter — nodes whose labels don't match are dimmed. */
  filter?: string;
  onNodeSelect?: (node: BrainNode | null) => void;
  className?: string;
}

export function BrainGraph({
  data,
  filter = "",
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

  // Seed positions from graph data whenever data changes
  useEffect(() => {
    const map = new Map<string, { x: number; y: number }>();
    for (const n of data.nodes) {
      map.set(n.node_id, { x: n.x, y: n.y });
    }
    setPositions(map);
  }, [data]);

  // Fit the graph to the viewport on initial load / data change
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || data.nodes.length === 0) return;
    const { minX, minY, maxX, maxY } = worldBounds(data.nodes);
    const w = svg.clientWidth || 800;
    const h = svg.clientHeight || 600;
    const gw = maxX - minX + 100;
    const gh = maxY - minY + 100;
    const scale = Math.min(w / gw, h / gh, 1.5);
    const tx = w / 2 - ((minX + maxX) / 2) * scale;
    const ty = h / 2 - ((minY + maxY) / 2) * scale;
    setTransform({ tx, ty, scale });
  }, [data]);

  // ── Wheel zoom ─────────────────────────────────────────────────────────
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

  // ── SVG background pan ─────────────────────────────────────────────────
  const onBgPointerDown = useCallback((e: ReactPointerEvent<SVGElement>) => {
    if (e.button !== 0) return;
    panRef.current = {
      startPx: e.clientX,
      startPy: e.clientY,
      startTx: transform.tx,
      startTy: transform.ty,
    };
    (e.target as SVGElement).setPointerCapture(e.pointerId);
  }, [transform]);

  const onBgPointerMove = useCallback((e: ReactPointerEvent<SVGElement>) => {
    if (!panRef.current) return;
    const dx = e.clientX - panRef.current.startPx;
    const dy = e.clientY - panRef.current.startPy;
    setTransform((prev) => ({
      ...prev,
      tx: panRef.current!.startTx + dx,
      ty: panRef.current!.startTy + dy,
    }));
  }, []);

  const onBgPointerUp = useCallback(() => {
    panRef.current = null;
  }, []);

  // ── Node drag ──────────────────────────────────────────────────────────
  const onNodePointerDown = useCallback(
    (e: ReactPointerEvent<SVGCircleElement>, nodeId: string) => {
      e.stopPropagation();
      const pos = positions.get(nodeId) ?? { x: 0, y: 0 };
      dragRef.current = {
        nodeId,
        startPx: e.clientX,
        startPy: e.clientY,
        startNx: pos.x,
        startNy: pos.y,
      };
      (e.target as SVGElement).setPointerCapture(e.pointerId);
    },
    [positions],
  );

  const onNodePointerMove = useCallback(
    (e: ReactPointerEvent<SVGCircleElement>) => {
      if (!dragRef.current) return;
      const dx = (e.clientX - dragRef.current.startPx) / transform.scale;
      const dy = (e.clientY - dragRef.current.startPy) / transform.scale;
      setPositions((prev) => {
        const next = new Map(prev);
        next.set(dragRef.current!.nodeId, {
          x: dragRef.current!.startNx + dx,
          y: dragRef.current!.startNy + dy,
        });
        return next;
      });
    },
    [transform.scale],
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
        setSelectedId((prev) => (prev === nodeId ? null : nodeId));
        onNodeSelect?.(selectedId === nodeId ? null : node);
      }
    },
    [data.nodes, onNodeSelect, selectedId],
  );

  // ── Filter matching ────────────────────────────────────────────────────
  const filterLower = filter.trim().toLowerCase();
  const matchNode = (n: BrainNode) =>
    !filterLower || n.label.toLowerCase().includes(filterLower);

  // ── Render ─────────────────────────────────────────────────────────────
  const { tx, ty, scale } = transform;

  return (
    <svg
      ref={svgRef}
      className={`w-full h-full select-none cursor-grab active:cursor-grabbing ${className}`}
      onPointerDown={onBgPointerDown}
      onPointerMove={(e) => {
        onBgPointerMove(e);
      }}
      onPointerUp={onBgPointerUp}
      onPointerCancel={onBgPointerUp}
      aria-label="Brain graph"
    >
      <defs>
        <marker
          id="arrow-uses"
          markerWidth="8"
          markerHeight="8"
          refX="6"
          refY="3"
          orient="auto"
        >
          <path d="M0,0 L0,6 L8,3 z" fill="var(--color-primary)" opacity="0.7" />
        </marker>
      </defs>

      <g transform={`translate(${tx},${ty}) scale(${scale})`}>
        {/* Edges */}
        {data.edges.map((edge, i) => {
          const src = positions.get(edge.source_id);
          const tgt = positions.get(edge.target_id);
          if (!src || !tgt) return null;
          const isUsesIndex = edge.edge_type === "uses_index";
          return (
            <line
              key={i}
              x1={src.x}
              y1={src.y}
              x2={tgt.x}
              y2={tgt.y}
              stroke={EDGE_COLOR[edge.edge_type] ?? "var(--color-border)"}
              strokeWidth={isUsesIndex ? 1.5 : 0.8}
              strokeOpacity={0.55}
              markerEnd={isUsesIndex ? "url(#arrow-uses)" : undefined}
            />
          );
        })}

        {/* Nodes */}
        {data.nodes.map((node) => {
          const pos = positions.get(node.node_id) ?? { x: node.x, y: node.y };
          const r = NODE_RADIUS[node.node_type] ?? 14;
          const color = NODE_COLOR[node.node_type] ?? "var(--color-muted)";
          const isSelected = selectedId === node.node_id;
          const isHovered = hoveredId === node.node_id;
          const dimmed = filterLower && !matchNode(node);
          const labelFontSize = node.node_type === "category" ? 9 : 7.5;

          return (
            <g
              key={node.node_id}
              opacity={dimmed ? 0.2 : 1}
              style={{ transition: "opacity 0.2s" }}
            >
              <circle
                cx={pos.x}
                cy={pos.y}
                r={r + (isSelected ? 3 : isHovered ? 1 : 0)}
                fill={color}
                fillOpacity={isSelected ? 0.95 : isHovered ? 0.85 : 0.75}
                stroke={isSelected ? "var(--color-ring)" : "transparent"}
                strokeWidth={isSelected ? 2.5 : 0}
                style={{ transition: "r 0.15s, fill-opacity 0.15s", cursor: "pointer" }}
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
                style={{ pointerEvents: "none", userSelect: "none" }}
              >
                {node.label.length > 18 ? `${node.label.slice(0, 17)}…` : node.label}
              </text>

              {/* Tooltip */}
              {isHovered && (
                <g>
                  <rect
                    x={pos.x + r + 4}
                    y={pos.y - 14}
                    width={Math.min(node.label.length * 6 + 16, 180)}
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
                    style={{ pointerEvents: "none" }}
                  >
                    {`[${node.node_type}] ${node.label}`}
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
