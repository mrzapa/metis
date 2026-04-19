import { describe, expect, it, vi } from "vitest";
import { StarCatalogue } from "../star-catalogue";
import { generateStellarProfile } from "@/lib/landing-stars/stellar-profile";
import type { StarCatalogueConfig } from "../types";

const BASE_CONFIG: StarCatalogueConfig = {
  galaxySeed: "metis-prime",
  sectorSize: 1000,
  starsPerSector: 200,
  numArms: 4,
  armWindingRate: 3.5,
};

function makeCatalogue(overrides: Partial<StarCatalogueConfig> = {}) {
  return new StarCatalogue({ ...BASE_CONFIG, ...overrides }, generateStellarProfile);
}

describe("StarCatalogue", () => {
  describe("generateSector", () => {
    it("produces deterministic stars for the same (sx, sy)", () => {
      const cat = makeCatalogue();
      const first = cat.generateSector(0, 0);
      // Fresh catalogue with the same config reproduces the same content.
      const cat2 = makeCatalogue();
      const second = cat2.generateSector(0, 0);

      expect(second.stars.length).toBe(first.stars.length);
      for (let i = 0; i < first.stars.length; i++) {
        expect(second.stars[i].id).toBe(first.stars[i].id);
        expect(second.stars[i].wx).toBe(first.stars[i].wx);
        expect(second.stars[i].wy).toBe(first.stars[i].wy);
        expect(second.stars[i].apparentMagnitude).toBe(first.stars[i].apparentMagnitude);
      }
    });

    it("produces different sectors for different galaxy seeds", () => {
      const a = new StarCatalogue(
        { ...BASE_CONFIG, galaxySeed: "galaxy-a" },
        generateStellarProfile,
      ).generateSector(0, 0);
      const b = new StarCatalogue(
        { ...BASE_CONFIG, galaxySeed: "galaxy-b" },
        generateStellarProfile,
      ).generateSector(0, 0);

      // IDs embed the seed so they must diverge
      expect(a.stars[0]?.id).not.toBe(b.stars[0]?.id);
    });

    it("returns stars with unique IDs within a viewport", () => {
      const cat = makeCatalogue();
      const stars = cat.getVisibleStars(-2000, 2000, -2000, 2000);
      const ids = new Set(stars.map((s) => s.id));
      expect(ids.size).toBe(stars.length);
    });

    it("caches sectors so the second call does not re-invoke the profile generator", () => {
      const spyProfile = vi.fn(generateStellarProfile);
      const cat = new StarCatalogue(BASE_CONFIG, spyProfile);

      cat.generateSector(3, 7);
      const callsAfterFirst = spyProfile.mock.calls.length;
      expect(callsAfterFirst).toBeGreaterThan(0);

      cat.generateSector(3, 7);
      // No new calls on the second invocation — sector was cached.
      expect(spyProfile.mock.calls.length).toBe(callsAfterFirst);
    });

    it("places stars inside the sector's world-space bounds", () => {
      const cat = makeCatalogue();
      const sector = cat.generateSector(2, -3);
      const { sectorSize } = BASE_CONFIG;
      const wxMin = 2 * sectorSize;
      const wxMax = (2 + 1) * sectorSize;
      const wyMin = -3 * sectorSize;
      const wyMax = (-3 + 1) * sectorSize;

      for (const star of sector.stars) {
        expect(star.wx).toBeGreaterThanOrEqual(wxMin);
        expect(star.wx).toBeLessThanOrEqual(wxMax);
        expect(star.wy).toBeGreaterThanOrEqual(wyMin);
        expect(star.wy).toBeLessThanOrEqual(wyMax);
      }
    });

    it("keeps apparentMagnitude in the spec range [0, 6.5]", () => {
      const cat = makeCatalogue();
      const sector = cat.generateSector(0, 0);
      for (const star of sector.stars) {
        expect(star.apparentMagnitude).toBeGreaterThanOrEqual(0);
        expect(star.apparentMagnitude).toBeLessThanOrEqual(6.5);
      }
    });

    it("keeps depthLayer in [0, 1]", () => {
      const cat = makeCatalogue();
      const sector = cat.generateSector(0, 0);
      for (const star of sector.stars) {
        expect(star.depthLayer).toBeGreaterThanOrEqual(0);
        expect(star.depthLayer).toBeLessThanOrEqual(1);
      }
    });
  });

  describe("getVisibleStars", () => {
    it("returns stars from every intersecting sector", () => {
      const cat = makeCatalogue();
      const stars = cat.getVisibleStars(-500, 500, -500, 500, 0);
      expect(stars.length).toBeGreaterThan(0);
    });

    it("returns stable results across repeated calls with the same viewport", () => {
      const cat = makeCatalogue();
      const a = cat.getVisibleStars(-1500, 1500, -1500, 1500);
      const b = cat.getVisibleStars(-1500, 1500, -1500, 1500);
      expect(a.length).toBe(b.length);
      for (let i = 0; i < a.length; i++) {
        expect(a[i].id).toBe(b[i].id);
      }
    });

    it("caches sector results (second identical call reuses the RNG output)", () => {
      const spyProfile = vi.fn(generateStellarProfile);
      const cat = new StarCatalogue(BASE_CONFIG, spyProfile);

      cat.getVisibleStars(-500, 500, -500, 500);
      const callsAfterFirst = spyProfile.mock.calls.length;
      expect(callsAfterFirst).toBeGreaterThan(0);

      cat.getVisibleStars(-500, 500, -500, 500);
      expect(spyProfile.mock.calls.length).toBe(callsAfterFirst);
    });
  });

  describe("worldToSector", () => {
    it("maps world coordinates to the enclosing sector", () => {
      const cat = makeCatalogue();
      expect(cat.worldToSector(0, 0)).toEqual({ sx: 0, sy: 0 });
      expect(cat.worldToSector(999, 0)).toEqual({ sx: 0, sy: 0 });
      expect(cat.worldToSector(1000, 0)).toEqual({ sx: 1, sy: 0 });
      expect(cat.worldToSector(-1, 0)).toEqual({ sx: -1, sy: 0 });
    });
  });

  describe("evictDistantSectors", () => {
    it("removes sectors beyond the given Manhattan distance", () => {
      const cat = makeCatalogue();
      cat.generateSector(0, 0);
      cat.generateSector(5, 0);
      cat.generateSector(0, 5);
      expect(cat.cachedSectorCount).toBe(3);

      cat.evictDistantSectors(0, 0, 3);
      expect(cat.cachedSectorCount).toBe(1);
    });

    it("keeps sectors within the given Manhattan distance", () => {
      const cat = makeCatalogue();
      cat.generateSector(1, 1);
      cat.generateSector(2, 0);
      cat.evictDistantSectors(0, 0, 3);
      expect(cat.cachedSectorCount).toBe(2);
    });
  });
});
