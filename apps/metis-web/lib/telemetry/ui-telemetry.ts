import { apiFetch, getApiAuthHeaderValue, getApiBase } from "@/lib/api";
import type { NormalizedArrowArtifact } from "@/lib/artifacts/extract-arrow-artifacts";

const TELEMETRY_ENDPOINT = "/v1/telemetry/ui";
const MAX_EVENTS_PER_BATCH = 10;

type ArtifactFallbackReason =
  | "feature_disabled"
  | "no_artifacts"
  | "invalid_payload"
  | "render_error";

type ArtifactRuntimeSkippedReason =
  | "runtime_disabled"
  | "unsupported_type"
  | "payload_truncated"
  | "invalid_payload";

type ArtifactRendererKind = "default" | "custom";
type BoundaryFlagState = "enabled" | "disabled" | "unset";
type ArtifactInteractionType = "card_click";

export type ArtifactTelemetryEventName =
  | "artifact_payload_detected"
  | "artifact_render_attempt"
  | "artifact_render_success"
  | "artifact_render_failure"
  | "artifact_render_fallback_markdown"
  | "artifact_interaction"
  | "artifact_boundary_flag_state"
  | "artifact_runtime_attempt"
  | "artifact_runtime_success"
  | "artifact_runtime_failure"
  | "artifact_runtime_skipped";

interface ArtifactTelemetryContext {
  runId: string;
  sessionId?: string | null;
  messageId?: string | null;
  isStreaming?: boolean;
}

interface ArtifactTelemetryEventBase {
  event_name: ArtifactTelemetryEventName;
  source: "chat_artifact_boundary";
  occurred_at: string;
  run_id: string;
  session_id?: string;
  message_id?: string;
  is_streaming: boolean;
}

interface ArtifactSummaryPayload {
  artifact_count: number;
  artifact_types: string[];
  artifact_ids: string[];
}

interface ArtifactPayloadDetectedEvent extends ArtifactTelemetryEventBase {
  event_name: "artifact_payload_detected";
  payload: ArtifactSummaryPayload & {
    has_valid_artifacts: boolean;
    detected_count: number;
    normalized_count: number;
    invalid_reason?: "invalid_payload";
  };
}

interface ArtifactRenderAttemptEvent extends ArtifactTelemetryEventBase {
  event_name: "artifact_render_attempt";
  payload: ArtifactSummaryPayload & {
    renderer: ArtifactRendererKind;
  };
}

interface ArtifactRenderSuccessEvent extends ArtifactTelemetryEventBase {
  event_name: "artifact_render_success";
  payload: ArtifactSummaryPayload & {
    renderer: ArtifactRendererKind;
  };
}

interface ArtifactRenderFailureEvent extends ArtifactTelemetryEventBase {
  event_name: "artifact_render_failure";
  payload: ArtifactSummaryPayload & {
    renderer: ArtifactRendererKind;
    error_name: string;
  };
}

interface ArtifactRenderFallbackMarkdownEvent extends ArtifactTelemetryEventBase {
  event_name: "artifact_render_fallback_markdown";
  payload: {
    reason: ArtifactFallbackReason;
  };
}

interface ArtifactInteractionEvent extends ArtifactTelemetryEventBase {
  event_name: "artifact_interaction";
  payload: {
    interaction_type: ArtifactInteractionType;
    artifact_index: number;
    artifact_id?: string;
    artifact_type?: string;
  };
}

interface ArtifactBoundaryFlagStateEvent extends ArtifactTelemetryEventBase {
  event_name: "artifact_boundary_flag_state";
  payload: {
    state: BoundaryFlagState;
  };
}

interface ArtifactRuntimeAttemptEvent extends ArtifactTelemetryEventBase {
  event_name: "artifact_runtime_attempt";
  payload: {
    artifact_index: number;
    artifact_id?: string;
    artifact_type: string;
  };
}

interface ArtifactRuntimeSuccessEvent extends ArtifactTelemetryEventBase {
  event_name: "artifact_runtime_success";
  payload: {
    artifact_index: number;
    artifact_id?: string;
    artifact_type: string;
  };
}

interface ArtifactRuntimeFailureEvent extends ArtifactTelemetryEventBase {
  event_name: "artifact_runtime_failure";
  payload: {
    artifact_index: number;
    artifact_id?: string;
    artifact_type: string;
    error_name: string;
  };
}

interface ArtifactRuntimeSkippedEvent extends ArtifactTelemetryEventBase {
  event_name: "artifact_runtime_skipped";
  payload: {
    artifact_index: number;
    artifact_id?: string;
    artifact_type: string;
    reason: ArtifactRuntimeSkippedReason;
  };
}

