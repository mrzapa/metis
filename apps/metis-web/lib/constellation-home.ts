"use client";

import type { UserStar } from "@/lib/constellation-types";

export const CORE_CENTER_X = 0.56;
export const CORE_CENTER_Y = 0.43;
export const CORE_EXCLUSION_RADIUS = 0.21;
export const ADD_CANDIDATE_HIT_RADIUS_PX = 26;
export const MOBILE_ADD_CANDIDATE_HIT_RADIUS_PX = 38;

const ADDABLE_EDGE_INSET_X = 0.03;
const ADDABLE_EDGE_INSET_Y = 0.04;
const ADDABLE_CORE_BUFFER = 0.04;
const ADDABLE_USER_STAR_BUFFER = 0.05;
const ADDABLE_NODE_BUFFER = 0.04;

export interface Point {
  x: number;
  y: number;
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

function getMinimumAddableStarSize(layer: number): number {
  if (layer <= 0) {
    return 0.38;
  }
  if (layer === 1) {
    return 0.44;
  }
  return 0.5;
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

export function projectBackgroundStar(
  star: Pick<ConstellationFieldStar, "nx" | "ny" | "parallaxFactor">,
  width: number,
  height: number,
  mouse: Point,
): Point {
  return {
    x: star.nx * width + (mouse.x - width / 2) * star.parallaxFactor,
    y: star.ny * height + (mouse.y - height / 2) * star.parallaxFactor,
  };
}

export function isAddableBackgroundStar(
  star: Pick<ConstellationFieldStar, "layer" | "baseSize" | "nx" | "ny">,
  nodes: Array<Pick<ConstellationNodePoint, "x" | "y">>,
  userStars: UserStar[],
  width: number,
  height: number,
): boolean {
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
  userStars: UserStar[],
  pointer: Point,
  mouse: Point,
  width: number,
  height: number,
  hitRadius: number,
): ConstellationFieldStar | null {
  let candidate: ConstellationFieldStar | null = null;
  let candidateDistance = Infinity;

  stars.forEach((star) => {
    if (!isAddableBackgroundStar(star, nodes, userStars, width, height)) {
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
