"use client";

import { Component, useEffect, useRef, type ReactNode } from "react";
import { AssistantMarkdown } from "@/components/chat/assistant-markdown";
import { ArtifactMessageContent } from "@/components/chat/artifacts/artifact-message-content";
import {
  extractArrowArtifacts,
  type NormalizedArrowArtifact,
} from "@/lib/artifacts/extract-arrow-artifacts";
import {
  createArtifactBoundaryFlagStateEvent,
  createArtifactFallbackMarkdownEvent,
  createArtifactInteractionEvent,
  createArtifactPayloadDetectedEvent,
  createArtifactRenderAttemptEvent,
  createArtifactRenderFailureEvent,
  createArtifactRenderSuccessEvent,
  createArtifactRuntimeAttemptEvent,
  createArtifactRuntimeFailureEvent,
  createArtifactRuntimeSkippedEvent,
  createArtifactRuntimeSuccessEvent,
  emitArtifactTelemetry,
} from "@/lib/telemetry/ui-telemetry";

interface ArrowArtifactBoundaryProps {
  content: string;
  artifacts?: unknown;
  isStreaming?: boolean;
  artifactsEnabled?: boolean;
  artifactRuntimeEnabled?: boolean;
  sessionId?: string | null;
  runId?: string | null;
  messageId?: string | null;
  renderArtifacts?: (artifacts: NormalizedArrowArtifact[]) => ReactNode;
}

interface ArrowRenderErrorBoundaryProps {
  fallback: ReactNode;
  children: ReactNode;
  onError?: (error: Error) => void;
}

interface ArrowRenderErrorBoundaryState {
  hasError: boolean;
}

class ArrowRenderErrorBoundary extends Component<
  ArrowRenderErrorBoundaryProps,
  ArrowRenderErrorBoundaryState
> {
  public constructor(props: ArrowRenderErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  public static getDerivedStateFromError(): ArrowRenderErrorBoundaryState {
    return { hasError: true };
  }

  public override componentDidCatch(error: Error) {
    this.props.onError?.(error);
  }

  public override render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }

    return this.props.children;
  }
}

function InjectedArtifactRenderer({
  artifacts,
  renderArtifacts,
}: {
  artifacts: NormalizedArrowArtifact[];
  renderArtifacts: (artifacts: NormalizedArrowArtifact[]) => ReactNode;
}) {
  return <>{renderArtifacts(artifacts)}</>;
}

function TrackedArtifactRenderer({
  artifacts,
  renderArtifacts,
  onRenderSuccess,
  onArtifactInteraction,
  artifactRuntimeEnabled,
  onRuntimeLifecycle,
}: {
  artifacts: NormalizedArrowArtifact[];
  renderArtifacts?: (artifacts: NormalizedArrowArtifact[]) => ReactNode;
  onRenderSuccess: () => void;
  onArtifactInteraction: (artifact: NormalizedArrowArtifact, index: number) => void;
  artifactRuntimeEnabled?: boolean;
  onRuntimeLifecycle: (options: {
    lifecycle: "attempt" | "success" | "failure" | "skipped";
    artifact: NormalizedArrowArtifact;
    artifactIndex: number;
    skipReason?: "runtime_disabled" | "unsupported_type" | "payload_truncated" | "invalid_payload";
    errorName?: string;
  }) => void;
}) {
  useEffect(() => {
    onRenderSuccess();
  }, [onRenderSuccess]);

  if (renderArtifacts) {
    return <InjectedArtifactRenderer artifacts={artifacts} renderArtifacts={renderArtifacts} />;
  }

  return (
    <ArtifactMessageContent
      artifacts={artifacts}
      runtimeEnabled={artifactRuntimeEnabled}
      onArtifactInteraction={onArtifactInteraction}
      onRuntimeLifecycleEvent={onRuntimeLifecycle}
    />
  );
}

function getTelemetryContext({
  sessionId,
  runId,
  messageId,
  isStreaming,
}: {
  sessionId?: string | null;
  runId?: string | null;
  messageId?: string | null;
  isStreaming: boolean;
}) {
  return {
    sessionId,
    runId: runId ?? "",
    messageId,
    isStreaming,
  };
}