export type ArtifactTelemetryEvent =
  | ArtifactPayloadDetectedEvent
  | ArtifactRenderAttemptEvent
  | ArtifactRenderSuccessEvent
  | ArtifactRenderFailureEvent
  | ArtifactRenderFallbackMarkdownEvent
  | ArtifactInteractionEvent
  | ArtifactBoundaryFlagStateEvent
  | ArtifactRuntimeAttemptEvent
  | ArtifactRuntimeSuccessEvent
  | ArtifactRuntimeFailureEvent
  | ArtifactRuntimeSkippedEvent;

interface ArtifactTelemetryBatch {
  events: ArtifactTelemetryEvent[];
}

function normalizeId(value: string | null | undefined): string | undefined {
  const normalized = typeof value === "string" ? value.trim() : "";
  return normalized || undefined;
}

function buildBaseEvent(
  context: ArtifactTelemetryContext,
  eventName: ArtifactTelemetryEventName,
): ArtifactTelemetryEventBase | null {
  const runId = normalizeId(context.runId);
  if (!runId) {
    return null;
  }

  return {
    event_name: eventName,
    source: "chat_artifact_boundary",
    occurred_at: new Date().toISOString(),
    run_id: runId,
    session_id: normalizeId(context.sessionId ?? undefined),
    message_id: normalizeId(context.messageId ?? undefined),
    is_streaming: Boolean(context.isStreaming),
  };
}

function getArtifactSummary(artifacts: NormalizedArrowArtifact[]): ArtifactSummaryPayload {
  return {
    artifact_count: artifacts.length,
    artifact_types: artifacts.map((artifact) => artifact.type).filter(Boolean),
    artifact_ids: artifacts.map((artifact) => artifact.id).filter(Boolean),
  };
}

async function postTelemetryBatch(batch: ArtifactTelemetryBatch): Promise<void> {
  const apiBase = await getApiBase();
  const body = JSON.stringify(batch);
  const url = `${apiBase}${TELEMETRY_ENDPOINT}`;
  const authHeaderValue = getApiAuthHeaderValue();

  if (!authHeaderValue && typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
    const blob = new Blob([body], { type: "application/json" });
    if (navigator.sendBeacon(url, blob)) {
      return;
    }
  }

  await apiFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  });
}

export function emitArtifactTelemetry(event: ArtifactTelemetryEvent | null): void {
  if (!event) {
    return;
  }

  void postTelemetryBatch({ events: [event] }).catch(() => {
    // Best-effort only. Rendering must never depend on telemetry delivery.
  });
}

export function emitArtifactTelemetryBatch(events: ArtifactTelemetryEvent[]): void {
  const batch = events.filter(Boolean).slice(0, MAX_EVENTS_PER_BATCH);
  if (batch.length === 0) {
    return;
  }

  void postTelemetryBatch({ events: batch }).catch(() => {
    // Best-effort only. Rendering must never depend on telemetry delivery.
  });
}

export function createArtifactBoundaryFlagStateEvent(
  context: ArtifactTelemetryContext,
  state: BoundaryFlagState,
): ArtifactBoundaryFlagStateEvent | null {
  const base = buildBaseEvent(context, "artifact_boundary_flag_state");
  if (!base) {
    return null;
  }
  return {
    ...base,
    event_name: "artifact_boundary_flag_state",
    payload: { state },
  };
}

export function createArtifactPayloadDetectedEvent(
  context: ArtifactTelemetryContext,
  options: {
    artifacts: NormalizedArrowArtifact[];
    detectedCount: number;
    hasValidArtifacts: boolean;
    invalidReason?: "invalid_payload";
  },
): ArtifactPayloadDetectedEvent | null {
  const base = buildBaseEvent(context, "artifact_payload_detected");
  if (!base) {
    return null;
  }
  return {
    ...base,
    event_name: "artifact_payload_detected",
    payload: {
      ...getArtifactSummary(options.artifacts),
      has_valid_artifacts: options.hasValidArtifacts,
      detected_count: options.detectedCount,
      normalized_count: options.artifacts.length,
      invalid_reason: options.invalidReason,
    },
  };
}

export function createArtifactRenderAttemptEvent(
  context: ArtifactTelemetryContext,
  artifacts: NormalizedArrowArtifact[],
  renderer: ArtifactRendererKind,
): ArtifactRenderAttemptEvent | null {
  const base = buildBaseEvent(context, "artifact_render_attempt");
  if (!base) {
    return null;
  }
  return {
    ...base,
    event_name: "artifact_render_attempt",
    payload: {
      ...getArtifactSummary(artifacts),
      renderer,
    },
  };
}

