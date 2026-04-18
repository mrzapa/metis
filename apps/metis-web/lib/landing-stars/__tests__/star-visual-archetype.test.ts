import { describe, expect, it } from "vitest";
import {
  CONTENT_TYPE_ARCHETYPE_MAP,
  DEFAULT_VISUAL_ARCHETYPE,
  selectStarVisualArchetype,
  type StarContentType,
  type StarVisualArchetype,
} from "../star-visual-archetype";

describe("selectStarVisualArchetype", () => {
  it("returns main_sequence when content type is null or undefined", () => {
    expect(selectStarVisualArchetype(null)).toBe(DEFAULT_VISUAL_ARCHETYPE);
    expect(selectStarVisualArchetype(undefined)).toBe(DEFAULT_VISUAL_ARCHETYPE);
    expect(DEFAULT_VISUAL_ARCHETYPE).toBe("main_sequence");
  });

  it("maps each canonical content type to the ADR 0006 archetype", () => {
    const cases: Array<[StarContentType, StarVisualArchetype]> = [
      ["document", "main_sequence"],
      ["podcast", "pulsar"],
      ["video", "quasar"],
      ["note", "brown_dwarf"],
      ["summary", "red_giant"],
      ["evidence_pack", "binary"],
      ["topic_cluster", "nebula"],
      ["archive", "black_hole"],
      ["live_feed", "comet"],
      ["learning_route", "constellation"],
      ["session", "variable"],
      ["skill", "wolf_rayet"],
    ];

    for (const [contentType, expected] of cases) {
      expect(selectStarVisualArchetype(contentType)).toBe(expected);
    }
  });

  it("exposes every content type in the content-type map", () => {
    const contentTypes: StarContentType[] = [
      "document",
      "podcast",
      "video",
      "note",
      "summary",
      "evidence_pack",
      "topic_cluster",
      "archive",
      "live_feed",
      "learning_route",
      "session",
      "skill",
    ];

    for (const contentType of contentTypes) {
      expect(CONTENT_TYPE_ARCHETYPE_MAP[contentType]).toBeDefined();
    }
  });
});
