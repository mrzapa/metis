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
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";

import {
  type BrainGraphData,
  type BrainNode,
  type BrainRenderMode,
  type BrainScope,
  ALL_BRAIN_SCOPES,
  NODE_COLOR_HEX,
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

const BG_COLOR = "#030508";
const FOG_DENSITY = 0.0003;
const CAMERA_TRANSITION_MS = 1200;
const ZOOM_TO_FIT_MS = 800;
const ZOOM_TO_FIT_PADDING = 70;
/** Small z-offset prevents gimbal lock when looking straight down. */
const CAMERA_TOP_VIEW_Z_OFFSET = 0.01;
/** Charge force strength – more negative = stronger node repulsion. */
const D3_CHARGE_STRENGTH = -120;
/** Preferred link distance between connected nodes. */
const D3_LINK_DISTANCE = 80;

// -- Bloom post-processing --------------------------------------------------

/** Bloom strength – tighter, more precise glow on node cores. */
const BLOOM_STRENGTH = 0.16;
/** Bloom radius – tight spread for sharp glows, not hazy halos. */
const BLOOM_RADIUS = 0.06;
/** Bloom threshold – only the very brightest node cores trigger bloom. */
const BLOOM_THRESHOLD = 0.86;
const BLOOM_PULSE_BOOST = 0.12;
const MAX_IDLE_LABELS = 14;
const MAX_SELECTION_LABELS = 20;

const ACTIVITY_PROFILES: Record<
  BrainNode["node_type"],
  {
    label: string;
    pulse: number;
    bloom: number;
    directionalParticles: number;
    directionalSpeed: number;
    directionalWidth: number;
    cameraOffset: number;
  }
> = {
  assistant: {
    label: "Reasoning",
    pulse: 1.15,
    bloom: 0.18,
    directionalParticles: 8,
    directionalSpeed: 0.010,
    directionalWidth: 2.6,
    cameraOffset: 54,
  },
  session: {
    label: "Conversation",
    pulse: 1.0,
    bloom: 0.16,
    directionalParticles: 7,
    directionalSpeed: 0.009,
    directionalWidth: 2.4,
    cameraOffset: 50,
  },
  memory: {
    label: "Memory Recall",
    pulse: 1.1,
    bloom: 0.17,
    directionalParticles: 8,
    directionalSpeed: 0.010,
    directionalWidth: 2.5,
    cameraOffset: 52,
  },
  index: {
    label: "Index Access",
    pulse: 0.95,
    bloom: 0.14,
    directionalParticles: 6,
    directionalSpeed: 0.008,
    directionalWidth: 2.2,
    cameraOffset: 48,
  },
  category: {
    label: "Category Context",
    pulse: 0.9,
    bloom: 0.13,
    directionalParticles: 5,
    directionalSpeed: 0.007,
    directionalWidth: 2.0,
    cameraOffset: 46,
  },
  playbook: {
    label: "Playbook Plan",
    pulse: 1.05,
    bloom: 0.16,
    directionalParticles: 7,
    directionalSpeed: 0.009,
    directionalWidth: 2.4,
    cameraOffset: 52,
  },
};

// -- Ambient dust particle system ---------------------------------------------

/** Number of atmospheric dust particles for depth perception. */
const DUST_COUNT = 800;
/** Radius of the dust cloud. */
const DUST_RADIUS = 1200;

// -- Vignette colours ---------------------------------------------------------

/** Inner purple tint of the cinematic vignette (inspired by Digital-Brain VignettePass). */
const VIGNETTE_PURPLE_TINT = "rgba(30,0,60,0.25)";
/** Outer dark edge of the cinematic vignette. */
const VIGNETTE_DARK_EDGE = "rgba(3,5,8,0.65)";

// -- Helpers ------------------------------------------------------------------

/**
 * Extract a node ID from a force-graph link endpoint.
 * After force simulation, source/target may be replaced by node objects.
 */
function getLinkNodeId(endpoint: unknown): string {
  if (typeof endpoint === "object" && endpoint !== null && "id" in endpoint) {
    return String((endpoint as { id: unknown }).id);
  }
  return String(endpoint);
}

/** Recursively dispose all Three.js geometries, materials, and textures. */
function disposeObject3D(obj: THREE.Object3D): void {
  obj.traverse((child: THREE.Object3D) => {
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

/** Create a canvas-based text sprite for a node label with crisp Apple-style backdrop. */
function makeTextSprite(text: string, color: string, nodeRadius: number): THREE.Sprite {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d")!;
  const fontSize = 56;
  const font = `500 ${fontSize}px -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Helvetica, Arial, sans-serif`;
  ctx.font = font;
  const metrics = ctx.measureText(text);
  const textW = metrics.width;

  const padX = 22;
  const padY = 14;
  canvas.width = textW + padX * 2;
  canvas.height = fontSize + padY * 2;

  // Frosted-glass pill backdrop (semi-transparent dark with subtle border)
  const bgRadius = 12;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Subtle border stroke
  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.lineWidth = 2;
  ctx.fillStyle = "rgba(8, 10, 16, 0.72)";
  ctx.beginPath();
  if (ctx.roundRect) {
    ctx.roundRect(3, 3, canvas.width - 6, canvas.height - 6, bgRadius);
  } else {
    const x = 3, y = 3, w = canvas.width - 6, h = canvas.height - 6, r = bgRadius;
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  ctx.fill();
  ctx.stroke();

  // Text with subtle shadow for legibility against bright backgrounds
  ctx.font = font;
  ctx.shadowColor = "rgba(0,0,0,0.6)";
  ctx.shadowBlur = 6;
  ctx.fillStyle = color;
  ctx.globalAlpha = 1.0;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);
  ctx.shadowBlur = 0;

  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false });
  const sprite = new THREE.Sprite(mat);

  // Scale relative to node size – slightly larger for better readability
  const labelScale = Math.max(0.42, nodeRadius * 0.075);
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
 * Uses per-particle colour and size variation for cinematic quality.
 */
function createAmbientDust(count: number, radius: number): THREE.Points {
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const sizes = new Float32Array(count);

  for (let i = 0; i < count; i++) {
    const i3 = i * 3;
    // Uniform distribution in a sphere
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    const r = radius * Math.cbrt(Math.random());
    positions[i3] = r * Math.sin(phi) * Math.cos(theta);
    positions[i3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    positions[i3 + 2] = r * Math.cos(phi);

    // Colour variation: cool blue to warm lavender
    const hue = 0.58 + Math.random() * 0.12;
    const color = new THREE.Color().setHSL(hue, 0.3 + Math.random() * 0.3, 0.55 + Math.random() * 0.2);
    colors[i3] = color.r;
    colors[i3 + 1] = color.g;
    colors[i3 + 2] = color.b;

    sizes[i] = 0.6 + Math.random() * 1.4;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  geometry.setAttribute("size", new THREE.Float32BufferAttribute(sizes, 1));

  const material = new THREE.PointsMaterial({
    size: 1.2,
    transparent: true,
    opacity: 0.25,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    sizeAttenuation: true,
    vertexColors: true,
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

/**
 * Spawn-burst particle effect (inspired by Vestige's EffectManager.createSpawnBurst).
 * 60 particles fly outward from a position, decelerate, and fade out.
 */
const SPAWN_BURST_COUNT = 60;
const SPAWN_BURST_LIFESPAN_MS = 1800;

interface SpawnBurstHandle {
  points: THREE.Points;
  velocities: THREE.Vector3[];
  startTime: number;
}

function createSpawnBurst(position: THREE.Vector3, color: THREE.Color): SpawnBurstHandle {
  const positions = new Float32Array(SPAWN_BURST_COUNT * 3);
  const velocities: THREE.Vector3[] = [];

  for (let i = 0; i < SPAWN_BURST_COUNT; i++) {
    positions[i * 3] = position.x;
    positions[i * 3 + 1] = position.y;
    positions[i * 3 + 2] = position.z;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    const speed = 0.8 + Math.random() * 1.5;
    velocities.push(new THREE.Vector3(
      Math.sin(phi) * Math.cos(theta) * speed,
      Math.sin(phi) * Math.sin(theta) * speed,
      Math.cos(phi) * speed,
    ));
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));

  const mat = new THREE.PointsMaterial({
    color,
    size: 0.8,
    transparent: true,
    opacity: 1.0,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    sizeAttenuation: true,
  });

  const points = new THREE.Points(geo, mat);
  points.frustumCulled = false;
  points.name = "spawn-burst";
  return { points, velocities, startTime: performance.now() };
}

/**
 * Connection flash line between two nodes (inspired by Vestige's connection flash).
 * A bright additive line that fades to zero over ~1 second.
 */
interface ConnectionFlashHandle {
  line: THREE.Line;
  startTime: number;
}

const FLASH_LIFESPAN_MS = 800;

function createConnectionFlash(from: THREE.Vector3, to: THREE.Vector3, color: THREE.Color): ConnectionFlashHandle {
  const geo = new THREE.BufferGeometry().setFromPoints([from.clone(), to.clone()]);
  const mat = new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity: 1.0,
    linewidth: 2,
    blending: THREE.AdditiveBlending,
  });
  const line = new THREE.Line(geo, mat);
  line.name = "connection-flash";
  return { line, startTime: performance.now() };
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
  companionSignal?: BrainCompanionSignal | null;
  onModelLoadError?: (message: string) => void;
  modelUrl?: string;
  className?: string;
}

export interface BrainCompanionSignal {
  state: string;
  trigger: string;
  summary: string;
  runtimeReady: boolean;
  paused: boolean;
  timestamp: number;
}

export default function BrainGraph3D({
  data,
  filter = "",
  activeScopes = ALL_BRAIN_SCOPES,
  renderMode = "hybrid",
  selectedNodeId = null,
  onSelectedNodeIdChange,
  onNodeSelect,
  companionSignal = null,
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
  const [activityLabel, setActivityLabel] = useState("Idle");
  const [activityProfile, setActivityProfile] = useState({
    directionalParticles: 4,
    directionalSpeed: 0.005,
    directionalWidth: 2.0,
  });
  const lastSignalTsRef = useRef(0);

  // Bloom post-processing pass ref (added to the library's internal composer)
  const bloomPassRef = useRef<UnrealBloomPass | null>(null);
  const outputPassRef = useRef<OutputPass | null>(null);
  // Ambient dust ref
  const dustRef = useRef<THREE.Points | null>(null);
  const pointerTargetRef = useRef(new THREE.Vector2(0, 0));
  const pointerCurrentRef = useRef(new THREE.Vector2(0, 0));
  const presenceTargetRef = useRef(0);
  const presenceCurrentRef = useRef(0);
  const bloomBoostRef = useRef(0);
  // Active shockwave effects
  const shockwavesRef = useRef<ShockwaveHandle[]>([]);
  // Active spawn burst effects (inspired by Vestige)
  const spawnBurstsRef = useRef<SpawnBurstHandle[]>([]);
  // Active connection flash lines (inspired by Vestige)
  const connectionFlashesRef = useRef<ConnectionFlashHandle[]>([]);
  // Selection targeting ring (spinning torus)
  const selectionRingRef = useRef<THREE.Mesh | null>(null);
  // Hover point light for interactive glow feedback
  const hoverLightRef = useRef<THREE.PointLight | null>(null);
  // Cinematic rim lights
  const rimLightsRef = useRef<THREE.PointLight[]>([]);

  // Track container dimensions for the ForceGraph width/height props
  const [dims, setDims] = useState({ w: 800, h: 600 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) {
        setDims({ w: width, h: height });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const handlePointerMove = (event: PointerEvent) => {
      const rect = el.getBoundingClientRect();
      const relX = (event.clientX - rect.left) / rect.width;
      const relY = (event.clientY - rect.top) / rect.height;
      const nx = (relX - 0.5) * 2;
      const ny = (relY - 0.5) * 2;

      pointerTargetRef.current.set(nx, ny);
      presenceTargetRef.current = 1;
      el.style.setProperty("--brain-mx", `${Math.round(relX * 100)}%`);
      el.style.setProperty("--brain-my", `${Math.round(relY * 100)}%`);
    };

    const handlePointerLeave = () => {
      pointerTargetRef.current.set(0, 0);
      presenceTargetRef.current = 0;
      el.style.setProperty("--brain-mx", "50%");
      el.style.setProperty("--brain-my", "50%");
    };

    el.addEventListener("pointermove", handlePointerMove);
    el.addEventListener("pointerleave", handlePointerLeave);
    return () => {
      el.removeEventListener("pointermove", handlePointerMove);
      el.removeEventListener("pointerleave", handlePointerLeave);
    };
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
      // Bloom/output passes are managed by the library's internal composer;
      // we only need to dispose our pass materials.
      if (bloomPassRef.current) {
        bloomPassRef.current.dispose();
        bloomPassRef.current = null;
      }
      if (outputPassRef.current) {
        outputPassRef.current.dispose();
        outputPassRef.current = null;
      }
      if (dustRef.current) {
        dustRef.current.geometry.dispose();
        (dustRef.current.material as THREE.PointsMaterial).dispose();
        dustRef.current = null;
      }
      // Dispose spawn bursts
      for (const burst of spawnBurstsRef.current) {
        burst.points.geometry.dispose();
        (burst.points.material as THREE.PointsMaterial).dispose();
      }
      spawnBurstsRef.current.length = 0;
      // Dispose connection flashes
      for (const flash of connectionFlashesRef.current) {
        flash.line.geometry.dispose();
        (flash.line.material as THREE.LineBasicMaterial).dispose();
      }
      connectionFlashesRef.current.length = 0;
    };
  }, []);

  // -- Animation loop for particle brain overlay and effects ----------------
  useEffect(() => {
    if (!sceneReady) return;
    const clock = new THREE.Clock();
    let rafId: number;
    let elapsedTime = 0;
    const tick = () => {
      const dt = clock.getDelta();
      elapsedTime += dt;

      // Update brain overlay breathing/pulse
      const overlay = modelOverlayRef.current;
      const pointerCurrent = pointerCurrentRef.current;
      const pointerTarget = pointerTargetRef.current;
      pointerCurrent.lerp(pointerTarget, 1 - Math.exp(-dt * 4.5));
      presenceCurrentRef.current +=
        (presenceTargetRef.current - presenceCurrentRef.current) * (1 - Math.exp(-dt * 4.0));

      if (overlay) {
        overlay.setPresence(presenceCurrentRef.current);
        overlay.update(dt);
      }

      // Slowly rotate ambient dust for living atmosphere
      // Plus per-particle bobbing motion (inspired by Vestige ParticleSystem.animate)
      // Throttled to every 4th frame to avoid updating 800 buffer attributes each tick
      const dust = dustRef.current;
      if (dust) {
        dust.rotation.y += dt * (0.015 + presenceCurrentRef.current * 0.01);
        dust.rotation.x += dt * 0.005 + pointerCurrent.y * dt * 0.01;

        const frameCounter = Math.round(elapsedTime * 60);
        if (frameCounter % 4 === 0) {
          const dustPos = dust.geometry.attributes.position as THREE.BufferAttribute;
          for (let i = 0; i < Math.min(dustPos.count, DUST_COUNT); i++) {
            const y = dustPos.getY(i);
            dustPos.setY(i, y + Math.sin(elapsedTime + i * 0.1) * 0.04);
            const x = dustPos.getX(i);
            dustPos.setX(i, x + Math.cos(elapsedTime + i * 0.05) * 0.02);
          }
          dustPos.needsUpdate = true;
        }
      }

      // Animate shockwaves (expand + fade)
      const waves = shockwavesRef.current;
      if (waves.length > 0) {
        const scene = modelSceneRef.current;
        const now = performance.now();
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
      }

      // Rotate the selection targeting ring with gentle wobble
      const ring = selectionRingRef.current;
      if (ring) {
        ring.rotation.z += 0.02;
        ring.rotation.x = Math.PI / 2 + Math.sin(elapsedTime * 1.5) * 0.08;
      }

      // Animate cinematic rim lights (gentle orbit)
      for (const rimLight of rimLightsRef.current) {
        if (rimLight.userData.orbitAngle != null) {
          rimLight.userData.orbitAngle += dt * rimLight.userData.orbitSpeed;
          const a = rimLight.userData.orbitAngle;
          const r = rimLight.userData.orbitRadius;
          rimLight.position.x = Math.cos(a) * r + pointerCurrent.x * 22;
          rimLight.position.z = Math.sin(a) * r - pointerCurrent.y * 18;
          rimLight.position.y = rimLight.userData.baseHeight + pointerCurrent.y * 20;
          rimLight.intensity = rimLight.userData.baseIntensity + presenceCurrentRef.current * 0.12;
        }
      }

      if (bloomPassRef.current) {
        bloomBoostRef.current = Math.max(0, bloomBoostRef.current - dt * 0.11);
        bloomPassRef.current.strength = BLOOM_STRENGTH + bloomBoostRef.current;
      }

      // Animate spawn bursts (particles fly outward + fade)
      // Inspired by Vestige EffectManager.createSpawnBurst
      const scene = modelSceneRef.current;
      const bursts = spawnBurstsRef.current;
      if (bursts.length > 0) {
        const now = performance.now();
        for (let i = bursts.length - 1; i >= 0; i--) {
          const burst = bursts[i];
          const age = now - burst.startTime;
          if (age > SPAWN_BURST_LIFESPAN_MS) {
            if (scene) scene.remove(burst.points);
            burst.points.geometry.dispose();
            (burst.points.material as THREE.PointsMaterial).dispose();
            bursts.splice(i, 1);
            continue;
          }
          const progress = age / SPAWN_BURST_LIFESPAN_MS;
          const posAttr = burst.points.geometry.attributes.position as THREE.BufferAttribute;
          for (let j = 0; j < SPAWN_BURST_COUNT; j++) {
            const vel = burst.velocities[j];
            posAttr.setX(j, posAttr.getX(j) + vel.x * dt * 60);
            posAttr.setY(j, posAttr.getY(j) + vel.y * dt * 60);
            posAttr.setZ(j, posAttr.getZ(j) + vel.z * dt * 60);
            // Decelerate
            vel.multiplyScalar(0.96);
          }
          posAttr.needsUpdate = true;
          const mat = burst.points.material as THREE.PointsMaterial;
          mat.opacity = Math.max(0, 1 - progress * progress);
          mat.size = 0.8 * (1 - progress * 0.5);
        }
      }

      // Animate connection flash lines (fade out)
      // Inspired by Vestige EffectManager connection flashes
      const flashes = connectionFlashesRef.current;
      if (flashes.length > 0) {
        const now = performance.now();
        for (let i = flashes.length - 1; i >= 0; i--) {
          const flash = flashes[i];
          const age = now - flash.startTime;
          if (age > FLASH_LIFESPAN_MS) {
            if (scene) scene.remove(flash.line);
            flash.line.geometry.dispose();
            (flash.line.material as THREE.LineBasicMaterial).dispose();
            flashes.splice(i, 1);
            continue;
          }
          const progress = age / FLASH_LIFESPAN_MS;
          (flash.line.material as THREE.LineBasicMaterial).opacity = 1 - progress;
        }
      }

      // Bloom rendering is handled by ForceGraph3D's internal post-processing
      // composer — no manual composer.render() call needed here.

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

  const graphTopology = useMemo(() => {
    const degreeById = new Map<string, number>();
    const neighborById = new Map<string, Set<string>>();

    for (const node of graphData.nodes) {
      degreeById.set(node.id, 0);
      neighborById.set(node.id, new Set());
    }

    for (const link of graphData.links) {
      const sourceId = getLinkNodeId(link.source);
      const targetId = getLinkNodeId(link.target);
      if (!degreeById.has(sourceId) || !degreeById.has(targetId)) continue;
      degreeById.set(sourceId, (degreeById.get(sourceId) ?? 0) + 1);
      degreeById.set(targetId, (degreeById.get(targetId) ?? 0) + 1);
      neighborById.get(sourceId)?.add(targetId);
      neighborById.get(targetId)?.add(sourceId);
    }

    return { degreeById, neighborById };
  }, [graphData.links, graphData.nodes]);

  const visibleLabelNodeIds = useMemo(() => {
    const labels = new Set<string>();
    const sortedByDegree = [...graphData.nodes].sort(
      (a, b) => (graphTopology.degreeById.get(b.id) ?? 0) - (graphTopology.degreeById.get(a.id) ?? 0),
    );

    if (!selectedNodeId) {
      for (const node of sortedByDegree) {
        if (labels.size >= MAX_IDLE_LABELS) break;
        if (!node.dimmed || node.brain.node_type === "assistant") labels.add(node.id);
      }
      return labels;
    }

    labels.add(selectedNodeId);
    const firstRing = graphTopology.neighborById.get(selectedNodeId) ?? new Set<string>();
    for (const id of firstRing) {
      labels.add(id);
      if (labels.size >= MAX_SELECTION_LABELS) return labels;
    }

    // Fill the remainder with globally central nodes so selection still keeps context.
    for (const node of sortedByDegree) {
      if (labels.size >= MAX_SELECTION_LABELS) break;
      if (labels.has(node.id)) continue;
      labels.add(node.id);
    }
    return labels;
  }, [graphData.nodes, graphTopology.degreeById, graphTopology.neighborById, selectedNodeId]);

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
      renderer.toneMappingExposure = 0.82;
    }

    // Exponential fog for depth perception (distant nodes subtly fade)
    const scene = fg.scene();
    if (scene && !scene.fog) {
      scene.fog = new THREE.FogExp2(BG_COLOR, FOG_DENSITY);
    }

    // Cinematic lighting setup
    if (scene) {
      // Soft ambient fill
      const ambientLight = new THREE.AmbientLight(0x303050, 0.35);
      ambientLight.name = "ambient-light";
      scene.add(ambientLight);

      // Key light: warm directional from top-front-right
      const keyLight = new THREE.DirectionalLight(0xeeddcc, 0.4);
      keyLight.position.set(200, 300, 200);
      keyLight.name = "key-light";
      scene.add(keyLight);

      // Cinematic rim lights (orbiting coloured accents)
      const rimColors = [0x4488ff, 0x8844ff, 0x44ffaa];
      const rimLights: THREE.PointLight[] = [];
      for (let i = 0; i < rimColors.length; i++) {
        const rimLight = new THREE.PointLight(rimColors[i], 0.35, 800, 1.5);
        const angle = (i / rimColors.length) * Math.PI * 2;
        const r = 350;
        rimLight.position.set(Math.cos(angle) * r, 50 + i * 40, Math.sin(angle) * r);
        rimLight.name = `rim-light-${i}`;
        rimLight.userData.orbitAngle = angle;
        rimLight.userData.orbitSpeed = 0.08 + i * 0.02;
        rimLight.userData.orbitRadius = r;
        rimLight.userData.baseHeight = 50 + i * 40;
        rimLight.userData.baseIntensity = 0.35;
        scene.add(rimLight);
        rimLights.push(rimLight);
      }
      rimLightsRef.current = rimLights;

      // Hover light (initially invisible, positioned on hover)
      const hoverLight = new THREE.PointLight(0xffffff, 0, 200, 2);
      hoverLight.name = "hover-light";
      scene.add(hoverLight);
      hoverLightRef.current = hoverLight;
    }

    // Bloom post-processing via the library's built-in EffectComposer.
    // The internal composer already has a RenderPass; we just append
    // the bloom and output passes so rendering stays in a single loop
    // and orbit/pan/zoom controls are never disrupted.
    const composer = fg.postProcessingComposer();
    if (composer && !bloomPassRef.current) {
      const bloomPass = new UnrealBloomPass(
        new THREE.Vector2(dims.w, dims.h),
        BLOOM_STRENGTH,
        BLOOM_RADIUS,
        BLOOM_THRESHOLD,
      );
      composer.addPass(bloomPass);
      const outPass = new OutputPass();
      composer.addPass(outPass);
      bloomPassRef.current = bloomPass;
      outputPassRef.current = outPass;
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

  useEffect(() => {
    if (!selectedNodeId) {
      setActivityLabel("Idle");
      setActivityProfile({
        directionalParticles: 4,
        directionalSpeed: 0.005,
        directionalWidth: 2.0,
      });
      return;
    }

    const selectedNode = graphData.nodes.find((node) => node.id === selectedNodeId);
    if (!selectedNode) return;
    const profile = ACTIVITY_PROFILES[selectedNode.brain.node_type];
    setActivityLabel(profile.label);
    setActivityProfile({
      directionalParticles: profile.directionalParticles,
      directionalSpeed: profile.directionalSpeed,
      directionalWidth: profile.directionalWidth,
    });
  }, [graphData.nodes, selectedNodeId]);

  useEffect(() => {
    if (!companionSignal) return;
    if (companionSignal.timestamp <= lastSignalTsRef.current) return;
    lastSignalTsRef.current = companionSignal.timestamp;

    // Global state-based guardrails first.
    if (!companionSignal.runtimeReady || companionSignal.paused) {
      setActivityLabel("Companion Paused");
      setActivityProfile({
        directionalParticles: 3,
        directionalSpeed: 0.003,
        directionalWidth: 1.8,
      });
      modelOverlayRef.current?.triggerPulse(0.45);
      bloomBoostRef.current = Math.max(bloomBoostRef.current, 0.04);
      return;
    }

    const triggerText = `${companionSignal.trigger} ${companionSignal.state} ${companionSignal.summary}`.toLowerCase();
    const pickProfile = (): keyof typeof ACTIVITY_PROFILES => {
      if (/(memory|recall|reflect|reflection|summar)/.test(triggerText)) return "memory";
      if (/(search|retrieve|query|rag)/.test(triggerText)) return "index";
      if (/(session|conversation|chat)/.test(triggerText)) return "session";
      if (/(playbook|plan|policy|workflow)/.test(triggerText)) return "playbook";
      if (/(identity|self|companion|assistant)/.test(triggerText)) return "assistant";
      return "assistant";
    };

    const profileKey = pickProfile();
    const profile = ACTIVITY_PROFILES[profileKey];
    setActivityLabel(profile.label);
    setActivityProfile({
      directionalParticles: profile.directionalParticles,
      directionalSpeed: profile.directionalSpeed,
      directionalWidth: profile.directionalWidth,
    });
    modelOverlayRef.current?.triggerPulse(profile.pulse);
    bloomBoostRef.current = Math.max(bloomBoostRef.current, BLOOM_PULSE_BOOST + profile.bloom * 0.8);
  }, [companionSignal]);

  useEffect(() => {
    if (!selectedNodeId || autoRotate) return;
    const selectedNode = graphData.nodes.find((node) => node.id === selectedNodeId);
    if (!selectedNode) return;
    if (selectedNode.x == null || selectedNode.y == null || selectedNode.z == null) return;

    const fg = fgRef.current;
    if (!fg) return;

    const profile = ACTIVITY_PROFILES[selectedNode.brain.node_type];
    const cam = fg.camera();
    const viewDir = cam.position.clone().sub(new THREE.Vector3(0, 0, 0)).normalize();
    const focus = new THREE.Vector3(selectedNode.x, selectedNode.y, selectedNode.z);
    const cameraPos = focus.clone().add(viewDir.multiplyScalar(profile.cameraOffset));
    fg.cameraPosition(
      { x: cameraPos.x, y: cameraPos.y, z: cameraPos.z },
      { x: focus.x, y: focus.y, z: focus.z },
      900,
    );
  }, [autoRotate, graphData.nodes, selectedNodeId]);

  // -- Node hover for cursor change and glow feedback -----------------------

  const handleNodeHover = useCallback((node: BrainSceneNode | null) => {
    if (containerRef.current) {
      containerRef.current.style.cursor = node ? "pointer" : "grab";
    }

    // Interactive hover glow: move a point light to the hovered node
    const hoverLight = hoverLightRef.current;
    if (hoverLight) {
      if (node && node.x != null && node.y != null && node.z != null) {
        hoverLight.position.set(node.x, node.y, node.z);
        hoverLight.color.set(node.color);
        hoverLight.intensity = 1.5;
        presenceTargetRef.current = 1;
      } else {
        hoverLight.intensity = 0;
      }
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

  const nodeThreeObject = useCallback((node: BrainSceneNode) => {
    const group = new THREE.Group();
    createdObjectsRef.current.push(group);

    const isSelected = node.id === selectedNodeId;
    const r = node.radius;
    const color = new THREE.Color(node.color);

    // --- Tight additive aura – crisp glow without a diffuse halo ---
    if (!node.dimmed) {
      const auraGeo = new THREE.SphereGeometry(r * (isSelected ? 1.8 : 1.45), 16, 16);
      const auraMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: isSelected ? 0.07 : 0.035,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      group.add(new THREE.Mesh(auraGeo, auraMat));
    }

    // Selection targeting ring: spinning 3D torus
    if (isSelected) {
      const torusGeo = new THREE.TorusGeometry(r + 2.0, 0.28, 16, 64);
      const torusMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.85,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      const torus = new THREE.Mesh(torusGeo, torusMat);
      torus.rotation.x = Math.PI / 2;
      torus.name = "selection-ring";
      group.add(torus);

      // Store ref so the animation loop can spin it
      selectionRingRef.current = torus;
    }

    // Inner nucleus: bright emissive core that triggers bloom
    const nucleusGeo = new THREE.SphereGeometry(r * 0.40, 16, 16);
    const nucleusMat = new THREE.MeshPhongMaterial({
      color: 0xffffff,
      emissive: color,
      emissiveIntensity: isSelected ? 1.0 : 0.80,
      shininess: 120,
      transparent: true,
      opacity: node.dimmed ? 0.12 : 0.95,
    });
    group.add(new THREE.Mesh(nucleusGeo, nucleusMat));

    // Main soma – Apple-quality PBR with clearcoat for a glassy, premium finish
    const geo = new THREE.SphereGeometry(r + (isSelected ? 0.6 : 0), 32, 32);
    const mat = new THREE.MeshPhysicalMaterial({
      color,
      emissive: color,
      emissiveIntensity: isSelected ? 0.55 : 0.42,
      roughness: 0.22,
      metalness: 0.10,
      clearcoat: 0.65,
      clearcoatRoughness: 0.08,
      transparent: true,
      opacity: node.dimmed ? 0.14 : 0.90,
    });
    group.add(new THREE.Mesh(geo, mat));

    // --- Readable text label ---
    const label = node.brain.label.length > 28
      ? `${node.brain.label.slice(0, 27)}\u2026`
      : node.brain.label;
    const labelColor = node.dimmed
      ? "rgba(255,255,255,0.22)"
      : isSelected
        ? "rgba(255,255,255,1)"
        : "rgba(255,255,255,0.90)";
    const shouldShowLabel = visibleLabelNodeIds.has(node.id);
    if (shouldShowLabel) {
      const sprite = makeTextSprite(label, labelColor, r);
      sprite.position.set(0, -(r + 4.5), 0);
      group.add(sprite);
    }

    return group;
  }, [selectedNodeId, visibleLabelNodeIds]);

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
      if (scene && node.x != null && node.y != null && node.z != null) {
        const pos = new THREE.Vector3(node.x, node.y, node.z);
        const color = new THREE.Color(node.color);
        const profile = ACTIVITY_PROFILES[node.brain.node_type];
        const nodeDegree = graphTopology.degreeById.get(node.id) ?? 0;
        const degreeBoost = Math.min(0.28, nodeDegree * 0.02);
        modelOverlayRef.current?.triggerPulse(profile.pulse + degreeBoost);
        bloomBoostRef.current = Math.max(
          bloomBoostRef.current,
          BLOOM_PULSE_BOOST + profile.bloom + degreeBoost * 0.2,
        );
        const wave = createShockwave(pos, color);
        scene.add(wave.mesh);
        shockwavesRef.current.push(wave);

        // Spawn-burst particle effect (inspired by Vestige)
        const burst = createSpawnBurst(pos, color);
        scene.add(burst.points);
        spawnBurstsRef.current.push(burst);

        // Connection flash lines to neighbour nodes (inspired by Vestige)
        // Flash bright lines from clicked node to all connected neighbours
        for (const link of graphData.links) {
          // After force simulation, source/target may be objects or strings
          const sourceId = getLinkNodeId(link.source);
          const targetId = getLinkNodeId(link.target);
          let neighbourId: string | undefined;
          if (sourceId === node.id) neighbourId = targetId;
          else if (targetId === node.id) neighbourId = sourceId;
          if (!neighbourId) continue;

          // Find the neighbour node's position
          const neighbour = graphData.nodes.find((n: BrainSceneNode) => n.id === neighbourId);
          if (neighbour && neighbour.x != null && neighbour.y != null && neighbour.z != null) {
            const nPos = new THREE.Vector3(neighbour.x, neighbour.y, neighbour.z);
            const flash = createConnectionFlash(pos, nPos, color);
            scene.add(flash.line);
            connectionFlashesRef.current.push(flash);
          }
        }
      }
    },
    [graphData.links, graphData.nodes, graphTopology.degreeById, onNodeSelect, onSelectedNodeIdChange, selectedNodeId],
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
  // (Replaced by persistent node-type legend; retained const to avoid refactor)

  // -- Render --------------------------------------------------------------

  return (
    <div
      ref={containerRef}
      className={`relative h-full w-full overflow-hidden ${className}`}
      aria-label="Brain graph"
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-90"
        style={{
          background: "radial-gradient(circle 420px at var(--brain-mx, 50%) var(--brain-my, 50%), rgba(118,205,255,0.14) 0%, rgba(122,123,255,0.08) 28%, rgba(0,0,0,0) 68%)",
        }}
      />

      <ForceGraph3D<BrainSceneNode, BrainSceneLink>
        ref={fgRef}
        width={dims.w}
        height={dims.h}
        graphData={graphData}
        backgroundColor={BG_COLOR}
        showNavInfo={false}
        /* Disable node dragging – nodes are fixed at brain-region positions */
        enableNodeDrag={false}
        /* Node styling */
        nodeThreeObject={nodeThreeObject}
        nodeThreeObjectExtend={false}
        /* Link styling — refined for Apple-level polish */
        linkColor={(link: BrainSceneLink) => link.color}
        linkWidth={(link: BrainSceneLink) => link.width * 1.8}
        linkOpacity={0.45}
        linkCurvature={0.15}
        linkCurveRotation={0}
        /* Directional link particles for synaptic-fire effect */
        linkDirectionalParticles={activityProfile.directionalParticles}
        linkDirectionalParticleWidth={activityProfile.directionalWidth}
        linkDirectionalParticleSpeed={activityProfile.directionalSpeed}
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

      {/* Cinematic vignette overlay — purple-tinted edges */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: `radial-gradient(ellipse at center, transparent 50%, ${VIGNETTE_PURPLE_TINT} 75%, ${VIGNETTE_DARK_EDGE} 100%)`,
        }}
      />

      {/* Node type legend — bottom-left, persistent */}
      <div className="pointer-events-none absolute bottom-5 left-5 flex flex-col gap-1.5 rounded-2xl border border-white/10 bg-black/40 px-3.5 py-3 backdrop-blur-xl">
        <p className="mb-0.5 text-[9px] font-semibold uppercase tracking-[0.22em] text-white/35">
          Node types
        </p>
        {(
          [
            ["category", "Category"],
            ["index", "Index"],
            ["session", "Session"],
            ["assistant", "Assistant"],
            ["memory", "Memory"],
            ["playbook", "Playbook"],
          ] as const
        ).map(([type, label]) => (
          <div key={type} className="flex items-center gap-2">
            <span
              className="size-2 shrink-0 rounded-full"
              style={{ backgroundColor: NODE_COLOR_HEX[type], boxShadow: `0 0 6px ${NODE_COLOR_HEX[type]}` }}
            />
            <span className="text-[10px] font-medium tracking-wide text-white/55">{label}</span>
          </div>
        ))}
        <div className="mx-0 my-1.5 border-t border-white/8" />
        <div className="flex items-center gap-2">
          <span className="size-1.5 rounded-full bg-cyan-300 shadow-[0_0_8px_rgba(103,232,249,0.85)]" />
          <span className="text-[10px] tracking-wide text-white/65">{activityLabel}</span>
        </div>
        <div className="flex items-center gap-3 text-[9px] text-white/30">
          <span>drag · orbit</span>
          <span className="text-white/15">·</span>
          <span>scroll · zoom</span>
        </div>
      </div>

      {/* Camera controls toolbar — glass-morphism design */}
      <div className="absolute right-4 top-4 flex flex-col gap-0.5 rounded-2xl border border-white/20 bg-white/8 p-1.5 backdrop-blur-xl">
        {(["front", "top", "side"] as const).map((view) => (
          <button
            key={view}
            type="button"
            title={`${view.charAt(0).toUpperCase() + view.slice(1)} view`}
            onClick={() => setCameraView(view)}
            className="rounded-xl px-3 py-1.5 text-[11px] font-medium capitalize tracking-wide text-white/70 transition-all duration-200 hover:bg-white/15 hover:text-white/95"
          >
            {view}
          </button>
        ))}
        <div className="mx-2 my-1 border-t border-white/12" />
        <button
          type="button"
          title={autoRotate ? "Stop rotation" : "Auto-rotate"}
          onClick={() => setAutoRotate((prev: boolean) => !prev)}
          className={`rounded-xl px-3 py-1.5 text-[11px] font-medium tracking-wide transition-all duration-200 ${
            autoRotate
              ? "bg-white/15 text-white/95"
              : "text-white/70 hover:bg-white/15 hover:text-white/95"
          }`}
        >
          {autoRotate ? "⏸ Pause" : "↻ Orbit"}
        </button>
        <button
          type="button"
          title="Reset view"
          onClick={resetView}
          className="rounded-xl px-3 py-1.5 text-[11px] font-medium tracking-wide text-white/70 transition-all duration-200 hover:bg-white/15 hover:text-white/95"
        >
          ⌘ Reset
        </button>
      </div>
    </div>
  );
}
