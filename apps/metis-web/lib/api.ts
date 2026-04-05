import type {
  ActionRequiredAction,
  ArrowArtifact,
  ChatMessageContent,
  EvidenceSource,
  NyxInstallAction,
  NyxInstallActionInstaller,
  NyxInstallActionPayload,
  NyxInstallActionResult,
  NyxInstallProposal,
  NyxInstallProposalComponent,
} from "@/lib/chat-types";
import { emitBrainGraphRagActivity } from "@/lib/brain-graph-rag-activity";

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
  return process.env.NEXT_PUBLIC_METIS_API_BASE ?? "http://127.0.0.1:8000";
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
  artifacts?: ArrowArtifact[];
  actions?: NyxInstallAction[];
}

export interface ForecastMapping {
  timestamp_column: string;
  target_column: string;
  dynamic_covariates: string[];
  static_covariates: string[];
}

export interface ForecastSchemaColumn {
  name: string;
  detected_type: string;
  non_null_count: number;
  unique_count: number;
  numeric_ratio: number;
  timestamp_ratio: number;
  sample_values: string[];
}

export interface ForecastValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  history_row_count: number;
  future_row_count: number;
  inferred_horizon: number;
  resolved_horizon: number;
  inferred_frequency: string;
}

export interface ForecastPreflightResult {
  ready: boolean;
  timesfm_available: boolean;
  covariates_available: boolean;
  model_id: string;
  max_context: number;
  max_horizon: number;
  xreg_mode: string;
  force_xreg_cpu: boolean;
  warnings: string[];
  install_guidance: string[];
}

export interface ForecastSchemaResult {
  file_path: string;
  file_name: string;
  delimiter: string;
  row_count: number;
  column_count: number;
  columns: ForecastSchemaColumn[];
  timestamp_candidates: string[];
  numeric_target_candidates: string[];
  suggested_mapping?: ForecastMapping | null;
  validation: ForecastValidationResult;
}

export interface ForecastQueryResult {
  run_id: string;
  answer_text: string;
  selected_mode: string;
  query_mode?: string;
  model_backend: string;
  model_id: string;
  horizon: number;
  context_used: number;
  warnings: string[];
  artifacts?: ArrowArtifact[];
}

export interface IndexSummary {
  index_id: string;
  manifest_path: string;
  document_count: number;
  chunk_count: number;
  backend: string;
  created_at: string;
  embedding_signature: string;
  brain_pass?: BrainPassMetadata;
}

export interface IndexDeleteResult {
  deleted: boolean;
  manifest_path: string;
  index_id: string;
}

export interface LearningRoutePreviewStarSnapshot {
  id: string;
  label?: string;
  intent?: string;
  notes?: string;
  active_manifest_path?: string;
  linked_manifest_paths?: string[];
  connected_user_star_ids?: string[];
}

export interface LearningRoutePreviewStep {
  id: string;
  kind: "orient" | "foundations" | "synthesis" | "apply";
  title: string;
  objective: string;
  rationale: string;
  manifest_path: string;
  source_star_id?: string | null;
  tutor_prompt: string;
  estimated_minutes: number;
}

export interface LearningRoutePreview {
  route_id: string;
  title: string;
  origin_star_id: string;
  created_at: string;
  updated_at: string;
  steps: LearningRoutePreviewStep[];
}

export interface LearningRoutePreviewRequest {
  origin_star: LearningRoutePreviewStarSnapshot;
  connected_stars: LearningRoutePreviewStarSnapshot[];
  indexes: Pick<
    IndexSummary,
    | "index_id"
    | "manifest_path"
    | "document_count"
    | "chunk_count"
    | "created_at"
    | "embedding_signature"
    | "brain_pass"
  >[];
}

export interface NyxCatalogFileSummary {
  path: string;
  file_type: string;
  target: string;
  content_bytes: number;
}

export interface NyxCatalogComponentSummary {
  component_name: string;
  title: string;
  description: string;
  curated_description: string;
  component_type: string;
  install_target: string;
  registry_url: string;
  schema_url: string;
  source: string;
  source_repo: string;
  required_dependencies: string[];
  dependencies: string[];
  dev_dependencies: string[];
  registry_dependencies: string[];
  file_count: number;
  targets: string[];
}

export interface NyxCatalogComponentDetail extends NyxCatalogComponentSummary {
  files: NyxCatalogFileSummary[];
}

export interface NyxCatalogSearchResponse {
  query: string;
  total: number;
  matched: number;
  curated_only: boolean;
  source: string;
  items: NyxCatalogComponentSummary[];
}

export interface BrainPassPlacement {
  faculty_id: string;
  confidence: number;
  rationale: string;
  provenance: string;
  secondary_faculty_id?: string;
  evidence?: string[];
}

export interface BrainPassNormalizedSource {
  source_path: string;
  source_name: string;
  source_modality: string;
  tribev2_input_modality: string;
  normalized_path?: string;
  extraction_method?: string;
  text_preview?: string;
  text_length?: number;
  metadata?: Record<string, unknown>;
}

