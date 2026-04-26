"use client";

/**
 * MetisSigil — the animated identity mark for the METIS companion.
 *
 * Replaces the generic `Bot` lucide icon previously used in the dock and
 * elsewhere with a signature sigil: a bright pulsing core surrounded by
 * concentric orbital rings rotating at different speeds. Ring count
 * follows the growth-stage progression (seedling=1, sapling=2,
 * bloom=3, elder=4) so the user can read the companion's maturity at
 * a glance.
 *
 * Animation is GSAP-driven:
 *   - Idle: gentle core breathing + continuous ring rotation at staggered
 *     rates (innermost fastest, outermost slowest, alternating directions).
 *   - Pulse: bumping `pulseToken` fires a one-shot core flash + ring
 *     pulse — wire to companion activity events for live feedback.
 *   - Reduced motion: snaps to a static frame, no continuous tweens.
 */

import { useEffect, useId, useMemo, useRef } from "react";
import { useReducedMotion } from "motion/react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import type { GrowthStage } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface MetisSigilProps {
  /** Outer pixel size; SVG keeps a 64×64 viewBox internally. */
  size?: number;
  /**
   * Companion growth stage. Drives the number of visible rings:
   * seedling=1, sapling=2, bloom=3, elder=4. Defaults to seedling.
   */
  stage?: GrowthStage;
  /**
   * Whether the companion is "active" right now (running, listening,
   * researching). When true, rings spin slightly faster and the core
   * glows brighter.
   */
  active?: boolean;
  /**
   * Increment this on every meaningful activity event to fire a one-shot
   * pulse animation — core flash + ring tighten. Triggered on change
   * (not on initial mount), so seeding the parent state at 0 is safe.
   */
  pulseToken?: number;
  className?: string;
  ariaLabel?: string;
}

interface RingDef {
  /** Radius in viewBox units (64×64). */
  r: number;
  /** stroke-dasharray pattern, in viewBox units. */
  dash: string;
  /** Rotation period in seconds — sign controls direction. */
  period: number;
  /** Stroke width in viewBox units. */
  strokeWidth: number;
  /** Base opacity for this ring at idle. */
  opacity: number;
}

const RINGS: RingDef[] = [
  { r: 12, dash: "1.5 3", period: 24, strokeWidth: 0.9, opacity: 0.62 },
  { r: 18, dash: "2.5 5", period: -36, strokeWidth: 0.8, opacity: 0.5 },
  { r: 24, dash: "1 4", period: 48, strokeWidth: 0.75, opacity: 0.4 },
  { r: 29, dash: "0.8 6", period: -80, strokeWidth: 0.6, opacity: 0.3 },
];

const STAGE_RING_COUNT: Record<GrowthStage, number> = {
  seedling: 1,
  sapling: 2,
  bloom: 3,
  elder: 4,
};

const STAGE_CORE_SCALE: Record<GrowthStage, number> = {
  seedling: 0.78,
  sapling: 0.92,
  bloom: 1.06,
  elder: 1.18,
};

