"use client";

import { useEffect, useMemo, useRef } from "react";
import type { KeyboardEvent } from "react";
import { StructuredArtifactContent } from "@/components/chat/artifacts/structured-artifact-content";
import type { NormalizedArrowArtifact } from "@/lib/artifacts/extract-arrow-artifacts";
import { useArrowState } from "@/hooks/use-arrow-state";

type ArtifactRuntimeLifecycle = "attempt" | "success" | "failure" | "skipped";
type ArtifactRuntimeSkipReason =
  | "runtime_disabled"
  | "unsupported_type"
  | "payload_truncated"
  | "invalid_payload";

interface ArtifactRuntimeLifecycleEvent {
  lifecycle: ArtifactRuntimeLifecycle;
  artifact: NormalizedArrowArtifact;
  artifactIndex: number;
  skipReason?: ArtifactRuntimeSkipReason;
  errorName?: string;
}

type ArrowSandboxFactory = (options: {
  source: Record<string, string>;
  shadowDOM?: boolean;
  onError?: (error: Error | string) => void;
  debug?: boolean;
}) => (parent: ParentNode) => ParentNode;

let sandboxFactoryPromise: Promise<ArrowSandboxFactory> | null = null;

interface TimelinePayload {
  items: Array<{
    label: string;
    detail?: string;
    occurred_at?: string;
  }>;
}

interface MetricCardsPayload {
  metrics: Array<{
    label: string;
    value: string | number;
    delta?: string;
  }>;
}

interface ArtifactMessageContentProps {
  artifacts: NormalizedArrowArtifact[];
  runtimeEnabled?: boolean;
  onArtifactInteraction?: (artifact: NormalizedArrowArtifact, index: number) => void;
  onRuntimeLifecycleEvent?: (event: ArtifactRuntimeLifecycleEvent) => void;
}

interface ArtifactRuntimeState {
  lifecycle: ArtifactRuntimeLifecycle | "structured";
  skipReason?: ArtifactRuntimeSkipReason;
  errorName?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}

function asTimelinePayload(payload: unknown): TimelinePayload {
  const record = isRecord(payload) ? payload : {};
  const rawItems = Array.isArray(record.items) ? record.items : [];

  return {
    items: rawItems
      .filter((item) => isRecord(item) && typeof item.label === "string" && item.label.trim().length > 0)
      .map((item) => ({
        label: String(item.label).trim(),
        detail: typeof item.detail === "string" ? item.detail.trim() : "",
        occurred_at: typeof item.occurred_at === "string" ? item.occurred_at.trim() : "",
      })),
  };
}

function assertTimelineDates(payload: TimelinePayload): void {
  payload.items.forEach((item) => {
    if (!item.occurred_at) {
      return;
    }

    const parsed = new Date(item.occurred_at);
    if (Number.isNaN(parsed.getTime())) {
      throw new RangeError("Invalid timeline occurred_at value");
    }
  });
}

function asMetricCardsPayload(payload: unknown): MetricCardsPayload {
  const record = isRecord(payload) ? payload : {};
  const rawMetrics = Array.isArray(record.metrics) ? record.metrics : [];

  return {
    metrics: rawMetrics
      .filter((item) => {
        if (!isRecord(item) || typeof item.label !== "string" || item.label.trim().length === 0) {
          return false;
        }
        const value = item.value;
        return typeof value === "string" || (typeof value === "number" && Number.isFinite(value));
      })
      .map((item) => ({
        label: String(item.label).trim(),
        value: typeof item.value === "number" ? item.value : String(item.value),
        delta: typeof item.delta === "string" ? item.delta.trim() : "",
      })),
  };
}

function getErrorName(error: unknown): string {
  if (error instanceof Error) {
    return error.name || "Error";
  }

  return "Error";
}

