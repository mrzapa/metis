"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type Status = "connected" | "disconnected" | "checking";

export default function Home() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const res = await fetch("http://127.0.0.1:8000/healthz");
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

      <Link
        href="/chat"
        className="rounded-full border border-foreground/20 px-6 py-2 text-sm font-medium transition-colors hover:bg-foreground/5"
      >
        Go to Chat
      </Link>
    </div>
  );
}
