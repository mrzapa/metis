"use client";

import { useState, useRef, useEffect, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { SessionMessage, SessionSummary } from "@/lib/api";
import { AlertCircle, Loader2, SendHorizontal } from "lucide-react";

interface ChatPanelProps {
  messages: SessionMessage[];
  sessionMeta: SessionSummary | null;
  loading?: boolean;
  error?: string | null;
}

export function ChatPanel({ messages, sessionMeta, loading, error }: ChatPanelProps) {
  const [draft, setDraft] = useState("");
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
    if (!draft.trim()) return;
    // Sending not wired yet — placeholder for future implementation
    setDraft("");
  }

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
      </div>

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
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>

      {/* Composer */}
      <div className="border-t p-3">
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <Textarea
            placeholder="Ask a question…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            className="min-h-[40px] max-h-[160px] resize-none text-sm"
            aria-label="Message input"
          />
          <Button
            size="icon"
            className="size-9 shrink-0"
            onClick={handleSend}
            disabled={!draft.trim()}
            aria-label="Send message"
          >
            <SendHorizontal className="size-4" />
          </Button>
        </div>
      </div>
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
