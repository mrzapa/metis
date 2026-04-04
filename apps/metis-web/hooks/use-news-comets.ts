"use client";

import { useEffect, useRef, useState } from "react";
import { streamCometEvents, pollComets } from "@/lib/api";
import type { CometEvent } from "@/lib/comet-types";

export interface UseCometNewsResult {
  /** Currently active comet events from the server. */
  comets: CometEvent[];
  /** Whether the initial fetch is in progress. */
  isLoading: boolean;
}

/**
 * Hook that subscribes to comet-news events via SSE (hydrate-then-stream).
 *
 * Maintains a live list of active comets and triggers a manual poll on
 * mount to kick off the backend's news cycle.
 */
export function useCometNews(
  enabled: boolean,
  pollIntervalMs = 300_000,
): UseCometNewsResult {
  const [comets, setComets] = useState<CometEvent[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!enabled) {
      setComets([]);
      return;
    }

    let cancelled = false;
    let stopStream: (() => void) | null = null;

    setIsLoading(true);

    // Subscribe to SSE stream (does hydrate-then-stream internally)
    streamCometEvents({
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
      .catch(() => {
        if (!cancelled) setIsLoading(false);
      });

    // Periodic manual poll to trigger backend news fetching
    pollTimerRef.current = setInterval(() => {
      if (!cancelled) {
        pollComets().catch(() => {});
      }
    }, pollIntervalMs);

    // Initial poll to trigger first batch
    pollComets().catch(() => {});

    return () => {
      cancelled = true;
      stopStream?.();
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [enabled, pollIntervalMs]);

  return { comets, isLoading };
}
