import { describe, expect, it } from "vitest";
import {
  assignLandingStarRenderTier,
  buildLandingStarRenderPlan,
  classifyLandingStarRenderTier,
  DEFAULT_LANDING_STAR_LOD_THRESHOLDS,
} from "@/lib/landing-stars/landing-star-lod";
import type { LandingProjectedStar } from "@/lib/landing-stars/landing-star-types";

function makeStar(overrides: Partial<LandingProjectedStar> = {}): LandingProjectedStar {
  return {
    id: "star-a",
    x: 100,
    y: 120,
    apparentSize: 1.5,
    brightness: 0.28,
    ...overrides,
  };
}

describe("landing star LOD", () => {
  it("keeps stars as points below the sprite zoom threshold", () => {
    expect(classifyLandingStarRenderTier(makeStar(), 15.99)).toBe("point");
  });

  it("promotes readable stars to sprites at the sprite threshold", () => {
    const tier = classifyLandingStarRenderTier(
      makeStar({ apparentSize: 2.6, brightness: 0.4 }),
      DEFAULT_LANDING_STAR_LOD_THRESHOLDS.spriteZoomFactor,
    );

    expect(tier).toBe("sprite");
  });

  it("promotes strong close-up stars to heroes above the hero threshold", () => {
    const tier = classifyLandingStarRenderTier(
      makeStar({ apparentSize: 8.5, brightness: 0.9 }),
      DEFAULT_LANDING_STAR_LOD_THRESHOLDS.heroZoomFactor,
    );

    expect(tier).toBe("hero");
  });

  it("assigns a render tier without mutating the input star", () => {
    const star = makeStar({ apparentSize: 2.8, brightness: 0.42 });
    const assigned = assignLandingStarRenderTier(star, 64);

    expect(assigned.renderTier).toBe("sprite");
    expect(star).not.toHaveProperty("renderTier");
  });

  it("caps hero stars and demotes overflow into the sprite batch", () => {
    const plan = buildLandingStarRenderPlan(
      [
        makeStar({ id: "hero-1", apparentSize: 9.2, brightness: 0.96 }),
        makeStar({ id: "hero-2", apparentSize: 8.7, brightness: 0.91 }),
        makeStar({ id: "hero-3", apparentSize: 8.4, brightness: 0.89 }),
        makeStar({ id: "point-1", apparentSize: 0.8, brightness: 0.12 }),
      ],
      96,
      { maxHeroCount: 2 },
    );

    expect(plan.batches.hero).toHaveLength(2);
    expect(plan.batches.sprite).toHaveLength(1);
    expect(plan.batches.sprite[0].id).toBe("hero-3");
    expect(plan.tierCounts).toEqual({ closeup: 0, hero: 2, point: 1, sprite: 1 });
  });
});
