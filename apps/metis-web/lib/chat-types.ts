export interface EvidenceSource {
  sid: string;
  source: string;
  snippet: string;
  title: string;
  score: number | null;
  breadcrumb: string;
  section_hint: string;
  chunk_id?: string;
  chunk_idx?: number | null;
  label?: string;
  locator?: string;
  anchor?: string;
  header_path?: string;
  excerpt?: string;
  file_path?: string;
  date?: string;
  timestamp?: string;
  speaker?: string;
  actor?: string;
  entry_type?: string;
  type?: string;
  metadata?: Record<string, unknown>;
}

export interface GenericActionRequiredAction {
  kind: string;
  summary: string;
  payload: Record<string, unknown>;
}

export interface NyxInstallProposalComponent {
  component_name: string;
  title: string;
  description?: string;
  curated_description?: string;
  component_type?: string;
  install_target?: string;
  registry_url?: string;
  source_repo?: string;
  required_dependencies?: string[];
  dependencies?: string[];
  dev_dependencies?: string[];
  registry_dependencies?: string[];
  file_count?: number;
  targets?: string[];
  review_status?: string;
  previewable?: boolean;
  installable?: boolean;
  install_path_policy?: string;
  install_path_safe?: boolean;
  install_path_issues?: string[];
  audit_issues?: string[];
}

export interface NyxInstallProposal {
  schema_version: string;
  proposal_token: string;
  source?: string;
  run_id?: string;
  query?: string;
  intent_type?: string;
  matched_signals?: string[];
  component_names: string[];
  component_count: number;
  components: NyxInstallProposalComponent[];
}

export interface NyxInstallActionPayload {
  action_id: string;
  action_type: "nyx_install";
  proposal_token: string;
  component_count: number;
  component_names: string[];
}

export interface NyxInstallAction {
  action_id: string;
  action_type: "nyx_install";
  label: string;
  summary: string;
  requires_approval: boolean;
  run_action_endpoint: string;
  payload: NyxInstallActionPayload;
  proposal: NyxInstallProposal;
}

export interface NyxInstallActionInstaller {
  command: string[];
  cwd: string;
  package_script: string;
  returncode: number;
  stdout_excerpt?: string;
  stderr_excerpt?: string;
}

export interface NyxInstallActionResult {
  run_id: string;
  approved: boolean;
  status: string;
  action_id: string;
  action_type: "nyx_install";
  proposal_token: string;
  component_names: string[];
  component_count: number;
  execution_status: string;
  proposal?: NyxInstallProposal | null;
  installer?: NyxInstallActionInstaller | null;
  failure_code?: string;
}

export type ActionRequiredAction =
  | GenericActionRequiredAction
  | NyxInstallAction;

export interface ArrowArtifact {
  id?: string;
  type: string;
  summary?: string;
  path?: string;
  mime_type?: string;
  payload?: unknown;
  payload_bytes?: number;
  payload_truncated?: boolean;
}

export interface ChatMessageContent {
  role: string;
  content: string;
  ts: string;
  run_id: string;
  sources: EvidenceSource[];
  artifacts?: ArrowArtifact[];
  actions?: NyxInstallAction[];
  action_result?: NyxInstallActionResult | null;
  llm_provider?: string;
  llm_model?: string;
  query_mode?: string;
}

export type ChatMessageStatus = "streaming" | "complete" | "aborted" | "error";

export type ChatActionStatus =
  | "pending"
  | "submitting"
  | "approved"
  | "denied"
  | "failed";

export interface ChatMessage extends ChatMessageContent {
  id: string;
  status: ChatMessageStatus;
  actionRequired?: {
    action: ActionRequiredAction;
    status: ChatActionStatus;
    result?: NyxInstallActionResult | null;
  };
}

export type ChatRunStatus =
  | "streaming"
  | "complete"
  | "aborted"
  | "error"
  | "action_required";

export interface ChatRun {
  run_id: string;
  assistant_message_id: string;
  action_message_id?: string;
  status: ChatRunStatus;
  sources: EvidenceSource[];
  pending_sources: EvidenceSource[];
  sub_queries?: string[];
}

export function isNyxInstallAction(
  action: ActionRequiredAction,
): action is NyxInstallAction {
  return (
    "action_type" in action &&
    action.action_type === "nyx_install"
  );
}

export function isNyxInstallActionResult(
  value: unknown,
): value is NyxInstallActionResult {
  return (
    value !== null &&
    typeof value === "object" &&
    "action_type" in value &&
    (value as { action_type?: unknown }).action_type === "nyx_install"
  );
}

export function getChatActionStatusFromResult(
  result?: NyxInstallActionResult | null,
): Exclude<ChatActionStatus, "submitting"> {
  if (!result) {
    return "pending";
  }
  if (
    result.execution_status === "failed" ||
    result.status === "error"
  ) {
    return "failed";
  }
  if (
    result.approved === false ||
    result.execution_status === "declined" ||
    result.status === "declined"
  ) {
    return "denied";
  }
  if (
    result.execution_status === "completed" ||
    result.status === "completed" ||
    result.status === "success"
  ) {
    return "approved";
  }
  return result.approved ? "approved" : "pending";
}