export interface BrainPassMetadata {
  provider: string;
  native_available?: boolean;
  source_modalities?: string[];
  normalized_sources?: BrainPassNormalizedSource[];
  placement?: BrainPassPlacement;
  analysis?: Record<string, unknown>;
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
  artifacts?: ArrowArtifact[];
  actions?: NyxInstallAction[];
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

export interface RagStreamEnvelopeFields {
  event_id?: string;
  event_type?: string;
  status?: string;
  lifecycle?: string;
  timestamp?: string;
  payload?: Record<string, unknown>;
  context?: Record<string, unknown>;
  // Scion-inspired three-axis agent state model
  agent_phase?: "initializing" | "running" | "stopped" | "error";
  agent_activity?: "idle" | "thinking" | "executing" | "waiting_for_input" | "completed";
  detail?: { tool_name?: string; task_summary?: string; message?: string };
  ancestry?: string[];
  subject?: string;
}

export interface RagStreamRetrievalCompleteEvent extends RagStreamEnvelopeFields {
  type: "retrieval_complete";
  run_id: string;
  sources: EvidenceSource[];
  context_block: string;
  top_score: number;
}

export interface RagStreamRetrievalAugmentedEvent extends RagStreamEnvelopeFields {
  type: "retrieval_augmented";
  run_id: string;
  sources: EvidenceSource[];
  context_block: string;
  top_score: number;
}

export interface RagStreamTokenEvent extends RagStreamEnvelopeFields {
  type: "token";
  run_id: string;
  text: string;
}

export interface RagStreamFinalEvent extends RagStreamEnvelopeFields {
  type: "final";
  run_id: string;
  answer_text: string;
  sources: EvidenceSource[];
  fallback?: RetrievalFallback;
  artifacts?: ArrowArtifact[];
  actions?: NyxInstallAction[];
}

export interface RagStreamErrorEvent extends RagStreamEnvelopeFields {
  type: "error";
  run_id: string;
  message: string;
}

export interface ForecastStreamRunStartedEvent extends RagStreamEnvelopeFields {
  type: "run_started";
  run_id: string;
}

export interface ForecastStreamFinalEvent extends RagStreamEnvelopeFields {
  type: "final";
  run_id: string;
  answer_text: string;
  selected_mode: string;
  query_mode?: string;
  model_backend: string;
  model_id: string;
  horizon: number;
  context_used: number;
  warnings?: string[];
  artifacts?: ArrowArtifact[];
}

export interface ForecastStreamErrorEvent extends RagStreamEnvelopeFields {
  type: "error";
  run_id: string;
  message: string;
}

export interface RagStreamActionRequiredEvent extends RagStreamEnvelopeFields {
  type: "action_required";
  run_id: string;
  action: ActionRequiredAction;
}

export interface RagStreamSubqueriesEvent extends RagStreamEnvelopeFields {
  type: "subqueries";
  run_id: string;
  queries: string[];
}

export interface RagStreamFallbackDecisionEvent extends RagStreamEnvelopeFields {
  type: "fallback_decision";
  run_id: string;
  fallback: RetrievalFallback;
}

export interface RagStreamIterationStartEvent extends RagStreamEnvelopeFields {
  type: "iteration_start";
  run_id: string;
  iteration: number;
  total_iterations: number;
}

export interface RagStreamGapsIdentifiedEvent extends RagStreamEnvelopeFields {
  type: "gaps_identified";
  run_id: string;
  gaps: string[];
  iteration: number;
}

export interface RagStreamRefinementRetrievalEvent extends RagStreamEnvelopeFields {
  type: "refinement_retrieval";
  run_id: string;
  iteration: number;
  sources: EvidenceSource[];
  context_block: string;
  top_score: number;
}

export interface RagStreamIterationConvergedEvent extends RagStreamEnvelopeFields {
  type: "iteration_converged";
  run_id: string;
  iteration: number;
  convergence_score: number;
}

export interface RagStreamIterationCompleteEvent extends RagStreamEnvelopeFields {
  type: "iteration_complete";
  run_id: string;
  iterations_used: number;
  convergence_score: number;
  query_text: string;
}

export interface RagStreamRunStartedEvent extends RagStreamEnvelopeFields {
  type: "run_started";
  run_id: string;
}

export interface RagStreamSwarmStartEvent extends RagStreamEnvelopeFields {
  type: "swarm_start";
  run_id: string;
  n_personas: number;
  n_rounds: number;
  topics: string[];
}

export interface RagStreamSwarmRoundStartEvent extends RagStreamEnvelopeFields {
  type: "swarm_round_start";
  run_id: string;
  round: number;
  n_rounds: number;
}

export interface RagStreamSwarmPersonaVoteEvent extends RagStreamEnvelopeFields {
  type: "swarm_persona_vote";
  run_id: string;
  persona: string;
  stance: string;
  summary: string;
}

export interface RagStreamSwarmRoundEndEvent extends RagStreamEnvelopeFields {
  type: "swarm_round_end";
  run_id: string;
  round: number;
  consensus_delta: number;
}

export interface RagStreamSwarmSynthesisEvent extends RagStreamEnvelopeFields {
  type: "swarm_synthesis";
  run_id: string;
  method: string;
}

export interface RagStreamSwarmCompleteEvent extends RagStreamEnvelopeFields {
  type: "swarm_complete";
  run_id: string;
  answer_text: string;
  sources: EvidenceSource[];
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
  | RagStreamRefinementRetrievalEvent
  | RagStreamIterationConvergedEvent
  | RagStreamIterationCompleteEvent
  | RagStreamSwarmStartEvent
  | RagStreamSwarmRoundStartEvent
  | RagStreamSwarmPersonaVoteEvent
  | RagStreamSwarmRoundEndEvent
  | RagStreamSwarmSynthesisEvent
  | RagStreamSwarmCompleteEvent;

export type ForecastStreamEvent =
  | ForecastStreamRunStartedEvent
  | ForecastStreamFinalEvent
  | ForecastStreamErrorEvent;

type JsonRecord = Record<string, unknown>;

function getRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" ? (value as JsonRecord) : {};
}

function getText(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function getNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function getBoolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function getStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

function getEvidenceSources(value: unknown): EvidenceSource[] {
  return Array.isArray(value) ? (value as EvidenceSource[]) : [];
}

function getArrowArtifacts(value: unknown): ArrowArtifact[] | undefined {
  return Array.isArray(value) ? (value as ArrowArtifact[]) : undefined;
}

function getNyxInstallProposalComponents(
  value: unknown,
): NyxInstallProposalComponent[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => {
      const component = getRecord(item);
      return {
        component_name: getText(component.component_name),
        title: getText(component.title),
        description: getText(component.description),
        curated_description: getText(component.curated_description),
        component_type: getText(component.component_type),
        install_target: getText(component.install_target),
        registry_url: getText(component.registry_url),
        source_repo: getText(component.source_repo),
        required_dependencies: getStringArray(component.required_dependencies),
        dependencies: getStringArray(component.dependencies),
        dev_dependencies: getStringArray(component.dev_dependencies),
        registry_dependencies: getStringArray(component.registry_dependencies),
        file_count: getNumber(component.file_count),
        targets: getStringArray(component.targets),
        review_status: getText(component.review_status),
        previewable: getBoolean(component.previewable, true),
        installable: getBoolean(component.installable, true),
        install_path_policy: getText(component.install_path_policy),
        install_path_safe: getBoolean(component.install_path_safe, true),
        install_path_issues: getStringArray(component.install_path_issues),
        audit_issues: getStringArray(component.audit_issues),
      };
    })
    .filter((component) => component.component_name);
}

function getNyxInstallProposal(value: unknown): NyxInstallProposal {
  const proposal = getRecord(value);
  const componentNames = getStringArray(proposal.component_names);
  return {
    schema_version: getText(proposal.schema_version, "1.0"),
    proposal_token: getText(proposal.proposal_token),
    source: getText(proposal.source),
    run_id: getText(proposal.run_id),
    query: getText(proposal.query),
    intent_type: getText(proposal.intent_type),
    matched_signals: getStringArray(proposal.matched_signals),
    component_names: componentNames,
    component_count: getNumber(
      proposal.component_count,
      componentNames.length,
    ),
    components: getNyxInstallProposalComponents(proposal.components),
  };
}

function getNyxInstallActionPayload(value: unknown) {
  const payload = getRecord(value);
  return {
    action_id: getText(payload.action_id),
    action_type: "nyx_install" as const,
    proposal_token: getText(payload.proposal_token),
    component_count: getNumber(payload.component_count),
    component_names: getStringArray(payload.component_names),
  };
}

function getNyxInstallAction(value: unknown): NyxInstallAction {
  const action = getRecord(value);
  return {
    action_id: getText(action.action_id),
    action_type: "nyx_install",
    label: getText(action.label, "Approve Nyx install proposal"),
    summary: getText(action.summary, "Action required"),
    requires_approval: getBoolean(action.requires_approval, true),
    run_action_endpoint: getText(action.run_action_endpoint),
    payload: getNyxInstallActionPayload(action.payload),
    proposal: getNyxInstallProposal(action.proposal),
  };
}

function getNyxInstallActions(value: unknown): NyxInstallAction[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  const actions = value
    .map((item) => getNyxInstallAction(item))
    .filter((action) => action.action_id);
  return actions.length > 0 ? actions : undefined;
}

function getNyxInstallActionInstaller(
  value: unknown,
): NyxInstallActionInstaller | undefined {
  const installer = getRecord(value);
  const command = getStringArray(installer.command);
  const cwd = getText(installer.cwd);
  const packageScript = getText(installer.package_script);
  const returncode = getNumber(installer.returncode);
  const stdoutExcerpt = getText(installer.stdout_excerpt);
  const stderrExcerpt = getText(installer.stderr_excerpt);

  if (
    command.length === 0 &&
    !cwd &&
    !packageScript &&
    returncode === 0 &&
    !stdoutExcerpt &&
    !stderrExcerpt
  ) {
    return undefined;
  }

  return {
    command,
    cwd,
    package_script: packageScript,
    returncode,
    stdout_excerpt: stdoutExcerpt || undefined,
    stderr_excerpt: stderrExcerpt || undefined,
  };
}

function getNyxInstallActionResult(value: unknown): NyxInstallActionResult {
  const result = getRecord(value);
  const proposalRecord = getRecord(result.proposal);
  const installer = getNyxInstallActionInstaller(result.installer);
  const componentNames = getStringArray(result.component_names);
  return {
    run_id: getText(result.run_id),
    approved: getBoolean(result.approved),
    status: getText(result.status),
    action_id: getText(result.action_id),
    action_type: "nyx_install",
    proposal_token: getText(result.proposal_token),
    component_names: componentNames,
    component_count: getNumber(result.component_count, componentNames.length),
    execution_status: getText(result.execution_status),
    proposal: Object.keys(proposalRecord).length
      ? getNyxInstallProposal(proposalRecord)
      : null,
    installer: installer ?? null,
    failure_code: getText(result.failure_code) || undefined,
  };
}

function getActionRequiredAction(value: unknown): ActionRequiredAction {
  const action = getRecord(value);
  if (getText(action.action_type) === "nyx_install") {
    return getNyxInstallAction(action);
  }
  return {
    kind: getText(action.kind, "action_required"),
    summary: getText(action.summary, "Action required"),
    payload: getRecord(action.payload),
  };
}

function getEnvelopeFields(input: JsonRecord): RagStreamEnvelopeFields {
  const payload = getRecord(input.payload);
  const context = getRecord(input.context);
  const eventId = getText(input.event_id).trim();
  const eventType = getText(input.event_type).trim();
  const status = getText(input.status).trim();
  const lifecycle = getText(input.lifecycle).trim();
  const timestamp = getText(input.timestamp).trim();

  return {
    event_id: eventId || undefined,
    event_type: eventType || undefined,
    status: status || undefined,
    lifecycle: lifecycle || undefined,
    timestamp: timestamp || undefined,
    payload: Object.keys(payload).length ? payload : undefined,
    context: Object.keys(context).length ? context : undefined,
  };
}

export function normalizeRagStreamEvent(rawEvent: unknown): RagStreamEvent {
  const event = getRecord(rawEvent);
  const payload = getRecord(event.payload);
  const envelope = getEnvelopeFields(event);
  const type = getText(event.type || event.event_type).trim() || "error";
  const runId = getText(event.run_id || payload.run_id).trim();

  switch (type) {
    case "run_started":
      return { type: "run_started", run_id: runId, ...envelope };
    case "retrieval_complete":
    case "retrieval_augmented":
    case "refinement_retrieval": {
      const sources = getEvidenceSources(event.sources ?? payload.sources);
      const contextBlock = getText(event.context_block ?? payload.context_block);
      const topScore = getNumber(event.top_score ?? payload.top_score);
      if (type === "retrieval_complete") {
        return {
          type,
          run_id: runId,
          sources,
          context_block: contextBlock,
          top_score: topScore,
          ...envelope,
        };
      }
      if (type === "retrieval_augmented") {
        return {
          type,
          run_id: runId,
          sources,
          context_block: contextBlock,
          top_score: topScore,
          ...envelope,
        };
      }
      return {
        type,
        run_id: runId,
        iteration: getNumber(event.iteration ?? payload.iteration),
        sources,
        context_block: contextBlock,
        top_score: topScore,
        ...envelope,
      };
    }
    case "token":
      return {
        type: "token",
        run_id: runId,
        text: getText(event.text ?? payload.text),
        ...envelope,
      };
    case "final":
      return {
        type: "final",
        run_id: runId,
        answer_text: getText(event.answer_text ?? payload.answer_text),
        sources: getEvidenceSources(event.sources ?? payload.sources),
        fallback: getRecord(event.fallback ?? payload.fallback),
        artifacts: getArrowArtifacts(event.artifacts ?? payload.artifacts),
        actions: getNyxInstallActions(event.actions ?? payload.actions),
        ...envelope,
      };
    case "error":
      return {
        type: "error",
        run_id: runId,
        message: getText(event.message ?? payload.message, "Unknown stream error"),
        ...envelope,
      };
    case "action_required":
      return {
        type: "action_required",
        run_id: runId,
        action: getActionRequiredAction(event.action ?? payload.action),
        ...envelope,
      };
    case "subqueries":
      return {
        type: "subqueries",
        run_id: runId,
        queries: getStringArray(event.queries ?? payload.queries),
        ...envelope,
      };
    case "fallback_decision":
      return {
        type: "fallback_decision",
        run_id: runId,
        fallback: getRecord(event.fallback ?? payload.fallback),
        ...envelope,
      };
    case "iteration_start":
      return {
        type: "iteration_start",
        run_id: runId,
        iteration: getNumber(event.iteration ?? payload.iteration),
        total_iterations: getNumber(event.total_iterations ?? payload.total_iterations),
        ...envelope,
      };
    case "gaps_identified":
      return {
        type: "gaps_identified",
        run_id: runId,
        gaps: getStringArray(event.gaps ?? payload.gaps),
        iteration: getNumber(event.iteration ?? payload.iteration),
        ...envelope,
      };
    case "swarm_start":
      return {
        type: "swarm_start",
        run_id: runId,
        n_personas: getNumber(event.n_personas ?? payload.n_personas, 8),
        n_rounds: getNumber(event.n_rounds ?? payload.n_rounds, 4),
        topics: getStringArray(event.topics ?? payload.topics),
        ...envelope,
      };
    case "swarm_round_start":
      return {
        type: "swarm_round_start",
        run_id: runId,
        round: getNumber(event.round ?? payload.round),
        n_rounds: getNumber(event.n_rounds ?? payload.n_rounds, 4),
        ...envelope,
      };
    case "swarm_persona_vote":
      return {
        type: "swarm_persona_vote",
        run_id: runId,
        persona: getText(event.persona ?? payload.persona),
        stance: getText(event.stance ?? payload.stance),
        summary: getText(event.summary ?? payload.summary),
        ...envelope,
      };
    case "swarm_round_end":
      return {
        type: "swarm_round_end",
        run_id: runId,
        round: getNumber(event.round ?? payload.round),
        consensus_delta: getNumber(event.consensus_delta ?? payload.consensus_delta),
        ...envelope,
      };
    case "swarm_synthesis":
      return {
        type: "swarm_synthesis",
        run_id: runId,
        method: getText(event.method ?? payload.method, "majority_vote"),
        ...envelope,
      };
    case "swarm_complete":
      return {
        type: "swarm_complete",
        run_id: runId,
        answer_text: getText(event.answer_text ?? payload.answer_text),
        sources: getEvidenceSources(event.sources ?? payload.sources),
        ...envelope,
      };
    default:
      return {
        type: "error",
        run_id: runId,
        message: `Unsupported stream event type: ${type}`,
        ...envelope,
      };
  }
}

export function normalizeForecastStreamEvent(rawEvent: unknown): ForecastStreamEvent {
  const event = getRecord(rawEvent);
  const payload = getRecord(event.payload);
  const envelope = getEnvelopeFields(event);
  const type = getText(event.type || event.event_type).trim() || "error";
  const runId = getText(event.run_id || payload.run_id).trim();

  switch (type) {
    case "run_started":
      return { type: "run_started", run_id: runId, ...envelope };
    case "final":
      return {
        type: "final",
        run_id: runId,
        answer_text: getText(event.answer_text ?? payload.answer_text),
        selected_mode: getText(event.selected_mode ?? payload.selected_mode, "Forecast"),
        query_mode: getText(event.query_mode ?? payload.query_mode, "forecast"),
        model_backend: getText(event.model_backend ?? payload.model_backend),
        model_id: getText(event.model_id ?? payload.model_id),
        horizon: getNumber(event.horizon ?? payload.horizon),
        context_used: getNumber(event.context_used ?? payload.context_used),
        warnings: getStringArray(event.warnings ?? payload.warnings),
        artifacts: getArrowArtifacts(event.artifacts ?? payload.artifacts),
        ...envelope,
      };
    default:
      return {
        type: "error",
        run_id: runId,
        message: getText(event.message ?? payload.message, `Unsupported forecast stream event type: ${type}`),
        ...envelope,
      };
  }
}

/**
 * Normalized trace event emitted during query and indexing pipelines.
 * 
 * Event types follow the standardized taxonomy defined in docs/trace-events.md:
 * - STAGE: Pipeline phase transitions (stage_start, stage_end)
 * - TOOL: Model/service invocations (tool_invoke, tool_result, tool_error, tool_skip)
 * - CHECKPOINT: Validation points (checkpoint, validation_pass, validation_fail)
 * - CONTENT: Artifact transformations (content_added, content_revised)
 * - ITERATION: Agentic loop milestones (iteration_start, iteration_end)
 * 
 * The `payload` field may contain normalized fields like `status`, `message`,
 * `duration_ms`, and `context` for structured event consumption.
 */
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

export interface CompanionActivityEvent {
  source: "rag_stream" | "index_build" | "autonomous_research" | "reflection";
  state: "running" | "completed" | "error";
  trigger: string;
  summary: string;
  timestamp: number;
  payload?: Record<string, unknown>;
}

export interface AutoResearchStreamEvent {
  type:
    | "research_started"
    | "research_phase"
    | "research_complete"
    | "research_error"
    | "scanning"
    | "formulating"
    | "searching"
    | "synthesizing"
    | "indexing"
    | "complete"
    | "skipped";
  phase?: string;
  faculty_id?: string;
  detail?: string;
  result?: unknown;
  message?: string;
}

type CompanionActivityListener = (event: CompanionActivityEvent) => void;

const companionActivityListeners = new Set<CompanionActivityListener>();

export function subscribeCompanionActivity(listener: CompanionActivityListener): () => void {
  companionActivityListeners.add(listener);
  return () => {
    companionActivityListeners.delete(listener);
  };
}

function emitCompanionActivity(event: CompanionActivityEvent): void {
  for (const listener of companionActivityListeners) {
    try {
      listener(event);
    } catch {
      // Listeners should be isolated so one faulty subscriber cannot break others.
    }
  }
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
  autonomous_research_enabled?: boolean;
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

export type UiTelemetrySummaryWindowHours = 24 | 168;

export interface UiTelemetryDataQuality {
  events_with_run_id_pct: number | null;
  events_with_source_boundary_pct: number | null;
  events_with_client_timestamp_pct: number | null;
}

export interface UiTelemetrySummaryMetrics {
  exposure_count: number;
  render_attempt_count: number;
  render_success_rate: number | null;
  render_failure_rate: number | null;
  fallback_rate_by_reason: Record<string, number | null>;
  interaction_rate: number | null;
  runtime_attempt_rate: number | null;
  runtime_success_rate: number | null;
  runtime_failure_rate: number | null;
  runtime_skip_mix: Record<string, number | null>;
  data_quality: UiTelemetryDataQuality;
}

export interface UiTelemetryMetricEvaluation {
  metric: string;
  status: "pass" | "warn" | "fail";
  observed: number | null;
  sample_count: number;
  comparator: "min" | "max";
  go_threshold: number;
  rollback_threshold: number | null;
  reason: string;
}

export interface UiTelemetryThresholdSample {
  exposure_count: number;
  payload_detected_count: number;
  render_attempt_count: number;
  runtime_attempt_count: number;
  minimum_exposure_count_for_go: number;
}

export interface UiTelemetryThresholdEvaluation {
  per_metric: Record<string, UiTelemetryMetricEvaluation>;
  overall_recommendation: "go" | "hold" | "rollback_runtime" | "rollback_artifacts";
  failed_conditions: string[];
  sample: UiTelemetryThresholdSample;
}

export interface UiTelemetrySummary {
  window_hours: UiTelemetrySummaryWindowHours;
  generated_at: string;
  sampled_event_count: number;
  metrics: UiTelemetrySummaryMetrics;
  thresholds: UiTelemetryThresholdEvaluation;
}

interface SseMessage<T> {
  id: string | null;
  event: string | null;
  data: T;
}

function getApiBearerToken(): string | undefined {
  const token = process.env.NEXT_PUBLIC_METIS_API_TOKEN?.trim();
  return token || undefined;
}

export function getApiAuthHeaderValue(): string | undefined {
  const token = getApiBearerToken();
  return token ? `Bearer ${token}` : undefined;
}

function withApiAuth(init?: RequestInit): RequestInit | undefined {
  const authHeaderValue = getApiAuthHeaderValue();
  if (!authHeaderValue) {
    return init;
  }

  const headers = new Headers(init?.headers);
  if (!headers.has("Authorization")) {
    headers.set("Authorization", authHeaderValue);
  }

  return {
    ...init,
    headers,
  };
}

export async function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, withApiAuth(init));
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
  signal?: AbortSignal,
): Promise<SessionSummary[]> {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  const url = `${await getApiBase()}/v1/sessions${params.toString() ? `?${params}` : ""}`;
  const res = await apiFetch(url, { signal });
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

export async function fetchUiTelemetrySummary(
  windowHours: UiTelemetrySummaryWindowHours,
  limit?: number,
): Promise<UiTelemetrySummary> {
  const params = new URLSearchParams({ window_hours: String(windowHours) });
  if (typeof limit === "number" && Number.isFinite(limit) && limit > 0) {
    params.set("limit", String(Math.trunc(limit)));
  }

  const res = await apiFetch(`${await getApiBase()}/v1/telemetry/ui/summary?${params.toString()}`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to fetch UI telemetry summary (${windowHours}h): ${detail || res.status}`);
  }
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

export async function previewLearningRoute(
  payload: LearningRoutePreviewRequest,
): Promise<LearningRoutePreview> {
  const res = await apiFetch(`${await getApiBase()}/v1/learning-routes/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to preview learning route (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function deleteIndex(manifestPath: string): Promise<IndexDeleteResult> {
  const params = new URLSearchParams({ manifest_path: manifestPath });
  const res = await apiFetch(`${await getApiBase()}/v1/index?${params.toString()}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to delete index (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function fetchNyxCatalog(
  query = "",
  options?: { limit?: number },
): Promise<NyxCatalogSearchResponse> {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("q", query.trim());
  }
  if (
    typeof options?.limit === "number" &&
    Number.isFinite(options.limit) &&
    options.limit > 0
  ) {
    params.set("limit", String(Math.trunc(options.limit)));
  }

  const url = `${await getApiBase()}/v1/nyx/catalog${params.toString() ? `?${params.toString()}` : ""}`;
  const res = await apiFetch(url);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to fetch Nyx catalog (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function fetchNyxComponentDetail(
  componentName: string,
): Promise<NyxCatalogComponentDetail> {
  const res = await apiFetch(
    `${await getApiBase()}/v1/nyx/catalog/${encodeURIComponent(componentName)}`,
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to fetch Nyx component detail (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function fetchForecastPreflight(): Promise<ForecastPreflightResult> {
  const res = await apiFetch(`${await getApiBase()}/v1/forecast/preflight`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Forecast preflight failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function fetchForecastSchema(
  filePath: string,
  options?: {
    mapping?: ForecastMapping | null;
    horizon?: number | null;
  },
): Promise<ForecastSchemaResult> {
  const res = await apiFetch(`${await getApiBase()}/v1/forecast/schema`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_path: filePath,
      mapping: options?.mapping ?? undefined,
      horizon: options?.horizon ?? undefined,
    }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Forecast schema failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function queryForecast(
  filePath: string,
  prompt: string,
  mapping: ForecastMapping,
  settings: Record<string, unknown>,
  options?: {
    horizon?: number | null;
    sessionId?: string | null;
  },
): Promise<ForecastQueryResult> {
  const res = await apiFetch(`${await getApiBase()}/v1/query/forecast`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_path: filePath,
      prompt,
      mapping,
      settings,
      session_id: options?.sessionId ?? "",
      horizon: options?.horizon ?? undefined,
    }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Forecast query failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function queryForecastStream(
  filePath: string,
  prompt: string,
  mapping: ForecastMapping,
  settings: Record<string, unknown>,
  options: {
    signal?: AbortSignal;
    sessionId?: string | null;
    horizon?: number | null;
    onEvent: (event: ForecastStreamEvent) => void;
  },
): Promise<void> {
  const res = await apiFetch(`${await getApiBase()}/v1/query/forecast/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_path: filePath,
      prompt,
      mapping,
      settings,
      session_id: options.sessionId ?? "",
      horizon: options.horizon ?? undefined,
    }),
    signal: options.signal,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Forecast stream failed (${res.status}): ${detail}`);
  }
  await readSseEvents<unknown>(res, (message) => {
    options.onEvent(normalizeForecastStreamEvent(message.data));
  });
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
  emitCompanionActivity({
    source: "rag_stream",
    state: "running",
    trigger: "query_stream_started",
    summary: question,
    timestamp: Date.now(),
    payload: { manifest_path },
  });

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
    emitCompanionActivity({
      source: "rag_stream",
      state: "error",
      trigger: "query_stream_error",
      summary: detail,
      timestamp: Date.now(),
    });
    throw new Error(`RAG stream failed (${res.status}): ${detail}`);
  }
  await readSseEvents<unknown>(res, (message) => {
    const parsedEvent = normalizeRagStreamEvent(message.data);
    const parsedEventId =
      message.id && /^-?\d+$/.test(message.id)
        ? Number.parseInt(message.id, 10)
        : Number.NaN;
    options.onEvent(parsedEvent, {
      eventId: Number.isFinite(parsedEventId) ? parsedEventId : null,
    });

    if (parsedEvent.type === "run_started") {
      emitCompanionActivity({
        source: "rag_stream",
        state: "running",
        trigger: "query_run_started",
        summary: parsedEvent.run_id,
        timestamp: Date.now(),
      });
    } else if (
      parsedEvent.type === "retrieval_complete" ||
      parsedEvent.type === "retrieval_augmented" ||
      parsedEvent.type === "refinement_retrieval"
    ) {
      emitBrainGraphRagActivity({
        runId: parsedEvent.run_id,
        sessionId: options.sessionId ?? null,
        manifestPath: manifest_path,
        sources: parsedEvent.sources,
        timestamp: Date.now(),
      });
      emitCompanionActivity({
        source: "rag_stream",
        state: "running",
        trigger: "query_retrieval",
        summary: `Retrieved ${parsedEvent.sources.length} sources`,
        timestamp: Date.now(),
      });
    } else if (parsedEvent.type === "final") {
      emitBrainGraphRagActivity({
        runId: parsedEvent.run_id,
        sessionId: options.sessionId ?? null,
        manifestPath: manifest_path,
        sources: parsedEvent.sources,
        timestamp: Date.now(),
      });
      emitCompanionActivity({
        source: "rag_stream",
        state: "completed",
        trigger: "query_final",
        summary: parsedEvent.answer_text.slice(0, 200),
        timestamp: Date.now(),
      });
    } else if (parsedEvent.type === "error") {
      emitCompanionActivity({
        source: "rag_stream",
        state: "error",
        trigger: "query_error",
        summary: parsedEvent.message,
        timestamp: Date.now(),
      });
    }
  });
}

export interface IndexBuildResult {
  index_id: string;
  manifest_path: string;
  document_count: number;
  chunk_count: number;
  embedding_signature: string;
  vector_backend: string;
  brain_pass?: BrainPassMetadata;
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
  emitCompanionActivity({
    source: "index_build",
    state: "running",
    trigger: "index_build_started",
    summary: `${documentPaths.length} documents`,
    timestamp: Date.now(),
  });

  const res = await apiFetch(`${await getApiBase()}/v1/index/build/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_paths: documentPaths, settings }),
  });
  if (!res.ok) {
    const detail = await res.text();
    emitCompanionActivity({
      source: "index_build",
      state: "error",
      trigger: "index_build_error",
      summary: detail,
      timestamp: Date.now(),
    });
    throw new Error(`Build stream failed (${res.status}): ${detail}`);
  }
  let buildResult: IndexBuildResult | null = null;
  await readSseEvents<Record<string, unknown>>(res, ({ data: event }) => {
    onEvent(event);
    if (event.type === "status") {
      emitCompanionActivity({
        source: "index_build",
        state: "running",
        trigger: "index_build_status",
        summary: String(event.text ?? "Indexing"),
        timestamp: Date.now(),
      });
    }
    if (event.type === "error") {
      emitCompanionActivity({
        source: "index_build",
        state: "error",
        trigger: "index_build_error",
        summary: String(event.message ?? "Build error"),
        timestamp: Date.now(),
      });
      throw new Error(String(event.message ?? "Build error"));
    }
    if (event.type === "build_complete") {
      emitCompanionActivity({
        source: "index_build",
        state: "completed",
        trigger: "index_build_completed",
        summary: String(event.manifest_path ?? "Index build complete"),
        timestamp: Date.now(),
      });
      buildResult = event as unknown as IndexBuildResult;
    }
  });
  if (buildResult) return buildResult;
  throw new Error("Build stream ended without completion");
}

