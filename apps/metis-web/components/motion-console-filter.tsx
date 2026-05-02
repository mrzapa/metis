"use client";

/**
 * Suppresses the noisy `motion/react` log that fires when the user has
 * `prefers-reduced-motion: reduce` enabled:
 *
 *   "You have Reduced Motion enabled on your device. Animations may
 *    not appear as expected.. For more information and steps for
 *    solving, visit https://motion.dev/troubleshooting/reduced-motion-disabled"
 *
 * The message is informational and aimed at library developers, not
 * end users; surfacing it as a console.warn pollutes our dev console
 * and (in browsers that mirror console output to a remote logger)
 * leaks an unrelated 3rd-party URL into our log stream.
 *
 * Install at module-load time (synchronous side effect, runs the
 * moment the chunk evaluates in the browser) so the wrapper is in
 * place BEFORE any motion-using component renders. A useLayoutEffect
 * approach would miss the very first render's warnings.
 *
 * The component itself renders nothing — it exists only to root the
 * module so the side effect runs.
 *
 * M21 P3 #19.
 */

interface FilteredWarn {
  (...args: unknown[]): void;
  __metisMotionFiltered?: boolean;
}

if (typeof window !== "undefined" && typeof console !== "undefined") {
  const original = console.warn as FilteredWarn;
  if (typeof original === "function" && !original.__metisMotionFiltered) {
    const wrapped: FilteredWarn = function metisMotionWarnFilter(...args: unknown[]) {
      const first = args[0];
      if (
        typeof first === "string"
        && (first.includes("reduced-motion-disabled")
          || first.includes("You have Reduced Motion enabled"))
      ) {
        return;
      }
      original.apply(console, args as []);
    };
    wrapped.__metisMotionFiltered = true;
    console.warn = wrapped;
  }
}

export function MotionConsoleFilter() {
  return null;
}
