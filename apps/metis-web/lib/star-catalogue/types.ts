import type { StellarProfile } from "@/lib/landing-stars/types";

export interface SectorKey {
  sx: number;
  sy: number;
}

export interface CatalogueStar {
  /** Unique deterministic ID: `${galaxySeed}-${sectorKey}-${index}` */
  id: string;
  /** World X coordinate */
  wx: number;
  /** World Y coordinate */
  wy: number;
  /** Full procedural stellar profile */
  profile: StellarProfile;
  /**
   * Display name. `null` for field stars (background decorative stars)
   * per ADR 0006. Populated only when a star is promoted to a named
   * landmark or carries user content.
   */
  name: string | null;
  /** Apparent magnitude (0=brightest, 6.5=dimmest visible) */
  apparentMagnitude: number;
  /** Depth layer for parallax (0=closest, 1=farthest) */
  depthLayer: number;
}

export interface CatalogueSector {
  key: SectorKey;
  stars: CatalogueStar[];
}

export interface StarCatalogueConfig {
  /** Master seed for the galaxy. Same seed = same galaxy. */
  galaxySeed: string;
  /** World-space size of each sector square */
  sectorSize: number;
  /** Number of stars to generate per sector */
  starsPerSector: number;
  /** Number of spiral arms */
  numArms: number;
  /** Winding rate of spiral arms (radians per unit radius) */
  armWindingRate: number;
}

/**
 * A CatalogueStar that has been promoted to the user's constellation.
 *
 * Naming note: the existing `UserStar` in `lib/constellation-types.ts` is the
 * legacy 2D-only shape (x, y, size, label, …). Phase 5 of the Interactive
 * Star Catalogue plan (`docs/plans/2026-04-05-interactive-star-catalogue.md`)
 * unifies the two so user stars are just CatalogueStars with extra metadata.
 * Until that migration happens we expose this new shape as `CatalogueUserStar`
 * so consumers that import from `constellation-types` keep compiling.
 */
export interface CatalogueUserStar extends CatalogueStar {
  label: string;
  primaryDomainId: string | null;
  relatedDomainIds: string[];
  stage: "seed" | "sprout" | "bloom" | "nova";
  notes: string;
  connectedUserStarIds: string[];
  learningRoute: string | null;
}

export const DEFAULT_CATALOGUE_CONFIG: StarCatalogueConfig = {
  galaxySeed: "metis-prime",
  sectorSize: 960,
  starsPerSector: 350,
  numArms: 4,
  armWindingRate: 3.5,
};
