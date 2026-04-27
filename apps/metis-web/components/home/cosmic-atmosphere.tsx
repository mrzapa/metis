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

import { useEffect, useRef, type MutableRefObject } from "react";
import { useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

export interface CosmicAtmosphereFocusFrame {
  centerX: number;
  centerY: number;
  strength: number;
}

export interface CosmicAtmosphereProps {
  /** Current camera zoom factor — 1.0 = default, >1 = zoomed in. */
  zoomFactor: number;
  /**
   * Optional ref to a focus-frame struct that the parent updates each
   * RAF tick. When supplied and `focusFrameRef.current.strength > 0.05`
   * an additional starlight bloom is rendered at the focus centre,
   * tracking the position smoothly without driving React re-renders.
   */
  focusFrameRef?: MutableRefObject<CosmicAtmosphereFocusFrame> | null;
  className?: string;
}

const MIN_ZOOM = 1;
const MAX_ZOOM_FOR_INTENSITY = 60;

export function CosmicAtmosphere({
  zoomFactor,
  focusFrameRef = null,
  className,
}: CosmicAtmosphereProps) {
  const reducedMotion = useReducedMotion();
  const focusBloomRef = useRef<HTMLDivElement | null>(null);

  // Per-frame focus bloom: read from the ref every animation frame and
  // imperatively update the bloom div's background. Bypasses React
  // re-renders so the bloom can track sub-frame focus updates without
  // perf cost.
  useEffect(() => {
    if (!focusFrameRef) return;
    const node = focusBloomRef.current;
    if (!node) return;
    let raf = 0;
    let lastApplied = "";
    const tick = () => {
      raf = requestAnimationFrame(tick);
      const f = focusFrameRef.current;
      const active =
        f.strength > 0.05
        && Number.isFinite(f.centerX)
        && Number.isFinite(f.centerY);
      if (!active) {
        if (lastApplied !== "idle") {
          node.style.opacity = "0";
          lastApplied = "idle";
        }
        return;
      }
      const z = Math.max(MIN_ZOOM, zoomFactor);
      const tNorm = Math.min(1, (z - MIN_ZOOM) / (MAX_ZOOM_FOR_INTENSITY - MIN_ZOOM));
      const intensity = reducedMotion
        ? Math.min(0.3, tNorm)
        : Math.pow(tNorm, 0.55);
      const alpha = reducedMotion
        ? Math.min(0.18, f.strength * 0.25)
        : f.strength * (0.28 + intensity * 0.22);
      const cx = Math.round(f.centerX);
      const cy = Math.round(f.centerY);
      const key = `${cx},${cy},${alpha.toFixed(3)}`;
      if (key === lastApplied) return;
      lastApplied = key;
      node.style.opacity = "1";
      node.style.background = [
        `radial-gradient(circle at ${cx}px ${cy}px,`
        + ` rgba(255, 234, 196, ${alpha * 0.9}) 0%,`
        + ` rgba(255, 196, 140, ${alpha * 0.42}) 6%,`
        + ` rgba(168, 188, 240, ${alpha * 0.22}) 16%,`
        + ` transparent 38%)`,
        `radial-gradient(circle at ${cx}px ${cy}px,`
        + ` transparent 22%,`
        + ` rgba(120, 175, 255, ${alpha * 0.12}) 32%,`
        + ` transparent 58%)`,
      ].join(", ");
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
    };
  }, [focusFrameRef, zoomFactor, reducedMotion]);

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
      // z-[3] sits above the `#universe` 2D canvas (which has
      // `z-index: 2` in page.tsx CSS) so the vignette + focus bloom
      // actually paint on top of the stars/comets they're meant to
      // tint. Earlier z-[2] tied with the canvas and DOM order put
      // the canvas on top, hiding the overlay (Codex review on PR
      // #566).
      className={cn(
        "pointer-events-none fixed inset-0 z-[3]",
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
      {/* Focused-star bloom — radial scatter centred on the active
          focus point. Updated imperatively each frame from the
          focusFrameRef so position tracks the focused star smoothly
          without driving React re-renders. Tiny chromatic split
          between the warm core and cool halo reads as atmospheric
          refraction. */}
      {focusFrameRef && (
        <div
          ref={focusBloomRef}
          className="absolute inset-0"
          data-testid="cosmic-atmosphere-focus-bloom"
          style={{
            opacity: 0,
            transition: "opacity 200ms ease-out",
            mixBlendMode: "screen",
          }}
        />
      )}
    </div>
  );
}
