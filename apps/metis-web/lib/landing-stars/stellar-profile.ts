import type {
  RgbColor,
  SeedInput,
  StellarPalette,
  StellarProfile,
  StellarType,
  StellarVisualProfile,
} from "./types";
import { selectStarVisualArchetype, type StarContentType } from "./star-visual-archetype";

export interface GenerateStellarProfileOptions {
  /**
   * What kind of content the star represents (document, podcast, video, …).
   * Drives the star's visualArchetype per ADR 0006's content-type mapping.
   * When omitted, the archetype falls back to `main_sequence`.
   */
  contentType?: StarContentType | null;
}

interface WeightedChoice<T> {
  readonly weight: number;
  readonly value: T;
}

const TWO_PI = Math.PI * 2;
const MIN_TEMPERATURE_K = 1200;
const MAX_TEMPERATURE_K = 50000;

const STELLAR_TYPE_CHOICES: ReadonlyArray<WeightedChoice<StellarType>> = [
  { value: "MAIN_SEQUENCE", weight: 82 },
  { value: "WHITE_DWARF", weight: 8 },
  { value: "SUBGIANT", weight: 2.5 },
  { value: "RED_GIANT", weight: 2 },
  { value: "PRE_MAIN_SEQUENCE", weight: 1.8 },
  { value: "PROTOSTAR", weight: 1.2 },
  { value: "NEUTRON_STAR", weight: 1 },
  { value: "WOLF_RAYET", weight: 0.8 },
  { value: "HYPERGIANT", weight: 0.5 },
  { value: "BLACK_HOLE", weight: 0.2 },
];

const MAIN_SEQUENCE_FAMILY_CHOICES = [
  { value: "M", weight: 72 },
  { value: "K", weight: 14 },
  { value: "G", weight: 8 },
  { value: "F", weight: 3 },
  { value: "A", weight: 2.2 },
  { value: "B", weight: 0.6 },
  { value: "O", weight: 0.2 },
] as const;
type MainSequenceFamily = (typeof MAIN_SEQUENCE_FAMILY_CHOICES)[number]["value"];

const WHITE_DWARF_SUBTYPES = ["DA", "DB", "DC", "DO", "DZ", "DQ"] as const;
const WOLF_RAYET_SUBTYPES = ["WN", "WC", "WO"] as const;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function clampByte(value: number): number {
  return Math.round(clamp(value, 0, 255));
}

function normalizeSeed(seed: SeedInput): string {
  if (typeof seed === "number") {
    if (!Number.isFinite(seed)) {
      return "0";
    }
    return String(seed);
  }

  return seed;
}

function hashSeed(input: string): number {
  let hash = 0x811c9dc5;

  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }

  return hash >>> 0;
}

function createSeededRandom(seed: SeedInput): () => number {
  let state = hashSeed(normalizeSeed(seed)) || 0x6d2b79f5;

  return () => {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return (state >>> 0) / 0x100000000;
  };
}

function chooseWeighted<T>(choices: ReadonlyArray<WeightedChoice<T>>, random: () => number): T {
  let total = 0;
  for (const choice of choices) {
    total += choice.weight;
  }

  let roll = random() * total;
  for (const choice of choices) {
    if (roll < choice.weight) {
      return choice.value;
    }
    roll -= choice.weight;
  }

  return choices[choices.length - 1].value;
}

function chooseIndexed<T extends string>(values: readonly T[], random: () => number): T {
  return values[Math.floor(random() * values.length) % values.length];
}

function lerp(from: number, to: number, amount: number): number {
  return from + (to - from) * amount;
}

function easeInOut(amount: number): number {
  const clamped = clamp(amount, 0, 1);
  return clamped * clamped * (3 - 2 * clamped);
}

function mixColors(left: RgbColor, right: RgbColor, amount: number): RgbColor {
  const t = clamp(amount, 0, 1);
  return [
    clampByte(lerp(left[0], right[0], t)),
    clampByte(lerp(left[1], right[1], t)),
    clampByte(lerp(left[2], right[2], t)),
  ];
}

function tintColor(color: RgbColor, red: number, green: number, blue: number): RgbColor {
  return [
    clampByte(color[0] + red),
    clampByte(color[1] + green),
    clampByte(color[2] + blue),
  ];
}

