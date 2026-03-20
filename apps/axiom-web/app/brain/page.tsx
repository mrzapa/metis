"use client";

/**
 * Brain Graph page - visualises indexes, sessions, assistant memory, and
 * relationships as an interactive 3D force-directed graph.
 */

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import {
  type BrainGraphData,
  type BrainNode,
  type BrainRenderMode,
  type BrainScope,
  ALL_BRAIN_SCOPES,
  scopeFromMetadata,
} from "@/components/brain/brain-graph";
import { buildBrainSceneGraph } from "@/components/brain/brain-graph-view-model";
import { PageChrome } from "@/components/shell/page-chrome";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fetchBrainGraph } from "@/lib/api";

const BrainGraph3D = dynamic(() => import("@/components/brain/brain-graph-3d"), {
  ssr: false,
  loading: () => (
    <div className="flex flex-1 items-center justify-center">
      <span className="animate-pulse text-sm text-muted-foreground">
        Initialising 3D engine...
      </span>
    </div>
  ),
});

const SCOPE_META: Record<
  BrainScope,
  { label: string; description: string; swatch: string; lineColor: string; dashed?: boolean }
> = {
  workspace: {
    label: "Workspace",
    description: "Indexes, sessions, and structural categories.",
    swatch: "var(--color-border)",
    lineColor: "var(--color-border)",
  },
  assistant_self: {
    label: "Axiom Self",
    description: "The companion's identity and self-structure.",
    swatch: "var(--color-chart-3)",
    lineColor: "var(--color-chart-3)",
  },
  assistant_learned: {
    label: "Assistant-Learned",
    description: "Memories, playbooks, and learned links.",
    swatch: "var(--color-chart-4)",
    lineColor: "var(--color-chart-4)",
    dashed: true,
  },
};

function normalizeBrainGraph(graph: Awaited<ReturnType<typeof fetchBrainGraph>>): BrainGraphData {
  return {
    nodes: graph.nodes.map((node) => ({
      ...node,
      metadata: node.metadata ?? {},
    })),
    edges: graph.edges.map((edge) => ({
      ...edge,
      metadata: edge.metadata ?? {},
    })),
  } as BrainGraphData;
}

function formatNodeValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.length > 0 ? value.join(", ") : "—";
  }
  if (typeof value === "object" && value !== null) {
    try {
      return JSON.stringify(value);
    } catch {
      return "—";
    }
  }
  return String(value);
}

function GraphInspectorPanel({
  node,
  visibleStats,
  nodeCount,
  edgeCount,
  activeScopeCount,
  onClose,
}: {
  node: BrainNode | null;
  visibleStats: { nodes: number; edges: number };
  nodeCount: number;
  edgeCount: number;
  activeScopeCount: number;
  onClose?: () => void;
}) {
  const scope = node ? scopeFromMetadata(node.metadata) : null;
  const metaEntries = node
    ? Object.entries(node.metadata).filter(
        ([key, value]) =>
          key !== "scope" &&
          value !== "" &&
          value !== null &&
          value !== undefined &&
          !(Array.isArray(value) && value.length === 0),
      )
    : [];

  return (
    <aside className="glass-panel w-full overflow-hidden rounded-[1.6rem] p-4 text-sm shadow-2xl shadow-black/25">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="text-[11px] font-medium uppercase tracking-[0.24em] text-muted-foreground">
            {node ? "Node inspector" : "Graph snapshot"}
          </p>
          <h3 className="truncate font-display text-lg font-semibold tracking-[-0.03em] text-foreground">
            {node ? node.label : "Select a node to inspect its metadata"}
          </h3>
          <p className="text-xs leading-5 text-muted-foreground">
            {node
              ? `Connected in the ${scope ? SCOPE_META[scope].label.toLowerCase() : "workspace"} scope.`
              : "Use the filters to tighten the graph, then click a node to pin its details here."}
          </p>
        </div>

        {node && onClose ? (
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-border/70 px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground"
            aria-label="Close detail panel"
          >
            Close
          </button>
        ) : null}
      </div>

      {node ? (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            <span className="rounded-full border border-border/70 bg-black/10 px-2.5 py-1 text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              {SCOPE_META[scope ?? "workspace"].label}
            </span>
            <span className="rounded-full border border-border/70 bg-black/10 px-2.5 py-1 text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              {node.node_type}
            </span>
            <span className="rounded-full border border-border/70 bg-black/10 px-2.5 py-1 text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              {metaEntries.length} metadata fields
            </span>
          </div>

          <dl className="space-y-2 text-xs leading-5">
            <div className="flex gap-2">
              <dt className="shrink-0 text-muted-foreground">ID</dt>
              <dd className="min-w-0 break-all font-mono text-[11px] text-foreground">
                {node.node_id}
              </dd>
            </div>
            {metaEntries.map(([key, value]) => (
              <div key={key} className="flex gap-2">
                <dt className="shrink-0 text-muted-foreground capitalize">
                  {key.replace(/_/g, " ")}
                </dt>
                <dd className="min-w-0 break-words text-foreground">
                  {formatNodeValue(value)}
                </dd>
              </div>
            ))}
          </dl>
        </>
      ) : (
        <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
          <div className="rounded-[1.1rem] border border-border/70 bg-background/35 px-3 py-3">
            <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Visible nodes
            </p>
            <p className="mt-2 font-display text-2xl font-semibold text-foreground">
              {visibleStats.nodes}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              of {nodeCount} total across the current scope set.
            </p>
          </div>
          <div className="rounded-[1.1rem] border border-border/70 bg-background/35 px-3 py-3">
            <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Visible edges
            </p>
            <p className="mt-2 font-display text-2xl font-semibold text-foreground">
              {visibleStats.edges}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              of {edgeCount} total relationships.
            </p>
          </div>
          <div className="rounded-[1.1rem] border border-border/70 bg-background/35 px-3 py-3">
            <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Active scopes
            </p>
            <p className="mt-2 font-display text-2xl font-semibold text-foreground">
              {activeScopeCount}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              of {ALL_BRAIN_SCOPES.length} available.
            </p>
          </div>
        </div>
      )}
    </aside>
  );
}

