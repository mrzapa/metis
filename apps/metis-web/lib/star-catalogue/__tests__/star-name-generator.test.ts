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
    it("produces a classical Bayer designation for bright magnitudes", () => {
      const rng = new SeededRNG(1);
      const result = generateStarName({ tier: "landmark", rng, magnitude: 1 });
      expect(result.kind).toBe("classical");
      expect(typeof result.name).toBe("string");
      expect(result.name).toMatch(/^[A-Z][a-z]+ [A-Z]/);
    });

    it("produces Flamsteed-style names for mid magnitudes", () => {
      const rng = new SeededRNG(2);
      const result = generateStarName({ tier: "landmark", rng, magnitude: 3 });
      expect(result.kind).toBe("classical");
      expect(result.name).toMatch(/^\d+ [A-Z]/);
    });

    it("produces HD catalogue numbers for dim magnitudes", () => {
      const rng = new SeededRNG(3);
      const result = generateStarName({ tier: "landmark", rng, magnitude: 5 });
      expect(result.kind).toBe("classical");
      expect(result.name).toMatch(/^HD \d+$/);
    });

    it("is deterministic for the same rng seed and magnitude", () => {
      const a = generateStarName({ tier: "landmark", rng: new SeededRNG(42), magnitude: 1 });
      const b = generateStarName({ tier: "landmark", rng: new SeededRNG(42), magnitude: 1 });
      expect(a).toEqual(b);
    });

    it("throws when rng is omitted", () => {
      expect(() => generateStarName({ tier: "landmark", magnitude: 1 })).toThrow();
    });

    it("throws when magnitude is omitted", () => {
      expect(() => generateStarName({ tier: "landmark", rng: new SeededRNG(1) })).toThrow();
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
