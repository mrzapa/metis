import { describe, expect, it } from "vitest";
import type { UserStar } from "@/lib/constellation-types";
import {
  DEFAULT_RING_OPACITY,
  DEFAULT_SATELLITE_PERIOD_SECONDS,
  DEFAULT_SATELLITE_RADIUS,
  HALO_RECENCY_HALF_LIFE_SECONDS,
  HALO_STRENGTH_THRESHOLD,
  deriveStarAnnotations,
  getStarAnnotationAttributeValues,
  haloStrengthFromAge,
} from "../star-annotations";

const NOW_MS = 1_712_000_000_000; // deterministic "now" used throughout

function makeStar(overrides: Partial<UserStar> = {}): UserStar {
  return {
    id: overrides.id ?? "user-star-1",
    x: 0.5,
    y: 0.5,
    size: 1,
    createdAt: NOW_MS,
    ...overrides,
  };
}

describe("haloStrengthFromAge", () => {
  it("returns 1 at age 0", () => {
    expect(haloStrengthFromAge(NOW_MS, NOW_MS)).toBe(1);
  });

  it("returns ~0.5 at the half-life", () => {
    const halfLifeMs = HALO_RECENCY_HALF_LIFE_SECONDS * 1000;
    const strength = haloStrengthFromAge(NOW_MS, NOW_MS - halfLifeMs);
    expect(strength).toBeCloseTo(0.5, 5);
  });

  it("returns ~0.25 at two half-lives", () => {
    const halfLifeMs = HALO_RECENCY_HALF_LIFE_SECONDS * 1000;
    const strength = haloStrengthFromAge(NOW_MS, NOW_MS - halfLifeMs * 2);
    expect(strength).toBeCloseTo(0.25, 5);
  });

  it("clamps to [0, 1] for future timestamps (clock skew)", () => {
    expect(haloStrengthFromAge(NOW_MS, NOW_MS + 60_000)).toBe(1);
  });
});

describe("deriveStarAnnotations — individual signals", () => {
  it("returns undefined when the star has no signals whatsoever", () => {
    // createdAt is extremely old so halo decays below threshold; no
    // learning route, no linked paths, no connections.
    const ancient = makeStar({
      createdAt: NOW_MS - HALO_RECENCY_HALF_LIFE_SECONDS * 1000 * 30,
    });
    expect(deriveStarAnnotations(ancient, { nowMs: NOW_MS })).toBeUndefined();
  });

  it("produces only a halo when only recency is present", () => {
    const fresh = makeStar({ createdAt: NOW_MS });
    const result = deriveStarAnnotations(fresh, { nowMs: NOW_MS });
    expect(result).toBeDefined();
    expect(result?.halo?.strength).toBeCloseTo(1, 5);
    expect(result?.ring).toBeUndefined();
    expect(result?.satellites).toBeUndefined();
  });

  it("drops the halo annotation once strength falls below the visual threshold", () => {
    // Pick an age that decays well past HALO_STRENGTH_THRESHOLD but
    // still keeps the star old enough to test the edge.
    const veryOld = makeStar({
      createdAt: NOW_MS - HALO_RECENCY_HALF_LIFE_SECONDS * 1000 * 10,
    });
    const result = deriveStarAnnotations(veryOld, { nowMs: NOW_MS });
    // Halo should be omitted because strength is below the threshold.
    expect(result?.halo).toBeUndefined();
    // And since nothing else is present, the whole object collapses.
    expect(result).toBeUndefined();
    // Sanity — the threshold constant exists and is within range.
    expect(HALO_STRENGTH_THRESHOLD).toBeGreaterThan(0);
    expect(HALO_STRENGTH_THRESHOLD).toBeLessThan(1);
  });

  it("produces only a ring when the star links manifest paths", () => {
    // Age the star past the halo threshold so only the ring fires.
    const old = makeStar({
      createdAt: NOW_MS - HALO_RECENCY_HALF_LIFE_SECONDS * 1000 * 10,
      linkedManifestPaths: ["/indexes/a.json", "/indexes/b.json"],
    });
    const result = deriveStarAnnotations(old, { nowMs: NOW_MS });
    expect(result).toBeDefined();
    expect(result?.halo).toBeUndefined();
    expect(result?.ring).toEqual({ count: 2 });
    expect(result?.satellites).toBeUndefined();
  });

  it("clamps ring.count at 3 when the series is large", () => {
    const old = makeStar({
      createdAt: NOW_MS - HALO_RECENCY_HALF_LIFE_SECONDS * 1000 * 10,
      linkedManifestPaths: ["/a.json", "/b.json", "/c.json", "/d.json", "/e.json"],
    });
    const result = deriveStarAnnotations(old, { nowMs: NOW_MS });
    expect(result?.ring?.count).toBe(3);
  });

  it("produces only satellites when only sub-nodes are present", () => {
    const old = makeStar({
      createdAt: NOW_MS - HALO_RECENCY_HALF_LIFE_SECONDS * 1000 * 10,
      connectedUserStarIds: ["s1", "s2", "s3"],
    });
    const result = deriveStarAnnotations(old, { nowMs: NOW_MS });
    expect(result).toBeDefined();
    expect(result?.halo).toBeUndefined();
    expect(result?.ring).toBeUndefined();
    expect(result?.satellites?.count).toBe(3);
    expect(result?.satellites?.radius).toBe(DEFAULT_SATELLITE_RADIUS);
  });

  it("clamps satellite.count at 4 when the sub-node list is larger", () => {
    const old = makeStar({
      createdAt: NOW_MS - HALO_RECENCY_HALF_LIFE_SECONDS * 1000 * 10,
      connectedUserStarIds: ["s1", "s2", "s3", "s4", "s5", "s6"],
    });
    const result = deriveStarAnnotations(old, { nowMs: NOW_MS });
    expect(result?.satellites?.count).toBe(4);
  });

  it("stacks all three annotations when every signal is present, no cross-talk", () => {
    const rich = makeStar({
      createdAt: NOW_MS,
      linkedManifestPaths: ["/a.json"],
      connectedUserStarIds: ["s1", "s2"],
    });
    const result = deriveStarAnnotations(rich, { nowMs: NOW_MS });
    expect(result).toBeDefined();
    expect(result?.halo?.strength).toBeCloseTo(1, 5);
    expect(result?.ring?.count).toBe(1);
    expect(result?.satellites?.count).toBe(2);
  });
});

