import type { RagStreamEvent } from "@/lib/api";

/**
 * Deduplicates SSE events from a single RAG stream attempt.
 *
 * The stream may redeliver events on reconnection (Last-Event-ID resume),
 * and the server may emit a logically identical event without a stable
 * numeric id. Callers used to track three correlated bits of state by
 * hand:
 *
 *   - `lastEventId` — the highest numeric id we've accepted (used to
 *     advance the resume cursor).
 *   - `dedupeFloorEventId` — events with id ≤ floor are silently
 *     discarded (resume floor; usually the high-watermark from the
 *     previous attempt).
 *   - `seenEventSignatures` — a per-attempt set of signatures so we
 *     never apply the same event twice within one attempt.
 *
 * Forgetting any of these — or the order of checks — produces subtle
 * double-render bugs in the chat UI. This module is the single seam
 * where that policy lives.
 */
export interface RagStreamDedupTracker {
  /** Highest numeric eventId observed and accepted. */
  readonly lastEventId: number;
  /**
   * Decide whether `event` (with `eventId` from the SSE message id)
   * should be applied to UI state. Mutates internal sets and the
   * lastEventId watermark on accept.
   */
  shouldEmit(event: RagStreamEvent, eventId: number | null): boolean;
}

export interface RagStreamDedupOptions {
  /** Resume cursor: events with eventId ≤ floor are discarded. */
  dedupeFloorEventId?: number;
  /** Initial lastEventId (typically the previous attempt's watermark). */
  initialLastEventId?: number;
  /**
   * Run id assumed when an event omits its own. Mirrors the server's
   * fallback behaviour during the brief window before `run_started`.
   */
  fallbackRunId?: string;
}

export function createRagStreamDedupTracker(
  options: RagStreamDedupOptions = {},
): RagStreamDedupTracker {
  const seen = new Set<string>();
  const floor = options.dedupeFloorEventId ?? 0;
  const fallbackRunId = options.fallbackRunId ?? "";
  let lastEventId = options.initialLastEventId ?? 0;

  return {
    get lastEventId() {
      return lastEventId;
    },
    shouldEmit(event, eventId) {
      // Resume floor: drop anything from before this attempt began.
      if (
        eventId !== null
        && event.run_id
        && eventId <= floor
      ) {
        return false;
      }

      const signature = buildEventSignature(event, fallbackRunId, eventId);
      if (seen.has(signature)) {
        return false;
      }
      seen.add(signature);

      if (
        eventId !== null
        && Number.isFinite(eventId)
        && eventId > lastEventId
      ) {
        lastEventId = eventId;
      }
      return true;
    },
  };
}

/**
 * Stable identity for a stream event. Numeric ids are preferred when
 * present; otherwise we hash the event payload so logically identical
 * events without ids still dedupe.
 */
export function buildEventSignature(
  event: RagStreamEvent,
  fallbackRunId: string,
  eventId: number | null,
): string {
  const runId = String(event.run_id || fallbackRunId || "").trim();
  if (eventId !== null) {
    return `${runId}:${eventId}`;
  }
  return `${runId}:${event.type}:${JSON.stringify(event)}`;
}
