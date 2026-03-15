import type {
  ActionRequiredAction,
  ChatMessageContent,
  EvidenceSource,
} from "@/lib/chat-types";

// Resolves the API base URL once and caches the result.
// In a Tauri desktop build the sidecar negotiates a dynamic port and exposes
// it via the `get_api_base_url` command.  In web / dev mode we fall back to
// the environment variable (or the default development address).
let _apiBaseCache: Promise<string> | null = null;

export function getApiBase(): Promise<string> {
  if (!_apiBaseCache) {
    _apiBaseCache = _resolveApiBase();
  }
  return _apiBaseCache;
}

async function _resolveApiBase(): Promise<string> {
  if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      // The sidecar reads the free port asynchronously; poll up to 15 s.
      for (let i = 0; i < 30; i++) {
        const url = await invoke<string | null>("get_api_base_url");
        if (url) return url;
        await new Promise<void>((r) => setTimeout(r, 500));
      }
    } catch {
      // Fall through to the default below.
    }
  }
  return process.env.NEXT_PUBLIC_AXIOM_API_BASE ?? "http://127.0.0.1:8000";
}

export interface SessionSummary {
  session_id: string;
  created_at: string;
  updated_at: string;
  title: string;
  summary: string;
  active_profile: string;
  mode: string;
  index_id: string;
  llm_provider: string;
  llm_model: string;
}

export type SessionMessage = ChatMessageContent;

export interface DirectQueryResult {
  run_id: string;
  answer_text: string;
  selected_mode: string;
  llm_provider: string;
  llm_model: string;
}

export interface IndexSummary {
  index_id: string;
  manifest_path: string;
  document_count: number;
  chunk_count: number;
  backend: string;
  created_at: string;
  embedding_signature: string;
}

export interface RagQueryResult {
  run_id: string;
  answer_text: string;
  sources: EvidenceSource[];
  context_block: string;
  top_score: number;
  selected_mode: string;
}

export interface RagStreamRunStartedEvent {
  type: "run_started";
  run_id: string;
}

export interface RagStreamRetrievalCompleteEvent {
  type: "retrieval_complete";
  run_id: string;
  sources: EvidenceSource[];
  context_block: string;
  top_score: number;
}

export interface RagStreamTokenEvent {
  type: "token";
  run_id: string;
  text: string;
}

export interface RagStreamFinalEvent {
  type: "final";
  run_id: string;
  answer_text: string;
  sources: EvidenceSource[];
}

export interface RagStreamErrorEvent {
  type: "error";
  run_id: string;
  message: string;
}

export interface RagStreamActionRequiredEvent {
  type: "action_required";
  run_id: string;
  action: ActionRequiredAction;
}

export interface RagStreamSubqueriesEvent {
  type: "subqueries";
  run_id: string;
  queries: string[];
}

export type RagStreamEvent =
  | RagStreamRunStartedEvent
  | RagStreamRetrievalCompleteEvent
  | RagStreamTokenEvent
  | RagStreamFinalEvent
  | RagStreamErrorEvent
  | RagStreamActionRequiredEvent
  | RagStreamSubqueriesEvent;

export interface TraceEvent {
  run_id: string;
  event_id?: string;
  stage: string;
  event_type: string;
  timestamp: string;
  iteration?: number;
  latency_ms?: number | null;
  payload: Record<string, unknown>;
  citations_chosen?: string[] | null;
}

export interface SessionDetail {
  summary: SessionSummary;
  messages: SessionMessage[];
  feedback: unknown[];
  traces: Record<string, unknown>;
}

interface SseMessage<T> {
  id: string | null;
  event: string | null;
  data: T;
}

async function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (error) {
    if (
      typeof error === "object" &&
      error !== null &&
      "name" in error &&
      error.name === "AbortError"
    ) {
      throw error;
    }
    throw new Error("Connection error: server unreachable");
  }
}

async function readSseEvents<T>(
  res: Response,
  onEvent: (event: SseMessage<T>) => void,
): Promise<void> {
  if (!res.body) {
    throw new Error("Streaming response missing body");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flushBuffer = (rawBuffer: string, forceFlush = false): string => {
    const normalized = rawBuffer.replace(/\r\n/g, "\n");
    const frames = normalized.split("\n\n");
    const remainder = forceFlush ? "" : (frames.pop() ?? "");

    for (const frame of forceFlush ? frames.filter(Boolean) : frames) {
      const message = parseSseMessage<T>(frame);
      if (message) {
        onEvent(message);
      }
    }

    if (forceFlush) {
      const trailing = parseSseMessage<T>(remainder);
      if (trailing) {
        onEvent(trailing);
      }
    }

    return remainder;
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
    } else if (value) {
      buffer += decoder.decode(value, { stream: true });
    }

    buffer = flushBuffer(buffer, done);

    if (done) {
      return;
    }
  }
}

