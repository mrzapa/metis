import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createArtifactBoundaryFlagStateEvent,
  createArtifactRuntimeFailureEvent,
  createArtifactRuntimeSkippedEvent,
  createArtifactRuntimeSuccessEvent,
  emitArtifactTelemetry,
} from "@/lib/telemetry/ui-telemetry";

function getEvent() {
  return createArtifactBoundaryFlagStateEvent({ runId: "run-telemetry" }, "enabled");
}

describe("ui telemetry delivery", () => {
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_METIS_API_TOKEN;
    vi.restoreAllMocks();
  });

  it("uses authenticated fetch when a frontend API token is configured", async () => {
    process.env.NEXT_PUBLIC_METIS_API_TOKEN = "secret-token";

    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    const sendBeaconMock = vi.fn().mockReturnValue(true);

    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(window.navigator, "sendBeacon", {
      configurable: true,
      value: sendBeaconMock,
    });

    emitArtifactTelemetry(getEvent());

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    expect(sendBeaconMock).not.toHaveBeenCalled();

    const [, init] = fetchMock.mock.calls[0] ?? [];
    const headers = new Headers(init?.headers);

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/v1/telemetry/ui");
    expect(headers.get("Authorization")).toBe("Bearer secret-token");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init?.keepalive).toBe(true);
  });

  it("prefers sendBeacon when telemetry is unauthenticated", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    const sendBeaconMock = vi.fn().mockReturnValue(true);

    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(window.navigator, "sendBeacon", {
      configurable: true,
      value: sendBeaconMock,
    });

    emitArtifactTelemetry(getEvent());

    await vi.waitFor(() => {
      expect(sendBeaconMock).toHaveBeenCalledTimes(1);
    });

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("swallows delivery failures so telemetry stays best-effort", async () => {
    process.env.NEXT_PUBLIC_METIS_API_TOKEN = "secret-token";

    const fetchMock = vi.fn().mockRejectedValue(new Error("network down"));
    vi.stubGlobal("fetch", fetchMock);

    expect(() => emitArtifactTelemetry(getEvent())).not.toThrow();

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
  });

  it("builds runtime success event payloads with strict shape", () => {
    const event = createArtifactRuntimeSuccessEvent(
      { runId: "run-telemetry", sessionId: "session-1", messageId: "message-1" },
      {
        artifactIndex: 0,
        artifactId: "artifact-1",
        artifactType: "timeline",
      },
    );

    expect(event).toMatchObject({
      event_name: "artifact_runtime_success",
      payload: {
        artifact_index: 0,
        artifact_id: "artifact-1",
        artifact_type: "timeline",
      },
    });
  });

  it("builds runtime failure event payloads with normalized error names", () => {
    const event = createArtifactRuntimeFailureEvent(
      { runId: "run-telemetry" },
      {
        artifactIndex: 1,
        artifactType: "timeline",
        errorName: " ",
      },
    );

    expect(event).toMatchObject({
      event_name: "artifact_runtime_failure",
      payload: {
        artifact_index: 1,
        artifact_type: "timeline",
        error_name: "Error",
      },
    });
  });

  it("builds runtime skipped event payloads with allowlisted reasons", () => {
    const event = createArtifactRuntimeSkippedEvent(
      { runId: "run-telemetry" },
      {
        artifactIndex: 2,
        artifactType: "metric_cards",
        reason: "runtime_disabled",
      },
    );

    expect(event).toMatchObject({
      event_name: "artifact_runtime_skipped",
      payload: {
        artifact_index: 2,
        artifact_type: "metric_cards",
        reason: "runtime_disabled",
      },
    });
  });
});