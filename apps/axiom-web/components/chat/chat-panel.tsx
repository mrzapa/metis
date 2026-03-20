"use client";

import Link from "next/link";
import { useState, useRef, useEffect, type KeyboardEvent, type RefObject } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { SessionSummary, TraceEvent } from "@/lib/api";
import type { ChatMessage } from "@/lib/chat-types";
import { ActionCard } from "@/components/chat/action-card";
import { AssistantCopyActions } from "@/components/chat/assistant-copy-actions";
import { AssistantMarkdown } from "@/components/chat/assistant-markdown";
import { AlertCircle, Bot, Loader2, SendHorizontal, Square } from "lucide-react";
import { AgenticStepIndicator } from "@/components/chat/agentic-step-indicator";
import { IndexPickerDialog } from "@/components/chat/index-picker-dialog";
import { ModelStatusDialog } from "@/components/chat/model-status-dialog";

interface ChatPanelProps {
  messages: ChatMessage[];
  sessionMeta: SessionSummary | null;
  loading?: boolean;
  error?: string | null;
  onDirectSend?: (prompt: string) => Promise<void>;
  onRagSend?: (question: string) => Promise<void>;
  isSending?: boolean;
  isStreamingRag?: boolean;
  onStopStreaming?: () => void;
  activeIndexPath?: string | null;
  activeIndexLabel?: string | null;
  initialQueryMode?: "direct" | "rag";
  initialDraft?: string;
  onIndexChange?: (manifestPath: string, label: string) => void;
  modelProvider?: string | null;
  modelName?: string | null;
  onModelChange?: (provider: string, model: string) => void;
  composerRef?: RefObject<HTMLTextAreaElement | null>;
  selectedMode?: string;
  onModeChange?: (mode: string) => void;
  onActionApprove?: (messageId: string) => void;
  onActionDeny?: (messageId: string) => void;
  reconnectState?: {
    question: string;
    lastEventId: number;
  } | null;
  onReconnectRun?: () => void;
  onDiscardReconnect?: () => void;
  getRunSubqueries?: (runId: string) => string[] | undefined;
  agenticMode?: boolean;
  agenticModeSaving?: boolean;
  agenticModeError?: string | null;
  onAgenticModeChange?: (enabled: boolean) => void;
  liveTraceEvents?: TraceEvent[];
}

const RAG_MODES = ["Q&A", "Summary", "Tutor", "Research", "Evidence Pack"] as const;
const DEFAULT_RAG_MODE = "Q&A";

