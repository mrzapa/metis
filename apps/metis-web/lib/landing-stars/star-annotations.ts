/**
 * Phase 6 annotations — lightweight 2D accoutrements that encode
 * user-star metadata onto the closeup-tier shader without introducing a
 * second WebGL context. See
 * `plans/constellation-2d-refactor/plan.md` (Phase 6) for the design.
 *
 * Shipped annotations:
 *  - **halo** (recency): age-decayed glow that dims as the star cools.
 *  - **ring** (document series): 1–3 concentric thin rings.
 *  - **satellites** (sub-nodes): up to 4 orbiting discs.
 *
 * Annotations are *content-driven*, not procedural. `StellarProfile`
 * defaults the field to `undefined`; callers attach it when they know
 * the star represents something annotatable (today: user stars only —
 * field / landmark paths leave it undefined).
 *
 * The helper here, `deriveStarAnnotations`, reads a `UserStar` and
 * returns the populated subset — absent annotations are omitted from
 * the object rather than rendered as zeros, so the "no signal" case
 * is a natural no-op at every layer (render plan → attribute pack →
 * shader).
 */

import type { UserStar } from "@/lib/constellation-types";

/**
 * Recency glow around the star — stronger for newer / recently touched
 * content. `strength` is a 0..1 scalar; the shader widens the halo and
 * warm-whites its tint proportionally.
 */
export interface StarAnnotationHalo {
  /** 0 = off, 1 = fresh. Values outside are clamped at render time. */
  strength: number;
  /** Optional hue shift in radians. Defaults to 0 at the renderer. */
  hueShift?: number;
}

/**
 * Document-series ring(s) — up to three concentric thin rings drawn at
 * fixed normalized radii around the disc. Count encodes series cardinality
 * (1 = single index, 2 = small series, 3+ = full corpus, clamped).
 */
export interface StarAnnotationRing {
  count: 1 | 2 | 3;
  /** Optional tilt in radians. Defaults to 0 (viewer-perpendicular). */
  tilt?: number;
  /** 0..1 opacity multiplier. Defaults to 0.75. */
  opacity?: number;
}

/**
 * Orbiting satellite blobs — sub-nodes for the star's graph. Each is a
 * tiny disc rendered at `radius` from the centre; positions are
 * evenly distributed around the clock and animate with `period`.
 * Hard-capped at 4 to keep the shader branch shallow.
 */
export interface StarAnnotationSatellites {
  count: 1 | 2 | 3 | 4;
  /** Orbit radius relative to the disc radius (1.8–3.2 suggested). */
  radius: number;
  /** Orbit period in seconds. Defaults to DEFAULT_SATELLITE_PERIOD_SECONDS. */
  period?: number;
}

export interface StarAnnotations {
  halo?: StarAnnotationHalo;
  ring?: StarAnnotationRing;
  satellites?: StarAnnotationSatellites;
}

/**
 * Half-life (seconds) of the recency halo. A star edited / created right
 * now has `halo.strength === 1`; one half-life later it has 0.5, and so
 * on. Chosen to match a roughly-week-long "this was recently touched"
 * intuition.
 */
export const HALO_RECENCY_HALF_LIFE_SECONDS = 7 * 24 * 60 * 60;

/**
 * Default satellite orbital period when not specified. Eight seconds is
 * slow enough to read as a bound system rather than a spinning motor.
 */
export const DEFAULT_SATELLITE_PERIOD_SECONDS = 8;

/** Default satellite orbit radius (relative to disc radius). */
export const DEFAULT_SATELLITE_RADIUS = 2.4;

/** Default ring opacity. */
export const DEFAULT_RING_OPACITY = 0.75;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/**
 * Compute the halo strength for a user-star timestamp.
 *
 * `nowMs` and `touchedAtMs` are epoch milliseconds. The returned
 * strength is `2^(-age / halfLife)` clamped to `[0, 1]`. A star touched
 * in the future (clock skew) is treated as fresh. A star older than a
 * few half-lives decays below the visual threshold — callers can drop
 * the annotation entirely at that point.
 */
export function haloStrengthFromAge(
  nowMs: number,
  touchedAtMs: number,
  halfLifeSeconds: number = HALO_RECENCY_HALF_LIFE_SECONDS,
): number {
  const ageSeconds = Math.max(0, (nowMs - touchedAtMs) / 1000);
  const halfLife = Math.max(1, halfLifeSeconds);
  const strength = Math.pow(2, -ageSeconds / halfLife);
  return clamp(strength, 0, 1);
}

