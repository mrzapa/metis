"use client";

import { useCallback, useRef, useState } from "react";

/**
 * Lifecycle of a "dive into star" interaction:
 *
 *   idle → focusing → details-open → returning → idle
 *
 * The phase drives camera animation, canvas pointer locking, and the
 * star-observatory dialog visibility. The render path needs the
 * reactive value (`phase`); the animation loop needs a synchronous
 * read (`phaseRef.current`) because reading state inside a
 * requestAnimationFrame callback closes over a stale snapshot.
 *
 * Centralising the ref/state pair behind a single setter prevents
 * the two from drifting — a class of bugs that cost the team several
 * "stuck in focusing forever" reports during M02.
 */
export type StarFocusPhase = "idle" | "focusing" | "details-open" | "returning";

export interface StarFocusPhaseHandle {
  /** Reactive value — drives renders. */
  phase: StarFocusPhase;
  /** Synchronous read — safe inside animation/event callbacks. */
  phaseRef: { readonly current: StarFocusPhase };
  /** Updates both state and ref in lockstep. No-op when unchanged. */
  setPhase: (next: StarFocusPhase) => void;
}

export function useStarFocusPhase(
  initial: StarFocusPhase = "idle",
): StarFocusPhaseHandle {
  const [phase, setPhase] = useState<StarFocusPhase>(initial);
  const phaseRef = useRef<StarFocusPhase>(initial);

  const setPhaseSynchronized = useCallback((next: StarFocusPhase) => {
    if (phaseRef.current === next) {
      return;
    }
    phaseRef.current = next;
    setPhase(next);
  }, []);

  return { phase, phaseRef, setPhase: setPhaseSynchronized };
}
