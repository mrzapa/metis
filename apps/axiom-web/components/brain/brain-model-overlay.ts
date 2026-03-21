"use client";

/**
 * Procedural particle-based brain overlay.
 *
 * Generates an anatomically-inspired brain-shaped point cloud with distinct
 * hemispheres, temporal lobes, frontal protrusion, occipital ridge, and a
 * brain-stem/cerebellum. Rendered with custom ShaderMaterial for a glowing,
 * holographic neural aesthetic with high brightness and recognisable shape.
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
const PARTICLE_COUNT = 32_000;
/** Extra scale so the brain shell comfortably encloses graph nodes. */
const BRAIN_SCALE_FACTOR = 1.15;
/** Base colour of the brain particles (brighter warm-blue-white). */
const BRAIN_COLOR = new THREE.Color(0xb8e0ff);

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

  const cellIndex = ix + iy * 157 + iz * 113;

  const a = hash(cellIndex);
  const b = hash(cellIndex + 1);
  const c = hash(cellIndex + 157);
  const d = hash(cellIndex + 158);
  const e = hash(cellIndex + 113);
  const f = hash(cellIndex + 114);
  const g = hash(cellIndex + 270);
  const h = hash(cellIndex + 271);

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

/** Fractal Brownian Motion with 4 octaves for richer cortical detail. */
function fbm3(x: number, y: number, z: number): number {
  let val = 0;
  let amp = 0.5;
  let freq = 1.0;
  for (let i = 0; i < 4; i++) {
    val += amp * noise3(x * freq, y * freq, z * freq);
    amp *= 0.5;
    freq *= 2.0;
  }
  return val;
}

// -- Brain point-cloud generator --------------------------------------------

/**
 * Produce an anatomically-inspired brain point cloud with:
 * - Two cerebral hemispheres with a longitudinal fissure
 * - Frontal lobe protrusion
 * - Temporal lobe bulges on the sides
 * - Occipital ridge at the back
 * - Pronounced cortical folds (sulci/gyri via noise)
 * - Deeper sulcus lines along key anatomical boundaries
 * - Interior volumetric particles for neural-pathway density
 * - Brain stem / cerebellum at the bottom-back
 */
