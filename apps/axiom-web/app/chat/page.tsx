"use client";

import { useCallback, useEffect, useState } from "react";
import { ResizablePanels } from "@/components/chat/resizable-panels";
import { SessionsPanel } from "@/components/chat/sessions-panel";
import { ChatPanel } from "@/components/chat/chat-panel";
import { EvidencePanel } from "@/components/chat/evidence-panel";
import { fetchSession } from "@/lib/api";
import type { SessionMessage, EvidenceSource } from "@/lib/api";

export default function ChatPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [sources, setSources] = useState<EvidenceSource[]>([]);
  const [sessionTitle, setSessionTitle] = useState<string | null>(null);

  const loadSession = useCallback(async (id: string) => {
    try {
      const detail = await fetchSession(id);
      setMessages(detail.messages);
      setSessionTitle(detail.summary.title || null);
      // Aggregate all sources from assistant messages
      const allSources = detail.messages.flatMap((m) => m.sources);
      setSources(allSources);
    } catch {
      setMessages([]);
      setSources([]);
      setSessionTitle(null);
    }
  }, []);

  const handleSelect = useCallback(
    (id: string) => {
      setSelectedId(id);
      loadSession(id);
    },
    [loadSession],
  );

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
              />
            ),
          },
          {
            default: 3,
            min: 400,
            children: (
              <ChatPanel messages={messages} sessionTitle={sessionTitle} />
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
