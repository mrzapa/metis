"use client";

/**
 * BrainGraph3D – interactive three-dimensional force-directed graph
 * visualisation of indexes, sessions, and categories.
 *
 * Uses react-force-graph-3d (Three.js / WebGL) to render nodes as 3D spheres
 * with glow halos and text-sprite labels.  The user can orbit (left-drag),
 * zoom (scroll), and pan (right-drag) in all three planes.
 *
 * **Must be loaded with `next/dynamic({ ssr: false })` because Three.js
 * requires a browser environment.**
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import ForceGraph3D, { type ForceGraphMethods } from "react-force-graph-3d";
import * as THREE from "three";

import {
  type BrainNode,
  type BrainEdge,
  type BrainGraphData,
  type BrainScope,
  scopeFromMetadata,
  NODE_COLOR_HEX,
  NODE_RADIUS_3D,
  SCOPE_LINK_COLOR,
} from "./brain-graph";

// -- Constants ----------------------------------------------------------------

const ALL_SCOPES: BrainScope[] = ["workspace", "assistant_self", "assistant_learned"];

const BG_COLOR = "#05070a";

// -- Internal graph node / link types for react-force-graph-3d ----------------

interface GraphNode {
  id: string;
  brain: BrainNode;
  color: string;
  radius: number;
  dimmed: boolean;
  x?: number;
  y?: number;
  z?: number;
}

interface GraphLink {
  source: string;
  target: string;
  edge: BrainEdge;
  color: string;
  width: number;
}

// -- Helpers ------------------------------------------------------------------

/** Create a canvas-based text sprite for a node label. */
function makeTextSprite(text: string, color: string): THREE.Sprite {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d")!;
  const fontSize = 48;
  const font = `${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif`;
  ctx.font = font;
  const metrics = ctx.measureText(text);
  const textW = metrics.width;

  const pad = 16;
  canvas.width = textW + pad * 2;
  canvas.height = fontSize + pad * 2;

  ctx.font = font;
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.9;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);

  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false });
  const sprite = new THREE.Sprite(mat);

  const labelScaleFactor = 0.25;
  sprite.scale.set(canvas.width * labelScaleFactor / fontSize, canvas.height * labelScaleFactor / fontSize, 1);
  return sprite;
}

// -- Component ----------------------------------------------------------------

export interface BrainGraph3DProps {
  data: BrainGraphData;
  filter?: string;
  activeScopes?: BrainScope[];
  onNodeSelect?: (node: BrainNode | null) => void;
  className?: string;
}

export default function BrainGraph3D({
  data,
  filter = "",
  activeScopes = ALL_SCOPES,
  onNodeSelect,
  className = "",
}: BrainGraph3DProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<ForceGraphMethods<GraphNode, GraphLink> | undefined>(undefined);
  const selectedIdRef = useRef<string | null>(null);

  // Track container dimensions for the ForceGraph width/height props
  const [dims, setDims] = useState({ w: 800, h: 600 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setDims({ w: width, h: height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // -- Build filtered graph data -------------------------------------------

  const filterLower = useMemo(() => filter.trim().toLowerCase(), [filter]);

  const activeScopeSet = useMemo(
    () => new Set<BrainScope>(activeScopes.length > 0 ? activeScopes : ALL_SCOPES),
    [activeScopes],
  );

  const graphData = useMemo(() => {
    const visibleNodes: GraphNode[] = [];
    const visibleIds = new Set<string>();

    for (const node of data.nodes) {
      const scope = scopeFromMetadata(node.metadata);
      if (!activeScopeSet.has(scope)) continue;

      const dimmed = filterLower ? !node.label.toLowerCase().includes(filterLower) : false;
      visibleIds.add(node.node_id);
      visibleNodes.push({
        id: node.node_id,
        brain: node,
        color: NODE_COLOR_HEX[node.node_type] ?? "#888888",
        radius: NODE_RADIUS_3D[node.node_type] ?? 4,
        dimmed,
      });
    }

    const visibleLinks: GraphLink[] = [];
    for (const edge of data.edges) {
      const scope = scopeFromMetadata(edge.metadata);
      if (!activeScopeSet.has(scope)) continue;
      if (!visibleIds.has(edge.source_id) || !visibleIds.has(edge.target_id)) continue;

      visibleLinks.push({
        source: edge.source_id,
        target: edge.target_id,
        edge,
        color: SCOPE_LINK_COLOR[scope] ?? "rgba(255,255,255,0.15)",
        width: scope === "assistant_learned" ? 1.4 : scope === "assistant_self" ? 1.0 : 0.6,
      });
    }

    return { nodes: visibleNodes, links: visibleLinks };
  }, [data, activeScopeSet, filterLower]);

  // -- Zoom-to-fit on first load / data change -----------------------------

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || graphData.nodes.length === 0) return;
    const timer = setTimeout(() => {
      fg.zoomToFit(600, 60);
    }, 350);
    return () => clearTimeout(timer);
  }, [graphData]);

  // -- Custom Three.js node objects ----------------------------------------

  const nodeThreeObject = useCallback((node: GraphNode) => {
    const group = new THREE.Group();

    const r = node.radius;
    const color = new THREE.Color(node.color);

    // Glow halo
    const glowGeo = new THREE.SphereGeometry(r * 1.9, 16, 16);
    const glowMat = new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: node.dimmed ? 0.02 : 0.08,
      depthWrite: false,
    });
    group.add(new THREE.Mesh(glowGeo, glowMat));

    // Main sphere
    const geo = new THREE.SphereGeometry(r, 24, 24);
    const mat = new THREE.MeshPhongMaterial({
      color,
      emissive: color,
      emissiveIntensity: 0.35,
      shininess: 60,
      transparent: true,
      opacity: node.dimmed ? 0.2 : 0.92,
    });
    group.add(new THREE.Mesh(geo, mat));

    // Text label
    const label = node.brain.label.length > 18
      ? `${node.brain.label.slice(0, 17)}…`
      : node.brain.label;
    const sprite = makeTextSprite(label, node.dimmed ? "rgba(255,255,255,0.3)" : "rgba(255,255,255,0.88)");
    sprite.position.set(0, -(r + 4), 0);
    group.add(sprite);

    return group;
  }, []);

  // -- Node click handler --------------------------------------------------

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      const isSame = selectedIdRef.current === node.id;
      const nextId = isSame ? null : node.id;
      selectedIdRef.current = nextId;
      onNodeSelect?.(nextId ? node.brain : null);
    },
    [onNodeSelect],
  );

  // -- Render --------------------------------------------------------------

  return (
    <div
      ref={containerRef}
      className={`relative h-full w-full overflow-hidden ${className}`}
      aria-label="Brain graph"
    >
      <ForceGraph3D<GraphNode, GraphLink>
        ref={fgRef}
        width={dims.w}
        height={dims.h}
        graphData={graphData}
        backgroundColor={BG_COLOR}
        showNavInfo={false}
        /* Node styling */
        nodeThreeObject={nodeThreeObject}
        nodeThreeObjectExtend={false}
        /* Link styling */
        linkColor={(link: GraphLink) => link.color}
        linkWidth={(link: GraphLink) => link.width}
        linkOpacity={0.7}
        /* Interactions */
        onNodeClick={handleNodeClick}
        /* Force engine tuning */
        d3AlphaDecay={0.04}
        d3VelocityDecay={0.3}
      />
    </div>
  );
}