describe("deriveStarAnnotations — learning-route recency", () => {
  it("prefers learningRoute.updatedAt over createdAt for halo strength", () => {
    // Star was created a long time ago but its learning route was just
    // touched — halo should read as fresh.
    const star = makeStar({
      createdAt: NOW_MS - HALO_RECENCY_HALF_LIFE_SECONDS * 1000 * 20,
      learningRoute: {
        id: "r1",
        title: "Route",
        originStarId: "user-star-1",
        createdAt: new Date(NOW_MS - 60_000).toISOString(),
        updatedAt: new Date(NOW_MS).toISOString(),
        steps: [
          {
            id: "step-1",
            kind: "orient",
            title: "Orient",
            objective: "Lay of the land.",
            rationale: "Start broad.",
            manifestPath: "/indexes/a.json",
            tutorPrompt: "Tutor me.",
            estimatedMinutes: 12,
            status: "todo",
          },
        ],
      },
    });
    const result = deriveStarAnnotations(star, { nowMs: NOW_MS });
    expect(result?.halo?.strength).toBeCloseTo(1, 5);
  });
});

describe("getStarAnnotationAttributeValues", () => {
  it("returns an all-zero bundle when annotations is undefined or null", () => {
    const fromUndefined = getStarAnnotationAttributeValues(undefined);
    const fromNull = getStarAnnotationAttributeValues(null);
    for (const bundle of [fromUndefined, fromNull]) {
      expect(bundle.haloStrength).toBe(0);
      expect(bundle.ringCount).toBe(0);
      expect(bundle.ringOpacity).toBe(0);
      expect(bundle.satelliteCount).toBe(0);
      expect(bundle.satelliteRadius).toBe(0);
      expect(bundle.satellitePeriod).toBe(0);
    }
  });

  it("packs halo strength clamped to [0, 1]", () => {
    expect(getStarAnnotationAttributeValues({ halo: { strength: 2 } }).haloStrength).toBe(1);
    expect(getStarAnnotationAttributeValues({ halo: { strength: -0.5 } }).haloStrength).toBe(0);
    expect(getStarAnnotationAttributeValues({ halo: { strength: 0.4 } }).haloStrength).toBe(0.4);
  });

  it("packs ring count and default opacity", () => {
    const values = getStarAnnotationAttributeValues({ ring: { count: 2 } });
    expect(values.ringCount).toBe(2);
    expect(values.ringOpacity).toBe(DEFAULT_RING_OPACITY);
  });

  it("packs ring opacity override clamped to [0, 1]", () => {
    const values = getStarAnnotationAttributeValues({ ring: { count: 1, opacity: 0.3 } });
    expect(values.ringCount).toBe(1);
    expect(values.ringOpacity).toBe(0.3);

    const overBright = getStarAnnotationAttributeValues({ ring: { count: 3, opacity: 1.4 } });
    expect(overBright.ringOpacity).toBe(1);
  });

  it("packs satellite count, radius, and default period", () => {
    const values = getStarAnnotationAttributeValues({
      satellites: { count: 3, radius: DEFAULT_SATELLITE_RADIUS },
    });
    expect(values.satelliteCount).toBe(3);
    expect(values.satelliteRadius).toBe(DEFAULT_SATELLITE_RADIUS);
    expect(values.satellitePeriod).toBe(DEFAULT_SATELLITE_PERIOD_SECONDS);
  });

  it("packs satellite period override and floors it to a positive value", () => {
    const values = getStarAnnotationAttributeValues({
      satellites: { count: 2, radius: 2.0, period: 4 },
    });
    expect(values.satellitePeriod).toBe(4);

    const degenerate = getStarAnnotationAttributeValues({
      satellites: { count: 1, radius: 2.0, period: 0 },
    });
    expect(degenerate.satellitePeriod).toBeGreaterThan(0);
  });

  it("stacks all three annotations cleanly with no cross-field leakage", () => {
    const stacked = getStarAnnotationAttributeValues({
      halo: { strength: 0.6 },
      ring: { count: 2, opacity: 0.5 },
      satellites: { count: 3, radius: 2.2 },
    });
    expect(stacked.haloStrength).toBe(0.6);
    expect(stacked.ringCount).toBe(2);
    expect(stacked.ringOpacity).toBe(0.5);
    expect(stacked.satelliteCount).toBe(3);
    expect(stacked.satelliteRadius).toBe(2.2);
    expect(stacked.satellitePeriod).toBe(DEFAULT_SATELLITE_PERIOD_SECONDS);
  });
});
