/**
 * M12 Phase 4b — adapter that projects a legacy `UserStar` (the storage
 * shape) into a `CatalogueUserStar` (the unified read shape).
 *
 * Storage stays `UserStar` per ADR 0012; this adapter is what downstream
 * consumers (M14 Forge, M16 evals, future marketplace) call when they want
 * the unified shape. Pure / side-effect-free.
 */

import { constellationPointToWorldPoint } from "@/lib/constellation-home";
import { fnv1a32 } from "./rng";
import type { CatalogueUserStar } from "./types";
import type { StellarProfile } from "@/lib/landing-stars/types";
import type { UserStar } from "@/lib/constellation-types";

export interface UserStarAdapterOptions {
  /** Viewport used to project normalised constellation coords → world coords. */
  viewport: { width: number; height: number };
  /**
   * Stellar profile generator (typically the project's `generateStellarProfile`).
   * Injected rather than imported to avoid a heavy module dependency in pure
   * tests.
   */
  generateProfile: (seed: string | number) => StellarProfile;
  /**
   * Optional explicit profile (e.g. one already derived from a promoted
   * catalogue star). When set, `generateProfile` is bypassed.
   */
  profileOverride?: StellarProfile;
}

const APPARENT_MAGNITUDE_MIN = 0;
const APPARENT_MAGNITUDE_MAX = 6.5;

/** Hash → [0, 1] uniform float, deterministic. */
function hashToUnit(hash: number): number {
  return (hash >>> 0) / 0x1_0000_0000;
}

function deriveApparentMagnitude(seedHash: number): number {
  // Uniform spread across the visible band [0, 6.5]. Deterministic in the
  // star id so a given star always projects to the same magnitude across
  // renders and sessions.
  const u = hashToUnit(seedHash);
  return APPARENT_MAGNITUDE_MIN + u * (APPARENT_MAGNITUDE_MAX - APPARENT_MAGNITUDE_MIN);
}

function deriveDepthLayer(seedHash: number): number {
  return hashToUnit(seedHash ^ 0x9e3779b9);
}

/**
 * Treat empty / whitespace-only labels as "no name". The
 * `CatalogueStar.name` contract is `null` for nameless field stars; an
 * empty string would slip through as a "real" name and render a blank
 * title in `CatalogueStarInspector` (which uses `star.name ?? fallback`).
 */
function normaliseDisplayName(label: string | undefined): string | null {
  if (!label) return null;
  const trimmed = label.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function cloneLearningRoute(
  route: UserStar["learningRoute"],
): CatalogueUserStar["learningRoute"] {
  if (!route) return null;
  return {
    ...route,
    steps: route.steps.map((step) => ({ ...step })),
  };
}

export function userStarToCatalogueUserStar(
  user: UserStar,
  options: UserStarAdapterOptions,
): CatalogueUserStar {
  const { viewport, generateProfile, profileOverride } = options;
  const world = constellationPointToWorldPoint(
    { x: user.x, y: user.y },
    viewport.width,
    viewport.height,
  );

  const profile = profileOverride ?? generateProfile(user.id);
  const seedHash = fnv1a32(user.id);

  // Defensive copies: the adapter is documented as a pure read-view, so the
  // returned object must not share mutable references with the source
  // `UserStar`. A caller mutating `relatedDomainIds.push(...)` on the view
  // would otherwise silently corrupt the in-memory store.
  return {
    id: user.id,
    wx: world.x,
    wy: world.y,
    profile,
    name: normaliseDisplayName(user.label),
    apparentMagnitude: deriveApparentMagnitude(seedHash),
    depthLayer: deriveDepthLayer(seedHash),
    label: user.label ?? "",
    primaryDomainId: user.primaryDomainId ?? null,
    relatedDomainIds: user.relatedDomainIds ? [...user.relatedDomainIds] : [],
    stage: user.stage ?? "seed",
    notes: user.notes ?? "",
    connectedUserStarIds: user.connectedUserStarIds
      ? [...user.connectedUserStarIds]
      : [],
    learningRoute: cloneLearningRoute(user.learningRoute),
  };
}
