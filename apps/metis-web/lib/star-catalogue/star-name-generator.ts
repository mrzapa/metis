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
 * Generate a star name from a SeededRNG instance and apparent magnitude.
 * Brighter stars (lower magnitude) get more prestigious designations.
 */
export function generateStarName(rng: SeededRNG, magnitude: number): string {
  if (magnitude < 2.5) {
    // Bayer designation: "Alpha Orionis"
    return `${rng.pick(GREEK)} ${rng.pick(CONSTELLATIONS_GENITIVE)}`;
  }
  if (magnitude < 4.5) {
    // Flamsteed-style: "47 Tauri"
    const num = rng.int(99) + 1;
    const constellation = rng.pick(CONSTELLATIONS_GENITIVE);
    return `${num} ${constellation}`;
  }
  // Henry Draper catalogue number
  const hd = rng.int(359083) + 1;
  return `HD ${hd}`;
}
