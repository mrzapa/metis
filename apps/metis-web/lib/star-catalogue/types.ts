import type { StellarProfile } from "@/lib/landing-stars/types";
import type { LearningRoute, UserStarStage } from "@/lib/constellation-types";

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
 * **Unified read-view of a user star** — a `CatalogueStar` with the user-
 * facing metadata (label, faculty assignment, stage, manifest links, etc.)
 * layered on top.
 *
 * **Storage contract (ADR 0012):** the persisted shape is still the legacy
 * `UserStar` from `lib/constellation-types.ts`. `CatalogueUserStar` is the
 * shape downstream consumers (M14 Forge, M16 evals, future marketplace)
 * read user stars *through* — derived on the fly via
 * `userStarToCatalogueUserStar` from `lib/star-catalogue/user-star-adapter`.
 * Storage migration (replacing `UserStar.x/y` with `wx/wy`, etc.) is
 * deliberately deferred — see ADR 0012 for the rationale.
 *
 * Stage and learning-route fields use the legacy `UserStarStage` /
 * `LearningRoute` types so adapter projection is mechanical, not a lossy
 * conversion.
 */
export interface CatalogueUserStar extends CatalogueStar {
  label: string;
  primaryDomainId: string | null;
  relatedDomainIds: string[];
  stage: UserStarStage;
  notes: string;
  connectedUserStarIds: string[];
  learningRoute: LearningRoute | null;
}

export const DEFAULT_CATALOGUE_CONFIG: StarCatalogueConfig = {
  galaxySeed: "metis-prime",
  sectorSize: 960,
  starsPerSector: 350,
  numArms: 4,
  armWindingRate: 3.5,
};
