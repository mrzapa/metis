import type { EvidenceSource } from "@/lib/chat-types";

export const DEFAULT_BRAIN_GRAPH_HIGHLIGHT_TTL_MS = 8000;

export interface BrainGraphRagActivity {
  runId: string;
  sessionId?: string | null;
  manifestPath?: string;
  sources: EvidenceSource[];
  timestamp: number;
  ttlMs?: number;
}

type BrainGraphRagActivityListener = (activity: BrainGraphRagActivity) => void;

const listeners = new Set<BrainGraphRagActivityListener>();
let latestActivity: BrainGraphRagActivity | null = null;

function normalizeActivity(activity: BrainGraphRagActivity): BrainGraphRagActivity {
  const ttlMs = Math.max(2000, Math.round(activity.ttlMs ?? DEFAULT_BRAIN_GRAPH_HIGHLIGHT_TTL_MS));
  return {
    runId: String(activity.runId || "").trim(),
    sessionId: activity.sessionId ?? null,
    manifestPath: activity.manifestPath,
    sources: Array.isArray(activity.sources) ? [...activity.sources] : [],
    timestamp: Number.isFinite(activity.timestamp) ? activity.timestamp : Date.now(),
    ttlMs,
  };
}

export function emitBrainGraphRagActivity(activity: BrainGraphRagActivity): void {
  const normalized = normalizeActivity(activity);
  latestActivity = normalized;
  for (const listener of listeners) {
    try {
      listener(normalized);
    } catch {
      // Keep listeners isolated from each other.
    }
  }
}

export function subscribeBrainGraphRagActivity(
  listener: BrainGraphRagActivityListener,
  options: { replayLatest?: boolean } = {},
): () => void {
  listeners.add(listener);
  if (options.replayLatest !== false && latestActivity) {
    listener(latestActivity);
  }

  return () => {
    listeners.delete(listener);
  };
}

export function getLatestBrainGraphRagActivity(): BrainGraphRagActivity | null {
  return latestActivity;
}
