import { describe, expect, it } from "vitest";

import {
  buildHeadFirstPath,
  clampTangentForReducedMotion,
  clampToSafeArea,
  computeArcLengths,
  drawCometHoverCard,
  drawCometLabel,
  findHoveredComet,
  formatCompactAge,
  placeCharactersAlongPath,
  rectsOverlap,
  samplePathAt,
  shouldFlipOrientation,
  smoothedTangentAt,
  truncateLabelToFit,
} from "../constellation-comet-labels";
import { measureSingleLineTextWidth } from "../pretext-labels";
import type { CometData } from "../comet-types";

function mkComet(overrides: Partial<CometData> = {}): CometData {
  return {
    comet_id: "test-comet",
    x: 100,
    y: 100,
    vx: 1,
    vy: 0,
    tailHistory: [
      { x: 60, y: 100 },
      { x: 70, y: 100 },
      { x: 80, y: 100 },
      { x: 90, y: 100 },
      { x: 100, y: 100 },
    ],
    color: [120, 200, 255],
    facultyId: "perception",
    targetX: 0,
    targetY: 0,
    phase: "drifting",
    phaseStartedAt: 0,
    size: 4,
    opacity: 1,
    title: "Hello world",
    summary: "",
    url: "",
    sourceChannel: "",
    publishedAt: 0,
    decision: "drift",
    relevanceScore: 0.5,
    ...overrides,
  };
}

describe("computeArcLengths", () => {
  it("returns cumulative arc length from index 0 outward along the polyline", () => {
    // Three points: (0,0) → (3,0) is 3px, (3,0) → (3,4) is 4px.
    const tail = [
      { x: 0, y: 0 },
      { x: 3, y: 0 },
      { x: 3, y: 4 },
    ];
    expect(computeArcLengths(tail)).toEqual([0, 3, 7]);
  });

  it("returns [0] for a single-point tail", () => {
    expect(computeArcLengths([{ x: 1, y: 2 }])).toEqual([0]);
  });

  it("returns [] for an empty tail", () => {
    expect(computeArcLengths([])).toEqual([]);
  });
});

describe("samplePathAt", () => {
  const tail = [
    { x: 0, y: 0 },
    { x: 10, y: 0 },
    { x: 10, y: 10 },
  ];
  const arc = computeArcLengths(tail); // [0, 10, 20]

  it("returns the first point at s=0 with tangent along the first segment", () => {
    expect(samplePathAt(arc, tail, 0)).toEqual({ x: 0, y: 0, tangent: 0 });
  });

  it("interpolates linearly within a segment", () => {
    // s=5 is halfway along segment 0; tangent points along +x.
    expect(samplePathAt(arc, tail, 5)).toEqual({ x: 5, y: 0, tangent: 0 });
  });

  it("picks the segment containing s and uses that segment's tangent", () => {
    // s=15 is halfway along segment 1, going +y → π/2.
    const r = samplePathAt(arc, tail, 15);
    expect(r.x).toBeCloseTo(10);
    expect(r.y).toBeCloseTo(5);
    expect(r.tangent).toBeCloseTo(Math.PI / 2);
  });

  it("clamps to the polyline's end if s exceeds total arc length", () => {
    const r = samplePathAt(arc, tail, 999);
    expect(r.x).toBe(10);
    expect(r.y).toBe(10);
    expect(r.tangent).toBeCloseTo(Math.PI / 2);
  });

  it("returns origin {0,0,0} for an empty tail", () => {
    expect(samplePathAt([], [], 0)).toEqual({ x: 0, y: 0, tangent: 0 });
  });
});

