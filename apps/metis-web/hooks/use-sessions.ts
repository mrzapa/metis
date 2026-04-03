"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchSessions, type SessionSummary } from "@/lib/api";

export function useSessions(search: string) {
  const [debounced, setDebounced] = useState(search);
  const [reloadKey, setReloadKey] = useState(0);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Debounce search input by 300 ms
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchSessions(debounced, controller.signal)
      .then((data) => {
        setSessions(data);
        setLoading(false);
      })
      .catch((err) => {
        if (err instanceof Error && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Failed to load sessions");
        setSessions([]);
        setLoading(false);
      });
    return () => controller.abort();
  }, [debounced, reloadKey]);

  const reload = useCallback(() => setReloadKey((k) => k + 1), []);

  return { sessions, loading, error, reload };
}

