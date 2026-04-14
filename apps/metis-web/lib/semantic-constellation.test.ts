import { describe, expect, it } from "vitest";

import {
  buildSemanticSearchState,
  buildSemanticShiftOffsets,
  getSemanticCorpusForStar,
  tokenizeSemanticText,
} from "@/lib/semantic-constellation";
import type { UserStar } from "@/lib/constellation-types";

function makeStar(overrides: Partial<UserStar>): UserStar {
  return {
    createdAt: Date.now(),
    id: overrides.id ?? "star",
    size: 2,
    x: 0.5,
    y: 0.5,
    ...overrides,
  };
}

describe("semantic constellation utilities", () => {
  it("tokenizes text and drops stop words", () => {
    expect(tokenizeSemanticText("The meeting with the company and person"))
      .toEqual(["meeting", "company", "person"]);
  });

  it("builds a semantic corpus from user star metadata", () => {
    const corpus = getSemanticCorpusForStar(makeStar({
      activeManifestPath: "manifests/acme.md",
      id: "s1",
      intent: "prep board meeting",
      label: "Acme update",
      linkedManifestPaths: ["manifests/acme.md"],
      notes: "company finance planning",
      primaryDomainId: "business",
      relatedDomainIds: ["operations"],
    }));
    expect(corpus).toContain("Acme update");
    expect(corpus).toContain("company finance planning");
    expect(corpus).toContain("operations");
  });

  it("ranks semantic matches and produces links", () => {
    const stars: UserStar[] = [
      makeStar({ id: "company", label: "company", notes: "board finance earnings" }),
      makeStar({ id: "meeting", label: "meeting", notes: "board sync agenda" }),
      makeStar({ id: "person", label: "person", notes: "founder profile" }),
    ];
    const state = buildSemanticSearchState("board meeting", stars);
    expect(state.active).toBe(true);
    expect(state.rankedIds.length).toBeGreaterThan(0);
    expect(state.links.length).toBeGreaterThan(0);
  });

  it("returns offsets for matched and unmatched stars while active", () => {
    const stars: UserStar[] = [
      makeStar({ id: "a", x: 0.2, y: 0.2 }),
      makeStar({ id: "b", x: 0.8, y: 0.2 }),
      makeStar({ id: "c", x: 0.5, y: 0.8 }),
    ];
    const offsets = buildSemanticShiftOffsets(stars, {
      active: true,
      links: [],
      matchedIds: new Set(["a", "b"]),
      rankedIds: ["a", "b"],
    });
    expect(offsets.size).toBe(3);
    expect(offsets.get("a")).toBeDefined();
    expect(offsets.get("c")).toBeDefined();
  });
});
