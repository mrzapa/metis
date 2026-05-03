import { describe, expect, it } from "vitest";
import { SeededRNG } from "../rng";
import {
  generateClassicalDesignation,
  generateStarName,
} from "../star-name-generator";

describe("generateStarName", () => {
  describe("field tier", () => {
    it("returns a null name and kind", () => {
      expect(generateStarName({ tier: "field" })).toEqual({ name: null, kind: null });
    });

    it("ignores any rng or magnitude inputs", () => {
      const rng = new SeededRNG(1234);
      expect(generateStarName({ tier: "field", rng, magnitude: 1 })).toEqual({
        name: null,
        kind: null,
      });
    });
  });

  describe("landmark tier", () => {
    // M24 Phase 6 (ADR 0019): the 8 classical-named landmark constellations
    // were retired alongside the faculty IA. Landmark tier now degrades to
    // a field-tier null name; legacy callers continue to compile.
    it("returns null name and kind (retired tier)", () => {
      const rng = new SeededRNG(1);
      expect(generateStarName({ tier: "landmark", rng, magnitude: 1 })).toEqual({
        name: null,
        kind: null,
      });
    });

    it("returns null even when rng or magnitude are omitted", () => {
      expect(generateStarName({ tier: "landmark" })).toEqual({
        name: null,
        kind: null,
      });
      expect(generateStarName({ tier: "landmark", magnitude: 3 })).toEqual({
        name: null,
        kind: null,
      });
      expect(generateStarName({ tier: "landmark", rng: new SeededRNG(7) })).toEqual({
        name: null,
        kind: null,
      });
    });
  });

  describe("user tier", () => {
    it("returns the user-supplied name with user kind", () => {
      expect(generateStarName({ tier: "user", userSuppliedName: "Project Kilo" })).toEqual({
        name: "Project Kilo",
        kind: "user",
      });
    });

    it("trims whitespace around the user-supplied name", () => {
      expect(
        generateStarName({ tier: "user", userSuppliedName: "   padded  " }),
      ).toEqual({ name: "padded", kind: "user" });
    });

    it("returns null name and kind when user name is empty", () => {
      expect(generateStarName({ tier: "user", userSuppliedName: "" })).toEqual({
        name: null,
        kind: null,
      });
      expect(generateStarName({ tier: "user", userSuppliedName: "   " })).toEqual({
        name: null,
        kind: null,
      });
    });

    it("returns null when user name is null or undefined", () => {
      expect(generateStarName({ tier: "user", userSuppliedName: null })).toEqual({
        name: null,
        kind: null,
      });
      expect(generateStarName({ tier: "user" })).toEqual({ name: null, kind: null });
    });
  });
});

describe("generateClassicalDesignation", () => {
  it("returns a Bayer-style name for bright stars (magnitude < 2.5)", () => {
    const name = generateClassicalDesignation(new SeededRNG(100), 1.5);
    expect(name).toMatch(/^[A-Z][a-z]+ [A-Z]/);
  });

  it("returns a Flamsteed-style name for mid stars (2.5 <= mag < 4.5)", () => {
    const name = generateClassicalDesignation(new SeededRNG(200), 3.5);
    expect(name).toMatch(/^\d+ [A-Z]/);
  });

  it("returns an HD catalogue number for dim stars (mag >= 4.5)", () => {
    const name = generateClassicalDesignation(new SeededRNG(300), 5.5);
    expect(name).toMatch(/^HD \d+$/);
  });

  it("is deterministic for the same rng seed and magnitude", () => {
    const a = generateClassicalDesignation(new SeededRNG(7), 2);
    const b = generateClassicalDesignation(new SeededRNG(7), 2);
    expect(a).toEqual(b);
  });
});
