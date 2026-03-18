"use client";

/**
 * Brain Graph page — visualises indexes, sessions, and their relationships
 * as an interactive force-directed SVG graph.
 */

import { useEffect, useState } from "react";
import { BrainGraph, type BrainGraphData, type BrainNode } from "@/components/brain/brain-graph";
import { fetchBrainGraph } from "@/lib/api";

function NodeDetailPanel({ node, onClose }: { node: BrainNode; onClose: () => void }) {
  const metaEntries = Object.entries(node.metadata).filter(
    ([, v]) => v !== "" && v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0),
  );

  return (
    <aside className="w-72 shrink-0 overflow-y-auto border-l border-border bg-card p-4 text-sm">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-semibold text-foreground">{node.label}</span>
        <button
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground transition-colors"
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
  const [selectedNode, setSelectedNode] = useState<BrainNode | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchBrainGraph()
      .then((graph) => {
        if (!cancelled) {
          setData(graph);
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

  const nodeCount = data?.nodes.length ?? 0;
  const edgeCount = data?.edges.length ?? 0;

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Header */}
      <header className="flex items-center gap-4 border-b border-border px-4 py-3">
        <div>
          <h1 className="text-base font-semibold text-foreground">Brain Graph</h1>
          <p className="text-xs text-muted-foreground">
            {loading
              ? "Loading…"
              : error
                ? "Failed to load"
                : `${nodeCount} nodes · ${edgeCount} edges`}
          </p>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <input
            type="search"
            placeholder="Filter nodes…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="h-8 w-48 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <button
            onClick={() => {
              setLoading(true);
              fetchBrainGraph()
                .then(setData)
                .catch((err: unknown) => setError(String(err instanceof Error ? err.message : err)))
                .finally(() => setLoading(false));
            }}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            Refresh
          </button>
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {loading && (
          <div className="flex flex-1 items-center justify-center">
            <span className="animate-pulse text-muted-foreground text-sm">Building graph…</span>
          </div>
        )}

        {error && !loading && (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-destructive text-sm">{error}</p>
          </div>
        )}

        {data && !loading && (
          <>
            <BrainGraph
              data={data}
              filter={filter}
              onNodeSelect={setSelectedNode}
              className="flex-1"
            />
            {selectedNode && (
              <NodeDetailPanel
                node={selectedNode}
                onClose={() => setSelectedNode(null)}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
