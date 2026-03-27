"use client";

import type { UserStar } from "@/lib/constellation-types";

export const CORE_CENTER_X = 0.56;
export const CORE_CENTER_Y = 0.43;
export const CORE_EXCLUSION_RADIUS = 0.21;
export const ADD_CANDIDATE_HIT_RADIUS_PX = 26;
export const MOBILE_ADD_CANDIDATE_HIT_RADIUS_PX = 38;
export const CONSTELLATION_FACULTY_CENTER_X = 0.5;
export const CONSTELLATION_FACULTY_CENTER_Y = 0.5;
export const CONSTELLATION_FACULTY_RING_RADIUS = 0.34;
export const CONSTELLATION_FACULTY_BRIDGE_RATIO = 1.15;

const ADDABLE_EDGE_INSET_X = 0.03;
const ADDABLE_EDGE_INSET_Y = 0.04;
const ADDABLE_CORE_BUFFER = 0.04;
const ADDABLE_USER_STAR_BUFFER = 0.05;
const ADDABLE_NODE_BUFFER = 0.04;

export interface Point {
  x: number;
  y: number;
}

export interface ConstellationFacultyMetadata {
  id: string;
  label: string;
  description: string;
  angle: number;
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

export interface ConstellationFacultyMatch {
  faculty: ConstellationFacultyMetadata;
  distance: number;
}

export interface ConstellationFacultyInference {
  primary: ConstellationFacultyMatch;
  secondary: ConstellationFacultyMatch | null;
  bridgeSuggestion: ConstellationFacultyMatch | null;
}

function createConstellationFaculty(
  id: string,
  label: string,
  description: string,
  angle: number,
): ConstellationFacultyMetadata {
  return {
    id,
    label,
    description,
    angle,
    x: CONSTELLATION_FACULTY_CENTER_X + Math.cos(angle) * CONSTELLATION_FACULTY_RING_RADIUS,
    y: CONSTELLATION_FACULTY_CENTER_Y + Math.sin(angle) * CONSTELLATION_FACULTY_RING_RADIUS,
  };
}

export const CONSTELLATION_FACULTIES: ConstellationFacultyMetadata[] = [
  createConstellationFaculty("perception", "Perception", "Sensory intake, pattern detection, and direct observation.", -Math.PI / 2),
  createConstellationFaculty("knowledge", "Knowledge", "Structured facts, concepts, and durable associations.", -Math.PI / 2 + (Math.PI * 2) / 11),
  createConstellationFaculty("memory", "Memory", "Retention, recall, and context continuity.", -Math.PI / 2 + (Math.PI * 4) / 11),
  createConstellationFaculty("reasoning", "Reasoning", "Inference, logic, and evidence-driven judgment.", -Math.PI / 2 + (Math.PI * 6) / 11),
  createConstellationFaculty("skills", "Skills", "Procedural capability, practiced technique, and execution fluency.", -Math.PI / 2 + (Math.PI * 8) / 11),
  createConstellationFaculty("strategy", "Strategy", "Planning, tradeoffs, and directional choice.", -Math.PI / 2 + (Math.PI * 10) / 11),
  createConstellationFaculty("personality", "Personality", "Style, temperament, and expressive posture.", -Math.PI / 2 + (Math.PI * 12) / 11),
  createConstellationFaculty("values", "Values", "Principles, priorities, and constraints.", -Math.PI / 2 + (Math.PI * 14) / 11),
  createConstellationFaculty("synthesis", "Synthesis", "Cross-domain integration and meaning-making.", -Math.PI / 2 + (Math.PI * 16) / 11),
  createConstellationFaculty("autonomy", "Autonomy", "Independent intent, self-direction, and self-governance.", -Math.PI / 2 + (Math.PI * 18) / 11),
  createConstellationFaculty("emergence", "Emergence", "Novel capability, adaptation, and new structure from existing parts.", -Math.PI / 2 + (Math.PI * 20) / 11),
];

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
