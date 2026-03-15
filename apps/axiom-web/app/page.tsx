"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getApiBase } from "@/lib/api";

type Status = "connected" | "disconnected" | "checking";

export default function Home() {
  const [status, setStatus] = useState<Status>("checking");
  const [sidecarError, setSidecarError] = useState<string | null>(null);

  // Listen for the sidecar-timeout event emitted by the Tauri host so we can
  // show a user-friendly message when the local API never becomes available.
  useEffect(() => {
    if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) {
      return;
    }
    let unlisten: (() => void) | undefined;
    import("@tauri-apps/api/event").then(({ listen }) => {
      listen<string>("sidecar-timeout", (event) => {
        setSidecarError(event.payload);
        setStatus("disconnected");
      }).then((fn) => {
        unlisten = fn;
      });
    });
    return () => unlisten?.();
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const base = await getApiBase();
        const res = await fetch(`${base}/healthz`);
        const data = await res.json();
        if (!cancelled) setStatus(data.ok ? "connected" : "disconnected");
      } catch {
        if (!cancelled) setStatus("disconnected");
      }
    }

    check();
    const id = setInterval(check, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 p-8">
      <h1 className="text-4xl font-bold tracking-tight">
        Axiom <span className="text-lg font-normal text-zinc-500">(Local-first)</span>
      </h1>

      {sidecarError && (
        <div className="max-w-sm rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
          {sidecarError}
        </div>
      )}

      <div className="flex items-center gap-2 text-sm">
        <span
          className={`inline-block h-3 w-3 rounded-full ${
            status === "connected"
              ? "bg-green-500"
              : status === "disconnected"
                ? "bg-red-500"
                : "bg-yellow-500 animate-pulse"
          }`}
        />
        <span>
          {status === "connected"
            ? "Connected"
            : status === "disconnected"
              ? "Disconnected"
              : "Checking\u2026"}
        </span>
      </div>

      <div className="flex flex-col items-center gap-3 sm:flex-row">
        <Link
          href="/chat"
          className="rounded-full border border-foreground/20 px-6 py-2 text-sm font-medium transition-colors hover:bg-foreground/5"
        >
          Go to Chat
        </Link>
        <Link
          href="/library"
          className="rounded-full border border-foreground/20 px-6 py-2 text-sm font-medium transition-colors hover:bg-foreground/5"
        >
          Build an Index
        </Link>
        <Link
          href="/settings"
          className="rounded-full border border-foreground/20 px-6 py-2 text-sm font-medium transition-colors hover:bg-foreground/5"
        >
          Settings
        </Link>
      </div>
    </div>
  );
}