function temperatureToRgb(temperatureK: number): RgbColor {
  const temperature = clamp(temperatureK, 1000, 40000) / 100;
  let red: number;
  let green: number;
  let blue: number;

  if (temperature <= 66) {
    red = 255;
    green = 99.4708025861 * Math.log(temperature) - 161.1195681661;

    blue = temperature <= 19
      ? 0
      : 138.5177312231 * Math.log(temperature - 10) - 305.0447927307;
  } else {
    red = 329.698727446 * Math.pow(temperature - 60, -0.1332047592);
    green = 288.1221695283 * Math.pow(temperature - 60, -0.0755148492);
    blue = 255;
  }

  return [clampByte(red), clampByte(green), clampByte(blue)];
}

function pickMainSequenceFamily(random: () => number): MainSequenceFamily {
  return chooseWeighted(MAIN_SEQUENCE_FAMILY_CHOICES, random);
}

function buildMainSequenceProfile(random: () => number) {
  const family = pickMainSequenceFamily(random);
  const subclass = Math.floor(random() * 10) % 10;
  const hotFraction = 1 - subclass / 9;

  const familyRanges: Record<MainSequenceFamily, { mass: [number, number]; radius: [number, number]; luminosity: [number, number]; temperature: [number, number] }> = {
    O: { mass: [16, 60], radius: [6.5, 15], luminosity: [30000, 1000000], temperature: [30000, 50000] },
    B: { mass: [2.1, 16], radius: [1.8, 6.5], luminosity: [25, 30000], temperature: [10000, 30000] },
    A: { mass: [1.4, 2.1], radius: [1.4, 1.8], luminosity: [5, 25], temperature: [7500, 10000] },
    F: { mass: [1.04, 1.4], radius: [1.15, 1.4], luminosity: [1.5, 5], temperature: [6000, 7500] },
    G: { mass: [0.8, 1.04], radius: [0.85, 1.15], luminosity: [0.6, 1.5], temperature: [5200, 6000] },
    K: { mass: [0.45, 0.8], radius: [0.65, 0.85], luminosity: [0.08, 0.6], temperature: [3700, 5200] },
    M: { mass: [0.08, 0.45], radius: [0.1, 0.65], luminosity: [0.001, 0.08], temperature: [2400, 3700] },
  };

  const ranges = familyRanges[family];
  const massSolar = lerp(ranges.mass[0], ranges.mass[1], easeInOut(random()));
  const radiusSolar = lerp(ranges.radius[0], ranges.radius[1], easeInOut(random()));
  const luminositySolar = lerp(ranges.luminosity[0], ranges.luminosity[1], easeInOut(random()));
  const temperatureK = lerp(ranges.temperature[1], ranges.temperature[0], easeInOut(hotFraction));
  const luminosityClass = "V";
  const spectralClass = `${family}${subclass}${luminosityClass}`;

  return {
    family,
    luminosityClass,
    luminositySolar,
    massSolar,
    radiusSolar,
    spectralClass,
    spectralSubclass: subclass,
    temperatureK,
  };
}

function buildWhiteDwarfProfile(random: () => number) {
  const subtype = chooseIndexed(WHITE_DWARF_SUBTYPES, random);
  const temperatureK = lerp(8000, 40000, easeInOut(random()));
  const luminositySolar = lerp(0.0005, 0.03, easeInOut(random()));
  const massSolar = lerp(0.45, 1.25, easeInOut(random()));
  const radiusSolar = lerp(0.008, 0.02, easeInOut(random()));

  return {
    family: "D",
    luminosityClass: "VII",
    luminositySolar,
    massSolar,
    radiusSolar,
    spectralClass: subtype,
    spectralSubclass: null,
    temperatureK,
  };
}

function buildSubgiantProfile(random: () => number) {
  const base = buildMainSequenceProfile(random);
  const family = base.temperatureK >= 6000 ? "F" : base.temperatureK >= 5200 ? "G" : "K";
  const spectralClass = `${family}${base.spectralSubclass ?? 0}IV`;

  return {
    family,
    luminosityClass: "IV",
    luminositySolar: lerp(1.8, 8, easeInOut(random())),
    massSolar: lerp(0.9, 2.5, easeInOut(random())),
    radiusSolar: lerp(1.4, 4.2, easeInOut(random())),
    spectralClass,
    spectralSubclass: base.spectralSubclass,
    temperatureK: lerp(5000, 7000, easeInOut(random())),
  };
}

