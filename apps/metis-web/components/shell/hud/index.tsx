"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { fetchSessions } from "@/lib/api";
import type { AssistantSnapshot, CompanionActivityEvent, SessionSummary } from "@/lib/api";
import { HUD_VARS } from "./hud-themes";
import { HudTopBar, type HudTabId } from "./HudTopBar";
import { IdentityPanel } from "./panels/IdentityPanel";
import { MemoryPanel } from "./panels/MemoryPanel";
import { SkillsPanel } from "./panels/SkillsPanel";
import { SessionsPanel as HudSessionsPanel } from "./panels/SessionsPanel";
import { HealthPanel } from "./panels/HealthPanel";

interface HermesHudProps {
  snapshot: AssistantSnapshot | null;
  thoughtLog: CompanionActivityEvent[];
  sessionId?: string | null;
  onClose: () => void;
}

const STORAGE_BOOTED_KEY = "hud-booted";

export function HermesHud({ snapshot, thoughtLog, sessionId, onClose }: HermesHudProps) {
  const [activeTab, setActiveTab] = useState<HudTabId>("identity");
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [refreshTick, setRefreshTick] = useState(0);
  const [booted, setBooted] = useState(() => {
    if (typeof sessionStorage === "undefined") return true;
    return sessionStorage.getItem(STORAGE_BOOTED_KEY) === "true";
  });
  const rootRef = useRef<HTMLDivElement>(null);

  // Boot animation — once per browser session
  useEffect(() => {
    if (!booted) {
      const t = setTimeout(() => {
        setBooted(true);
        sessionStorage.setItem(STORAGE_BOOTED_KEY, "true");
      }, 1400);
      return () => clearTimeout(t);
    }
  }, [booted]);

  // Load sessions
  useEffect(() => {
    fetchSessions()
      .then(setSessions)
      .catch(() => setSessions([]));
  }, [refreshTick]);

  // Keyboard shortcuts
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      const tabKeys: Record<string, HudTabId> = {
        "1": "identity", "2": "memory", "3": "skills", "4": "sessions", "5": "health",
      };
      if (tabKeys[e.key]) { setActiveTab(tabKeys[e.key]); return; }
      if (e.key === "r" || e.key === "R") { setRefreshTick((n: number) => n + 1); return; }
      if (e.key === "Escape") { onClose(); return; }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const handleRefresh = useCallback(() => setRefreshTick((n: number) => n + 1), []);

  /**
   * The HUD is a large floating liquid-glass panel that sits over the page.
   * It does NOT cover the full viewport — inset margins leave the constellation
   * visible around the edges, and backdrop-filter lets it bleed through the glass.
   */
  const overlay = (
    <div
      ref={rootRef}
      className="home-liquid-glass fixed inset-3 z-[9998] flex flex-col overflow-hidden rounded-[2rem] sm:inset-5"
      style={HUD_VARS as Record<string, string>}
    >
      {!booted ? (
        <BootScreen />
      ) : (
        <>
          <HudTopBar
            activeTab={activeTab}
            onTabChange={setActiveTab}
            onRefresh={handleRefresh}
            onClose={onClose}
          />
          <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">
            <TabContent
              tab={activeTab}
              snapshot={snapshot}
              thoughtLog={thoughtLog}
              sessions={sessions}
              sessionId={sessionId}
            />
          </div>
        </>
      )}
    </div>
  );

  if (typeof document === "undefined") return null;
  return createPortal(overlay, document.body);
}

// ── Boot screen ──────────────────────────────────────────────────────────────

function BootScreen() {
  const [dots, setDots] = useState("");

  useEffect(() => {
    const id = setInterval(
      () => setDots((d: string) => (d.length >= 3 ? "" : d + ".")),
      320,
    );
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6">
      <div className="text-center">
        <p
          className="font-display text-[48px] font-bold tracking-[0.06em]"
          style={{
            background: "linear-gradient(135deg, var(--hud-primary) 0%, var(--hud-accent) 55%, var(--hud-primary) 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          METIS
        </p>
        <p className="mt-2 text-[11px] uppercase tracking-[0.35em] text-muted-foreground">
          HUD initialising{dots}
        </p>
      </div>

      <div
        className="h-px w-48 overflow-hidden"
        style={{ background: "color-mix(in oklch, white 8%, transparent)" }}
      >
        <div
          className="h-full"
          style={{
            background: "linear-gradient(90deg, var(--hud-primary), var(--hud-accent))",
            animation: "hud-boot-bar 1.3s ease-out forwards",
          }}
        />
      </div>

      <style>{`
        @keyframes hud-boot-bar { from { width: 0% } to { width: 100% } }
      `}</style>
    </div>
  );
}

// ── Tab content router ────────────────────────────────────────────────────────

interface TabContentProps {
  tab: HudTabId;
  snapshot: AssistantSnapshot | null;
  thoughtLog: CompanionActivityEvent[];
  sessions: SessionSummary[];
  sessionId?: string | null;
}

function TabContent({ tab, snapshot, thoughtLog, sessions, sessionId }: TabContentProps) {
  switch (tab) {
    case "identity":
      return <IdentityPanel snapshot={snapshot} sessions={sessions} thoughtLog={thoughtLog} sessionId={sessionId} />;
    case "memory":
      return <MemoryPanel snapshot={snapshot} />;
    case "skills":
      return <SkillsPanel snapshot={snapshot} />;
    case "sessions":
      return <HudSessionsPanel sessions={sessions} currentSessionId={sessionId} />;
    case "health":
      return <HealthPanel snapshot={snapshot} />;
    default:
      return null;
  }
}
