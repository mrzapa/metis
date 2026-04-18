"use client";

import {
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { CONSTELLATION_DIVE_DURATION_MS } from "@/hooks/use-constellation-camera";
import { cn } from "@/lib/utils";

/**
 * Orbital Observatory layout (M02 Phase 4).
 *
 * Renders named slots ("top", "right", "bottom", "left") as docked rings around
 * a central content area so the underlying star stays visible in the middle.
 * Slots are abstract — the caller decides which sub-panel goes in which slot.
 *
 * Entrance animation: each filled slot fades + slides inward from its edge,
 * staggered by {@link SLOT_ENTRANCE_STAGGER_MS} ms in ring order, with the
 * same cubic-out curve + total duration as the camera dive
 * ({@link CONSTELLATION_DIVE_DURATION_MS}) so the panels settle in sync with
 * the camera pullback.
 *
 * Exit animation reverses the transform/opacity back to the off-stage state
 * before the caller unmounts (callers drive this by flipping the `open` prop
 * and waiting {@link OBSERVATORY_EXIT_DURATION_MS} ms before tearing down).
 *
 * Accessibility: this component is a pure presentational container. Focus
 * trap + Esc dismiss + click-outside dismiss stay with the Dialog primitive
 * the caller wraps this in. We intentionally do not duplicate that logic here.
 *
 * Mobile: this layout assumes desktop real estate. Callers should fall back to
 * the existing modal when the viewport is below
 * {@link OBSERVATORY_ORBITAL_MIN_WIDTH_PX}. See {@link isOrbitalViewport}.
 */

/** Docked-ring slot identifier. Four cardinal rings around the centre. */
export type OrbitalSlotName = "top" | "right" | "bottom" | "left";

/** Ring enter order — staggered by {@link SLOT_ENTRANCE_STAGGER_MS}. */
export const OBSERVATORY_SLOT_ORDER: readonly OrbitalSlotName[] = [
  "top",
  "right",
  "bottom",
  "left",
] as const;

/** Stagger between successive slot entrances. */
export const SLOT_ENTRANCE_STAGGER_MS = 80;

/** Exit animation runs on the same curve but a shortened duration. */
export const OBSERVATORY_EXIT_DURATION_MS = Math.round(CONSTELLATION_DIVE_DURATION_MS * 0.6);

/** Minimum viewport width (px) at which the orbital layout is preferred. */
export const OBSERVATORY_ORBITAL_MIN_WIDTH_PX = 768;

/**
 * Slot offset in the off-stage direction. Translated inward to zero when the
 * slot enters. Keep small so the ring barely "docks" rather than flying across
 * the whole viewport — the camera is already doing the heavy motion.
 */
const OFFSTAGE_OFFSET_PX = 48;

export interface ObservatoryOrbitalLayoutProps {
  /** Drives entrance/exit. `true` → animate in, `false` → animate out. */
  open: boolean;
  /**
   * Map of slot → content. Missing keys render as empty spacers so the grid
   * keeps its shape. Callers decide which panel goes in which ring.
   */
  slots: Partial<Record<OrbitalSlotName, ReactNode>>;
  /**
   * Content to render at the centre (usually empty — the star is rendered by
   * the underlying canvas and the orbital layout just hosts rings around it).
   * Kept optional to preserve the centre-visible principle.
   */
  center?: ReactNode;
  /** Respect `prefers-reduced-motion` — skips transforms and stagger. */
  reducedMotion?: boolean;
  /**
   * Override the entrance duration (ms). Defaults to
   * {@link CONSTELLATION_DIVE_DURATION_MS} to sync with the Phase 2 camera.
   */
  entranceDurationMs?: number;
  /** Extra className applied to the outer grid container. */
  className?: string;
  /**
   * Ring-specific class overrides so callers can adjust per-slot sizing
   * without reaching into internal styles. Optional.
   */
  slotClassName?: Partial<Record<OrbitalSlotName, string>>;
  /** Test hook. */
  "data-testid"?: string;
}

interface SlotPositionStyle {
  /** Starting transform applied when the slot is off-stage. */
  offstageTransform: string;
  /** Position rules for placing the slot ring in the grid. */
  placement: CSSProperties;
}

const SLOT_POSITION: Record<OrbitalSlotName, SlotPositionStyle> = {
  top: {
    offstageTransform: `translate(-50%, calc(-100% - ${OFFSTAGE_OFFSET_PX}px))`,
    placement: {
      position: "absolute",
      top: 0,
      left: "50%",
      transform: "translate(-50%, 0)",
    },
  },
  right: {
    offstageTransform: `translate(calc(100% + ${OFFSTAGE_OFFSET_PX}px), -50%)`,
    placement: {
      position: "absolute",
      top: "50%",
      right: 0,
      transform: "translate(0, -50%)",
    },
  },
  bottom: {
    offstageTransform: `translate(-50%, calc(100% + ${OFFSTAGE_OFFSET_PX}px))`,
    placement: {
      position: "absolute",
      bottom: 0,
      left: "50%",
      transform: "translate(-50%, 0)",
    },
  },
  left: {
    offstageTransform: `translate(calc(-100% - ${OFFSTAGE_OFFSET_PX}px), -50%)`,
    placement: {
      position: "absolute",
      top: "50%",
      left: 0,
      transform: "translate(0, -50%)",
    },
  },
};

/**
 * Matches-media helper — returns whether the current viewport is wide enough
 * for the orbital layout. Returns `true` on the server (SSR), matching the
 * desktop-first assumption; callers should re-render on mount.
 */
export function isOrbitalViewport(width?: number): boolean {
  if (typeof width === "number") {
    return width >= OBSERVATORY_ORBITAL_MIN_WIDTH_PX;
  }
  if (typeof window === "undefined") {
    return true;
  }
  return window.matchMedia(`(min-width: ${OBSERVATORY_ORBITAL_MIN_WIDTH_PX}px)`).matches;
}

/**
 * React hook counterpart to {@link isOrbitalViewport} that re-renders when the
 * viewport crosses the breakpoint. Use in the caller to flip between orbital
 * and classic modal layouts.
 */
export function useIsOrbitalViewport(): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === "undefined") {
      return true;
    }
    return window.matchMedia(`(min-width: ${OBSERVATORY_ORBITAL_MIN_WIDTH_PX}px)`).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) {
      return;
    }
    const query = window.matchMedia(`(min-width: ${OBSERVATORY_ORBITAL_MIN_WIDTH_PX}px)`);
    const handler = (event: MediaQueryListEvent) => setMatches(event.matches);
    // Modern browsers → addEventListener; older Safari → addListener.
    if (typeof query.addEventListener === "function") {
      query.addEventListener("change", handler);
      return () => query.removeEventListener("change", handler);
    }
    query.addListener(handler);
    return () => query.removeListener(handler);
  }, []);

  return matches;
}

