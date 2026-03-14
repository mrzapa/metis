"use client";

import { startTransition, useCallback, useEffect, useRef, useState } from "react";
import { ResizablePanels } from "@/components/chat/resizable-panels";
import { SessionsPanel } from "@/components/chat/sessions-panel";
import { ChatPanel, type ChatMessage } from "@/components/chat/chat-panel";
import { EvidencePanel } from "@/components/chat/evidence-panel";
import { fetchSession, fetchSettings, queryDirect, queryRagStream } from "@/lib/api";
import type { SessionMessage, EvidenceSource, SessionSummary, TraceEvent } from "@/lib/api";

type StopStreamReason = "user" | "navigation";

export default function ChatPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sources, setSources] = useState<EvidenceSource[]>([]);
  const [sessionMeta, setSessionMeta] = useState<SessionSummary | null>(null);
  const [loadingSession, setLoadingSession] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [isStreamingRag, setIsStreamingRag] = useState(false);
  const [activeIndexPath, setActiveIndexPath] = useState<string | null>(null);
  const [activeIndexLabel, setActiveIndexLabel] = useState<string | null>(null);
  const [queryModeOverride, setQueryModeOverride] = useState<"rag" | null>(null);
  const [latestRunId, setLatestRunId] = useState<string | null>(null);
  const [liveTraceEvents, setLiveTraceEvents] = useState<TraceEvent[]>([]);
  const settingsRef = useRef<Record<string, unknown> | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const messageIdRef = useRef(0);
  const ragRequestIdRef = useRef(0);
  const activeRagStreamRef = useRef<{
    assistantId: string;
    controller: AbortController;
    pendingSources: EvidenceSource[];
    requestId: number;
  } | null>(null);
  const [modelProvider, setModelProvider] = useState<string | null>(null);
  const [modelName, setModelName] = useState<string | null>(null);

  const createChatMessage = useCallback(
    (
      message: SessionMessage,
      overrides?: Partial<ChatMessage>,
    ): ChatMessage => ({
      ...message,
      client_id: `${message.role}-${messageIdRef.current++}`,
      status: "complete",
      ...overrides,
    }),
    [],
  );

  const updateMessage = useCallback(
    (clientId: string, updater: (message: ChatMessage) => ChatMessage) => {
      startTransition(() => {
        setMessages((prev) =>
          prev.map((message) =>
            message.client_id === clientId ? updater(message) : message,
          ),
        );
      });
    },
    [],
  );

  const stopRagStream = useCallback(
    (reason: StopStreamReason = "user") => {
      const activeStream = activeRagStreamRef.current;
      if (!activeStream) return;

      activeRagStreamRef.current = null;
      activeStream.controller.abort();
      setIsStreamingRag(false);

      if (reason !== "user") return;

      updateMessage(activeStream.assistantId, (message) =>
        message.status === "streaming"
          ? { ...message, status: "aborted" }
          : message,
      );
    },
    [updateMessage],
  );

  // Load current model info for the badge
  useEffect(() => {
    fetchSettings().then((s) => {
      const provider = String(s.llm_provider ?? "");
      const raw = String(s.llm_model ?? "");
      const model = raw === "custom" ? String(s.llm_model_custom ?? raw) : raw;
      setModelProvider(provider);
      setModelName(model);
      settingsRef.current = s;
    }).catch(() => {
      // badge stays empty on fetch error
    });
  }, []);

  const handleModelChange = useCallback((provider: string, model: string) => {
    setModelProvider(provider);
    setModelName(model);
    settingsRef.current = null; // force re-fetch on next query
  }, []);

  // Pre-select index from library page
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
      // ignore malformed entry
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

  const loadSession = useCallback(async (id: string) => {
    setLoadingSession(true);
    setSessionError(null);
    try {
      const detail = await fetchSession(id);
      setMessages(detail.messages.map((message) => createChatMessage(message)));
      setSessionMeta(detail.summary);
      const allSources = detail.messages.flatMap((m) => m.sources);
      setSources(allSources);
    } catch (err) {
      setSessionError(
        err instanceof Error ? err.message : "Failed to load session"
      );
      setMessages([]);
      setSources([]);
      setSessionMeta(null);
    } finally {
      setLoadingSession(false);
    }
  }, [createChatMessage]);

  const handleSelect = useCallback(
    (id: string) => {
      stopRagStream("navigation");
      setSelectedId(id);
      loadSession(id);
    },
    [loadSession, stopRagStream],
  );

  const handleDirectSend = useCallback(async (prompt: string) => {
    setIsSending(true);
    const userMsg = createChatMessage({
      role: "user",
      content: prompt,
      ts: new Date().toISOString(),
      run_id: "",
      sources: [],
    });
    setMessages((prev) => [...prev, userMsg]);
    try {
      if (!settingsRef.current) {
        settingsRef.current = await fetchSettings();
      }
      const result = await queryDirect(prompt, settingsRef.current);
      const assistantMsg = createChatMessage({
        role: "assistant",
        content: result.answer_text,
        ts: new Date().toISOString(),
        run_id: result.run_id,
        sources: [],
        llm_provider: result.llm_provider,
        llm_model: result.llm_model,
        query_mode: "direct",
      });
      setMessages((prev) => [...prev, assistantMsg]);
      if (result.run_id) setLatestRunId(result.run_id);
    } catch (err) {
      const errorMsg = createChatMessage({
        role: "assistant",
        content: err instanceof Error ? err.message : "An error occurred.",
        ts: new Date().toISOString(),
        run_id: "",
        sources: [],
        query_mode: "direct",
      }, {
        status: "error",
      });
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsSending(false);
    }
  }, [createChatMessage]);

  const handleRagSend = useCallback(async (question: string) => {
    if (!activeIndexPath || isStreamingRag) return;

    stopRagStream("navigation");

    const userMsg = createChatMessage({
      role: "user",
      content: question,
      ts: new Date().toISOString(),
      run_id: "",
      sources: [],
    });
    const assistantId = `assistant-stream-${messageIdRef.current++}`;
    const assistantMsg: ChatMessage = {
      role: "assistant",
      content: "",
      ts: new Date().toISOString(),
      run_id: "",
      sources: [],
      query_mode: "rag",
      client_id: assistantId,
      status: "streaming",
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setSources([]);
    setLiveTraceEvents([]);
    setIsStreamingRag(true);

    const controller = new AbortController();
    const requestId = ++ragRequestIdRef.current;
    activeRagStreamRef.current = {
      assistantId,
      controller,
      pendingSources: [],
      requestId,
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
              setLatestRunId(event.run_id);
              setLiveTraceEvents([{
                run_id: event.run_id,
                stage: "retrieval",
                event_type: "run_started",
                timestamp: new Date().toISOString(),
                payload: {},
              }]);
              updateMessage(assistantId, (message) => ({
                ...message,
                run_id: event.run_id,
              }));
              break;
            case "retrieval_complete":
              activeStream.pendingSources = event.sources;
              setLiveTraceEvents((prev) => [...prev, {
                run_id: event.run_id,
                stage: "retrieval",
                event_type: "retrieval_complete",
                timestamp: new Date().toISOString(),
                payload: { sources_count: event.sources.length, top_score: event.top_score },
              }]);
              break;
            case "token":
              updateMessage(assistantId, (message) => ({
                ...message,
                content: `${message.content}${event.text}`,
                run_id: event.run_id || message.run_id,
              }));
              break;
            case "final": {
              const finalSources =
                event.sources.length > 0 ? event.sources : activeStream.pendingSources;
              setLiveTraceEvents((prev) => [...prev, {
                run_id: event.run_id,
                stage: "synthesis",
                event_type: "final",
                timestamp: new Date().toISOString(),
                payload: { answer_length: event.answer_text.length, sources_count: finalSources.length },
              }]);
              activeRagStreamRef.current = null;
              setIsStreamingRag(false);
              startTransition(() => {
                setMessages((prev) =>
                  prev.map((message) =>
                    message.client_id === assistantId
                      ? {
                          ...message,
                          content: event.answer_text,
                          run_id: event.run_id,
                          sources: finalSources,
                          status: "complete",
                        }
                      : message,
                  ),
                );
              });
              setSources(finalSources);
              setLatestRunId(event.run_id);
              break;
            }
            case "error":
              setLiveTraceEvents((prev) => [...prev, {
                run_id: event.run_id,
                stage: "error",
                event_type: "error",
                timestamp: new Date().toISOString(),
                payload: { message: event.message },
              }]);
              activeRagStreamRef.current = null;
              setIsStreamingRag(false);
              updateMessage(assistantId, (message) => ({
                ...message,
                content: message.content.trim() ? message.content : event.message,
                run_id: event.run_id || message.run_id,
                status: "error",
              }));
              break;
          }
        },
      });

      if (activeRagStreamRef.current?.requestId === requestId) {
        activeRagStreamRef.current = null;
        setIsStreamingRag(false);
        updateMessage(assistantId, (message) => ({
          ...message,
          content: message.content.trim()
            ? message.content
            : "Streaming response ended unexpectedly.",
          status: "error",
        }));
      }
    } catch (err) {
      if (
        typeof err === "object" &&
        err !== null &&
        "name" in err &&
        err.name === "AbortError"
      ) {
        return;
      }

      if (activeRagStreamRef.current?.requestId !== requestId) {
        return;
      }

      activeRagStreamRef.current = null;
      setIsStreamingRag(false);

      const message = err instanceof Error ? err.message : "An error occurred.";
      updateMessage(assistantId, (assistant) => ({
        ...assistant,
        content: assistant.content.trim() ? assistant.content : message,
        status: "error",
      }));
    }
  }, [activeIndexPath, createChatMessage, isStreamingRag, stopRagStream, updateMessage]);

  const handleNewChat = useCallback(() => {
    stopRagStream("navigation");
    setSelectedId(null);
    setMessages([]);
    setSources([]);
    setSessionMeta(null);
    setLoadingSession(false);
    setSessionError(null);
    setLatestRunId(null);
    setLiveTraceEvents([]);
  }, [stopRagStream]);

  // Keyboard shortcut: Cmd/Ctrl+K focuses the composer
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
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
              />
            ),
          },
          {
            default: 1.5,
            min: 240,
            children: (
              <EvidencePanel
                sources={sources}
                runIds={messages
                  .filter((m) => m.role === "assistant" && m.run_id)
                  .map((m) => m.run_id)
                  .reverse()}
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
