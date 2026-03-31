import { describe, expect, it } from "vitest";
import { normalizeUserStar, parseUserStars } from "@/lib/constellation-types";

describe("constellation learning-route persistence", () => {
  it("normalizes and preserves a saved learning route on a user star", () => {
    const star = normalizeUserStar({
      id: "star-1",
      x: 0.3,
      y: 0.4,
      size: 1,
      createdAt: 1,
      label: "Route star",
      learningRoute: {
        id: "route-1",
        title: "Route Through the Stars: Graph Thinking",
        originStarId: "star-1",
        createdAt: "2026-03-31T10:00:00+00:00",
        updatedAt: "2026-03-31T10:00:00+00:00",
        steps: [
          {
            id: "step-1",
            kind: "orient",
            title: "Orient Around Graph Thinking",
            objective: "Get the lay of the land.",
            rationale: "Start broad before diving in.",
            manifestPath: "/indexes/atlas-a.json",
            tutorPrompt: "Tutor me through the overview.",
            estimatedMinutes: 12,
            status: "todo",
          },
        ],
      },
    });

    expect(star.learningRoute).toEqual(
      expect.objectContaining({
        id: "route-1",
        originStarId: "star-1",
        steps: [
          expect.objectContaining({
            id: "step-1",
            kind: "orient",
            manifestPath: "/indexes/atlas-a.json",
            status: "todo",
          }),
        ],
      }),
    );
  });

  it("round-trips saved learning routes from parsed settings payloads", () => {
    const parsed = parseUserStars([
      {
        id: "star-1",
        x: 0.25,
        y: 0.5,
        size: 1.1,
        createdAt: 10,
        label: "Parsed route star",
        linkedManifestPaths: ["/indexes/atlas-a.json"],
        activeManifestPath: "/indexes/atlas-a.json",
        learningRoute: {
          id: "route-1",
          title: "Route Through the Stars: Parsed route star",
          originStarId: "star-1",
          createdAt: "2026-03-31T10:00:00+00:00",
          updatedAt: "2026-03-31T10:00:00+00:00",
          steps: [
            {
              id: "step-1",
              kind: "orient",
              title: "Orient Around Parsed route star",
              objective: "Map the core ideas.",
              rationale: "Start with the framing.",
              manifestPath: "/indexes/atlas-a.json",
              tutorPrompt: "Tutor me through the framing.",
              estimatedMinutes: 14,
              status: "done",
              completedAt: "2026-03-31T10:30:00+00:00",
            },
          ],
        },
      },
    ]);

    expect(parsed).toEqual([
      expect.objectContaining({
        id: "star-1",
        learningRoute: expect.objectContaining({
          steps: [
            expect.objectContaining({
              status: "done",
              completedAt: "2026-03-31T10:30:00+00:00",
            }),
          ],
        }),
      }),
    ]);
  });
});
