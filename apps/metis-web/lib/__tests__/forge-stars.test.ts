import { describe, expect, it } from "vitest";

import {
  FORGE_STAR_RING_PHASE,
  FORGE_STAR_RING_RADIUS,
  FORGE_STAR_SIZE,
  forgeStarPositions,
  pillarStarPalette,
} from "../forge-stars";
import { CONSTELLATION_FACULTIES, FACULTY_PALETTE } from "../constellation-home";
import type { ForgeTechnique } from "../api";

const SKILLS = CONSTELLATION_FACULTIES.find((f) => f.id === "skills");
if (!SKILLS) throw new Error("Skills faculty missing from CONSTELLATION_FACULTIES");

function makeTechnique(id: string, overrides: Partial<ForgeTechnique> = {}): ForgeTechnique {
  return {
    id,
    name: id,
    description: `${id} description`,
    pillar: "cortex",
    enabled: true,
    setting_keys: [],
    engine_symbols: [],
    recent_uses: [],
    ...overrides,
  };
}

describe("forgeStarPositions", () => {
  it("returns nothing when there are no enabled techniques", () => {
    expect(forgeStarPositions([])).toEqual([]);
  });

  it("places one star at the seeded angle around the Skills anchor", () => {
    const [star] = forgeStarPositions([makeTechnique("reranker")]);
    expect(star).toBeDefined();
    expect(star.id).toBe("reranker");
    expect(star.size).toBe(FORGE_STAR_SIZE);
    const expectedX = SKILLS.x + Math.cos(FORGE_STAR_RING_PHASE) * FORGE_STAR_RING_RADIUS;
    const expectedY = SKILLS.y + Math.sin(FORGE_STAR_RING_PHASE) * FORGE_STAR_RING_RADIUS;
    expect(star.x).toBeCloseTo(expectedX, 6);
    expect(star.y).toBeCloseTo(expectedY, 6);
  });

  it("fans multiple stars evenly around the anchor with stable per-id slots", () => {
    const techniques = [
      makeTechnique("a"),
      makeTechnique("b"),
      makeTechnique("c"),
      makeTechnique("d"),
    ];
    const stars = forgeStarPositions(techniques);
    expect(stars).toHaveLength(4);
    const angles = stars.map((star) => Math.atan2(star.y - SKILLS.y, star.x - SKILLS.x));
    const diffs = angles.slice(1).map((angle, i) => normaliseAngle(angle - angles[i]));
    diffs.forEach((diff) => expect(diff).toBeCloseTo(Math.PI / 2, 5));
  });

  it("propagates each technique's pillar onto its star palette", () => {
    const stars = forgeStarPositions([
      makeTechnique("c", { pillar: "cortex" }),
      makeTechnique("p", { pillar: "companion" }),
    ]);
    expect(stars[0].paletteRgb).toEqual(FACULTY_PALETTE.reasoning);
    expect(stars[1].paletteRgb).toEqual(FACULTY_PALETTE.skills);
  });
});

describe("pillarStarPalette", () => {
  it("returns the skills tone for companion techniques", () => {
    expect(pillarStarPalette("companion")).toEqual(FACULTY_PALETTE.skills);
  });

  it("returns the reasoning tone for cortex techniques", () => {
    expect(pillarStarPalette("cortex")).toEqual(FACULTY_PALETTE.reasoning);
  });

  it("returns a neutral palette for cross-cutting techniques", () => {
    expect(pillarStarPalette("cross-cutting")).toEqual([208, 216, 232]);
  });
});

function normaliseAngle(theta: number): number {
  let normalised = theta;
  while (normalised <= -Math.PI) normalised += Math.PI * 2;
  while (normalised > Math.PI) normalised -= Math.PI * 2;
  return Math.abs(normalised);
}
