"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, CheckCircle2, ChevronRight, ClipboardCopy, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { fetchSettings, fetchLogTail, fetchApiVersion, type LogTailResult } from "@/lib/api";

const WEB_VERSION = "1.0";

async function resolveDesktopVersion(): Promise<string> {
  if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
    try {
      const { getVersion } = await import("@tauri-apps/api/app");
      return await getVersion();
    } catch {
      return "unavailable";
    }
  }
  return "unavailable";
}

interface Versions {
  web: string;
  desktop: string;
  api: string;
}

export default function DiagnosticsPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [versions, setVersions] = useState<Versions | null>(null);
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null);
  const [logTail, setLogTail] = useState<LogTailResult | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    Promise.all([
      fetchSettings(),
      fetchLogTail(),
      fetchApiVersion(),
      resolveDesktopVersion(),
    ])
      .then(([s, lt, apiVer, desktopVer]) => {
        setSettings(s);
        setLogTail(lt);
        setVersions({ web: WEB_VERSION, api: apiVer, desktop: desktopVer });
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load diagnostics"))
      .finally(() => setLoading(false));
  }, []);

  async function handleCopy() {
    const bundle = {
      versions,
      settings,
      log_tail: logTail,
    };
    await navigator.clipboard.writeText(JSON.stringify(bundle, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Nav */}
      <header className="flex h-12 items-center gap-4 border-b px-6">
        <Link href="/" className="text-sm font-semibold tracking-tight">
          Axiom
        </Link>
        <ChevronRight className="size-3.5 text-muted-foreground" />
        <span className="text-sm text-muted-foreground">Diagnostics</span>
        <div className="ml-auto flex items-center gap-4">
          <Link href="/settings" className="text-sm text-muted-foreground hover:text-foreground">
            Settings
          </Link>
          <Link href="/chat" className="text-sm text-muted-foreground hover:text-foreground">
            Chat →
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-8 px-4 py-8">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-lg font-semibold">Diagnostics</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Version info, safe settings, and redacted log tail for bug reports.
            </p>
          </div>
          <Button
            onClick={handleCopy}
            disabled={loading || !!error}
            variant="outline"
            className="gap-1.5"
          >
            {copied ? (
              <>
                <CheckCircle2 className="size-4 text-green-600" />
                Copied
              </>
            ) : (
              <>
                <ClipboardCopy className="size-4" />
                Copy diagnostics
              </>
            )}
          </Button>
        </div>

        {error && (
          <div className="flex items-center gap-1.5 text-sm text-destructive">
            <AlertCircle className="size-4" />
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading diagnostics…
          </div>
        ) : (
          <>
            {/* Versions */}
            <section className="space-y-3">
              <h2 className="text-base font-semibold">Versions</h2>
              <Separator />
              <dl className="grid grid-cols-[10rem_1fr] gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">Web</dt>
                <dd className="font-mono">{versions?.web ?? "—"}</dd>
                <dt className="text-muted-foreground">API</dt>
                <dd className="font-mono">{versions?.api ?? "—"}</dd>
                <dt className="text-muted-foreground">Desktop</dt>
                <dd className="font-mono">
                  {versions?.desktop === "unavailable" ? (
                    <span className="text-muted-foreground italic">unavailable (browser mode)</span>
                  ) : (
                    versions?.desktop ?? "—"
                  )}
                </dd>
              </dl>
            </section>

            {/* Safe settings */}
            <section className="space-y-3">
              <h2 className="text-base font-semibold">Settings (safe subset)</h2>
              <Separator />
              {settings ? (
                <pre className="max-h-64 overflow-auto rounded-md border bg-muted/30 p-3 text-xs font-mono">
                  {JSON.stringify(settings, null, 2)}
                </pre>
              ) : (
                <p className="text-sm text-muted-foreground">No settings loaded.</p>
              )}
            </section>

            {/* Log tail */}
            <section className="space-y-3">
              <div className="flex items-center gap-3">
                <h2 className="text-base font-semibold">API log tail</h2>
                {logTail?.missing && (
                  <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs text-amber-700 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-400">
                    log file not found
                  </span>
                )}
                {!logTail?.missing && logTail && (
                  <span className="text-xs text-muted-foreground">
                    last {logTail.lines.length} of {logTail.total_lines ?? "?"} lines · redacted
                  </span>
                )}
              </div>
              <Separator />
              {logTail?.missing || !logTail?.lines.length ? (
                <p className="text-sm text-muted-foreground italic">No log entries available.</p>
              ) : (
                <pre className="max-h-96 overflow-auto rounded-md border bg-muted/30 p-3 text-xs font-mono leading-relaxed">
                  {logTail.lines.join("\n")}
                </pre>
              )}
              {logTail && (
                <p className="text-xs text-muted-foreground">
                  Path: <code className="font-mono">{logTail.log_path}</code>
                </p>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
