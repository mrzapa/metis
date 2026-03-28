import type { BrainPassMetadata } from "@/lib/api";
import {
  buildOutwardPlacement,
  CONSTELLATION_FACULTIES,
  CORE_CENTER_X,
  CORE_CENTER_Y,
  CORE_EXCLUSION_RADIUS,
} from "@/lib/constellation-home";

const DEFAULT_FACULTY_ID = "knowledge";
const FACULTY_SWEEP_OFFSETS = [-0.18, -0.09, 0, 0.09, 0.18] as const;
const FACULTY_VERTICAL_RATIO = 0.82;

export interface ConstellationPlacementDecision {
  facultyId: string;
  secondaryFacultyIds: string[];
  rationale: string;
  confidence: number | null;
  provider: string;
}

function isKnownFacultyId(facultyId: string): boolean {
  return CONSTELLATION_FACULTIES.some((faculty) => faculty.id === facultyId);
}

function normalizeFacultyId(facultyId: string | undefined): string {
  if (facultyId && isKnownFacultyId(facultyId)) {
    return facultyId;
  }
  return DEFAULT_FACULTY_ID;
}

export function getConstellationPlacementDecision(input: {
  brain_pass?: BrainPassMetadata | null;
}): ConstellationPlacementDecision {
  const placement = input.brain_pass?.placement;
  const facultyId = normalizeFacultyId(placement?.faculty_id?.trim());
  const secondaryFacultyId = normalizeFacultyId(placement?.secondary_faculty_id?.trim());

  return {
    facultyId,
    secondaryFacultyIds:
      secondaryFacultyId && secondaryFacultyId !== facultyId
        ? [secondaryFacultyId]
        : [],
    rationale: placement?.rationale?.trim() ?? "",
    confidence:
      typeof placement?.confidence === "number" && Number.isFinite(placement.confidence)
        ? placement.confidence
        : null,
    provider: input.brain_pass?.provider?.trim() || "fallback",
  };
}

export function buildFacultyAnchoredPlacement(
  facultyId: string | undefined,
  placementSeed: number,
): { x: number; y: number } {
  const resolvedFacultyId = normalizeFacultyId(facultyId);
  const faculty =
    CONSTELLATION_FACULTIES.find((candidate) => candidate.id === resolvedFacultyId)
    ?? CONSTELLATION_FACULTIES[1];
  const normalizedSeed = Math.abs(Math.trunc(placementSeed));
  const sweep = FACULTY_SWEEP_OFFSETS[normalizedSeed % FACULTY_SWEEP_OFFSETS.length];
  const shell = Math.floor(normalizedSeed / FACULTY_SWEEP_OFFSETS.length) + 1;
  const radius = CORE_EXCLUSION_RADIUS + 0.095 + shell * 0.055;
  const angle = faculty.angle + sweep;
  const targetX = CORE_CENTER_X + Math.cos(angle) * radius;
  const targetY = CORE_CENTER_Y + Math.sin(angle) * radius * FACULTY_VERTICAL_RATIO;
  const [x, y] = buildOutwardPlacement(targetX, targetY, normalizedSeed);

  return { x, y };
}

export function buildBrainPlacementIntent(provider: string): string {
  if (provider === "tribev2") {
    return "Filed by Tribev2 brain pass";
  }
  if (provider === "disabled") {
    return "Filed manually";
  }
  return "Filed by METIS brain pass";
}