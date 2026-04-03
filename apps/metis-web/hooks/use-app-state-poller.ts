"use client";

import { useEffect, useRef, useState } from "react";
import { getAppState, pollSync, AppStateEntry } from "@/lib/api";

export interface AppStatePollerResult {
  appState: Record<string, string>;
  version: number;
  isLoading: boolean;
}

function entriesToRecord(entries: AppStateEntry | AppStateEntry[]): {
  record: Record<string, string>;
  maxVersion: number;
} {
  const arr = Array.isArray(entries) ? entries : [entries];
  const record = arr.reduce<Record<string, string>>(
    (acc, e) => ({ ...acc, [e.key]: e.value }),
    {},
  );
  const maxVersion = arr.length > 0 ? Math.max(...arr.map((e) => e.version)) : 0;
  return { record, maxVersion };
}

export function useAppStatePoller(
  sessionId: string | null,
  intervalMs = 2000,
): AppStatePollerResult {
  const [appState, setAppState] = useState<Record<string, string>>({});
  const [version, setVersion] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const versionRef = useRef<number>(0);

  useEffect(() => {
    if (!sessionId) {
      setAppState({});
      setVersion(0);
      versionRef.current = 0;
      return;
    }

    let cancelled = false;

    // Initial fetch
    setIsLoading(true);
    getAppState(sessionId)
      .then((entries) => {
        if (cancelled) return;
        const { record, maxVersion } = entriesToRecord(entries);
        setAppState(record);
        versionRef.current = maxVersion;
        setVersion(maxVersion);
      })
      .catch(() => {
        // ignore initial fetch errors
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    // Polling interval
    const interval = setInterval(async () => {
      if (cancelled) return;
      try {
        const result = await pollSync(versionRef.current);
        if (result.changed) {
          const entries = await getAppState(sessionId);
          if (cancelled) return;
          const { record } = entriesToRecord(entries);
          setAppState(record);
          versionRef.current = result.version;
          setVersion(result.version);
        }
      } catch {
        // ignore poll errors (network may be temporarily down)
      }
    }, intervalMs);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [sessionId, intervalMs]);

  return { appState, version, isLoading };
}