function buildRedGiantProfile(random: () => number) {
  const family = chooseIndexed(["K", "M"] as const, random);
  const spectralSubclass = Math.floor(random() * 10) % 10;

  return {
    family,
    luminosityClass: "III",
    luminositySolar: lerp(80, 2000, easeInOut(random())),
    massSolar: lerp(0.8, 8, easeInOut(random())),
    radiusSolar: lerp(10, 80, easeInOut(random())),
    spectralClass: `${family}${spectralSubclass}III`,
    spectralSubclass,
    temperatureK: lerp(3200, 5000, easeInOut(random())),
  };
}

function buildPreMainSequenceProfile(random: () => number) {
  const family = chooseIndexed(["K", "G", "A"] as const, random);
  const spectralSubclass = Math.floor(random() * 10) % 10;

  return {
    family,
    luminosityClass: "V",
    luminositySolar: lerp(0.05, 50, easeInOut(random())),
    massSolar: lerp(0.2, 8, easeInOut(random())),
    radiusSolar: lerp(1, 8, easeInOut(random())),
    spectralClass: `${family}${spectralSubclass}PMS`,
    spectralSubclass,
    temperatureK: lerp(3000, 8000, easeInOut(random())),
  };
}

function buildProtostarProfile(random: () => number) {
  const family = chooseIndexed(["M", "K"] as const, random);
  const spectralSubclass = Math.floor(random() * 10) % 10;

  return {
    family,
    luminosityClass: "I",
    luminositySolar: lerp(0.01, 20, easeInOut(random())),
    massSolar: lerp(0.1, 8, easeInOut(random())),
    radiusSolar: lerp(2, 20, easeInOut(random())),
    spectralClass: `${family}${spectralSubclass}PROTO`,
    spectralSubclass,
    temperatureK: lerp(1500, 4500, easeInOut(random())),
  };
}

function buildWolfRayetProfile(random: () => number) {
  const subtype = chooseIndexed(WOLF_RAYET_SUBTYPES, random);
  const family = subtype === "WO" ? "O" : "W";

  return {
    family,
    luminosityClass: "I",
    luminositySolar: lerp(20000, 500000, easeInOut(random())),
    massSolar: lerp(5, 40, easeInOut(random())),
    radiusSolar: lerp(0.5, 10, easeInOut(random())),
    spectralClass: subtype,
    spectralSubclass: null,
    temperatureK: lerp(30000, 200000, easeInOut(random())),
  };
}

function buildHypergiantProfile(random: () => number) {
  const family = chooseIndexed(["O", "B", "A"] as const, random);
  const spectralSubclass = Math.floor(random() * 10) % 10;

  return {
    family,
    luminosityClass: "I",
    luminositySolar: lerp(300000, 1000000, easeInOut(random())),
    massSolar: lerp(20, 120, easeInOut(random())),
    radiusSolar: lerp(50, 500, easeInOut(random())),
    spectralClass: `${family}${spectralSubclass}Ia`,
    spectralSubclass,
    temperatureK: lerp(3500, 20000, easeInOut(random())),
  };
}

function buildNeutronStarProfile(random: () => number) {
  const spectralClass = random() < 0.75 ? "P" : "NS";

  return {
    family: "NS",
    luminosityClass: null,
    luminositySolar: lerp(0.001, 0.5, easeInOut(random())),
    massSolar: lerp(1.1, 2.3, easeInOut(random())),
    radiusSolar: lerp(0.000003, 0.000005, easeInOut(random())),
    spectralClass,
    spectralSubclass: null,
    temperatureK: lerp(600000, 2000000, easeInOut(random())),
  };
}

function buildBlackHoleProfile(random: () => number) {
  return {
    family: "BH",
    luminosityClass: null,
    luminositySolar: lerp(0.000001, 0.01, easeInOut(random())),
    massSolar: lerp(3, 50, easeInOut(random())),
    radiusSolar: lerp(0.000001, 0.00002, easeInOut(random())),
    spectralClass: "BH",
    spectralSubclass: null,
    temperatureK: 2.7,
  };
}

