import { fnv1a32, SeededRNG } from "./rng";
import { galaxyDensityFactor } from "./galaxy-distribution";
import type { CatalogueStar, CatalogueSector, SectorKey, StarCatalogueConfig } from "./types";

// NOTE: This import path assumes lib/landing-stars/stellar-profile.ts exports generateStellarProfile.
// In the actual codebase this would be:
//   import { generateStellarProfile } from "@/lib/landing-stars/stellar-profile";
// For now we declare the dependency explicitly.
type StellarProfileOptions =
  import("@/lib/landing-stars/stellar-profile").GenerateStellarProfileOptions;
type StellarProfileGenerator = (
  seed: string | number,
  options?: StellarProfileOptions,
) => import("@/lib/landing-stars/types").StellarProfile;

const MAX_CACHED_SECTORS = 512;

export class StarCatalogue {
  private readonly cfg: StarCatalogueConfig;
  private readonly sectorCache = new Map<string, CatalogueSector>();
  private readonly generateProfile: StellarProfileGenerator;

  constructor(cfg: StarCatalogueConfig, generateProfile: StellarProfileGenerator) {
    this.cfg = cfg;
    this.generateProfile = generateProfile;
  }

  /** Canonical string key for a sector. */
  private sectorKeyStr(sx: number, sy: number): string {
    return `${sx},${sy}`;
  }

  /** World coordinate to sector index. */
  worldToSector(wx: number, wy: number): SectorKey {
    return {
      sx: Math.floor(wx / this.cfg.sectorSize),
      sy: Math.floor(wy / this.cfg.sectorSize),
    };
  }

  /**
   * Generate all stars for a sector. Pure/deterministic.
   * Calling this twice with the same (sx, sy) always returns identical results.
   */
  generateSector(sx: number, sy: number): CatalogueSector {
    const key = this.sectorKeyStr(sx, sy);
    const cached = this.sectorCache.get(key);
    if (cached) {
      // LRU: move to end
      this.sectorCache.delete(key);
      this.sectorCache.set(key, cached);
      return cached;
    }

    const sectorSeed = fnv1a32(`${this.cfg.galaxySeed}:${key}`);
    const rng = new SeededRNG(sectorSeed);
    const stars: CatalogueStar[] = [];

    // Galaxy-scale density: sectors near the galactic centre get more stars;
    // outer sectors thin out, breaking the uniform-grid look at zoom-out.
    const galaxyRadius = this.cfg.sectorSize * 8; // ~8 sectors = galaxy radius
    const sectorCentreWx = (sx + 0.5) * this.cfg.sectorSize;
    const sectorCentreWy = (sy + 0.5) * this.cfg.sectorSize;
    const density = galaxyDensityFactor(
      sectorCentreWx,
      sectorCentreWy,
      this.cfg.numArms,
      this.cfg.armWindingRate,
      galaxyRadius,
    );
    // Poisson-style count: floor + stochastic rounding so average = starsPerSector * density
    const expectedCount = this.cfg.starsPerSector * density;
    const starsToGen = Math.floor(expectedCount) + (rng.next() < (expectedCount % 1) ? 1 : 0);

    for (let i = 0; i < starsToGen; i++) {
      const starSeedStr = `${this.cfg.galaxySeed}:${key}:${i}`;
      const starSeed = fnv1a32(starSeedStr);
      const starRng = new SeededRNG(starSeed);

      // Uniform random placement within sector — avoids the repeating per-sector
      // mini-spiral texture that looks like a grid at extreme zoom-out.
      const wx = starRng.next();
      const wy = starRng.next();
      const depthLayer = Math.min(1, 0.3 + starRng.next() * 0.7);

      const sectorWx = sx * this.cfg.sectorSize + wx * this.cfg.sectorSize;
      const sectorWy = sy * this.cfg.sectorSize + wy * this.cfg.sectorSize;

      const profile = this.generateProfile(starSeedStr);

      // Apparent magnitude from luminosity
      const luminosity = profile.luminositySolar;
      const baseMag = 5.0 - 2.5 * Math.log10(Math.max(luminosity, 0.0001));
      const apparentMagnitude = Math.max(0, Math.min(6.5, baseMag + starRng.range(-0.5, 0.5)));

      stars.push({
        id: `cat-${this.cfg.galaxySeed}-${key}-${i}`,
        wx: sectorWx,
        wy: sectorWy,
        profile,
        name: null,
        apparentMagnitude,
        depthLayer,
      });
    }

    const sector: CatalogueSector = { key: { sx, sy }, stars };
    this.sectorCache.set(key, sector);

    // LRU eviction
    if (this.sectorCache.size > MAX_CACHED_SECTORS) {
      const oldestKey = this.sectorCache.keys().next().value;
      if (oldestKey) {
        this.sectorCache.delete(oldestKey);
      }
    }

    return sector;
  }

  /**
   * Return all visible stars for the given world-space viewport rectangle.
   * Generates sectors on demand, caches them.
   */
  getVisibleStars(
    wxMin: number,
    wxMax: number,
    wyMin: number,
    wyMax: number,
    bufferFactor = 1,
  ): CatalogueStar[] {
    const s = this.cfg.sectorSize;
    const sxMin = Math.floor(wxMin / s) - bufferFactor;
    const sxMax = Math.floor(wxMax / s) + bufferFactor;
    const syMin = Math.floor(wyMin / s) - bufferFactor;
    const syMax = Math.floor(wyMax / s) + bufferFactor;

    const result: CatalogueStar[] = [];
    for (let sx = sxMin; sx <= sxMax; sx++) {
      for (let sy = syMin; sy <= syMax; sy++) {
        const sector = this.generateSector(sx, sy);
        for (const star of sector.stars) {
          result.push(star);
        }
      }
    }
    return result;
  }

  /**
   * Evict sectors far from the current viewport to prevent unbounded memory growth.
   * Call periodically (e.g. once per second), not per frame.
   */
  evictDistantSectors(
    currentSx: number,
    currentSy: number,
    maxManhattanDistance: number,
  ): void {
    for (const [key, sector] of this.sectorCache.entries()) {
      const dx = Math.abs(sector.key.sx - currentSx);
      const dy = Math.abs(sector.key.sy - currentSy);
      if (dx + dy > maxManhattanDistance) {
        this.sectorCache.delete(key);
      }
    }
  }

  /** Number of sectors currently cached. */
  get cachedSectorCount(): number {
    return this.sectorCache.size;
  }
}
