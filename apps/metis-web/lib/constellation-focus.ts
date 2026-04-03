"use client";

import {
  clampBackgroundZoomFactor,
  constellationPointToWorldPoint,
  getConstellationCameraScale,
  projectConstellationPoint,
  type BackgroundCameraState,
  type ConstellationFieldStar,
  type Point,
} from "@/lib/constellation-home";
import type { UserStar } from "@/lib/constellation-types";

export interface ConstellationCameraSnapshot {
  x: number;
  y: number;
  zoomFactor: number;
}

export interface StarFocusLayout {
  focusZoomFactor: number;
  viewportX: number;
  viewportY: number;
}

export interface ProjectedHitTarget {
  id: string;
  x: number;
  y: number;
  hitRadius: number;
}

export interface ProjectedUserStarHitTarget extends ProjectedHitTarget {
  point: Point;
}

export interface UserStarVisualProfile {
  asymmetryOffset: Point;
  coreIntensity: number;
  haloFalloff: number;
  hasDiffraction: boolean;
  spikeAngle: number;
  tintBias: number;
  twinklePhase: number;
}

export const STAR_FOCUS_PANEL_BREAKPOINT_PX = 1024;
export const STAR_FOCUS_SETTLE_TIMEOUT_MS = 900;
export const STAR_FOCUS_CLOSE_LOCK_MS = 900;
export const USER_STAR_PARALLAX_FACTOR = 0.02;

export const DESKTOP_STAR_FOCUS_LAYOUT: StarFocusLayout = {
  focusZoomFactor: 1.72,
  viewportX: 0.34,
  viewportY: 0.48,
};

export const MOBILE_STAR_FOCUS_LAYOUT: StarFocusLayout = {
  focusZoomFactor: 1.42,
  viewportX: 0.5,
  viewportY: 0.3,
};

export function cloneCameraSnapshot(
  snapshot: ConstellationCameraSnapshot,
): ConstellationCameraSnapshot {
  return {
    x: snapshot.x,
    y: snapshot.y,
    zoomFactor: snapshot.zoomFactor,
  };
}

export function getStarFocusLayout(
  viewportWidth: number,
  viewportHeight: number,
): StarFocusLayout {
  const isDesktop =
    viewportWidth >= STAR_FOCUS_PANEL_BREAKPOINT_PX && viewportWidth >= viewportHeight;

  return isDesktop ? DESKTOP_STAR_FOCUS_LAYOUT : MOBILE_STAR_FOCUS_LAYOUT;
}

export function buildCameraForConstellationPoint(
  point: Point,
  viewportWidth: number,
  viewportHeight: number,
  zoomFactor: number,
  layout: StarFocusLayout,
): ConstellationCameraSnapshot {
  const clampedZoomFactor = clampBackgroundZoomFactor(zoomFactor);
  const scale = getConstellationCameraScale(clampedZoomFactor);
  const worldPoint = constellationPointToWorldPoint(point, viewportWidth, viewportHeight);

  return {
    x: worldPoint.x - ((layout.viewportX - 0.5) * viewportWidth) / scale,
    y: worldPoint.y - ((layout.viewportY - 0.5) * viewportHeight) / scale,
    zoomFactor: clampedZoomFactor,
  };
}

export function buildStarFocusCamera(
  star: Pick<UserStar, "x" | "y" | "size">,
  viewportWidth: number,
  viewportHeight: number,
  layout = getStarFocusLayout(viewportWidth, viewportHeight),
): ConstellationCameraSnapshot {
  const viewportFactor = Math.min(
    1.15,
    Math.max(0.82, Math.min(viewportWidth, viewportHeight) / 980),
  );
  const sizeFactor = Math.min(1.08, Math.max(0.92, 1 + ((star.size ?? 1) - 1) * 0.1));

  return buildCameraForConstellationPoint(
    { x: star.x, y: star.y },
    viewportWidth,
    viewportHeight,
    layout.focusZoomFactor / viewportFactor / sizeFactor,
    layout,
  );
}

function hashString(value: string): number {
  let hash = 2166136261;

  for (const character of value) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }

  return hash >>> 0;
}

function nextSeed(seed: number): number {
  return (Math.imul(seed, 1664525) + 1013904223) >>> 0;
}

function sampleSeededUnit(seed: number): [number, number] {
  const nextValue = nextSeed(seed);

  return [nextValue, nextValue / 4294967296];
}