function chooseStellarBaseProfile(random: () => number) {
  const stellarType = chooseWeighted(STELLAR_TYPE_CHOICES, random);

  switch (stellarType) {
    case "WHITE_DWARF":
      return { stellarType, ...buildWhiteDwarfProfile(random) };
    case "SUBGIANT":
      return { stellarType, ...buildSubgiantProfile(random) };
    case "RED_GIANT":
      return { stellarType, ...buildRedGiantProfile(random) };
    case "PRE_MAIN_SEQUENCE":
      return { stellarType, ...buildPreMainSequenceProfile(random) };
    case "PROTOSTAR":
      return { stellarType, ...buildProtostarProfile(random) };
    case "NEUTRON_STAR":
      return { stellarType, ...buildNeutronStarProfile(random) };
    case "WOLF_RAYET":
      return { stellarType, ...buildWolfRayetProfile(random) };
    case "HYPERGIANT":
      return { stellarType, ...buildHypergiantProfile(random) };
    case "BLACK_HOLE":
      return { stellarType, ...buildBlackHoleProfile(random) };
    case "MAIN_SEQUENCE":
    default:
      return { stellarType, ...buildMainSequenceProfile(random) };
  }
}

function buildBaseColor(
  stellarType: StellarType,
  temperatureK: number,
  random: () => number,
): RgbColor {
  const bodyColor = temperatureToRgb(temperatureK);
  const coolBias = mixColors(bodyColor, [255, 214, 170], 0.22);
  const hotBias = mixColors(bodyColor, [235, 244, 255], 0.2);
  const whiteBias = mixColors(hotBias, [255, 255, 255], 0.45);

  switch (stellarType) {
    case "RED_GIANT":
    case "PROTOSTAR":
      return tintColor(coolBias, 10, -8, -12);
    case "SUBGIANT":
    case "PRE_MAIN_SEQUENCE":
      return mixColors(coolBias, hotBias, 0.4);
    case "WHITE_DWARF":
      return mixColors(whiteBias, hotBias, 0.25);
    case "NEUTRON_STAR":
      return mixColors(hotBias, [212, 244, 255], 0.35);
    case "WOLF_RAYET":
      return mixColors(hotBias, [204, 255, 240], 0.45);
    case "HYPERGIANT":
      return mixColors(coolBias, [255, 170, 150], 0.4);
    case "BLACK_HOLE":
      return [12, 14, 20];
    case "MAIN_SEQUENCE":
    default: {
      const bias = random() * 0.18;
      return mixColors(bodyColor, whiteBias, bias);
    }
  }
}

function buildPalette(
  stellarType: StellarType,
  temperatureK: number,
  baseColor: RgbColor,
): StellarPalette {
  const temperatureFactor = clamp((temperatureK - MIN_TEMPERATURE_K) / (MAX_TEMPERATURE_K - MIN_TEMPERATURE_K), 0, 1);
  const hotCore = mixColors(baseColor, [255, 255, 255], 0.45 + temperatureFactor * 0.35);
  const coolHalo = mixColors(baseColor, [104, 142, 214], 0.18 + (1 - temperatureFactor) * 0.25);
  const warmAccent = mixColors(baseColor, [255, 196, 122], 0.25);
  const darkRim = mixColors(baseColor, [8, 10, 18], 0.28);

  switch (stellarType) {
    case "BLACK_HOLE":
      return {
        accent: [28, 34, 48],
        core: [0, 0, 0],
        halo: [20, 24, 35],
        rim: [8, 10, 16],
        surface: [4, 5, 8],
      };
    case "NEUTRON_STAR":
      return {
        accent: mixColors(baseColor, [177, 255, 255], 0.35),
        core: hotCore,
        halo: mixColors(coolHalo, [193, 245, 255], 0.5),
        rim: darkRim,
        surface: mixColors(baseColor, [244, 255, 255], 0.18),
      };
    case "WHITE_DWARF":
      return {
        accent: mixColors(baseColor, [255, 255, 255], 0.3),
        core: hotCore,
        halo: mixColors(coolHalo, [240, 248, 255], 0.5),
        rim: darkRim,
        surface: mixColors(baseColor, [255, 250, 240], 0.14),
      };
    case "RED_GIANT":
    case "PROTOSTAR":
      return {
        accent: mixColors(baseColor, [255, 168, 105], 0.3),
        core: mixColors(baseColor, [255, 234, 214], 0.42),
        halo: mixColors(baseColor, [255, 152, 87], 0.32),
        rim: darkRim,
        surface: mixColors(baseColor, [255, 222, 188], 0.15),
      };
    case "HYPERGIANT":
      return {
        accent: mixColors(baseColor, [255, 217, 167], 0.34),
        core: mixColors(baseColor, [255, 252, 246], 0.55),
        halo: mixColors(baseColor, [255, 174, 146], 0.28),
        rim: darkRim,
        surface: mixColors(baseColor, [255, 241, 225], 0.18),
      };
    case "WOLF_RAYET":
      return {
        accent: mixColors(baseColor, [210, 255, 242], 0.4),
        core: mixColors(baseColor, [255, 255, 255], 0.48),
        halo: mixColors(baseColor, [155, 255, 235], 0.35),
        rim: darkRim,
        surface: mixColors(baseColor, [232, 255, 250], 0.2),
      };
    case "SUBGIANT":
    case "PRE_MAIN_SEQUENCE":
      return {
        accent: warmAccent,
        core: hotCore,
        halo: coolHalo,
        rim: darkRim,
        surface: mixColors(baseColor, [255, 237, 208], 0.16),
      };
    case "MAIN_SEQUENCE":
    default:
      return {
        accent: warmAccent,
        core: hotCore,
        halo: coolHalo,
        rim: darkRim,
        surface: mixColors(baseColor, [255, 244, 226], 0.08),
      };
  }
}

