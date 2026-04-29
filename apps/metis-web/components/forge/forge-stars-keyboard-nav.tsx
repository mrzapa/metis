"use client";

import { useRouter } from "next/navigation";
import type { ForgeStar } from "@/lib/forge-stars";

interface ForgeStarsKeyboardNavProps {
  stars: ForgeStar[];
}

// Keyboard / screen-reader access path for the canvas-rendered
// technique stars. The forge stars themselves live on `<canvas>`,
// which is opaque to assistive tech and not focusable. This component
// renders one real `<button>` per active technique inside a `<nav>`
// landmark so:
//
//   * Tab navigates through the active techniques
//   * Screen readers announce ""Active Forge techniques"" then each
//     technique's name
//   * Enter / Space activates the deep-link to `/forge#<id>`
//
// Visually hidden by default (the canvas already paints the stars).
// On `:focus-within` the nav reveals itself with a thin pinned card
// in the bottom-right corner so sighted keyboard users can see what
// they have focused. No motion / no transition — meets reduced-motion
// users half-way without requiring a `prefers-reduced-motion` query.
//
// Mounted alongside the canvas in `app/page.tsx`. Source of truth is
// the same `useForgeStars()` hook the canvas uses, so the focus list
// and the painted stars cannot drift out of sync.
export function ForgeStarsKeyboardNav({ stars }: ForgeStarsKeyboardNavProps) {
  const router = useRouter();

  if (stars.length === 0) return null;

  return (
    <nav
      aria-label="Active Forge techniques"
      data-testid="forge-stars-keyboard-nav"
      className="sr-only focus-within:not-sr-only focus-within:fixed focus-within:bottom-4 focus-within:right-4 focus-within:z-50 focus-within:max-w-xs focus-within:rounded-2xl focus-within:border focus-within:border-white/15 focus-within:bg-background/95 focus-within:p-3 focus-within:shadow-lg"
    >
      <h2 className="text-xs font-semibold uppercase tracking-[0.18em] text-foreground/80">
        Active Forge techniques
      </h2>
      <ul className="mt-2 flex flex-col gap-1.5">
        {stars.map((star) => (
          <li key={star.id}>
            <button
              type="button"
              data-technique-id={star.id}
              onClick={() => router.push(`/forge#${star.id}`)}
              className="w-full rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-left text-xs text-foreground/90 outline-none transition-colors hover:border-white/25 hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-white/55"
            >
              Open {star.name} in the Forge
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
