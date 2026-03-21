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
  type BrainGraphData,
  type BrainNode,
  type BrainRenderMode,
  type BrainScope,
  ALL_BRAIN_SCOPES,
} from "./brain-graph";
import {
  buildBrainSceneGraph,
  type BrainSceneGraph,
  type BrainSceneLink,
  type BrainSceneNode,
} from "./brain-graph-view-model";
import {
  loadBrainModelOverlay,
  type BrainModelOverlayHandle,
} from "./brain-model-overlay";

// -- Constants ----------------------------------------------------------------

const BG_COLOR = "#05070a";
const FOG_DENSITY = 0.0018;
const CAMERA_TRANSITION_MS = 1000;
const ZOOM_TO_FIT_MS = 600;
const ZOOM_TO_FIT_PADDING = 60;
/** Small z-offset prevents gimbal lock when looking straight down. */
const CAMERA_TOP_VIEW_Z_OFFSET = 0.01;

// -- Helpers ------------------------------------------------------------------

/** Recursively dispose all Three.js geometries, materials, and textures. */
function disposeObject3D(obj: THREE.Object3D): void {
  obj.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      child.geometry?.dispose();
      const mat = child.material;
      if (Array.isArray(mat)) {
        mat.forEach((m) => disposeMaterial(m));
      } else if (mat) {
        disposeMaterial(mat);
      }
    } else if (child instanceof THREE.Sprite) {
      const mat = child.material as THREE.SpriteMaterial;
      mat.map?.dispose();
      mat.dispose();
    }
  });
}

function disposeMaterial(mat: THREE.Material): void {
  if ("map" in mat && (mat as THREE.MeshBasicMaterial).map) {
    (mat as THREE.MeshBasicMaterial).map!.dispose();
  }
  mat.dispose();
}

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
  renderMode?: BrainRenderMode;
  selectedNodeId?: string | null;
  onSelectedNodeIdChange?: (nodeId: string | null) => void;
  onNodeSelect?: (node: BrainNode | null) => void;
  onModelLoadError?: (message: string) => void;
  modelUrl?: string;
  className?: string;
}

