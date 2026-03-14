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

export interface SessionDetail {
  summary: SessionSummary;
  messages: SessionMessage[];
  feedback: unknown[];
  traces: Record<string, unknown>;
}

async function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch {
    throw new Error("Connection error: server unreachable");
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
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const event = JSON.parse(line.slice(6)) as Record<string, unknown>;
      onEvent(event);
      if (event.type === "error") throw new Error(String(event.message ?? "Build error"));
      if (event.type === "build_complete") return event as unknown as IndexBuildResult;
    }
  }
  throw new Error("Build stream ended without completion");
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