describe("placeCharactersAlongPath", () => {
  // Long horizontal tail — plenty of arc length for any short label.
  const horizontalTail = [
    { x: 0, y: 0 },
    { x: 200, y: 0 },
  ];
  const font = '400 11px "Space Grotesk", sans-serif';

  it("places one entry per character that fits", () => {
    const placed = placeCharactersAlongPath("ABC", font, horizontalTail);
    expect(placed).toHaveLength(3);
  });

  it("first character lands close to the head (tail point at index 0)", () => {
    const placed = placeCharactersAlongPath("ABC", font, horizontalTail);
    expect(placed[0].x).toBeLessThan(15);
    expect(placed[0].y).toBe(0);
    expect(placed[0].tangent).toBeCloseTo(0, 2);
  });

  it("characters advance along +x along a straight horizontal tail", () => {
    const placed = placeCharactersAlongPath("ABC", font, horizontalTail);
    expect(placed[1].x).toBeGreaterThan(placed[0].x);
    expect(placed[2].x).toBeGreaterThan(placed[1].x);
    for (const p of placed) {
      expect(p.y).toBe(0);
    }
  });

  it("returns at most as many chars as fit in the available arc length", () => {
    const tinyTail = [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
    ];
    const placed = placeCharactersAlongPath("Hello", font, tinyTail);
    expect(placed.length).toBeLessThanOrEqual(1);
  });

  it("returns [] for empty label or sub-2 tail", () => {
    expect(placeCharactersAlongPath("", font, horizontalTail)).toEqual([]);
    expect(placeCharactersAlongPath("ABC", font, [{ x: 0, y: 0 }])).toEqual([]);
    expect(placeCharactersAlongPath("ABC", font, [])).toEqual([]);
  });

  it("treats a ZWJ-emoji sequence as a single grapheme cluster", () => {
    // 👨‍👩‍👧 = man (U+1F468) + ZWJ + woman (U+1F469) + ZWJ + girl (U+1F467)
    // = 5 code points, 8 UTF-16 code units, but ONE user-visible character.
    // Iterating by code point would yield 5 PlacedChar entries; correct
    // behaviour is one entry per grapheme cluster.
    const placed = placeCharactersAlongPath("👨‍👩‍👧A", font, horizontalTail);
    expect(placed).toHaveLength(2);
    expect(placed[0].char).toBe("👨‍👩‍👧");
    expect(placed[1].char).toBe("A");
  });

  it("treats a base-letter + combining-mark as a single grapheme cluster", () => {
    // "e" + U+0301 (combining acute accent) = "é" — 2 code points, 1 grapheme.
    const placed = placeCharactersAlongPath("éz", font, horizontalTail);
    expect(placed).toHaveLength(2);
    expect(placed[0].char).toBe("é");
    expect(placed[1].char).toBe("z");
  });
});

describe("smoothedTangentAt", () => {
  it("matches the raw tangent on a straight horizontal line", () => {
    const tail = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 20, y: 0 },
      { x: 30, y: 0 },
    ];
    const arc = computeArcLengths(tail);
    expect(smoothedTangentAt(arc, tail, 15)).toBeCloseTo(0, 3);
  });

  it("smooths a sharp right-angle corner — tangent at the elbow lies between the two segment angles", () => {
    // 90° turn: x then y. Raw tangent jumps from 0 to π/2 at the elbow.
    // Smoothed should land somewhere in (0, π/2).
    const tail = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 10, y: 20 },
    ];
    const arc = computeArcLengths(tail);
    const smoothed = smoothedTangentAt(arc, tail, 10); // exactly at the elbow
    expect(smoothed).toBeGreaterThan(0);
    expect(smoothed).toBeLessThan(Math.PI / 2);
  });

  it("falls back to samplePathAt's tangent for sub-2-point tails", () => {
    expect(smoothedTangentAt([], [], 0)).toBeCloseTo(0);
    expect(smoothedTangentAt([0], [{ x: 5, y: 5 }], 0)).toBeCloseTo(0);
  });

  it("equals the raw segment tangent at endpoints (no neighbour to smooth with)", () => {
    const tail = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
    ];
    const arc = computeArcLengths(tail);
    // s=0 and s=total — no later/earlier neighbour to average against.
    expect(smoothedTangentAt(arc, tail, 0)).toBeCloseTo(0);
    expect(smoothedTangentAt(arc, tail, 20)).toBeCloseTo(Math.PI / 2);
  });
});

describe("clampTangentForReducedMotion", () => {
  const TEN_DEG_RAD = (10 * Math.PI) / 180;

  it("does not clamp when reducedMotion is false", () => {
    expect(clampTangentForReducedMotion(Math.PI / 3, false)).toBeCloseTo(Math.PI / 3);
    expect(clampTangentForReducedMotion(-Math.PI, false)).toBeCloseTo(-Math.PI);
  });

  it("clamps positive tangents to +10° under reducedMotion", () => {
    expect(clampTangentForReducedMotion(Math.PI / 2, true)).toBeCloseTo(TEN_DEG_RAD);
  });

  it("clamps negative tangents to -10° under reducedMotion", () => {
    expect(clampTangentForReducedMotion(-Math.PI / 2, true)).toBeCloseTo(-TEN_DEG_RAD);
  });

  it("preserves small tangents under reducedMotion (within the band)", () => {
    expect(clampTangentForReducedMotion(0.1, true)).toBeCloseTo(0.1);
    expect(clampTangentForReducedMotion(-0.05, true)).toBeCloseTo(-0.05);
  });

  it("preserves zero", () => {
    expect(clampTangentForReducedMotion(0, true)).toBe(0);
    expect(clampTangentForReducedMotion(0, false)).toBe(0);
  });
});

