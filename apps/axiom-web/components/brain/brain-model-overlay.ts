"use client";

/**
 * Procedural particle-based brain overlay.
 *
 * Instead of loading a GLB mesh (which causes zoom/clipping issues and looks
 * plastic), this module generates a brain-shaped point cloud procedurally and
 * renders it with custom ShaderMaterial for a glowing, holographic neural
 * aesthetic.  Inspired by victors1681/3dbrain.
 *
 * The brain shape is produced by sampling points on a pair of deformed
 * ellipsoids (left/right hemispheres) plus a brain-stem extension, with
 * simplex-style noise displacement to mimic sulci and gyri.
 */

import * as THREE from "three";

// -- Public interface -------------------------------------------------------

interface GraphPoint {
  x?: number;
  y?: number;
  z?: number;
}

export interface BrainModelOverlayHandle {
  root: THREE.Group;
  lightRig: THREE.Group;
  fitToGraph: (nodes: readonly GraphPoint[]) => void;
  update: (deltaSeconds: number) => void;
  dispose: () => void;
}

// -- Constants ---------------------------------------------------------------

/** Number of particles that form the brain shape. */
const PARTICLE_COUNT = 18_000;
/** Extra scale so the brain shell comfortably encloses graph nodes. */
const BRAIN_SCALE_FACTOR = 1.15;
/** Base colour of the brain particles (soft blue-white). */
const BRAIN_COLOR = new THREE.Color(0x84ccff);

// -- Procedural noise (hash-based, no external deps) ------------------------

function hash(n: number): number {
  const x = Math.sin(n) * 43758.5453;
  return x - Math.floor(x);
}

function noise3(x: number, y: number, z: number): number {
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  const iz = Math.floor(z);
  const fx = x - ix;
  const fy = y - iy;
  const fz = z - iz;

  const ux = fx * fx * (3 - 2 * fx);
  const uy = fy * fy * (3 - 2 * fy);
  const uz = fz * fz * (3 - 2 * fz);

  const n = ix + iy * 157 + iz * 113;

  const a = hash(n);
  const b = hash(n + 1);
  const c = hash(n + 157);
  const d = hash(n + 158);
  const e = hash(n + 113);
  const f = hash(n + 114);
  const g = hash(n + 270);
  const h = hash(n + 271);

  return (
    a +
    (b - a) * ux +
    (c - a) * uy +
    (a - b - c + d) * ux * uy +
    (e - a) * uz +
    (a - b - e + f) * ux * uz +
    (a - c - e + g) * uy * uz +
    (-a + b + c - d + e - f - g + h) * ux * uy * uz
  );
}

/** Fractal Brownian Motion with 3 octaves. */
function fbm3(x: number, y: number, z: number): number {
  let val = 0;
  let amp = 0.5;
  let freq = 1.0;
  for (let i = 0; i < 3; i++) {
    val += amp * noise3(x * freq, y * freq, z * freq);
    amp *= 0.5;
    freq *= 2.0;
  }
  return val;
}

// -- Brain point-cloud generator --------------------------------------------

/**
 * Produce a brain-shaped point cloud.
 *
 * Strategy:
 * 1. Sample points uniformly on a unit sphere.
 * 2. Deform into an ellipsoid (wider than tall, elongated front-to-back).
 * 3. Split into two hemispheres with a narrow gap.
 * 4. Apply noise displacement for cortical folds.
 * 5. Add a brain-stem / cerebellum extension below.
 * 6. Mix surface points with a few interior volumetric points.
 */
