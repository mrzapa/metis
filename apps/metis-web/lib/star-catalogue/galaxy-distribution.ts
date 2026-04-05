import { SeededRNG } from "./rng";

export interface GalaxyDistributionConfig {
  numArms: number;
  armWindingRate: number;
  coreRadius: number;
  diskFalloff: number;
}

/**
 * Generate a world-space position for a star within a galaxy.
 * Returns position in approximately [-1, 1] range with spiral arm structure.
 */
export function sampleGalaxyPosition(
  rng: SeededRNG,
  cfg: GalaxyDistributionConfig,
): { wx: number; wy: number; depthLayer: number } {
  const roll = rng.next();
  let wx: number;
  let wy: number;

  if (roll < 0.15) {
    // Galactic core: tight Gaussian blob
    const r = Math.abs(rng.gaussian()) * cfg.coreRadius;
    const theta = rng.next() * Math.PI * 2;
    wx = Math.cos(theta) * r;
    wy = Math.sin(theta) * r;
  } else if (roll < 0.85) {
    // Spiral arm
    const armIndex = rng.int(cfg.numArms);
    const armOffset = (armIndex / cfg.numArms) * Math.PI * 2;
    const rawRadius = -Math.log(1 - rng.next() * 0.9999) / cfg.diskFalloff;
    const r = Math.min(rawRadius, 1.0);
    const armAngle = armOffset + r * cfg.armWindingRate;
    const scatter = rng.range(-0.04, 0.04) * (0.5 + r);
    const theta = armAngle + scatter;
    wx = Math.cos(theta) * r;
    wy = Math.sin(theta) * r;
  } else {
    // Halo: uniform disk, low density
    const r = rng.next() * 0.9 + 0.05;
    const theta = rng.next() * Math.PI * 2;
    wx = Math.cos(theta) * r;
    wy = Math.sin(theta) * r;
  }

  // Depth layer loosely correlated with distance from centre
  const dist = Math.hypot(wx, wy);
  const depthLayer = 0.3 + rng.next() * 0.4 + dist * 0.3;

  return { wx, wy, depthLayer: Math.min(1, depthLayer) };
}