function generateBrainPoints(count: number): Float32Array {
  const positions = new Float32Array(count * 3);
  const surfaceCount = Math.floor(count * 0.70);
  const sulcusCount = Math.floor(count * 0.08);
  const volumeCount = Math.floor(count * 0.10);
  const stemCount = Math.floor(count * 0.07);
  const temporalCount = count - surfaceCount - sulcusCount - volumeCount - stemCount;
  let idx = 0;

  const pushPoint = (x: number, y: number, z: number) => {
    positions[idx++] = x;
    positions[idx++] = y;
    positions[idx++] = z;
  };

  /** Sample a uniform point on the unit sphere (Marsaglia). */
  function randomOnSphere(): [number, number, number] {
    let u: number, v: number, s: number;
    do {
      u = Math.random() * 2 - 1;
      v = Math.random() * 2 - 1;
      s = u * u + v * v;
    } while (s >= 1 || s === 0);
    const factor = Math.sqrt(1 - s);
    return [2 * u * factor, 2 * v * factor, 1 - 2 * s];
  }

  /**
   * Deform a unit-sphere point into the brain ellipsoid shape with
   * anatomical-lobe modifiers, then add cortical fold noise.
   */
  function deformToBrain(nx: number, ny: number, nz: number): [number, number, number] {
    // Base ellipsoid radii (wider laterally, shorter vertically, moderate depth)
    let rx = 0.55;
    let ry = 0.44;
    let rz = 0.50;

    // Frontal lobe: bulge forward when z > 0 and y > -0.1
    if (nz > 0.2 && ny > -0.2) {
      rz += 0.06 * Math.max(0, nz);
      ry += 0.03 * Math.max(0, nz) * Math.max(0, ny + 0.2);
    }

    // Occipital lobe: slight protrusion at the back
    if (nz < -0.3) {
      rz += 0.04 * Math.abs(nz);
    }

    // Temporal lobes: wider bulge at the sides, lower half
    if (ny < 0.1 && Math.abs(nx) > 0.3) {
      rx += 0.05 * Math.abs(nx) * (1 - ny);
      ry += 0.02 * Math.abs(nx);
    }

    // Flatten bottom slightly (brain rests on the skull base)
    if (ny < -0.5) {
      ry *= 0.85;
    }

    let px = nx * rx;
    let py = ny * ry;
    let pz = nz * rz;

    // Hemisphere split: longitudinal fissure along x
    const gap = 0.025;
    px += px >= 0 ? gap : -gap;

    // Cortical fold displacement via noise (stronger for more visible sulci)
    const noiseScale = 4.0;
    const noiseAmp = 0.08;
    const displacement = fbm3(
      px * noiseScale + 7.3,
      py * noiseScale + 2.1,
      pz * noiseScale + 5.7,
    );
    const radial = Math.sqrt(px * px + py * py + pz * pz) || 1;
    px += (px / radial) * displacement * noiseAmp;
    py += (py / radial) * displacement * noiseAmp;
    pz += (pz / radial) * displacement * noiseAmp;

    return [px, py, pz];
  }

  // -- Surface particles (two hemispheres with anatomical lobes) --
  for (let i = 0; i < surfaceCount; i++) {
    const [nx, ny, nz] = randomOnSphere();
    const [px, py, pz] = deformToBrain(nx, ny, nz);

    // Slight random scatter
    const scatter = 0.006;
    pushPoint(
      px + (Math.random() - 0.5) * scatter,
      py + (Math.random() - 0.5) * scatter,
      pz + (Math.random() - 0.5) * scatter,
    );
  }

  // -- Sulcus-line particles: concentrate along key anatomical grooves --
  for (let i = 0; i < sulcusCount; i++) {
    const [nx, ny, nz] = randomOnSphere();
    // Central sulcus (divides frontal/parietal) — runs roughly across the top
    // Lateral sulcus (Sylvian fissure) — runs along the side
    const t = Math.random();
    let snx = nx;
    let sny = ny;
    let snz = nz;
    if (t < 0.4) {
      // Central sulcus: near the equator on x, running along z
      sny = 0.15 + (Math.random() - 0.5) * 0.08;
      snz = nz;
      snx = nx;
    } else if (t < 0.7) {
      // Lateral sulcus: lower sides
      sny = -0.15 + (Math.random() - 0.5) * 0.06;
      snx = nx > 0 ? 0.5 + Math.random() * 0.3 : -(0.5 + Math.random() * 0.3);
    }
    // Re-normalise to sphere surface
    const len = Math.sqrt(snx * snx + sny * sny + snz * snz) || 1;
    const [px, py, pz] = deformToBrain(snx / len, sny / len, snz / len);

    // Inset sulcus particles slightly inward to create visible grooves
    const inset = 0.015 + Math.random() * 0.01;
    const r = Math.sqrt(px * px + py * py + pz * pz) || 1;
    pushPoint(
      px - (px / r) * inset,
      py - (py / r) * inset,
      pz - (pz / r) * inset,
    );
  }

  // -- Temporal lobe reinforcement: extra density on the side lobes --
  for (let i = 0; i < temporalCount; i++) {
    const angle = Math.random() * Math.PI * 2;
    const side = Math.random() > 0.5 ? 1 : -1;
    // Temporal lobes sit low and to the sides
    const nx = side * (0.5 + Math.random() * 0.4);
    const ny = -0.25 + (Math.random() - 0.5) * 0.3;
    const nz = Math.cos(angle) * 0.3;
    const len = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;
    const [px, py, pz] = deformToBrain(nx / len, ny / len, nz / len);
    const scatter = 0.008;
    pushPoint(
      px + (Math.random() - 0.5) * scatter,
      py + (Math.random() - 0.5) * scatter,
      pz + (Math.random() - 0.5) * scatter,
    );
  }

  // -- Volumetric interior particles (neural pathways feel) --
  for (let i = 0; i < volumeCount; i++) {
    const r = Math.random() * 0.38;
    const [nx, ny, nz] = randomOnSphere();
    pushPoint(
      nx * r * 0.52,
      ny * r * 0.42,
      nz * r * 0.48,
    );
  }

  // -- Brain stem / cerebellum extension --
  for (let i = 0; i < stemCount; i++) {
    const t = Math.random();
    if (t < 0.6) {
      // Brain stem: narrow cylinder downward
      const stemLen = 0.30;
      const baseRadius = 0.10 * (1 - t * 0.5);
      const angle = Math.random() * Math.PI * 2;
      const rr = baseRadius * Math.sqrt(Math.random());
      pushPoint(
        Math.cos(angle) * rr,
        -0.42 - t * stemLen,
        Math.sin(angle) * rr + 0.04,
      );
    } else {
      // Cerebellum: small rounded lobe at the bottom-back
      const [nx, ny, nz] = randomOnSphere();
      const cR = 0.18;
      pushPoint(
        nx * cR * 0.7,
        -0.38 + ny * cR * 0.4 - 0.06,
        nz * cR * 0.6 - 0.22,
      );
    }
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
  varying float vDepth;

  void main() {
    vRandom = aRandom;

    // Breathing displacement along normals (increased amplitude for visible pulse)
    vec3 pos = position;
    float pulse = sin(uTime * 0.8 + aRandom * 6.2831) * 0.008;
    pos += normalize(pos) * pulse;

    vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);

    // Size attenuation: particles shrink with distance
    gl_PointSize = uPointSize * (220.0 / -mvPosition.z);

    // Alpha fades slightly for particles further from camera
    vAlpha = clamp(1.0 - (-mvPosition.z - 40.0) / 700.0, 0.25, 1.0);
    vDepth = clamp(-mvPosition.z / 500.0, 0.0, 1.0);

    gl_Position = projectionMatrix * mvPosition;
  }
`;

const FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uColor;
  uniform float uTime;
  varying float vAlpha;
  varying float vRandom;
  varying float vDepth;

  void main() {
    // Soft circle shape
    float dist = distance(gl_PointCoord, vec2(0.5));
    if (dist > 0.5) discard;

    float circle = 1.0 - smoothstep(0.0, 0.5, dist);

    // Colour variation: warm pinks at edges, cool blues in center
    float hueShift = vRandom * 0.25;
    vec3 warmTint = vec3(0.18, -0.02, 0.06); // subtle pink/purple
    vec3 variantTint = vec3(hueShift * 0.14, -hueShift * 0.04, hueShift * 0.22);
    vec3 col = uColor + variantTint + warmTint * (1.0 - vDepth) * 0.35;

    // Gentle pulse glow (slightly brighter baseline for bloom interaction)
    float glow = 0.85 + 0.15 * sin(uTime * 1.0 + vRandom * 6.2831);

    // Higher base alpha for brighter, more visible brain
    gl_FragColor = vec4(col * glow, circle * vAlpha * 0.80);
  }
`;

// -- Bounds helper ----------------------------------------------------------

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
 * Generates a high-detail brain with ~32k particles for a bright, recognisable
 * brain shape. Keeps the async signature for API compatibility.
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
      uPointSize: { value: 3.0 },
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

  // Minimal light rig for API compatibility
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