function pickTouchedAtMs(star: UserStar): number | undefined {
  // Prefer the learning route's updatedAt when present — it represents
  // the most recent non-procedural interaction. Fall back to createdAt.
  const routeTs = star.learningRoute?.updatedAt;
  if (routeTs) {
    const parsed = Date.parse(routeTs);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  if (Number.isFinite(star.createdAt)) {
    return star.createdAt;
  }
  return undefined;
}

function countLinkedDocuments(star: UserStar): number {
  const series = star.linkedManifestPaths?.length ?? 0;
  if (series > 0) {
    return series;
  }
  return star.activeManifestPath ? 1 : 0;
}

function clampRingCount(count: number): 1 | 2 | 3 | null {
  if (count <= 0) return null;
  if (count === 1) return 1;
  if (count === 2) return 2;
  return 3;
}

function clampSatelliteCount(count: number): 1 | 2 | 3 | 4 | null {
  if (count <= 0) return null;
  if (count === 1) return 1;
  if (count === 2) return 2;
  if (count === 3) return 3;
  return 4;
}

/**
 * Threshold below which the halo is indistinguishable from noise. Stars
 * older than this return no halo at all — one fewer active shader path.
 */
export const HALO_STRENGTH_THRESHOLD = 0.04;

export interface DeriveStarAnnotationsOptions {
  /** Current time in epoch ms. Defaults to `Date.now()`. */
  nowMs?: number;
  /** Override the halo half-life. Defaults to the ~7-day constant. */
  halfLifeSeconds?: number;
}

/**
 * Derive the annotation bundle for a `UserStar`.
 *
 * Only the annotations whose signal is non-trivial are included in the
 * returned object. A star with no signals at all returns `undefined`,
 * matching the "no annotations" render-plan shortcut.
 */
export function deriveStarAnnotations(
  star: UserStar,
  options: DeriveStarAnnotationsOptions = {},
): StarAnnotations | undefined {
  const nowMs = options.nowMs ?? Date.now();
  const halfLifeSeconds = options.halfLifeSeconds ?? HALO_RECENCY_HALF_LIFE_SECONDS;
  const annotations: StarAnnotations = {};

  const touchedAtMs = pickTouchedAtMs(star);
  if (touchedAtMs !== undefined) {
    const strength = haloStrengthFromAge(nowMs, touchedAtMs, halfLifeSeconds);
    if (strength >= HALO_STRENGTH_THRESHOLD) {
      annotations.halo = { strength };
    }
  }

  const ringCount = clampRingCount(countLinkedDocuments(star));
  if (ringCount !== null) {
    annotations.ring = { count: ringCount };
  }

  const subNodeCount = star.connectedUserStarIds?.length ?? 0;
  const satelliteCount = clampSatelliteCount(subNodeCount);
  if (satelliteCount !== null) {
    annotations.satellites = {
      count: satelliteCount,
      radius: DEFAULT_SATELLITE_RADIUS,
    };
  }

  if (annotations.halo === undefined && annotations.ring === undefined && annotations.satellites === undefined) {
    return undefined;
  }
  return annotations;
}

/**
 * Attribute-pack a `StarAnnotations` bundle into the float encoding read
 * by the WebGL vertex shader. Kept pure so the attribute path is unit-
 * testable without spinning up WebGL.
 *
 * Returned floats correspond to shader attributes:
 *   - `aHaloStrength`  — 0..1 scalar.
 *   - `aRingCount`     — 0, 1, 2, or 3.
 *   - `aRingOpacity`   — 0..1 opacity (0 when no ring).
 *   - `aSatelliteCount`— 0..4.
 *   - `aSatelliteRadius` — 0 when no satellites; annotation radius
 *                          otherwise.
 *   - `aSatellitePeriod` — seconds; 0 when no satellites.
 */
export interface StarAnnotationAttributeValues {
  haloStrength: number;
  ringCount: number;
  ringOpacity: number;
  satelliteCount: number;
  satelliteRadius: number;
  satellitePeriod: number;
}

export function getStarAnnotationAttributeValues(
  annotations: StarAnnotations | null | undefined,
): StarAnnotationAttributeValues {
  if (!annotations) {
    return {
      haloStrength: 0,
      ringCount: 0,
      ringOpacity: 0,
      satelliteCount: 0,
      satelliteRadius: 0,
      satellitePeriod: 0,
    };
  }

  const halo = annotations.halo;
  const ring = annotations.ring;
  const satellites = annotations.satellites;

  return {
    haloStrength: halo ? clamp(halo.strength, 0, 1) : 0,
    ringCount: ring ? ring.count : 0,
    ringOpacity: ring ? clamp(ring.opacity ?? DEFAULT_RING_OPACITY, 0, 1) : 0,
    satelliteCount: satellites ? satellites.count : 0,
    satelliteRadius: satellites ? Math.max(0, satellites.radius) : 0,
    satellitePeriod: satellites
      ? Math.max(0.01, satellites.period ?? DEFAULT_SATELLITE_PERIOD_SECONDS)
      : 0,
  };
}
