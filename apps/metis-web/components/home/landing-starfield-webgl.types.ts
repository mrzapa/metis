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
}
