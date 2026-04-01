"use client";

import { useLayoutEffect } from "react";

/**
 * Reads the stored UI variant from localStorage and applies it to the <html>
 * element before the first paint. Renders null — no DOM output, no hydration
 * mismatch, no React 19 script-tag warning.
 */
export function UiVariantBootstrap() {
  useLayoutEffect(() => {
    try {
      const stored = window.localStorage.getItem("metis-ui-variant");
      const variant =
        stored === "refined" || stored === "motion" || stored === "bold"
          ? stored
          : "refined";
      document.documentElement.dataset.uiVariant = variant;
    } catch {
      // localStorage unavailable — keep the server-rendered default "refined"
    }
  }, []);

  return null;
}
