import { describe, expect, it } from "vitest";

import {
  computeArcLengths,
  placeCharactersAlongPath,
  samplePathAt,
} from "../constellation-comet-labels";

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
});