export function ChatPanel({
  messages,
  sessionMeta,
  loading,
  error,
  onDirectSend,
  onRagSend,
  isSending,
  isStreamingRag,
  onStopStreaming,
  activeIndexPath,
  activeIndexLabel,
  initialQueryMode,
  initialDraft,
  onIndexChange,
  modelProvider,
  modelName,
  onModelChange,
  composerRef,
  selectedMode,
  onModeChange,
  onActionApprove,
  onActionDeny,
  reconnectState,
  onReconnectRun,
  onDiscardReconnect,
  getRunSubqueries,
  agenticMode,
  agenticModeSaving,
  agenticModeError,
  onAgenticModeChange,
  liveTraceEvents,
}: ChatPanelProps) {
  const [draft, setDraft] = useState(initialDraft ?? "");
  const [queryMode, setQueryMode] = useState<"direct" | "rag">(initialQueryMode ?? "direct");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [modelDialogOpen, setModelDialogOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll when messages change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Don't intercept keys while IME composition is active (CJK input, etc.)
    if (e.nativeEvent.isComposing) return;

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
    if (e.key === "Escape") {
      setDraft("");
    }
  }

  function handleSend() {
    if (!draft.trim() || isSending || isStreamingRag) return;
    const text = draft.trim();
    setDraft("");
    if (queryMode === "direct" && onDirectSend) {
      onDirectSend(text);
    } else if (queryMode === "rag" && activeIndexPath && onRagSend) {
      onRagSend(text);
    }
  }

  const canSend =
    !!draft.trim() &&
    !isSending &&
    !isStreamingRag &&
    ((queryMode === "direct" && !!onDirectSend) ||
      (queryMode === "rag" && !!activeIndexPath && !!onRagSend));

  const ragInputDisabled = queryMode === "rag" && !activeIndexPath;

  return (
    <div className="glass-panel-strong flex h-full min-h-0 flex-col overflow-hidden rounded-[1.8rem]">
      {/* Header */}
      <div className="flex min-h-12 shrink-0 flex-wrap items-center gap-2 border-b border-white/8 px-4 py-3">
        <h2 className="truncate text-sm font-semibold">
          {sessionMeta?.title ?? "New Chat"}
        </h2>
        {sessionMeta && (
          <div className="flex shrink-0 flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
            {sessionMeta.mode && (
              <span className="rounded bg-muted px-1.5 py-0.5">
                {sessionMeta.mode}
              </span>
            )}
            {sessionMeta.llm_provider && (
              <span className="rounded bg-muted px-1.5 py-0.5">
                {sessionMeta.llm_provider}
              </span>
            )}
            {sessionMeta.updated_at && (
              <span className="rounded bg-muted px-1.5 py-0.5">
                {formatDate(sessionMeta.updated_at)}
              </span>
            )}
          </div>
        )}
        {/* Agentic mode toggle + settings link */}
        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            onClick={() => onAgenticModeChange?.(!agenticMode)}
            disabled={agenticModeSaving}
            className={cn(
              "flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors",
              agenticMode
                ? "bg-sky-100 text-sky-700 hover:bg-sky-200"
                : "bg-muted text-muted-foreground hover:bg-muted/80",
            )}
            aria-pressed={agenticMode}
          >
            <Bot className="size-3" />
            Agentic {agenticMode ? "on" : "off"}
          </button>
          <Link
            href="/settings"
            className="rounded px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground hover:text-foreground hover:underline"
          >
            Settings
          </Link>
          {/* Model status badge */}
          {(modelProvider || modelName) && (
            <>
              <span className="rounded bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
                {[modelProvider, modelName].filter(Boolean).join(" / ")}
              </span>
              <button
                type="button"
                onClick={() => setModelDialogOpen(true)}
                className="rounded px-1.5 py-0.5 text-[10px] font-medium text-primary hover:underline"
              >
                Change
              </button>
            </>
          )}
        </div>
      </div>

      {agenticModeError && (
        <div className="flex items-center gap-1.5 border-b border-white/8 bg-destructive/10 px-4 py-1.5 text-[11px] text-destructive">
          <AlertCircle className="size-3 shrink-0" />
          {agenticModeError}
        </div>
      )}

      {reconnectState && (
        <div className="border-b border-white/8 bg-chart-4/10 px-4 py-3">
          <div className="mx-auto flex max-w-3xl flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-chart-4">
                Interrupted RAG Run
              </p>
              <p className="mt-1 text-sm text-foreground">
                Reconnect to continue the response for &quot;{truncateMiddle(reconnectState.question, 120)}&quot;.
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Last acknowledged event: {Math.max(reconnectState.lastEventId, 0)}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Button size="sm" className="h-8 px-3" onClick={onReconnectRun}>
                Reconnect
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-8 px-3"
                onClick={onDiscardReconnect}
              >
                Discard
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Index banner (RAG mode only) */}
      {queryMode === "rag" && (
        <div className="flex shrink-0 items-center justify-between border-b border-white/8 bg-white/4 px-4 py-2 text-xs">
          {activeIndexPath ? (
            <>
              <span className="text-muted-foreground">
                Index:{" "}
                <span className="font-medium text-foreground">
                  {activeIndexLabel}
                </span>
              </span>
              <button
                type="button"
                onClick={() => setPickerOpen(true)}
                className="text-primary hover:underline"
              >
                Change
              </button>
            </>
          ) : (
            <>
              <span className="text-muted-foreground">No index selected</span>
              <button
                type="button"
                onClick={() => setPickerOpen(true)}
                className="font-medium text-primary hover:underline"
              >
                Select an index →
              </button>
            </>
          )}
        </div>
      )}

      {/* Transcript */}
      <ScrollArea className="flex-1 min-h-0" ref={scrollRef as React.Ref<HTMLDivElement>}>
        <div className="mx-auto max-w-4xl space-y-4 p-4 sm:p-5">
          {loading && (
            <div className="flex flex-col items-center justify-center py-20 text-center text-muted-foreground">
              <Loader2 className="size-6 animate-spin" />
              <p className="mt-2 text-sm">Loading session…</p>
            </div>
          )}

          {!loading && error && (
            <div className="flex flex-col items-center justify-center gap-2 py-20 text-center">
              <AlertCircle className="size-6 text-destructive" />
              <p className="text-sm font-medium text-destructive">
                Failed to load session
              </p>
              <p className="text-xs text-muted-foreground">{error}</p>
            </div>
          )}

          {!loading && !error && messages.length === 0 && (
            <div className="glass-panel mx-auto flex max-w-3xl flex-col items-center justify-center rounded-[1.8rem] px-8 py-16 text-center text-muted-foreground">
              <p className="font-display text-3xl font-semibold tracking-[-0.04em] text-foreground">
                Start with a question that feels specific.
              </p>
              <p className="mt-3 max-w-xl text-sm leading-7">
                {queryMode === "rag"
                  ? activeIndexPath
                    ? "Ask about the material you indexed, compare documents, or request a high-confidence overview grounded in sources."
                    : "Choose an index to unlock grounded RAG answers and evidence-backed synthesis."
                  : "Use direct mode for fast ideation, planning, or questions that do not need document grounding yet."}
              </p>
            </div>
          )}

          {!loading && !error && messages.map((msg) => (
            <div
              key={msg.id}
              className={cn(
                "flex",
                msg.role === "user" ? "justify-end" : "justify-start"
              )}
            >
              {msg.actionRequired ? (
                <div className="max-w-[80%]">
                  <ActionCard
                    runId={msg.run_id}
                    action={msg.actionRequired.action}
                    status={msg.actionRequired.status}
                    onApprove={() => onActionApprove?.(msg.id)}
                    onDeny={() => onActionDeny?.(msg.id)}
                  />
                </div>
              ) : (
                <div
                  className={cn(
                    "max-w-[82%] rounded-[1.25rem] border px-4 py-3 text-sm leading-relaxed shadow-lg shadow-black/10",
                    msg.role === "user"
                      ? "border-primary/25 bg-primary text-primary-foreground"
                      : "border-white/8 bg-white/6"
                  )}
                >
                  {msg.role === "assistant" ? (
                    <div className="flex items-start">
                      <div className="min-w-0 flex-1">
                        {msg.run_id && (() => {
                          const sq = getRunSubqueries?.(msg.run_id);
                          return sq && sq.length > 0 ? (
                            <div className="mb-2 flex flex-wrap gap-1">
                              {sq.map((q) => (
                                <span
                                  key={q}
                                  className="rounded-full bg-background/70 px-2 py-0.5 text-[10px] text-muted-foreground ring-1 ring-border"
                                >
                                  {q}
                                </span>
                              ))}
                            </div>
                          ) : null;
                        })()}
                        <AssistantMarkdown
                          content={msg.content || (msg.status === "aborted" ? "Stopped." : "")}
                        />
                      </div>
                      <AssistantCopyActions message={msg} sessionId={sessionMeta?.session_id} />
                    </div>
                  ) : (
                    <p className="whitespace-pre-wrap">
                      {msg.content || (msg.status === "aborted" ? "Stopped." : "")}
                    </p>
                  )}
                  {msg.role === "assistant" && msg.status === "streaming" && (
                    agenticMode ? (
                      <AgenticStepIndicator
                        liveTraceEvents={liveTraceEvents ?? []}
                        isStreaming={true}
                      />
                    ) : (
                      <div className="mt-1.5 flex items-center gap-1 text-[10px] text-muted-foreground">
                        <span className="size-1.5 animate-pulse rounded-full bg-current/70" />
                        Streaming
                      </div>
                    )
                  )}
                  {msg.role === "assistant" && msg.status === "error" && (
                    <div className="mt-1.5 text-[10px] text-destructive">
                      Response interrupted
                    </div>
                  )}
                  {msg.sources.length > 0 && (
                    <p className="mt-1 text-xs opacity-70">
                      {msg.sources.length} source{msg.sources.length > 1 ? "s" : ""}
                    </p>
                  )}
                  {msg.role === "assistant" && (msg.llm_provider || msg.llm_model) && (
                    <div className="mt-1.5 flex gap-1">
                      {msg.llm_provider && (
                        <span className="rounded bg-background/50 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                          {msg.llm_provider}
                        </span>
                      )}
                      {msg.llm_model && (
                        <span className="rounded bg-background/50 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                          {msg.llm_model}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {isSending && !isStreamingRag && (
            <div className="flex justify-start">
              <div className="rounded-[1.1rem] border border-white/8 bg-white/6 px-3 py-2 text-sm text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" />
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Composer */}
      <div className="border-t border-white/8 bg-black/10 p-3">
        <div className="mx-auto max-w-4xl space-y-2">
          {/* Path + RAG mode selector */}
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground">Path:</span>
            <button
              type="button"
              onClick={() => setQueryMode("direct")}
              className={cn(
                "rounded-full px-3 py-1 text-[11px] font-medium transition-colors",
                queryMode === "direct"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              )}
            >
              Direct
            </button>
            <button
              type="button"
              onClick={() => setQueryMode("rag")}
              className={cn(
                "rounded-full px-3 py-1 text-[11px] font-medium transition-colors",
                queryMode === "rag"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              )}
            >
              RAG
            </button>
            {queryMode === "rag" && (
              <>
                <span className="text-[11px] text-muted-foreground/50">·</span>
                <span className="text-[11px] text-muted-foreground">Mode:</span>
                <select
                  value={selectedMode ?? DEFAULT_RAG_MODE}
                  onChange={(e) => {
                    onModeChange?.(e.target.value);
                  }}
                  className="rounded-full bg-muted px-3 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted/80 focus:outline-none focus:ring-1 focus:ring-primary/50 cursor-pointer"
                  aria-label="RAG mode"
                >
                  {RAG_MODES.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </>
            )}
          </div>

          <div className="flex items-end gap-2">
            <Textarea
              ref={composerRef}
              placeholder={
                ragInputDisabled
                  ? "Select an index first…"
                  : queryMode === "rag"
                  ? "Ask about your documents…"
                  : "Ask anything…"
              }
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              className="min-h-[40px] max-h-[160px] resize-none text-sm"
              aria-label="Message input"
              disabled={ragInputDisabled}
            />
            {isStreamingRag ? (
              <Button
                variant="outline"
                className="h-10 shrink-0 px-3"
                onClick={onStopStreaming}
                aria-label="Stop streaming response"
              >
                <Square className="size-3.5 fill-current" />
                Stop
              </Button>
            ) : (
              <Button
                size="icon"
                className="size-10 shrink-0"
                onClick={handleSend}
                disabled={!canSend}
                aria-label="Send message"
              >
                {isSending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <SendHorizontal className="size-4" />
                )}
              </Button>
            )}
          </div>
          <p className="select-none text-[11px] text-muted-foreground/60">
            Enter to send · Shift+Enter for new line · Esc to clear · Ctrl/⌘+K to focus
          </p>
        </div>
      </div>

      <IndexPickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        onSelect={(path, label) => {
          onIndexChange?.(path, label);
        }}
      />

      <ModelStatusDialog
        open={modelDialogOpen}
        onOpenChange={setModelDialogOpen}
        provider={modelProvider ?? ""}
        model={modelName ?? ""}
        onSaved={(provider, model) => {
          onModelChange?.(provider, model);
        }}
      />
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function truncateMiddle(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  const edgeLength = Math.max(Math.floor((maxLength - 1) / 2), 1);
  return `${value.slice(0, edgeLength)}…${value.slice(-edgeLength)}`;
}
