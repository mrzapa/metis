"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PlaneTakeoff, Wifi } from "lucide-react";
import { fetchNetworkAuditRecentCount, fetchSettings } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Audit panel uses a 5-minute window (300s) for the "recent outbound"
 * counter; mirror that here so the pill agrees with the panel.
 */
const RECENT_COUNT_WINDOW_SECONDS = 300;

/**
 * Audit panel polls every ~5s because it's the active focus. The pill
 * is ambient — 30s is enough to keep it honest without wasting
 * round-trips on every page that mounts the chrome.
 */
const POLL_INTERVAL_MS = 30_000;

type PillState =
  | { kind: "loading" }
  | { kind: "hidden" } // unrecoverable: API unreachable / never returned data
  | { kind: "ok"; airplane: boolean; count: number };

/**
 * Promote the privacy/network-audit panel to a small clickable pill in
 * the page header. Click → ``/settings/privacy``.
 *
 * Failure mode is "render nothing": the pill never error-toasts, never
 * 500s the chrome. If the initial settings + recent-count probe both
 * fail before any value lands, we hide; otherwise we keep showing the
 * last good value (transient poll failures don't flip the pill off).
 */
export function NetworkAuditPill() {
  const [state, setState] = useState<PillState>({ kind: "loading" });

  // Single poll cycle reads airplane mode + recent count together so the
  // pill reflects toggles made in /settings/privacy without waiting for
  // a remount. Transient settings or count failures keep the last good
  // value rather than flipping the pill off — only an unrecoverable
  // bootstrap (no value ever observed) hides it.
  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    const poll = async (): Promise<void> => {
      const [settingsResult, countResult] = await Promise.allSettled([
        fetchSettings(),
        fetchNetworkAuditRecentCount(RECENT_COUNT_WINDOW_SECONDS, {
          signal: controller.signal,
        }),
      ]);
      if (cancelled) return;

      // Drop AbortError so unmount-driven aborts don't hide the pill.
      const isAbort = (reason: unknown): boolean =>
        typeof reason === "object" &&
        reason !== null &&
        "name" in reason &&
        (reason as { name: string }).name === "AbortError";

      if (
        countResult.status === "rejected" &&
        isAbort(countResult.reason)
      ) {
        return;
      }

      setState((prev) => {
        const nextAirplane =
          settingsResult.status === "fulfilled" &&
          typeof settingsResult.value.network_audit_airplane_mode === "boolean"
            ? settingsResult.value.network_audit_airplane_mode
            : prev.kind === "ok"
              ? prev.airplane
              : false;
        const nextCount =
          countResult.status === "fulfilled"
            ? countResult.value.count
            : prev.kind === "ok"
              ? prev.count
              : 0;
        const everySourceFailed =
          settingsResult.status === "rejected" &&
          countResult.status === "rejected";
        if (prev.kind !== "ok" && everySourceFailed) {
          return { kind: "hidden" };
        }
        return { kind: "ok", airplane: nextAirplane, count: nextCount };
      });
    };

    void poll();
    const timer = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(timer);
    };
  }, []);

  if (state.kind !== "ok") {
    return null;
  }

  const { airplane, count } = state;

  if (airplane) {
    const label = "Airplane mode";
    const title = "Airplane mode is on — all network calls are blocked. Click to open the privacy panel.";
    return (
      <Link
        href="/settings/privacy"
        title={title}
        aria-label={`${label}. Open privacy and network audit panel.`}
        data-testid="network-audit-pill"
        data-state="airplane"
        className={cn(
          "hidden sm:inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1",
          "text-[12px] font-medium tracking-[0.04em]",
          "border-sky-300/30 bg-sky-300/10 text-sky-200",
          "transition-colors duration-300",
          "hover:border-sky-300/50 hover:bg-sky-300/15 hover:text-sky-100",
        )}
      >
        <PlaneTakeoff aria-hidden="true" className="size-3.5" />
        <span>{label}</span>
      </Link>
    );
  }

  const isQuiet = count === 0;
  const label = `${count} outbound`;
  const title = isQuiet
    ? "0 outbound calls in the last 5 minutes — click to see details."
    : `${count} outbound call${count === 1 ? "" : "s"} in the last 5 minutes — click to see details.`;
  const dotClass = isQuiet ? "bg-emerald-400" : "bg-amber-300";

  return (
    <Link
      href="/settings/privacy"
      title={title}
      aria-label={`${label} calls in the last 5 minutes. Open privacy and network audit panel.`}
      data-testid="network-audit-pill"
      data-state={isQuiet ? "quiet" : "active"}
      className={cn(
        "hidden sm:inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1",
        "text-[12px] font-medium tracking-[0.04em]",
        "border-white/10 bg-white/[0.04] text-muted-foreground/70",
        "transition-colors duration-300",
        "hover:border-white/20 hover:bg-white/[0.08] hover:text-foreground",
      )}
    >
      <span aria-hidden="true" className={cn("size-1.5 rounded-full", dotClass)} />
      <Wifi aria-hidden="true" className="size-3.5 opacity-60" />
      <span>{label}</span>
    </Link>
  );
}
