/**
 * Type-only exports for landing-starfield-webgl.tsx.
 *
 * Kept in a separate file so page.tsx can import the types without pulling in
 * Three.js (which is imported by the component itself and deferred via
 * next/dynamic).
 */

import type { LandingStarRenderTier } from "@/lib/landing-stars/landing-star-types";
import type { StellarProfile } from "@/lib/landing-stars/types";

export type { LandingStarRenderTier };

export interface LandingWebglStar {
  addable: boolean;
  apparentSize: number;
  brightness: number;
  id: string;
  profile: StellarProfile;
  renderTier: LandingStarRenderTier;
  x: number;
  y: number;
}

export interface LandingStarfieldFrame {
  height: number;
  revision: number;
  stars: LandingWebglStar[];
  width: number;
  zoomScale: number;
  /**
   * Dive focus centre in screen-space pixels — the projected location of the
   * focused star, used to drive depth-of-field falloff around it. When
   * `focusStrength === 0`, the values are ignored by the shader.
   */
  focusCenterX?: number;
  focusCenterY?: number;
  /** 0 when not in a dive; 1 at full dive. */
  focusStrength?: number;
  /** Pixel radius around the focus centre kept sharp (no DoF). */
  focusRadius?: number;
  /** Pixel width over which DoF ramps in from `focusRadius` outward. */
  focusFalloff?: number;
  /**
   * Mouse-driven parallax offset in shader-space pixels. The shader
   * subtracts this scaled by tier (field full, sprite half, hero
   * quarter, closeup zero) so the cursor's position from viewport
   * centre fakes a 3D parallax effect. Both axes default to 0.
   */
  mouseParallaxX?: number;
  mouseParallaxY?: number;
  /**
   * M02 Phase 7.3 — respect `prefers-reduced-motion: reduce`. When true, the
   * WebGL shader freezes its `uTime` uniform so twinkle, archetype pulsation,
   * and Phase 6 satellite orbits all halt. Callers update this flag in sync
   * with the OS media query (see `app/page.tsx`). Defaults to `false` so
   * existing callers keep their motion.
   */
  reducedMotion?: boolean;
}
