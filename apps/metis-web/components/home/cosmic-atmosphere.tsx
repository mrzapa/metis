"use client";

/**
 * CosmicAtmosphere — fixed full-viewport overlay layer that intensifies
 * with zoom. Two stacked effects:
 *
 *   1. Vignette: a radial gradient transparent in the centre, fading
 *      to a dark frame at the corners. Intensity ramps with zoom so
 *      diving deeper into the cosmos visually frames the focal point.
 *   2. Chromatic glow: a subtle warm/cool radial bloom at viewport
 *      centre that breathes in/out with zoom. Reads as atmospheric
 *      scatter without committing to a full lens-flare aesthetic
 *      (the user has previously rejected hard lens-flare).
 *
 * Pure presentational layer — no animation loop, no canvas. The
 * `zoomFactor` prop drives the CSS-variable intensities so updates
 * are cheap.
 */

import { useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

export interface CosmicAtmosphereProps {
  /** Current camera zoom factor — 1.0 = default, >1 = zoomed in. */
  zoomFactor: number;
  className?: string;
}

const MIN_ZOOM = 1;
const MAX_ZOOM_FOR_INTENSITY = 60;

export function CosmicAtmosphere({ zoomFactor, className }: CosmicAtmosphereProps) {
  const reducedMotion = useReducedMotion();

  // Map zoom (1 → 60+) onto a 0..1 intensity. Use a sub-linear curve so
  // the effect is felt early and saturates rather than going wild at
  // extreme zooms.
  const z = Math.max(MIN_ZOOM, zoomFactor);
  const tNorm = Math.min(1, (z - MIN_ZOOM) / (MAX_ZOOM_FOR_INTENSITY - MIN_ZOOM));
  const intensity = reducedMotion ? Math.min(0.3, tNorm) : Math.pow(tNorm, 0.55);

  // Vignette: outer dimming up to 55% at full intensity.
  const vignetteAlpha = 0.18 + intensity * 0.37;
  // Glow: warm haze brightens through the middle range, then plateaus.
  const glowAlpha = 0.0 + intensity * 0.18;

  return (
    <div
      className={cn(
        "pointer-events-none fixed inset-0 z-[2]",
        className,
      )}
      data-testid="cosmic-atmosphere"
      data-intensity={intensity.toFixed(3)}
      aria-hidden="true"
    >
      {/* Vignette frame — normal blend so the dark gradient actually
          darkens. Sits underneath the glow so the glow can lift the
          centre back up. */}
      <div
        className="absolute inset-0 transition-opacity duration-300"
        style={{
          background:
            `radial-gradient(ellipse 80% 90% at 50% 50%,`
            + ` transparent 38%,`
            + ` rgba(2, 5, 12, ${vignetteAlpha * 0.5}) 78%,`
            + ` rgba(0, 1, 4, ${vignetteAlpha}) 100%)`,
        }}
      />
      {/* Central atmospheric glow — screen blend so it adds light
          rather than overlaying colour. Warm + cool radial bloom
          read as scatter without committing to lens-flare. */}
      <div
        className="absolute inset-0 transition-opacity duration-300"
        style={{
          background:
            `radial-gradient(circle at 50% 50%,`
            + ` rgba(255, 213, 168, ${glowAlpha * 0.55}) 0%,`
            + ` rgba(120, 145, 220, ${glowAlpha * 0.32}) 25%,`
            + ` transparent 55%)`,
          mixBlendMode: "screen",
        }}
      />
    </div>
  );
}
