"use client";

import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, ClipboardCopy, Loader2, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageChrome } from "@/components/shell/page-chrome";
import { fetchSettings, fetchLogTail, fetchApiVersion, checkApiCompatibility, type LogTailResult } from "@/lib/api";

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

interface CompatibilityStatus {
  compatible: boolean;
  warning: string | null;
}

function StatCard({
  label,
  value,
  caption,
}: {
  label: string;
  value: string;
  caption: string;
}) {
  return (
    <div className="rounded-[1.2rem] border border-white/8 bg-black/10 px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-2 font-mono text-lg text-foreground">{value}</p>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{caption}</p>
    </div>
  );
}

export default function DiagnosticsPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [versions, setVersions] = useState<Versions | null>(null);
  const [compatibility, setCompatibility] = useState<CompatibilityStatus | null>(null);
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null);
  const [logTail, setLogTail] = useState<LogTailResult | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    Promise.all([
      fetchSettings(),
      fetchLogTail(),
      fetchApiVersion(),
      resolveDesktopVersion(),
      checkApiCompatibility(),
    ])
      .then(([s, lt, apiVer, desktopVer, compat]) => {
        setSettings(s);
        setLogTail(lt);
        setVersions({ web: WEB_VERSION, api: apiVer, desktop: desktopVer });
        setCompatibility(compat);
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
    <PageChrome
      eyebrow="Diagnostics"
      title="System health and logs"
      description="Check API compatibility, view logs, and inspect settings. Useful for troubleshooting startup or connection issues."
      actions={
        <Button
          onClick={handleCopy}
          disabled={loading || !!error}
          variant="outline"
          className="shrink-0 gap-1.5"
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
      }
      heroAside={
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
            Recovery posture
          </p>
          <p className="text-sm leading-7 text-muted-foreground">
            Version mismatches, safe settings, and the redacted API log tail all live here so startup and runtime failures are easier to diagnose.
          </p>
        </div>
      }
    >
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <section className="grid gap-3 md:grid-cols-3">
          <StatCard
            label="Web"
            value={versions?.web ?? "1.0"}
            caption="Frontend build version."
          />
          <StatCard
            label="API"
            value={versions?.api ?? "—"}
            caption="Backend service version."
          />
          <StatCard
            label="Desktop"
            value={versions?.desktop ?? "—"}
            caption={
              versions?.desktop === "unavailable"
                ? "Browser mode or no desktop bridge."
                : "Tauri shell version."
            }
          />
        </section>

        {error && (
          <div className="flex items-center gap-2 rounded-[1.1rem] border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <AlertCircle className="size-4" />
            {error}
          </div>
        )}

        {compatibility && !compatibility.compatible && compatibility.warning && (
          <Card className="border-yellow-500/40 bg-yellow-500/10">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base text-yellow-700 dark:text-yellow-400">
                <TriangleAlert className="size-4" />
                Compatibility warning
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-yellow-700 dark:text-yellow-400">
              {compatibility.warning}
            </CardContent>
          </Card>
        )}

        {loading ? (
          <div className="flex items-center gap-2 rounded-[1.2rem] border border-white/8 bg-black/10 px-4 py-4 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading diagnostics…
          </div>
        ) : (
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.12fr)_minmax(20rem,0.88fr)]">
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>Versions</CardTitle>
                </CardHeader>
                <CardContent>
                  <dl className="grid gap-x-4 gap-y-4 sm:grid-cols-2 xl:grid-cols-3">
                    <div className="rounded-[1rem] border border-white/8 bg-black/10 px-4 py-3">
                      <dt className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        Web
                      </dt>
                      <dd className="mt-2 font-mono text-base text-foreground">
                        {versions?.web ?? "—"}
                      </dd>
                    </div>
                    <div className="rounded-[1rem] border border-white/8 bg-black/10 px-4 py-3">
                      <dt className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        API
                      </dt>
                      <dd className="mt-2 font-mono text-base text-foreground">
                        {versions?.api ?? "—"}
                      </dd>
                    </div>
                    <div className="rounded-[1rem] border border-white/8 bg-black/10 px-4 py-3 sm:col-span-2 xl:col-span-1">
                      <dt className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        Desktop
                      </dt>
                      <dd className="mt-2 font-mono text-base text-foreground">
                        {versions?.desktop === "unavailable" ? (
                          <span className="text-muted-foreground italic">
                            unavailable (browser mode)
                          </span>
                        ) : (
                          versions?.desktop ?? "—"
                        )}
                      </dd>
                    </div>
                  </dl>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>API log tail</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
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
                  {logTail?.missing || !logTail?.lines.length ? (
                    <p className="rounded-[1rem] border border-white/8 bg-black/10 px-4 py-6 text-sm text-muted-foreground italic">
                      No log entries available.
                    </p>
                  ) : (
                    <pre className="max-h-[32rem] overflow-auto rounded-[1rem] border border-white/8 bg-black/10 p-4 text-xs font-mono leading-relaxed text-foreground/90">
                      {logTail.lines.join("\n")}
                    </pre>
                  )}
                  {logTail && (
                    <p className="text-xs text-muted-foreground">
                      Path: <code className="font-mono">{logTail.log_path}</code>
                    </p>
                  )}
                </CardContent>
              </Card>
            </div>

            <aside className="space-y-6 xl:sticky xl:top-24">
              <Card>
                <CardHeader>
                  <CardTitle>Safe settings</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm leading-6 text-muted-foreground">
                    This is the redacted settings subset that can help spot bad provider state or mismatched local config at a glance.
                  </p>
                  {settings ? (
                    <pre className="max-h-[28rem] overflow-auto rounded-[1rem] border border-white/8 bg-black/10 p-4 text-xs font-mono leading-relaxed text-foreground/90">
                      {JSON.stringify(settings, null, 2)}
                    </pre>
                  ) : (
                    <p className="rounded-[1rem] border border-white/8 bg-black/10 px-4 py-6 text-sm text-muted-foreground">
                      No settings loaded.
                    </p>
                  )}
                </CardContent>
              </Card>
            </aside>
          </div>
        )}
      </div>
    </PageChrome>
  );
}
