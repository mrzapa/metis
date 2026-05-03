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

/**
 * Predicate split out so the unit tests can exercise the matcher
 * without having to hijack `console.warn` themselves. Exported only
 * for tests; production callers go through the wrapped `console.warn`.
 *
 * @internal
 */
export function isMotionReducedMotionWarning(message: unknown): boolean {
  if (typeof message !== "string") return false;
  return (
    message.includes("reduced-motion-disabled")
    || message.includes("You have Reduced Motion enabled")
  );
}

/**
 * Wraps the supplied `console.warn` so the motion/react reduced-motion
 * warning is dropped and everything else is forwarded unchanged.
 * Idempotent against double-installation via the `__metisMotionFiltered`
 * flag. Exported for tests; production wires this in via the
 * module-load side effect below.
 *
 * @internal
 */
export function installMotionWarnFilter(target: Console): void {
  const original = target.warn as FilteredWarn;
  if (typeof original !== "function" || original.__metisMotionFiltered) {
    return;
  }
  const wrapped: FilteredWarn = function metisMotionWarnFilter(...args: unknown[]) {
    if (isMotionReducedMotionWarning(args[0])) {
      return;
    }
    // Forward verbatim. Spread keeps the call signature honest —
    // earlier draft used `original.apply(console, args as [])` which
    // mis-types the call as taking no arguments and would silently
    // break if `apply`'s typings tighten.
    (original as (...rest: unknown[]) => void)(...args);
  };
  wrapped.__metisMotionFiltered = true;
  target.warn = wrapped as Console["warn"];
}

if (typeof window !== "undefined" && typeof console !== "undefined") {
  installMotionWarnFilter(console);
}

export function MotionConsoleFilter() {
  return null;
}
