"use client";

import { motion, useReducedMotion } from "motion/react";
import { type ReactNode, useId } from "react";

import { cn } from "@/lib/utils";

import { METIS_MARK_PATH_D, METIS_MARK_VIEWBOX } from "./metis-mark-path";

export type MetisGlowAnimated = "static" | "on-mount" | "loop";

export interface MetisGlowProps {
  /** Pixel size of the wrapper (square). Default 280. */
  size?: number;
  /** Multiplier on glow opacity (0..1). Default 1. */
  intensity?: number;
  /**
   * Animation behaviour.
   * - "static" — rings hidden, glow visible, no animation
   * - "on-mount" (default) — rings stagger out once on mount, then settle;
   *    mark gently breathes after 800ms
   * - "loop" — rings re-emit continuously (sonar; used by MetisLoader)
   */
  animated?: MetisGlowAnimated;
  /** The mark (or any child) to wrap. */
  children: ReactNode;
  className?: string;
}

const RING_DILATIONS = [8, 18, 30, 44, 60] as const;
const RING_OPACITIES = [0.45, 0.32, 0.22, 0.14, 0.08] as const;
const RING_STAGGER_MS = 80;
const RING_DURATION_S = 0.6;
const SONAR_LOOP_GAP_S = 2.4;

/**
 * Wraps a `<MetisMark>` (or any child) in the brand glow + topographic
 * ripple rings. The outer halo comes from the `.metis-glow` CSS class
 * (layered drop-shadows in globals.css). The rings are rendered as
 * progressively-dilated copies of the mark path via SVG feMorphology
 * filters — a tactical refinement of the design doc's "offset paths"
 * approach: same visual goal, no build script, no extra deps.
 *
 * Reduced-motion users see a static fallback at 0.9 intensity — the
 * brand stays visible, only the animation is removed. Verified manually
 * in the Phase 1 verification gate; the conditional itself is one line
 * (`!reducedMotion && animated !== "static"`) and exercised by the
 * `animated="static"` test path.
 */
export function MetisGlow({
  size = 280,
  intensity = 1,
  animated = "on-mount",
  children,
  className,
}: MetisGlowProps) {
  const reducedMotion = useReducedMotion();
  const filterIdBase = useId();

  const showRings = !reducedMotion && animated !== "static";
  const effectiveIntensity =
    reducedMotion && animated !== "static" ? 0.9 * intensity : intensity;

  return (
    <div
      className={cn(
        "metis-glow relative inline-flex items-center justify-center",
        className,
      )}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        opacity: effectiveIntensity,
      }}
      data-motion-active={showRings ? "true" : "false"}
    >
      {showRings && (
        <svg
          className="pointer-events-none absolute inset-0"
          viewBox={METIS_MARK_VIEWBOX}
          width={size}
          height={size}
          aria-hidden="true"
        >
          <defs>
            {RING_DILATIONS.map((radius, i) => (
              <filter
                id={`${filterIdBase}-ring-${i}`}
                key={i}
                x="-20%"
                y="-20%"
                width="140%"
                height="140%"
              >
                <feMorphology operator="dilate" radius={radius} />
              </filter>
            ))}
          </defs>
          {RING_DILATIONS.map((_, i) => {
            const transition =
              animated === "loop"
                ? {
                    duration: RING_DURATION_S,
                    delay: (i * RING_STAGGER_MS) / 1000,
                    repeat: Infinity,
                    repeatDelay: SONAR_LOOP_GAP_S,
                    ease: "easeOut" as const,
                  }
                : {
                    duration: RING_DURATION_S,
                    delay: (i * RING_STAGGER_MS) / 1000,
                    ease: "easeOut" as const,
                  };
            return (
              <motion.g
                key={i}
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: RING_OPACITIES[i], scale: 1 }}
                transition={transition}
                style={{ transformOrigin: "500px 500px" }}
              >
                <path
                  d={METIS_MARK_PATH_D}
                  fill="rgb(var(--brand-ripple))"
                  fillRule="evenodd"
                  filter={`url(#${filterIdBase}-ring-${i})`}
                  opacity={0.45}
                />
              </motion.g>
            );
          })}
        </svg>
      )}

      {/* Mark, with a subtle breathing pulse during on-mount idle. The
          breathing is a glow-opacity oscillation on the mark itself —
          the rings handle the entrance moment; this carries the idle. */}
      {!reducedMotion && animated === "on-mount" ? (
        <motion.div
          className="relative inline-flex"
          initial={{ opacity: 0 }}
          animate={{ opacity: [0.85, 1, 0.85] }}
          transition={{
            opacity: {
              delay: 0.8,
              duration: 4,
              repeat: Infinity,
              ease: "easeInOut",
            },
          }}
        >
          {children}
        </motion.div>
      ) : (
        <div className="relative inline-flex">{children}</div>
      )}
    </div>
  );
}
