"use client";

import {
  clampBackgroundZoomFactor,
  constellationPointToWorldPoint,
  getConstellationCameraScale,
  projectBackgroundStar,
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

export const STAR_FOCUS_PANEL_BREAKPOINT_PX = 1024;
export const STAR_FOCUS_SETTLE_TIMEOUT_MS = 900;
export const STAR_FOCUS_CLOSE_LOCK_MS = 900;

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

export function buildProjectedUserStarHitTarget(
  star: Pick<UserStar, "id" | "x" | "y" | "size">,
  viewportWidth: number,
  viewportHeight: number,
  camera: BackgroundCameraState,
  hitRadiusBoost = 0,
): ProjectedUserStarHitTarget {
  const projected = projectConstellationPoint(
    { x: star.x, y: star.y },
    viewportWidth,
    viewportHeight,
    camera,
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
  mouse: Point,
  hitRadius: number,
): ProjectedHitTarget {
  const projected = projectBackgroundStar(star, viewportWidth, viewportHeight, mouse);

  return {
    id: star.id,
    x: projected.x,
    y: projected.y,
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
