"use client";

/**
 * Brain Graph page — visualises indexes, sessions, and their relationships
 * as an interactive force-directed SVG graph.
 */

import { useEffect, useState } from "react";
import { BrainGraph, type BrainGraphData, type BrainNode } from "@/components/brain/brain-graph";
import { PageChrome } from "@/components/shell/page-chrome";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fetchBrainGraph } from "@/lib/api";

function NodeDetailPanel({ node, onClose }: { node: BrainNode; onClose: () => void }) {
  const metaEntries = Object.entries(node.metadata).filter(
    ([, v]) => v !== "" && v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0),
  );

  return (
    <aside className="glass-panel w-80 shrink-0 overflow-y-auto rounded-[1.6rem] p-4 text-sm">
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
    <PageChrome
      eyebrow="Brain"
      title="Visualize your knowledge graph"
      description="Explore how sessions, indexes, and categories connect across your workspace."
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
              fetchBrainGraph()
                .then(setData)
                .catch((err: unknown) => setError(String(err instanceof Error ? err.message : err)))
                .finally(() => setLoading(false));
            }}
          >
            Refresh
          </Button>
        </>
      }
      heroAside={
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
            Graph snapshot
          </p>
          <p className="text-sm leading-7 text-muted-foreground">
            {loading
              ? "Loading graph data..."
              : error
                ? "The graph failed to load."
                : `${nodeCount} nodes and ${edgeCount} edges are available for exploration.`}
          </p>
        </div>
      }
      fullBleed
      contentClassName="rounded-none border-0 bg-transparent p-0"
    >
      <div className="flex h-[calc(100vh-15.5rem)] min-h-[38rem] gap-4 overflow-hidden">
        <div className="glass-panel-strong flex flex-1 overflow-hidden rounded-[1.8rem]">
          {loading ? (
            <div className="flex flex-1 items-center justify-center">
              <span className="animate-pulse text-muted-foreground text-sm">Building graph...</span>
            </div>
          ) : error ? (
            <div className="flex flex-1 items-center justify-center">
              <p className="text-destructive text-sm">{error}</p>
            </div>
          ) : data ? (
            <BrainGraph
              data={data}
              filter={filter}
              onNodeSelect={setSelectedNode}
              className="flex-1"
            />
          ) : null}
        </div>

        {selectedNode ? (
          <NodeDetailPanel
            node={selectedNode}
            onClose={() => setSelectedNode(null)}
          />
        ) : null}
      </div>
    </PageChrome>
  );
}