function getArtifactSignature(artifacts: NormalizedArrowArtifact[]): string {
  return artifacts
    .map((artifact, index) => [artifact.id, artifact.type, artifact.path, artifact.mime_type, index].join(":"))
    .join("|");
}

export function ArrowArtifactBoundary({
  content,
  artifacts,
  isStreaming = false,
  artifactsEnabled,
  artifactRuntimeEnabled,
  sessionId,
  runId,
  messageId,
  renderArtifacts,
}: ArrowArtifactBoundaryProps) {
  const markdownFallback = (
    <AssistantMarkdown content={content} isStreaming={isStreaming} />
  );

  const telemetryContext = getTelemetryContext({
    sessionId,
    runId,
    messageId,
    isStreaming,
  });
  const rawArtifactCount = Array.isArray(artifacts) ? Math.min(artifacts.length, 5) : 0;
  const extraction = extractArrowArtifacts(artifacts);
  const artifactSignature = getArtifactSignature(extraction.artifacts);
  const renderer = renderArtifacts ? "custom" : "default";
  const flagState = artifactsEnabled === undefined ? "unset" : artifactsEnabled ? "enabled" : "disabled";
  const runtimeFlagState = artifactRuntimeEnabled !== false;
  const lastFlagStateRef = useRef<string>("");
  const lastDetectedSignatureRef = useRef<string>("");
  const lastFallbackSignatureRef = useRef<string>("");
  const lastRenderAttemptSignatureRef = useRef<string>("");
  const lastRenderSuccessSignatureRef = useRef<string>("");
  const emittedRuntimeLifecycleRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (lastFlagStateRef.current === flagState) {
      return;
    }
    lastFlagStateRef.current = flagState;
    emitArtifactTelemetry(createArtifactBoundaryFlagStateEvent(telemetryContext, flagState));
  }, [flagState, telemetryContext]);

  useEffect(() => {
    if (!extraction.hasArtifacts) {
      return;
    }

    const detectionSignature = `${rawArtifactCount}:${artifactSignature}:${extraction.isValid ? "valid" : "invalid"}`;
    if (lastDetectedSignatureRef.current === detectionSignature) {
      return;
    }

    lastDetectedSignatureRef.current = detectionSignature;
    emitArtifactTelemetry(
      createArtifactPayloadDetectedEvent(telemetryContext, {
        artifacts: extraction.artifacts,
        detectedCount: rawArtifactCount,
        hasValidArtifacts: extraction.isValid,
        invalidReason: extraction.isValid ? undefined : "invalid_payload",
      }),
    );
  }, [artifactSignature, extraction.artifacts, extraction.hasArtifacts, extraction.isValid, rawArtifactCount, telemetryContext]);

  const fallbackReason =
    artifactsEnabled === false
      ? "feature_disabled"
      : !extraction.hasArtifacts
        ? "no_artifacts"
        : !extraction.isValid
          ? "invalid_payload"
          : null;

  useEffect(() => {
    if (!fallbackReason) {
      return;
    }

    const signature = `${fallbackReason}:${artifactSignature}:${rawArtifactCount}`;
    if (lastFallbackSignatureRef.current === signature) {
      return;
    }
    lastFallbackSignatureRef.current = signature;
    emitArtifactTelemetry(createArtifactFallbackMarkdownEvent(telemetryContext, fallbackReason));
  }, [artifactSignature, fallbackReason, rawArtifactCount, telemetryContext]);

  const shouldRenderArtifacts =
    artifactsEnabled !== false && extraction.hasArtifacts && extraction.isValid;

  useEffect(() => {
    if (!shouldRenderArtifacts) {
      return;
    }

    const signature = `${renderer}:${artifactSignature}`;
    if (lastRenderAttemptSignatureRef.current === signature) {
      return;
    }
    lastRenderAttemptSignatureRef.current = signature;
    emitArtifactTelemetry(
      createArtifactRenderAttemptEvent(telemetryContext, extraction.artifacts, renderer),
    );
  }, [artifactSignature, extraction.artifacts, renderer, shouldRenderArtifacts, telemetryContext]);

  useEffect(() => {
    emittedRuntimeLifecycleRef.current.clear();
  }, [artifactSignature, artifactRuntimeEnabled]);

  if (artifactsEnabled === false) {
    return markdownFallback;
  }

  if (!extraction.hasArtifacts) {
    return markdownFallback;
  }

  if (!extraction.isValid) {
    return markdownFallback;
  }

  function handleRenderSuccess() {
    const signature = `${renderer}:${artifactSignature}`;
    if (lastRenderSuccessSignatureRef.current === signature) {
      return;
    }
    lastRenderSuccessSignatureRef.current = signature;
    emitArtifactTelemetry(
      createArtifactRenderSuccessEvent(telemetryContext, extraction.artifacts, renderer),
    );
  }

  function handleRenderError(error: Error) {
    emitArtifactTelemetry(
      createArtifactRenderFailureEvent(
        telemetryContext,
        extraction.artifacts,
        renderer,
        error.name || "Error",
      ),
    );
    emitArtifactTelemetry(createArtifactFallbackMarkdownEvent(telemetryContext, "render_error"));
  }

  function handleArtifactInteraction(artifact: NormalizedArrowArtifact, index: number) {
    emitArtifactTelemetry(
      createArtifactInteractionEvent(telemetryContext, {
        artifactIndex: index,
        artifactId: artifact.id,
        artifactType: artifact.type,
      }),
    );
  }

  function handleRuntimeLifecycle(options: {
    lifecycle: "attempt" | "success" | "failure" | "skipped";
    artifact: NormalizedArrowArtifact;
    artifactIndex: number;
    skipReason?: "runtime_disabled" | "unsupported_type" | "payload_truncated" | "invalid_payload";
    errorName?: string;
  }) {
    const eventKey = [
      options.lifecycle,
      options.artifactIndex,
      options.artifact.id || "",
      options.artifact.type,
      options.skipReason || "",
      options.errorName || "",
      runtimeFlagState ? "runtime_enabled" : "runtime_disabled",
    ].join(":");

    if (emittedRuntimeLifecycleRef.current.has(eventKey)) {
      return;
    }
    emittedRuntimeLifecycleRef.current.add(eventKey);

    if (options.lifecycle === "attempt") {
      emitArtifactTelemetry(
        createArtifactRuntimeAttemptEvent(telemetryContext, {
          artifactIndex: options.artifactIndex,
          artifactId: options.artifact.id,
          artifactType: options.artifact.type,
        }),
      );
      return;
    }

    if (options.lifecycle === "success") {
      emitArtifactTelemetry(
        createArtifactRuntimeSuccessEvent(telemetryContext, {
          artifactIndex: options.artifactIndex,
          artifactId: options.artifact.id,
          artifactType: options.artifact.type,
        }),
      );
      return;
    }

    if (options.lifecycle === "failure") {
      emitArtifactTelemetry(
        createArtifactRuntimeFailureEvent(telemetryContext, {
          artifactIndex: options.artifactIndex,
          artifactId: options.artifact.id,
          artifactType: options.artifact.type,
          errorName: options.errorName || "Error",
        }),
      );
      return;
    }

    emitArtifactTelemetry(
      createArtifactRuntimeSkippedEvent(telemetryContext, {
        artifactIndex: options.artifactIndex,
        artifactId: options.artifact.id,
        artifactType: options.artifact.type,
        reason: options.skipReason || "invalid_payload",
      }),
    );
  }

  return (
    <ArrowRenderErrorBoundary fallback={markdownFallback} onError={handleRenderError}>
      <TrackedArtifactRenderer
        artifacts={extraction.artifacts}
        renderArtifacts={renderArtifacts}
        onRenderSuccess={handleRenderSuccess}
        onArtifactInteraction={handleArtifactInteraction}
        artifactRuntimeEnabled={artifactRuntimeEnabled}
        onRuntimeLifecycle={handleRuntimeLifecycle}
      />
    </ArrowRenderErrorBoundary>
  );
}