describe("placeCharactersAlongPath with reducedMotion opt", () => {
  const elbow = [
    { x: 0, y: 0 },
    { x: 10, y: 0 },
    { x: 10, y: 100 }, // sharp elbow into a long vertical
    { x: 10, y: 200 },
  ];
  const font = '400 11px "Space Grotesk", sans-serif';

  it("clamps every character's tangent to ±10° when reducedMotion is true", () => {
    const TEN_DEG_RAD = (10 * Math.PI) / 180;
    const placed = placeCharactersAlongPath("AAAAAAAAAA", font, elbow, { reducedMotion: true });
    for (const p of placed) {
      expect(Math.abs(p.tangent)).toBeLessThanOrEqual(TEN_DEG_RAD + 1e-9);
    }
  });

  it("does not clamp when reducedMotion is unset", () => {
    const placed = placeCharactersAlongPath("AAAAAAAAAA", font, elbow);
    // At least one character downstream of the elbow has a steep tangent.
    const TEN_DEG_RAD = (10 * Math.PI) / 180;
    expect(placed.some((p) => Math.abs(p.tangent) > TEN_DEG_RAD)).toBe(true);
  });

  it("under flipped: true AND reducedMotion: true, the FINAL (post-flip) tangent stays in the readable band", () => {
    // Tail pointing in -x direction → smoothedTangent ≈ ±π, which triggers
    // the flip. Pre-fix bug: the ±10° clamp was applied to the raw tangent
    // BEFORE the flip offset, so a tangent of ~π collapsed to ±10° and then
    // gained +π = ~190°, rendering glyphs upside-down for exactly the
    // down-left/down-right cases that need flipping. Regression test: under
    // reducedMotion AND flipped, every character must still read upright
    // (final |tangent| ≤ 10°).
    const backwardTail = [
      { x: 0, y: 0 },
      { x: -200, y: 0 },
    ];
    const placed = placeCharactersAlongPath("AB", font, backwardTail, {
      flipped: true,
      reducedMotion: true,
    });
    const TEN_DEG_RAD = (10 * Math.PI) / 180;
    for (const p of placed) {
      expect(Math.abs(p.tangent)).toBeLessThanOrEqual(TEN_DEG_RAD + 1e-9);
    }
  });
});

describe("truncateLabelToFit", () => {
  const font = '400 11px "Space Grotesk", sans-serif';

  it("returns the full string when it fits and is under the hard cap", () => {
    expect(truncateLabelToFit("Hi", font, 10000)).toBe("Hi");
  });

  it("hard-caps at 18 graphemes + ellipsis when the text is long", () => {
    const long = "This is a much longer headline than 18 chars";
    const out = truncateLabelToFit(long, font, 10000);
    expect(out.endsWith("…")).toBe(true);
    // 18 graphemes + 1 ellipsis = 19 (codepoint length, not UTF-16 length)
    const cps = Array.from(out);
    expect(cps.length).toBeLessThanOrEqual(19);
    expect(out.startsWith(long.slice(0, 5))).toBe(true);
  });

  it("further truncates when the available arc length is short", () => {
    const out = truncateLabelToFit("Hello world", font, 20);
    expect(out.length).toBeLessThan("Hello world".length);
    expect(out.length).toBeGreaterThan(0);
    expect(out.startsWith("H")).toBe(true);
    // The result's full pixel width must fit within the budget.
    expect(measureSingleLineTextWidth(out, font)).toBeLessThanOrEqual(20 + 0.5);
  });

  it("returns empty string when no character + ellipsis fits", () => {
    expect(truncateLabelToFit("Hello", font, 1)).toBe("");
  });

  it("returns empty for empty input or zero budget", () => {
    expect(truncateLabelToFit("", font, 100)).toBe("");
    expect(truncateLabelToFit("Hello", font, 0)).toBe("");
  });
});

