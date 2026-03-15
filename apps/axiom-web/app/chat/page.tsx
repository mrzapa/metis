"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ResizablePanels } from "@/components/chat/resizable-panels";
import { SessionsPanel } from "@/components/chat/sessions-panel";
import { ChatPanel } from "@/components/chat/chat-panel";
import { EvidencePanel } from "@/components/chat/evidence-panel";
import { fetchSession, fetchSettings, queryDirect, queryRagStream, submitRunAction } from "@/lib/api";
import type { SessionSummary, TraceEvent } from "@/lib/api";
import type { EvidenceSource } from "@/lib/chat-types";
import { useChatTranscript } from "@/app/chat/use-chat-transcript";

type StopStreamReason = "user" | "navigation";

export default function ChatPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sessionMeta, setSessionMeta] = useState<SessionSummary | null>(null);
  const [loadingSession, setLoadingSession] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [isStreamingRag, setIsStreamingRag] = useState(false);
  const [activeIndexPath, setActiveIndexPath] = useState<string | null>(null);
  const [activeIndexLabel, setActiveIndexLabel] = useState<string | null>(null);
  const [queryModeOverride, setQueryModeOverride] = useState<"rag" | null>(null);
  const [liveTraceEvents, setLiveTraceEvents] = useState<TraceEvent[]>([]);
  const settingsRef = useRef<Record<string, unknown> | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const ragRequestIdRef = useRef(0);
  const activeRagStreamRef = useRef<{
    assistantMessageId: string;
    controller: AbortController;
    pendingSources: EvidenceSource[];
    requestId: number;
    runId: string | null;
  } | null>(null);
  const [modelProvider, setModelProvider] = useState<string | null>(null);
  const [modelName, setModelName] = useState<string | null>(null);
  const {
    createMessage,
    setSessionMessages,
    reset,
    appendMessages,
    appendCompletedRunMessage,
    bindRunToAssistantMessage,
    setRunPendingSources,
    appendRunToken,
    finalizeRun,
    markRunActionRequired,
    markRunError,
    markMessageError,
    markRunAborted,
    markMessageAborted,
    setActionStatus,
    getMessage,
    messages,
    latestRunId,
    latestSources,
    runIdsNewestFirst,
  } = useChatTranscript();

  const stopRagStream = useCallback(
    (reason: StopStreamReason = "user") => {
      const activeStream = activeRagStreamRef.current;
      if (!activeStream) return;

      activeRagStreamRef.current = null;
      activeStream.controller.abort();
      setIsStreamingRag(false);

      if (reason !== "user") return;

      if (activeStream.runId) {
        markRunAborted(activeStream.runId);
        return;
      }

      markMessageAborted(activeStream.assistantMessageId);
    },
    [markMessageAborted, markRunAborted],
  );

  useEffect(() => {
    fetchSettings()
      .then((settings) => {
        const provider = String(settings.llm_provider ?? "");
        const rawModel = String(settings.llm_model ?? "");
        const model =
          rawModel === "custom"
            ? String(settings.llm_model_custom ?? rawModel)
            : rawModel;

        setModelProvider(provider);
        setModelName(model);
        settingsRef.current = settings;
      })
      .catch(() => {
        // Keep the badge empty on fetch error.
      });
  }, []);

  const handleModelChange = useCallback((provider: string, model: string) => {
    setModelProvider(provider);
    setModelName(model);
    settingsRef.current = null;
  }, []);

  useEffect(() => {
    const raw = localStorage.getItem("axiom_active_index");
    if (!raw) return;

    try {
      const { manifest_path, label } = JSON.parse(raw) as {
        manifest_path: string;
        label: string;
      };
      setActiveIndexPath(manifest_path);
      setActiveIndexLabel(label);
      setQueryModeOverride("rag");
    } catch {
      // Ignore malformed local storage entries.
    }

    localStorage.removeItem("axiom_active_index");
  }, []);

  useEffect(() => {
    return () => {
      const activeStream = activeRagStreamRef.current;
      activeRagStreamRef.current = null;
      activeStream?.controller.abort();
    };
  }, []);

  const loadSession = useCallback(
    async (id: string) => {
      setLoadingSession(true);
      setSessionError(null);
      setLiveTraceEvents([]);

      try {
        const detail = await fetchSession(id);
        setSessionMessages(detail.messages);
        setSessionMeta(detail.summary);
      } catch (error) {
        setSessionError(
          error instanceof Error ? error.message : "Failed to load session",
        );
        reset();
        setSessionMeta(null);
      } finally {
        setLoadingSession(false);
      }
    },
    [reset, setSessionMessages],
  );

  const handleSelect = useCallback(
    (id: string) => {
      stopRagStream("navigation");
      setSelectedId(id);
      loadSession(id);
    },
    [loadSession, stopRagStream],
  );

  const handleDirectSend = useCallback(
    async (prompt: string) => {
      setIsSending(true);

      appendMessages([
        createMessage({
          role: "user",
          content: prompt,
          ts: new Date().toISOString(),
          run_id: "",
          sources: [],
        }),
      ]);

      try {
        if (!settingsRef.current) {
          settingsRef.current = await fetchSettings();
        }

        const result = await queryDirect(prompt, settingsRef.current);
        appendCompletedRunMessage(
          createMessage({
            role: "assistant",
            content: result.answer_text,
            ts: new Date().toISOString(),
            run_id: result.run_id,
            sources: [],
            llm_provider: result.llm_provider,
            llm_model: result.llm_model,
            query_mode: "direct",
          }),
        );
      } catch (error) {
        appendMessages([
          createMessage(
            {
              role: "assistant",
              content:
                error instanceof Error ? error.message : "An error occurred.",
              ts: new Date().toISOString(),
              run_id: "",
              sources: [],
              query_mode: "direct",
            },
            { status: "error" },
          ),
        ]);
      } finally {
        setIsSending(false);
      }
    },
    [appendCompletedRunMessage, appendMessages, createMessage],
  );

  const handleRagSend = useCallback(
    async (question: string) => {
      if (!activeIndexPath || isStreamingRag) return;

      stopRagStream("navigation");

      const assistantMessage = createMessage(
        {
          role: "assistant",
          content: "",
          ts: new Date().toISOString(),
          run_id: "",
          sources: [],
          query_mode: "rag",
        },
        { status: "streaming" },
      );

      appendMessages([
        createMessage({
          role: "user",
          content: question,
          ts: new Date().toISOString(),
          run_id: "",
          sources: [],
        }),
        assistantMessage,
      ]);
      setLiveTraceEvents([]);
      setIsStreamingRag(true);

      const controller = new AbortController();
      const requestId = ++ragRequestIdRef.current;
      activeRagStreamRef.current = {
        assistantMessageId: assistantMessage.id,
        controller,
        pendingSources: [],
        requestId,
        runId: null,
      };

      try {
        if (!settingsRef.current) {
          settingsRef.current = await fetchSettings();
        }

        await queryRagStream(activeIndexPath, question, settingsRef.current, {
          signal: controller.signal,
          onEvent: (event) => {
            const activeStream = activeRagStreamRef.current;
            if (!activeStream || activeStream.requestId !== requestId) return;

            switch (event.type) {
              case "run_started":
                activeStream.runId = event.run_id;
                setLiveTraceEvents([
                  {
                    run_id: event.run_id,
                    stage: "retrieval",
                    event_type: "run_started",
                    timestamp: new Date().toISOString(),
                    payload: {},
                  },
                ]);
                bindRunToAssistantMessage(event.run_id, activeStream.assistantMessageId);
                break;
              case "retrieval_complete":
                activeStream.pendingSources = event.sources;
                setRunPendingSources(event.run_id, event.sources);
                setLiveTraceEvents((previousEvents) => [
                  ...previousEvents,
                  {
                    run_id: event.run_id,
                    stage: "retrieval",
                    event_type: "retrieval_complete",
                    timestamp: new Date().toISOString(),
                    payload: {
                      sources_count: event.sources.length,
                      top_score: event.top_score,
                    },
                  },
                ]);
                break;
              case "token": {
                const runId = event.run_id || activeStream.runId;
                if (!runId) {
                  return;
                }
                appendRunToken(runId, event.text);
                break;
              }
              case "final": {
                const finalSources =
                  event.sources.length > 0
                    ? event.sources
                    : activeStream.pendingSources;
                setLiveTraceEvents((previousEvents) => [
                  ...previousEvents,
                  {
                    run_id: event.run_id,
                    stage: "synthesis",
                    event_type: "final",
                    timestamp: new Date().toISOString(),
                    payload: {
                      answer_length: event.answer_text.length,
                      sources_count: finalSources.length,
                    },
                  },
                ]);
                activeRagStreamRef.current = null;
                setIsStreamingRag(false);
                finalizeRun(event.run_id, event.answer_text, finalSources);
                break;
              }
              case "action_required":
                activeRagStreamRef.current = null;
                setIsStreamingRag(false);
                markRunActionRequired(
                  event.run_id,
                  event.action,
                  new Date().toISOString(),
                );
                break;
              case "error": {
                const runId = event.run_id || activeStream.runId;
                setLiveTraceEvents((previousEvents) => [
                  ...previousEvents,
                  {
                    run_id: runId ?? "",
                    stage: "error",
                    event_type: "error",
                    timestamp: new Date().toISOString(),
                    payload: { message: event.message },
                  },
                ]);
                activeRagStreamRef.current = null;
                setIsStreamingRag(false);
                if (runId) {
                  markRunError(runId, event.message);
                } else {
                  markMessageError(activeStream.assistantMessageId, event.message);
                }
                break;
              }
            }
          },
        });

        const activeStream = activeRagStreamRef.current;
        if (activeStream?.requestId === requestId) {
          activeRagStreamRef.current = null;
          setIsStreamingRag(false);
          if (activeStream.runId) {
            markRunError(activeStream.runId, "Streaming response ended unexpectedly.");
          } else {
            markMessageError(
              activeStream.assistantMessageId,
              "Streaming response ended unexpectedly.",
            );
          }
        }
      } catch (error) {
        if (
          typeof error === "object" &&
          error !== null &&
          "name" in error &&
          error.name === "AbortError"
        ) {
          return;
        }

        const activeStream = activeRagStreamRef.current;
        if (!activeStream || activeStream.requestId !== requestId) {
          return;
        }

        activeRagStreamRef.current = null;
        setIsStreamingRag(false);

        const message =
          error instanceof Error ? error.message : "An error occurred.";
        if (activeStream.runId) {
          markRunError(activeStream.runId, message);
        } else {
          markMessageError(activeStream.assistantMessageId, message);
        }
      }
    },
    [
      activeIndexPath,
      appendMessages,
      appendRunToken,
      bindRunToAssistantMessage,
      createMessage,
      finalizeRun,
      isStreamingRag,
      markMessageError,
      markRunActionRequired,
      markRunError,
      setRunPendingSources,
      stopRagStream,
    ],
  );

  const handleNewChat = useCallback(() => {
    stopRagStream("navigation");
    setSelectedId(null);
    reset();
    setSessionMeta(null);
    setLoadingSession(false);
    setSessionError(null);
    setLiveTraceEvents([]);
  }, [reset, stopRagStream]);

  const handleActionApprove = useCallback(
    async (messageId: string) => {
      const message = getMessage(messageId);
      if (!message?.actionRequired) return;

      setActionStatus(messageId, "submitting");

      try {
        await submitRunAction(message.run_id, {
          approved: true,
          payload: message.actionRequired.action.payload,
        });
        setActionStatus(messageId, "approved");
      } catch {
        setActionStatus(messageId, "pending");
      }
    },
    [getMessage, setActionStatus],
  );

  const handleActionDeny = useCallback(
    async (messageId: string) => {
      const message = getMessage(messageId);
      if (!message?.actionRequired) return;

      setActionStatus(messageId, "submitting");

      try {
        await submitRunAction(message.run_id, { approved: false });
        setActionStatus(messageId, "denied");
      } catch {
        setActionStatus(messageId, "pending");
      }
    },
    [getMessage, setActionStatus],
  );

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        composerRef.current?.focus();
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <main className="h-screen w-screen overflow-hidden bg-background">
      <ResizablePanels
        panels={[
          {
            default: 1,
            min: 200,
            children: (
              <SessionsPanel
                selectedId={selectedId}
                onSelect={handleSelect}
                onNewChat={handleNewChat}
              />
            ),
          },
          {
            default: 3,
            min: 400,
            children: (
              <ChatPanel
                messages={messages}
                sessionMeta={sessionMeta}
                loading={loadingSession}
                error={sessionError}
                onDirectSend={handleDirectSend}
                onRagSend={handleRagSend}
                isSending={isSending}
                isStreamingRag={isStreamingRag}
                onStopStreaming={() => stopRagStream("user")}
                activeIndexPath={activeIndexPath}
                activeIndexLabel={activeIndexLabel}
                initialQueryMode={queryModeOverride ?? undefined}
                onIndexChange={(path, label) => {
                  setActiveIndexPath(path);
                  setActiveIndexLabel(label);
                }}
                modelProvider={modelProvider}
                modelName={modelName}
                onModelChange={handleModelChange}
                composerRef={composerRef}
                onActionApprove={handleActionApprove}
                onActionDeny={handleActionDeny}
              />
            ),
          },
          {
            default: 1.5,
            min: 240,
            children: (
              <EvidencePanel
                sources={latestSources}
                runIds={runIdsNewestFirst}
                latestRunId={latestRunId}
                liveTraceEvents={liveTraceEvents}
                isStreaming={isStreamingRag}
              />
            ),
          },
        ]}
      />
    </main>
  );
}
