import { describe, expect, it } from "vitest";

import type { RagStreamEvent } from "@/lib/api";
import {
  buildEventSignature,
  createRagStreamDedupTracker,
} from "@/lib/services/rag-stream-dedup";

function runStartedEvent(runId: string): RagStreamEvent {
  return { type: "run_started", run_id: runId };
}

describe("createRagStreamDedupTracker", () => {
  it("emits the first occurrence of an event and remembers it", () => {
    const tracker = createRagStreamDedupTracker();
    const event = runStartedEvent("r1");
    expect(tracker.shouldEmit(event, 1)).toBe(true);
    expect(tracker.shouldEmit(event, 1)).toBe(false);
  });

  it("advances lastEventId on accept", () => {
    const tracker = createRagStreamDedupTracker();
    tracker.shouldEmit(runStartedEvent("r1"), 5);
    expect(tracker.lastEventId).toBe(5);
    tracker.shouldEmit(runStartedEvent("r1"), 9);
    expect(tracker.lastEventId).toBe(9);
  });

  it("does not regress lastEventId when an out-of-order event arrives", () => {
    const tracker = createRagStreamDedupTracker();
    tracker.shouldEmit(runStartedEvent("r1"), 9);
    tracker.shouldEmit({ ...runStartedEvent("r1"), type: "run_started" }, 3);
    expect(tracker.lastEventId).toBe(9);
  });

  it("discards events at or below the dedupe floor (resume cursor)", () => {
    const tracker = createRagStreamDedupTracker({ dedupeFloorEventId: 10 });
    expect(tracker.shouldEmit(runStartedEvent("r1"), 10)).toBe(false);
    expect(tracker.shouldEmit(runStartedEvent("r1"), 11)).toBe(true);
  });

  it("dedupes signature-only events that share a payload", () => {
    const tracker = createRagStreamDedupTracker();
    const event: RagStreamEvent = { type: "run_started", run_id: "r1" };
    expect(tracker.shouldEmit(event, null)).toBe(true);
    expect(tracker.shouldEmit({ ...event }, null)).toBe(false);
  });
});

describe("buildEventSignature", () => {
  it("uses run_id + numeric event id when present", () => {
    expect(buildEventSignature(runStartedEvent("r1"), "", 42)).toBe("r1:42");
  });

  it("falls back to the supplied run_id when the event omits one", () => {
    const event = { type: "run_started", run_id: "" } as RagStreamEvent;
    expect(buildEventSignature(event, "fallback", 7)).toBe("fallback:7");
  });

  it("hashes the payload when no eventId is supplied", () => {
    const sig = buildEventSignature(runStartedEvent("r1"), "", null);
    expect(sig.startsWith("r1:run_started:")).toBe(true);
  });
});