export default function BrainGraph3D({
  data,
  filter = "",
  activeScopes = ALL_BRAIN_SCOPES,
  renderMode = "hybrid",
  selectedNodeId = null,
  onSelectedNodeIdChange,
  onNodeSelect,
  onModelLoadError,
  modelUrl = "/brain/brain-model.glb",
  className = "",
}: BrainGraph3DProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<ForceGraphMethods<BrainSceneNode, BrainSceneLink> | undefined>(undefined);

  // Track Three.js objects we create so we can dispose them on cleanup
  const createdObjectsRef = useRef<THREE.Object3D[]>([]);
  const modelOverlayRef = useRef<BrainModelOverlayHandle | null>(null);
  const modelSceneRef = useRef<THREE.Scene | null>(null);
  const modelLoadAttemptRef = useRef(0);
  const [sceneReady, setSceneReady] = useState(false);
  const [autoRotate, setAutoRotate] = useState(false);

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

  // Dispose all created Three.js objects on unmount
  useEffect(() => {
    const objects = createdObjectsRef.current;
    return () => {
      for (const obj of objects) disposeObject3D(obj);
      objects.length = 0;
      if (modelOverlayRef.current) {
        modelOverlayRef.current.dispose();
        modelOverlayRef.current = null;
      }
    };
  }, []);

  // -- Build filtered graph data -------------------------------------------
  const graphData = useMemo<BrainSceneGraph>(
    () => buildBrainSceneGraph(data, { filter, activeScopes }),
    [data, filter, activeScopes],
  );

  // -- Zoom-to-fit on first load / data change -----------------------------

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || graphData.nodes.length === 0) return;
    const timer = setTimeout(() => {
      fg.zoomToFit(ZOOM_TO_FIT_MS, ZOOM_TO_FIT_PADDING);
    }, 350);
    return () => clearTimeout(timer);
  }, [graphData]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (fgRef.current?.scene()) {
        modelSceneRef.current = fgRef.current.scene();
        setSceneReady(true);
      }
    }, 0);

    return () => clearTimeout(timer);
  }, [dims.h, dims.w, graphData.nodes.length]);

  // -- Post-mount renderer / scene / controls configuration ----------------

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || !sceneReady) return;

    // Renderer quality: crisp rendering on high-DPI displays + filmic tone mapping
    const renderer = fg.renderer();
    if (renderer) {
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.0;
    }

    // Exponential fog for depth perception (distant nodes subtly fade)
    const scene = fg.scene();
    if (scene && !scene.fog) {
      scene.fog = new THREE.FogExp2(BG_COLOR, FOG_DENSITY);
    }

    // Orbit controls: smooth damped interaction, constrained zoom range
    const controls = fg.controls() as Record<string, unknown>;
    if (controls) {
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.rotateSpeed = 0.8;
      controls.zoomSpeed = 1.2;
      controls.minDistance = 30;
      controls.maxDistance = 800;
    }
  }, [sceneReady]);

  // -- Auto-rotate control -------------------------------------------------

  useEffect(() => {
    if (!sceneReady) return;
    const controls = fgRef.current?.controls() as Record<string, unknown> | undefined;
    if (controls) {
      controls.autoRotate = autoRotate;
      controls.autoRotateSpeed = 0.8;
    }
  }, [autoRotate, sceneReady]);

  const clearModelOverlay = useCallback(() => {
    const scene = modelSceneRef.current;
    const overlay = modelOverlayRef.current;
    if (!overlay) return;

    if (scene) {
      scene.remove(overlay.root);
      scene.remove(overlay.lightRig);
    }
    overlay.dispose();
    modelOverlayRef.current = null;
  }, []);

  useEffect(() => {
    if (!sceneReady || !modelSceneRef.current) return;

    if (renderMode !== "hybrid") {
      clearModelOverlay();
      return;
    }

    let cancelled = false;
    const loadAttempt = modelLoadAttemptRef.current + 1;
    modelLoadAttemptRef.current = loadAttempt;
    clearModelOverlay();

    loadBrainModelOverlay(modelUrl)
      .then((overlay) => {
        if (cancelled || modelLoadAttemptRef.current !== loadAttempt || !modelSceneRef.current) {
          overlay.dispose();
          return;
        }

        modelSceneRef.current.add(overlay.root);
        modelSceneRef.current.add(overlay.lightRig);
        overlay.fitToGraph(graphData.nodes);
        modelOverlayRef.current = overlay;
      })
      .catch((error: unknown) => {
        if (cancelled || modelLoadAttemptRef.current !== loadAttempt) return;
        const message =
          error instanceof Error
            ? error.message
            : "The anatomical brain model could not be loaded.";
        clearModelOverlay();
        onModelLoadError?.(message);
      });

    return () => {
      cancelled = true;
    };
  }, [clearModelOverlay, graphData.nodes, modelUrl, onModelLoadError, renderMode, sceneReady]);

  const fitModelOverlay = useCallback(() => {
    modelOverlayRef.current?.fitToGraph(graphData.nodes);
  }, [graphData.nodes]);

  useEffect(() => {
    if (renderMode !== "hybrid") return;
    const timer = setTimeout(() => {
      fitModelOverlay();
    }, 500);
    return () => clearTimeout(timer);
  }, [fitModelOverlay, graphData, renderMode]);

  // -- Node hover for cursor change ----------------------------------------

  const handleNodeHover = useCallback((node: BrainSceneNode | null) => {
    if (containerRef.current) {
      containerRef.current.style.cursor = node ? "pointer" : "grab";
    }
  }, []);

  // -- Camera preset views --------------------------------------------------

  const setCameraView = useCallback((direction: "front" | "top" | "side") => {
    const fg = fgRef.current;
    if (!fg) return;
    const dist = fg.camera().position.length() || 300;
    const views: Record<string, { x: number; y: number; z: number }> = {
      front: { x: 0, y: 0, z: dist },
      top: { x: 0, y: dist, z: CAMERA_TOP_VIEW_Z_OFFSET },
      side: { x: dist, y: 0, z: 0 },
    };
    fg.cameraPosition(views[direction], { x: 0, y: 0, z: 0 }, CAMERA_TRANSITION_MS);
  }, []);

  const resetView = useCallback(() => {
    fgRef.current?.zoomToFit(ZOOM_TO_FIT_MS, ZOOM_TO_FIT_PADDING);
  }, []);

  // -- Custom Three.js node objects ----------------------------------------

  const nodeThreeObject = useCallback((node: BrainSceneNode) => {
    const group = new THREE.Group();
    createdObjectsRef.current.push(group);

    const isSelected = node.id === selectedNodeId;
    const r = node.radius;
    const color = new THREE.Color(node.color);

    // Selection ring (only for the selected node)
    if (isSelected) {
      const ringGeo = new THREE.RingGeometry(r + 2, r + 3.2, 32);
      const ringMat = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.7,
        side: THREE.DoubleSide,
        depthWrite: false,
      });
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.lookAt(0, 0, 1);
      group.add(ring);
    }

    // Glow halo
    const glowGeo = new THREE.SphereGeometry(r * (isSelected ? 2.4 : 1.9), 16, 16);
    const glowMat = new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: node.dimmed ? 0.02 : isSelected ? 0.14 : 0.08,
      depthWrite: false,
    });
    group.add(new THREE.Mesh(glowGeo, glowMat));

    // Main sphere
    const geo = new THREE.SphereGeometry(r + (isSelected ? 1.5 : 0), 24, 24);
    const mat = new THREE.MeshPhongMaterial({
      color,
      emissive: color,
      emissiveIntensity: isSelected ? 0.55 : 0.35,
      shininess: 60,
      transparent: true,
      opacity: node.dimmed ? 0.2 : 0.92,
    });
    group.add(new THREE.Mesh(geo, mat));

    // Text label
    const label = node.brain.label.length > 18
      ? `${node.brain.label.slice(0, 17)}…`
      : node.brain.label;
    const sprite = makeTextSprite(
      label,
      node.dimmed ? "rgba(255,255,255,0.3)" : isSelected ? "rgba(255,255,255,1)" : "rgba(255,255,255,0.88)",
    );
    sprite.position.set(0, -(r + 4), 0);
    group.add(sprite);

    return group;
  }, [selectedNodeId]);

  // -- Node click handler --------------------------------------------------

  const handleNodeClick = useCallback(
    (node: BrainSceneNode) => {
      const nextId = selectedNodeId === node.id ? null : node.id;
      onSelectedNodeIdChange?.(nextId);
      onNodeSelect?.(nextId ? node.brain : null);
    },
    [onNodeSelect, onSelectedNodeIdChange, selectedNodeId],
  );

  // Clear selection when the selected node is no longer visible
  useEffect(() => {
    if (!selectedNodeId) return;
    const stillVisible = graphData.visibleNodeIds.has(selectedNodeId);
    if (!stillVisible) {
      onSelectedNodeIdChange?.(null);
      onNodeSelect?.(null);
    }
  }, [graphData.visibleNodeIds, onNodeSelect, onSelectedNodeIdChange, selectedNodeId]);

  useEffect(() => {
    if (!onNodeSelect) return;
    onNodeSelect(selectedNodeId ? graphData.visibleNodeById.get(selectedNodeId) ?? null : null);
  }, [graphData.visibleNodeById, onNodeSelect, selectedNodeId]);

  // -- Controls hint visibility -------------------------------------------

  const [showHint, setShowHint] = useState(true);

  useEffect(() => {
    if (!showHint) return;
    const timer = setTimeout(() => setShowHint(false), 6000);
    return () => clearTimeout(timer);
  }, [showHint]);

  // -- Render --------------------------------------------------------------

  return (
    <div
      ref={containerRef}
      className={`relative h-full w-full overflow-hidden ${className}`}
      aria-label="Brain graph"
    >
      <ForceGraph3D<BrainSceneNode, BrainSceneLink>
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
        linkColor={(link: BrainSceneLink) => link.color}
        linkWidth={(link: BrainSceneLink) => link.width}
        linkOpacity={0.7}
        /* Directional link particles for visual flow */
        linkDirectionalParticles={2}
        linkDirectionalParticleWidth={1.5}
        linkDirectionalParticleSpeed={0.004}
        linkDirectionalParticleColor={(link: BrainSceneLink) => link.color}
        /* Interactions */
        onNodeClick={handleNodeClick}
        onNodeHover={handleNodeHover}
        onBackgroundClick={() => {
          onSelectedNodeIdChange?.(null);
          onNodeSelect?.(null);
        }}
        onEngineStop={fitModelOverlay}
        /* Force engine tuning */
        d3AlphaDecay={0.04}
        d3VelocityDecay={0.3}
        warmupTicks={30}
      />

      {/* 3D navigation hint overlay */}
      {showHint && (
        <div className="pointer-events-none absolute bottom-4 left-4 flex items-center gap-3 rounded-xl border border-white/10 bg-black/60 px-3.5 py-2 text-[11px] text-white/60 backdrop-blur-sm transition-opacity duration-500">
          <span>Orbit: left-drag</span>
          <span className="text-white/20">·</span>
          <span>Zoom: scroll</span>
          <span className="text-white/20">·</span>
          <span>Pan: right-drag</span>
        </div>
      )}

      {/* Camera controls toolbar */}
      <div className="absolute right-4 top-4 flex flex-col gap-1 rounded-xl border border-white/10 bg-black/60 p-1.5 backdrop-blur-sm">
        {(["front", "top", "side"] as const).map((view) => (
          <button
            key={view}
            type="button"
            title={`${view.charAt(0).toUpperCase() + view.slice(1)} view`}
            onClick={() => setCameraView(view)}
            className="rounded-lg px-2 py-1.5 text-[11px] capitalize text-white/60 transition-colors hover:bg-white/10 hover:text-white/90"
          >
            {view}
          </button>
        ))}
        <div className="my-0.5 border-t border-white/10" />
        <button
          type="button"
          title={autoRotate ? "Stop rotation" : "Auto-rotate"}
          onClick={() => setAutoRotate((prev) => !prev)}
          className={`rounded-lg px-2 py-1.5 text-[11px] transition-colors ${
            autoRotate
              ? "bg-white/15 text-white/90"
              : "text-white/60 hover:bg-white/10 hover:text-white/90"
          }`}
        >
          {autoRotate ? "⏸ Stop" : "🔄 Spin"}
        </button>
        <button
          type="button"
          title="Reset view"
          onClick={resetView}
          className="rounded-lg px-2 py-1.5 text-[11px] text-white/60 transition-colors hover:bg-white/10 hover:text-white/90"
        >
          ↺ Reset
        </button>
      </div>
    </div>
  );
}
