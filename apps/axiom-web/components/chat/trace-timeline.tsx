"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Clock } from "lucide-react";
import type { TraceEvent } from "@/lib/api";

// Canonical stage order; unknown stages are appended at the end
const STAGE_ORDER = ["skills", "retrieval", "synthesis", "validation", "grounding"];

const STAGE_LABELS: Record<string, string> = {
  skills: "Skills",
  retrieval: "Retrieval",
  synthesis: "Synthesis",
  validation: "Validation",
  grounding: "Grounding",
};

const STAGE_COLORS: Record<string, string> = {
  skills: "bg-violet-500/15 text-violet-700 dark:text-violet-300",
  retrieval: "bg-blue-500/15 text-blue-700 dark:text-blue-300",
  synthesis: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  validation: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  grounding: "bg-rose-500/15 text-rose-700 dark:text-rose-300",
};

const STAGE_DOT_COLORS: Record<string, string> = {
  skills: "bg-violet-400",
  retrieval: "bg-blue-400",
  synthesis: "bg-emerald-400",
  validation: "bg-amber-400",
  grounding: "bg-rose-400",
};

const PAYLOAD_TRUNCATE_CHARS = 400;

function truncateJson(obj: unknown): { text: string; truncated: boolean } {
  try {
    const full = JSON.stringify(obj, null, 2);
    if (full.length <= PAYLOAD_TRUNCATE_CHARS) {
      return { text: full, truncated: false };
    }
    return { text: full.slice(0, PAYLOAD_TRUNCATE_CHARS) + "\n…", truncated: true };
  } catch {
    return { text: String(obj), truncated: false };
  }
}

function PayloadViewer({ payload }: { payload: Record<string, unknown> }) {
  const [expanded, setExpanded] = useState(false);
  const keys = Object.keys(payload);

  if (keys.length === 0) {
    return <span className="text-muted-foreground italic text-xs">empty</span>;
  }

  const { text: truncated, truncated: wasTruncated } = truncateJson(payload);
  let fullText = "";
  try {
    fullText = JSON.stringify(payload, null, 2);
  } catch {
    fullText = String(payload);
  }

  const display = expanded ? fullText : truncated;

  return (
    <div className="mt-1">
      <pre className="text-xs font-mono bg-muted/50 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all leading-relaxed">
        {display}
      </pre>
      {wasTruncated && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 text-xs text-primary hover:underline flex items-center gap-0.5"
        >
          {expanded ? (
            <>
              <ChevronDown className="size-3" /> Show less
            </>
          ) : (
            <>
              <ChevronRight className="size-3" /> Show full payload
            </>
          )}
        </button>
      )}
    </div>
  );
}

function TraceEventRow({ event }: { event: TraceEvent }) {
  const [open, setOpen] = useState(false);
  const stage = (event.stage || "").toLowerCase();
  const dotColor = STAGE_DOT_COLORS[stage] ?? "bg-muted-foreground";

  const hasPayload =
    event.payload && Object.keys(event.payload).length > 0;

  const ts = event.timestamp
    ? new Date(event.timestamp).toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        fractionalSecondDigits: 3,
      })
    : null;

  return (
    <div className="relative pl-5">
      {/* Timeline dot */}
      <span
        className={`absolute left-0 top-[7px] size-2 rounded-full ${dotColor}`}
      />

      <div className="border rounded-md overflow-hidden">
        <button
          onClick={() => setOpen((v) => !v)}
          className="w-full flex items-start gap-2 px-3 py-2 hover:bg-muted/40 text-left transition-colors"
          disabled={!hasPayload}
          aria-expanded={open}
        >
          <span className="flex-1 min-w-0">
            <span className="font-medium text-xs">{event.event_type || "(unknown)"}</span>
            {event.iteration !== undefined && event.iteration > 0 && (
              <span className="ml-1.5 text-xs text-muted-foreground">
                iter {event.iteration}
              </span>
            )}
          </span>
          <span className="shrink-0 flex items-center gap-1.5 text-xs text-muted-foreground">
            {event.latency_ms != null && (
              <span className="flex items-center gap-0.5">
                <Clock className="size-2.5" />
                {event.latency_ms}ms
              </span>
            )}
            {ts && <span>{ts}</span>}
            {hasPayload && (
              open ? (
                <ChevronDown className="size-3" />
              ) : (
                <ChevronRight className="size-3" />
              )
            )}
          </span>
        </button>

        {open && hasPayload && (
          <div className="px-3 pb-3 pt-1 border-t bg-muted/20">
            <PayloadViewer payload={event.payload} />
          </div>
        )}
      </div>
    </div>
  );
}

function StageGroup({ stage, events }: { stage: string; events: TraceEvent[] }) {
  const [collapsed, setCollapsed] = useState(false);
  const label = STAGE_LABELS[stage] ?? stage.charAt(0).toUpperCase() + stage.slice(1);
  const chipColor =
    STAGE_COLORS[stage] ?? "bg-muted text-muted-foreground";
  const lineColor =
    STAGE_DOT_COLORS[stage] ?? "bg-muted-foreground/30";

  return (
    <div className="space-y-1">
      {/* Stage header */}
      <button
        onClick={() => setCollapsed((v) => !v)}
        className="flex items-center gap-1.5 w-full text-left"
      >
        {collapsed ? (
          <ChevronRight className="size-3 text-muted-foreground" />
        ) : (
          <ChevronDown className="size-3 text-muted-foreground" />
        )}
        <span className={`text-xs font-semibold px-1.5 py-0.5 rounded-sm ${chipColor}`}>
          {label}
        </span>
        <span className="text-xs text-muted-foreground">{events.length}</span>
      </button>

      {!collapsed && (
        <div className="relative pl-2 space-y-1.5">
          {/* Vertical line */}
          <span
            className={`absolute left-[3px] top-0 bottom-0 w-px ${lineColor} opacity-40`}
          />
          {events.map((evt, i) => (
            <TraceEventRow key={evt.event_id ?? `${evt.event_type}-${i}`} event={evt} />
          ))}
        </div>
      )}
    </div>
  );
}

interface TraceTimelineProps {
  events: TraceEvent[];
}

export function TraceTimeline({ events }: TraceTimelineProps) {
  if (events.length === 0) {
    return (
      <p className="py-8 text-center text-xs text-muted-foreground">
        No trace events for this run.
      </p>
    );
  }

  // Group by stage, preserving canonical order
  const grouped = new Map<string, TraceEvent[]>();
  for (const evt of events) {
    const stage = (evt.stage || "unknown").toLowerCase();
    if (!grouped.has(stage)) grouped.set(stage, []);
    grouped.get(stage)!.push(evt);
  }

  const orderedStages: string[] = [
    ...STAGE_ORDER.filter((s) => grouped.has(s)),
    ...[...grouped.keys()].filter((s) => !STAGE_ORDER.includes(s)),
  ];

  return (
    <div className="space-y-3">
      {orderedStages.map((stage) => (
        <StageGroup
          key={stage}
          stage={stage}
          events={grouped.get(stage)!}
        />
      ))}
    </div>
  );
}