function timelineSandboxSource(payload: TimelinePayload): Record<string, string> {
  assertTimelineDates(payload);

  return {
    "main.ts": `
import { html } from "@arrow-js/core";

const payload = ${JSON.stringify(payload)};
const items = Array.isArray(payload.items) ? payload.items : [];

const formatDate = (value) => {
  if (typeof value !== "string" || value.trim().length === 0) {
    return "";
  }
  return new Date(value).toISOString().slice(0, 10);
};

export default html\`<div class="space-y-2">
  <p class="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">Timeline</p>
  <ol class="space-y-2">
    \${() =>
      items.map(
        (item, index) =>
          html\`<li class="rounded-md border border-white/10 bg-white/5 px-2 py-1.5" data-arrow-item="\${() => String(index)}">
            <p class="text-sm font-medium text-foreground">\${() => String(item.label ?? "")}</p>
            \${() => {
              if (typeof item.detail === "string" && item.detail.trim().length > 0) {
                return html\`<p class="text-xs text-muted-foreground">\${() => item.detail.trim()}</p>\`;
              }
              return "";
            }}
            \${() => {
              const formatted = formatDate(item.occurred_at);
              if (!formatted) {
                return "";
              }
              return html\`<p class="mt-1 text-[11px] text-muted-foreground/80">\${() => formatted}</p>\`;
            }}
          </li>\`
      )}
  </ol>
</div>\`;
`.trim(),
  };
}

function metricCardsSandboxSource(payload: MetricCardsPayload): Record<string, string> {
  return {
    "main.ts": `
import { html } from "@arrow-js/core";

const payload = ${JSON.stringify(payload)};
const metrics = Array.isArray(payload.metrics) ? payload.metrics : [];

export default html\`<div class="space-y-2">
  <p class="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">Metrics</p>
  <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
    \${() =>
      metrics.map(
        (metric, index) =>
          html\`<div class="rounded-md border border-white/10 bg-white/5 px-2 py-1.5" data-arrow-metric="\${() => String(index)}">
            <p class="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">\${() => String(metric.label ?? "")}</p>
            <p class="text-lg font-semibold text-foreground">\${() => String(metric.value ?? "")}</p>
            \${() => {
              if (typeof metric.delta === "string" && metric.delta.trim().length > 0) {
                return html\`<p class="text-xs text-muted-foreground">\${() => metric.delta.trim()}</p>\`;
              }
              return "";
            }}
          </div>\`
      )}
  </div>
</div>\`;
`.trim(),
  };
}

function getArtifactSandboxSource(artifact: NormalizedArrowArtifact): Record<string, string> | null {
  if (artifact.type === "timeline") {
    return timelineSandboxSource(asTimelinePayload(artifact.payload));
  }

  if (artifact.type === "metric_cards") {
    return metricCardsSandboxSource(asMetricCardsPayload(artifact.payload));
  }

  return null;
}

async function loadSandboxFactory(): Promise<ArrowSandboxFactory> {
  if (!sandboxFactoryPromise) {
    sandboxFactoryPromise = import("@arrow-js/sandbox").then((module) => module.sandbox as ArrowSandboxFactory);
  }

  return sandboxFactoryPromise;
}

function RuntimeArtifactFallback({ artifact }: { artifact: NormalizedArrowArtifact }) {
  return (
    <>
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        {artifact.type}
      </p>
      {artifact.summary ? (
        <p className="mt-1 text-sm leading-relaxed text-foreground/95">{artifact.summary}</p>
      ) : (
        <p className="mt-1 text-sm italic leading-relaxed text-muted-foreground">No summary available.</p>
      )}
      {(artifact.path || artifact.mime_type) && (
        <p className="mt-1 text-[11px] text-muted-foreground/80">
          {[artifact.path, artifact.mime_type].filter(Boolean).join(" • ")}
        </p>
      )}
    </>
  );
}

function getSkipReasonLabel(reason?: ArtifactRuntimeSkipReason): string {
  if (reason === "runtime_disabled") {
    return "Runtime disabled";
  }
  if (reason === "unsupported_type") {
    return "Unsupported type";
  }
  if (reason === "payload_truncated") {
    return "Payload truncated";
  }
  return "Invalid payload";
}

function getRuntimeBadgeLabel(state: ArtifactRuntimeState): string {
  if (state.lifecycle === "structured") {
    return "Structured render";
  }
  if (state.lifecycle === "attempt") {
    return "Runtime loading";
  }
  if (state.lifecycle === "success") {
    return "Runtime ready";
  }
  if (state.lifecycle === "failure") {
    return `Runtime failed${state.errorName ? ` (${state.errorName})` : ""}`;
  }
  return `Runtime skipped: ${getSkipReasonLabel(state.skipReason)}`;
}

