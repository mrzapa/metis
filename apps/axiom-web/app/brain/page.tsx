"use client";

/**
 * Brain Graph page - visualises indexes, sessions, assistant memory, and
 * relationships as an interactive force-directed SVG graph.
 */

import { useEffect, useMemo, useState } from "react";
import {
  BrainGraph,
  type BrainGraphData,
  type BrainNode,
  type BrainScope,
} from "@/components/brain/brain-graph";
import { PageChrome } from "@/components/shell/page-chrome";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fetchBrainGraph } from "@/lib/api";

const ALL_SCOPES: BrainScope[] = ["workspace", "assistant_self", "assistant_learned"];

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

function scopeFromMetadata(metadata: Record<string, unknown>): BrainScope {
  const raw = metadata.scope;
  return raw === "assistant_self" || raw === "assistant_learned" ? raw : "workspace";
}

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

function NodeDetailPanel({ node, onClose }: { node: BrainNode; onClose: () => void }) {
  const scope = scopeFromMetadata(node.metadata);
  const metaEntries = Object.entries(node.metadata).filter(
    ([key, v]) =>
      key !== "scope" &&
      v !== "" &&
      v !== null &&
      v !== undefined &&
      !(Array.isArray(v) && v.length === 0),
  );

  return (
    <aside className="glass-panel w-80 shrink-0 overflow-y-auto rounded-[1.6rem] p-4 text-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-semibold text-foreground">{node.label}</p>
          <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">
            {SCOPE_META[scope].label}
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-muted-foreground transition-colors hover:text-foreground"
          aria-label="Close detail panel"
        >
          ✕
        </button>
      </div>

      <dl className="space-y-1.5">
        <div className="flex gap-2">
          <dt className="text-muted-foreground">Type</dt>
          <dd className="font-medium capitalize text-foreground">{node.node_type}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-muted-foreground">Scope</dt>
          <dd className="font-medium text-foreground">{SCOPE_META[scope].label}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-muted-foreground">ID</dt>
          <dd className="truncate font-mono text-xs text-foreground">{node.node_id}</dd>
        </div>
        {metaEntries.map(([key, value]) => (
          <div key={key} className="flex gap-2">
            <dt className="shrink-0 text-muted-foreground capitalize">
              {key.replace(/_/g, " ")}
            </dt>
            <dd className="truncate text-foreground">
              {Array.isArray(value) ? value.join(", ") || "—" : String(value)}
            </dd>
          </div>
        ))}
      </dl>
    </aside>
  );
}

export default function BrainPage() {
  const [data, setData] = useState<BrainGraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [activeScopes, setActiveScopes] = useState<BrainScope[]>(() => [...ALL_SCOPES]);
  const [selectedNode, setSelectedNode] = useState<BrainNode | null>(null);

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
    const active = new Set(activeScopes.length > 0 ? activeScopes : ALL_SCOPES);
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

  const toggleScope = (scope: BrainScope) => {
    setActiveScopes((prev) => {
      if (prev.includes(scope)) {
        const next = prev.filter((item) => item !== scope);
        return next.length > 0 ? next : [...ALL_SCOPES];
      }
      return [...prev, scope];
    });
  };

  return (
    <PageChrome
      eyebrow="Brain"
      title="Visualize your persistent companion brain"
      description="Explore how workspace structure, the Axiom Self, and learned companion memory connect."
      actions={
        <>
          <Input
            type="search"
            placeholder="Filter nodes..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="w-56"
          />
          <Button
            variant="outline"
            onClick={() => {
              setLoading(true);
              setError(null);
              setSelectedNode(null);
              fetchBrainGraph()
                .then((graph) => setData(normalizeBrainGraph(graph)))
                .catch((err: unknown) => setError(String(err instanceof Error ? err.message : err)))
                .finally(() => setLoading(false));
            }}
          >
            Refresh
          </Button>
        </>
      }
      heroAside={
        <div className="space-y-3">
          <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
            Graph snapshot
          </p>
          <p className="text-sm leading-7 text-muted-foreground">
            {loading
              ? "Loading graph data..."
              : error
                ? "The graph failed to load."
                : `${visibleStats.nodes} visible nodes and ${visibleStats.edges} visible edges out of ${nodeCount} nodes and ${edgeCount} edges.`}
          </p>
          <div className="space-y-2 rounded-[1.1rem] border border-border/70 bg-background/35 px-3 py-3">
            <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-muted-foreground">
              Legend
            </p>
            <div className="space-y-2 text-xs text-muted-foreground">
              {ALL_SCOPES.map((scope) => {
                const meta = SCOPE_META[scope];
                return (
                  <div key={scope} className="flex items-center gap-2.5">
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
                      }}
                    />
                    <span>{meta.label}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      }
      fullBleed
      contentClassName="rounded-none border-0 bg-transparent p-0"
    >
      <div className="flex h-[calc(100vh-15.5rem)] min-h-[38rem] gap-4 overflow-hidden">
        <div className="flex min-w-0 flex-1 flex-col gap-4 overflow-hidden">
          <div className="glass-panel rounded-[1.4rem] p-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-1">
                <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
                  Scope filters
                </p>
                <p className="text-sm leading-6 text-muted-foreground">
                  Toggle between workspace structure, the Axiom Self, and learned memory links.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setActiveScopes([...ALL_SCOPES])}
                className="rounded-full border border-border/70 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground"
              >
                Reset scopes
              </button>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {ALL_SCOPES.map((scope) => {
                const meta = SCOPE_META[scope];
                const active = activeScopes.includes(scope);
                const count = scopeStats[scope];

                return (
                  <button
                    key={scope}
                    type="button"
                    aria-pressed={active}
                    onClick={() => toggleScope(scope)}
                    className={[
                      "flex items-center gap-3 rounded-full border px-3 py-2 text-left transition-all",
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
          </div>

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
              <BrainGraph
                data={data}
                filter={filter}
                activeScopes={activeScopes}
                onNodeSelect={setSelectedNode}
                className="flex-1"
              />
            ) : null}
          </div>
        </div>

        {selectedNode ? <NodeDetailPanel node={selectedNode} onClose={() => setSelectedNode(null)} /> : null}
      </div>
    </PageChrome>
  );
}
