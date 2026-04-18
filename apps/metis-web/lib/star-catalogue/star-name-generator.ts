import { SeededRNG } from "./rng";

const GREEK = [
  "Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta",
  "Iota", "Kappa", "Lambda", "Mu", "Nu", "Xi", "Omicron", "Pi", "Rho",
  "Sigma", "Tau", "Upsilon", "Phi", "Chi", "Psi", "Omega",
] as const;

const CONSTELLATIONS_GENITIVE = [
  "Orionis", "Cygni", "Leonis", "Tauri", "Scorpii", "Aquilae", "Herculis",
  "Persei", "Cassiopeiae", "Ursae Majoris", "Ursae Minoris", "Draconis",
  "Lyrae", "Carinae", "Centauri", "Crucis", "Virginis", "Piscium",
  "Sagittarii", "Capricorni", "Aquarii", "Geminorum", "Cancri", "Arietis",
  "Librae", "Ophiuchi", "Serpentis", "Aurigae", "Bootis", "Coronae Borealis",
] as const;

/**
 * Naming tier per ADR 0006:
 *  - `field`: background decorative stars. No visible name.
 *  - `landmark`: faculty-constellation stars. Classical Bayer/Flamsteed/HD.
 *  - `user`: user-created content stars. User-supplied name.
 */
export type NameTier = "field" | "landmark" | "user";

/**
 * Classification of the produced name, surfaced to renderers so they can
 * style classical vs user names differently (and explain the Bayer
 * convention on classical-tier tooltips).
 */
export type NameKind = "classical" | "user" | null;

export interface GeneratedStarName {
  name: string | null;
  kind: NameKind;
}

export interface GenerateStarNameInput {
  tier: NameTier;
  /** Required for `landmark` tier — drives classical name generation. */
  rng?: SeededRNG;
  /** Required for `landmark` tier — selects Bayer / Flamsteed / HD form. */
  magnitude?: number;
  /** Used for `user` tier. Trimmed; empty strings are treated as absent. */
  userSuppliedName?: string | null;
}

/**
 * Generate a star name following the ADR 0006 tiered naming policy.
 *
 * Replaces the legacy magnitude-only `generateStarName(rng, magnitude)`
 * that applied classical astronomical names indiscriminately.
 */
export function generateStarName(input: GenerateStarNameInput): GeneratedStarName {
  switch (input.tier) {
    case "field":
      return { name: null, kind: null };
    case "landmark": {
      if (!input.rng || input.magnitude === undefined) {
        throw new Error("landmark tier requires rng and magnitude");
      }
      return {
        name: generateClassicalDesignation(input.rng, input.magnitude),
        kind: "classical",
      };
    }
    case "user": {
      const trimmed = input.userSuppliedName?.trim();
      if (trimmed) {
        return { name: trimmed, kind: "user" };
      }
      return { name: null, kind: null };
    }
  }
}

/**
 * Classical Bayer / Flamsteed / Henry Draper designation.
 *
 * Exported so legacy caller sites that still need a procedural fallback
 * (user stars created without an explicit label) can keep generating a
 * name string. Per ADR 0006 the naming policy is to only apply classical
 * designations to faculty-constellation landmarks; remaining legacy uses
 * are temporary and expected to disappear once the Observatory naming
 * UI lands in a later M02 phase.
 */
export function generateClassicalDesignation(rng: SeededRNG, magnitude: number): string {
  if (magnitude < 2.5) {
    return `${rng.pick(GREEK)} ${rng.pick(CONSTELLATIONS_GENITIVE)}`;
  }
  if (magnitude < 4.5) {
    const num = rng.int(99) + 1;
    const constellation = rng.pick(CONSTELLATIONS_GENITIVE);
    return `${num} ${constellation}`;
  }
  const hd = rng.int(359083) + 1;
  return `HD ${hd}`;
}
