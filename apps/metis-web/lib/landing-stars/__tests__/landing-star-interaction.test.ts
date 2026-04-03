import { describe, expect, it } from "vitest";
import {
  getLandingStarInteractionHitRadius,
  getLandingStarSelectableApparentSize,
} from "@/lib/landing-stars/landing-star-interaction";

describe("landing star interaction helpers", () => {
  it("keeps point-tier stars on their original apparent-size threshold", () => {
    const star = {
      apparentSize: 0.31,
      brightness: 0.22,
      id: "point-star",
      x: 320,
      y: 240,
    };

    expect(getLandingStarSelectableApparentSize(star, 12)).toBeCloseTo(0.31, 6);
    expect(getLandingStarInteractionHitRadius(star, 12)).toBe(8);
  });

  it("promotes visibly rendered sprite stars into the selectable candidate pool", () => {
    const star = {
      apparentSize: 0.33,
      brightness: 0.52,
      id: "sprite-star",
      x: 640,
      y: 360,
    };

    expect(getLandingStarSelectableApparentSize(star, 55)).toBe(0.44);
    expect(getLandingStarInteractionHitRadius(star, 55)).toBe(12);
  });
});
