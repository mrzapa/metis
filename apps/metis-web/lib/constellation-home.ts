"use client";

import type { UserStar } from "@/lib/constellation-types";

export const CORE_CENTER_X = 0.5;
export const CORE_CENTER_Y = 0.5;
export const CORE_EXCLUSION_RADIUS = 0.21;
export const ADD_CANDIDATE_HIT_RADIUS_PX = 26;
export const MOBILE_ADD_CANDIDATE_HIT_RADIUS_PX = 38;
export const MIN_BACKGROUND_ZOOM_FACTOR = 0.75;
export const MAX_BACKGROUND_ZOOM_FACTOR = 2000;
export const STAR_DIVE_ZOOM_THRESHOLD = 200;
export const STAR_DIVE_FULL_ZOOM = 800;
export const CONSTELLATION_FACULTY_CENTER_X = CORE_CENTER_X;
export const CONSTELLATION_FACULTY_CENTER_Y = CORE_CENTER_Y;
export const CONSTELLATION_FACULTY_RING_RADIUS = 0.34;
export const CONSTELLATION_FACULTY_BRIDGE_RATIO = 1.15;

const ADDABLE_EDGE_INSET_X = 0.03;
const ADDABLE_EDGE_INSET_Y = 0.04;
const ADDABLE_CORE_BUFFER = 0.04;
const ADDABLE_USER_STAR_BUFFER = 0.05;
const ADDABLE_NODE_BUFFER = 0.04;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export interface Point {
  x: number;
  y: number;
}

export interface BackgroundCameraState {
  x: number;
  y: number;
  zoomFactor: number;
}