export function MetisSigil({
  size = 36,
  stage = "seedling",
  active = false,
  pulseToken = 0,
  className,
  ariaLabel,
}: MetisSigilProps) {
  const prefersReducedMotion = useReducedMotion();

  const containerRef = useRef<SVGSVGElement>(null);
  const coreRef = useRef<SVGCircleElement>(null);
  const coreGlowRef = useRef<SVGCircleElement>(null);
  const ringRefs = useRef<Array<SVGCircleElement | null>>([null, null, null, null]);

  const visibleRings = useMemo(() => {
    const count = STAGE_RING_COUNT[stage];
    return RINGS.slice(0, count);
  }, [stage]);

  // Idle animation timeline — core breath + continuous ring rotation.
  useGSAP(
    () => {
      if (prefersReducedMotion) {
        // Snap to a clean static state. Each ring is held at a different
        // angle so the dashes don't all line up in one boring stripe.
        ringRefs.current.forEach((ring, i) => {
          if (!ring) return;
          gsap.set(ring, { rotation: i * 18, svgOrigin: "32 32" });
        });
        if (coreRef.current) {
          gsap.set(coreRef.current, { scale: STAGE_CORE_SCALE[stage], svgOrigin: "32 32" });
        }
        if (coreGlowRef.current) {
          gsap.set(coreGlowRef.current, { scale: STAGE_CORE_SCALE[stage] * (active ? 1.18 : 1), opacity: active ? 0.85 : 0.65, svgOrigin: "32 32" });
        }
        return;
      }

      const speedScale = active ? 0.7 : 1; // active = faster
      ringRefs.current.forEach((ring, i) => {
        if (!ring) return;
        const def = RINGS[i];
        if (!def) return;
        const dir = def.period > 0 ? 1 : -1;
        const duration = Math.abs(def.period) * speedScale;
        gsap.to(ring, {
          rotation: dir * 360,
          duration,
          repeat: -1,
          ease: "none",
          svgOrigin: "32 32",
        });
      });

      if (coreRef.current) {
        const baseScale = STAGE_CORE_SCALE[stage];
        gsap.to(coreRef.current, {
          scale: baseScale * 1.08,
          duration: 2.4,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
          svgOrigin: "32 32",
        });
      }

      if (coreGlowRef.current) {
        const baseScale = STAGE_CORE_SCALE[stage] * (active ? 1.22 : 1);
        const baseOpacity = active ? 0.85 : 0.55;
        gsap.set(coreGlowRef.current, { svgOrigin: "32 32" });
        gsap.to(coreGlowRef.current, {
          scale: baseScale * 1.18,
          opacity: baseOpacity,
          duration: 2.4,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
        });
      }
    },
    { scope: containerRef, dependencies: [stage, active, prefersReducedMotion] },
  );

  // Pulse on activity — fires whenever pulseToken changes (skipping mount).
  const lastPulseTokenRef = useRef<number>(pulseToken);
  useEffect(() => {
    if (pulseToken === lastPulseTokenRef.current) return;
    lastPulseTokenRef.current = pulseToken;
    if (prefersReducedMotion) return;

    if (coreRef.current) {
      gsap.fromTo(
        coreRef.current,
        { scale: STAGE_CORE_SCALE[stage] },
        {
          scale: STAGE_CORE_SCALE[stage] * 1.55,
          duration: 0.18,
          ease: "power2.out",
          yoyo: true,
          repeat: 1,
          svgOrigin: "32 32",
        },
      );
    }
    if (coreGlowRef.current) {
      gsap.fromTo(
        coreGlowRef.current,
        { scale: STAGE_CORE_SCALE[stage] * 1.1, opacity: 0.6 },
        {
          scale: STAGE_CORE_SCALE[stage] * 1.9,
          opacity: 1,
          duration: 0.22,
          ease: "power2.out",
          yoyo: true,
          repeat: 1,
          svgOrigin: "32 32",
        },
      );
    }
    // Tighten then release rings — they pull in toward the core briefly.
    ringRefs.current.forEach((ring) => {
      if (!ring) return;
      gsap.fromTo(
        ring,
        { strokeOpacity: 1 },
        {
          strokeOpacity: 0.2,
          duration: 0.32,
          ease: "power2.in",
          yoyo: true,
          repeat: 1,
        },
      );
    });
  }, [pulseToken, prefersReducedMotion, stage]);

  const reactId = useId();
  // useId yields stable, SSR-safe ids; sanitize the colon React inserts so
  // the value works inside SVG `url(#…)` references.
  const safeId = reactId.replace(/:/g, "");
  const gradientId = `metis-sigil-core-${safeId}`;
  const haloGradientId = `metis-sigil-halo-${safeId}`;

  return (
    <svg
      ref={containerRef}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role={ariaLabel ? "img" : "presentation"}
      aria-label={ariaLabel}
      aria-hidden={ariaLabel ? undefined : true}
      className={cn("overflow-visible", className)}
      data-testid="metis-sigil"
      data-stage={stage}
      data-active={active ? "true" : "false"}
    >
      <defs>
        <radialGradient id={gradientId} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.95" />
          <stop offset="35%" stopColor="currentColor" stopOpacity="0.75" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </radialGradient>
        <radialGradient id={haloGradientId} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.32" />
          <stop offset="65%" stopColor="currentColor" stopOpacity="0.12" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Outer halo — the diffuse atmospheric glow framing the rings. */}
      <circle
        cx={32}
        cy={32}
        r={30}
        fill={`url(#${haloGradientId})`}
        opacity={active ? 0.9 : 0.6}
      />

      {/* Concentric orbital rings — count follows growth stage. */}
      {visibleRings.map((ring, i) => (
        <circle
          key={i}
          ref={(node) => {
            ringRefs.current[i] = node;
          }}
          cx={32}
          cy={32}
          r={ring.r}
          fill="none"
          stroke="currentColor"
          strokeWidth={ring.strokeWidth}
          strokeDasharray={ring.dash}
          strokeOpacity={ring.opacity}
          strokeLinecap="round"
        />
      ))}

      {/* Soft core glow underlay. Drives the breathing pulse. */}
      <circle
        ref={coreGlowRef}
        cx={32}
        cy={32}
        r={9}
        fill={`url(#${haloGradientId})`}
      />

      {/* Bright core. Scaled by stage; pulsed on activity. */}
      <circle
        ref={coreRef}
        cx={32}
        cy={32}
        r={4.6}
        fill={`url(#${gradientId})`}
      />

      {/* Small fixed white pinpoint so the centre always reads as a
          star, not a fuzzy blob — even at small render sizes. */}
      <circle cx={32} cy={32} r={1.1} fill="#ffffff" opacity={0.95} />
    </svg>
  );
}