describe("shouldFlipOrientation", () => {
  // Hysteresis: enter flipped state at |tangent| > 95°, exit at |tangent| ≤ 90°.
  it("does not flip below the enter threshold from unflipped", () => {
    expect(shouldFlipOrientation(Math.PI / 2 - 0.1, false)).toBe(false);
  });

  it("flips when |tangent| crosses 95° from unflipped", () => {
    expect(shouldFlipOrientation((95 * Math.PI) / 180 + 0.01, false)).toBe(true);
  });

  it("once flipped, stays flipped while |tangent| > 90°", () => {
    expect(shouldFlipOrientation((92 * Math.PI) / 180, true)).toBe(true);
  });

  it("once flipped, unflips when |tangent| ≤ 90°", () => {
    expect(shouldFlipOrientation((89 * Math.PI) / 180, true)).toBe(false);
  });

  it("treats negative tangents symmetrically (uses magnitude)", () => {
    // -100° is just as upside-down as +100°.
    expect(shouldFlipOrientation((-100 * Math.PI) / 180, false)).toBe(true);
    expect(shouldFlipOrientation((-89 * Math.PI) / 180, true)).toBe(false);
  });

  it("π (perfect 180°) flips from either state", () => {
    expect(shouldFlipOrientation(Math.PI, false)).toBe(true);
    expect(shouldFlipOrientation(-Math.PI, true)).toBe(true);
  });
});

describe("placeCharactersAlongPath with flipped opt", () => {
  const horizontalTail = [
    { x: 0, y: 0 },
    { x: 200, y: 0 },
  ];
  const font = '400 11px "Space Grotesk", sans-serif';

  it("when flipped: true, all character tangents are rotated by π", () => {
    const placed = placeCharactersAlongPath("AB", font, horizontalTail, { flipped: true });
    expect(placed).toHaveLength(2);
    // Underlying smoothed tangent on a horizontal tail is 0; flipped → π.
    expect(placed[0].tangent).toBeCloseTo(Math.PI, 5);
    expect(placed[1].tangent).toBeCloseTo(Math.PI, 5);
  });

  it("when flipped: false (default), tangents match the smoothed baseline", () => {
    const placed = placeCharactersAlongPath("AB", font, horizontalTail);
    expect(placed[0].tangent).toBeCloseTo(0, 5);
    expect(placed[1].tangent).toBeCloseTo(0, 5);
  });
});

describe("drawCometHoverCard", () => {
  const vp = { w: 1000, h: 800 };

  it("returns a 220px-wide bbox", () => {
    const c = mkComet({ x: 100, y: 100 });
    const bbox = drawCometHoverCard(null, c, { x: 100, y: 100 }, { viewport: vp });
    expect(bbox.w).toBe(220);
  });

  it("positions the card 16px to the right of the anchor by default", () => {
    const c = mkComet({ x: 100, y: 100 });
    const bbox = drawCometHoverCard(null, c, { x: 100, y: 100 }, { viewport: vp });
    expect(bbox.x).toBe(100 + 16);
  });

  it("clamps the card inside the viewport when the anchor is near the right edge", () => {
    const c = mkComet({ x: 990, y: 100 });
    const bbox = drawCometHoverCard(null, c, { x: 990, y: 100 }, { viewport: vp });
    expect(bbox.x + bbox.w).toBeLessThanOrEqual(vp.w - 16);
  });

  it("avoids fixed UI rects passed in opts (e.g. zoom pill at bottom)", () => {
    const c = mkComet({ x: 300, y: 690 });
    const fixedRects = [{ x: 290, y: 700, w: 420, h: 60 }];
    const bbox = drawCometHoverCard(null, c, { x: 300, y: 690 }, { viewport: vp, fixedRects });
    expect(rectsOverlap(bbox, fixedRects[0])).toBe(false);
  });

  it("returns dynamic height that scales with summary length", () => {
    const shortSummary = mkComet({ x: 100, y: 100, title: "Short", summary: "Brief." });
    const longSummary = mkComet({
      x: 100,
      y: 100,
      title: "Short",
      summary:
        "A much longer summary that will wrap to multiple lines once it exceeds the 196px content width budget that the card layout uses for the body text region.",
    });
    const a = drawCometHoverCard(null, shortSummary, { x: 100, y: 100 }, { viewport: vp });
    const b = drawCometHoverCard(null, longSummary, { x: 100, y: 100 }, { viewport: vp });
    expect(b.h).toBeGreaterThan(a.h);
  });

  it("does not throw when called with a real ctx (smoke under jsdom)", () => {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return; // jsdom env without canvas package — skip
    const c = mkComet();
    expect(() =>
      drawCometHoverCard(ctx, c, { x: c.x, y: c.y }, { viewport: vp }),
    ).not.toThrow();
  });
});