function generateBrainPoints(count: number): Float32Array {
  const positions = new Float32Array(count * 3);
  const surfaceCount = Math.floor(count * 0.82);
  const volumeCount = Math.floor(count * 0.10);
  const stemCount = count - surfaceCount - volumeCount;
  let idx = 0;

  const pushPoint = (x: number, y: number, z: number) => {
    positions[idx++] = x;
    positions[idx++] = y;
    positions[idx++] = z;
  };

  // -- Surface particles (two hemispheres) --
  for (let i = 0; i < surfaceCount; i++) {
    // Uniform point on unit sphere (Marsaglia method)
    let u: number, v: number, s: number;
    do {
      u = Math.random() * 2 - 1;
      v = Math.random() * 2 - 1;
      s = u * u + v * v;
    } while (s >= 1 || s === 0);
    const factor = Math.sqrt(1 - s);
    const nx = 2 * u * factor;
    const ny = 2 * v * factor;
    const nz = 1 - 2 * s;

    // Ellipsoid deformation: wider laterally (x), taller (y), deep (z)
    const rx = 0.52; // half-width (left-right)
    const ry = 0.42; // half-height (top-bottom)
    const rz = 0.48; // half-depth (front-back)

    let px = nx * rx;
    let py = ny * ry;
    let pz = nz * rz;

    // Hemisphere split: push halves apart along x
    const gap = 0.03;
    px += px >= 0 ? gap : -gap;

    // Cortical fold displacement via noise
    const noiseScale = 3.5;
    const noiseAmp = 0.06;
    const displacement = fbm3(
      px * noiseScale + 7.3,
      py * noiseScale + 2.1,
      pz * noiseScale + 5.7,
    );
    const radial = Math.sqrt(px * px + py * py + pz * pz) || 1;
    px += (px / radial) * displacement * noiseAmp;
    py += (py / radial) * displacement * noiseAmp;
    pz += (pz / radial) * displacement * noiseAmp;

    // Slight random scatter to avoid perfectly crisp surface
    const scatter = 0.008;
    px += (Math.random() - 0.5) * scatter;
    py += (Math.random() - 0.5) * scatter;
    pz += (Math.random() - 0.5) * scatter;

    pushPoint(px, py, pz);
  }

  // -- Volumetric interior particles (neural pathways feel) --
  for (let i = 0; i < volumeCount; i++) {
    const r = Math.random() * 0.38;
    let u2: number, v2: number, s2: number;
    do {
      u2 = Math.random() * 2 - 1;
      v2 = Math.random() * 2 - 1;
      s2 = u2 * u2 + v2 * v2;
    } while (s2 >= 1 || s2 === 0);
    const f2 = Math.sqrt(1 - s2);
    pushPoint(
      2 * u2 * f2 * r * 0.52,
      2 * v2 * f2 * r * 0.42,
      (1 - 2 * s2) * r * 0.48,
    );
  }

  // -- Brain stem / cerebellum extension --
  for (let i = 0; i < stemCount; i++) {
    const t = Math.random();
    const stemLen = 0.28;
    const baseRadius = 0.14 * (1 - t * 0.6);
    const angle = Math.random() * Math.PI * 2;
    const rr = baseRadius * Math.sqrt(Math.random());
    pushPoint(
      Math.cos(angle) * rr,
      -0.42 - t * stemLen,
      Math.sin(angle) * rr + 0.05,
    );
  }

  return positions;
}

// -- Custom shader material -------------------------------------------------

const VERTEX_SHADER = /* glsl */ `
  uniform float uTime;
  uniform float uPointSize;
  attribute float aRandom;
  varying float vAlpha;
  varying float vRandom;

  void main() {
    vRandom = aRandom;

    // Subtle breathing displacement along normals (approximated by position dir)
    vec3 pos = position;
    float pulse = sin(uTime * 0.8 + aRandom * 6.2831) * 0.003;
    pos += normalize(pos) * pulse;

    vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);

    // Size attenuation: particles shrink with distance
    gl_PointSize = uPointSize * (200.0 / -mvPosition.z);

    // Alpha fades slightly for particles further from camera
    vAlpha = clamp(1.0 - (-mvPosition.z - 50.0) / 600.0, 0.15, 1.0);

    gl_Position = projectionMatrix * mvPosition;
  }
`;

const FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uColor;
  uniform float uTime;
  varying float vAlpha;
  varying float vRandom;

  void main() {
    // Soft circle shape (discard hard square edges)
    float dist = distance(gl_PointCoord, vec2(0.5));
    if (dist > 0.5) discard;

    float circle = 1.0 - smoothstep(0.0, 0.5, dist);

    // Subtle colour variation per particle
    float hueShift = vRandom * 0.15;
    vec3 col = uColor + vec3(hueShift * 0.1, -hueShift * 0.05, hueShift * 0.2);

    // Gentle pulse glow
    float glow = 0.7 + 0.3 * sin(uTime * 1.2 + vRandom * 6.2831);

    gl_FragColor = vec4(col * glow, circle * vAlpha * 0.55);
  }
`;

// -- Bounds helper (same logic as before) -----------------------------------

function computeBounds(nodes: readonly GraphPoint[]): {
  center: THREE.Vector3;
  maxDimension: number;
} | null {
  const points = nodes.filter(
    (node) =>
      Number.isFinite(node.x) &&
      Number.isFinite(node.y),
  );

  if (points.length === 0) return null;

  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let minZ = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  let maxZ = Number.NEGATIVE_INFINITY;

  for (const point of points) {
    minX = Math.min(minX, point.x ?? 0);
    minY = Math.min(minY, point.y ?? 0);
    minZ = Math.min(minZ, point.z ?? 0);
    maxX = Math.max(maxX, point.x ?? 0);
    maxY = Math.max(maxY, point.y ?? 0);
    maxZ = Math.max(maxZ, point.z ?? 0);
  }

  return {
    center: new THREE.Vector3(
      (minX + maxX) / 2,
      (minY + maxY) / 2,
      (minZ + maxZ) / 2,
    ),
    maxDimension: Math.max(maxX - minX, maxY - minY, maxZ - minZ),
  };
}

// -- Public API -------------------------------------------------------------

/**
 * Create the procedural brain particle overlay.
 *
 * Unlike the previous GLB-based approach, this is synchronous and never fails
 * to load a network resource, but we keep the async signature for API compat.
 */
export async function loadBrainModelOverlay(
  _modelUrl?: string,
): Promise<BrainModelOverlayHandle> {
  // Generate procedural brain point cloud
  const positions = generateBrainPoints(PARTICLE_COUNT);

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));

  // Per-particle random value for shader variation
  const randoms = new Float32Array(PARTICLE_COUNT);
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    randoms[i] = Math.random();
  }
  geometry.setAttribute("aRandom", new THREE.Float32BufferAttribute(randoms, 1));

  const material = new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0.0 },
      uColor: { value: BRAIN_COLOR.clone() },
      uPointSize: { value: 2.5 },
    },
    vertexShader: VERTEX_SHADER,
    fragmentShader: FRAGMENT_SHADER,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    depthTest: true,
  });

  const points = new THREE.Points(geometry, material);
  points.frustumCulled = false;
  points.renderOrder = -1;

  const root = new THREE.Group();
  root.name = "brain-model-overlay";
  root.add(points);

  // The particle brain doesn't need a heavy light rig; use a minimal group
  // to keep the interface compatible.
  const lightRig = new THREE.Group();
  lightRig.name = "brain-model-light-rig";

  const fitToGraph = (nodes: readonly GraphPoint[]) => {
    const bounds = computeBounds(nodes);
    const center = bounds?.center ?? new THREE.Vector3(0, 0, 0);
    const maxDimension = Math.max(bounds?.maxDimension ?? 80, 40);
    const targetScale = maxDimension * BRAIN_SCALE_FACTOR;

    root.position.copy(center);
    root.scale.setScalar(targetScale);
    lightRig.position.copy(center);
  };

  let disposed = false;

  const update = (deltaSeconds: number) => {
    if (disposed) return;
    material.uniforms.uTime.value += deltaSeconds;
  };

  const dispose = () => {
    disposed = true;
    geometry.dispose();
    material.dispose();
  };

  return { root, lightRig, fitToGraph, update, dispose };
}
