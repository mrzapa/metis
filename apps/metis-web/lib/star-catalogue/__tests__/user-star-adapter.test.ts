import { describe, expect, it } from "vitest";

import { userStarToCatalogueUserStar } from "../user-star-adapter";
import { generateStellarProfile } from "@/lib/landing-stars";
import type { LearningRoute, UserStar } from "@/lib/constellation-types";

function makeUserStar(overrides: Partial<UserStar> = {}): UserStar {
  return {
    id: "star-1",
    x: 0.4,
    y: 0.6,
    size: 0.95,
    createdAt: 1700000000000,
    ...overrides,
  };
}

const VIEWPORT = { width: 1000, height: 800 };

describe("userStarToCatalogueUserStar", () => {
  it("projects normalised x/y into world-space wx/wy via the viewport", () => {
    // Per worldPointToConstellationPoint inverse: wx = (cx - 0.5) * width.
    const out = userStarToCatalogueUserStar(
      makeUserStar({ x: 0.5, y: 0.5 }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(out.wx).toBeCloseTo(0, 5);
    expect(out.wy).toBeCloseTo(0, 5);
  });

  it("projects off-centre points correctly", () => {
    const out = userStarToCatalogueUserStar(
      makeUserStar({ x: 0.75, y: 0.25 }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(out.wx).toBeCloseTo(250, 5);
    expect(out.wy).toBeCloseTo(-200, 5);
  });

  it("preserves the star id", () => {
    const out = userStarToCatalogueUserStar(
      makeUserStar({ id: "abc" }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(out.id).toBe("abc");
  });

  it("uses the user star label as the catalogue name (or null when missing)", () => {
    const labelled = userStarToCatalogueUserStar(
      makeUserStar({ label: "Linear Algebra" }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(labelled.name).toBe("Linear Algebra");
    expect(labelled.label).toBe("Linear Algebra");

    const unlabelled = userStarToCatalogueUserStar(
      makeUserStar({ label: undefined }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(unlabelled.name).toBeNull();
    expect(unlabelled.label).toBe("");
  });

  it("treats empty / whitespace-only labels as no-name (null)", () => {
    const empty = userStarToCatalogueUserStar(
      makeUserStar({ label: "" }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(empty.name).toBeNull();

    const spaces = userStarToCatalogueUserStar(
      makeUserStar({ label: "   " }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(spaces.name).toBeNull();

    const padded = userStarToCatalogueUserStar(
      makeUserStar({ label: "  Vega  " }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(padded.name).toBe("Vega");
  });

  it("preserves the stage when present, falls back to 'seed'", () => {
    const growing = userStarToCatalogueUserStar(
      makeUserStar({ stage: "growing" }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(growing.stage).toBe("growing");

    const noStage = userStarToCatalogueUserStar(
      makeUserStar({ stage: undefined }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(noStage.stage).toBe("seed");
  });

  it("preserves the LearningRoute object when present", () => {
    const route: LearningRoute = {
      id: "route-1",
      title: "Vectors",
      originStarId: "star-1",
      createdAt: "2026-04-24T00:00:00.000Z",
      updatedAt: "2026-04-24T00:00:00.000Z",
      steps: [],
    };
    const out = userStarToCatalogueUserStar(
      makeUserStar({ learningRoute: route }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(out.learningRoute).toEqual(route);
  });

  it("returns null learningRoute when the user star has none", () => {
    const out = userStarToCatalogueUserStar(
      makeUserStar({ learningRoute: undefined }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(out.learningRoute).toBeNull();
  });

  it("normalises optional fields to non-undefined defaults", () => {
    const out = userStarToCatalogueUserStar(
      makeUserStar(),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(out.primaryDomainId).toBeNull();
    expect(out.relatedDomainIds).toEqual([]);
    expect(out.connectedUserStarIds).toEqual([]);
    expect(out.notes).toBe("");
  });

  it("threads through user-supplied primary + related domains and connected star ids", () => {
    const out = userStarToCatalogueUserStar(
      makeUserStar({
        primaryDomainId: "perception",
        relatedDomainIds: ["knowledge"],
        connectedUserStarIds: ["other-1", "other-2"],
        notes: "wip",
      }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(out.primaryDomainId).toBe("perception");
    expect(out.relatedDomainIds).toEqual(["knowledge"]);
    expect(out.connectedUserStarIds).toEqual(["other-1", "other-2"]);
    expect(out.notes).toBe("wip");
  });

  it("derives a deterministic StellarProfile from the star id (unless overridden)", () => {
    const a = userStarToCatalogueUserStar(
      makeUserStar({ id: "star-x" }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    const b = userStarToCatalogueUserStar(
      makeUserStar({ id: "star-x" }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(a.profile.spectralClass).toBe(b.profile.spectralClass);
    expect(a.profile.seed).toBe(b.profile.seed);
  });

  it("respects an explicit profile override (e.g. catalogue-derived)", () => {
    const customProfile = generateStellarProfile("override-seed");
    const out = userStarToCatalogueUserStar(
      makeUserStar(),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile, profileOverride: customProfile },
    );
    expect(out.profile).toBe(customProfile);
  });

  it("computes apparentMagnitude in the [0, 6.5] range", () => {
    const out = userStarToCatalogueUserStar(
      makeUserStar(),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(out.apparentMagnitude).toBeGreaterThanOrEqual(0);
    expect(out.apparentMagnitude).toBeLessThanOrEqual(6.5);
  });

  it("emits a depthLayer in [0, 1]", () => {
    const out = userStarToCatalogueUserStar(
      makeUserStar(),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    expect(out.depthLayer).toBeGreaterThanOrEqual(0);
    expect(out.depthLayer).toBeLessThanOrEqual(1);
  });

  it("output arrays are isolated from the source UserStar (mutation safety)", () => {
    const source = makeUserStar({
      relatedDomainIds: ["knowledge"],
      connectedUserStarIds: ["other-1", "other-2"],
    });
    const out = userStarToCatalogueUserStar(source, {
      viewport: VIEWPORT,
      generateProfile: generateStellarProfile,
    });
    out.relatedDomainIds.push("memory");
    out.connectedUserStarIds.push("other-3");
    expect(source.relatedDomainIds).toEqual(["knowledge"]);
    expect(source.connectedUserStarIds).toEqual(["other-1", "other-2"]);
  });

  it("output learningRoute is isolated from the source UserStar (deep clone)", () => {
    const route: LearningRoute = {
      id: "route-1",
      title: "Vectors",
      originStarId: "star-1",
      createdAt: "2026-04-25T00:00:00.000Z",
      updatedAt: "2026-04-25T00:00:00.000Z",
      steps: [
        {
          id: "step-1",
          kind: "orient",
          title: "Intro",
          objective: "warm up",
          rationale: "establish context",
          manifestPath: "/x.json",
          tutorPrompt: "go",
          estimatedMinutes: 5,
          status: "todo",
        },
      ],
    };
    const source = makeUserStar({ learningRoute: route });
    const out = userStarToCatalogueUserStar(source, {
      viewport: VIEWPORT,
      generateProfile: generateStellarProfile,
    });
    expect(out.learningRoute).not.toBe(source.learningRoute);
    expect(out.learningRoute?.steps[0]).not.toBe(route.steps[0]);
    out.learningRoute!.title = "Mutated";
    out.learningRoute!.steps[0].status = "done";
    out.learningRoute!.steps.push({
      ...route.steps[0],
      id: "step-2",
    });
    expect(source.learningRoute?.title).toBe("Vectors");
    expect(source.learningRoute?.steps[0].status).toBe("todo");
    expect(source.learningRoute?.steps).toHaveLength(1);
  });

  it("output is structurally a CatalogueUserStar (every field present)", () => {
    const out = userStarToCatalogueUserStar(
      makeUserStar({ label: "Vega" }),
      { viewport: VIEWPORT, generateProfile: generateStellarProfile },
    );
    // Catalogue-derived
    expect(typeof out.id).toBe("string");
    expect(typeof out.wx).toBe("number");
    expect(typeof out.wy).toBe("number");
    expect(out.profile).toBeDefined();
    expect(typeof out.apparentMagnitude).toBe("number");
    expect(typeof out.depthLayer).toBe("number");
    // User-derived
    expect(typeof out.label).toBe("string");
    expect(out.primaryDomainId === null || typeof out.primaryDomainId === "string").toBe(true);
    expect(Array.isArray(out.relatedDomainIds)).toBe(true);
    expect(typeof out.stage).toBe("string");
    expect(typeof out.notes).toBe("string");
    expect(Array.isArray(out.connectedUserStarIds)).toBe(true);
  });
});
