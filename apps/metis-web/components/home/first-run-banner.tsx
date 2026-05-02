"use client";

/**
 * First-run setup banner for the constellation home (`/`).
 *
 * The setup-guard exempts `/` so a brand-new user can explore the
 * constellation before configuring anything. That leaves zero signal
 * that setup is required. This slim, dismissible banner overlays the
 * top of the viewport and points the user at `/setup` without trapping
 * them.
 *
 * Visibility rules:
 *   1. Hidden until `fetchSettings` resolves — avoids flashing while
 *      we don't yet know whether the wizard has completed.
 *   2. Hidden when `basic_wizard_completed === true`, regardless of
 *      any prior dismissal.
 *   3. Hidden when the user has explicitly dismissed via the close
 *      button (persisted in `localStorage`).
 *
 * Dismissal persists in `localStorage` (not server settings) because
 * this is a per-browser nudge, not a workspace-level state. If the
 * user finishes the wizard the dismissal flag becomes irrelevant.
 *
 * Layout: `position: fixed` at the top of the viewport with compact
 * padding so the constellation canvas behind it is not pushed down.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { Settings2, X } from "lucide-react";
import { fetchSettings } from "@/lib/api";

/** localStorage key tracking whether the user has dismissed the banner. */
export const FIRST_RUN_BANNER_DISMISSED_KEY = "metis:first-run-banner-dismissed";

export function FirstRunBanner(): React.JSX.Element | null {
  // tri-state: null while loading, true to show, false to hide.
  const [shouldShow, setShouldShow] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // Read dismissal first — if dismissed, we don't even need to
      // hit the settings endpoint to know we should stay quiet.
      let dismissed = false;
      try {
        dismissed =
          typeof window !== "undefined" &&
          window.localStorage.getItem(FIRST_RUN_BANNER_DISMISSED_KEY) === "true";
      } catch {
        // localStorage unavailable (private mode, etc.) — treat as not dismissed.
      }
      if (dismissed) {
        if (!cancelled) setShouldShow(false);
        return;
      }

      try {
        const settings = await fetchSettings();
        if (cancelled) return;
        const completed = settings.basic_wizard_completed === true;
        setShouldShow(!completed);
      } catch {
        // Settings fetch failed (e.g. backend not running). Stay quiet —
        // a banner we can't trust is worse than no banner.
        if (!cancelled) setShouldShow(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleDismiss = (): void => {
    setShouldShow(false);
    try {
      window.localStorage.setItem(FIRST_RUN_BANNER_DISMISSED_KEY, "true");
    } catch {
      // Best-effort persistence; the banner will reappear next reload
      // if storage is unavailable. That is acceptable.
    }
  };

  if (shouldShow !== true) return null;

  return (
    <>
      <style>{firstRunBannerStyles}</style>
      <aside
        data-testid="first-run-banner"
        aria-label="Workspace setup banner"
        className="metis-first-run-banner"
      >
        <div className="metis-first-run-banner-message">
          <Settings2 size={14} aria-hidden="true" className="metis-first-run-banner-icon" />
          <span>Workspace not set up yet</span>
        </div>
        <Link
          href="/setup"
          className="metis-first-run-banner-cta cursor-pointer"
        >
          Set up &rarr;
        </Link>
        <button
          type="button"
          onClick={handleDismiss}
          aria-label="Dismiss setup banner"
          className="metis-first-run-banner-dismiss"
        >
          <X size={14} aria-hidden="true" />
        </button>
      </aside>
    </>
  );
}

const firstRunBannerStyles = `
.metis-first-run-banner {
  /* M21 #12: was top 12px, which placed the banner inside the
     .metis-nav band on /. At narrow viewports the centered banner
     widened to calc(100vw - 32px) and bled through the left-aligned
     nav links (Chat / Settings / etc.). Move below the nav (matches
     the .metis-network-audit-first-run-card convention at top 72px). */
  position: fixed;
  top: 80px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 46;
  display: flex;
  align-items: center;
  gap: 14px;
  height: 36px;
  padding: 0 10px 0 14px;
  border-radius: 999px;
  background: rgba(8, 10, 18, 0.78);
  border: 1px solid rgba(120, 140, 190, 0.18);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  font-size: 12px;
  letter-spacing: 0.2px;
  color: var(--text-dim, rgba(220, 228, 245, 0.72));
  white-space: nowrap;
  max-width: calc(100vw - 32px);
}
.metis-first-run-banner-message {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-bright, #e7ecf7);
  font-weight: 500;
}
.metis-first-run-banner-icon {
  opacity: 0.85;
}
.metis-first-run-banner-cta {
  display: inline-flex;
  align-items: center;
  font-weight: 600;
  letter-spacing: 0.3px;
  color: #22c55e;
  text-decoration: none;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(34, 197, 94, 0.35);
  background: rgba(34, 197, 94, 0.08);
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}
.metis-first-run-banner-cta:hover {
  background: rgba(34, 197, 94, 0.18);
  border-color: rgba(34, 197, 94, 0.6);
  color: #4ade80;
}
.metis-first-run-banner-dismiss {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  color: var(--text-dim, rgba(220, 228, 245, 0.6));
  background: transparent;
  border: none;
  cursor: pointer;
  border-radius: 999px;
  transition: color 0.2s ease, background 0.2s ease;
}
.metis-first-run-banner-dismiss:hover {
  color: var(--text-bright, #e7ecf7);
  background: rgba(255, 255, 255, 0.06);
}
`;
