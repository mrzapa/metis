import type { StarVisualArchetype } from "./star-visual-archetype";

export type LandingStarRenderTier = "point" | "sprite" | "hero" | "closeup";

export interface LandingProjectedStar {
  id: string;
  x: number;
  y: number;
  apparentSize: number;
  brightness: number;
  /**
   * Visual template driving closeup-tier rendering per ADR 0006.
   * Optional so callers that don't care (e.g. pure-procedural field
   * stars) can omit it; omitted = `main_sequence` at render time.
   */
  visualArchetype?: StarVisualArchetype;
}

export interface LandingStarHitTarget extends LandingProjectedStar {
  hitRadius: number;
}

export interface LandingStarLodThresholds {
  heroBrightness?: number;
  heroSizePx?: number;
  heroZoomFactor?: number;
  maxHeroCount?: number;
  spriteBrightness?: number;
  spriteSizePx?: number;
  spriteZoomFactor?: number;
}

export type LandingStarRenderItem<TStar extends LandingProjectedStar = LandingProjectedStar> =
  TStar & {
    renderTier: LandingStarRenderTier;
  };

export interface LandingStarRenderBatches<TStar extends LandingProjectedStar = LandingProjectedStar> {
  closeup: Array<LandingStarRenderItem<TStar>>;
  hero: Array<LandingStarRenderItem<TStar>>;
  point: Array<LandingStarRenderItem<TStar>>;
  sprite: Array<LandingStarRenderItem<TStar>>;
}

export interface LandingStarRenderPlan<TStar extends LandingProjectedStar = LandingProjectedStar> {
  batches: LandingStarRenderBatches<TStar>;
  tierCounts: Record<LandingStarRenderTier, number>;
}

export interface LandingStarSpatialHashOptions {
  cellSize?: number;
  queryPaddingPx?: number;
}

export interface LandingStarSpatialHash<TStar extends LandingStarHitTarget = LandingStarHitTarget> {
  cellSize: number;
  cells: Map<string, Array<TStar>>;
  maxHitRadius: number;
  starCount: number;
}
