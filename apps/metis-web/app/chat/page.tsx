"use client";

import { useCallback, useEffect, useRef } from "react";
import { ResizablePanels } from "@/components/chat/resizable-panels";
import { SessionsPanel } from "@/components/chat/sessions-panel";
import { ChatPanel } from "@/components/chat/chat-panel";
import { EvidencePanel } from "@/components/chat/evidence-panel";
import { Badge } from "@/components/ui/badge";
import { PageChrome } from "@/components/shell/page-chrome";
import { createSession, fetchSession, fetchSettings, queryDirect, queryKnowledgeSearch, queryRagStream, submitRunAction, updateSettings } from "@/lib/api";
import type { RetrievalFallback, SessionSummary, TraceEvent } from "@/lib/api";
import type { RagStreamEvent } from "@/lib/api";
import type { EvidenceSource } from "@/lib/chat-types";
import { useChatTranscript } from "@/app/chat/use-chat-transcript";
import { useArrowState } from "@/hooks/use-arrow-state";
import {
  clearResumableRagRun,
  loadResumableRagRun,
  saveResumableRagRun,
  type ResumableRagRunSnapshot,
} from "@/app/chat/rag-stream-resume";

type StopStreamReason = "user" | "navigation";
const KNOWLEDGE_SEARCH_MODE = "Knowledge Search";

function resolveArtifactsEnabled(settings: Record<string, unknown>): boolean | undefined {
  const candidate = settings.enable_arrow_artifacts;
  return typeof candidate === "boolean" ? candidate : undefined;
}

function resolveArtifactRuntimeEnabled(settings: Record<string, unknown>): boolean | undefined {
  const candidate = settings.enable_arrow_artifact_runtime;
  return typeof candidate === "boolean" ? candidate : undefined;
}

interface ActiveRagStream {
  assistantMessageId: string;
  controller: AbortController;
  fallback: RetrievalFallback | null;
  pendingSources: EvidenceSource[];
  requestId: number;
  runId: string;
  question: string;
  manifestPath: string;
  indexLabel: string | null;
  userMessageTs: string;
  assistantMessageTs: string;
  assistantContent: string;
  lastEventId: number;
  dedupeFloorEventId: number;
  liveTraceEvents: TraceEvent[];
  hasBoundRun: boolean;
  seenEventSignatures: Set<string>;
  subQueries?: string[];
}

interface ResumableRagRunState extends ResumableRagRunSnapshot {
  assistantMessageId: string;
  hasBoundRun: boolean;
}

interface StartRagStreamOptions {
  assistantMessageId: string;
  assistantMessageTs: string;
  assistantSeedContent: string;
  dedupeFloorEventId?: number;
  hasBoundRun: boolean;
  indexLabel: string | null;
  lastEventId: number;
  liveTraceEvents: TraceEvent[];
  manifestPath: string;
  pendingSources: EvidenceSource[];
  question: string;
  runId: string;
  sessionId?: string | null;
  userMessageTs: string;
}

function buildEventSignature(
  event: RagStreamEvent,
  fallbackRunId: string,
  eventId: number | null,
): string {
  const runId = String(event.run_id || fallbackRunId || "").trim();
  if (eventId !== null) {
    return `${runId}:${eventId}`;
  }
  return `${runId}:${event.type}:${JSON.stringify(event)}`;
}

