const MAX_ARROW_ARTIFACTS = 5;

const RUNTIME_SUPPORTED_TYPES = new Set(["timeline", "metric_cards"]);
const STRUCTURED_SUPPORTED_TYPES = new Set([
  "forecast_report",
  "nyx_component_selection",
  "nyx_install_plan",
  "nyx_dependency_report",
]);

export type ArtifactRenderKind = "runtime" | "structured" | "fallback";

export type ArtifactRuntimeSkipReason =
  | "unsupported_type"
  | "payload_truncated"
  | "invalid_payload";

export interface NormalizedArrowArtifact {
  id: string;
  type: string;
  summary: string;
  path: string;
  mime_type: string;
  payload?: unknown;
  payload_bytes: number;
  payload_truncated: boolean;
  render_kind: ArtifactRenderKind;
  runtime_eligible: boolean;
  runtime_skip_reason?: ArtifactRuntimeSkipReason;
}

export interface ArrowArtifactExtractionResult {
  hasArtifacts: boolean;
  isValid: boolean;
  artifacts: NormalizedArrowArtifact[];
  error?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}

function toStringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function toNumberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : 0;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => toStringValue(item).length > 0);
}

function isTimelinePayload(payload: unknown): boolean {
  if (!isRecord(payload)) {
    return false;
  }

  const rawItems = payload.items;
  if (!Array.isArray(rawItems) || rawItems.length === 0 || rawItems.length > 20) {
    return false;
  }

  return rawItems.every((item) => {
    if (!isRecord(item)) {
      return false;
    }

    const label = toStringValue(item.label);
    if (!label) {
      return false;
    }

    if (item.occurred_at !== undefined && toStringValue(item.occurred_at) === "") {
      return false;
    }

    return true;
  });
}

function isMetricCardsPayload(payload: unknown): boolean {
  if (!isRecord(payload)) {
    return false;
  }

  const rawMetrics = payload.metrics;
  if (!Array.isArray(rawMetrics) || rawMetrics.length === 0 || rawMetrics.length > 12) {
    return false;
  }

  return rawMetrics.every((item) => {
    if (!isRecord(item)) {
      return false;
    }

    const label = toStringValue(item.label);
    if (!label) {
      return false;
    }

    const value = item.value;
    return (
      typeof value === "string" ||
      (typeof value === "number" && Number.isFinite(value))
    );
  });
}

function isNyxSelectedComponentPayload(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }

  const componentName = toStringValue(value.component_name);
  const installTarget = toStringValue(value.install_target);
  if (!componentName || !installTarget) {
    return false;
  }

  return [
    value.targets,
    value.preview_targets,
    value.required_dependencies,
    value.dependencies,
    value.dev_dependencies,
    value.registry_dependencies,
    value.match_reasons,
  ].every((entry) => entry === undefined || isStringArray(entry));
}

function isNyxComponentSelectionPayload(payload: unknown): boolean {
  if (!isRecord(payload)) {
    return false;
  }

  const rawComponents = payload.selected_components;
  if (!Array.isArray(rawComponents) || rawComponents.length === 0) {
    return false;
  }

  return rawComponents.every((item) => isNyxSelectedComponentPayload(item));
}

function isNyxInstallPlanStep(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }

  return Boolean(toStringValue(value.label) || toStringValue(value.command));
}

function isNyxInstallPlanComponent(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }

  const componentName = toStringValue(value.component_name);
  const installTarget = toStringValue(value.install_target);
  const steps = value.steps;
  if (!componentName || !installTarget || !Array.isArray(steps) || steps.length === 0) {
    return false;
  }

  return (
    steps.every((step) => isNyxInstallPlanStep(step))
    && (value.targets === undefined || isStringArray(value.targets))
    && (value.dependency_packages === undefined || isStringArray(value.dependency_packages))
  );
}

function isNyxInstallPlanPayload(payload: unknown): boolean {
  if (!isRecord(payload)) {
    return false;
  }

  const rawComponents = payload.components;
  if (!Array.isArray(rawComponents) || rawComponents.length === 0) {
    return false;
  }

  return rawComponents.every((item) => isNyxInstallPlanComponent(item));
}

function isNyxDependencyEntry(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }

  const packageName = toStringValue(value.package_name);
  const dependencyType = toStringValue(value.dependency_type);
  if (!packageName || !dependencyType) {
    return false;
  }

  return [value.required_by, value.install_targets, value.registry_urls].every(
    (entry) => entry === undefined || isStringArray(entry),
  );
}

