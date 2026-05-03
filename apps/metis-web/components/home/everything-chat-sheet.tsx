"use client";

/**
 * EverythingChatSheet — M24 Phase 5 "Chat with everything" entry point.
 *
 * Slide-over sheet hosted on the home page; opens when the user clicks
 * the central METIS star. Sends RAG queries against the virtual
 * "_all_stars" index — the backend treats that sentinel as "union of
 * every attached index across every user star" and merges/re-ranks the
 * retrieved passages before synthesising the answer.
 *
 * Implementation choice (Option B per the M24 plan): rather than
 * hosting the full ChatPanel (40+ controlled props, sessionMeta,
 * SSE streaming, RAG-mode toolbar, forecast controls, build-studio
 * dialog…) we render a thin standalone composer + transcript that
 * issues plain non-streaming `queryRag(manifest_path="_all_stars", ...)`
 * calls. The full ChatPanel was too heavy to embed without rewiring
 * the home page as a session host; deferring that to a future
 * milestone keeps Phase 5 surgical.
 *
 * The sheet is built on top of the existing Dialog primitive (no
 * dedicated `@/components/ui/sheet` exists yet) plus Tailwind classes
 * that anchor the popup to the right edge of the viewport.
 */

import { useEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { queryRag, fetchSettings } from "@/lib/api";

/** Sentinel manifest path that the backend interprets as
 *  "RAG over the union of every attached index". Kept in sync with
 *  ``ALL_STARS_MARKER`` in ``metis_app/services/workspace_orchestrator.py``. */
export const ALL_STARS_MARKER = "_all_stars";

interface Message {
  id: string;
  role: "user" | "assistant" | "error";
  text: string;
  sourceCount?: number;
  /** Number of attached indexes that errored during retrieval, surfaced
   *  from `result.retrieval_plan.stages[0].payload.errors`. Rendered as
   *  a small amber notice under the answer so users know a partial
   *  result is being shown rather than silently swallowing failures. */
  errorCount?: number;
}

/** Defensive narrowing of `result.retrieval_plan` — the type is
 *  `Record<string, unknown>` on the stage payload, so we can't trust
 *  the shape statically. Returns 0 when the field is missing or the
 *  shape doesn't match. */
function countRetrievalErrors(retrievalPlan: unknown): number {
  if (!retrievalPlan || typeof retrievalPlan !== "object") return 0;
  const stages = (retrievalPlan as { stages?: unknown }).stages;
  if (!Array.isArray(stages) || stages.length === 0) return 0;
  const firstStage = stages[0];
  if (!firstStage || typeof firstStage !== "object") return 0;
  const payload = (firstStage as { payload?: unknown }).payload;
  if (!payload || typeof payload !== "object") return 0;
  const errors = (payload as { errors?: unknown }).errors;
  return Array.isArray(errors) ? errors.length : 0;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Optional override for the index marker — exposed for tests so
   *  the spec can assert the correct sentinel flows through to the
   *  network layer without depending on production constants. */
  indexMarker?: string;
}

export function EverythingChatSheet({
  open,
  onOpenChange,
  indexMarker = ALL_STARS_MARKER,
}: Props) {
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [pending, setPending] = useState(false);
  const messageIdRef = useRef(0);

  // Reset transcript when the sheet closes so the next open starts
  // clean (mirrors AddStarDialog's lifecycle reset behaviour).
  useEffect(() => {
    if (open) return;
    setDraft("");
    setMessages([]);
    setPending(false);
  }, [open]);

  function nextId(): string {
    messageIdRef.current += 1;
    return `everything-chat-${messageIdRef.current}`;
  }

  async function handleSend() {
    const text = draft.trim();
    if (!text || pending) return;

    const userMsg: Message = { id: nextId(), role: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setDraft("");
    setPending(true);

    try {
      const settings = await fetchSettings();
      const result = await queryRag(indexMarker, text, settings);
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "assistant",
          text: result.answer_text,
          sourceCount: result.sources?.length ?? 0,
          errorCount: countRetrievalErrors(result.retrieval_plan),
        },
      ]);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Query failed";
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "error", text: message },
      ]);
    } finally {
      setPending(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.nativeEvent.isComposing) return;
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="fixed top-0 right-0 left-auto bottom-0 z-[270] grid h-screen w-full max-w-[100vw] -translate-x-0 -translate-y-0 grid-rows-[auto_1fr_auto] gap-0 rounded-none border-l border-white/10 p-0 sm:max-w-2xl"
        data-testid="everything-chat-sheet"
      >
        <header className="flex shrink-0 items-center gap-2 border-b border-white/10 px-5 py-4">
          <DialogTitle className="text-base font-semibold">
            Chat with everything
          </DialogTitle>
          <span className="ml-auto text-[11px] text-muted-foreground">
            RAG · union of all attached indexes
          </span>
        </header>

        <div
          className="overflow-y-auto px-5 py-4"
          data-testid="everything-chat-transcript"
        >
          {messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Ask a question that spans your entire constellation —
              this chat retrieves across every attached index at once.
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  data-testid={`everything-chat-msg-${msg.role}`}
                  className={
                    msg.role === "user"
                      ? "self-end max-w-[85%] rounded-2xl bg-primary/85 px-3 py-2 text-sm text-primary-foreground"
                      : msg.role === "error"
                      ? "self-start max-w-[85%] rounded-2xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
                      : "self-start max-w-[85%] rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm"
                  }
                >
                  <p className="whitespace-pre-wrap">{msg.text}</p>
                  {msg.role === "assistant" && msg.sourceCount ? (
                    <p className="mt-1 text-[10px] opacity-70">
                      {msg.sourceCount} source
                      {msg.sourceCount === 1 ? "" : "s"}
                    </p>
                  ) : null}
                  {msg.role === "assistant" && msg.errorCount ? (
                    <p
                      className="mt-1 text-[10px] text-amber-600"
                      data-testid="everything-chat-error-notice"
                    >
                      Note: {msg.errorCount} index
                      {msg.errorCount === 1 ? "" : "es"} couldn&apos;t be queried
                      for this question.
                    </p>
                  ) : null}
                </div>
              ))}
              {pending && (
                <div className="self-start max-w-[85%] rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-muted-foreground">
                  Thinking…
                </div>
              )}
            </div>
          )}
        </div>

        <footer className="flex shrink-0 items-end gap-2 border-t border-white/10 px-5 py-4">
          <Textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask across every attached index…"
            rows={1}
            className="min-h-11 max-h-40 flex-1 resize-none"
            aria-label="Everything chat message"
            data-testid="everything-chat-input"
          />
          <Button
            onClick={() => {
              void handleSend();
            }}
            disabled={pending || draft.trim().length === 0}
            data-testid="everything-chat-send"
          >
            Send
          </Button>
        </footer>
      </DialogContent>
    </Dialog>
  );
}
