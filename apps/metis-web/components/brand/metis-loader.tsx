"use client";

import { MetisGlow, type MetisGlowProps } from "./metis-glow";
import { MetisMark } from "./metis-mark";

export interface MetisLoaderProps
  extends Omit<MetisGlowProps, "animated" | "children"> {
  /** Outer wrapper size in px. Default 96. */
  size?: number;
}

/**
 * Convenience wrapper: a MetisGlow in loop mode (continuous sonar)
 * with the mark inside. Used for in-flight loading states —
 * DesktopReadyGuard, SetupGuard splash, companion-dock loading.
 *
 * The mark renders at 40 % of the wrapper size so the rings have
 * room to expand without being clipped by the wrapper bounds.
 */
export function MetisLoader({ size = 96, ...rest }: MetisLoaderProps) {
  return (
    <MetisGlow size={size} animated="loop" {...rest}>
      <MetisMark size={Math.round(size * 0.4)} title="Loading Metis" />
    </MetisGlow>
  );
}
