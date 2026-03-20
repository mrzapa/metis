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
        if (url) {
          // Verify the API is healthy before returning the URL
          try {
            const healthRes = await fetch(`${url}/healthz`, { signal: AbortSignal.timeout(5000) });
            if (healthRes.ok) {
              return url;
            }
          } catch {
            // Health check failed, continue polling or fall through
          }
        }
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
  retrieval_plan: RetrievalPlan;
  fallback: RetrievalFallback;
}

export interface RetrievalFallback {
  triggered?: boolean;
  strategy?: string;
  reason?: string;
  min_score?: number;
  observed_score?: number;
  message?: string;
}

export interface RetrievalPlanStage {
  stage_type: string;
  payload: Record<string, unknown>;
}

export interface RetrievalPlan {
  question?: string;
  selected_mode?: string;
  effective_queries?: string[];
  fallback?: RetrievalFallback;
  stages: RetrievalPlanStage[];
  top_score?: number;
  source_count?: number;
}

export interface KnowledgeSearchResult {
  run_id: string;
  summary_text: string;
  sources: EvidenceSource[];
  context_block: string;
  top_score: number;
  selected_mode: string;
  retrieval_plan: RetrievalPlan;
  fallback: RetrievalFallback;
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

export interface RagStreamRetrievalAugmentedEvent {
  type: "retrieval_augmented";
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
  fallback?: RetrievalFallback;
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

export interface RagStreamFallbackDecisionEvent {
  type: "fallback_decision";
  run_id: string;
  fallback: RetrievalFallback;
}

export interface RagStreamIterationStartEvent {
  type: "iteration_start";
  run_id: string;
  iteration: number;
  total_iterations: number;
}

export interface RagStreamGapsIdentifiedEvent {
  type: "gaps_identified";
  run_id: string;
  gaps: string[];
  iteration: number;
}

export interface RagStreamRefinementRetrievalEvent {
  type: "refinement_retrieval";
  run_id: string;
  iteration: number;
  sources: EvidenceSource[];
  context_block: string;
  top_score: number;
}

export type RagStreamEvent =
  | RagStreamRunStartedEvent
  | RagStreamRetrievalCompleteEvent
  | RagStreamRetrievalAugmentedEvent
  | RagStreamTokenEvent
  | RagStreamFinalEvent
  | RagStreamErrorEvent
  | RagStreamActionRequiredEvent
  | RagStreamSubqueriesEvent
  | RagStreamFallbackDecisionEvent
  | RagStreamIterationStartEvent
  | RagStreamGapsIdentifiedEvent
  | RagStreamRefinementRetrievalEvent;

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

export interface AssistantIdentity {
  assistant_id: string;
  name: string;
  archetype: string;
  companion_enabled: boolean;
  greeting: string;
  prompt_seed: string;
  docked: boolean;
  minimized: boolean;
}

export interface AssistantRuntime {
  provider: string;
  model: string;
  local_gguf_model_path: string;
  local_gguf_context_length: number;
  local_gguf_gpu_layers: number;
  local_gguf_threads: number;
  fallback_to_primary: boolean;
  auto_bootstrap: boolean;
  auto_install: boolean;
  bootstrap_state: string;
  recommended_model_name: string;
  recommended_quant: string;
  recommended_use_case: string;
}

export interface AssistantPolicy {
  reflection_enabled: boolean;
  reflection_backend: string;
  reflection_cooldown_seconds: number;
  max_memory_entries: number;
  max_playbooks: number;
  max_brain_links: number;
  trigger_on_onboarding: boolean;
  trigger_on_index_build: boolean;
  trigger_on_completed_run: boolean;
  allow_automatic_writes: boolean;
}

export interface AssistantStatus {
  state: string;
  paused: boolean;
  runtime_ready: boolean;
  runtime_source: string;
  runtime_provider: string;
  runtime_model: string;
  bootstrap_state: string;
  bootstrap_message: string;
  recommended_model_name: string;
  recommended_quant: string;
  recommended_use_case: string;
  last_reflection_at: string;
  last_reflection_trigger: string;
  latest_summary: string;
  latest_why: string;
}

export interface AssistantMemoryEntry {
  entry_id: string;
  created_at: string;
  kind: string;
  title: string;
  summary: string;
  details: string;
  why: string;
  provenance: string;
  confidence: number;
  trigger: string;
  context_id: string;
  session_id: string;
  run_id: string;
  tags: string[];
  related_node_ids: string[];
}

export interface AssistantPlaybook {
  playbook_id: string;
  created_at: string;
  title: string;
  bullets: string[];
  source_session_id: string;
  source_run_id: string;
  provenance: string;
  confidence: number;
  active: boolean;
}

export interface AssistantBrainLink {
  link_id: string;
  created_at: string;
  source_node_id: string;
  target_node_id: string;
  relation: string;
  label: string;
  provenance: string;
  summary: string;
  confidence: number;
  session_id: string;
  run_id: string;
  metadata: Record<string, unknown>;
}

export interface AssistantSnapshot {
  identity: AssistantIdentity;
  runtime: AssistantRuntime;
  policy: AssistantPolicy;
  status: AssistantStatus;
  memory: AssistantMemoryEntry[];
  playbooks: AssistantPlaybook[];
  brain_links: AssistantBrainLink[];
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

export async function createSession(title: string): Promise<SessionSummary> {
  const res = await apiFetch(`${await getApiBase()}/v1/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`Failed to create session: ${res.status}`);
  return res.json();
}

export async function fetchSession(
  sessionId: string,
): Promise<SessionDetail> {
  const res = await apiFetch(`${await getApiBase()}/v1/sessions/${sessionId}`);
  if (!res.ok) throw new Error(`Failed to fetch session: ${res.status}`);
  return res.json();
}

export async function submitFeedback(
  sessionId: string,
  runId: string,
  vote: 1 | -1,
  note = "",
): Promise<void> {
  const res = await apiFetch(
    `${await getApiBase()}/v1/sessions/${encodeURIComponent(sessionId)}/feedback`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, vote, note }),
    },
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Feedback submit failed (${res.status}): ${detail}`);
  }
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
  sessionId?: string,
): Promise<RagQueryResult> {
  const res = await apiFetch(`${await getApiBase()}/v1/query/rag`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ manifest_path, question, settings, session_id: sessionId ?? "" }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`RAG query failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function queryKnowledgeSearch(
  manifest_path: string,
  question: string,
  settings: Record<string, unknown>,
  options?: {
    runId?: string;
    sessionId?: string | null;
  },
): Promise<KnowledgeSearchResult> {
  const res = await apiFetch(`${await getApiBase()}/v1/search/knowledge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      manifest_path,
      question,
      settings,
      run_id: options?.runId,
      session_id: options?.sessionId ?? "",
    }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Knowledge search failed (${res.status}): ${detail}`);
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
    sessionId?: string | null;
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
      session_id: options.sessionId ?? "",
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
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Action submit failed (${res.status}): ${detail}`);
  }
}

