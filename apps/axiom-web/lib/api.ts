const API_BASE =
  process.env.NEXT_PUBLIC_AXIOM_API_BASE ?? "http://127.0.0.1:8000";

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

export interface SessionMessage {
  role: string;
  content: string;
  ts: string;
  run_id: string;
  sources: EvidenceSource[];
  llm_provider?: string;
  llm_model?: string;
  query_mode?: string;
}

export interface DirectQueryResult {
  run_id: string;
  answer_text: string;
  selected_mode: string;
  llm_provider: string;
  llm_model: string;
}

export interface EvidenceSource {
  sid: string;
  source: string;
  snippet: string;
  title: string;
  score: number | null;
  breadcrumb: string;
  section_hint: string;
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

export interface ActionRequiredAction {
  kind: string;
  summary: string;
  payload: Record<string, unknown>;
}

export interface RagStreamActionRequiredEvent {
  type: "action_required";
  run_id: string;
  action: ActionRequiredAction;
}

export type RagStreamEvent =
  | RagStreamRunStartedEvent
  | RagStreamRetrievalCompleteEvent
  | RagStreamTokenEvent
  | RagStreamFinalEvent
  | RagStreamErrorEvent
  | RagStreamActionRequiredEvent;

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
  onEvent: (event: T) => void,
): Promise<void> {
  if (!res.body) {
    throw new Error("Streaming response missing body");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
    } else if (value) {
      buffer += decoder.decode(value, { stream: true });
    }

    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() ?? "";

    for (const rawLine of lines) {
      const line = rawLine.trimEnd();
      if (!line.startsWith("data: ")) continue;
      onEvent(JSON.parse(line.slice(6)) as T);
    }

    if (done) {
      const finalLine = buffer.trim();
      if (finalLine.startsWith("data: ")) {
        onEvent(JSON.parse(finalLine.slice(6)) as T);
      }
      return;
    }
  }
}

export async function fetchSessions(
  search = "",
): Promise<SessionSummary[]> {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  const url = `${API_BASE}/v1/sessions${params.toString() ? `?${params}` : ""}`;
  const res = await apiFetch(url);
  if (!res.ok) throw new Error(`Failed to fetch sessions: ${res.status}`);
  return res.json();
}

export async function fetchSession(
  sessionId: string,
): Promise<SessionDetail> {
  const res = await apiFetch(`${API_BASE}/v1/sessions/${sessionId}`);
  if (!res.ok) throw new Error(`Failed to fetch session: ${res.status}`);
  return res.json();
}

export async function fetchTraceEvents(runId: string): Promise<TraceEvent[]> {
  const res = await apiFetch(`${API_BASE}/v1/traces/${encodeURIComponent(runId)}`);
  if (!res.ok) throw new Error(`Failed to fetch trace: ${res.status}`);
  return res.json();
}

export async function fetchSettings(): Promise<Record<string, unknown>> {
  const res = await apiFetch(`${API_BASE}/v1/settings`);
  if (!res.ok) throw new Error(`Failed to fetch settings: ${res.status}`);
  return res.json();
}

export async function updateSettings(
  updates: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const res = await apiFetch(`${API_BASE}/v1/settings`, {
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
  const res = await apiFetch(`${API_BASE}/v1/index/list`);
  if (!res.ok) throw new Error(`Failed to fetch indexes: ${res.status}`);
  return res.json();
}

export async function queryRag(
  manifest_path: string,
  question: string,
  settings: Record<string, unknown>,
): Promise<RagQueryResult> {
  const res = await apiFetch(`${API_BASE}/v1/query/rag`, {
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
    onEvent: (event: RagStreamEvent) => void;
  },
): Promise<void> {
  const res = await apiFetch(`${API_BASE}/v1/query/rag/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ manifest_path, question, settings }),
    signal: options.signal,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`RAG stream failed (${res.status}): ${detail}`);
  }
  await readSseEvents<RagStreamEvent>(res, options.onEvent);
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
  const res = await apiFetch(`${API_BASE}/v1/files/upload`, { method: "POST", body: form });
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
  const res = await apiFetch(`${API_BASE}/v1/index/build/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_paths: documentPaths, settings }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Build stream failed (${res.status}): ${detail}`);
  }
  let buildResult: IndexBuildResult | null = null;
  await readSseEvents<Record<string, unknown>>(res, (event) => {
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
    `${API_BASE}/v1/runs/${encodeURIComponent(runId)}/actions`,
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
  const res = await apiFetch(`${API_BASE}/v1/query/direct`, {
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
