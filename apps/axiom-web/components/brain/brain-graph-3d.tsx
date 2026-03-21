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
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";

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
const FOG_DENSITY = 0.0008;
const CAMERA_TRANSITION_MS = 1000;
const ZOOM_TO_FIT_MS = 600;
const ZOOM_TO_FIT_PADDING = 60;
/** Small z-offset prevents gimbal lock when looking straight down. */
const CAMERA_TOP_VIEW_Z_OFFSET = 0.01;
/** Charge force strength – more negative = stronger node repulsion. */
const D3_CHARGE_STRENGTH = -120;
/** Preferred link distance between connected nodes. */
const D3_LINK_DISTANCE = 80;

// -- Bloom post-processing (inspired by Hastur-HP/The-Brain) ------------------

/** Bloom strength – how bright the glow is. */
const BLOOM_STRENGTH = 1.0;
/** Bloom radius – how far the glow spreads. */
const BLOOM_RADIUS = 0.75;
/** Bloom threshold – luminance threshold for bloom to kick in. */
const BLOOM_THRESHOLD = 0.15;

// -- Ambient dust particle system ---------------------------------------------

/** Number of atmospheric dust particles for depth perception. */
const DUST_COUNT = 600;
/** Radius of the dust cloud. */
const DUST_RADIUS = 1200;

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

/** Create a canvas-based text sprite for a node label with semi-transparent backdrop. */
function makeTextSprite(text: string, color: string, nodeRadius: number): THREE.Sprite {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d")!;
  const fontSize = 64;
  const font = `600 ${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif`;
  ctx.font = font;
  const metrics = ctx.measureText(text);
  const textW = metrics.width;

  const padX = 24;
  const padY = 18;
  canvas.width = textW + padX * 2;
  canvas.height = fontSize + padY * 2;

  // Semi-transparent dark backdrop pill for readability
  const bgRadius = 14;
  ctx.fillStyle = "rgba(5, 7, 10, 0.65)";
  ctx.beginPath();
  if (ctx.roundRect) {
    ctx.roundRect(4, 4, canvas.width - 8, canvas.height - 8, bgRadius);
  } else {
    // Fallback for browsers without roundRect
    const x = 4, y = 4, w = canvas.width - 8, h = canvas.height - 8, r = bgRadius;
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  ctx.fill();

  // Text
  ctx.font = font;
  ctx.fillStyle = color;
  ctx.globalAlpha = 1.0;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);

  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false });
  const sprite = new THREE.Sprite(mat);

  // Scale relative to node size for readability
  const labelScale = Math.max(0.35, nodeRadius * 0.06);
  sprite.scale.set(canvas.width * labelScale / fontSize, canvas.height * labelScale / fontSize, 1);
  return sprite;
}

/**
 * Create small tendril lines radiating from a node to mimic neuron dendrites.
 * Returns a THREE.Group containing the tendril line segments.
 */
function createDendrites(radius: number, color: THREE.Color, count: number): THREE.Group {
  const group = new THREE.Group();
  const mat = new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity: 0.35,
    linewidth: 1,
  });

  for (let i = 0; i < count; i++) {
    // Random direction on a sphere
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    const dx = Math.sin(phi) * Math.cos(theta);
    const dy = Math.sin(phi) * Math.sin(theta);
    const dz = Math.cos(phi);

    // Tendril: short line from node surface outward with a slight curve
    const len = radius * (1.2 + Math.random() * 1.8);
    const midLen = len * 0.5;
    // Add a small perpendicular offset for organic curve
    const perpX = (Math.random() - 0.5) * radius * 0.4;
    const perpY = (Math.random() - 0.5) * radius * 0.4;

    const points = [
      new THREE.Vector3(dx * radius, dy * radius, dz * radius),
      new THREE.Vector3(dx * midLen + perpX, dy * midLen + perpY, dz * midLen),
      new THREE.Vector3(dx * len, dy * len, dz * len),
    ];
    const geo = new THREE.BufferGeometry().setFromPoints(points);
    const line = new THREE.Line(geo, mat);
    group.add(line);
  }
  return group;
}

