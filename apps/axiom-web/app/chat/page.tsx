"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ResizablePanels } from "@/components/chat/resizable-panels";
import { SessionsPanel } from "@/components/chat/sessions-panel";
import { ChatPanel } from "@/components/chat/chat-panel";
import { EvidencePanel } from "@/components/chat/evidence-panel";
import { fetchSession, fetchSettings, queryDirect, queryRag } from "@/lib/api";
import type { SessionMessage, EvidenceSource, SessionSummary } from "@/lib/api";

export default function ChatPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [sources, setSources] = useState<EvidenceSource[]>([]);
  const [sessionMeta, setSessionMeta] = useState<SessionSummary | null>(null);
  const [loadingSession, setLoadingSession] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [activeIndexPath, setActiveIndexPath] = useState<string | null>(null);
  const [activeIndexLabel, setActiveIndexLabel] = useState<string | null>(null);
  const [queryModeOverride, setQueryModeOverride] = useState<"rag" | null>(null);
  const settingsRef = useRef<Record<string, unknown> | null>(null);
  const [modelProvider, setModelProvider] = useState<string | null>(null);
  const [modelName, setModelName] = useState<string | null>(null);

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

  const loadSession = useCallback(async (id: string) => {
    setLoadingSession(true);
    setSessionError(null);
    try {
      const detail = await fetchSession(id);
      setMessages(detail.messages);
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
  }, []);

  const handleSelect = useCallback(
    (id: string) => {
      setSelectedId(id);
      loadSession(id);
    },
    [loadSession],
  );

  const handleDirectSend = useCallback(async (prompt: string) => {
    setIsSending(true);
    const userMsg: SessionMessage = {
      role: "user",
      content: prompt,
      ts: new Date().toISOString(),
      run_id: "",
      sources: [],
    };
    setMessages((prev) => [...prev, userMsg]);
    try {
      if (!settingsRef.current) {
        settingsRef.current = await fetchSettings();
      }
      const result = await queryDirect(prompt, settingsRef.current);
      const assistantMsg: SessionMessage = {
        role: "assistant",
        content: result.answer_text,
        ts: new Date().toISOString(),
        run_id: result.run_id,
        sources: [],
        llm_provider: result.llm_provider,
        llm_model: result.llm_model,
        query_mode: "direct",
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errorMsg: SessionMessage = {
        role: "assistant",
        content: err instanceof Error ? err.message : "An error occurred.",
        ts: new Date().toISOString(),
        run_id: "",
        sources: [],
        query_mode: "direct",
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsSending(false);
    }
  }, []);

  const handleRagSend = useCallback(async (question: string) => {
    if (!activeIndexPath) return;
    setIsSending(true);
    const userMsg: SessionMessage = {
      role: "user",
      content: question,
      ts: new Date().toISOString(),
      run_id: "",
      sources: [],
    };
    setMessages((prev) => [...prev, userMsg]);
    try {
      if (!settingsRef.current) {
        settingsRef.current = await fetchSettings();
      }
      const result = await queryRag(activeIndexPath, question, settingsRef.current);
      const assistantMsg: SessionMessage = {
        role: "assistant",
        content: result.answer_text,
        ts: new Date().toISOString(),
        run_id: result.run_id,
        sources: result.sources,
        query_mode: "rag",
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setSources(result.sources);
    } catch (err) {
      const errorMsg: SessionMessage = {
        role: "assistant",
        content: err instanceof Error ? err.message : "An error occurred.",
        ts: new Date().toISOString(),
        run_id: "",
        sources: [],
        query_mode: "rag",
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsSending(false);
    }
  }, [activeIndexPath]);

  const handleNewChat = useCallback(() => {
    setSelectedId(null);
    setMessages([]);
    setSources([]);
    setSessionMeta(null);
    setLoadingSession(false);
    setSessionError(null);
  }, []);

  // Keyboard shortcut: Cmd/Ctrl+K focuses search
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        const searchInput = document.querySelector<HTMLInputElement>(
          'input[aria-label="Search sessions"]',
        );
        searchInput?.focus();
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
              />
            ),
          },
          {
            default: 1.5,
            min: 240,
            children: <EvidencePanel sources={sources} />,
          },
        ]}
      />
    </main>
  );
}