function buildVisualProfile(
  stellarType: StellarType,
  temperatureK: number,
  luminositySolar: number,
  random: () => number,
): StellarVisualProfile {
  const temperatureFactor = clamp((temperatureK - MIN_TEMPERATURE_K) / (MAX_TEMPERATURE_K - MIN_TEMPERATURE_K), 0, 1);
  const luminosityFactor = clamp((Math.log10(Math.max(luminositySolar, 0.000001)) + 3) / 9, 0, 1);
  const compactFactor =
    stellarType === "WHITE_DWARF" || stellarType === "NEUTRON_STAR" || stellarType === "BLACK_HOLE"
      ? 1
      : 0;
  const giantFactor =
    stellarType === "RED_GIANT" || stellarType === "HYPERGIANT" || stellarType === "WOLF_RAYET"
      ? 1
      : 0;
  const youngFactor =
    stellarType === "PROTOSTAR" || stellarType === "PRE_MAIN_SEQUENCE"
      ? 1
      : 0;

  const coreRadiusFactor = clamp(
    0.12 + temperatureFactor * 0.12 + giantFactor * 0.08 - compactFactor * 0.03,
    0.06,
    0.44,
  );
  const haloRadiusFactor = clamp(
    1.6 + luminosityFactor * 2.4 + giantFactor * 1.7 + youngFactor * 0.6 + compactFactor * 0.2,
    1.25,
    7.5,
  );
  const bloomFactor = clamp(
    0.7 + luminosityFactor * 1.2 + giantFactor * 0.6 + youngFactor * 0.35 - compactFactor * 0.1,
    0.5,
    2.6,
  );
  const coronaIntensity = clamp(
    0.18 + temperatureFactor * 0.55 + giantFactor * 0.16 + compactFactor * 0.22,
    0.12,
    1,
  );
  const diffractionStrength = clamp(
    0.12 + temperatureFactor * 0.65 + compactFactor * 0.25 + giantFactor * 0.2,
    0,
    1,
  );
  const spikeCount =
    stellarType === "BLACK_HOLE" ? 0
      : stellarType === "NEUTRON_STAR" ? 6
        : stellarType === "WHITE_DWARF" ? 4
          : giantFactor > 0 ? 4
            : temperatureFactor > 0.65 ? 4
              : 2;
  const spriteHardness = clamp(0.82 + temperatureFactor * 0.12 + compactFactor * 0.1 - giantFactor * 0.12, 0.35, 1);
  const parallaxFactor = clamp(
    0.0025 + (1 - temperatureFactor) * 0.004 + giantFactor * 0.0015 + youngFactor * 0.0008,
    0.0015,
    0.02,
  );

  return {
    asymmetryX: (random() * 2 - 1) * (0.08 + giantFactor * 0.12 + youngFactor * 0.08),
    asymmetryY: (random() * 2 - 1) * (0.08 + giantFactor * 0.1 + youngFactor * 0.08),
    bloomFactor,
    coronaIntensity,
    coreRadiusFactor,
    diffractionStrength,
    parallaxFactor,
    haloRadiusFactor,
    spikeAngle: random() * Math.PI,
    spikeCount,
    spriteHardness,
    twinklePhase: random() * TWO_PI,
    twinkleSpeed: lerp(0.00025, 0.0035, easeInOut(random())),
  };
}