/**
 * Create ambient dust particles scattered in 3D space for atmospheric depth.
 * Inspired by Hastur-HP/The-Brain's ambient data dust effect.
 */
function createAmbientDust(count: number, radius: number): THREE.Points {
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const i3 = i * 3;
    // Uniform distribution in a sphere
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    const r = radius * Math.cbrt(Math.random());
    positions[i3] = r * Math.sin(phi) * Math.cos(theta);
    positions[i3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    positions[i3 + 2] = r * Math.cos(phi);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));

  const material = new THREE.PointsMaterial({
    color: 0x8888aa,
    size: 1.2,
    transparent: true,
    opacity: 0.3,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    sizeAttenuation: true,
  });

  const dust = new THREE.Points(geometry, material);
  dust.frustumCulled = false;
  dust.name = "ambient-dust";
  return dust;
}

/**
 * Shockwave effect: expanding wireframe sphere on node click.
 * Inspired by Hastur-HP/The-Brain's click feedback.
 */
interface ShockwaveHandle {
  mesh: THREE.Mesh;
  startTime: number;
}

function createShockwave(position: THREE.Vector3, color: THREE.Color): ShockwaveHandle {
  const geo = new THREE.SphereGeometry(1, 32, 32);
  const mat = new THREE.MeshBasicMaterial({
    color,
    wireframe: true,
    transparent: true,
    opacity: 0.5,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.copy(position);
  mesh.name = "shockwave";
  return { mesh, startTime: performance.now() };
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
  const needsInitialZoomRef = useRef(true);
  const rendererConfiguredRef = useRef(false);
  const [autoRotate, setAutoRotate] = useState(false);

  // Bloom post-processing refs
  const composerRef = useRef<EffectComposer | null>(null);
  // Ambient dust ref
  const dustRef = useRef<THREE.Points | null>(null);
  // Active shockwave effects
  const shockwavesRef = useRef<ShockwaveHandle[]>([]);
  // Selection targeting ring (spinning torus)
  const selectionRingRef = useRef<THREE.Mesh | null>(null);

  // Track container dimensions for the ForceGraph width/height props
  const [dims, setDims] = useState({ w: 800, h: 600 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) {
        setDims({ w: width, h: height });
        // Update bloom composer resolution on resize
        composerRef.current?.setSize(width, height);
      }
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
      if (composerRef.current) {
        composerRef.current.dispose();
        composerRef.current = null;
      }
      if (dustRef.current) {
        dustRef.current.geometry.dispose();
        (dustRef.current.material as THREE.PointsMaterial).dispose();
        dustRef.current = null;
      }
    };
  }, []);

  // -- Animation loop for particle brain overlay, bloom, and effects --------
  useEffect(() => {
    if (!sceneReady) return;
    const clock = new THREE.Clock();
    let rafId: number;
    const tick = () => {
      const dt = clock.getDelta();

      // Update brain overlay breathing/pulse
      const overlay = modelOverlayRef.current;
      if (overlay) overlay.update(dt);

      // Animate shockwaves (expand + fade)
      const scene = modelSceneRef.current;
      const now = performance.now();
      const waves = shockwavesRef.current;
      for (let i = waves.length - 1; i >= 0; i--) {
        const wave = waves[i];
        const elapsed = (now - wave.startTime) / 1000;
        const scale = 1 + elapsed * 40;
        wave.mesh.scale.setScalar(scale);
        const opacity = Math.max(0, 0.5 - elapsed * 0.8);
        (wave.mesh.material as THREE.MeshBasicMaterial).opacity = opacity;
        if (opacity <= 0) {
          if (scene) scene.remove(wave.mesh);
          wave.mesh.geometry.dispose();
          (wave.mesh.material as THREE.MeshBasicMaterial).dispose();
          waves.splice(i, 1);
        }
      }

      // Rotate the selection targeting ring
      const ring = selectionRingRef.current;
      if (ring) {
        ring.rotation.z += 0.02;
      }

      // Render bloom composer if active, otherwise normal render
      if (composerRef.current) {
        composerRef.current.render();
      }

      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [sceneReady]);

  // -- Build filtered graph data -------------------------------------------
  const graphData = useMemo<BrainSceneGraph>(
    () => buildBrainSceneGraph(data, { filter, activeScopes }),
    [data, filter, activeScopes],
  );

  // -- Zoom-to-fit on first load / data change -----------------------------

  useEffect(() => {
    needsInitialZoomRef.current = true;
    const fg = fgRef.current;
    if (!fg || graphData.nodes.length === 0) return;
    const timer = setTimeout(() => {
      fg.zoomToFit(ZOOM_TO_FIT_MS, ZOOM_TO_FIT_PADDING);
    }, 350);
    return () => clearTimeout(timer);
  }, [graphData]);

  // -- Post-mount: configure renderer, fog, bloom, dust, controls, forces --

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || rendererConfiguredRef.current) return;
    rendererConfiguredRef.current = true;

    // Renderer quality settings
    const renderer = fg.renderer?.();
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

    // Add subtle ambient light for better material visibility
    if (scene) {
      const ambientLight = new THREE.AmbientLight(0x404060, 0.6);
      ambientLight.name = "ambient-light";
      scene.add(ambientLight);
    }

    // Bloom post-processing (inspired by Hastur-HP/The-Brain)
    if (renderer && scene) {
      const camera = fg.camera();
      const composer = new EffectComposer(renderer);
      composer.addPass(new RenderPass(scene, camera));
      const bloomPass = new UnrealBloomPass(
        new THREE.Vector2(dims.w, dims.h),
        BLOOM_STRENGTH,
        BLOOM_RADIUS,
        BLOOM_THRESHOLD,
      );
      composer.addPass(bloomPass);
      composer.addPass(new OutputPass());
      composerRef.current = composer;
    }

    // Ambient dust particles for atmospheric depth
    if (scene && !dustRef.current) {
      const dust = createAmbientDust(DUST_COUNT, DUST_RADIUS);
      scene.add(dust);
      dustRef.current = dust;
    }

    // Orbit controls: smooth damped interaction, constrained zoom range
    const controls = fg.controls() as Record<string, unknown>;
    if (controls) {
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.rotateSpeed = 0.8;
      controls.zoomSpeed = 1.2;
      controls.minDistance = 5;
      controls.maxDistance = 5000;
    }

    // d3-force tuning: spread nodes out to fill the brain volume
    fg.d3Force("charge")?.strength(D3_CHARGE_STRENGTH);
    fg.d3Force("link")?.distance(D3_LINK_DISTANCE);
    fg.d3ReheatSimulation();
  }, [dims.w, dims.h]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (fgRef.current?.scene()) {
        modelSceneRef.current = fgRef.current.scene();
        setSceneReady(true);
      }
    }, 0);

    return () => clearTimeout(timer);
  }, [dims.h, dims.w, graphData.nodes.length]);

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

  const handleEngineStop = useCallback(() => {
    fitModelOverlay();
    if (needsInitialZoomRef.current) {
      needsInitialZoomRef.current = false;
      fgRef.current?.zoomToFit(ZOOM_TO_FIT_MS, ZOOM_TO_FIT_PADDING);
    }
  }, [fitModelOverlay]);

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

    // --- Neuron soma (cell body) ---

    // Outer membrane: translucent glowing shell
    const membraneGeo = new THREE.SphereGeometry(r * (isSelected ? 2.0 : 1.6), 24, 24);
    const membraneMat = new THREE.MeshPhongMaterial({
      color,
      emissive: color,
      emissiveIntensity: isSelected ? 0.6 : 0.35,
      transparent: true,
      opacity: node.dimmed ? 0.03 : isSelected ? 0.22 : 0.12,
      depthWrite: false,
      side: THREE.FrontSide,
    });
    group.add(new THREE.Mesh(membraneGeo, membraneMat));

    // Selection targeting ring: spinning 3D torus (inspired by The-Brain)
    if (isSelected) {
      const torusGeo = new THREE.TorusGeometry(r + 2.5, 0.4, 16, 64);
      const torusMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.75,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      const torus = new THREE.Mesh(torusGeo, torusMat);
      torus.rotation.x = Math.PI / 2; // Lay flat like a planetary ring
      torus.name = "selection-ring";
      group.add(torus);

      // Store ref so the animation loop can spin it
      selectionRingRef.current = torus;
    }

    // Inner nucleus: bright core sphere with high emissive
    const nucleusGeo = new THREE.SphereGeometry(r * 0.5, 16, 16);
    const nucleusMat = new THREE.MeshPhongMaterial({
      color,
      emissive: color,
      emissiveIntensity: isSelected ? 0.9 : 0.7,
      shininess: 80,
      transparent: true,
      opacity: node.dimmed ? 0.15 : 0.95,
    });
    group.add(new THREE.Mesh(nucleusGeo, nucleusMat));

    // Main soma sphere with glossy Phong material
    const geo = new THREE.SphereGeometry(r + (isSelected ? 1.0 : 0), 24, 24);
    const mat = new THREE.MeshPhongMaterial({
      color,
      emissive: color,
      emissiveIntensity: isSelected ? 0.6 : 0.45,
      shininess: 80,
      transparent: true,
      opacity: node.dimmed ? 0.15 : 0.85,
    });
    group.add(new THREE.Mesh(geo, mat));

    // --- Dendrite tendrils ---
    if (!node.dimmed) {
      const dendCount = isSelected ? 8 : 5;
      const dendrites = createDendrites(r, color, dendCount);
      group.add(dendrites);
    }

    // --- Readable text label ---
    const label = node.brain.label.length > 28
      ? `${node.brain.label.slice(0, 27)}…`
      : node.brain.label;
    const labelColor = node.dimmed
      ? "rgba(255,255,255,0.25)"
      : isSelected
        ? "rgba(255,255,255,1)"
        : "rgba(255,255,255,0.92)";
    const sprite = makeTextSprite(label, labelColor, r);
    sprite.position.set(0, -(r + 5), 0);
    group.add(sprite);

    return group;
  }, [selectedNodeId]);

  // -- Node click handler with shockwave effect ----------------------------

  const handleNodeClick = useCallback(
    (node: BrainSceneNode) => {
      const nextId = selectedNodeId === node.id ? null : node.id;
      onSelectedNodeIdChange?.(nextId);
      onNodeSelect?.(nextId ? node.brain : null);

      // Clear the old selection ring ref when deselecting
      if (!nextId) {
        selectionRingRef.current = null;
      }

      // Shockwave effect on click (inspired by The-Brain)
      const scene = modelSceneRef.current;
      if (scene && node.x != null && node.y != null) {
        const pos = new THREE.Vector3(node.x ?? 0, node.y ?? 0, node.z ?? 0);
        const color = new THREE.Color(node.color);
        const wave = createShockwave(pos, color);
        scene.add(wave.mesh);
        shockwavesRef.current.push(wave);
      }
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
        linkWidth={(link: BrainSceneLink) => link.width * 1.5}
        linkOpacity={0.55}
        /* Directional link particles for synaptic-fire effect */
        linkDirectionalParticles={3}
        linkDirectionalParticleWidth={2.5}
        linkDirectionalParticleSpeed={0.006}
        linkDirectionalParticleColor={(link: BrainSceneLink) => link.color}
        /* Interactions */
        onNodeClick={handleNodeClick}
        onNodeHover={handleNodeHover}
        onBackgroundClick={() => {
          onSelectedNodeIdChange?.(null);
          onNodeSelect?.(null);
        }}
        onEngineStop={handleEngineStop}
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