function getLiveRegionMessage(event: ArtifactRuntimeLifecycleEvent): string {
  const label = `Artifact ${event.artifactIndex + 1}`;
  if (event.lifecycle === "attempt") {
    return `${label} runtime loading`;
  }
  if (event.lifecycle === "success") {
    return `${label} runtime ready`;
  }
  if (event.lifecycle === "failure") {
    return `${label} runtime failed${event.errorName ? ` (${event.errorName})` : ""}`;
  }
  return `${label} runtime skipped: ${getSkipReasonLabel(event.skipReason)}`;
}

function getRuntimeBadgeClassName(state: ArtifactRuntimeState): string {
  if (state.lifecycle === "structured") {
    return "border-primary/35 bg-primary/10 text-primary";
  }
  if (state.lifecycle === "attempt") {
    return "border-blue-500/35 bg-blue-500/10 text-blue-200";
  }
  if (state.lifecycle === "success") {
    return "border-emerald-500/35 bg-emerald-500/10 text-emerald-200";
  }
  if (state.lifecycle === "failure") {
    return "border-amber-500/35 bg-amber-500/10 text-amber-200";
  }
  return "border-slate-500/35 bg-slate-500/10 text-slate-200";
}

function getArtifactDisplayLabel(artifact: NormalizedArrowArtifact, index: number): string {
  const fallbackLabel = `${artifact.type.replaceAll("_", " ")} ${index + 1}`;
  if (!artifact.summary) {
    return fallbackLabel;
  }
  const summary = artifact.summary.trim();
  if (!summary) {
    return fallbackLabel;
  }
  return summary.length > 40 ? `${summary.slice(0, 37)}...` : summary;
}

function ArrowRuntimeArtifact({
  artifact,
  artifactIndex,
  onRuntimeLifecycleEvent,
}: {
  artifact: NormalizedArrowArtifact;
  artifactIndex: number;
  onRuntimeLifecycleEvent?: (event: ArtifactRuntimeLifecycleEvent) => void;
}) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [runtimeReady, setRuntimeReady] = useArrowState(false);

  useEffect(() => {
    const mountPoint = mountRef.current;
    if (!mountPoint) {
      return;
    }

    let cancelled = false;
    let resolved = false;

    function markFailure(errorName: string) {
      if (resolved || cancelled) {
        return;
      }
      resolved = true;
      setRuntimeReady(false);
      onRuntimeLifecycleEvent?.({
        lifecycle: "failure",
        artifact,
        artifactIndex,
        errorName,
      });
    }

    function markSuccess() {
      if (resolved || cancelled) {
        return;
      }
      resolved = true;
      setRuntimeReady(true);
      onRuntimeLifecycleEvent?.({
        lifecycle: "success",
        artifact,
        artifactIndex,
      });
    }

    onRuntimeLifecycleEvent?.({
      lifecycle: "attempt",
      artifact,
      artifactIndex,
    });

    const render = async () => {
      try {
        const source = getArtifactSandboxSource(artifact);
        if (!source) {
          throw new Error("Unsupported artifact type");
        }

        const sandbox = await loadSandboxFactory();
        if (cancelled) {
          return;
        }

        mountPoint.replaceChildren();
        const view = sandbox({
          source,
          shadowDOM: false,
          onError: (error) => {
            markFailure(getErrorName(error));
          },
        });

        view(mountPoint);
        markSuccess();
      } catch (error) {
        markFailure(getErrorName(error));
      }
    };

    void render();

    return () => {
      cancelled = true;
      setRuntimeReady(false);
      mountPoint.replaceChildren();
    };
  }, [artifact, artifactIndex, onRuntimeLifecycleEvent, setRuntimeReady]);

  return (
    <>
      <div
        ref={mountRef}
        className={runtimeReady ? "block" : "hidden"}
        data-testid="arrow-artifact-runtime-host"
      />
      {!runtimeReady && <RuntimeArtifactFallback artifact={artifact} />}
    </>
  );
}