describe("formatCompactAge", () => {
  // Use an explicit nowMs so tests are wall-clock independent. The
  // fixed reference is 2026-05-01T00:00:00Z = 1761955200000ms.
  const REFERENCE_NOW_MS = 1_761_955_200_000;

  it("returns 'now' for a future or zero age", () => {
    // publishedAt in the future relative to nowMs
    expect(formatCompactAge(REFERENCE_NOW_MS / 1000 + 60, REFERENCE_NOW_MS)).toBe("now");
    // publishedAt exactly at nowMs
    expect(formatCompactAge(REFERENCE_NOW_MS / 1000, REFERENCE_NOW_MS)).toBe("now");
  });

  it("returns 'Xs ago' for sub-minute ages", () => {
    expect(formatCompactAge((REFERENCE_NOW_MS - 30_000) / 1000, REFERENCE_NOW_MS)).toBe("30s ago");
  });

  it("returns 'Xm ago' for sub-hour ages", () => {
    expect(formatCompactAge((REFERENCE_NOW_MS - 12 * 60 * 1000) / 1000, REFERENCE_NOW_MS)).toBe(
      "12m ago",
    );
  });

  it("returns 'Xh ago' for sub-day ages", () => {
    expect(
      formatCompactAge((REFERENCE_NOW_MS - 5 * 60 * 60 * 1000) / 1000, REFERENCE_NOW_MS),
    ).toBe("5h ago");
  });

  it("returns 'Xd ago' for multi-day ages", () => {
    expect(
      formatCompactAge((REFERENCE_NOW_MS - 3 * 24 * 60 * 60 * 1000) / 1000, REFERENCE_NOW_MS),
    ).toBe("3d ago");
  });

  it("treats publishedAt=0 (unset) as 'now', not the 1970 epoch", () => {
    // Without this guard, formatCompactAge(0, Date.now()) returns
    // ~20000d ago — the bug Copilot caught in PR #592.
    expect(formatCompactAge(0, REFERENCE_NOW_MS)).toBe("now");
  });
});

describe("rectsOverlap", () => {
  it("returns true for overlapping rects", () => {
    expect(rectsOverlap({ x: 0, y: 0, w: 10, h: 10 }, { x: 5, y: 5, w: 10, h: 10 })).toBe(true);
  });
  it("returns false for separated rects", () => {
    expect(rectsOverlap({ x: 0, y: 0, w: 10, h: 10 }, { x: 20, y: 0, w: 10, h: 10 })).toBe(false);
  });
  it("treats edge-touching rects as non-overlapping", () => {
    // a's right edge meets b's left edge exactly
    expect(rectsOverlap({ x: 0, y: 0, w: 10, h: 10 }, { x: 10, y: 0, w: 10, h: 10 })).toBe(false);
  });
});

describe("clampToSafeArea", () => {
  const vp = { w: 1000, h: 800 };
  const margin = 16;

  it("returns input unchanged when fully inside the safe area", () => {
    const r = clampToSafeArea({ x: 100, y: 100, w: 200, h: 120 }, vp, []);
    expect(r).toEqual({ x: 100, y: 100, w: 200, h: 120 });
  });

  it("nudges left when the rect overflows the right edge", () => {
    const r = clampToSafeArea({ x: 950, y: 100, w: 220, h: 120 }, vp, []);
    expect(r.x + r.w).toBeLessThanOrEqual(vp.w - margin);
    expect(r.w).toBe(220); // size unchanged
  });

  it("nudges down when the rect overflows the top edge", () => {
    const r = clampToSafeArea({ x: 100, y: -50, w: 220, h: 120 }, vp, []);
    expect(r.y).toBeGreaterThanOrEqual(margin);
  });

  it("nudges up when the rect overflows the bottom edge", () => {
    const r = clampToSafeArea({ x: 100, y: 750, w: 220, h: 120 }, vp, []);
    expect(r.y + r.h).toBeLessThanOrEqual(vp.h - margin);
  });

  it("nudges away from a fixed UI rect (zoom pill at bottom)", () => {
    const fixedRects = [{ x: 290, y: 700, w: 420, h: 60 }];
    const r = clampToSafeArea({ x: 300, y: 680, w: 220, h: 120 }, vp, fixedRects);
    expect(rectsOverlap(r, fixedRects[0])).toBe(false);
  });

  it("preserves rect size when nudging", () => {
    const fixedRects = [{ x: 0, y: 0, w: 1000, h: 600 }]; // huge rect
    const r = clampToSafeArea({ x: 100, y: 100, w: 220, h: 120 }, vp, fixedRects);
    expect(r.w).toBe(220);
    expect(r.h).toBe(120);
  });
});

