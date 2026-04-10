"use client";

import { HudPanel, HudStat } from "../HudPanel";
import type { AssistantSnapshot, CompanionActivityEvent, SessionSummary } from "@/lib/api";

const RAG_MODES = ["Q&A", "Summary", "Tutor", "Research", "Evidence Pack", "Knowledge Search"];
const COMPANION_TOOLS = ["Reflection", "Autonomous Research", "Quick-Ask", "Atlas Memory"];

interface IdentityPanelProps {
  snapshot: AssistantSnapshot | null;
  sessions: SessionSummary[];
  thoughtLog: CompanionActivityEvent[];
  sessionId?: string | null;
}

export function IdentityPanel({ snapshot, sessions, thoughtLog, sessionId }: IdentityPanelProps) {
  const model = snapshot?.runtime.model ?? "—";
  const provider = snapshot?.runtime.provider ?? "—";
  const modelDisplay = model.length > 28 ? `${model.slice(0, 27)}…` : model;
  const contextLen = snapshot?.runtime.local_gguf_context_length;

  // Count activity events by type for "How I'm operating" summary
  const eventCounts = thoughtLog.reduce<Record<string, number>>((acc, ev) => {
    acc[ev.source] = (acc[ev.source] ?? 0) + 1;
    return acc;
  }, {});

  const memoryCount = snapshot?.memory.length ?? 0;
  const playbookCount = snapshot?.playbooks.length ?? 0;
  const brainLinkCount = snapshot?.brain_links.length ?? 0;

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {/* Designation */}
      <HudPanel title="Designation">
        <div className="space-y-3">
          <div>
            <p
              className="text-[28px] font-bold leading-none tracking-tight"
              style={{
                background: "linear-gradient(90deg, var(--hud-primary), var(--hud-accent))",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              {snapshot?.identity.name ?? "METIS"}
            </p>
            <p className="mt-1 text-[11px] uppercase tracking-[0.18em]" style={{ color: "var(--hud-text-dim)" }}>
              {snapshot?.identity.archetype ?? "companion"}
            </p>
          </div>

          <div className="space-y-1">
            <Row label="Substrate" value={`${provider} / ${modelDisplay}`} />
            {contextLen ? <Row label="Context window" value={`${contextLen.toLocaleString()} tokens`} /> : null}
            <Row
              label="Runtime"
              value={
                snapshot?.status.runtime_source === "dedicated_local"
                  ? "Dedicated local"
                  : "Companion overlay"
              }
            />
            {sessionId && (
              <Row label="Session" value={sessionId.slice(0, 12) + "…"} mono />
            )}
          </div>
        </div>
      </HudPanel>

      {/* What I Know */}
      <HudPanel title="What I Know">
        <div className="grid grid-cols-2 gap-x-4 gap-y-3">
          <HudStat value={sessions.length} label="Sessions" />
          <HudStat value={RAG_MODES.length} label="RAG modes" />
          <HudStat value={memoryCount} label="Memories" />
          <HudStat value={playbookCount} label="Playbooks" />
          <HudStat value={brainLinkCount} label="Brain links" accent />
          <HudStat value={COMPANION_TOOLS.length} label="Tools" accent />
        </div>

        <div className="mt-3 space-y-1">
          <p className="text-[10px] uppercase tracking-[0.15em]" style={{ color: "var(--hud-text-dim)" }}>
            Available RAG modes
          </p>
          <div className="flex flex-wrap gap-1">
            {RAG_MODES.map((m) => (
              <span
                key={m}
                className="rounded px-1.5 py-0.5 text-[10px] font-medium"
                style={{ background: "color-mix(in oklch, white 8%, transparent)", color: "var(--hud-primary)" }}
              >
                {m}
              </span>
            ))}
          </div>
        </div>
      </HudPanel>

      {/* Recent Activity */}
      <HudPanel title="My Rhythm">
        {thoughtLog.length === 0 ? (
          <p className="text-[12px]" style={{ color: "var(--hud-text-dim)" }}>
            No recent activity
          </p>
        ) : (
          <div className="space-y-2">
            {thoughtLog.slice(0, 6).map((ev, i) => (
              <div key={i} className="flex items-start gap-2">
                <span
                  className="mt-0.5 size-1.5 shrink-0 rounded-full"
                  style={{ background: sourceColor(ev.source) }}
                />
                <div className="min-w-0">
                  <p className="truncate text-[12px] leading-tight" style={{ color: "var(--hud-text)" }}>
                    {ev.summary}
                  </p>
                  <p className="text-[10px]" style={{ color: "var(--hud-text-dim)" }}>
                    {ev.source}
                    {ev.state === "running" ? " ▸" : ev.state === "completed" ? " ✓" : ev.state === "error" ? " ⚠" : ""}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}

        {Object.keys(eventCounts).length > 0 && (
          <div className="mt-3 space-y-1.5">
            <p className="text-[10px] uppercase tracking-[0.15em]" style={{ color: "var(--hud-text-dim)" }}>
              Event breakdown
            </p>
            {Object.entries(eventCounts).map(([src, count]) => (
              <div key={src} className="flex items-center justify-between text-[11px]">
                <span style={{ color: sourceColor(src) }}>{src}</span>
                <span className="tabular-nums" style={{ color: "var(--hud-text-dim)" }}>{count}</span>
              </div>
            ))}
          </div>
        )}
      </HudPanel>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="shrink-0 text-[11px] uppercase tracking-[0.1em]" style={{ color: "var(--hud-text-dim)" }}>
        {label}
      </span>
      <span
        className={`truncate text-right text-[12px] ${mono ? "font-mono" : ""}`}
        style={{ color: "var(--hud-text)" }}
      >
        {value}
      </span>
    </div>
  );
}

function sourceColor(source: string): string {
  if (source.includes("rag")) return "#60a5fa";
  if (source.includes("index") || source.includes("build")) return "#34d399";
  if (source.includes("research") || source.includes("autonomous")) return "#a78bfa";
  if (source.includes("reflect")) return "#fbbf24";
  return "var(--hud-primary)";
}
