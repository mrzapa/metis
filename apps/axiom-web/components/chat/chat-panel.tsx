"use client";

import { useState, useRef, useEffect, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { SessionMessage, SessionSummary } from "@/lib/api";
import { AlertCircle, Loader2, SendHorizontal } from "lucide-react";
import { IndexPickerDialog } from "@/components/chat/index-picker-dialog";
import { ModelStatusDialog } from "@/components/chat/model-status-dialog";

interface ChatPanelProps {
  messages: SessionMessage[];
  sessionMeta: SessionSummary | null;
  loading?: boolean;
  error?: string | null;
  onDirectSend?: (prompt: string) => Promise<void>;
  onRagSend?: (question: string) => Promise<void>;
  isSending?: boolean;
  activeIndexPath?: string | null;
  activeIndexLabel?: string | null;
  initialQueryMode?: "direct" | "rag";
  onIndexChange?: (manifestPath: string, label: string) => void;
  modelProvider?: string | null;
  modelName?: string | null;
  onModelChange?: (provider: string, model: string) => void;
}

export function ChatPanel({
  messages,
  sessionMeta,
  loading,
  error,
  onDirectSend,
  onRagSend,
  isSending,
  activeIndexPath,
  activeIndexLabel,
  initialQueryMode,
  onIndexChange,
  modelProvider,
  modelName,
  onModelChange,
}: ChatPanelProps) {
  const [draft, setDraft] = useState("");
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
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleSend() {
    if (!draft.trim() || isSending) return;
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
    ((queryMode === "direct" && !!onDirectSend) ||
      (queryMode === "rag" && !!activeIndexPath && !!onRagSend));

  const ragInputDisabled = queryMode === "rag" && !activeIndexPath;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex h-10 shrink-0 items-center gap-2 border-b px-4">
        <h2 className="truncate text-sm font-semibold">
          {sessionMeta?.title ?? "New Chat"}
        </h2>
        {sessionMeta && (
          <div className="flex shrink-0 items-center gap-1 text-[10px] text-muted-foreground">
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
        {/* Model status badge */}
        {(modelProvider || modelName) && (
          <div className="ml-auto flex shrink-0 items-center gap-1.5">
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
          </div>
        )}
      </div>

      {/* Index banner (RAG mode only) */}
      {queryMode === "rag" && (
        <div className="flex shrink-0 items-center justify-between border-b bg-muted/40 px-4 py-1.5 text-xs">
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
      <ScrollArea className="flex-1" ref={scrollRef as React.Ref<HTMLDivElement>}>
        <div className="mx-auto max-w-3xl space-y-4 p-4">
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
            <div className="flex flex-col items-center justify-center py-20 text-center text-muted-foreground">
              <p className="text-lg font-medium">Start a conversation</p>
              <p className="mt-1 text-sm">
                Ask a question about your documents.
              </p>
            </div>
          )}

          {!loading && !error && messages.map((msg, i) => (
            <div
              key={`${msg.run_id}-${i}`}
              className={cn(
                "flex",
                msg.role === "user" ? "justify-end" : "justify-start"
              )}
            >
              <div
                className={cn(
                  "max-w-[80%] rounded-lg px-3 py-2 text-sm leading-relaxed",
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted"
                )}
              >
                <p className="whitespace-pre-wrap">{msg.content}</p>
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
            </div>
          ))}

          {isSending && (
            <div className="flex justify-start">
              <div className="rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" />
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Composer */}
      <div className="border-t p-3">
        <div className="mx-auto max-w-3xl space-y-2">
          {/* Mode selector */}
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground">Path:</span>
            <button
              type="button"
              onClick={() => setQueryMode("direct")}
              className={cn(
                "rounded px-2 py-0.5 text-[11px] font-medium transition-colors",
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
                "rounded px-2 py-0.5 text-[11px] font-medium transition-colors",
                queryMode === "rag"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              )}
            >
              RAG
            </button>
          </div>

          <div className="flex items-end gap-2">
            <Textarea
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
            <Button
              size="icon"
              className="size-9 shrink-0"
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
          </div>
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