export async function buildWebGraphIndexStream(
  topic: string,
  settings: Record<string, unknown>,
  onEvent: (event: Record<string, unknown>) => void,
  indexId?: string,
): Promise<IndexBuildResult> {
  emitCompanionActivity({
    source: "index_build",
    state: "running",
    trigger: "index_build_started",
    summary: `Web graph: ${topic}`,
    timestamp: Date.now(),
  });

  const res = await apiFetch(`${await getApiBase()}/v1/index/build/web-graph/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, settings, index_id: indexId }),
  });
  if (!res.ok) {
    const detail = await res.text();
    emitCompanionActivity({
      source: "index_build",
      state: "error",
      trigger: "index_build_error",
      summary: detail,
      timestamp: Date.now(),
    });
    throw new Error(`Web graph build failed (${res.status}): ${detail}`);
  }
  let buildResult: IndexBuildResult | null = null;
  await readSseEvents<Record<string, unknown>>(res, ({ data: event }) => {
    onEvent(event);
    if (event.type === "build_started") {
      emitCompanionActivity({
        source: "index_build",
        state: "running",
        trigger: "index_build_status",
        summary: `Searching and scraping: ${String(event.topic ?? topic)}`,
        timestamp: Date.now(),
      });
    }
    if (event.type === "error") {
      emitCompanionActivity({
        source: "index_build",
        state: "error",
        trigger: "index_build_error",
        summary: String(event.message ?? "Build error"),
        timestamp: Date.now(),
      });
      throw new Error(String(event.message ?? "Build error"));
    }
    if (event.type === "build_complete") {
      emitCompanionActivity({
        source: "index_build",
        state: "completed",
        trigger: "index_build_completed",
        summary: String(event.manifest_path ?? "Web graph index complete"),
        timestamp: Date.now(),
      });
      buildResult = event as unknown as IndexBuildResult;
    }
  });
  if (buildResult) return buildResult;
  throw new Error("Web graph build stream ended without completion");
}

export async function submitRunAction(
  runId: string,
  body: {
    approved: boolean;
    action_id?: string;
    action_type?: string;
    proposal_token?: string;
    payload?: NyxInstallActionPayload | Record<string, unknown>;
  },
): Promise<RunActionResponse> {
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
  const payload = (await res.json()) as unknown;
  return parseRunActionResponse(payload);
}

export interface RunActionAcceptedResponse {
  run_id: string;
  approved: boolean;
  status: string;
}

export type RunActionResponse =
  | RunActionAcceptedResponse
  | NyxInstallActionResult;

function parseRunActionResponse(value: unknown): RunActionResponse {
  const payload = getRecord(value);
  if (getText(payload.action_type) === "nyx_install") {
    return getNyxInstallActionResult(payload);
  }
  return {
    run_id: getText(payload.run_id),
    approved: getBoolean(payload.approved),
    status: getText(payload.status, "accepted"),
  };
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
  score: number;
  recommendation_summary: string;
  notes: string[];
  caveats: string[];
  score_components: Record<string, number>;
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

export interface HereticPreflightResponse {
  ready: boolean;
  heretic_available: boolean;
  convert_script: string | null;
  errors: string[];
}

export interface HereticStreamStartedEvent {
  type: "started";
  message: string;
}

export interface HereticStreamProgressEvent {
  type: "progress";
  message: string;
}

export interface HereticStreamCompleteEvent {
  type: "complete";
  message: string;
  gguf_path?: string;
}

export interface HereticStreamErrorEvent {
  type: "error";
  message: string;
}

export type HereticStreamEvent =
  | HereticStreamStartedEvent
  | HereticStreamProgressEvent
  | HereticStreamCompleteEvent
  | HereticStreamErrorEvent;

function normalizeHereticStreamEvent(
  data: unknown,
  fallbackEventType: string | null,
): HereticStreamEvent {
  const payload = getRecord(data);
  const message = getText(payload.message, "");
  const payloadType = getText(payload.type).trim().toLowerCase();
  const eventType = (payloadType || String(fallbackEventType || "").trim().toLowerCase()) as
    | "started"
    | "progress"
    | "complete"
    | "error"
    | "";

  if (eventType === "complete") {
    return {
      type: "complete",
      message,
      gguf_path: getText(payload.gguf_path) || undefined,
    };
  }

  if (eventType === "error") {
    return {
      type: "error",
      message: message || "Heretic pipeline failed",
    };
  }

  if (eventType === "started") {
    return {
      type: "started",
      message,
    };
  }

  return {
    type: "progress",
    message,
  };
}

export async function fetchHereticPreflight(): Promise<HereticPreflightResponse> {
  const res = await apiFetch(`${await getApiBase()}/v1/heretic/preflight`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to fetch Heretic preflight (${res.status}): ${detail}`);
  }
  const payload = (await res.json()) as unknown;
  const record = getRecord(payload);
  return {
    ready: getBoolean(record.ready),
    heretic_available: getBoolean(record.heretic_available),
    convert_script: getText(record.convert_script) || null,
    errors: getStringArray(record.errors),
  };
}

