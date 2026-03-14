"use client";

import { useEffect, useMemo, useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { EvidenceSource, TraceEvent } from "@/lib/api";
import { fetchTraceEvents } from "@/lib/api";
import { FileText, List, Activity } from "lucide-react";
import { EvidenceSourceCard } from "@/components/chat/evidence-source-card";
import { TraceTimeline } from "@/components/chat/trace-timeline";
import { cn } from "@/lib/utils";

interface EvidencePanelProps {
  sources: EvidenceSource[];
  runIds: string[];
  latestRunId: string | null;
  selectedMode?: string;
  latestAnswer?: string;
}

export function EvidencePanel({ sources, runIds, latestRunId, selectedMode, latestAnswer }: EvidencePanelProps) {
  const [selectedRunId, setSelectedRunId] = useState<string>(latestRunId ?? "");
  const [syncedLatestRunId, setSyncedLatestRunId] = useState<string | null>(latestRunId);
  const [traceEvents, setTraceEvents] = useState<TraceEvent[]>([]);
  const [traceLoading, setTraceLoading] = useState(Boolean(latestRunId));
  const [traceError, setTraceError] = useState<string | null>(null);
  const [traceStateRunId, setTraceStateRunId] = useState<string>(latestRunId ?? "");
  const [activeTab, setActiveTab] = useState("sources");
  const [syncedMode, setSyncedMode] = useState(selectedMode);

  if (selectedMode !== syncedMode) {
    setSyncedMode(selectedMode);
    if (selectedMode === "Evidence Pack") {
      setActiveTab("sources");
    }
  }

  if (latestRunId !== syncedLatestRunId) {
    setSyncedLatestRunId(latestRunId);
    if (latestRunId) {
      setSelectedRunId(latestRunId);
    }
  }

  if (selectedRunId !== traceStateRunId) {
    setTraceStateRunId(selectedRunId);
    setTraceEvents([]);
    setTraceError(null);
    setTraceLoading(Boolean(selectedRunId));
  }

  // Deduplicated, non-empty run IDs (most-recent first as they appear in the array)
  const availableRunIds = useMemo(() => [...new Set(runIds.filter(Boolean))], [runIds]);

  // Fetch trace events whenever selectedRunId changes
  useEffect(() => {
    if (!selectedRunId) {
      return;
    }
    let cancelled = false;
    fetchTraceEvents(selectedRunId)
      .then((events) => {
        if (!cancelled) {
          setTraceEvents(events);
          setTraceLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setTraceError(err instanceof Error ? err.message : "Failed to load trace");
          setTraceLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRunId]);

  return (
    <div className="flex h-full flex-col">
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex h-full flex-col">
        {/* Tab bar */}
        <div className="shrink-0 border-b px-3 pt-2">
          <TabsList variant="line" className="h-8">
            <TabsTrigger
              value="sources"
              className={cn(
                "gap-1 text-xs",
                selectedMode === "Evidence Pack" && "font-semibold text-primary"
              )}
            >
              <FileText className="size-3" />
              Sources
            </TabsTrigger>
            <TabsTrigger value="outline" className="gap-1 text-xs">
              <List className="size-3" />
              Outline
            </TabsTrigger>
            <TabsTrigger value="trace" className="gap-1 text-xs">
              <Activity className="size-3" />
              Trace
            </TabsTrigger>
          </TabsList>
        </div>

        {/* Sources tab */}
        <TabsContent value="sources" className="flex-1 overflow-hidden">
          <ScrollArea className="h-full">
            <div className="space-y-2 p-3">
              {selectedMode === "Evidence Pack" && sources.length > 0 && (
                <div className="flex justify-end pb-1">
                  <button
                    type="button"
                    onClick={() => {
                      const data = { answer: latestAnswer ?? "", sources };
                      const blob = new Blob([JSON.stringify(data, null, 2)], {
                        type: "application/json",
                      });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = "evidence-pack.json";
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                    className="rounded border px-2 py-1 text-[11px] font-medium hover:bg-muted transition-colors"
                  >
                    Download JSON
                  </button>
                </div>
              )}

              {sources.length === 0 && (
                <p className="py-8 text-center text-xs text-muted-foreground">
                  No sources yet. Sources will appear here when the assistant
                  references documents.
                </p>
              )}

              {sources.map((src) => (
                <EvidenceSourceCard key={src.sid} source={src} />
              ))}
            </div>
          </ScrollArea>
        </TabsContent>

        {/* Outline tab */}
        <TabsContent value="outline" className="flex-1 overflow-hidden">
          <ScrollArea className="h-full">
            <div className="p-3">
              <p className="py-8 text-center text-xs text-muted-foreground">
                Outline will show the structure of the current conversation.
              </p>
            </div>
          </ScrollArea>
        </TabsContent>

        {/* Trace tab */}
        <TabsContent value="trace" className="flex h-full flex-col overflow-hidden">
          {/* Run selector */}
          <div className="shrink-0 border-b px-3 py-2">
            <div className="flex items-center gap-2">
              <label htmlFor="run-selector" className="text-xs text-muted-foreground whitespace-nowrap">
                Run
              </label>
              {availableRunIds.length === 0 ? (
                <span className="text-xs text-muted-foreground italic">No runs yet</span>
              ) : (
                <select
                  id="run-selector"
                  value={selectedRunId}
                  onChange={(e) => setSelectedRunId(e.target.value)}
                  className="flex-1 text-xs rounded border bg-background px-2 py-1 text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="">Select a run…</option>
                  {availableRunIds.map((id, idx) => (
                    <option key={id} value={id}>
                      {id === latestRunId
                        ? `Latest — ${id.slice(0, 8)}…`
                        : `Run ${availableRunIds.length - idx} — ${id.slice(0, 8)}…`}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>

          {/* Timeline content */}
          <div className="flex-1 overflow-hidden">
            <ScrollArea className="h-full">
              <div className="p-3">
                {!selectedRunId ? (
                  <p className="py-8 text-center text-xs text-muted-foreground">
                    Select a run above to view its trace.
                  </p>
                ) : traceLoading ? (
                  <p className="py-8 text-center text-xs text-muted-foreground animate-pulse">
                    Loading trace…
                  </p>
                ) : traceError ? (
                  <p className="py-8 text-center text-xs text-destructive">
                    {traceError}
                  </p>
                ) : (
                  <TraceTimeline events={traceEvents} />
                )}
              </div>
            </ScrollArea>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
