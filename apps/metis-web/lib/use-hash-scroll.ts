"use client";

import { useEffect } from "react";

/**
 * Scroll the element matching the URL hash into view once `ready` is
 * true, and re-scroll on subsequent `hashchange` events.
 *
 * Pages that load their content via client-side fetch can't rely on
 * the browser's automatic fragment navigation: the target element
 * doesn't exist when the user lands. Pass `ready={true}` once the
 * post-fetch DOM has been committed (typically by gating on the
 * fetched data) and this hook honours the hash.
 *
 * No-op on the server, when `ready` is false, when the hash is empty,
 * or when the hash points at a missing id.
 */
export function useHashScroll(ready: boolean): void {
  useEffect(() => {
    if (!ready || typeof window === "undefined") return;

    const scrollToHash = () => {
      const hash = window.location.hash.slice(1);
      if (!hash) return;
      const el = document.getElementById(hash);
      if (!el) return;
      // One frame of slack so the render that made `ready` true has
      // committed before we measure layout.
      window.requestAnimationFrame(() => {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    };

    scrollToHash();
    window.addEventListener("hashchange", scrollToHash);
    return () => window.removeEventListener("hashchange", scrollToHash);
  }, [ready]);
}