export async function runHereticAbliterateStream(
  payload: {
    model_id: string;
    bnb_4bit?: boolean;
    outtype?: string;
  },
  options: {
    signal?: AbortSignal;
    onEvent: (event: HereticStreamEvent) => void;
  },
): Promise<void> {
  const res = await apiFetch(`${await getApiBase()}/v1/heretic/abliterate/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      model_id: payload.model_id,
      bnb_4bit: payload.bnb_4bit ?? false,
      outtype: payload.outtype ?? "f16",
    }),
    signal: options.signal,
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Heretic stream failed (${res.status}): ${detail}`);
  }

  await readSseEvents<unknown>(res, (message) => {
    const event = normalizeHereticStreamEvent(message.data, message.event);
    options.onEvent(event);
  });
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
  node_type: "category" | "index" | "session" | "assistant" | "memory" | "playbook";
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
  weight: number;
}

export interface BrainGraphResponse {
  nodes: BrainGraphNode[];
  edges: BrainGraphEdge[];
}

export interface BrainScaffoldPair {
  birth: number;
  death: number;
  dimension: number;
  node_ids: string[];
}

export interface BrainScaffoldEdge {
  source_id: string;
  target_id: string;
  persistence_weight: number;
  frequency_weight: number;
}

export interface BrainScaffoldResponse {
  betti_0: number;
  betti_1: number;
  h0_pairs: BrainScaffoldPair[];
  h1_pairs: BrainScaffoldPair[];
  scaffold_edges: BrainScaffoldEdge[];
  summary: string;
}

