import { describe, expect, it } from "vitest";

import { buildCanvasFont, wrapText } from "../pretext-labels";

const font = buildCanvasFont(13, '"Space Grotesk", sans-serif', 600);

describe("wrapText", () => {
  it("returns an empty array for an empty string", () => {
    expect(wrapText("", font, 100)).toEqual([]);
  });

  it("returns one line for short input that fits within maxWidth", () => {
    const lines = wrapText("Short", font, 1000);
    expect(lines).toHaveLength(1);
    expect(lines[0].text).toBe("Short");
    expect(lines[0].width).toBeGreaterThan(0);
  });

  it("wraps long input across multiple lines, each fitting maxWidth", () => {
    const lines = wrapText(
      "AnthropicAI: Sonnet 4.7 release with extended context window",
      font,
      120,
    );
    expect(lines.length).toBeGreaterThan(1);
    for (const l of lines) {
      // Allow a 1px slop for floating-point rounding inside pretext.
      expect(l.width).toBeLessThanOrEqual(120 + 1);
      expect(l.width).toBeGreaterThan(0);
      expect(l.text.length).toBeGreaterThan(0);
    }
  });

  it("returns referentially-equal results from the cache on identical calls", () => {
    const a = wrapText("Cached headline text here", font, 200);
    const b = wrapText("Cached headline text here", font, 200);
    expect(b).toBe(a);
  });

  it("treats different maxWidth values as cache misses", () => {
    const a = wrapText("Cached headline text here", font, 200);
    const b = wrapText("Cached headline text here", font, 100);
    expect(b).not.toBe(a);
  });

  it("treats different fonts as cache misses", () => {
    const f2 = buildCanvasFont(11, '"Space Grotesk", sans-serif', 400);
    const a = wrapText("Cached headline text here", font, 200);
    const b = wrapText("Cached headline text here", f2, 200);
    expect(b).not.toBe(a);
  });

  it("freezes both the outer array and each line entry so mutation can't corrupt the cache", () => {
    const lines = wrapText("Frozen payload check", font, 200);
    expect(Object.isFrozen(lines)).toBe(true);
    if (lines.length > 0) {
      expect(Object.isFrozen(lines[0])).toBe(true);
    }
  });
});
