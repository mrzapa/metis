"use client";

import { HudPanel } from "../HudPanel";
import type { SessionSummary } from "@/lib/api";

interface SessionsPanelProps {
  sessions: SessionSummary[];
  currentSessionId?: string | null;
}

const MODE_COLORS: Record<string, string> = {
  rag: "var(--hud-primary)",
  direct: "var(--hud-accent)",
  forecast: "var(--hud-secondary)",
};

export function SessionsPanel({ sessions, currentSessionId }: SessionsPanelProps) {
  return (
    <HudPanel title="Session History" fullHeight>
      {sessions.length === 0 ? (
        <p className="text-[12px]" style={{ color: "var(--hud-text-dim)" }}>
          No sessions found
        </p>
      ) : (
        <div className="max-h-[calc(100vh-14rem)] space-y-2 overflow-y-auto pr-1">
          {sessions.map((s) => {
            const isCurrent = s.session_id === currentSessionId;
            const modeColor = MODE_COLORS[s.mode?.toLowerCase() ?? ""] ?? "var(--hud-text-dim)";
            const date = new Date(s.updated_at);
            const dateLabel = date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
            const timeLabel = date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

            return (
              <div
                key={s.session_id}
                className="rounded px-2 py-2 transition-colors"
                style={{
                  background: isCurrent ? "color-mix(in oklch, white 8%, transparent)" : "transparent",
                  borderLeft: isCurrent ? "2px solid var(--hud-primary)" : "2px solid transparent",
                }}
              >
                <div className="flex items-start justify-between gap-2">
                  <p
                    className="line-clamp-1 text-[13px] font-medium leading-tight"
                    style={{ color: isCurrent ? "var(--hud-primary)" : "var(--hud-text)" }}
                  >
                    {s.title || "Untitled session"}
                  </p>
                  <span
                    className="shrink-0 rounded px-1 py-0.5 text-[10px] font-bold uppercase"
                    style={{ color: modeColor, background: "color-mix(in oklch, white 8%, transparent)" }}
                  >
                    {s.mode || "—"}
                  </span>
                </div>

                {s.summary && (
                  <p
                    className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed"
                    style={{ color: "var(--hud-text-dim)" }}
                  >
                    {s.summary}
                  </p>
                )}

                <div className="mt-1 flex items-center gap-2 text-[10px]" style={{ color: "var(--hud-text-dim)" }}>
                  <span>{dateLabel} {timeLabel}</span>
                  {s.llm_provider && (
                    <>
                      <span>·</span>
                      <span>{s.llm_provider}</span>
                    </>
                  )}
                  {isCurrent && (
                    <>
                      <span>·</span>
                      <span style={{ color: "var(--hud-success)" }}>active</span>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </HudPanel>
  );
}