export async function fetchBrainGraph(): Promise<BrainGraphResponse> {
  const res = await apiFetch(`${await getApiBase()}/v1/brain/graph`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to fetch brain graph (${res.status}): ${detail}`);
  }
  return res.json();
}

export interface BrainGraphSnapshot extends BrainGraphResponse {
  hash: string;
}

/**
 * SSE stream of brain graph snapshots (Scion hydrate-then-stream pattern).
 *
 * Performs an initial REST fetch to hydrate the graph immediately, then opens
 * an SSE connection to `/v1/brain/graph/events` and calls `onSnapshot`
 * whenever the server emits a change.
 *
 * @example
 * const stop = await streamBrainGraphEvents({ onSnapshot: (s) => setGraph(s) });
 * // later:
 * stop();
 */
export async function streamBrainGraphEvents(options: {
  signal?: AbortSignal;
  pollSeconds?: number;
  onSnapshot: (snapshot: BrainGraphSnapshot) => void;
}): Promise<() => void> {
  const { signal, pollSeconds = 5, onSnapshot } = options;
  const base = await getApiBase();

  // 1. Hydrate immediately
  const initial = await fetchBrainGraph();
  onSnapshot({ ...initial, hash: "initial" });

  // 2. Open SSE for live deltas
  const params = new URLSearchParams({ poll_seconds: String(pollSeconds) });
  const url = `${base}/v1/brain/graph/events?${params}`;
  const controller = new AbortController();
  if (signal) {
    if (signal.aborted) {
      controller.abort();
    } else {
      signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }

  const res = await apiFetch(url, { signal: controller.signal });
  if (!res.ok || !res.body) {
    return () => controller.abort();
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  (async () => {
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const dataLine = part.split("\n").find((l) => l.startsWith("data: "));
          if (!dataLine) continue;
          try {
            const snapshot = JSON.parse(dataLine.slice(6)) as BrainGraphSnapshot;
            onSnapshot(snapshot);
          } catch {
            // skip malformed events
          }
        }
      }
    } catch {
      // connection closed or aborted — silently exit
    }
  })();

  return () => controller.abort();
}

// ── Trace playback ─────────────────────────────────────────────────────────

export interface TracePlaybackEvent {
  type: string;
  timestamp: string;
  data: Record<string, unknown>;
}

export interface TracePlaybackManifest {
  type: "manifest";
  run_id: string;
  time_range: { start: string; end: string };
  event_count: number;
  events: TracePlaybackEvent[];
}

export async function fetchTracePlayback(runId: string): Promise<TracePlaybackManifest> {
  const res = await apiFetch(`${await getApiBase()}/v1/traces/${encodeURIComponent(runId)}/playback`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to fetch trace playback for ${runId} (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function fetchBrainScaffold(): Promise<BrainScaffoldResponse> {
  const res = await apiFetch(`${await getApiBase()}/v1/brain/scaffold`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to fetch brain scaffold (${res.status}): ${detail}`);
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
  emitCompanionActivity({
    source: "reflection",
    state: "running",
    trigger: payload.trigger ?? "manual",
    summary: "METIS is reflecting…",
    timestamp: Date.now(),
  });
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
    emitCompanionActivity({
      source: "reflection",
      state: "error",
      trigger: payload.trigger ?? "manual",
      summary: "Reflection failed",
      timestamp: Date.now(),
    });
    throw new Error(`Failed to reflect assistant (${res.status}): ${detail}`);
  }
  const result = await res.json();
  emitCompanionActivity({
    source: "reflection",
    state: "completed",
    trigger: payload.trigger ?? "manual",
    summary: "Reflection complete",
    timestamp: Date.now(),
  });
  return result;
}

