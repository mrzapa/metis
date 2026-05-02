"use client";

import { useEffect, useRef, useState } from "react";
import { streamCometEvents, pollComets } from "@/lib/api";
import type { CometEvent } from "@/lib/comet-types";

export interface UseCometNewsResult {
  /** Currently active comet events from the server. */
  comets: CometEvent[];
  /** Whether the initial fetch is in progress. */
  isLoading: boolean;
  /** Error message if the stream or initial fetch failed. */
  error: string | null;
}

/**
 * M21 #7: defer the actual fetch start by this many ms after mount so
 * React 19 strict-mode mount → unmount → mount double-fires (dev only)
 * and quick router-transition remounts are absorbed without ever firing
 * a request. Long enough to outlast strict-mode tear-down (~immediate)
 * and React-Router-style transient mounts; short enough to feel
 * instant on real first paint.
 */
const STREAM_START_DELAY_MS = 50;

/**
 * Hook that subscribes to comet-news events via SSE (hydrate-then-stream).
 *
 * Maintains a live list of active comets and triggers a manual poll on
 * mount to kick off the backend's news cycle.
 *
 * **Abort discipline (M21 #7):** a single `AbortController` per effect
 * run is threaded into `streamCometEvents`, which forwards it to both
 * the hydrate `fetchActiveComets` *and* the SSE `apiFetch`. Cleanup
 * aborts the controller, so all in-flight fetches stop in lockstep —
 * no more `200 OK [FAILED: net::ERR_ABORTED]` entries on the privacy
 * panel from the un-cancellable hydrate path.
 */
export function useCometNews(
  enabled: boolean,
  pollIntervalMs = 300_000,
): UseCometNewsResult {
  const [comets, setComets] = useState<CometEvent[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!enabled) {
      setComets([]);
      return;
    }

    let cancelled = false;
    let stopStream: (() => void) | null = null;
    const controller = new AbortController();

    // Defer the actual stream start so transient mount-unmount cycles
    // (React 19 strict-mode in dev, fast nav-back-and-forth) never
    // fire a real request. See STREAM_START_DELAY_MS comment above.
    const startTimer = setTimeout(() => {
      if (cancelled) return;

      setIsLoading(true);
      setError(null);

      // Subscribe to SSE stream (does hydrate-then-stream internally).
      // Pass the controller's signal so the hydrate fetch *and* the
      // long-poll SSE both abort on cleanup.
      streamCometEvents({
        signal: controller.signal,
        pollSeconds: 10,
        onUpdate: (serverComets) => {
          if (!cancelled) {
            setComets(serverComets);
            setIsLoading(false);
          }
        },
      })
        .then((stop) => {
          if (cancelled) {
            stop();
          } else {
            stopStream = stop;
          }
        })
        .catch((err) => {
          if (cancelled) return;
          // AbortError from a deliberate cleanup is normal noise —
          // suppress it from the surfaced error state.
          if (err instanceof Error && err.name === "AbortError") return;
          setIsLoading(false);
          setError(err instanceof Error ? err.message : "Stream connection failed");
        });

      // Periodic manual poll to trigger backend news fetching
      pollTimerRef.current = setInterval(() => {
        if (!cancelled) {
          pollComets().catch(() => {});
        }
      }, pollIntervalMs);

      // Initial poll to trigger first batch
      pollComets().catch(() => {});
    }, STREAM_START_DELAY_MS);

    return () => {
      cancelled = true;
      clearTimeout(startTimer);
      controller.abort();
      stopStream?.();
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [enabled, pollIntervalMs]);

  return { comets, isLoading, error };
}
