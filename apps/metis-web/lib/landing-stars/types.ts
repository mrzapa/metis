import type { StarVisualArchetype } from "./star-visual-archetype";

export type SeedInput = string | number;

export type StellarType =
  | "BLACK_HOLE"
  | "HYPERGIANT"
  | "NEUTRON_STAR"
  | "PRE_MAIN_SEQUENCE"
  | "PROTOSTAR"
  | "RED_GIANT"
  | "SUBGIANT"
  | "WHITE_DWARF"
  | "WOLF_RAYET"
  | "MAIN_SEQUENCE";

export type RgbColor = readonly [number, number, number];

export interface StellarPalette {
  accent: RgbColor;
  core: RgbColor;
  halo: RgbColor;
  rim: RgbColor;
  surface: RgbColor;
}

export interface StellarVisualProfile {
  asymmetryX: number;
  asymmetryY: number;
  bloomFactor: number;
  coronaIntensity: number;
  coreRadiusFactor: number;
  diffractionStrength: number;
  parallaxFactor: number;
  haloRadiusFactor: number;
  spikeAngle: number;
  spikeCount: number;
  spriteHardness: number;
  twinklePhase: number;
  twinkleSpeed: number;
}

export interface StellarProfile {
  baseColor: RgbColor;
  luminosityClass: string | null;
  luminositySolar: number;
  massSolar: number;
  palette: StellarPalette;
  radiusSolar: number;
  seed: string;
  seedHash: number;
  spectralClass: string;
  spectralFamily: string;
  spectralSubclass: number | null;
  stellarType: StellarType;
  temperatureK: number;
  visual: StellarVisualProfile;
  visualArchetype: StarVisualArchetype;
}
