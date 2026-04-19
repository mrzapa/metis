import { describe, expect, it } from "vitest";
import { fnv1a32, SeededRNG } from "../rng";

describe("fnv1a32", () => {
  it("returns the same hash for the same input", () => {
    expect(fnv1a32("test")).toBe(fnv1a32("test"));
  });

  it("returns different hashes for different inputs", () => {
    expect(fnv1a32("test")).not.toBe(fnv1a32("Test"));
    expect(fnv1a32("")).not.toBe(fnv1a32("a"));
  });

  it("returns an unsigned 32-bit integer", () => {
    const h = fnv1a32("the quick brown fox");
    expect(Number.isInteger(h)).toBe(true);
    expect(h).toBeGreaterThanOrEqual(0);
    expect(h).toBeLessThan(2 ** 32);
  });

  it("handles the empty string with the FNV-1a offset basis", () => {
    // Offset basis 0x811c9dc5 -> 2166136261 unsigned
    expect(fnv1a32("")).toBe(0x811c9dc5);
  });
});

describe("SeededRNG", () => {
  it("produces the same sequence for the same seed", () => {
    const a = new SeededRNG(42);
    const b = new SeededRNG(42);
    for (let i = 0; i < 100; i++) {
      expect(a.next()).toBe(b.next());
    }
  });

  it("produces different sequences for different seeds", () => {
    const a = new SeededRNG(1);
    const b = new SeededRNG(2);
    // First ~10 samples almost always diverge; if every pair matched the PRNG
    // would be broken.
    let differences = 0;
    for (let i = 0; i < 10; i++) {
      if (a.next() !== b.next()) differences += 1;
    }
    expect(differences).toBeGreaterThan(5);
  });

  it("returns floats in [0, 1)", () => {
    const rng = new SeededRNG(123);
    for (let i = 0; i < 1000; i++) {
      const v = rng.next();
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });

  it("range(min, max) returns values within [min, max)", () => {
    const rng = new SeededRNG(7);
    for (let i = 0; i < 1000; i++) {
      const v = rng.range(-5, 10);
      expect(v).toBeGreaterThanOrEqual(-5);
      expect(v).toBeLessThan(10);
    }
  });

  it("int(n) returns integers in [0, n)", () => {
    const rng = new SeededRNG(999);
    for (let i = 0; i < 1000; i++) {
      const v = rng.int(7);
      expect(Number.isInteger(v)).toBe(true);
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(7);
    }
  });

  it("pick selects elements from the array", () => {
    const rng = new SeededRNG(5);
    const items = ["a", "b", "c", "d"] as const;
    const seen = new Set<string>();
    for (let i = 0; i < 200; i++) {
      const v = rng.pick(items);
      expect(items).toContain(v);
      seen.add(v);
    }
    expect(seen.size).toBe(items.length);
  });

  it("gaussian returns approximately normal samples", () => {
    const rng = new SeededRNG(31);
    const samples: number[] = [];
    for (let i = 0; i < 2000; i++) samples.push(rng.gaussian());
    const mean = samples.reduce((s, v) => s + v, 0) / samples.length;
    // Sample mean for N(0,1) should be near 0 for 2000 draws
    expect(Math.abs(mean)).toBeLessThan(0.15);
    // Some samples must land on either side of zero
    expect(samples.some((v) => v > 0)).toBe(true);
    expect(samples.some((v) => v < 0)).toBe(true);
  });
});