function createClientRunId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `rag-run-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function mergeEvidenceSources(
  existing: EvidenceSource[],
  incoming: EvidenceSource[],
): EvidenceSource[] {
  const merged = [...existing];
  const seen = new Set(
    existing.map((source) => String(source.chunk_id || source.sid || source.snippet || "")),
  );

  for (const source of incoming) {
    const key = String(source.chunk_id || source.sid || source.snippet || "");
    if (key && seen.has(key)) {
      continue;
    }
    if (key) {
      seen.add(key);
    }
    merged.push(source);
  }

  return merged;
}

function buildResumableRagRunState(
  stream: ActiveRagStream,
): ResumableRagRunState {
  return {
    version: 1,
    manifestPath: stream.manifestPath,
    indexLabel: stream.indexLabel,
    question: stream.question,
    runId: stream.runId,
    lastEventId: stream.lastEventId,
    userMessageTs: stream.userMessageTs,
    assistantMessageTs: stream.assistantMessageTs,
    assistantContent: stream.assistantContent,
    pendingSources: [...stream.pendingSources],
    sources: [...stream.pendingSources],
    liveTraceEvents: [...stream.liveTraceEvents],
    subQueries: stream.subQueries ? [...stream.subQueries] : undefined,
    assistantMessageId: stream.assistantMessageId,
    hasBoundRun: stream.hasBoundRun,
  };
}

function toStoredResumableRagRun(
  state: ResumableRagRunState,
): ResumableRagRunSnapshot {
  return {
    version: state.version,
    manifestPath: state.manifestPath,
    indexLabel: state.indexLabel,
    question: state.question,
    runId: state.runId,
    lastEventId: state.lastEventId,
    userMessageTs: state.userMessageTs,
    assistantMessageTs: state.assistantMessageTs,
    assistantContent: state.assistantContent,
    pendingSources: [...state.pendingSources],
    sources: [...state.sources],
    liveTraceEvents: [...state.liveTraceEvents],
    subQueries: state.subQueries ? [...state.subQueries] : undefined,
  };
}

export default function ChatPage() {
  const [selectedId, setSelectedId] = useArrowState<string | null>(null);
  const [sessionMeta, setSessionMeta] = useArrowState<SessionSummary | null>(null);
  const [loadingSession, setLoadingSession] = useArrowState(false);
  const [sessionError, setSessionError] = useArrowState<string | null>(null);
  const [isSending, setIsSending] = useArrowState(false);
  const [isStreamingRag, setIsStreamingRag] = useArrowState(false);
  const [activeIndexPath, setActiveIndexPath] = useArrowState<string | null>(null);
  const [activeIndexLabel, setActiveIndexLabel] = useArrowState<string | null>(null);
  const [queryModeOverride, setQueryModeOverride] = useArrowState<"rag" | null>(null);
  const [liveTraceEvents, setLiveTraceEvents] = useArrowState<TraceEvent[]>([]);
  const [resumableRun, setResumableRun] = useArrowState<ResumableRagRunState | null>(null);
  const settingsRef = useRef<Record<string, unknown> | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const ragRequestIdRef = useRef(0);
  const activeRagStreamRef = useRef<ActiveRagStream | null>(null);
  const [modelProvider, setModelProvider] = useArrowState<string | null>(null);
  const [modelName, setModelName] = useArrowState<string | null>(null);
  const [agenticMode, setAgenticMode] = useArrowState(false);
  const [agenticModeSaving, setAgenticModeSaving] = useArrowState(false);
  const [agenticModeError, setAgenticModeError] = useArrowState<string | null>(null);
  const [traceFirstLayout, setTraceFirstLayout] = useArrowState(false);
  const [shellPostureToken, setShellPostureToken] = useArrowState(0);
  const [preferredEvidenceTab, setPreferredEvidenceTab] = useArrowState<"sources" | "trace">("sources");
  const [initialDraft, setInitialDraft] = useArrowState("");
  const [sessionRefreshToken, setSessionRefreshToken] = useArrowState(0);
  const [selectedRagMode, setSelectedRagMode] = useArrowState<string>("Q&A");
  const [latestFallback, setLatestFallback] = useArrowState<RetrievalFallback | null>(null);
  const [artifactsEnabled, setArtifactsEnabled] = useArrowState<boolean | undefined>(undefined);
  const [artifactRuntimeEnabled, setArtifactRuntimeEnabled] = useArrowState<boolean | undefined>(undefined);
  const sessionIdRef = useRef<string | null>(null);
  const {
    createMessage,
    restoreStreamingRun,
    setSessionMessages,
    reset,
    appendMessages,
    appendCompletedRunMessage,
    bindRunToAssistantMessage,
    setRunPendingSources,
    setRunSubqueries,
    appendRunToken,
    finalizeRun,
    markRunActionRequired,
    markRunError,
    markMessageError,
    markRunAborted,
    markMessageAborted,
    setMessageStatus,
    setActionStatus,
    getMessage,
    getRun,
    messages,
    latestRunId,
    latestSources,
    latestAnswer,
    runIdsNewestFirst,
  } = useChatTranscript();
  const companionSessionId = selectedId ?? sessionMeta?.session_id ?? null;

  const getRunSubqueries = useCallback(
    (runId: string) => getRun(runId)?.sub_queries,
    [getRun],
  );

  const publishResumableRun = useCallback((snapshot: ResumableRagRunState | null) => {
    setResumableRun(snapshot);
    if (snapshot) {
      saveResumableRagRun(toStoredResumableRagRun(snapshot));
      return;
    }
    clearResumableRagRun();
  }, []);

  const stopRagStream = useCallback(
    (reason: StopStreamReason = "user") => {
      const activeStream = activeRagStreamRef.current;
      if (!activeStream) return;

      activeRagStreamRef.current = null;
      activeStream.controller.abort();
      setIsStreamingRag(false);
      setLatestFallback(activeStream.fallback);
      publishResumableRun(null);

      if (reason !== "user") return;

      if (activeStream.hasBoundRun) {
        markRunAborted(activeStream.runId);
        return;
      }

      markMessageAborted(activeStream.assistantMessageId);
    },
    [markMessageAborted, markRunAborted, publishResumableRun],
  );

  const applyShellPosture = useCallback((isAgentic: boolean) => {
    setTraceFirstLayout(isAgentic);
    setPreferredEvidenceTab(isAgentic ? "trace" : "sources");
    setShellPostureToken((t) => t + 1);
  }, []);

  const handleAgenticModeChange = useCallback(
    async (enabled: boolean) => {
      setAgenticMode(enabled);
      setAgenticModeSaving(true);
      setAgenticModeError(null);
      applyShellPosture(enabled);
      try {
        await updateSettings({ agentic_mode: enabled });
        settingsRef.current = null;
      } catch (err) {
        setAgenticMode(!enabled);
        applyShellPosture(!enabled);
        setAgenticModeError(err instanceof Error ? err.message : "Failed to save");
      } finally {
        setAgenticModeSaving(false);
      }
    },
    [applyShellPosture],
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
        setArtifactsEnabled(resolveArtifactsEnabled(settings));
        setArtifactRuntimeEnabled(resolveArtifactRuntimeEnabled(settings));

        const isAgentic = Boolean(settings.agentic_mode);
        setAgenticMode(isAgentic);
        applyShellPosture(isAgentic);

        const mode = String(settings.selected_mode ?? "Q&A");
        setSelectedRagMode(mode);
      })
      .catch(() => {
        // Keep the badge empty on fetch error.
      });
  }, [applyShellPosture]);

  const handleRagModeChange = useCallback(async (mode: string) => {
    setSelectedRagMode(mode);
    try {
      await updateSettings({ selected_mode: mode });
      settingsRef.current = null;
    } catch {
      // Best-effort — the mode is still applied for the current session.
    }
  }, []);

  const handleModelChange = useCallback((provider: string, model: string) => {
    setModelProvider(provider);
    setModelName(model);
    settingsRef.current = null;
  }, []);

  useEffect(() => {
    let raw = localStorage.getItem("metis_active_index");
    if (!raw) {
      const legacy = localStorage.getItem("metis_active_index");
      if (legacy) {
        localStorage.setItem("metis_active_index", legacy);
        localStorage.removeItem("metis_active_index");
        raw = legacy;
      }
    }
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

    localStorage.removeItem("metis_active_index");
    localStorage.removeItem("metis_active_index");
  }, []);

  useEffect(() => {
    sessionIdRef.current = companionSessionId;
  }, [companionSessionId]);

  useEffect(() => {
    let seedPrompt = localStorage.getItem("metis_chat_seed_prompt");
    if (!seedPrompt) {
      const legacy = localStorage.getItem("metis_chat_seed_prompt");
      if (legacy) {
        localStorage.setItem("metis_chat_seed_prompt", legacy);
        localStorage.removeItem("metis_chat_seed_prompt");
        seedPrompt = legacy;
      }
    }
    if (!seedPrompt) {
      return;
    }
    setInitialDraft(seedPrompt);
    localStorage.removeItem("metis_chat_seed_prompt");
    localStorage.removeItem("metis_chat_seed_prompt");
  }, []);

  useEffect(() => {
    const snapshot = loadResumableRagRun();
    if (!snapshot) {
      return;
    }

    const visibleSources =
      snapshot.sources.length > 0 ? snapshot.sources : snapshot.pendingSources;
    const userMessage = createMessage({
      role: "user",
      content: snapshot.question,
      ts: snapshot.userMessageTs,
      run_id: "",
      sources: [],
      query_mode: "rag",
    });
    const assistantMessage = createMessage(
      {
        role: "assistant",
        content: snapshot.assistantContent,
        ts: snapshot.assistantMessageTs,
        run_id: snapshot.runId,
        sources: visibleSources,
        query_mode: "rag",
      },
      { status: "error" },
    );

    restoreStreamingRun({
      userMessage,
      assistantMessage,
      runId: snapshot.runId,
      sources: visibleSources,
      pendingSources: snapshot.pendingSources,
    });
    setLiveTraceEvents(snapshot.liveTraceEvents);
    setActiveIndexPath(snapshot.manifestPath);
    setActiveIndexLabel(snapshot.indexLabel);
    setQueryModeOverride("rag");
    setResumableRun({
      ...snapshot,
      assistantMessageId: assistantMessage.id,
      hasBoundRun: true,
    });
  }, [createMessage, restoreStreamingRun]);

  useEffect(() => {
    function persistInterruptedRun() {
      const activeStream = activeRagStreamRef.current;
      if (!activeStream) {
        return;
      }
      saveResumableRagRun(
        toStoredResumableRagRun(buildResumableRagRunState(activeStream)),
      );
    }

    window.addEventListener("pagehide", persistInterruptedRun);

    return () => {
      window.removeEventListener("pagehide", persistInterruptedRun);
      persistInterruptedRun();
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
      sessionIdRef.current = id;

      try {
        const detail = await fetchSession(id);
      setSessionMessages(detail.messages);
      setSessionMeta(detail.summary);
      setLatestFallback(null);
    } catch (error) {
        setSessionError(
          error instanceof Error ? error.message : "Failed to load session",
        );
      reset();
      setSessionMeta(null);
      setLatestFallback(null);
      } finally {
        setLoadingSession(false);
      }
    },
    [reset, setSessionMessages],
  );

  const handleSelect = useCallback(
    (id: string) => {
      stopRagStream("navigation");
      publishResumableRun(null);
      setSelectedId(id);
      loadSession(id);
      applyShellPosture(agenticMode);
    },
    [agenticMode, applyShellPosture, loadSession, publishResumableRun, stopRagStream],
  );

  const autoCreateSession = useCallback(
    async (question: string): Promise<string | null> => {
      if (sessionIdRef.current !== null || messages.length > 0) {
        return sessionIdRef.current;
      }
      const trimmed = question.trim();
      const title = trimmed.slice(0, 60) + (trimmed.length > 60 ? "…" : "");
      try {
        const summary = await createSession(title || "New Chat");
        setSelectedId(summary.session_id);
        setSessionMeta(summary);
        sessionIdRef.current = summary.session_id;
        setSessionRefreshToken((t) => t + 1);
        return summary.session_id;
      } catch {
        // Best-effort — proceed without a session if creation fails.
        return sessionIdRef.current;
      }
    },
    [messages.length],
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
      setLatestFallback(null);

      const sessionId = await autoCreateSession(prompt);

      try {
        if (!settingsRef.current) {
          const settings = await fetchSettings();
          settingsRef.current = settings;
          setArtifactsEnabled(resolveArtifactsEnabled(settings));
          setArtifactRuntimeEnabled(resolveArtifactRuntimeEnabled(settings));
        }

        const result = await queryDirect(prompt, settingsRef.current, sessionId ?? undefined);
        appendCompletedRunMessage(
          createMessage({
            role: "assistant",
            content: result.answer_text,
            ts: new Date().toISOString(),
            run_id: result.run_id,
            sources: [],
            llm_provider: result.llm_provider,
            llm_model: result.llm_model,
            artifacts: result.artifacts,
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
    [appendCompletedRunMessage, appendMessages, autoCreateSession, createMessage],
  );

  const startRagStream = useCallback(
    async ({
      assistantMessageId,
      assistantMessageTs,
      assistantSeedContent,
      dedupeFloorEventId = 0,
      hasBoundRun,
      indexLabel,
      lastEventId,
      liveTraceEvents: initialLiveTraceEvents,
      manifestPath,
      pendingSources: initialPendingSources,
      question,
      runId,
      sessionId,
      userMessageTs,
    }: StartRagStreamOptions) => {
      const appendTraceEvent = (
        activeStream: ActiveRagStream,
        traceEvent: TraceEvent,
      ) => {
        activeStream.liveTraceEvents = [
          ...activeStream.liveTraceEvents,
          traceEvent,
        ];
        setLiveTraceEvents(activeStream.liveTraceEvents);
      };

      const handleInterruption = (
        activeStream: ActiveRagStream,
        message: string,
      ) => {
        if (activeStream.hasBoundRun) {
          markRunError(activeStream.runId, message);
        } else {
          markMessageError(activeStream.assistantMessageId, message);
        }
        publishResumableRun(buildResumableRagRunState(activeStream));
      };

      const runAttempt = async (
        attemptLastEventId: number | null,
        attemptDedupeFloor: number,
        allowRestartFallback: boolean,
      ): Promise<void> => {
        const controller = new AbortController();
        const requestId = ++ragRequestIdRef.current;
        const activeStream: ActiveRagStream = {
          assistantMessageId,
          controller,
          fallback: null,
          pendingSources: [...initialPendingSources],
          requestId,
          runId,
          question,
          manifestPath,
          indexLabel,
          userMessageTs,
          assistantMessageTs,
          assistantContent: assistantSeedContent,
          lastEventId,
          dedupeFloorEventId: attemptDedupeFloor,
          liveTraceEvents: [...initialLiveTraceEvents],
          hasBoundRun,
          seenEventSignatures: new Set<string>(),
        };

        activeRagStreamRef.current = activeStream;
        setIsStreamingRag(true);
        setLiveTraceEvents(activeStream.liveTraceEvents);

        let appliedEventCount = 0;

        try {
          if (!settingsRef.current) {
            const settings = await fetchSettings();
            settingsRef.current = settings;
            setArtifactsEnabled(resolveArtifactsEnabled(settings));
            setArtifactRuntimeEnabled(resolveArtifactRuntimeEnabled(settings));
          }

          const ragSettings = { ...settingsRef.current, selected_mode: selectedRagMode };

          await queryRagStream(manifestPath, question, ragSettings, {
            signal: controller.signal,
            runId,
            sessionId,
            lastEventId: attemptLastEventId,
            onEvent: (event, meta) => {
              const currentStream = activeRagStreamRef.current;
              if (!currentStream || currentStream.requestId !== requestId) {
                return;
              }

              const eventId = meta.eventId;
              if (
                eventId !== null &&
                event.run_id === currentStream.runId &&
                eventId <= currentStream.dedupeFloorEventId
              ) {
                return;
              }

              const signature = buildEventSignature(
                event,
                currentStream.runId,
                eventId,
              );
              if (currentStream.seenEventSignatures.has(signature)) {
                return;
              }
              currentStream.seenEventSignatures.add(signature);
              appliedEventCount += 1;

              if (
                eventId !== null &&
                Number.isFinite(eventId) &&
                eventId > currentStream.lastEventId
              ) {
                currentStream.lastEventId = eventId;
              }

              const resolvedRunId = event.run_id || currentStream.runId;

              switch (event.type) {
                case "run_started":
                  currentStream.runId = event.run_id;
                  currentStream.hasBoundRun = true;
                  bindRunToAssistantMessage(
                    event.run_id,
                    currentStream.assistantMessageId,
                  );
                  appendTraceEvent(currentStream, {
                    run_id: event.run_id,
                    event_id: eventId !== null ? String(eventId) : undefined,
                    stage: "retrieval",
                    event_type: "run_started",
                    timestamp: new Date().toISOString(),
                    payload: {},
                  });
                  break;
                case "retrieval_complete":
                  currentStream.pendingSources = event.sources;
                  setRunPendingSources(resolvedRunId, event.sources);
                  appendTraceEvent(currentStream, {
                    run_id: resolvedRunId,
                    event_id: eventId !== null ? String(eventId) : undefined,
                    stage: "retrieval",
                    event_type: "retrieval_complete",
                    timestamp: new Date().toISOString(),
                    payload: {
                      sources_count: event.sources.length,
                      top_score: event.top_score,
                    },
                  });
                  break;
                case "retrieval_augmented": {
                  const mergedSources = mergeEvidenceSources(
                    currentStream.pendingSources,
                    event.sources,
                  );
                  currentStream.pendingSources = mergedSources;
                  setRunPendingSources(resolvedRunId, mergedSources);
                  appendTraceEvent(currentStream, {
                    run_id: resolvedRunId,
                    event_id: eventId !== null ? String(eventId) : undefined,
                    stage: "retrieval",
                    event_type: "retrieval_augmented",
                    timestamp: new Date().toISOString(),
                    payload: {
                      sources_count: event.sources.length,
                      top_score: event.top_score,
                    },
                  });
                  break;
                }
                case "subqueries":
                  currentStream.subQueries = event.queries;
                  setRunSubqueries(resolvedRunId, event.queries);
                  appendTraceEvent(currentStream, {
                    run_id: resolvedRunId,
                    event_id: eventId !== null ? String(eventId) : undefined,
                    stage: "retrieval",
                    event_type: "subqueries",
                    timestamp: new Date().toISOString(),
                    payload: { queries: event.queries },
                  });
                  break;
                case "iteration_start":
                  appendTraceEvent(currentStream, {
                    run_id: resolvedRunId,
                    event_id: eventId !== null ? String(eventId) : undefined,
                    stage: "reflection",
                    event_type: "iteration_start",
                    timestamp: new Date().toISOString(),
                    iteration: event.iteration,
                    payload: {
                      total_iterations: event.total_iterations,
                    },
                  });
                  break;
                case "gaps_identified":
                  appendTraceEvent(currentStream, {
                    run_id: resolvedRunId,
                    event_id: eventId !== null ? String(eventId) : undefined,
                    stage: "reflection",
                    event_type: "gaps_identified",
                    timestamp: new Date().toISOString(),
                    iteration: event.iteration,
                    payload: { gaps: event.gaps },
                  });
                  break;
                case "refinement_retrieval": {
                  const mergedSources = mergeEvidenceSources(
                    currentStream.pendingSources,
                    event.sources,
                  );
                  currentStream.pendingSources = mergedSources;
                  setRunPendingSources(resolvedRunId, mergedSources);
                  appendTraceEvent(currentStream, {
                    run_id: resolvedRunId,
                    event_id: eventId !== null ? String(eventId) : undefined,
                    stage: "retrieval",
                    event_type: "refinement_retrieval",
                    timestamp: new Date().toISOString(),
                    iteration: event.iteration,
                    payload: {
                      sources_count: event.sources.length,
                      top_score: event.top_score,
                    },
                  });
                  break;
                }
                case "fallback_decision":
                  currentStream.fallback = event.fallback ?? null;
                  setLatestFallback(event.fallback ?? null);
                  appendTraceEvent(currentStream, {
                    run_id: resolvedRunId,
                    event_id: eventId !== null ? String(eventId) : undefined,
                    stage: "fallback",
                    event_type: "fallback_decision",
                    timestamp: new Date().toISOString(),
                    payload: { fallback: event.fallback },
                  });
                  break;
                case "token":
                  currentStream.assistantContent = `${currentStream.assistantContent}${event.text}`;
                  appendRunToken(resolvedRunId, event.text);
                  setMessageStatus(currentStream.assistantMessageId, "streaming");
                  break;
                case "final": {
                  const finalSources =
                    event.sources.length > 0
                      ? event.sources
                      : currentStream.pendingSources;
                  currentStream.assistantContent = event.answer_text;
                  appendTraceEvent(currentStream, {
                    run_id: resolvedRunId,
                    event_id: eventId !== null ? String(eventId) : undefined,
                    stage: "synthesis",
                    event_type: "final",
                    timestamp: new Date().toISOString(),
                    payload: {
                      answer_length: event.answer_text.length,
                      sources_count: finalSources.length,
                      fallback_triggered: Boolean(event.fallback?.triggered ?? currentStream.fallback?.triggered),
                    },
                  });
                  setLatestFallback(event.fallback ?? currentStream.fallback);
                  activeRagStreamRef.current = null;
                  setIsStreamingRag(false);
                  publishResumableRun(null);
                  finalizeRun(
                    resolvedRunId,
                    event.answer_text,
                    finalSources,
                    event.artifacts,
                  );
                  break;
                }
                case "action_required":
                  activeRagStreamRef.current = null;
                  setIsStreamingRag(false);
                  setLatestFallback(null);
                  publishResumableRun(null);
                  markRunActionRequired(
                    resolvedRunId,
                    event.action,
                    new Date().toISOString(),
                  );
                  break;
                case "error":
                  appendTraceEvent(currentStream, {
                    run_id: resolvedRunId,
                    event_id: eventId !== null ? String(eventId) : undefined,
                    stage: "error",
                    event_type: "error",
                    timestamp: new Date().toISOString(),
                    payload: { message: event.message },
                  });
                  activeRagStreamRef.current = null;
                  setIsStreamingRag(false);
                  setLatestFallback(null);
                  publishResumableRun(null);
                  if (currentStream.hasBoundRun) {
                    markRunError(resolvedRunId, event.message);
                  } else {
                    markMessageError(
                      currentStream.assistantMessageId,
                      event.message,
                    );
                  }
                  break;
              }
            },
          });

          const currentStream = activeRagStreamRef.current;
          if (!currentStream || currentStream.requestId !== requestId) {
            return;
          }

          if (
            allowRestartFallback &&
            attemptLastEventId !== null &&
            attemptLastEventId > 0 &&
            appliedEventCount === 0
          ) {
            await runAttempt(null, currentStream.lastEventId, false);
            return;
          }

          activeRagStreamRef.current = null;
          setIsStreamingRag(false);
          handleInterruption(
            currentStream,
            "Streaming response ended unexpectedly.",
          );
        } catch (error) {
          if (
            typeof error === "object" &&
            error !== null &&
            "name" in error &&
            error.name === "AbortError"
          ) {
            return;
          }

          const currentStream = activeRagStreamRef.current;
          if (!currentStream || currentStream.requestId !== requestId) {
            return;
          }

          activeRagStreamRef.current = null;
          setIsStreamingRag(false);
          handleInterruption(
            currentStream,
            error instanceof Error ? error.message : "An error occurred.",
          );
        }
      };

      await runAttempt(
        lastEventId > 0 ? lastEventId : null,
        dedupeFloorEventId,
        lastEventId > 0,
      );
    },
    [
      appendRunToken,
      bindRunToAssistantMessage,
      finalizeRun,
      markMessageError,
      markRunActionRequired,
      markRunError,
      publishResumableRun,
      selectedRagMode,
      setMessageStatus,
      setRunPendingSources,
      setRunSubqueries,
    ],
  );

  const handleRagSend = useCallback(
    async (question: string) => {
      if (!activeIndexPath || isStreamingRag) {
        return;
      }

      stopRagStream("navigation");
      publishResumableRun(null);
      setLatestFallback(null);

      const sessionId = await autoCreateSession(question);
      const isKnowledgeSearch = selectedRagMode === KNOWLEDGE_SEARCH_MODE;

      const userMessageTs = new Date().toISOString();
      const runId = createClientRunId();

      appendMessages([
        createMessage({
          role: "user",
          content: question,
          ts: userMessageTs,
          run_id: "",
          sources: [],
          query_mode: isKnowledgeSearch ? "knowledge_search" : "rag",
        }),
      ]);
      setLiveTraceEvents([]);

      if (isKnowledgeSearch) {
        setIsSending(true);
        try {
          if (!settingsRef.current) {
            const settings = await fetchSettings();
            settingsRef.current = settings;
            setArtifactsEnabled(resolveArtifactsEnabled(settings));
            setArtifactRuntimeEnabled(resolveArtifactRuntimeEnabled(settings));
          }

          const ragSettings = { ...settingsRef.current, selected_mode: selectedRagMode };
          const result = await queryKnowledgeSearch(activeIndexPath, question, ragSettings, {
            runId,
            sessionId,
          });
          setLatestFallback(result.fallback ?? null);
          appendCompletedRunMessage(
            createMessage({
              role: "assistant",
              content: result.summary_text,
              ts: new Date().toISOString(),
              run_id: result.run_id,
              sources: result.sources,
              query_mode: "knowledge_search",
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
                query_mode: "knowledge_search",
              },
              { status: "error" },
            ),
          ]);
        } finally {
          setIsSending(false);
        }
        return;
      }

      const assistantMessageTs = new Date().toISOString();
      const assistantMessage = createMessage(
        {
          role: "assistant",
          content: "",
          ts: assistantMessageTs,
          run_id: "",
          sources: [],
          query_mode: "rag",
        },
        { status: "streaming" },
      );

      appendMessages([assistantMessage]);

      await startRagStream({
        assistantMessageId: assistantMessage.id,
        assistantMessageTs,
        assistantSeedContent: "",
        hasBoundRun: false,
        indexLabel: activeIndexLabel,
        lastEventId: 0,
        liveTraceEvents: [],
        manifestPath: activeIndexPath,
        pendingSources: [],
        question,
        runId,
        sessionId,
        userMessageTs,
      });
    },
    [
      activeIndexLabel,
      activeIndexPath,
      appendMessages,
      autoCreateSession,
      createMessage,
      isStreamingRag,
      selectedRagMode,
      publishResumableRun,
      appendCompletedRunMessage,
      startRagStream,
      stopRagStream,
    ],
  );

  const handleReconnectRag = useCallback(async () => {
    if (!resumableRun || isStreamingRag) {
      return;
    }

    setMessageStatus(resumableRun.assistantMessageId, "streaming");
    setLiveTraceEvents(resumableRun.liveTraceEvents);

    await startRagStream({
      assistantMessageId: resumableRun.assistantMessageId,
      assistantMessageTs: resumableRun.assistantMessageTs,
      assistantSeedContent: resumableRun.assistantContent,
      dedupeFloorEventId: 0,
      hasBoundRun: resumableRun.hasBoundRun,
      indexLabel: resumableRun.indexLabel,
      lastEventId: resumableRun.lastEventId,
      liveTraceEvents: resumableRun.liveTraceEvents,
      manifestPath: resumableRun.manifestPath,
      pendingSources: resumableRun.pendingSources,
      question: resumableRun.question,
      runId: resumableRun.runId,
      sessionId: sessionIdRef.current,
      userMessageTs: resumableRun.userMessageTs,
    });
  }, [isStreamingRag, resumableRun, setMessageStatus, startRagStream]);

  const handleDiscardResumableRun = useCallback(() => {
    if (!resumableRun) {
      return;
    }

    publishResumableRun(null);
    if (resumableRun.hasBoundRun) {
      markRunAborted(resumableRun.runId);
      return;
    }
    markMessageAborted(resumableRun.assistantMessageId);
  }, [markMessageAborted, markRunAborted, publishResumableRun, resumableRun]);

  const handleNewChat = useCallback(() => {
    stopRagStream("navigation");
    publishResumableRun(null);
    setSelectedId(null);
    reset();
    setSessionMeta(null);
    setLoadingSession(false);
    setSessionError(null);
    setLiveTraceEvents([]);
    setLatestFallback(null);
    applyShellPosture(agenticMode);
  }, [agenticMode, applyShellPosture, publishResumableRun, reset, stopRagStream]);

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
    <PageChrome
      eyebrow="Chat"
      title="Ask questions, get grounded answers"
      description="Switch between direct reasoning and retrieval-augmented mode. Inspect evidence, trace data, and manage sessions."
      actions={
        <>
          {activeIndexLabel ? <Badge variant="outline">Index: {activeIndexLabel}</Badge> : null}
        </>
      }
      heroAside={undefined}
      fullBleed
      contentClassName="rounded-none border-0 bg-transparent p-0"
      companionContext={{
        sessionId: companionSessionId,
        runId: latestRunId,
      }}
    >
      <div className="chat-shell-frame h-[calc(100dvh-13.75rem)] min-h-176 overflow-hidden rounded-[2rem] p-2.5 sm:p-3">
        <ResizablePanels
          className="h-full"
          resetToken={shellPostureToken}
          storageKey="metis_chat_panel_sizes_v2"
          panels={[
            {
              default: 0.95,
              min: 220,
              children: (
                <SessionsPanel
                  selectedId={selectedId}
                  onSelect={handleSelect}
                  onNewChat={handleNewChat}
                  refreshToken={sessionRefreshToken}
                />
              ),
            },
            {
              default: traceFirstLayout ? 2.9 : 4.25,
              min: 460,
              children: (
                <ChatPanel
                  key={`${queryModeOverride ?? "direct"}:${initialDraft ? "seeded" : "blank"}:${activeIndexPath ?? "no-index"}`}
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
                  initialDraft={initialDraft}
                  onIndexChange={(path, label) => {
                    setActiveIndexPath(path);
                    setActiveIndexLabel(label);
                  }}
                  reconnectState={
                    resumableRun && !isStreamingRag
                      ? {
                          question: resumableRun.question,
                          lastEventId: resumableRun.lastEventId,
                        }
                      : null
                  }
                  onReconnectRun={handleReconnectRag}
                  onDiscardReconnect={handleDiscardResumableRun}
                  getRunSubqueries={getRunSubqueries}
                  modelProvider={modelProvider}
                  modelName={modelName}
                  onModelChange={handleModelChange}
                  composerRef={composerRef}
                  selectedMode={selectedRagMode}
                  onModeChange={handleRagModeChange}
                  onActionApprove={handleActionApprove}
                  onActionDeny={handleActionDeny}
                  agenticMode={agenticMode}
                  agenticModeSaving={agenticModeSaving}
                  agenticModeError={agenticModeError}
                  onAgenticModeChange={handleAgenticModeChange}
                  liveTraceEvents={liveTraceEvents}
                  artifactsEnabled={artifactsEnabled}
                  artifactRuntimeEnabled={artifactRuntimeEnabled}
                />
              ),
            },
            {
              default: traceFirstLayout ? 2.1 : 1.55,
              min: 280,
              children: (
                <EvidencePanel
                  sources={latestSources}
                  runIds={runIdsNewestFirst}
                  latestRunId={latestRunId}
                  selectedMode={selectedRagMode}
                  latestAnswer={latestAnswer}
                  fallback={latestFallback}
                  liveTraceEvents={liveTraceEvents}
                  isStreaming={isStreamingRag}
                  preferredTab={preferredEvidenceTab}
                  postureToken={shellPostureToken}
                />
              ),
            },
          ]}
        />
      </div>
    </PageChrome>
  );
}
