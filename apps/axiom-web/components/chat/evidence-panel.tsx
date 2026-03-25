"use client";

import { useEffect, useMemo, useRef } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { fetchTraceEvents, type RetrievalFallback, type TraceEvent } from "@/lib/api";
import type { EvidenceSource } from "@/lib/chat-types";
import { FileText, List, Activity, FileDown } from "lucide-react";
import { EvidenceSourceCard } from "@/components/chat/evidence-source-card";
import { TraceTimeline } from "@/components/chat/trace-timeline";
import { cn } from "@/lib/utils";
import { useArrowState } from "@/hooks/use-arrow-state";
import { exportChatAnswerAsPptx } from "@/lib/export/pptx";

interface EvidencePanelProps {
  sources: EvidenceSource[];
  runIds: string[];
  latestRunId: string | null;
  selectedMode?: string;
  latestAnswer?: string;
  fallback?: RetrievalFallback | null;
  liveTraceEvents?: TraceEvent[];
  isStreaming?: boolean;
  preferredTab?: "sources" | "trace";
  postureToken?: number;
}

export function EvidencePanel({ sources, runIds, latestRunId, selectedMode, latestAnswer, fallback, liveTraceEvents, isStreaming, preferredTab, postureToken }: EvidencePanelProps) {
  const [selectedRunId, setSelectedRunId] = useArrowState<string>(latestRunId ?? "");
  const [traceEvents, setTraceEvents] = useArrowState<TraceEvent[]>([]);
  const [traceLoading, setTraceLoading] = useArrowState(Boolean(latestRunId));
  const [traceError, setTraceError] = useArrowState<string | null>(null);
  const [activeTab, setActiveTab] = useArrowState(preferredTab ?? "sources");
  const [exportingPptx, setExportingPptx] = useArrowState(false);
  const [exportStatus, setExportStatus] = useArrowState<string | null>(null);
  const exportStatusTimerRef = useRef<number | null>(null);

  // Deduplicated, non-empty run IDs (most-recent first as they appear in the array)
  const availableRunIds = useMemo(() => [...new Set(runIds.filter(Boolean))], [runIds]);
  const showLiveTrace = Boolean(isStreaming && selectedRunId === latestRunId);

  useEffect(() => {
    if (selectedMode !== "Evidence Pack") {
      return;
    }
    queueMicrotask(() => setActiveTab("sources"));
  }, [selectedMode, setActiveTab]);

  useEffect(() => {
    if (!preferredTab) {
      return;
    }
    queueMicrotask(() => setActiveTab(preferredTab));
  }, [postureToken, preferredTab, setActiveTab]);

  useEffect(() => {
    if (!latestRunId) {
      return;
    }
    queueMicrotask(() => setSelectedRunId(latestRunId));
  }, [latestRunId, setSelectedRunId]);

  useEffect(() => {
    queueMicrotask(() => {
      setTraceEvents([]);
      setTraceError(null);
      setTraceLoading(Boolean(selectedRunId));
    });
  }, [selectedRunId, setTraceError, setTraceEvents, setTraceLoading]);

  // Fetch trace events whenever selectedRunId changes (skip while streaming the active run)
  useEffect(() => {
    if (!selectedRunId || showLiveTrace) {
      return;
    }

    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) {
        return;
      }
      setTraceEvents([]);
      setTraceError(null);
      setTraceLoading(true);
    });

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
  }, [selectedRunId, setTraceError, setTraceEvents, setTraceLoading, showLiveTrace]);

  useEffect(() => {
    return () => {
      if (exportStatusTimerRef.current !== null) {
        window.clearTimeout(exportStatusTimerRef.current);
      }
    };
  }, []);

  const showTransientExportStatus = (message: string) => {
    setExportStatus(message);

    if (exportStatusTimerRef.current !== null) {
      window.clearTimeout(exportStatusTimerRef.current);
    }

    exportStatusTimerRef.current = window.setTimeout(() => {
      setExportStatus(null);
      exportStatusTimerRef.current = null;
    }, 2600);
  };

  const canExportPptx = Boolean((latestAnswer ?? "").trim() || sources.length > 0);

  const handleExportPptx = async () => {
    if (!canExportPptx || exportingPptx) {
      return;
    }

    try {
      setExportingPptx(true);
      await exportChatAnswerAsPptx({
        answer: latestAnswer ?? "",
        sources,
        mode: selectedMode,
        title: selectedMode ? `Axiom ${selectedMode} Export` : "Axiom Chat Export",
        fileName: selectedMode ? `axiom-${selectedMode}` : "axiom-chat-export",
      });
      showTransientExportStatus("PPTX downloaded");
    } catch {
      showTransientExportStatus("PPTX export failed");
    } finally {
      setExportingPptx(false);
    }
  };

  return (
    <div className="chat-pane-surface flex h-full min-h-0 flex-col overflow-hidden rounded-[1.9rem]">
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex h-full flex-col">
        {/* Tab bar */}
        <div className="glass-strip shrink-0 border-b border-white/10 px-3 pt-3">
          <TabsList variant="line" className="glass-tab-rail h-9 px-1.5">
            <TabsTrigger
              value="sources"
              className={cn(
                "glass-tab-pill gap-1 text-xs",
                selectedMode === "Evidence Pack" && "font-semibold text-primary"
              )}
            >
              <FileText className="size-3" />
              Sources
            </TabsTrigger>
            <TabsTrigger value="outline" className="glass-tab-pill gap-1 text-xs">
              <List className="size-3" />
              Outline
            </TabsTrigger>
            <TabsTrigger value="trace" className="glass-tab-pill gap-1 text-xs">
              <Activity className="size-3" />
              Trace
            </TabsTrigger>
          </TabsList>
        </div>

        {/* Sources tab */}
        <TabsContent value="sources" className="flex-1 min-h-0 overflow-hidden">
          <ScrollArea className="h-full min-h-0">
            <div className="space-y-2 p-3">
              {fallback?.triggered && (
                <div className="glass-micro-surface rounded-2xl border-amber-500/25 bg-amber-500/12 px-3 py-2">
                  <p className="text-xs font-medium text-amber-800 dark:text-amber-200">
                    Retrieval fallback triggered
                  </p>
                  <p className="mt-1 text-xs text-amber-700/90 dark:text-amber-200/80">
                    {fallback.message || fallback.reason || "The system could not find strong enough evidence to answer confidently."}
                  </p>
                </div>
              )}
              {(selectedMode === "Evidence Pack" || canExportPptx) && (
                <div className="flex items-center justify-end gap-1.5 pb-1">
                  {selectedMode === "Evidence Pack" && (
                    <button
                      type="button"
                      onClick={() => {
                        const data = { answer: latestAnswer ?? "", mode: selectedMode, fallback, sources };
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
                      className="glass-micro-surface rounded-full px-3 py-1 text-[11px] font-medium transition-colors hover:bg-white/10"
                    >
                      Download JSON
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      void handleExportPptx();
                    }}
                    disabled={!canExportPptx || exportingPptx}
                    className="glass-micro-surface inline-flex items-center gap-1 rounded-full px-3 py-1 text-[11px] font-medium transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-55"
                  >
                    <FileDown className="size-3" />
                    {exportingPptx ? "Exporting…" : "Export PPTX"}
                  </button>
                  {exportStatus && (
                    <span className="text-[10px] text-muted-foreground">{exportStatus}</span>
                  )}
                </div>
              )}

              {sources.length === 0 && (
                <p className="glass-micro-surface rounded-[1.2rem] px-4 py-8 text-center text-xs text-muted-foreground">
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
        <TabsContent value="outline" className="flex-1 min-h-0 overflow-hidden">
          <ScrollArea className="h-full min-h-0">
            <div className="p-3.5">
              <p className="glass-micro-surface rounded-[1.2rem] px-4 py-8 text-center text-xs text-muted-foreground">
                Outline will show the structure of the current conversation.
              </p>
            </div>
          </ScrollArea>
        </TabsContent>

        {/* Trace tab */}
        <TabsContent value="trace" className="flex h-full min-h-0 flex-col overflow-hidden">
          {/* Run selector */}
          <div className="glass-strip shrink-0 border-b border-white/10 px-3 py-2">
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
                  className="glass-micro-surface flex-1 rounded px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
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
            <ScrollArea className="h-full min-h-0">
              <div className="p-3.5">
                {!selectedRunId ? (
                  <p className="glass-micro-surface rounded-[1.2rem] px-4 py-8 text-center text-xs text-muted-foreground">
                    Select a run above to view its trace.
                  </p>
                ) : showLiveTrace ? (
                  <>
                    <div className="flex items-center gap-1.5 mb-3">
                      <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      <span className="text-[10px] font-medium text-emerald-600 uppercase tracking-wide">Live</span>
                    </div>
                    {liveTraceEvents && liveTraceEvents.length > 0 ? (
                      <TraceTimeline events={liveTraceEvents} />
                    ) : (
                      <p className="glass-micro-surface rounded-[1.2rem] px-4 py-8 text-center text-xs text-muted-foreground animate-pulse">
                        Waiting for trace events…
                      </p>
                    )}
                  </>
                ) : traceLoading ? (
                  <p className="glass-micro-surface rounded-[1.2rem] px-4 py-8 text-center text-xs text-muted-foreground animate-pulse">
                    Loading trace…
                  </p>
                ) : traceError ? (
                  <p className="glass-micro-surface rounded-[1.2rem] px-4 py-8 text-center text-xs text-destructive">
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
