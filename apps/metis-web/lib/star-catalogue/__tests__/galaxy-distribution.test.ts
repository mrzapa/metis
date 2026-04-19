import { describe, expect, it } from "vitest";
import { SeededRNG } from "../rng";
import {
  galaxyDensityFactor,
  sampleGalaxyPosition,
  type GalaxyDistributionConfig,
} from "../galaxy-distribution";

const DEFAULT_CFG: GalaxyDistributionConfig = {
  numArms: 4,
  armWindingRate: 3.5,
  coreRadius: 0.15,
  diskFalloff: 3.0,
};

describe("sampleGalaxyPosition", () => {
  it("returns finite (wx, wy) within [-1, 1]", () => {
    const rng = new SeededRNG(1);
    for (let i = 0; i < 2000; i++) {
      const { wx, wy } = sampleGalaxyPosition(rng, DEFAULT_CFG);
      expect(Number.isFinite(wx)).toBe(true);
      expect(Number.isFinite(wy)).toBe(true);
      expect(wx).toBeGreaterThanOrEqual(-1);
      expect(wx).toBeLessThanOrEqual(1);
      expect(wy).toBeGreaterThanOrEqual(-1);
      expect(wy).toBeLessThanOrEqual(1);
    }
  });

  it("returns depthLayer in [0, 1]", () => {
    const rng = new SeededRNG(2);
    for (let i = 0; i < 1000; i++) {
      const { depthLayer } = sampleGalaxyPosition(rng, DEFAULT_CFG);
      expect(depthLayer).toBeGreaterThanOrEqual(0);
      expect(depthLayer).toBeLessThanOrEqual(1);
    }
  });

  it("is deterministic for the same seed", () => {
    const a = sampleGalaxyPosition(new SeededRNG(777), DEFAULT_CFG);
    const b = sampleGalaxyPosition(new SeededRNG(777), DEFAULT_CFG);
    expect(a).toEqual(b);
  });

  it("produces samples across the disk (not degenerate)", () => {
    // Sanity check: 1000 samples should cover a decent fraction of a small grid
    // so the distribution isn't collapsed to a single point.
    const rng = new SeededRNG(3);
    const visited = new Set<string>();
    for (let i = 0; i < 1000; i++) {
      const { wx, wy } = sampleGalaxyPosition(rng, DEFAULT_CFG);
      const bx = Math.round(wx * 8);
      const by = Math.round(wy * 8);
      visited.add(`${bx},${by}`);
    }
    expect(visited.size).toBeGreaterThan(40);
  });
});

describe("galaxyDensityFactor", () => {
  it("is highest at the galactic centre", () => {
    const core = galaxyDensityFactor(0, 0, 4, 3.5, 1);
    const midRim = galaxyDensityFactor(0.6, 0, 4, 3.5, 1);
    expect(core).toBeGreaterThan(midRim);
  });

  it("clamps to at least the minimum background density in the far void", () => {
    const far = galaxyDensityFactor(100, 100, 4, 3.5, 1);
    expect(far).toBeGreaterThan(0);
    expect(far).toBeLessThan(0.1);
  });

  it("returns values bounded in (0, 1]", () => {
    for (const [x, y] of [[0, 0], [0.5, 0.5], [1, 0], [-0.5, 0.8], [5, -5]]) {
      const d = galaxyDensityFactor(x, y, 4, 3.5, 1);
      expect(d).toBeGreaterThan(0);
      expect(d).toBeLessThanOrEqual(1);
    }
  });

  it("is deterministic (same inputs -> same output)", () => {
    const a = galaxyDensityFactor(0.25, -0.4, 2, 4.0, 1.2);
    const b = galaxyDensityFactor(0.25, -0.4, 2, 4.0, 1.2);
    expect(a).toBe(b);
  });
});
