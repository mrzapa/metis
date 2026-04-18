import { describe, expect, it } from "vitest";
import type { UserStar } from "@/lib/constellation-types";
import { deriveUserStarContentType } from "@/lib/user-star-content-type";

function makeStar(overrides: Partial<UserStar> = {}): UserStar {
  return {
    id: overrides.id ?? "user-star-1",
    x: 0.5,
    y: 0.5,
    size: 1,
    createdAt: 1,
    ...overrides,
  };
}

describe("deriveUserStarContentType", () => {
  it("returns learning_route when the star carries a learning route", () => {
    const star = makeStar({
      learningRoute: {
        id: "route-1",
        title: "Graph Thinking",
        originStarId: "user-star-1",
        createdAt: "2026-03-31T10:00:00+00:00",
        updatedAt: "2026-03-31T10:00:00+00:00",
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

    expect(deriveUserStarContentType(star)).toBe("learning_route");
  });

  it("returns document when the star has at least one linked manifest path", () => {
    expect(
      deriveUserStarContentType(
        makeStar({ activeManifestPath: "/indexes/a.json" }),
      ),
    ).toBe("document");

    expect(
      deriveUserStarContentType(
        makeStar({ linkedManifestPaths: ["/indexes/a.json"] }),
      ),
    ).toBe("document");
  });

  it("prefers learning_route when both a route and manifest paths are present", () => {
    const star = makeStar({
      activeManifestPath: "/indexes/a.json",
      linkedManifestPaths: ["/indexes/a.json"],
      learningRoute: {
        id: "route-1",
        title: "Route",
        originStarId: "user-star-1",
        createdAt: "2026-03-31T10:00:00+00:00",
        updatedAt: "2026-03-31T10:00:00+00:00",
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

    expect(deriveUserStarContentType(star)).toBe("learning_route");
  });

  it("returns null for a plain seed star with no content signal", () => {
    expect(deriveUserStarContentType(makeStar())).toBeNull();
    expect(deriveUserStarContentType(makeStar({ notes: "just a thought" }))).toBeNull();
    expect(deriveUserStarContentType(makeStar({ linkedManifestPaths: [] }))).toBeNull();
  });
});