export async function triggerAutonomousResearchStream({
  signal,
  onEvent,
}: {
  signal?: AbortSignal;
  onEvent?: (event: AutoResearchStreamEvent) => void;
}): Promise<void> {
  const base = await getApiBase();
  const res = await apiFetch(`${base}/v1/autonomous/research/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`Autonomous research stream failed (${res.status})`);
  }
  emitCompanionActivity({
    source: "autonomous_research",
    state: "running",
    trigger: "manual",
    summary: "Autonomous research started…",
    timestamp: Date.now(),
  });
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        try {
          const event: AutoResearchStreamEvent = JSON.parse(line.slice(5).trim());
          onEvent?.(event);
          // Map backend phase events to companion activity events
          const phaseLabels: Record<string, string> = {
            scanning: "Scanning constellation for gaps…",
            formulating: event.detail ?? "Formulating research query…",
            searching: event.detail ?? "Searching the web…",
            synthesizing: event.detail ?? "Synthesising sources…",
            indexing: event.detail ?? "Building new star index…",
            complete: event.detail ?? "New star added to constellation",
            skipped: "Constellation fully covered — nothing to research",
          };
          if (event.type in phaseLabels) {
            emitCompanionActivity({
              source: "autonomous_research",
              state: "running",
              trigger: "manual",
              summary: phaseLabels[event.type],
              timestamp: Date.now(),
              payload: { phase: event.type, faculty_id: event.faculty_id },
            });
          } else if (event.type === "research_complete") {
            emitCompanionActivity({
              source: "autonomous_research",
              state: "completed",
              trigger: "manual",
              summary: "Autonomous research complete",
              timestamp: Date.now(),
              payload: { result: event.result },
            });
          } else if (event.type === "research_error") {
            emitCompanionActivity({
              source: "autonomous_research",
              state: "error",
              trigger: "manual",
              summary: event.message ?? "Research failed",
              timestamp: Date.now(),
            });
          }
        } catch {
          // Ignore malformed SSE frames
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
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

// ─── Autonomous Research ────────────────────────────────────────────────────

export interface AutonomousStatus {
  enabled: boolean;
  provider: string;
  web_search_api_key_set: boolean;
}

export async function fetchAutonomousStatus(): Promise<AutonomousStatus> {
  const base = await getApiBase();
  const res = await fetch(`${base}/v1/autonomous/status`);
  if (!res.ok) throw new Error(`autonomous status: ${res.status}`);
  return res.json() as Promise<AutonomousStatus>;
}

export async function triggerAutonomousResearch(): Promise<{ ok: boolean; result?: unknown }> {
  const base = await getApiBase();
  const res = await fetch(`${base}/v1/autonomous/trigger`, { method: "POST" });
  if (!res.ok) throw new Error(`autonomous trigger: ${res.status}`);
  return res.json() as Promise<{ ok: boolean; result?: unknown }>;
}

// ─── Agent-Native Bridge ────────────────────────────────────────────────────

export interface ActionPayload {
  action_type: string;
  payload: Record<string, unknown>;
  session_id?: string;
}

export interface AppStateEntry {
  session_id: string;
  key: string;
  value: string;
  version: number;
  updated_at: string;
}

export async function getAppState(
  sessionId: string,
  key?: string,
): Promise<AppStateEntry | AppStateEntry[]> {
  const url = key
    ? `${await getApiBase()}/v1/app-state/${encodeURIComponent(sessionId)}/${encodeURIComponent(key)}`
    : `${await getApiBase()}/v1/app-state/${encodeURIComponent(sessionId)}`;
  const res = await apiFetch(url);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to get app state (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function setAppState(
  sessionId: string,
  key: string,
  value: string,
): Promise<{ version: number }> {
  const res = await apiFetch(
    `${await getApiBase()}/v1/app-state/${encodeURIComponent(sessionId)}/${encodeURIComponent(key)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    },
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to set app state (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function deleteAppState(
  sessionId: string,
  key: string,
): Promise<{ ok: boolean }> {
  const res = await apiFetch(
    `${await getApiBase()}/v1/app-state/${encodeURIComponent(sessionId)}/${encodeURIComponent(key)}`,
    { method: "DELETE" },
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to delete app state (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function pollSync(since: number): Promise<{ version: number; changed: boolean }> {
  const res = await apiFetch(
    `${await getApiBase()}/v1/poll?since=${encodeURIComponent(String(since))}`,
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to poll sync (${res.status}): ${detail}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Comet News API
// ---------------------------------------------------------------------------

import type { CometEvent, CometSourcesResponse } from "@/lib/comet-types";

export async function fetchCometSources(): Promise<CometSourcesResponse> {
  const res = await apiFetch(`${await getApiBase()}/v1/comets/sources`);
  if (!res.ok) return { enabled: false, sources: [], available_sources: [], rss_feeds: [], reddit_subs: [], poll_interval_seconds: 300, max_active: 5 };
  return res.json();
}

export async function fetchActiveComets(): Promise<CometEvent[]> {
  const res = await apiFetch(`${await getApiBase()}/v1/comets/active`);
  if (!res.ok) return [];
  return res.json();
}

export async function pollComets(): Promise<{ comets: CometEvent[]; total_active: number }> {
  const res = await apiFetch(`${await getApiBase()}/v1/comets/poll`, { method: "POST" });
  if (!res.ok) return { comets: [], total_active: 0 };
  return res.json();
}

export async function absorbComet(cometId: string): Promise<{ ok: boolean }> {
  const res = await apiFetch(`${await getApiBase()}/v1/comets/${encodeURIComponent(cometId)}/absorb`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(`Failed to absorb comet ${cometId}`);
  return res.json();
}

export async function dismissComet(cometId: string): Promise<{ ok: boolean }> {
  const res = await apiFetch(`${await getApiBase()}/v1/comets/${encodeURIComponent(cometId)}/dismiss`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(`Failed to dismiss comet ${cometId}`);
  return res.json();
}

/**
 * SSE stream of comet lifecycle events (hydrate-then-stream pattern).
 */
export async function streamCometEvents(options: {
  signal?: AbortSignal;
  pollSeconds?: number;
  onUpdate: (comets: CometEvent[]) => void;
}): Promise<() => void> {
  const { signal, pollSeconds = 10, onUpdate } = options;
  const base = await getApiBase();

  // 1. Hydrate immediately
  const initial = await fetchActiveComets();
  onUpdate(initial);

  // 2. Open SSE for live updates
  const params = new URLSearchParams({ poll_seconds: String(pollSeconds) });
  const url = `${base}/v1/comets/events?${params}`;
  const controller = new AbortController();
  if (signal) {
    if (signal.aborted) {
      controller.abort();
    } else {
      signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }

  const res = await apiFetch(url, { signal: controller.signal });
  if (!res.ok || !res.body) {
    return () => controller.abort();
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  (async () => {
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const dataLine = part.split("\n").find((l) => l.startsWith("data: "));
          if (!dataLine) continue;
          try {
            const payload = JSON.parse(dataLine.slice(6)) as { comets: CometEvent[] };
            onUpdate(payload.comets ?? []);
          } catch {
            // skip malformed events
          }
        }
      }
    } catch {
      // connection closed or aborted
    }
  })();

  return () => controller.abort();
}
