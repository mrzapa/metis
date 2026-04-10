"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface HudPanelProps {
  title: string;
  children: ReactNode;
  className?: string;
  fullHeight?: boolean;
}

export function HudPanel({ title, children, className, fullHeight }: HudPanelProps) {
  return (
    <div
      className={cn(
        "glass-micro-surface rounded-2xl p-3.5",
        "border-l-2",
        fullHeight && "flex flex-col",
        className,
      )}
      style={{ borderLeftColor: "color-mix(in oklch, var(--primary) 55%, transparent)" }}
    >
      <p
        className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.18em]"
        style={{ color: "var(--hud-primary)" }}
      >
        {title}
      </p>
      <div className={cn(fullHeight && "flex-1 overflow-auto")}>{children}</div>
    </div>
  );
}

/** Large number stat with label — e.g. "42 / Sessions" */
export function HudStat({
  value,
  label,
  accent,
}: {
  value: string | number;
  label: string;
  accent?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span
        className="text-[22px] font-bold leading-none tabular-nums"
        style={{ color: accent ? "var(--hud-accent)" : "var(--hud-primary)" }}
      >
        {value}
      </span>
      <span
        className="text-[11px] uppercase tracking-[0.12em]"
        style={{ color: "var(--hud-text-dim)" }}
      >
        {label}
      </span>
    </div>
  );
}

/** Horizontal capacity bar that turns amber/red as it fills */
export function HudBar({
  value,
  max,
  label,
}: {
  value: number;
  max: number;
  label?: string;
}) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  const barColor =
    pct >= 90 ? "var(--hud-error)" : pct >= 70 ? "var(--hud-warning)" : "var(--hud-success)";

  return (
    <div className="space-y-1">
      {label && (
        <div className="flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-[0.1em]" style={{ color: "var(--hud-text-dim)" }}>
            {label}
          </span>
          <span className="text-[11px] tabular-nums" style={{ color: "var(--hud-text-dim)" }}>
            {value} / {max}
          </span>
        </div>
      )}
      <div
        className="h-[4px] w-full overflow-hidden rounded-full"
        style={{ background: "color-mix(in oklch, var(--primary) 12%, transparent)" }}
      >
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: barColor }}
        />
      </div>
    </div>
  );
}
