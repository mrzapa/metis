const MAX_ARROW_ARTIFACTS = 5;

const RUNTIME_SUPPORTED_TYPES = new Set(["timeline", "metric_cards"]);

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

function resolveRuntimeEligibility(
  type: string,
  payload: unknown,
  payloadTruncated: boolean,
): { runtimeEligible: boolean; runtimeSkipReason?: ArtifactRuntimeSkipReason } {
  if (payloadTruncated) {
    return { runtimeEligible: false, runtimeSkipReason: "payload_truncated" };
  }

  if (!RUNTIME_SUPPORTED_TYPES.has(type)) {
    return { runtimeEligible: false, runtimeSkipReason: "unsupported_type" };
  }

  const isValidPayload =
    type === "timeline"
      ? isTimelinePayload(payload)
      : type === "metric_cards"
        ? isMetricCardsPayload(payload)
        : false;

  if (!isValidPayload) {
    return { runtimeEligible: false, runtimeSkipReason: "invalid_payload" };
  }

  return { runtimeEligible: true };
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
    const runtimeEligibility = resolveRuntimeEligibility(type, item.payload, payloadTruncated);

    normalized.push({
      id: toStringValue(item.id),
      type,
      summary: toStringValue(item.summary),
      path: toStringValue(item.path),
      mime_type: toStringValue(item.mime_type),
      payload: item.payload,
      payload_bytes: toNumberValue(item.payload_bytes),
      payload_truncated: payloadTruncated,
      runtime_eligible: runtimeEligibility.runtimeEligible,
      runtime_skip_reason: runtimeEligibility.runtimeSkipReason,
    });
  }

  return {
    hasArtifacts: normalized.length > 0,
    isValid: normalized.length > 0,
    artifacts: normalized,
  };
}