describe("findHoveredComet", () => {
  it("returns the nearest comet within 24px of the cursor", () => {
    const comets = [
      mkComet({ comet_id: "a", x: 100, y: 100 }),
      mkComet({ comet_id: "b", x: 200, y: 200 }),
    ];
    expect(findHoveredComet(comets, { x: 110, y: 105 })?.comet_id).toBe("a");
    expect(findHoveredComet(comets, { x: 195, y: 210 })?.comet_id).toBe("b");
  });

  it("returns the nearer of two comets in range (relevance is NOT used as tie-breaker)", () => {
    // Distance-based contract: "closer to the cursor wins". The two
    // relevance values here are intentionally inverted from distance
    // ordering to confirm the function ignores relevance — both
    // assertions resolve purely by which comet head is nearer.
    const comets = [
      mkComet({ comet_id: "low", x: 100, y: 100, relevanceScore: 0.9 }),
      mkComet({ comet_id: "high", x: 110, y: 100, relevanceScore: 0.1 }),
    ];
    expect(findHoveredComet(comets, { x: 102, y: 100 })?.comet_id).toBe("low");
    expect(findHoveredComet(comets, { x: 108, y: 100 })?.comet_id).toBe("high");
  });

  it("returns null when no comet is within 24px", () => {
    const comets = [mkComet({ comet_id: "a", x: 0, y: 0 })];
    expect(findHoveredComet(comets, { x: 50, y: 50 })).toBeNull();
  });

  it("returns null on an empty comet list", () => {
    expect(findHoveredComet([], { x: 0, y: 0 })).toBeNull();
  });

  it("considers the 24px boundary inclusive", () => {
    const comets = [mkComet({ comet_id: "a", x: 0, y: 0 })];
    // Exactly 24px away (3-4-5 triangle scaled).
    expect(findHoveredComet(comets, { x: 0, y: 24 })?.comet_id).toBe("a");
    // Beyond.
    expect(findHoveredComet(comets, { x: 0, y: 25 })).toBeNull();
  });
});

describe("buildHeadFirstPath", () => {
  it("prepends the comet's current head position before the reversed tail", () => {
    // tickComet records the OLD position to tailHistory then advances comet.x/y.
    // After a tick, comet.x/y is the rendered head position; tailHistory's
    // last entry is one frame behind. The label path must start at the
    // current head, not at tailHistory's last entry.
    const comet = mkComet({
      x: 100,
      y: 50,
      tailHistory: [
        { x: 60, y: 50 },
        { x: 70, y: 50 },
        { x: 80, y: 50 },
        { x: 90, y: 50 }, // last recorded — one frame behind comet.x
      ],
    });
    const path = buildHeadFirstPath(comet);
    expect(path[0]).toEqual({ x: 100, y: 50 }); // current head first
    expect(path[1]).toEqual({ x: 90, y: 50 }); // most recent recorded
    expect(path[path.length - 1]).toEqual({ x: 60, y: 50 }); // oldest last
    expect(path).toHaveLength(5);
  });

  it("returns just the head when tailHistory is empty", () => {
    const comet = mkComet({ x: 7, y: 11, tailHistory: [] });
    expect(buildHeadFirstPath(comet)).toEqual([{ x: 7, y: 11 }]);
  });

  it("does not mutate the input tailHistory", () => {
    const original = [
      { x: 60, y: 50 },
      { x: 70, y: 50 },
    ];
    const comet = mkComet({ x: 80, y: 50, tailHistory: original });
    buildHeadFirstPath(comet);
    expect(original).toEqual([
      { x: 60, y: 50 },
      { x: 70, y: 50 },
    ]);
  });
});

describe("drawCometLabel (smoke)", () => {
  it("does not throw with a real-shaped comet", () => {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return; // jsdom without canvas package — skip
    const comet = mkComet();
    expect(() => drawCometLabel(ctx, comet)).not.toThrow();
  });

  it("returns early without throwing when tail is too short", () => {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const shortTail = mkComet({ tailHistory: [{ x: 0, y: 0 }] });
    expect(() => drawCometLabel(ctx, shortTail)).not.toThrow();
  });

  it("returns early without throwing when title is empty", () => {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    expect(() => drawCometLabel(ctx, mkComet({ title: "" }))).not.toThrow();
  });
});
