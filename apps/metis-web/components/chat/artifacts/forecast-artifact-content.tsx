"use client";

import { Badge } from "@/components/ui/badge";
import type { NormalizedArrowArtifact } from "@/lib/artifacts/extract-arrow-artifacts";

interface ForecastPoint {
  timestamp: string;
  value: number;
}

interface ForecastReportPayload {
  mapping: {
    file_path: string;
    file_name: string;
    timestamp_column: string;
    target_column: string;
    dynamic_covariates: string[];
    static_covariates: string[];
  };
  metadata: {
    horizon: number;
    context_used: number;
    model_backend: string;
    model_id: string;
    xreg_mode: string;
    frequency?: string;
    history_row_count?: number;
    future_row_count?: number;
  };
  history_points: ForecastPoint[];
  forecast_points: ForecastPoint[];
  quantiles: Record<string, ForecastPoint[]>;
  warnings: string[];
  session_state?: Record<string, unknown>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}

function toStringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function toNumberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => toStringValue(item)).filter(Boolean) : [];
}

function asPoint(value: unknown): ForecastPoint | null {
  if (!isRecord(value)) {
    return null;
  }
  const timestamp = toStringValue(value.timestamp);
  const numericValue = value.value;
  if (!timestamp || typeof numericValue !== "number" || !Number.isFinite(numericValue)) {
    return null;
  }
  return { timestamp, value: numericValue };
}

function asPoints(value: unknown): ForecastPoint[] {
  return Array.isArray(value)
    ? value.map((item) => asPoint(item)).filter((item): item is ForecastPoint => Boolean(item))
    : [];
}

function asForecastReportPayload(payload: unknown): ForecastReportPayload | null {
  if (!isRecord(payload) || !isRecord(payload.mapping) || !isRecord(payload.metadata)) {
    return null;
  }

  const historyPoints = asPoints(payload.history_points);
  const forecastPoints = asPoints(payload.forecast_points);
  if (historyPoints.length === 0 || forecastPoints.length === 0) {
    return null;
  }

  const quantilesRecord = isRecord(payload.quantiles) ? payload.quantiles : {};
  const quantiles: Record<string, ForecastPoint[]> = {};
  Object.entries(quantilesRecord).forEach(([key, value]) => {
    const points = asPoints(value);
    if (points.length > 0) {
      quantiles[key] = points;
    }
  });

  return {
    mapping: {
      file_path: toStringValue(payload.mapping.file_path),
      file_name: toStringValue(payload.mapping.file_name),
      timestamp_column: toStringValue(payload.mapping.timestamp_column),
      target_column: toStringValue(payload.mapping.target_column),
      dynamic_covariates: toStringArray(payload.mapping.dynamic_covariates),
      static_covariates: toStringArray(payload.mapping.static_covariates),
    },
    metadata: {
      horizon: toNumberValue(payload.metadata.horizon),
      context_used: toNumberValue(payload.metadata.context_used),
      model_backend: toStringValue(payload.metadata.model_backend),
      model_id: toStringValue(payload.metadata.model_id),
      xreg_mode: toStringValue(payload.metadata.xreg_mode),
      frequency: toStringValue(payload.metadata.frequency),
      history_row_count: toNumberValue(payload.metadata.history_row_count),
      future_row_count: toNumberValue(payload.metadata.future_row_count),
    },
    history_points: historyPoints,
    forecast_points: forecastPoints,
    quantiles,
    warnings: toStringArray(payload.warnings),
    session_state: isRecord(payload.session_state) ? payload.session_state : undefined,
  };
}

function formatValue(value: number): string {
  if (!Number.isFinite(value)) {
    return "n/a";
  }
  const rounded = Number(value.toFixed(4));
  if (Math.abs(rounded) >= 100 || Number.isInteger(rounded)) {
    return rounded.toFixed(2);
  }
  return String(rounded);
}

