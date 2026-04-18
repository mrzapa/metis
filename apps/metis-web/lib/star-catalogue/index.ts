export type {
  CatalogueStar,
  CatalogueSector,
  SectorKey,
  StarCatalogueConfig,
} from "./types";
export { DEFAULT_CATALOGUE_CONFIG } from "./types";
export { fnv1a32, SeededRNG } from "./rng";
export type {
  GeneratedStarName,
  GenerateStarNameInput,
  NameKind,
  NameTier,
} from "./star-name-generator";
export {
  generateClassicalDesignation,
  generateStarName,
} from "./star-name-generator";
export { sampleGalaxyPosition, galaxyDensityFactor } from "./galaxy-distribution";
export type { GalaxyDistributionConfig } from "./galaxy-distribution";
export { StarCatalogue } from "./star-catalogue";
