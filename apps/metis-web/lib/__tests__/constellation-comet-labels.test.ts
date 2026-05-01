import { describe, expect, it } from "vitest";

import {
  buildHeadFirstPath,
  computeArcLengths,
  drawCometLabel,
  placeCharactersAlongPath,
  samplePathAt,
  shouldFlipOrientation,
  smoothedTangentAt,
} from "../constellation-comet-labels";
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