function buildLinePath(points: ForecastPoint[], width: number, height: number, min: number, max: number): string {
  if (points.length === 0 || min === max) {
    return "";
  }
  return points
    .map((point, index) => {
      const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width;
      const y = height - ((point.value - min) / (max - min)) * height;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function buildBandPath(
  lower: ForecastPoint[],
  upper: ForecastPoint[],
  width: number,
  height: number,
  min: number,
  max: number,
): string {
  if (lower.length === 0 || upper.length === 0 || lower.length !== upper.length || min === max) {
    return "";
  }

  const top = upper.map((point, index) => {
    const x = upper.length === 1 ? width / 2 : (index / (upper.length - 1)) * width;
    const y = height - ((point.value - min) / (max - min)) * height;
    return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
  });
  const bottom = lower
    .map((point, index) => {
      const reverseIndex = lower.length - 1 - index;
      const x = lower.length === 1 ? width / 2 : (reverseIndex / (lower.length - 1)) * width;
      const y = height - ((lower[reverseIndex].value - min) / (max - min)) * height;
      return `L ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");

  return `${top.join(" ")} ${bottom} Z`;
}

function EmptyArtifactState({ message }: { message: string }) {
  return <p className="text-sm leading-relaxed text-muted-foreground">{message}</p>;
}

export function ForecastArtifactContent({ artifact }: { artifact: NormalizedArrowArtifact }) {
  const payload = asForecastReportPayload(artifact.payload);
  if (!payload) {
    return <EmptyArtifactState message="Forecast report details were unavailable." />;
  }

  const history = payload.history_points;
  const forecast = payload.forecast_points;
  const lowerBand = payload.quantiles.p10 ?? payload.quantiles.p20 ?? [];
  const upperBand = payload.quantiles.p90 ?? payload.quantiles.p80 ?? [];
  const allValues = [...history, ...forecast, ...lowerBand, ...upperBand].map((point) => point.value);
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const historyPath = buildLinePath(history, 100, 44, min, max);
  const forecastPath = buildLinePath(forecast, 100, 44, min, max);
  const bandPath = buildBandPath(lowerBand, upperBand, 100, 44, min, max);
  const lastHistory = history[history.length - 1];
  const lastForecast = forecast[forecast.length - 1];

  return (
    <div className="space-y-3" data-testid="forecast-report-artifact">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-1">
          <p className="text-sm leading-relaxed text-foreground/95">
            {artifact.summary || `${payload.mapping.target_column} forecast`}
          </p>
          <p className="text-xs text-muted-foreground">
            {payload.mapping.file_name} · {payload.mapping.timestamp_column} → {payload.mapping.target_column}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="outline">{payload.metadata.horizon} steps</Badge>
          {payload.metadata.frequency ? <Badge variant="outline">{payload.metadata.frequency}</Badge> : null}
          {payload.metadata.xreg_mode ? <Badge variant="outline">{payload.metadata.xreg_mode}</Badge> : null}
        </div>
      </div>

      <div className="rounded-xl border border-white/10 bg-black/10 px-3 py-3">
        <svg viewBox="0 0 100 44" className="h-44 w-full overflow-visible">
          <line x1="0" y1="43" x2="100" y2="43" className="stroke-white/10" strokeWidth="0.4" />
          {bandPath ? (
            <path d={bandPath} fill="rgba(125, 211, 252, 0.18)" stroke="none" />
          ) : null}
          {historyPath ? (
            <path d={historyPath} fill="none" stroke="rgba(244, 208, 63, 0.95)" strokeWidth="1.4" />
          ) : null}
          {forecastPath ? (
            <path d={forecastPath} fill="none" stroke="rgba(96, 165, 250, 0.95)" strokeWidth="1.6" />
          ) : null}
        </svg>
        <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
          <p>Last observed: <span className="text-foreground">{formatValue(lastHistory.value)}</span></p>
          <p>Final forecast: <span className="text-foreground">{formatValue(lastForecast.value)}</span></p>
          <p>Context used: <span className="text-foreground">{payload.metadata.context_used}</span></p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <section className="rounded-lg border border-white/10 bg-background/30 px-3 py-2">
          <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-primary/80">Covariates</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {payload.mapping.dynamic_covariates.map((item) => (
              <Badge key={`dynamic:${item}`} variant="secondary">{item}</Badge>
            ))}
            {payload.mapping.static_covariates.map((item) => (
              <Badge key={`static:${item}`} variant="outline">{item}</Badge>
            ))}
            {payload.mapping.dynamic_covariates.length === 0 && payload.mapping.static_covariates.length === 0 ? (
              <p className="text-xs text-muted-foreground">Univariate run</p>
            ) : null}
          </div>
        </section>

        <section className="rounded-lg border border-white/10 bg-background/30 px-3 py-2">
          <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-primary/80">Model</p>
          <p className="mt-2 break-all text-xs text-foreground">{payload.metadata.model_backend}</p>
          <p className="mt-1 break-all text-[11px] text-muted-foreground">{payload.metadata.model_id}</p>
        </section>
      </div>

      {payload.warnings.length > 0 ? (
        <section className="rounded-lg border border-amber-500/20 bg-amber-500/8 px-3 py-2">
          <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-amber-200">Warnings</p>
          <ul className="mt-2 space-y-1 text-xs text-amber-100/90">
            {payload.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

