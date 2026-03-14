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
