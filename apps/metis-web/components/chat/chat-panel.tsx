"use client";

import Link from "next/link";
import { useRef, useEffect, useLayoutEffect, useState, type KeyboardEvent, type RefObject } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { SessionSummary, TraceEvent } from "@/lib/api";
import type { ChatMessage } from "@/lib/chat-types";
import { ActionCard } from "@/components/chat/action-card";
import { AssistantCopyActions } from "@/components/chat/assistant-copy-actions";
import { ArrowArtifactBoundary } from "@/components/chat/artifacts/arrow-artifact-boundary";
import { AnimatedLucideIcon } from "@/components/ui/animated-lucide-icon";
import { useArrowState } from "@/hooks/use-arrow-state";
import { AlertCircle, Bot, Loader2, SendHorizontal, Square } from "lucide-react";
import { AgenticStepIndicator } from "@/components/chat/agentic-step-indicator";
import { IndexPickerDialog } from "@/components/chat/index-picker-dialog";
import { ModelStatusDialog } from "@/components/chat/model-status-dialog";
import { IndexBuildStudio } from "@/components/library/index-build-studio";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

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
  artifactsEnabled?: boolean;
  artifactRuntimeEnabled?: boolean;
}

const RAG_MODES = ["Q&A", "Summary", "Tutor", "Research", "Evidence Pack", "Knowledge Search"] as const;
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
  artifactsEnabled,
  artifactRuntimeEnabled,
}: ChatPanelProps) {
  const [draft, setDraft] = useArrowState(initialDraft ?? "");
  const [queryMode, setQueryMode] = useArrowState<"direct" | "rag">(initialQueryMode ?? "direct");
  const [pickerOpen, setPickerOpen] = useArrowState(false);
  const [modelDialogOpen, setModelDialogOpen] = useArrowState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const isKnowledgeSearchMode = queryMode === "rag" && selectedMode === "Knowledge Search";

  // Windowed infinite scroll state
  const [displayFromIndex, setDisplayFromIndex] = useState(() => Math.max(0, messages.length - 50));
  const [isLoadingOlder, setIsLoadingOlder] = useState(false);
  const topSentinelRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLElement | null>(null);
  const isAtBottomRef = useRef(true);
  const displayFromIndexRef = useRef(displayFromIndex);
  displayFromIndexRef.current = displayFromIndex;
  const prevScrollHeightRef = useRef<number | null>(null);
  const displayedMessages = messages.slice(displayFromIndex);

  // Reset window on new session (session_id change only)
  useEffect(() => {
    isAtBottomRef.current = true;
    setDisplayFromIndex(Math.max(0, messages.length - 50));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionMeta?.session_id]);

  // Auto-scroll to bottom when new messages arrive (only when already at bottom)
  // Use 'instant' to bypass CSS scroll-behavior: smooth on the viewport, which
  // would otherwise animate the jump and look jittery during rapid streaming.
  useEffect(() => {
    if (!isAtBottomRef.current) return;
    const vp = viewportRef.current;
    if (vp) vp.scrollTo({ top: vp.scrollHeight, behavior: "instant" });
  }, [messages]);

  // Set up viewport ref, scroll tracker, and top-sentinel IntersectionObserver (once on mount)
  useEffect(() => {
    const scrollEl = scrollRef.current;
    if (!scrollEl) return;
    const vp = scrollEl.querySelector('[data-slot="scroll-area-viewport"]') as HTMLElement | null;
    if (!vp) return;
    viewportRef.current = vp;

    function onScroll() {
      const distFromBottom = vp!.scrollHeight - vp!.scrollTop - vp!.clientHeight;
      isAtBottomRef.current = distFromBottom < 60;
    }
    vp.addEventListener("scroll", onScroll, { passive: true });

    const sentinel = topSentinelRef.current;
    let sentinelObserver: IntersectionObserver | null = null;
    if (sentinel) {
      sentinelObserver = new IntersectionObserver(
        (entries) => {
          if (entries[0].isIntersecting && displayFromIndexRef.current > 0) {
            prevScrollHeightRef.current = vp.scrollHeight;
            setIsLoadingOlder(true);
            setDisplayFromIndex((prev) => Math.max(0, prev - 25));
          }
        },
        { root: vp, rootMargin: "100px 0px 0px 0px", threshold: 0 },
      );
      sentinelObserver.observe(sentinel);
    }

    return () => {
      vp.removeEventListener("scroll", onScroll);
      sentinelObserver?.disconnect();
    };
  }, []);

  // Restore scroll position after older messages are injected (prevents jump).
  // Must use 'instant' so the correction happens synchronously before paint;
  // CSS scroll-behavior: smooth would animate this and produce a visible scroll.
  useLayoutEffect(() => {
    const saved = prevScrollHeightRef.current;
    if (saved === null) return;
    prevScrollHeightRef.current = null;
    const vp = viewportRef.current;
    if (vp) vp.scrollTo({ top: vp.scrollTop + (vp.scrollHeight - saved), behavior: "instant" });
    setIsLoadingOlder(false);
  }, [displayFromIndex]);

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
    <div className="chat-pane-surface flex h-full min-h-0 flex-col overflow-hidden rounded-[1.9rem]">
      {/* Header */}
      <div className="glass-strip flex min-h-13 shrink-0 flex-wrap items-center gap-2.5 border-b border-white/10 px-4 py-3.5">
        <h2 className="truncate text-sm font-semibold">
          {sessionMeta?.title ?? "New Chat"}
        </h2>
        {sessionMeta && (
          <div className="flex shrink-0 flex-wrap items-center gap-1 text-[10px] text-muted-foreground">
            {sessionMeta.mode && (
              <span className="chat-control-pill rounded-full px-2 py-0.5">
                {sessionMeta.mode}
              </span>
            )}
            {sessionMeta.llm_provider && (
              <span className="chat-control-pill rounded-full px-2 py-0.5">
                {sessionMeta.llm_provider}
              </span>
            )}
            {sessionMeta.updated_at && (
              <span className="chat-control-pill rounded-full px-2 py-0.5">
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
            aria-pressed={agenticMode}
            className={cn(
              "chat-control-pill flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-medium transition-colors",
              agenticMode
                ? "border-sky-400/25 bg-sky-500/14 text-sky-100 hover:bg-sky-500/18"
                : "text-muted-foreground hover:bg-white/10",
            )}
          >
            <AnimatedLucideIcon icon={Bot} mode="hoverLift" className="size-3" />
            Agentic {agenticMode ? "on" : "off"}
          </button>
          <Link
            href="/settings"
            className="chat-control-pill rounded-full px-2 py-1 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-white/10 hover:text-foreground"
          >
            Settings
          </Link>
          <Link
            href="/settings?tab=models&modelsTab=heretic"
            className="chat-control-pill rounded-full px-2 py-1 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-white/10 hover:text-foreground"
          >
            Heretic
          </Link>
          {/* Model status badge */}
          {(modelProvider || modelName) && (
            <>
              <span className="chat-control-pill rounded-full px-2 py-1 text-[10px] text-muted-foreground">
                {[modelProvider, modelName].filter(Boolean).join(" / ")}
              </span>
              <button
                type="button"
                onClick={() => setModelDialogOpen(true)}
                className="chat-control-pill rounded-full px-2 py-1 text-[10px] font-medium text-primary transition-colors hover:bg-primary/12"
              >
                Change
              </button>
            </>
          )}
        </div>
      </div>

      {agenticModeError && (
        <div className="glass-strip flex items-center gap-1.5 border-b border-destructive/25 bg-destructive/12 px-4 py-1.5 text-[11px] text-destructive">
          <AnimatedLucideIcon icon={AlertCircle} mode="idlePulse" className="size-3 shrink-0" />
          {agenticModeError}
        </div>
      )}

      {reconnectState && (
        <div className="glass-strip border-b border-chart-4/35 bg-chart-4/12 px-4 py-3">
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
        <div className="glass-strip flex shrink-0 items-center justify-between border-b border-white/10 px-4 py-2 text-xs">
          {activeIndexPath ? (
            <>
              <span className="text-muted-foreground">
                Index:{" "}
                <span className="font-medium text-foreground">
                  {activeIndexLabel}
                </span>
              </span>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setBuildStudioOpen(true)}
                  className="text-muted-foreground hover:text-foreground"
                >
                  + New
                </button>
                <button
                  type="button"
                  onClick={() => setPickerOpen(true)}
                  className="text-primary hover:underline"
                >
                  Change
                </button>
              </div>
            </>
          ) : (
            <>
              <span className="text-muted-foreground">No index selected</span>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setBuildStudioOpen(true)}
                  className="text-muted-foreground hover:text-foreground"
                >
                  + New
                </button>
                <button
                  type="button"
                  onClick={() => setPickerOpen(true)}
                  className="font-medium text-primary hover:underline"
                >
                  Select an index →
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* Transcript */}
      <ScrollArea className="flex-1 min-h-0" ref={scrollRef as React.Ref<HTMLDivElement>}>
        <div className="mx-auto max-w-4xl space-y-4 p-4 sm:p-5 lg:p-6">
          {/* Top sentinel – fires when user scrolls near the top to reveal older messages */}
          <div ref={topSentinelRef} className="h-0" aria-hidden="true" />
          {isLoadingOlder && displayFromIndex > 0 && (
            <div className="flex items-center justify-center gap-1.5 py-2 text-[11px] text-muted-foreground">
              <Loader2 className="size-3 animate-spin" />
              Loading older messages…
            </div>
          )}
          {loading && (
            <div className="flex flex-col items-center justify-center py-20 text-center text-muted-foreground">
              <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-6" />
              <p className="mt-2 text-sm">Loading session…</p>
            </div>
          )}

          {!loading && error && (
            <div className="flex flex-col items-center justify-center gap-2 py-20 text-center">
              <AnimatedLucideIcon icon={AlertCircle} mode="idlePulse" className="size-6 text-destructive" />
              <p className="text-sm font-medium text-destructive">
                Failed to load session
              </p>
              <p className="text-xs text-muted-foreground">{error}</p>
            </div>
          )}

          {!loading && !error && messages.length === 0 && (
            <div className="chat-empty-state glass-panel mx-auto flex max-w-3xl flex-col items-center justify-center rounded-[1.8rem] px-8 py-16 text-center text-muted-foreground">
              <p className="font-display text-3xl font-semibold tracking-[-0.04em] text-foreground">
                Start with a question that feels specific.
              </p>
              <p className="mt-3 max-w-xl text-sm leading-7">
                {queryMode === "rag"
                  ? activeIndexPath
                    ? isKnowledgeSearchMode
                      ? "Search the indexed material first and inspect the strongest evidence without running a full synthesis pass."
                      : "Ask about the material you indexed, compare documents, or request a high-confidence overview grounded in sources."
                    : "Choose an index to unlock grounded RAG answers and evidence-backed synthesis."
                  : "Use direct mode for fast ideation, planning, or questions that do not need document grounding yet."}
              </p>
            </div>
          )}

          {!loading && !error && displayedMessages.map((msg) => (
            <div
              key={msg.id}
              className={cn(
                "flex",
                msg.role === "user" ? "justify-end" : "justify-start"
              )}
            >
              {msg.actionRequired ? (
                <div className="max-w-[82%]">
                  <ActionCard
                    runId={msg.run_id}
                    action={msg.actionRequired.action}
                    status={msg.actionRequired.status}
                    result={msg.actionRequired.result}
                    onApprove={() => onActionApprove?.(msg.id)}
                    onDeny={() => onActionDeny?.(msg.id)}
                  />
                </div>
              ) : (
                <div
                  className={cn(
                    "chat-message-surface max-w-[84%] rounded-[1.35rem] border px-4 py-3 text-sm leading-[1.72] shadow-lg shadow-black/10",
                    msg.role === "user"
                      ? "chat-message-surface--user border-primary/30 bg-primary/92 text-primary-foreground shadow-primary/20"
                      : "chat-message-surface--assistant glass-micro-surface border-white/10 bg-white/7 text-foreground/96"
                  )}
                >
                  {msg.role === "assistant" ? (
                    <div className="flex items-start">
                      <div className="min-w-0 flex-1">
                        {msg.run_id && (() => {
                          const sq = getRunSubqueries?.(msg.run_id);
                          return sq && sq.length > 0 ? (
                            <div className="mb-2.5 flex flex-wrap gap-1.5">
                              {sq.map((q) => (
                                <span
                                  key={q}
                                  className="chat-control-pill rounded-full px-2 py-0.5 text-[10px] text-muted-foreground"
                                >
                                  {q}
                                </span>
                              ))}
                            </div>
                          ) : null;
                        })()}
                        <ArrowArtifactBoundary
                          content={msg.content || (msg.status === "aborted" ? "Stopped." : "")}
                          artifacts={msg.artifacts}
                          isStreaming={msg.status === "streaming"}
                          artifactsEnabled={artifactsEnabled}
                          artifactRuntimeEnabled={artifactRuntimeEnabled}
                          sessionId={sessionMeta?.session_id}
                          runId={msg.run_id}
                          messageId={msg.id}
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
                        className={cn(
                            "flex animate-msg-enter justify-start"
                        )}
                          isStreaming={true}
                        />
                      ) : (
                        <div className="mt-1.5 flex animate-msg-enter items-center gap-1 text-[10px] text-muted-foreground">
                          <span className="size-1.5 animate-pulse rounded-full bg-current/70" />
                          Streaming
                        </div>
                      )
                  )}
                  {msg.role === "assistant" && msg.status === "error" && (
                    <div className="mt-2 text-[10px] text-destructive">
                      Response interrupted
                    </div>
                  )}
                  {msg.sources.length > 0 && (
                    <p className="mt-2 text-xs opacity-70">
                      {msg.sources.length} source{msg.sources.length > 1 ? "s" : ""}
                    </p>
                  )}
                  {msg.role === "assistant" && (msg.llm_provider || msg.llm_model) && (
                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                      {msg.llm_provider && (
                        <span className="chat-control-pill rounded-full px-2 py-0.5 text-[10px] text-muted-foreground">
                          {msg.llm_provider}
                        </span>
                      )}
                      {msg.llm_model && (
                        <span className="chat-control-pill rounded-full px-2 py-0.5 text-[10px] text-muted-foreground">
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
              <div className="glass-micro-surface rounded-[1.1rem] px-3 py-2 text-sm text-muted-foreground">
                <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-3.5" />
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Composer */}
      <div className="glass-strip border-t border-white/10 px-3 py-3.5">
        <div className="mx-auto max-w-4xl space-y-2.5">
          {/* Path + RAG mode selector */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground">Path:</span>
            <button
              type="button"
              onClick={() => setQueryMode("direct")}
              data-active={queryMode === "direct" ? "true" : "false"}
              className={cn(
                "chat-control-pill rounded-full px-3 py-1 text-[11px] font-medium transition-colors",
                queryMode === "direct"
                  ? "border-primary/30 bg-primary/90 text-primary-foreground"
                  : "text-muted-foreground hover:bg-white/10"
              )}
            >
              Direct
            </button>
            <button
              type="button"
              onClick={() => setQueryMode("rag")}
              data-active={queryMode === "rag" ? "true" : "false"}
              className={cn(
                "chat-control-pill rounded-full px-3 py-1 text-[11px] font-medium transition-colors",
                queryMode === "rag"
                  ? "border-primary/30 bg-primary/90 text-primary-foreground"
                  : "text-muted-foreground hover:bg-white/10"
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
                  className="chat-control-pill cursor-pointer rounded-full px-3 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-white/10 focus:outline-none focus:ring-1 focus:ring-primary/50"
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

          <div className="flex items-end gap-2.5">
            <Textarea
              ref={composerRef}
              placeholder={
                ragInputDisabled
                  ? "Select an index first…"
                  : queryMode === "rag"
                  ? isKnowledgeSearchMode
                    ? "Search your indexed knowledge…"
                    : "Ask about your documents…"
                  : "Ask anything…"
              }
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              className="glass-micro-surface min-h-11 max-h-40 resize-none border-white/10 bg-white/6 px-3 py-2.5 text-sm leading-6 transition-[border-color,box-shadow] duration-200 focus:border-primary/30 focus:shadow-sm"
              aria-label="Message input"
              disabled={ragInputDisabled}
            />
            {isStreamingRag ? (
              <Button
                variant="outline"
                className="chat-control-pill h-11 shrink-0 px-3"
                onClick={onStopStreaming}
                aria-label="Stop streaming response"
              >
                <Square className="size-3.5 fill-current" />
                Stop
              </Button>
            ) : (
              <Button
                size="icon"
                className="chat-send-button size-11 shrink-0 rounded-2xl text-primary-foreground disabled:opacity-50 disabled:scale-95"
                onClick={handleSend}
                disabled={!canSend}
                aria-label="Send message"
              >
                {isSending ? (
                  <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" />
                ) : (
                  <AnimatedLucideIcon icon={SendHorizontal} mode="hoverLift" className="size-4" />
                )}
              </Button>
            )}
          </div>
          {isKnowledgeSearchMode && (
            <p className="text-[11px] text-muted-foreground/70">
              Retrieval-first mode returns a concise search summary plus the strongest sources.
            </p>
          )}
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

      <Dialog open={buildStudioOpen} onOpenChange={setBuildStudioOpen}>
        <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Build a new index</DialogTitle>
          </DialogHeader>
          <IndexBuildStudio
            showExistingIndexes={false}
            onIndexBuilt={(result) => {
              onIndexChange?.(result.manifest_path, result.index_id);
              setBuildStudioOpen(false);
            }}
          />
        </DialogContent>
      </Dialog>

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