function buildSlotStyle({
  slot,
  index,
  open,
  reducedMotion,
  entranceDurationMs,
  exitDurationMs,
}: {
  slot: OrbitalSlotName;
  index: number;
  open: boolean;
  reducedMotion: boolean;
  entranceDurationMs: number;
  exitDurationMs: number;
}): CSSProperties {
  const position = SLOT_POSITION[slot];
  const delayMs = reducedMotion ? 0 : index * SLOT_ENTRANCE_STAGGER_MS;
  const durationMs = open ? entranceDurationMs : exitDurationMs;
  // Cubic-out matches {@link cubicOutEasing} in use-constellation-camera.ts.
  const easing = "cubic-bezier(0.33, 1, 0.68, 1)";

  return {
    ...position.placement,
    transform: reducedMotion || open
      ? position.placement.transform
      : `${position.placement.transform} ${position.offstageTransform}`,
    opacity: reducedMotion ? 1 : open ? 1 : 0,
    transition: reducedMotion
      ? "none"
      : `transform ${durationMs}ms ${easing} ${delayMs}ms, opacity ${durationMs}ms ${easing} ${delayMs}ms`,
    willChange: reducedMotion ? undefined : "transform, opacity",
  };
}

export function ObservatoryOrbitalLayout({
  open,
  slots,
  center,
  reducedMotion = false,
  entranceDurationMs = CONSTELLATION_DIVE_DURATION_MS,
  className,
  slotClassName,
  "data-testid": dataTestId,
}: ObservatoryOrbitalLayoutProps) {
  // `visible` starts offstage (unless reduced motion) so the entrance
  // animation has a state to transition *from*. The effect below schedules a
  // single RAF after any `open` change to flip the state; that RAF hop
  // guarantees the browser commits the offstage style to the DOM before the
  // onstage style replaces it. Reduced-motion renders skip the hop.
  const [visible, setVisible] = useState<boolean>(() =>
    reducedMotion ? open : false,
  );

  useEffect(() => {
    if (reducedMotion) {
      // Reduced motion: sync to `open` on the next frame so the effect hook
      // rules stay clean — no cascading render because the RAF runs outside
      // React's commit phase.
      const raf = requestAnimationFrame(() => setVisible(open));
      return () => cancelAnimationFrame(raf);
    }
    const raf = requestAnimationFrame(() => setVisible(open));
    return () => cancelAnimationFrame(raf);
  }, [open, reducedMotion]);

  const entries = useMemo(
    () => OBSERVATORY_SLOT_ORDER.map((name, index) => ({
      name,
      index,
      content: slots[name],
    })),
    [slots],
  );

  return (
    <div
      className={cn(
        "observatory-orbital-layout relative mx-auto flex h-full w-full items-center justify-center",
        className,
      )}
      data-testid={dataTestId ?? "observatory-orbital-layout"}
      data-open={visible ? "true" : "false"}
      data-reduced-motion={reducedMotion ? "true" : "false"}
    >
      {/* Centre slot — transparent passthrough so the star stays visible. */}
      <div
        className="observatory-orbital-center pointer-events-none relative flex items-center justify-center"
        data-slot="center"
        aria-hidden={center ? undefined : true}
      >
        {center ?? null}
      </div>

      {entries.map(({ name, index, content }) => (
        <div
          key={name}
          data-slot={name}
          data-slot-filled={content ? "true" : "false"}
          className={cn(
            "observatory-orbital-slot pointer-events-auto",
            !content && "observatory-orbital-slot--empty",
            slotClassName?.[name],
          )}
          style={buildSlotStyle({
            slot: name,
            index,
            open: visible,
            reducedMotion,
            entranceDurationMs,
            exitDurationMs: OBSERVATORY_EXIT_DURATION_MS,
          })}
        >
          {content ?? null}
        </div>
      ))}
    </div>
  );
}
