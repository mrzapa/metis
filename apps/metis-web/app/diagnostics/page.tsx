"use client";

import { useCallback, useEffect } from "react";
import { motion } from "motion/react";
import { AlertCircle, CheckCircle2, ClipboardCopy, Loader2, RotateCcw, ShieldAlert, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { GlowCard } from "@/components/ui/glow-card";
import { AnimatedLucideIcon } from "@/components/ui/animated-lucide-icon";
import { PageChrome } from "@/components/shell/page-chrome";
import {
  checkApiCompatibility,
  fetchApiVersion,
  fetchLogTail,
  fetchSettings,
  fetchUiTelemetrySummary,
  type LogTailResult,
  type UiTelemetrySummary,
  type UiTelemetrySummaryWindowHours,
  updateSettings,
} from "@/lib/api";
import { useArrowState } from "@/hooks/use-arrow-state";

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

interface SummaryState {
  loading: boolean;
  data: UiTelemetrySummary | null;
  error: string | null;
}

type RolloutAction = "rollback_runtime" | "rollback_artifacts";

const SUMMARY_WINDOWS: UiTelemetrySummaryWindowHours[] = [24, 168];

function formatPercent(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatNumber(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  return new Intl.NumberFormat("en-US").format(value);
}

function formatSettingValue(value: unknown): string {
  return typeof value === "boolean" ? String(value) : "unset";
}

function recommendationTone(recommendation: UiTelemetrySummary["thresholds"]["overall_recommendation"]) {
  switch (recommendation) {
    case "go":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400";
    case "hold":
      return "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400";
    case "rollback_runtime":
      return "border-orange-500/30 bg-orange-500/10 text-orange-700 dark:text-orange-400";
    case "rollback_artifacts":
      return "border-destructive/30 bg-destructive/10 text-destructive";
  }
}

function SettingPill({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="glass-tab-rail rounded-full px-3 py-1 text-xs text-muted-foreground">
      <span className="font-medium text-foreground">{label}</span>: {formatSettingValue(value)}
    </div>
  );
}

function SummaryMetric({ label, value, caption }: { label: string; value: string; caption: string }) {
  return (
    <GlowCard
      variant="liquid"
      liquidColor="#6366f1"
      intensity={0.65}
      allowCustomBackground
      className="p-0 rounded-[1rem] border border-white/10"
    >
      <div className="px-3 py-3">
        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
        <p className="mt-2 text-base font-semibold text-foreground">{value}</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{caption}</p>
      </div>
    </GlowCard>
  );
}

function RolloutSummaryCard({
  summary,
  windowHours,
  error,
  loading,
  settings,
  actionLoading,
  onAction,
}: {
  summary: UiTelemetrySummary | null;
  windowHours: UiTelemetrySummaryWindowHours;
  error: string | null;
  loading: boolean;
  settings: Record<string, unknown> | null;
  actionLoading: boolean;
  onAction: (action: RolloutAction) => void;
}) {
  const artifactsEnabled = settings?.enable_arrow_artifacts;
  const runtimeEnabled = settings?.enable_arrow_artifact_runtime;

  return (
    <Card data-testid={`artifact-rollout-${windowHours}h`} className="glass-panel border-white/12">
      <CardHeader className="space-y-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <CardTitle>{windowHours === 24 ? "Artifact rollout alert window" : "Artifact rollout decision window"}</CardTitle>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              {windowHours === 24
                ? "Use the 24h window for rollback decisions and incident response."
                : "Use the 7-day window for go/hold stage decisions once exposure minimums are met."}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <SettingPill label="Artifacts" value={artifactsEnabled} />
            <SettingPill label="Runtime" value={runtimeEnabled} />
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <div className="glass-settings-pane flex items-center gap-2 rounded-[1rem] px-4 py-4 text-sm text-muted-foreground">
            <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" />
            Loading {windowHours}h rollout summary…
          </div>
        ) : error ? (
          <div className="rounded-[1rem] border border-destructive/30 bg-destructive/10 px-4 py-4 text-sm text-destructive">
            <div className="flex items-center gap-2 font-medium">
              <AnimatedLucideIcon icon={AlertCircle} mode="idlePulse" className="size-4" />
              Failed to load {windowHours}h summary
            </div>
            <p className="mt-2 leading-6">{error}</p>
          </div>
        ) : !summary ? (
          <p className="glass-settings-pane rounded-[1rem] px-4 py-6 text-sm text-muted-foreground">
            No summary data available for this window.
          </p>
        ) : (
          <>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] ${recommendationTone(summary.thresholds.overall_recommendation)}`}
                >
                  Recommendation: {summary.thresholds.overall_recommendation.replace("_", " ")}
                </span>
                <span className="text-xs text-muted-foreground">
                  Generated {new Date(summary.generated_at).toLocaleString()}
                </span>
              </div>
              <span className="text-xs text-muted-foreground">
                Exposure {formatNumber(summary.thresholds.sample.exposure_count)} / {formatNumber(summary.thresholds.sample.minimum_exposure_count_for_go)} minimum
              </span>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <SummaryMetric
                label="Render success"
                value={formatPercent(summary.metrics.render_success_rate)}
                caption={`${formatNumber(summary.metrics.render_attempt_count)} render attempts`}
              />
              <SummaryMetric
                label="Render failure"
                value={formatPercent(summary.metrics.render_failure_rate)}
                caption="Artifact boundary reliability"
              />
              <SummaryMetric
                label="Runtime success"
                value={formatPercent(summary.metrics.runtime_success_rate)}
                caption={`${formatNumber(summary.thresholds.sample.runtime_attempt_count)} runtime attempts`}
              />
              <SummaryMetric
                label="Run ID quality"
                value={formatPercent(summary.metrics.data_quality.events_with_run_id_pct == null ? null : summary.metrics.data_quality.events_with_run_id_pct / 100)}
                caption={`${formatNumber(summary.sampled_event_count)} sampled events`}
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto]">
              <div className="glass-settings-pane space-y-3 rounded-[1rem] px-4 py-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Failed conditions</p>
                  {summary.thresholds.failed_conditions.length ? (
                    <ul className="mt-2 space-y-2 text-sm text-foreground">
                      {summary.thresholds.failed_conditions.map((condition) => (
                        <li key={condition} className="glass-tab-rail rounded-md px-3 py-2">
                          {condition}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 text-sm text-muted-foreground">No failed conditions for this window.</p>
                  )}
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <SummaryMetric
                    label="Interaction"
                    value={formatPercent(summary.metrics.interaction_rate)}
                    caption="Successful render engagement"
                  />
                  <SummaryMetric
                    label="Runtime failure"
                    value={formatPercent(summary.metrics.runtime_failure_rate)}
                    caption="Immediate runtime rollback trigger"
                  />
                </div>
              </div>

              <div className="glass-settings-pane min-w-0 space-y-3 rounded-[1rem] px-4 py-4 lg:w-72">
                <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Operator action</p>
                {summary.thresholds.overall_recommendation === "rollback_runtime" ? (
                  runtimeEnabled === false ? (
                    <p className="text-sm text-muted-foreground">Runtime is already disabled.</p>
                  ) : (
                    <Button
                      type="button"
                      variant="destructive"
                      className="w-full gap-2"
                      disabled={actionLoading}
                      onClick={() => onAction("rollback_runtime")}
                    >
                      {actionLoading ? <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" /> : <AnimatedLucideIcon icon={RotateCcw} mode="hoverLift" className="size-4" />}
                      Disable artifact runtime
                    </Button>
                  )
                ) : summary.thresholds.overall_recommendation === "rollback_artifacts" ? (
                  artifactsEnabled === false ? (
                    <p className="text-sm text-muted-foreground">Artifacts are already disabled.</p>
                  ) : (
                    <Button
                      type="button"
                      variant="destructive"
                      className="w-full gap-2"
                      disabled={actionLoading}
                      onClick={() => onAction("rollback_artifacts")}
                    >
                      {actionLoading ? <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" /> : <AnimatedLucideIcon icon={ShieldAlert} mode="hoverLift" className="size-4" />}
                      Disable artifacts
                    </Button>
                  )
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No rollback action is recommended for this window.
                  </p>
                )}
                <p className="text-xs leading-5 text-muted-foreground">
                  Confirmation is required before any rollback is applied. A successful action refreshes settings and both rollout summaries.
                </p>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function StatCard({
  label,
  value,
  caption,
  delay = 0,
}: {
  label: string;
  value: string;
  caption: string;
  delay?: number;
}) {
  return (
    <motion.div
      className="home-liquid-glass rounded-[1.2rem] px-4 py-3"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-2 font-mono text-lg text-foreground">{value}</p>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{caption}</p>
    </motion.div>
  );
}

export default function DiagnosticsPage() {
  const [loading, setLoading] = useArrowState(true);
  const [error, setError] = useArrowState<string | null>(null);
  const [versions, setVersions] = useArrowState<Versions | null>(null);
  const [compatibility, setCompatibility] = useArrowState<CompatibilityStatus | null>(null);
  const [settings, setSettings] = useArrowState<Record<string, unknown> | null>(null);
  const [logTail, setLogTail] = useArrowState<LogTailResult | null>(null);
  const [copied, setCopied] = useArrowState(false);
  const [actionError, setActionError] = useArrowState<string | null>(null);
  const [actionLoading, setActionLoading] = useArrowState(false);
  const [summary24h, setSummary24h] = useArrowState<SummaryState>({ loading: true, data: null, error: null });
  const [summary168h, setSummary168h] = useArrowState<SummaryState>({ loading: true, data: null, error: null });

  const loadBaseDiagnostics = useCallback(async () => {
    setLoading(true);
    setError(null);

    const [settingsResult, logResult, apiVersionResult, desktopVersionResult, compatibilityResult] = await Promise.allSettled([
      fetchSettings(),
      fetchLogTail(),
      fetchApiVersion(),
      resolveDesktopVersion(),
      checkApiCompatibility(),
    ]);

    if (settingsResult.status === "fulfilled") {
      setSettings(settingsResult.value);
    }
    if (logResult.status === "fulfilled") {
      setLogTail(logResult.value);
    }
    if (apiVersionResult.status === "fulfilled" || desktopVersionResult.status === "fulfilled") {
      setVersions({
        web: WEB_VERSION,
        api: apiVersionResult.status === "fulfilled" ? apiVersionResult.value : "—",
        desktop: desktopVersionResult.status === "fulfilled" ? desktopVersionResult.value : "unavailable",
      });
    }
    if (compatibilityResult.status === "fulfilled") {
      setCompatibility(compatibilityResult.value);
    }

    const failures = [settingsResult, logResult, apiVersionResult, compatibilityResult].filter(
      (result): result is PromiseRejectedResult => result.status === "rejected",
    );
    if (failures.length > 0) {
      const firstFailure = failures[0].reason;
      setError(firstFailure instanceof Error ? firstFailure.message : "Failed to load diagnostics");
    }

    setLoading(false);
  }, [setCompatibility, setError, setLoading, setLogTail, setSettings, setVersions]);

  const loadSummary = useCallback(async (windowHours: UiTelemetrySummaryWindowHours) => {
    const setState = windowHours === 24 ? setSummary24h : setSummary168h;
    setState({ loading: true, data: null, error: null });

    try {
      const summary = await fetchUiTelemetrySummary(windowHours);
      setState({ loading: false, data: summary, error: null });
    } catch (err) {
      setState({
        loading: false,
        data: null,
        error: err instanceof Error ? err.message : `Failed to load ${windowHours}h summary`,
      });
    }
  }, [setSummary168h, setSummary24h]);

  async function refreshRolloutConsole() {
    setActionError(null);
    const [settingsResult] = await Promise.allSettled([fetchSettings()]);
    if (settingsResult.status === "fulfilled") {
      setSettings(settingsResult.value);
    } else {
      setActionError(settingsResult.reason instanceof Error ? settingsResult.reason.message : "Failed to refresh settings");
    }

    await Promise.all(SUMMARY_WINDOWS.map((windowHours) => loadSummary(windowHours)));
  }

  useEffect(() => {
    void loadBaseDiagnostics();
    void Promise.all(SUMMARY_WINDOWS.map((windowHours) => loadSummary(windowHours)));
  }, [loadBaseDiagnostics, loadSummary]);

  async function handleCopy() {
    const bundle = {
      versions,
      settings,
      log_tail: logTail,
      rollout_summary_24h: summary24h.data,
      rollout_summary_168h: summary168h.data,
    };
    await navigator.clipboard.writeText(JSON.stringify(bundle, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  }

  async function handleRollback(action: RolloutAction) {
    const message =
      action === "rollback_runtime"
        ? "Disable artifact runtime rendering? Artifact cards and fallback rendering will remain enabled."
        : "Disable artifacts globally? Chat will return to markdown-only rendering.";

    if (typeof window !== "undefined" && !window.confirm(message)) {
      return;
    }

    setActionLoading(true);
    setActionError(null);
    try {
      if (action === "rollback_runtime") {
        await updateSettings({ enable_arrow_artifact_runtime: false });
      } else {
        await updateSettings({ enable_arrow_artifacts: false });
      }
      await refreshRolloutConsole();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to apply rollback action");
    } finally {
      setActionLoading(false);
    }
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
              <AnimatedLucideIcon icon={CheckCircle2} mode="idlePulse" className="size-4 text-green-600" />
              Copied
            </>
          ) : (
            <>
              <AnimatedLucideIcon icon={ClipboardCopy} mode="hoverLift" className="size-4" />
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
            delay={0}
          />
          <StatCard
            label="API"
            value={versions?.api ?? "—"}
            caption="Backend service version."
            delay={0.08}
          />
          <StatCard
            label="Desktop"
            value={versions?.desktop ?? "—"}
            caption={
              versions?.desktop === "unavailable"
                ? "Browser mode or no desktop bridge."
                : "Tauri shell version."
            }
            delay={0.16}
          />
        </section>

        {error && (
          <div className="flex items-center gap-2 rounded-[1.1rem] border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <AnimatedLucideIcon icon={AlertCircle} mode="idlePulse" className="size-4" />
            {error}
          </div>
        )}

        {compatibility && !compatibility.compatible && compatibility.warning && (
          <Card className="glass-panel border-yellow-500/40 bg-yellow-500/10">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base text-yellow-700 dark:text-yellow-400">
                <AnimatedLucideIcon icon={TriangleAlert} mode="idlePulse" className="size-4" />
                Compatibility warning
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-yellow-700 dark:text-yellow-400">
              {compatibility.warning}
            </CardContent>
          </Card>
        )}

        {loading ? (
          <div className="glass-panel flex items-center gap-2 rounded-[1.2rem] border-white/10 px-4 py-4 text-sm text-muted-foreground">
            <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" />
            Loading diagnostics…
          </div>
        ) : (
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.12fr)_minmax(20rem,0.88fr)]">
            <div className="space-y-6">
              <Card className="glass-panel-strong border-white/12">
                <CardHeader>
                  <CardTitle>Versions</CardTitle>
                </CardHeader>
                <CardContent>
                  <dl className="grid gap-x-4 gap-y-4 sm:grid-cols-2 xl:grid-cols-3">
                    <div className="glass-settings-pane rounded-[1rem] px-4 py-3">
                      <dt className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        Web
                      </dt>
                      <dd className="mt-2 font-mono text-base text-foreground">
                        {versions?.web ?? "—"}
                      </dd>
                    </div>
                    <div className="glass-settings-pane rounded-[1rem] px-4 py-3">
                      <dt className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        API
                      </dt>
                      <dd className="mt-2 font-mono text-base text-foreground">
                        {versions?.api ?? "—"}
                      </dd>
                    </div>
                    <div className="glass-settings-pane rounded-[1rem] px-4 py-3 sm:col-span-2 xl:col-span-1">
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

              <Card className="glass-panel-strong border-white/12">
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
                    <p className="glass-settings-pane rounded-[1rem] px-4 py-6 text-sm text-muted-foreground italic">
                      No log entries available.
                    </p>
                  ) : (
                    <pre className="glass-settings-pane max-h-128 overflow-auto rounded-[1rem] p-4 text-xs font-mono leading-relaxed text-foreground/90">
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

              <Card className="glass-panel-strong border-white/12">
                <CardHeader>
                  <CardTitle>Artifact rollout console</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm leading-6 text-muted-foreground">
                    This operator console combines the Phase 3 telemetry summary endpoint with the active artifact rollout flags so rollback decisions can be made in-product.
                  </p>
                  {actionError && (
                    <div className="rounded-[1rem] border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                      {actionError}
                    </div>
                  )}
                  <RolloutSummaryCard
                    summary={summary24h.data}
                    windowHours={24}
                    error={summary24h.error}
                    loading={summary24h.loading}
                    settings={settings}
                    actionLoading={actionLoading}
                    onAction={handleRollback}
                  />
                  <RolloutSummaryCard
                    summary={summary168h.data}
                    windowHours={168}
                    error={summary168h.error}
                    loading={summary168h.loading}
                    settings={settings}
                    actionLoading={actionLoading}
                    onAction={handleRollback}
                  />
                </CardContent>
              </Card>
            </div>

            <aside className="space-y-6 xl:sticky xl:top-24">
              <Card className="glass-panel-strong border-white/12">
                <CardHeader>
                  <CardTitle>Safe settings</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm leading-6 text-muted-foreground">
                    This is the redacted settings subset that can help spot bad provider state or mismatched local config at a glance.
                  </p>
                  {settings ? (
                    <pre className="glass-settings-pane max-h-112 overflow-auto rounded-[1rem] p-4 text-xs font-mono leading-relaxed text-foreground/90">
                      {JSON.stringify(settings, null, 2)}
                    </pre>
                  ) : (
                    <p className="glass-settings-pane rounded-[1rem] px-4 py-6 text-sm text-muted-foreground">
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
