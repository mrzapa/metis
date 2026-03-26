import type { TraceEvent } from "@/lib/api";
import type { EvidenceSource } from "@/lib/chat-types";

const RESUMABLE_RAG_RUN_KEY = "metis_resumable_rag_run";
const LEGACY_RESUMABLE_RAG_RUN_KEY = "metis_resumable_rag_run";

export interface ResumableRagRunSnapshot {
  version: 1;
  manifestPath: string;
  indexLabel: string | null;
  question: string;
  runId: string;
  lastEventId: number;
  userMessageTs: string;
  assistantMessageTs: string;
  assistantContent: string;
  pendingSources: EvidenceSource[];
  sources: EvidenceSource[];
  liveTraceEvents: TraceEvent[];
  subQueries?: string[];
}

export function loadResumableRagRun(): ResumableRagRunSnapshot | null {
  if (typeof window === "undefined") {
    return null;
  }

  let raw = window.sessionStorage.getItem(RESUMABLE_RAG_RUN_KEY);
  if (!raw) {
    const legacy = window.sessionStorage.getItem(LEGACY_RESUMABLE_RAG_RUN_KEY);
    if (legacy) {
      window.sessionStorage.setItem(RESUMABLE_RAG_RUN_KEY, legacy);
      window.sessionStorage.removeItem(LEGACY_RESUMABLE_RAG_RUN_KEY);
      raw = legacy;
    }
  }
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as unknown;
    const snapshot = normalizeResumableRagRun(parsed);
    if (!snapshot) {
      window.sessionStorage.removeItem(RESUMABLE_RAG_RUN_KEY);
    }
    return snapshot;
  } catch {
    window.sessionStorage.removeItem(RESUMABLE_RAG_RUN_KEY);
    return null;
  }
}

export function saveResumableRagRun(snapshot: ResumableRagRunSnapshot): void {
  if (typeof window === "undefined") {
    return;
  }

  window.sessionStorage.setItem(
    RESUMABLE_RAG_RUN_KEY,
    JSON.stringify(snapshot),
  );
}

export function clearResumableRagRun(): void {
  if (typeof window === "undefined") {
    return;
  }

  window.sessionStorage.removeItem(RESUMABLE_RAG_RUN_KEY);
  window.sessionStorage.removeItem(LEGACY_RESUMABLE_RAG_RUN_KEY);
}

function normalizeResumableRagRun(
  value: unknown,
): ResumableRagRunSnapshot | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const candidate = value as Record<string, unknown>;
  const version = Number(candidate.version);
  const manifestPath = String(candidate.manifestPath ?? "").trim();
  const question = String(candidate.question ?? "").trim();
  const runId = String(candidate.runId ?? "").trim();

  if (version !== 1 || !manifestPath || !question || !runId) {
    return null;
  }

  return {
    version: 1,
    manifestPath,
    indexLabel: normalizeOptionalString(candidate.indexLabel),
    question,
    runId,
    lastEventId: normalizeEventId(candidate.lastEventId),
    userMessageTs: String(candidate.userMessageTs ?? new Date().toISOString()),
    assistantMessageTs: String(
      candidate.assistantMessageTs ?? new Date().toISOString(),
    ),
    assistantContent: String(candidate.assistantContent ?? ""),
    pendingSources: normalizeEvidenceSources(candidate.pendingSources),
    sources: normalizeEvidenceSources(candidate.sources),
    liveTraceEvents: normalizeTraceEvents(candidate.liveTraceEvents),
    subQueries: Array.isArray(candidate.subQueries)
      ? candidate.subQueries.map(String).filter(Boolean)
      : undefined,
  };
}

function normalizeOptionalString(value: unknown): string | null {
  const normalized = String(value ?? "").trim();
  return normalized || null;
}

function normalizeEventId(value: unknown): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return 0;
  }
  return Math.floor(parsed);
}

function normalizeEvidenceSources(value: unknown): EvidenceSource[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.reduce<EvidenceSource[]>((sources, entry) => {
      if (!entry || typeof entry !== "object") {
        return sources;
      }
      const source = entry as Record<string, unknown>;
      const normalized: EvidenceSource = {
        sid: String(source.sid ?? ""),
        source: String(source.source ?? ""),
        snippet: String(source.snippet ?? ""),
        title: String(source.title ?? ""),
        score:
          typeof source.score === "number" || source.score === null
            ? source.score
            : null,
        breadcrumb: String(source.breadcrumb ?? ""),
        section_hint: String(source.section_hint ?? ""),
        chunk_id: String(source.chunk_id ?? ""),
        chunk_idx:
          typeof source.chunk_idx === "number" || source.chunk_idx === null
            ? source.chunk_idx
            : null,
        label: String(source.label ?? ""),
        locator: String(source.locator ?? ""),
        anchor: String(source.anchor ?? ""),
        header_path: String(source.header_path ?? ""),
        excerpt: String(source.excerpt ?? ""),
        file_path: String(source.file_path ?? ""),
        date: String(source.date ?? ""),
        timestamp: String(source.timestamp ?? ""),
        speaker: String(source.speaker ?? ""),
        actor: String(source.actor ?? ""),
        entry_type: String(source.entry_type ?? ""),
        type: String(source.type ?? ""),
        metadata:
          source.metadata && typeof source.metadata === "object"
            ? (source.metadata as Record<string, unknown>)
            : {},
      };
      if (normalized.sid) {
        sources.push(normalized);
      }
      return sources;
    }, []);
}

function normalizeTraceEvents(value: unknown): TraceEvent[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((entry) => {
      if (!entry || typeof entry !== "object") {
        return null;
      }
      const event = entry as Record<string, unknown>;
      return {
        run_id: String(event.run_id ?? ""),
        event_id: normalizeOptionalString(event.event_id) ?? undefined,
        stage: String(event.stage ?? ""),
        event_type: String(event.event_type ?? ""),
        timestamp: String(event.timestamp ?? new Date().toISOString()),
        iteration:
          typeof event.iteration === "number" ? event.iteration : undefined,
        latency_ms:
          typeof event.latency_ms === "number" || event.latency_ms === null
            ? event.latency_ms
            : undefined,
        payload:
          event.payload && typeof event.payload === "object"
            ? (event.payload as Record<string, unknown>)
            : {},
        citations_chosen: Array.isArray(event.citations_chosen)
          ? event.citations_chosen.map((citation) => String(citation))
          : null,
      } satisfies TraceEvent;
    })
    .filter(
      (entry): entry is NonNullable<typeof entry> =>
        entry !== null && Boolean(entry.run_id && entry.stage && entry.event_type),
    ) as TraceEvent[];
}