export interface WorldBounds {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export interface ConstellationShape {
  /** Offsets from anchor star (star[0]) in normalized canvas coordinates. star[0] is always {dx:0, dy:0}. */
  stars: ReadonlyArray<{ readonly dx: number; readonly dy: number }>;
  /** Index pairs into stars[] forming the stick-figure lines. */
  edges: ReadonlyArray<readonly [number, number]>;
}

export interface ConstellationFacultyMetadata {
  id: string;
  label: string;
  description: string;
  angle: number;
  x: number;
  y: number;
  shape: ConstellationShape;
}

export interface ConstellationFieldStar {
  id: string;
  nx: number;
  ny: number;
  layer: number;
  baseSize: number;
  brightness: number;
  twinkle: boolean;
  twinkleSpeed: number;
  twinklePhase: number;
  parallaxFactor: number;
  hasDiffraction: boolean;
}

export interface ConstellationNodePoint {
  x: number;
  y: number;
}

export interface ConstellationFacultyMatch {
  faculty: ConstellationFacultyMetadata;
  distance: number;
}

export interface ConstellationFacultyInference {
  primary: ConstellationFacultyMatch;
  secondary: ConstellationFacultyMatch | null;
  bridgeSuggestion: ConstellationFacultyMatch | null;
}

export type ConstellationFacultyColor = [number, number, number];

const DEFAULT_FACULTY_COLOR: ConstellationFacultyColor = [208, 216, 232];

export const FACULTY_PALETTE = {
  autonomy: [199, 218, 121],
  emergence: [148, 153, 239],
  knowledge: [232, 184, 74],
  memory: [160, 133, 228],
  perception: [119, 181, 235],
  personality: [232, 144, 198],
  reasoning: [129, 220, 198],
  skills: [104, 219, 170],
  strategy: [232, 128, 103],
  synthesis: [136, 209, 238],
  values: [214, 108, 120],
} as const satisfies Record<string, ConstellationFacultyColor>;

function createConstellationFaculty(
  id: string,
  label: string,
  description: string,
  angle: number,
  shape: ConstellationShape,
): ConstellationFacultyMetadata {
  return {
    id,
    label,
    description,
    angle,
    x: CONSTELLATION_FACULTY_CENTER_X + Math.cos(angle) * CONSTELLATION_FACULTY_RING_RADIUS,
    y: CONSTELLATION_FACULTY_CENTER_Y + Math.sin(angle) * CONSTELLATION_FACULTY_RING_RADIUS,
    shape,
  };
}

export const CONSTELLATION_FACULTIES: ConstellationFacultyMetadata[] = [
  // Perception (top) — Perseus-inspired 6-star arc chain
  createConstellationFaculty("perception", "Perception", "Sensory intake, pattern detection, and direct observation.", -Math.PI / 2, {
    stars: [{dx:0,dy:0},{dx:-0.080,dy:0.032},{dx:-0.140,dy:0.008},{dx:0.068,dy:-0.024},{dx:0.120,dy:0.040},{dx:-0.040,dy:-0.040}],
    edges: [[0,1],[1,2],[0,3],[3,4],[0,5]],
  }),
  // Knowledge (upper-right) — Auriga-inspired 5-star pentagon
  createConstellationFaculty("knowledge", "Knowledge", "Structured facts, concepts, and durable associations.", -Math.PI / 2 + (Math.PI * 2) / 11, {
    stars: [{dx:0,dy:0},{dx:0.060,dy:0},{dx:0.080,dy:0.060},{dx:0.020,dy:0.100},{dx:-0.040,dy:0.060}],
    edges: [[0,1],[1,2],[2,3],[3,4],[4,0]],
  }),
  // Memory (right) — Draco-inspired 5-star winding chain
  createConstellationFaculty("memory", "Memory", "Retention, recall, and context continuity.", -Math.PI / 2 + (Math.PI * 4) / 11, {
    stars: [{dx:0,dy:0},{dx:0.040,dy:-0.040},{dx:0.068,dy:-0.100},{dx:0.020,dy:-0.140},{dx:-0.056,dy:-0.060}],
    edges: [[0,1],[1,2],[2,3],[0,4]],
  }),
  // Reasoning (lower-right) — Hercules-inspired 6-star keystone + spurs
  createConstellationFaculty("reasoning", "Reasoning", "Inference, logic, and evidence-driven judgment.", -Math.PI / 2 + (Math.PI * 6) / 11, {
    stars: [{dx:0,dy:0},{dx:-0.040,dy:-0.064},{dx:-0.072,dy:-0.040},{dx:-0.040,dy:0.056},{dx:0,dy:0.100},{dx:0.040,dy:-0.092}],
    edges: [[0,1],[1,2],[2,3],[3,0],[0,4],[1,5]],
  }),
  // Skills (lower) — Gemini-inspired 5-star twin chain
  createConstellationFaculty("skills", "Skills", "Procedural capability, practiced technique, and execution fluency.", -Math.PI / 2 + (Math.PI * 8) / 11, {
    stars: [{dx:0,dy:0},{dx:-0.060,dy:-0.024},{dx:-0.044,dy:0.068},{dx:0.028,dy:0.080},{dx:-0.016,dy:0.120}],
    edges: [[0,1],[0,3],[1,2],[2,4],[3,4]],
  }),
  // Strategy (bottom) — Ursa Major Big Dipper 7-star bowl + handle
  createConstellationFaculty("strategy", "Strategy", "Planning, tradeoffs, and directional choice.", -Math.PI / 2 + (Math.PI * 10) / 11, {
    stars: [{dx:0,dy:0},{dx:0.060,dy:-0.012},{dx:0.060,dy:0.056},{dx:0,dy:0.044},{dx:-0.048,dy:0.020},{dx:-0.100,dy:-0.008},{dx:-0.140,dy:-0.040}],
    edges: [[0,1],[1,2],[2,3],[3,0],[3,4],[4,5],[5,6]],
  }),
  // Personality (lower-left) — Lyra-inspired 5-star apex + parallelogram
  createConstellationFaculty("personality", "Personality", "Style, temperament, and expressive posture.", -Math.PI / 2 + (Math.PI * 12) / 11, {
    stars: [{dx:0,dy:0},{dx:-0.036,dy:0.072},{dx:0.036,dy:0.072},{dx:-0.036,dy:0.108},{dx:0.036,dy:0.108}],
    edges: [[0,1],[0,2],[1,2],[1,3],[2,4],[3,4]],
  }),
  // Values (left) — Boötes-inspired 6-star kite
  createConstellationFaculty("values", "Values", "Principles, priorities, and constraints.", -Math.PI / 2 + (Math.PI * 14) / 11, {
    stars: [{dx:0,dy:0},{dx:-0.040,dy:-0.060},{dx:0.040,dy:-0.060},{dx:-0.044,dy:-0.128},{dx:0.040,dy:-0.128},{dx:0,dy:-0.168}],
    edges: [[0,1],[0,2],[1,3],[2,4],[3,4],[3,5],[4,5]],
  }),
  // Synthesis (upper-left) — Andromeda-inspired 5-star chain + branches
  createConstellationFaculty("synthesis", "Synthesis", "Cross-domain integration and meaning-making.", -Math.PI / 2 + (Math.PI * 16) / 11, {
    stars: [{dx:0,dy:0},{dx:-0.040,dy:-0.060},{dx:-0.072,dy:-0.100},{dx:-0.040,dy:0.072},{dx:0,dy:0.100}],
    edges: [[0,1],[1,2],[0,3],[0,4]],
  }),
  // Autonomy (upper-left) — Cygnus Northern Cross 5-star
  createConstellationFaculty("autonomy", "Autonomy", "Independent intent, self-direction, and self-governance.", -Math.PI / 2 + (Math.PI * 18) / 11, {
    stars: [{dx:0,dy:0},{dx:0,dy:0.072},{dx:-0.060,dy:0.072},{dx:0.060,dy:0.072},{dx:0,dy:0.140}],
    edges: [[0,1],[1,2],[1,3],[1,4]],
  }),
  // Emergence (upper) — Cassiopeia W/M 5-star zigzag
  createConstellationFaculty("emergence", "Emergence", "Novel capability, adaptation, and new structure from existing parts.", -Math.PI / 2 + (Math.PI * 20) / 11, {
    stars: [{dx:0,dy:0},{dx:-0.060,dy:-0.040},{dx:-0.120,dy:0},{dx:0.060,dy:-0.040},{dx:0.120,dy:0}],
    edges: [[2,1],[1,0],[0,3],[3,4]],
  }),
];

export function getFacultyColor(facultyId?: string): ConstellationFacultyColor {
  if (facultyId && facultyId in FACULTY_PALETTE) {
    return FACULTY_PALETTE[facultyId as keyof typeof FACULTY_PALETTE];
  }
  return DEFAULT_FACULTY_COLOR;
}

export function getInfluenceColors(
  primaryDomainId?: string,
  relatedDomainIds?: string[],
): ConstellationFacultyColor[] {
  const domainIds = [primaryDomainId, ...(relatedDomainIds ?? [])].filter(
    (domainId): domainId is string => Boolean(domainId),
  );
  const uniqueDomainIds = [...new Set(domainIds)];

  if (uniqueDomainIds.length === 0) {
    return [DEFAULT_FACULTY_COLOR];
  }

  return uniqueDomainIds.map((domainId) => getFacultyColor(domainId));
}

/** Returns true if this index was autonomously created by the METIS Companion */
export function isAutonomousStar(indexId?: string): boolean {
  return typeof indexId === "string" && indexId.startsWith("auto_");
}

/** Extract faculty from an auto-generated index ID like "auto_emergence_abc123" */
export function getAutoStarFaculty(indexId?: string): string | undefined {
  if (!isAutonomousStar(indexId)) return undefined;
  const parts = (indexId ?? "").split("_");
  return parts.length >= 2 ? parts[1] : undefined;
}

export function mixConstellationColors(
  colors: readonly ConstellationFacultyColor[],
): ConstellationFacultyColor {
  if (colors.length === 0) {
    return DEFAULT_FACULTY_COLOR;
  }

  const totals = colors.reduce(
    (accumulator, [r, g, b]) => {
      accumulator[0] += r;
      accumulator[1] += g;
      accumulator[2] += b;
      return accumulator;
    },
    [0, 0, 0] as [number, number, number],
  );

  return [
    Math.round(totals[0] / colors.length),
    Math.round(totals[1] / colors.length),
    Math.round(totals[2] / colors.length),
  ];
}

export function clampBackgroundZoomFactor(value: number): number {
  if (!Number.isFinite(value)) {
    return 1;
  }

  return clamp(value, MIN_BACKGROUND_ZOOM_FACTOR, MAX_BACKGROUND_ZOOM_FACTOR);
}

export function getBackgroundCameraScale(zoomFactor: number): number {
  return 1 / Math.sqrt(clampBackgroundZoomFactor(zoomFactor));
}

export function getConstellationCameraScale(zoomFactor: number): number {
  return 0.08 + getBackgroundCameraScale(zoomFactor) * 0.92;
}

export function worldToScreenPoint(
  point: Point,
  width: number,
  height: number,
  camera: BackgroundCameraState,
  parallaxOffset?: Point,
): Point {
  const scale = getBackgroundCameraScale(camera.zoomFactor);
  const offset = parallaxOffset ?? { x: 0, y: 0 };

  return {
    x: (point.x - camera.x) * scale + width / 2 + offset.x,
    y: (point.y - camera.y) * scale + height / 2 + offset.y,
  };
}

export function constellationPointToWorldPoint(
  point: Point,
  width: number,
  height: number,
): Point {
  return {
    x: (point.x - 0.5) * width,
    y: (point.y - 0.5) * height,
  };
}

export function worldPointToConstellationPoint(
  point: Point,
  width: number,
  height: number,
): Point {
  return {
    x: point.x / width + 0.5,
    y: point.y / height + 0.5,
  };
}

export function projectConstellationPoint(
  point: Point,
  width: number,
  height: number,
  camera: BackgroundCameraState,
  parallaxOffset?: Point,
): Point {
  const scale = getConstellationCameraScale(camera.zoomFactor);
  const offset = parallaxOffset ?? { x: 0, y: 0 };
  const worldPoint = constellationPointToWorldPoint(point, width, height);

  return {
    x: (worldPoint.x - camera.x) * scale + width / 2 + offset.x,
    y: (worldPoint.y - camera.y) * scale + height / 2 + offset.y,
  };
}

export function screenToConstellationPoint(
  point: Point,
  width: number,
  height: number,
  camera: BackgroundCameraState,
  parallaxOffset?: Point,
): Point {
  const scale = getConstellationCameraScale(camera.zoomFactor);
  const offset = parallaxOffset ?? { x: 0, y: 0 };

  return worldPointToConstellationPoint(
    {
      x: (point.x - width / 2 - offset.x) / scale + camera.x,
      y: (point.y - height / 2 - offset.y) / scale + camera.y,
    },
    width,
    height,
  );
}

export function screenToWorldPoint(
  point: Point,
  width: number,
  height: number,
  camera: BackgroundCameraState,
  parallaxOffset?: Point,
): Point {
  const scale = getBackgroundCameraScale(camera.zoomFactor);
  const offset = parallaxOffset ?? { x: 0, y: 0 };

  return {
    x: (point.x - width / 2 - offset.x) / scale + camera.x,
    y: (point.y - height / 2 - offset.y) / scale + camera.y,
  };
}

export function getBackgroundViewportWorldBounds(
  width: number,
  height: number,
  camera: BackgroundCameraState,
  padding = 0,
): WorldBounds {
  return {
    bottom: screenToWorldPoint({ x: width / 2, y: height + padding }, width, height, camera).y,
    left: screenToWorldPoint({ x: -padding, y: height / 2 }, width, height, camera).x,
    right: screenToWorldPoint({ x: width + padding, y: height / 2 }, width, height, camera).x,
    top: screenToWorldPoint({ x: width / 2, y: -padding }, width, height, camera).y,
  };
}

function getMinimumAddableStarSize(layer: number): number {
  if (layer <= 0) {
    return 0.38;
  }
  if (layer === 1) {
    return 0.44;
  }
  return 0.5;
}

function getConstellationFacultyMatches(point: Point): ConstellationFacultyMatch[] {
  return [...CONSTELLATION_FACULTIES]
    .map((faculty) => ({
      faculty,
      distance: Math.hypot(point.x - faculty.x, point.y - faculty.y),
    }))
    .sort((left, right) => left.distance - right.distance);
}

export function buildOutwardPlacement(
  targetX: number,
  targetY: number,
  existingStars: number,
): [number, number] {
  const dx = targetX - CORE_CENTER_X;
  const dy = targetY - CORE_CENTER_Y;
  const angle = Math.atan2(dy, dx);
  const dist = Math.hypot(dx, dy);
  const shell = Math.floor(existingStars / 8) + 1;
  const minRadius = CORE_EXCLUSION_RADIUS + shell * 0.055;
  const radius = Math.max(minRadius, dist);
  const nx = Math.min(0.96, Math.max(0.04, CORE_CENTER_X + Math.cos(angle) * radius));
  const ny = Math.min(0.95, Math.max(0.06, CORE_CENTER_Y + Math.sin(angle) * radius));
  return [nx, ny];
}

export function inferConstellationFaculty(point: Point): ConstellationFacultyInference {
  const [primary, secondary = null] = getConstellationFacultyMatches(point);
  const bridgeSuggestion =
    secondary && primary.distance > 0 && secondary.distance / primary.distance <= CONSTELLATION_FACULTY_BRIDGE_RATIO
      ? secondary
      : null;

  return {
    primary,
    secondary,
    bridgeSuggestion,
  };
}

export function getConstellationBridgeSuggestion(point: Point): ConstellationFacultyMatch | null {
  return inferConstellationFaculty(point).bridgeSuggestion;
}

export function projectBackgroundStar(
  star: Pick<ConstellationFieldStar, "nx" | "ny" | "parallaxFactor">,
  width: number,
  height: number,
  _mouse: Point,
): Point {
  return {
    // Keep hover and selection targets anchored to the same screen-space
    // coordinates used by the WebGL starfield renderer.
    x: star.nx * width,
    y: star.ny * height,
  };
}

export function isAddableBackgroundStar(
  star: Pick<ConstellationFieldStar, "layer" | "baseSize" | "nx" | "ny">,
  nodes: Array<Pick<ConstellationNodePoint, "x" | "y">>,
  userStars: Array<Pick<UserStar, "x" | "y">>,
  width: number,
  height: number,
  hasUserContent: boolean = true,
): boolean {
  // Only allow adding new stars once the user has uploaded files or built an index
  if (!hasUserContent && userStars.length === 0) {
    return false;
  }

  if (star.layer > 2 || star.baseSize < getMinimumAddableStarSize(star.layer)) {
    return false;
  }

  const distanceFromCore = Math.hypot(star.nx - CORE_CENTER_X, star.ny - CORE_CENTER_Y);
  if (distanceFromCore < CORE_EXCLUSION_RADIUS + ADDABLE_CORE_BUFFER) {
    return false;
  }

  if (
    star.nx < ADDABLE_EDGE_INSET_X
    || star.nx > 1 - ADDABLE_EDGE_INSET_X
    || star.ny < ADDABLE_EDGE_INSET_Y
    || star.ny > 1 - ADDABLE_EDGE_INSET_Y
  ) {
    return false;
  }

  if (
    userStars.some(
      (userStar) => Math.hypot(userStar.x - star.nx, userStar.y - star.ny) < ADDABLE_USER_STAR_BUFFER,
    )
  ) {
    return false;
  }

  if (
    nodes.some(
      (node) => Math.hypot(node.x / width - star.nx, node.y / height - star.ny) < ADDABLE_NODE_BUFFER,
    )
  ) {
    return false;
  }

  return true;
}

export function findHoveredAddCandidate(
  stars: ConstellationFieldStar[],
  nodes: Array<Pick<ConstellationNodePoint, "x" | "y">>,
  userStars: Array<Pick<UserStar, "x" | "y">>,
  pointer: Point,
  mouse: Point,
  width: number,
  height: number,
  hitRadius: number,
  hasUserContent: boolean = true,
): ConstellationFieldStar | null {
  let candidate: ConstellationFieldStar | null = null;
  let candidateDistance = Infinity;

  stars.forEach((star) => {
    if (!isAddableBackgroundStar(star, nodes, userStars, width, height, hasUserContent)) {
      return;
    }

    const projected = projectBackgroundStar(star, width, height, mouse);
    const distance = Math.hypot(projected.x - pointer.x, projected.y - pointer.y);

    if (distance <= hitRadius && distance < candidateDistance) {
      candidate = star;
      candidateDistance = distance;
    }
  });

  return candidate;
}

export function getPreviewConnectionNodes<T extends Pick<ConstellationNodePoint, "x" | "y">>(
  candidate: Pick<ConstellationFieldStar, "nx" | "ny">,
  nodes: T[],
  width: number,
  height: number,
): T[] {
  return [...nodes]
    .sort(
      (left, right) =>
        Math.hypot(left.x / width - candidate.nx, left.y / height - candidate.ny)
        - Math.hypot(right.x / width - candidate.nx, right.y / height - candidate.ny),
    )
    .slice(0, 2);
}

/**
 * Compute the Star Dive focus strength (0→1) from the current zoom factor.
 * Returns 0 below STAR_DIVE_ZOOM_THRESHOLD and 1 at STAR_DIVE_FULL_ZOOM.
 */
export function getStarDiveFocusStrength(zoomFactor: number): number {
  if (zoomFactor <= STAR_DIVE_ZOOM_THRESHOLD) return 0;
  if (zoomFactor >= STAR_DIVE_FULL_ZOOM) return 1;
  return clamp(
    (zoomFactor - STAR_DIVE_ZOOM_THRESHOLD) / (STAR_DIVE_FULL_ZOOM - STAR_DIVE_ZOOM_THRESHOLD),
    0,
    1,
  );
}

/**
 * Find the best star to focus on during a Star Dive.
 * Picks the brightest star nearest the viewport center, weighted by distance.
 */
export function findStarDiveFocusTarget<
  T extends { id: string; screenX: number; screenY: number; brightness: number },
>(
  stars: readonly T[],
  viewportWidth: number,
  viewportHeight: number,
): T | null {
  const cx = viewportWidth / 2;
  const cy = viewportHeight / 2;
  const maxSearchRadius = Math.min(viewportWidth, viewportHeight) * 0.4;

  let best: T | null = null;
  let bestScore = -Infinity;

  for (const star of stars) {
    const dx = star.screenX - cx;
    const dy = star.screenY - cy;
    const dist = Math.hypot(dx, dy);
    if (dist > maxSearchRadius) continue;
    const proximityScore = 1 - dist / maxSearchRadius;
    const score = star.brightness * 1.6 + proximityScore * 0.8;
    if (score > bestScore) {
      bestScore = score;
      best = star;
    }
  }

  return best;
}
