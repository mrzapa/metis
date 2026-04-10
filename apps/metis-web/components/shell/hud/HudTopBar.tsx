"use client";

import { X, RefreshCw } from "lucide-react";

export type HudTabId = "identity" | "memory" | "skills" | "sessions" | "health";

const TABS: { id: HudTabId; label: string; key: string }[] = [
  { id: "identity", label: "Identity", key: "1" },
  { id: "memory",   label: "Memory",   key: "2" },
  { id: "skills",   label: "Skills",   key: "3" },
  { id: "sessions", label: "Sessions", key: "4" },
  { id: "health",   label: "Health",   key: "5" },
];

interface HudTopBarProps {
  activeTab: HudTabId;
  onTabChange: (tab: HudTabId) => void;
  onRefresh: () => void;
  onClose: () => void;
}

export function HudTopBar({ activeTab, onTabChange, onRefresh, onClose }: HudTopBarProps) {
  return (
    <div
      className="shrink-0 border-b px-5 py-3"
      style={{ borderColor: "color-mix(in oklch, white 9%, transparent)" }}
    >
      <div className="flex items-center gap-4">
        {/* Wordmark */}
        <span
          className="shrink-0 font-display text-[13px] font-bold uppercase tracking-[0.22em]"
          style={{
            background: "linear-gradient(90deg, var(--hud-primary), var(--hud-accent))",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          METIS HUD
        </span>

        {/* Tab strip */}
        <div className="glass-tab-rail flex flex-1 items-center gap-0.5 overflow-x-auto px-1 py-1">
          {TABS.map((tab) => {
            const active = tab.id === activeTab;
            return (
              <button
                key={tab.id}
                type="button"
                data-active={active || undefined}
                onClick={() => onTabChange(tab.id)}
                className="glass-tab-pill shrink-0 rounded-xl px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.1em] text-muted-foreground transition-all"
              >
                <span className="opacity-40">{tab.key} </span>
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Controls */}
        <div className="flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            onClick={onRefresh}
            title="Refresh (R)"
            className="flex size-8 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-white/8 hover:text-foreground"
          >
            <RefreshCw className="size-3.5" />
          </button>
          <button
            type="button"
            onClick={onClose}
            title="Close (Esc)"
            className="flex size-8 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-white/8 hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>
      </div>

      {/* Hint strip */}
      <p className="mt-2 text-[10px] text-muted-foreground/50">
        1–5 tabs · R refresh · Esc close
      </p>
    </div>
  );
}

export { TABS };
