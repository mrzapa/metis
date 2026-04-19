export type {
  RgbColor,
  SeedInput,
  StellarPalette,
  StellarProfile,
  StellarType,
  StellarVisualProfile,
} from "./types";
export type {
  StarContentType,
  StarVisualArchetype,
} from "./star-visual-archetype";
export {
  CONTENT_TYPE_ARCHETYPE_MAP,
  DEFAULT_VISUAL_ARCHETYPE,
  STAR_VISUAL_ARCHETYPE_IDS,
  getStarVisualArchetypeId,
  selectStarVisualArchetype,
} from "./star-visual-archetype";
export type {
  DeriveStarAnnotationsOptions,
  StarAnnotationAttributeValues,
  StarAnnotationHalo,
  StarAnnotationRing,
  StarAnnotationSatellites,
  StarAnnotations,
} from "./star-annotations";
export {
  DEFAULT_RING_OPACITY,
  DEFAULT_SATELLITE_PERIOD_SECONDS,
  DEFAULT_SATELLITE_RADIUS,
  HALO_RECENCY_HALF_LIFE_SECONDS,
  HALO_STRENGTH_THRESHOLD,
  deriveStarAnnotations,
  getStarAnnotationAttributeValues,
  haloStrengthFromAge,
} from "./star-annotations";
export type { GenerateStellarProfileOptions } from "./stellar-profile";
export {
  createStellarPaletteFromTemperature,
  createStellarSeededRandom,
  formatLuminositySolar,
  formatSpectralClassLabel,
  formatTemperatureK,
  formatVisualArchetypeLabel,
  generateStellarProfile,
  getStellarBaseColor,
} from "./stellar-profile";
export type {
  LandingProjectedStar,
  LandingStarHitTarget,
  LandingStarLodThresholds,
  LandingStarRenderBatches,
  LandingStarRenderItem,
  LandingStarRenderPlan,
  LandingStarRenderTier,
  LandingStarSpatialHash,
  LandingStarSpatialHashOptions,
} from "./landing-star-types";
export {
  DEFAULT_LANDING_STAR_LOD_THRESHOLDS,
  assignLandingStarRenderTier,
  buildLandingStarRenderPlan,
  classifyLandingStarRenderTier,
} from "./landing-star-lod";
export {
  buildLandingStarSpatialHash,
  findClosestLandingStarHitTarget,
  queryLandingStarSpatialHash,
} from "./landing-star-spatial-index";