export interface LogTailResult {
  lines: string[];
  missing: boolean;
  log_path: string;
  total_lines?: number;
}

export async function fetchLogTail(): Promise<LogTailResult> {
  const res = await apiFetch(`${await getApiBase()}/v1/logs/tail`);
  if (!res.ok) throw new Error(`Failed to fetch log tail: ${res.status}`);
  return res.json();
}

export interface ApiVersion {
  version: string;
  min_compatible: string;
}

export async function fetchApiVersion(): Promise<string> {
  try {
    const res = await apiFetch(`${await getApiBase()}/v1/version`);
    if (!res.ok) return "unknown";
    const data = (await res.json()) as ApiVersion;
    return data.version;
  } catch {
    return "unknown";
  }
}

export async function checkApiCompatibility(): Promise<{
  compatible: boolean;
  warning: string | null;
}> {
  try {
    const res = await apiFetch(`${await getApiBase()}/v1/version`);
    if (!res.ok) {
      return { compatible: false, warning: "Could not connect to API" };
    }
    const data = (await res.json()) as ApiVersion;
    const apiVersion = data.version;
    const minCompatible = data.min_compatible || apiVersion;

    const apiMajor = parseInt(apiVersion.split(".")[0] || "0", 10);
    const minMajor = parseInt(minCompatible.split(".")[0] || "0", 10);

    if (apiMajor !== minMajor) {
      return {
        compatible: false,
        warning: `API version ${apiVersion} is incompatible with frontend. Minimum compatible: ${minCompatible}`,
      };
    }

    return { compatible: true, warning: null };
  } catch {
    return { compatible: false, warning: "Could not connect to API for compatibility check" };
  }
}

