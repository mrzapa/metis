export interface EvidenceSource {
  sid: string;
  source: string;
  snippet: string;
  title: string;
  score: number | null;
  breadcrumb: string;
  section_hint: string;
}

export interface ActionRequiredAction {
  kind: string;
  summary: string;
  payload: Record<string, unknown>;
}

export interface ChatMessageContent {
  role: string;
  content: string;
  ts: string;
  run_id: string;
  sources: EvidenceSource[];
  llm_provider?: string;
  llm_model?: string;
  query_mode?: string;
}

export type ChatMessageStatus = "streaming" | "complete" | "aborted" | "error";

export type ChatActionStatus = "pending" | "submitting" | "approved" | "denied";

export interface ChatMessage extends ChatMessageContent {
  id: string;
  status: ChatMessageStatus;
  actionRequired?: {
    action: ActionRequiredAction;
    status: ChatActionStatus;
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
}