export function generateStellarProfile(
  seed: SeedInput,
  options?: GenerateStellarProfileOptions,
): StellarProfile {
  const random = createSeededRandom(seed);
  const base = chooseStellarBaseProfile(random);
  const baseColor = buildBaseColor(base.stellarType, base.temperatureK, random);
  const palette = buildPalette(base.stellarType, base.temperatureK, baseColor);
  const visual = buildVisualProfile(base.stellarType, base.temperatureK, base.luminositySolar, random);

  return {
    baseColor,
    luminosityClass: base.luminosityClass,
    luminositySolar: base.luminositySolar,
    massSolar: base.massSolar,
    palette,
    radiusSolar: base.radiusSolar,
    seed: normalizeSeed(seed),
    seedHash: hashSeed(normalizeSeed(seed)),
    spectralClass: base.spectralClass,
    spectralFamily: base.family,
    spectralSubclass: base.spectralSubclass,
    stellarType: base.stellarType,
    temperatureK: Math.round(base.temperatureK),
    visual,
    visualArchetype: selectStarVisualArchetype(options?.contentType),
  };
}

export function createStellarPaletteFromTemperature(temperatureK: number): StellarPalette {
  const baseColor = temperatureToRgb(temperatureK);

  return buildPalette("MAIN_SEQUENCE", temperatureK, baseColor);
}

export function createStellarSeededRandom(seed: SeedInput): () => number {
  return createSeededRandom(seed);
}

export function getStellarBaseColor(temperatureK: number): RgbColor {
  return temperatureToRgb(temperatureK);
}

/**
 * Identity-panel formatters (M02 Phase 7.1).
 *
 * These turn raw `StellarProfile` numeric fields into human-readable strings
 * for the Observatory character sheet. They stay in `stellar-profile.ts` so
 * the unit tests don't have to cross into DOM-rendered component territory.
 *
 * Each formatter returns a plain string with no trailing unit markup — the
 * caller owns layout (e.g. rendering "K" or "L☉" as a subscript-style suffix).
 */
export function formatTemperatureK(temperatureK: number): string {
  if (!Number.isFinite(temperatureK)) {
    return "—";
  }
  const rounded = Math.round(temperatureK);
  // Thousands separator keeps 12,000 K readable. No fractional K — surface
  // temperature precision under 1 K is noise at this scale.
  return rounded.toLocaleString("en-US");
}

export function formatLuminositySolar(luminositySolar: number): string {
  if (!Number.isFinite(luminositySolar) || luminositySolar <= 0) {
    return "—";
  }
  // L☉ spans ~10⁻⁵ (brown dwarfs) to ~10⁶ (hypergiants). Scientific notation
  // past 10,000 and below 0.01 keeps the panel from showing "1e-5" as
  // "0.00001". Otherwise fixed-point with enough significance.
  if (luminositySolar >= 10000 || luminositySolar < 0.01) {
    return luminositySolar.toExponential(2);
  }
  if (luminositySolar >= 100) {
    return luminositySolar.toFixed(0);
  }
  if (luminositySolar >= 10) {
    return luminositySolar.toFixed(1);
  }
  return luminositySolar.toFixed(2);
}

/**
 * Convert the canonical spectral family + subclass + luminosity class into the
 * classical compact form — e.g. "G2 V", "M5 III", "O9 Ia". Falls back to the
 * spectralClass field if the composite parts are missing.
 */
export function formatSpectralClassLabel(profile: StellarProfile): string {
  const subclassText = profile.spectralSubclass != null
    ? String(profile.spectralSubclass)
    : "";
  const head = `${profile.spectralFamily}${subclassText}`.trim();
  const tail = profile.luminosityClass ?? "";
  if (head && tail) {
    return `${head} ${tail}`;
  }
  return head || profile.spectralClass || "—";
}

const VISUAL_ARCHETYPE_LABELS: Record<string, string> = {
  main_sequence: "Main sequence",
  pulsar: "Pulsar",
  quasar: "Quasar",
  brown_dwarf: "Brown dwarf",
  red_giant: "Red giant",
  binary: "Binary",
  nebula: "Nebula",
  black_hole: "Black hole",
  comet: "Comet",
  constellation: "Constellation",
  variable: "Variable",
  wolf_rayet: "Wolf-Rayet",
};

/**
 * Pretty label for a {@link StarVisualArchetype}. The snake_case ids are fine
 * as an ABI / internal enum but look noisy in a user-facing panel.
 */
export function formatVisualArchetypeLabel(archetype: string | null | undefined): string {
  if (!archetype) {
    return "Main sequence";
  }
  return VISUAL_ARCHETYPE_LABELS[archetype] ?? archetype.replace(/_/g, " ");
}