export function ArtifactMessageContent({
  artifacts,
  runtimeEnabled = true,
  onArtifactInteraction,
  onRuntimeLifecycleEvent,
}: ArtifactMessageContentProps) {
  const runtimeResults = useMemo(() => {
    return artifacts.map((artifact, index) => {
      const shouldUseStructured = artifact.render_kind === "structured";
      const shouldUseRuntime = artifact.render_kind === "runtime" && runtimeEnabled && artifact.runtime_eligible;
      const skipReason = artifact.render_kind === "runtime" && !runtimeEnabled
        ? "runtime_disabled"
        : (artifact.runtime_skip_reason as ArtifactRuntimeSkipReason | undefined);

      const lifecycleEvents: ArtifactRuntimeLifecycleEvent[] = [];

      if (!shouldUseRuntime && !shouldUseStructured) {
        lifecycleEvents.push({
          lifecycle: "skipped",
          artifact,
          artifactIndex: index,
          skipReason: skipReason ?? "invalid_payload",
        });
      }

      return {
        key: artifact.id || `${artifact.type}-${index}`,
        artifact,
        index,
        shouldUseStructured,
        shouldUseRuntime,
        lifecycleEvents,
      };
    });
  }, [artifacts, runtimeEnabled]);

  const [selectedIndex, setSelectedIndex] = useArrowState(0);
  const [liveRegionMessage, setLiveRegionMessage] = useArrowState("");
  const [runtimeStateByKey, setRuntimeStateByKey] = useArrowState<Record<string, ArtifactRuntimeState>>({});

  useEffect(() => {
    setSelectedIndex((current) => {
      if (runtimeResults.length === 0) {
        return 0;
      }
      return Math.min(current, runtimeResults.length - 1);
    });
  }, [runtimeResults.length, setSelectedIndex]);

  useEffect(() => {
    setRuntimeStateByKey((current) => {
      const next: Record<string, ArtifactRuntimeState> = {};

      runtimeResults.forEach((result) => {
        if (result.shouldUseStructured) {
          next[result.key] = {
            lifecycle: "structured",
          };
          return;
        }

        if (!result.shouldUseRuntime) {
          const skippedEvent = result.lifecycleEvents[0];
          next[result.key] = {
            lifecycle: "skipped",
            skipReason: skippedEvent?.skipReason,
          };
          return;
        }

        next[result.key] = current[result.key] ?? {
          lifecycle: "attempt",
        };
      });

      return next;
    });
  }, [runtimeResults, setRuntimeStateByKey]);

  function handleRuntimeLifecycleEvent(event: ArtifactRuntimeLifecycleEvent) {
    const artifactResult = runtimeResults[event.artifactIndex];
    if (artifactResult) {
      setRuntimeStateByKey((current) => ({
        ...current,
        [artifactResult.key]: {
          lifecycle: event.lifecycle,
          skipReason: event.skipReason,
          errorName: event.errorName,
        },
      }));
    }

    setLiveRegionMessage(getLiveRegionMessage(event));
    onRuntimeLifecycleEvent?.(event);
  }

  function handleCardInteraction(artifact: NormalizedArrowArtifact, index: number) {
    onArtifactInteraction?.(artifact, index);
  }

  function handleNavigatorSelection(index: number) {
    setSelectedIndex(index);
  }

  function handleCardKeyDown(
    event: KeyboardEvent<HTMLElement>,
    artifact: NormalizedArrowArtifact,
    index: number,
  ) {
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }
    event.preventDefault();
    handleCardInteraction(artifact, index);
  }

  const workspaceMode = runtimeResults.length > 1;
  const selectedResult = runtimeResults[selectedIndex] ?? runtimeResults[0];

  useEffect(() => {
    runtimeResults.forEach((result) => {
      result.lifecycleEvents.forEach((event) => {
        setLiveRegionMessage(getLiveRegionMessage(event));
        onRuntimeLifecycleEvent?.(event);
      });
    });
  }, [onRuntimeLifecycleEvent, runtimeResults, setLiveRegionMessage]);

  if (!selectedResult) {
    return null;
  }

  const selectedRuntimeState = runtimeStateByKey[selectedResult.key] ?? {
    lifecycle: selectedResult.shouldUseStructured
      ? "structured"
      : selectedResult.shouldUseRuntime
        ? "attempt"
        : "skipped",
    skipReason: selectedResult.lifecycleEvents[0]?.skipReason,
  };

  const isCardInteractive = Boolean(onArtifactInteraction);
  const selectedArtifactLabel = getArtifactDisplayLabel(selectedResult.artifact, selectedResult.index);
  const selectedPanelId = `arrow-artifact-panel-${selectedResult.index}`;
  const selectedRuntimeBadge = getRuntimeBadgeLabel(selectedRuntimeState);

  const selectedCard = (
    <div
      className="rounded-lg border border-white/12 bg-background/35 px-3 py-2"
      data-testid="arrow-artifact-card"
      data-artifact-index={selectedResult.index}
      data-artifact-id={selectedResult.artifact.id || ""}
      data-artifact-type={selectedResult.artifact.type}
      role={isCardInteractive ? "button" : undefined}
      tabIndex={isCardInteractive ? 0 : undefined}
      aria-label={`Artifact ${selectedResult.index + 1}: ${selectedArtifactLabel}`}
      onClick={
        isCardInteractive
          ? () => handleCardInteraction(selectedResult.artifact, selectedResult.index)
          : undefined
      }
      onKeyDown={
        isCardInteractive
          ? (event) => handleCardKeyDown(event, selectedResult.artifact, selectedResult.index)
          : undefined
      }
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="truncate text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          {selectedResult.artifact.type.replaceAll("_", " ")}
        </p>
        <span
          className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${getRuntimeBadgeClassName(selectedRuntimeState)}`}
          data-testid={`arrow-artifact-runtime-badge-${selectedResult.index}`}
        >
          {selectedRuntimeBadge}
        </span>
      </div>
      <div className="min-h-12">
        {selectedResult.shouldUseRuntime ? (
          <ArrowRuntimeArtifact
            artifact={selectedResult.artifact}
            artifactIndex={selectedResult.index}
            onRuntimeLifecycleEvent={handleRuntimeLifecycleEvent}
          />
        ) : selectedResult.shouldUseStructured ? (
          <StructuredArtifactContent artifact={selectedResult.artifact} />
        ) : (
          <RuntimeArtifactFallback artifact={selectedResult.artifact} />
        )}
      </div>
    </div>
  );

  return (
    <div className="space-y-2">
      {workspaceMode ? (
        <>
          <nav
            className="flex gap-1 overflow-x-auto pb-1"
            aria-label="Artifact navigator"
            data-testid="arrow-artifact-navigator"
          >
            {runtimeResults.map((result, index) => {
              const runtimeState = runtimeStateByKey[result.key] ?? {
                lifecycle: result.shouldUseStructured
                  ? "structured"
                  : result.shouldUseRuntime
                    ? "attempt"
                    : "skipped",
                skipReason: result.lifecycleEvents[0]?.skipReason,
              };
              const isSelected = selectedResult.index === result.index;

              return (
                <button
                  key={result.key}
                  type="button"
                  className={`inline-flex min-w-0 items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors ${
                    isSelected
                      ? "border-white/30 bg-white/12 text-foreground"
                      : "border-white/10 bg-white/5 text-muted-foreground hover:bg-white/8"
                  }`}
                  aria-pressed={isSelected}
                  aria-controls={selectedPanelId}
                  aria-label={`Select artifact ${index + 1}: ${getArtifactDisplayLabel(result.artifact, index)}`}
                  onClick={() => {
                    handleNavigatorSelection(index);
                  }}
                >
                  <span className="truncate">{getArtifactDisplayLabel(result.artifact, index)}</span>
                  <span className="text-[10px] opacity-80">{getRuntimeBadgeLabel(runtimeState)}</span>
                </button>
              );
            })}
          </nav>
          <div role="region" id={selectedPanelId} aria-label={`Artifact ${selectedResult.index + 1} details`}>
            {selectedCard}
          </div>
        </>
      ) : (
        selectedCard
      )}
      <p className="sr-only" aria-live="polite" aria-atomic="true" data-testid="arrow-artifact-runtime-live-region">
        {liveRegionMessage}
      </p>
    </div>
  );
}
