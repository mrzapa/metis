"use client";

import { cn } from "@/lib/utils";

import { MetisGlow } from "./metis-glow";
import { MetisMark } from "./metis-mark";

export interface MetisLockupProps {
  /** Visual scale. "md" = 64 px mark; "lg" = 128 px mark. Default "md". */
  size?: "md" | "lg";
  /** Where to place the lowercase `metis` wordmark relative to the mark. */
  wordmarkPosition?: "right" | "below";
  className?: string;
}

const MARK_PX = { md: 64, lg: 128 } as const;
const WORDMARK_PX = { md: 28, lg: 56 } as const;

/**
 * Mark + lowercase `metis` wordmark, with brand glow.
 *
 * **External surfaces only** per M20 option A — OG image, Apple touch
 * icon, /setup welcome card, Tauri splash. NOT used in in-app chrome
 * (chrome shows the mark only; mixing the lockup back in is a
 * typography migration in disguise).
 *
 * Wordmark uses Inter Tight (placeholder; the design team may swap
 * to Geist or a custom face later — that's a one-line font-family
 * change inside this component, not a structural rebuild).
 */
export function MetisLockup({
  size = "md",
  wordmarkPosition = "right",
  className,
}: MetisLockupProps) {
  const isVertical = wordmarkPosition === "below";
  return (
    <div
      className={cn(
        "inline-flex items-center gap-4",
        isVertical ? "flex-col" : "flex-row",
        className,
      )}
    >
      <MetisGlow size={MARK_PX[size]} animated="static">
        <MetisMark size={MARK_PX[size]} title="Metis" />
      </MetisGlow>
      <span
        style={{
          fontFamily: "'Inter Tight', 'Inter', sans-serif",
          fontWeight: 500,
          fontSize: `${WORDMARK_PX[size]}px`,
          letterSpacing: "-0.02em",
          color: "var(--brand-mark)",
          lineHeight: 1,
        }}
      >
        metis
      </span>
    </div>
  );
}
