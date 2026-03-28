import { describe, expect, it } from "vitest";
import {
  buildBrainPlacementIntent,
  buildFacultyAnchoredPlacement,
  getConstellationPlacementDecision,
} from "@/lib/constellation-brain";

describe("constellation brain placement", () => {
  it("defaults to knowledge when no brain-pass metadata is available", () => {
    const placement = getConstellationPlacementDecision({});

    expect(placement.facultyId).toBe("knowledge");
    expect(placement.secondaryFacultyIds).toEqual([]);
    expect(placement.provider).toBe("fallback");
  });

  it("preserves primary and secondary faculties from brain-pass metadata", () => {
    const placement = getConstellationPlacementDecision({
      brain_pass: {
        provider: "tribev2",
        placement: {
          faculty_id: "reasoning",
          confidence: 0.81,
          rationale: "Reasoning-dominant signal.",
          provenance: "tribev2-text",
          secondary_faculty_id: "knowledge",
        },
      },
    });

    expect(placement.facultyId).toBe("reasoning");
    expect(placement.secondaryFacultyIds).toEqual(["knowledge"]);
    expect(placement.rationale).toBe("Reasoning-dominant signal.");
    expect(placement.provider).toBe("tribev2");
  });

  it("anchors placements inside the constellation bounds", () => {
    const placement = buildFacultyAnchoredPlacement("reasoning", 7);

    expect(placement.x).toBeGreaterThan(0.04);
    expect(placement.x).toBeLessThanOrEqual(0.96);
    expect(placement.y).toBeGreaterThan(0.06);
    expect(placement.y).toBeLessThanOrEqual(0.95);
  });

  it("builds an intent label from the provider", () => {
    expect(buildBrainPlacementIntent("tribev2")).toBe("Filed by Tribev2 brain pass");
    expect(buildBrainPlacementIntent("fallback")).toBe("Filed by METIS brain pass");
  });
});