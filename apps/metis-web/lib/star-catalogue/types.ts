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

export const DEFAULT_CATALOGUE_CONFIG: StarCatalogueConfig = {
  galaxySeed: "metis-prime",
  sectorSize: 960,
  starsPerSector: 350,
  numArms: 4,
  armWindingRate: 3.5,
};