export async function queryDirect(
  prompt: string,
  settings: Record<string, unknown>,
  sessionId?: string,
): Promise<DirectQueryResult> {
  const res = await apiFetch(`${await getApiBase()}/v1/query/direct`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, settings, session_id: sessionId ?? "" }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Direct query failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export interface GgufCatalogEntry {
  model_name: string;
  provider: string;
  parameter_count: string;
  architecture: string;
  use_case: string;
  fit_level: string;
  run_mode: string;
  best_quant: string;
  estimated_tps: number;
  memory_required_gb: number;
  memory_available_gb: number;
  recommended_context_length: number;
  source_repo: string;
  source_provider: string;
}

export interface GgufHardwareProfile {
  total_ram_gb: number;
  available_ram_gb: number;
  total_cpu_cores: number;
  cpu_name: string;
  has_gpu: boolean;
  gpu_vram_gb: number | null;
  total_gpu_vram_gb: number | null;
  gpu_name: string;
  gpu_count: number;
  unified_memory: boolean;
  backend: string;
  detected: boolean;
  override_enabled: boolean;
  notes: string[];
}

export interface GgufInstalledEntry {
  id: string;
  name: string;
  path: string;
  metadata: Record<string, unknown>;
}

export interface GgufValidateResult {
  valid: boolean;
  path: string;
  filename: string;
  file_size_bytes: number;
  quant: string;
  is_instruct: boolean;
}

export async function fetchGgufCatalog(useCase = "general"): Promise<GgufCatalogEntry[]> {
  const res = await apiFetch(`${await getApiBase()}/v1/gguf/catalog?use_case=${encodeURIComponent(useCase)}`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to fetch GGUF catalogue (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function fetchGgufHardware(): Promise<GgufHardwareProfile> {
  const res = await apiFetch(`${await getApiBase()}/v1/gguf/hardware`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to fetch GGUF hardware (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function fetchGgufInstalled(): Promise<GgufInstalledEntry[]> {
  const res = await apiFetch(`${await getApiBase()}/v1/gguf/installed`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to fetch installed GGUF models (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function validateGgufModel(modelPath: string): Promise<GgufValidateResult> {
  const res = await apiFetch(`${await getApiBase()}/v1/gguf/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model_path: modelPath }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`GGUF validation failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function refreshGgufCatalog(useCase = "general"): Promise<{ status: string; use_case: string; advisory_only: boolean }> {
  const res = await apiFetch(`${await getApiBase()}/v1/gguf/refresh?use_case=${encodeURIComponent(useCase)}`, {
    method: "POST",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to refresh GGUF catalogue (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function registerGgufModel(
  name: string,
  path: string,
  metadata?: Record<string, unknown>,
): Promise<{ status: string; id: string; name: string; path: string }> {
  const res = await apiFetch(`${await getApiBase()}/v1/gguf/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, path, metadata: metadata || {} }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to register GGUF model (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function unregisterGgufModel(id: string): Promise<{ status: string; id: string }> {
  const res = await apiFetch(`${await getApiBase()}/v1/gguf/installed/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to unregister GGUF model (${res.status}): ${detail}`);
  }
  return res.json();
}

// ── Brain graph ────────────────────────────────────────────────────────────

export interface BrainGraphNode {
  node_id: string;
  node_type: "category" | "index" | "session";
  label: string;
  x: number;
  y: number;
  metadata: Record<string, unknown>;
}

export interface BrainGraphEdge {
  source_id: string;
  target_id: string;
  edge_type: string;
  metadata: Record<string, unknown>;
}

export interface BrainGraphResponse {
  nodes: BrainGraphNode[];
  edges: BrainGraphEdge[];
}

export async function fetchBrainGraph(): Promise<BrainGraphResponse> {
  const res = await apiFetch(`${await getApiBase()}/v1/brain/graph`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to fetch brain graph (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function fetchAssistant(): Promise<AssistantSnapshot> {
  const res = await apiFetch(`${await getApiBase()}/v1/assistant`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to fetch assistant (${res.status}): ${detail}`);
  }
  return res.json();
}

export interface AssistantSettings {
  assistant_identity: AssistantIdentity;
  assistant_runtime: AssistantRuntime;
  assistant_policy: AssistantPolicy;
}

export interface AssistantSettingsUpdate {
  assistant_identity?: Partial<AssistantIdentity>;
  assistant_runtime?: Partial<AssistantRuntime>;
  assistant_policy?: Partial<AssistantPolicy>;
}

export async function fetchAssistantSettings(): Promise<AssistantSettings> {
  const snapshot = await fetchAssistant();
  return {
    assistant_identity: snapshot.identity,
    assistant_runtime: snapshot.runtime,
    assistant_policy: snapshot.policy,
  };
}

export async function updateAssistant(payload: {
  identity?: Record<string, unknown>;
  runtime?: Record<string, unknown>;
  policy?: Record<string, unknown>;
  status?: Record<string, unknown>;
}): Promise<AssistantSnapshot> {
  const res = await apiFetch(`${await getApiBase()}/v1/assistant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to update assistant (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function updateAssistantSettings(
  payload: AssistantSettingsUpdate,
): Promise<AssistantSettings> {
  const snapshot = await updateAssistant({
    identity: payload.assistant_identity,
    runtime: payload.assistant_runtime,
    policy: payload.assistant_policy,
  });
  return {
    assistant_identity: snapshot.identity,
    assistant_runtime: snapshot.runtime,
    assistant_policy: snapshot.policy,
  };
}

export async function fetchAssistantStatus(): Promise<AssistantStatus> {
  const res = await apiFetch(`${await getApiBase()}/v1/assistant/status`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to fetch assistant status (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function reflectAssistant(payload: {
  trigger?: string;
  context_id?: string;
  session_id?: string;
  run_id?: string;
  force?: boolean;
}): Promise<Record<string, unknown>> {
  const res = await apiFetch(`${await getApiBase()}/v1/assistant/reflect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      trigger: payload.trigger ?? "manual",
      context_id: payload.context_id ?? "",
      session_id: payload.session_id ?? "",
      run_id: payload.run_id ?? "",
      force: Boolean(payload.force),
    }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to reflect assistant (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function bootstrapAssistant(
  installLocalModel = false,
): Promise<AssistantSnapshot> {
  const res = await apiFetch(`${await getApiBase()}/v1/assistant/bootstrap`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ install_local_model: installLocalModel }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to bootstrap assistant (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function fetchAssistantMemory(limit = 20): Promise<AssistantMemoryEntry[]> {
  const res = await apiFetch(`${await getApiBase()}/v1/assistant/memory?limit=${encodeURIComponent(String(limit))}`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to fetch assistant memory (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function clearAssistantMemory(limit = 10): Promise<Record<string, unknown>> {
  const res = await apiFetch(`${await getApiBase()}/v1/assistant/memory?limit=${encodeURIComponent(String(limit))}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to clear assistant memory (${res.status}): ${detail}`);
  }
  return res.json();
}