function parseSseMessage<T>(frame: string): SseMessage<T> | null {
  const trimmedFrame = frame.trim();
  if (!trimmedFrame) {
    return null;
  }

  let id: string | null = null;
  let event: string | null = null;
  const dataLines: string[] = [];

  for (const rawLine of trimmedFrame.split("\n")) {
    const line = rawLine.trimEnd();
    if (!line || line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("id:")) {
      id = line.slice(3).trim();
      continue;
    }
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  return {
    id,
    event,
    data: JSON.parse(dataLines.join("\n")) as T,
  };
}

export async function fetchSessions(
  search = "",
): Promise<SessionSummary[]> {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  const url = `${await getApiBase()}/v1/sessions${params.toString() ? `?${params}` : ""}`;
  const res = await apiFetch(url);
  if (!res.ok) throw new Error(`Failed to fetch sessions: ${res.status}`);
  return res.json();
}

export async function fetchSession(
  sessionId: string,
): Promise<SessionDetail> {
  const res = await apiFetch(`${await getApiBase()}/v1/sessions/${sessionId}`);
  if (!res.ok) throw new Error(`Failed to fetch session: ${res.status}`);
  return res.json();
}

export async function fetchTraceEvents(runId: string): Promise<TraceEvent[]> {
  const res = await apiFetch(`${await getApiBase()}/v1/traces/${encodeURIComponent(runId)}`);
  if (!res.ok) throw new Error(`Failed to fetch trace: ${res.status}`);
  return res.json();
}

export async function fetchSettings(): Promise<Record<string, unknown>> {
  const res = await apiFetch(`${await getApiBase()}/v1/settings`);
  if (!res.ok) throw new Error(`Failed to fetch settings: ${res.status}`);
  return res.json();
}

export async function updateSettings(
  updates: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const res = await apiFetch(`${await getApiBase()}/v1/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ updates }),
  });
  if (!res.ok) {
    const text = await res.text();
    let message = text;
    try {
      const json = JSON.parse(text) as { detail?: string };
      if (json.detail) message = json.detail;
    } catch {
      // use raw text
    }
    throw new Error(message);
  }
  return res.json();
}

export async function fetchIndexes(): Promise<IndexSummary[]> {
  const res = await apiFetch(`${await getApiBase()}/v1/index/list`);
  if (!res.ok) throw new Error(`Failed to fetch indexes: ${res.status}`);
  return res.json();
}

export async function queryRag(
  manifest_path: string,
  question: string,
  settings: Record<string, unknown>,
): Promise<RagQueryResult> {
  const res = await apiFetch(`${await getApiBase()}/v1/query/rag`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ manifest_path, question, settings }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`RAG query failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function queryRagStream(
  manifest_path: string,
  question: string,
  settings: Record<string, unknown>,
  options: {
    signal?: AbortSignal;
    runId?: string;
    lastEventId?: number | null;
    onEvent: (event: RagStreamEvent, meta: { eventId: number | null }) => void;
  },
): Promise<void> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (
    typeof options.lastEventId === "number" &&
    Number.isFinite(options.lastEventId) &&
    options.lastEventId > 0
  ) {
    headers["Last-Event-ID"] = String(options.lastEventId);
  }

  const res = await apiFetch(`${await getApiBase()}/v1/query/rag/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      manifest_path,
      question,
      settings,
      run_id: options.runId,
    }),
    signal: options.signal,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`RAG stream failed (${res.status}): ${detail}`);
  }
  await readSseEvents<RagStreamEvent>(res, (message) => {
    const parsedEventId =
      message.id && /^-?\d+$/.test(message.id)
        ? Number.parseInt(message.id, 10)
        : Number.NaN;
    options.onEvent(message.data, {
      eventId: Number.isFinite(parsedEventId) ? parsedEventId : null,
    });
  });
}

export interface IndexBuildResult {
  index_id: string;
  manifest_path: string;
  document_count: number;
  chunk_count: number;
  embedding_signature: string;
  vector_backend: string;
}

export async function uploadFiles(files: File[]): Promise<{ paths: string[] }> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  const res = await apiFetch(`${await getApiBase()}/v1/files/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Upload failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function buildIndexStream(
  documentPaths: string[],
  settings: Record<string, unknown>,
  onEvent: (event: Record<string, unknown>) => void,
): Promise<IndexBuildResult> {
  const res = await apiFetch(`${await getApiBase()}/v1/index/build/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_paths: documentPaths, settings }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Build stream failed (${res.status}): ${detail}`);
  }
  let buildResult: IndexBuildResult | null = null;
  await readSseEvents<Record<string, unknown>>(res, ({ data: event }) => {
    onEvent(event);
    if (event.type === "error") {
      throw new Error(String(event.message ?? "Build error"));
    }
    if (event.type === "build_complete") {
      buildResult = event as unknown as IndexBuildResult;
    }
  });
  if (buildResult) return buildResult;
  throw new Error("Build stream ended without completion");
}

export async function submitRunAction(
  runId: string,
  body: { approved: boolean; payload?: Record<string, unknown> },
): Promise<void> {
  const res = await apiFetch(
    `${await getApiBase()}/v1/runs/${encodeURIComponent(runId)}/actions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  // 501 is expected for the stub — don't throw
  if (!res.ok && res.status !== 501) {
    const detail = await res.text();
    throw new Error(`Action submit failed (${res.status}): ${detail}`);
  }
}

export async function queryDirect(
  prompt: string,
  settings: Record<string, unknown>,
): Promise<DirectQueryResult> {
  const res = await apiFetch(`${await getApiBase()}/v1/query/direct`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, settings }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Direct query failed (${res.status}): ${detail}`);
  }
  return res.json();
}
