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

export interface LandingStarfieldFocusedStar {
  screenX: number;      // CSS pixels from viewport left
  screenY: number;      // CSS pixels from viewport top
  focusStrength: number; // 0→1
  profile: StellarProfile;
}

export interface LandingStarfieldFrame {
  focusedStar?: LandingStarfieldFocusedStar | null;
  height: number;
  revision: number;
  stars: LandingWebglStar[];
  width: number;
  zoomScale: number;
}