function isNyxDependencyReportPayload(payload: unknown): boolean {
  if (!isRecord(payload)) {
    return false;
  }

  const rawGroups = isRecord(payload.groups) ? payload.groups : null;
  if (!rawGroups) {
    return false;
  }

  const groups = [rawGroups.required, rawGroups.runtime, rawGroups.dev, rawGroups.registry];
  return groups.every(
    (group) => Array.isArray(group) && group.every((entry) => isNyxDependencyEntry(entry)),
  );
}

function isForecastPoint(value: unknown): boolean {
  return (
    isRecord(value)
    && toStringValue(value.timestamp).length > 0
    && typeof value.value === "number"
    && Number.isFinite(value.value)
  );
}

function isForecastReportPayload(payload: unknown): boolean {
  if (!isRecord(payload) || !isRecord(payload.mapping) || !isRecord(payload.metadata)) {
    return false;
  }

  const historyPoints = payload.history_points;
  const forecastPoints = payload.forecast_points;
  if (
    !Array.isArray(historyPoints)
    || !Array.isArray(forecastPoints)
    || historyPoints.length === 0
    || forecastPoints.length === 0
  ) {
    return false;
  }

  if (!historyPoints.every((point) => isForecastPoint(point)) || !forecastPoints.every((point) => isForecastPoint(point))) {
    return false;
  }

  const quantiles = isRecord(payload.quantiles) ? payload.quantiles : {};
  return Object.values(quantiles).every(
    (series) => Array.isArray(series) && series.every((point) => isForecastPoint(point)),
  );
}

function resolveArtifactRendering(
  type: string,
  payload: unknown,
  payloadTruncated: boolean,
): {
  renderKind: ArtifactRenderKind;
  runtimeEligible: boolean;
  runtimeSkipReason?: ArtifactRuntimeSkipReason;
} {
  if (payloadTruncated) {
    return {
      renderKind: "fallback",
      runtimeEligible: false,
      runtimeSkipReason: "payload_truncated",
    };
  }

  if (RUNTIME_SUPPORTED_TYPES.has(type)) {
    const isValidPayload =
      type === "timeline"
        ? isTimelinePayload(payload)
        : type === "metric_cards"
          ? isMetricCardsPayload(payload)
          : false;

    if (!isValidPayload) {
      return {
        renderKind: "fallback",
        runtimeEligible: false,
        runtimeSkipReason: "invalid_payload",
      };
    }

    return { renderKind: "runtime", runtimeEligible: true };
  }

  if (STRUCTURED_SUPPORTED_TYPES.has(type)) {
    const isValidPayload =
      type === "forecast_report"
        ? isForecastReportPayload(payload)
        : type === "nyx_component_selection"
        ? isNyxComponentSelectionPayload(payload)
        : type === "nyx_install_plan"
          ? isNyxInstallPlanPayload(payload)
          : type === "nyx_dependency_report"
            ? isNyxDependencyReportPayload(payload)
            : false;

    if (!isValidPayload) {
      return {
        renderKind: "fallback",
        runtimeEligible: false,
        runtimeSkipReason: "invalid_payload",
      };
    }

    return { renderKind: "structured", runtimeEligible: false };
  }

  return {
    renderKind: "fallback",
    runtimeEligible: false,
    runtimeSkipReason: "unsupported_type",
  };
}

export function extractArrowArtifacts(rawArtifacts: unknown): ArrowArtifactExtractionResult {
  if (!Array.isArray(rawArtifacts) || rawArtifacts.length === 0) {
    return {
      hasArtifacts: false,
      isValid: false,
      artifacts: [],
    };
  }

  const normalized: NormalizedArrowArtifact[] = [];

  for (const item of rawArtifacts.slice(0, MAX_ARROW_ARTIFACTS)) {
    if (!isRecord(item)) {
      return {
        hasArtifacts: true,
        isValid: false,
        artifacts: [],
        error: "Artifact payload includes a non-object item.",
      };
    }

    const type = toStringValue(item.type);
    if (!type) {
      return {
        hasArtifacts: true,
        isValid: false,
        artifacts: [],
        error: "Artifact payload is missing a valid type.",
      };
    }

    const payloadTruncated = Boolean(item.payload_truncated);
    const renderState = resolveArtifactRendering(type, item.payload, payloadTruncated);

    normalized.push({
      id: toStringValue(item.id),
      type,
      summary: toStringValue(item.summary),
      path: toStringValue(item.path),
      mime_type: toStringValue(item.mime_type),
      payload: item.payload,
      payload_bytes: toNumberValue(item.payload_bytes),
      payload_truncated: payloadTruncated,
      render_kind: renderState.renderKind,
      runtime_eligible: renderState.runtimeEligible,
      runtime_skip_reason: renderState.runtimeSkipReason,
    });
  }

  return {
    hasArtifacts: normalized.length > 0,
    isValid: normalized.length > 0,
    artifacts: normalized,
  };
}
