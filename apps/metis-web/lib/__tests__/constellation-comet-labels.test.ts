import { describe, expect, it } from "vitest";

import { computeArcLengths } from "../constellation-comet-labels";

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