export function createArtifactRenderSuccessEvent(
  context: ArtifactTelemetryContext,
  artifacts: NormalizedArrowArtifact[],
  renderer: ArtifactRendererKind,
): ArtifactRenderSuccessEvent | null {
  const base = buildBaseEvent(context, "artifact_render_success");
  if (!base) {
    return null;
  }
  return {
    ...base,
    event_name: "artifact_render_success",
    payload: {
      ...getArtifactSummary(artifacts),
      renderer,
    },
  };
}

export function createArtifactRenderFailureEvent(
  context: ArtifactTelemetryContext,
  artifacts: NormalizedArrowArtifact[],
  renderer: ArtifactRendererKind,
  errorName: string,
): ArtifactRenderFailureEvent | null {
  const base = buildBaseEvent(context, "artifact_render_failure");
  if (!base) {
    return null;
  }
  return {
    ...base,
    event_name: "artifact_render_failure",
    payload: {
      ...getArtifactSummary(artifacts),
      renderer,
      error_name: normalizeId(errorName) ?? "Error",
    },
  };
}

export function createArtifactFallbackMarkdownEvent(
  context: ArtifactTelemetryContext,
  reason: ArtifactFallbackReason,
): ArtifactRenderFallbackMarkdownEvent | null {
  const base = buildBaseEvent(context, "artifact_render_fallback_markdown");
  if (!base) {
    return null;
  }
  return {
    ...base,
    event_name: "artifact_render_fallback_markdown",
    payload: { reason },
  };
}

export function createArtifactInteractionEvent(
  context: ArtifactTelemetryContext,
  options: {
    artifactIndex: number;
    artifactId?: string;
    artifactType?: string;
  },
): ArtifactInteractionEvent | null {
  const base = buildBaseEvent(context, "artifact_interaction");
  if (!base) {
    return null;
  }
  return {
    ...base,
    event_name: "artifact_interaction",
    payload: {
      interaction_type: "card_click",
      artifact_index: options.artifactIndex,
      artifact_id: normalizeId(options.artifactId),
      artifact_type: normalizeId(options.artifactType),
    },
  };
}

export function createArtifactRuntimeAttemptEvent(
  context: ArtifactTelemetryContext,
  options: {
    artifactIndex: number;
    artifactId?: string;
    artifactType?: string;
  },
): ArtifactRuntimeAttemptEvent | null {
  const base = buildBaseEvent(context, "artifact_runtime_attempt");
  const artifactType = normalizeId(options.artifactType);
  if (!base || !artifactType) {
    return null;
  }

  return {
    ...base,
    event_name: "artifact_runtime_attempt",
    payload: {
      artifact_index: options.artifactIndex,
      artifact_id: normalizeId(options.artifactId),
      artifact_type: artifactType,
    },
  };
}

export function createArtifactRuntimeSuccessEvent(
  context: ArtifactTelemetryContext,
  options: {
    artifactIndex: number;
    artifactId?: string;
    artifactType?: string;
  },
): ArtifactRuntimeSuccessEvent | null {
  const base = buildBaseEvent(context, "artifact_runtime_success");
  const artifactType = normalizeId(options.artifactType);
  if (!base || !artifactType) {
    return null;
  }

  return {
    ...base,
    event_name: "artifact_runtime_success",
    payload: {
      artifact_index: options.artifactIndex,
      artifact_id: normalizeId(options.artifactId),
      artifact_type: artifactType,
    },
  };
}

export function createArtifactRuntimeFailureEvent(
  context: ArtifactTelemetryContext,
  options: {
    artifactIndex: number;
    artifactId?: string;
    artifactType?: string;
    errorName: string;
  },
): ArtifactRuntimeFailureEvent | null {
  const base = buildBaseEvent(context, "artifact_runtime_failure");
  const artifactType = normalizeId(options.artifactType);
  if (!base || !artifactType) {
    return null;
  }

  return {
    ...base,
    event_name: "artifact_runtime_failure",
    payload: {
      artifact_index: options.artifactIndex,
      artifact_id: normalizeId(options.artifactId),
      artifact_type: artifactType,
      error_name: normalizeId(options.errorName) ?? "Error",
    },
  };
}

export function createArtifactRuntimeSkippedEvent(
  context: ArtifactTelemetryContext,
  options: {
    artifactIndex: number;
    artifactId?: string;
    artifactType?: string;
    reason: ArtifactRuntimeSkippedReason;
  },
): ArtifactRuntimeSkippedEvent | null {
  const base = buildBaseEvent(context, "artifact_runtime_skipped");
  const artifactType = normalizeId(options.artifactType);
  if (!base || !artifactType) {
    return null;
  }

  return {
    ...base,
    event_name: "artifact_runtime_skipped",
    payload: {
      artifact_index: options.artifactIndex,
      artifact_id: normalizeId(options.artifactId),
      artifact_type: artifactType,
      reason: options.reason,
    },
  };
}