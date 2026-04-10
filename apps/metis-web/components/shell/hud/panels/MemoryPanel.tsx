"use client";

import { useEffect, useState } from "react";
import { fetchAssistantMemory } from "@/lib/api";
import type { AssistantMemoryEntry, AssistantSnapshot } from "@/lib/api";
import { HudPanel, HudBar } from "../HudPanel";
import { Loader2 } from "lucide-react";

interface MemoryPanelProps {
  snapshot: AssistantSnapshot | null;
}

export function MemoryPanel({ snapshot }: MemoryPanelProps) {
  const [entries, setEntries] = useState<AssistantMemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAssistantMemory(50)
      .then(setEntries)
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, []);

  const maxEntries = snapshot?.policy.max_memory_entries ?? 100;
  const maxPlaybooks = snapshot?.policy.max_playbooks ?? 20;
  const maxBrainLinks = snapshot?.policy.max_brain_links ?? 50;

  const playbookCount = snapshot?.playbooks.length ?? 0;
  const brainLinkCount = snapshot?.brain_links.length ?? 0;

  const byKind = entries.reduce<Record<string, AssistantMemoryEntry[]>>(
    (acc: Record<string, AssistantMemoryEntry[]>, e: AssistantMemoryEntry) => {
      const k = e.kind || "general";
      if (!acc[k]) acc[k] = [];
      acc[k].push(e);
      return acc;
    },
    {},
  );

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {/* Capacity */}
      <HudPanel title="What I Remember — Capacity">
        <div className="space-y-4">
          <HudBar value={entries.length} max={maxEntries} label="Memory entries" />
          <HudBar value={playbookCount} max={maxPlaybooks} label="Playbooks" />
          <HudBar value={brainLinkCount} max={maxBrainLinks} label="Brain links" />
        </div>

        {/* Kind breakdown */}
        {Object.keys(byKind).length > 0 && (
          <div className="mt-4 space-y-2">
            <p className="text-[10px] uppercase tracking-[0.15em]" style={{ color: "var(--hud-text-dim)" }}>
              By category
            </p>
            {(Object.entries(byKind) as [string, AssistantMemoryEntry[]][]).map(([kind, items]) => (
              <div key={kind} className="flex items-center justify-between text-[12px]">
                <span className="font-medium uppercase tracking-wide" style={{ color: "var(--hud-primary)" }}>
                  {kind}
                </span>
                <span className="tabular-nums" style={{ color: "var(--hud-text-dim)" }}>
                  {items.length}
                </span>
              </div>
            ))}
          </div>
        )}
      </HudPanel>

      {/* Entry list */}
      <HudPanel title="Memory Entries" fullHeight>
        {loading ? (
          <div className="flex items-center gap-2" style={{ color: "var(--hud-text-dim)" }}>
            <Loader2 className="size-3.5 animate-spin" />
            <span className="text-[12px]">Loading…</span>
          </div>
        ) : entries.length === 0 ? (
          <p className="text-[12px]" style={{ color: "var(--hud-text-dim)" }}>
            No memory entries yet
          </p>
        ) : (
          <div className="max-h-80 space-y-3 overflow-y-auto pr-1">
            {entries.map((e: AssistantMemoryEntry) => (
              <div
                key={e.entry_id}
                className="rounded px-2 py-1.5"
                style={{ background: "color-mix(in oklch, white 8%, transparent)" }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className="text-[10px] font-bold uppercase tracking-wide"
                    style={{ color: "var(--hud-primary)" }}
                  >
                    {e.kind || "general"}
                  </span>
                  <span className="text-[10px] tabular-nums" style={{ color: "var(--hud-text-dim)" }}>
                    {e.summary.length} chars
                  </span>
                </div>
                {e.title && (
                  <p className="mt-0.5 text-[12px] font-medium leading-tight" style={{ color: "var(--hud-text)" }}>
                    {e.title}
                  </p>
                )}
                <p
                  className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed"
                  style={{ color: "var(--hud-text-dim)" }}
                >
                  {e.summary}
                </p>
              </div>
            ))}
          </div>
        )}
      </HudPanel>
    </div>
  );
}