export function createUserStarVisualProfile(starId: string): UserStarVisualProfile {
  let seed = hashString(starId);
  let value: number;

  [seed, value] = sampleSeededUnit(seed);
  const haloFalloff = 0.5 + value * 0.24;

  [seed, value] = sampleSeededUnit(seed);
  const coreIntensity = 0.88 + value * 0.34;

  [seed, value] = sampleSeededUnit(seed);
  const tintBias = value * 2 - 1;

  [seed, value] = sampleSeededUnit(seed);
  const hasDiffraction = value > 0.52;

  [seed, value] = sampleSeededUnit(seed);
  const spikeAngle = value * Math.PI;

  [seed, value] = sampleSeededUnit(seed);
  const twinklePhase = value * Math.PI * 2;

  [seed, value] = sampleSeededUnit(seed);
  const offsetX = (value * 2 - 1) * 0.34;

  [seed, value] = sampleSeededUnit(seed);
  const offsetY = (value * 2 - 1) * 0.28;

  return {
    asymmetryOffset: {
      x: offsetX,
      y: offsetY,
    },
    coreIntensity,
    haloFalloff,
    hasDiffraction,
    spikeAngle,
    tintBias,
    twinklePhase,
  };
}

export function projectUserStarScreenPoint(
  star: Pick<UserStar, "x" | "y">,
  viewportWidth: number,
  viewportHeight: number,
  camera: BackgroundCameraState,
  mouse?: Point,
): Point {
  const projected = projectConstellationPoint(
    { x: star.x, y: star.y },
    viewportWidth,
    viewportHeight,
    camera,
  );
  const hasVisiblePointer = mouse
    && mouse.x >= 0
    && mouse.x <= viewportWidth
    && mouse.y >= 0
    && mouse.y <= viewportHeight;
  const parallaxX = hasVisiblePointer ? (mouse.x - viewportWidth / 2) * USER_STAR_PARALLAX_FACTOR : 0;
  const parallaxY = hasVisiblePointer ? (mouse.y - viewportHeight / 2) * USER_STAR_PARALLAX_FACTOR : 0;

  return {
    x: projected.x + parallaxX,
    y: projected.y + parallaxY,
  };
}

export function buildProjectedUserStarHitTarget(
  star: Pick<UserStar, "id" | "x" | "y" | "size">,
  viewportWidth: number,
  viewportHeight: number,
  camera: BackgroundCameraState,
  hitRadiusBoost = 0,
  mouse?: Point,
): ProjectedUserStarHitTarget {
  const projected = projectUserStarScreenPoint(
    star,
    viewportWidth,
    viewportHeight,
    camera,
    mouse,
  );

  return {
    id: star.id,
    x: projected.x,
    y: projected.y,
    hitRadius: Math.max(16, star.size * 10 + 8 + hitRadiusBoost),
    point: { x: star.x, y: star.y },
  };
}

export function buildProjectedCandidateHitTarget(
  star: Pick<ConstellationFieldStar, "id" | "nx" | "ny" | "parallaxFactor">,
  viewportWidth: number,
  viewportHeight: number,
  _mouse: Point,
  hitRadius: number,
): ProjectedHitTarget {
  return {
    id: star.id,
    x: star.nx * viewportWidth,
    y: star.ny * viewportHeight,
    hitRadius,
  };
}

export function findClosestProjectedTarget<T extends ProjectedHitTarget>(
  targets: readonly T[],
  point: Point,
): T | null {
  let candidate: T | null = null;
  let candidateDistance = Infinity;

  targets.forEach((target) => {
    const distance = Math.hypot(target.x - point.x, target.y - point.y);
    if (distance <= target.hitRadius && distance < candidateDistance) {
      candidate = target;
      candidateDistance = distance;
    }
  });

  return candidate;
}

export function isCameraSettled(
  current: BackgroundCameraState | ConstellationCameraSnapshot,
  target: ConstellationCameraSnapshot,
  options?: {
    positionEpsilon?: number;
    zoomEpsilon?: number;
  },
): boolean {
  const positionEpsilon = options?.positionEpsilon ?? 0.75;
  const zoomEpsilon = options?.zoomEpsilon ?? 0.015;

  return (
    Math.abs(current.x - target.x) <= positionEpsilon
    && Math.abs(current.y - target.y) <= positionEpsilon
    && Math.abs(current.zoomFactor - target.zoomFactor) <= zoomEpsilon
  );
}

export function projectFocusedStar(
  star: Pick<UserStar, "x" | "y">,
  viewportWidth: number,
  viewportHeight: number,
  camera: BackgroundCameraState,
): Point {
  return projectConstellationPoint(
    { x: star.x, y: star.y },
    viewportWidth,
    viewportHeight,
    camera,
  );
}