export default function BrainPage() {
  const [data, setData] = useState<BrainGraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [activeScopes, setActiveScopes] = useState<BrainScope[]>(() => [...ALL_BRAIN_SCOPES]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [renderMode, setRenderMode] = useState<BrainRenderMode>("hybrid");
  const [modelWarning, setModelWarning] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchBrainGraph()
      .then((graph) => {
        if (!cancelled) {
          setError(null);
          setData(normalizeBrainGraph(graph));
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(String(err instanceof Error ? err.message : err));
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const sceneGraph = useMemo(
    () => (data ? buildBrainSceneGraph(data, { filter, activeScopes }) : null),
    [activeScopes, data, filter],
  );

  useEffect(() => {
    if (!selectedNodeId || !sceneGraph) return;
    if (!sceneGraph.visibleNodeIds.has(selectedNodeId)) {
      setSelectedNodeId(null);
    }
  }, [sceneGraph, selectedNodeId]);

  const scopeStats = useMemo(() => {
    const counts: Record<BrainScope, { nodes: number; edges: number }> = {
      workspace: { nodes: 0, edges: 0 },
      assistant_self: { nodes: 0, edges: 0 },
      assistant_learned: { nodes: 0, edges: 0 },
    };

    for (const node of data?.nodes ?? []) {
      counts[scopeFromMetadata(node.metadata)].nodes += 1;
    }
    for (const edge of data?.edges ?? []) {
      counts[scopeFromMetadata(edge.metadata)].edges += 1;
    }

    return counts;
  }, [data]);

  const visibleStats = useMemo(() => {
    const active = new Set(activeScopes.length > 0 ? activeScopes : ALL_BRAIN_SCOPES);
    let nodes = 0;
    let edges = 0;

    for (const node of data?.nodes ?? []) {
      if (active.has(scopeFromMetadata(node.metadata))) nodes += 1;
    }
    for (const edge of data?.edges ?? []) {
      if (active.has(scopeFromMetadata(edge.metadata))) edges += 1;
    }

    return { nodes, edges };
  }, [activeScopes, data]);

  const nodeCount = data?.nodes.length ?? 0;
  const edgeCount = data?.edges.length ?? 0;
  const selectedNode = useMemo<BrainNode | null>(() => {
    if (!data || !selectedNodeId) return null;
    if (sceneGraph && !sceneGraph.visibleNodeIds.has(selectedNodeId)) return null;
    return data.nodes.find((node) => node.node_id === selectedNodeId) ?? null;
  }, [data, sceneGraph, selectedNodeId]);
  const selectedScope = selectedNode ? scopeFromMetadata(selectedNode.metadata) : null;

  const heroMetrics = [
    {
      label: "Visible nodes",
      value: visibleStats.nodes,
      note: `${nodeCount} total nodes in the workspace`,
    },
    {
      label: "Visible edges",
      value: visibleStats.edges,
      note: `${edgeCount} total relationships`,
    },
    {
      label: "Selection",
      value: selectedNode ? "Pinned" : "Idle",
      note: selectedNode
        ? `${selectedScope ? SCOPE_META[selectedScope].label : "Workspace"} node selected`
        : "Click a node to inspect it",
    },
  ] as const;

  const toggleScope = (scope: BrainScope) => {
    setActiveScopes((prev) => {
      if (prev.includes(scope)) {
        const next = prev.filter((item) => item !== scope);
        return next.length > 0 ? next : [...ALL_BRAIN_SCOPES];
      }
      return [...prev, scope];
    });
  };

  return (
    <PageChrome
      eyebrow="Brain"
      title="Visualise your persistent companion brain"
      description="Explore how workspace structure, the Axiom Self, and learned companion memory connect."
      actions={
        <div className="flex w-full flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 rounded-full border border-border/70 bg-background/50 p-1">
            <button
              type="button"
              onClick={() => {
                setModelWarning(null);
                setRenderMode("hybrid");
              }}
              className={[
                "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                renderMode === "hybrid"
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:text-foreground",
              ].join(" ")}
            >
              Hybrid
            </button>
            <button
              type="button"
              onClick={() => setRenderMode("raw")}
              className={[
                "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                renderMode === "raw"
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:text-foreground",
              ].join(" ")}
            >
              Graph only
            </button>
          </div>
          <Input
            type="search"
            placeholder="Filter nodes..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="h-10 w-full rounded-full md:w-72"
          />
          <Button
            variant="outline"
            onClick={() => {
              setLoading(true);
              setError(null);
              setSelectedNodeId(null);
              setModelWarning(null);
              fetchBrainGraph()
                .then((graph) => setData(normalizeBrainGraph(graph)))
                .catch((err: unknown) => setError(String(err instanceof Error ? err.message : err)))
                .finally(() => setLoading(false));
            }}
            className="shrink-0"
          >
            Refresh
          </Button>
        </div>
      }
      heroAside={
        <div className="grid min-w-[18rem] gap-3 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
          {heroMetrics.map((metric) => (
            <div
              key={metric.label}
              className="rounded-[1.1rem] border border-border/70 bg-background/35 px-3 py-3"
            >
              <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                {metric.label}
              </p>
              <p className="mt-2 font-display text-2xl font-semibold text-foreground">
                {metric.value}
              </p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {metric.note}
              </p>
            </div>
          ))}
        </div>
      }
      fullBleed
      contentClassName="rounded-none border-0 bg-transparent p-0"
    >
      <div className="flex min-h-[calc(100vh-12.5rem)] flex-col gap-4 overflow-hidden">
        <div className="glass-panel rounded-[1.5rem] p-4 sm:p-5">
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(18rem,0.85fr)]">
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
                  Scope filters
                </p>
                <span className="rounded-full border border-border/70 bg-black/10 px-2.5 py-1 text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                  {activeScopes.length} active
                </span>
                <span className="rounded-full border border-border/70 bg-black/10 px-2.5 py-1 text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                  {renderMode === "hybrid" ? "Hybrid anatomy" : "Graph only"}
                </span>
                <button
                  type="button"
                  onClick={() => setActiveScopes([...ALL_BRAIN_SCOPES])}
                  className="ml-auto rounded-full border border-border/70 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground"
                >
                  Reset scopes
                </button>
              </div>

              <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
                Toggle the workspace, the Axiom Self, and learned memory layers, then inspect the graph at a denser desktop scale.
              </p>

              <div className="flex flex-wrap gap-2">
                {ALL_BRAIN_SCOPES.map((scope) => {
                  const meta = SCOPE_META[scope];
                  const active = activeScopes.includes(scope);
                  const count = scopeStats[scope];

                  return (
                    <button
                      key={scope}
                      type="button"
                      aria-pressed={active}
                      aria-label={meta.label}
                      onClick={() => toggleScope(scope)}
                      className={[
                        "flex items-center gap-3 rounded-full border px-3 py-2.5 text-left transition-all",
                        active
                          ? "border-foreground/20 bg-foreground/10 text-foreground shadow-sm"
                          : "border-border/70 bg-background/40 text-muted-foreground hover:border-foreground/20 hover:text-foreground",
                      ].join(" ")}
                    >
                      <span
                        className="h-3 w-3 rounded-full"
                        style={{
                          backgroundColor: meta.swatch,
                          border: scope === "workspace" ? "1px solid var(--color-border)" : "none",
                        }}
                      />
                      <span className="min-w-0">
                        <span className="block text-sm font-medium">{meta.label}</span>
                        <span className="block text-[11px] opacity-80">{meta.description}</span>
                      </span>
                      <span className="flex flex-col items-end gap-1">
                        <span className="rounded-full bg-background/70 px-2 py-0.5 text-[11px] font-medium">
                          {count.nodes}n / {count.edges}e
                        </span>
                        <span
                          className="block h-0 w-8 rounded-full"
                          style={{
                            borderBottom: meta.dashed
                              ? `2px dashed ${meta.lineColor}`
                              : `2px solid ${meta.lineColor}`,
                            opacity: active ? 1 : 0.45,
                          }}
                        />
                      </span>
                    </button>
                  );
                })}
              </div>

              <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-3">
                {heroMetrics.map((metric) => (
                  <div
                    key={metric.label}
                    className="rounded-[1.1rem] border border-border/70 bg-background/30 px-3 py-3"
                  >
                    <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                      {metric.label}
                    </p>
                    <p className="mt-2 font-display text-xl font-semibold text-foreground">
                      {metric.value}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      {metric.note}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[1.3rem] border border-border/70 bg-background/35 px-4 py-4">
              <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-muted-foreground">
                Legend and focus
              </p>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {loading
                  ? "Loading graph data..."
                  : error
                    ? "The graph failed to load."
                    : `${visibleStats.nodes} visible nodes and ${visibleStats.edges} visible edges currently survive the active scope filters.`}
              </p>
              {modelWarning ? (
                <p className="mt-3 rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs leading-5 text-amber-100">
                  Hybrid mode fell back to the raw graph: {modelWarning}
                </p>
              ) : null}
              <div className="mt-4 space-y-2">
                {ALL_BRAIN_SCOPES.map((scope) => {
                  const meta = SCOPE_META[scope];
                  const active = activeScopes.includes(scope);
                  return (
                    <div key={scope} className="flex items-center gap-2.5 text-xs text-muted-foreground">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{
                          backgroundColor: meta.swatch,
                          border: scope === "workspace" ? "1px solid var(--color-border)" : "none",
                        }}
                      />
                      <span
                        className="block h-0 w-6 shrink-0"
                        style={{
                          borderBottom: meta.dashed
                            ? `2px dashed ${meta.lineColor}`
                            : `2px solid ${meta.lineColor}`,
                          opacity: active ? 1 : 0.45,
                        }}
                      />
                      <span className="flex-1">{meta.label}</span>
                      <span className="rounded-full border border-border/60 bg-black/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.16em]">
                        {active ? "active" : "dimmed"}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        <div className="relative flex min-h-[40rem] flex-1 overflow-hidden rounded-[1.9rem]">
          <div className="glass-panel-strong flex min-h-0 flex-1 overflow-hidden rounded-[1.8rem]">
            {loading ? (
              <div className="flex flex-1 items-center justify-center">
                <span className="animate-pulse text-sm text-muted-foreground">
                  Building graph...
                </span>
              </div>
            ) : error ? (
              <div className="flex flex-1 items-center justify-center">
                <p className="text-sm text-destructive">{error}</p>
              </div>
            ) : data ? (
              <BrainGraph3D
                data={data}
                filter={filter}
                activeScopes={activeScopes}
                renderMode={renderMode}
                selectedNodeId={selectedNodeId}
                onSelectedNodeIdChange={setSelectedNodeId}
                onModelLoadError={(message) => {
                  setModelWarning(message);
                  setRenderMode("raw");
                }}
                className="flex-1"
              />
            ) : null}
          </div>

          <div className="pointer-events-none absolute inset-x-4 bottom-4 hidden xl:flex xl:justify-end">
            <div className="pointer-events-auto w-[20.5rem] max-w-full">
              <GraphInspectorPanel
              node={selectedNode}
              visibleStats={visibleStats}
              nodeCount={nodeCount}
              edgeCount={edgeCount}
              activeScopeCount={activeScopes.length}
              onClose={selectedNode ? () => setSelectedNodeId(null) : undefined}
              />
            </div>
          </div>
        </div>

        <div className="xl:hidden">
          <GraphInspectorPanel
            node={selectedNode}
            visibleStats={visibleStats}
            nodeCount={nodeCount}
            edgeCount={edgeCount}
            activeScopeCount={activeScopes.length}
            onClose={selectedNode ? () => setSelectedNodeId(null) : undefined}
          />
        </div>
      </div>
    </PageChrome>
  );
}
