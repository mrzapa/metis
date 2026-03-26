"use client";

/**
 * BrainGraphAnimationShowcase – demonstrates all animation components
 * and shows integration patterns for the brain visualization system.
 *
 * This file serves as both documentation and a testing ground for
 * animation timing, stagger patterns, and visual feedback loops.
 */

import { useCallback } from "react";
import { useArrowState } from "@/hooks/use-arrow-state";
import BrainGraph3D, { type BrainGraph3DProps } from "./brain-graph-3d";
import { BrainGraphAnimatedWrapper } from "./brain-graph-animated-wrapper";
import { AnimatedEvidencePanel, type EvidenceItem } from "./animated-evidence-panel";
import {
  AnimatedResearchModeIndicator,
  type SubQuery,
} from "./animated-research-mode-indicator";

export interface BrainGraphAnimationShowcaseProps
  extends Omit<BrainGraph3DProps, "ref"> {
  /**
   * Enable demo mode with mock data cycling
   */
  demoMode?: boolean;
}

/**
 * Mock evidence data for demo
 */
const MOCK_EVIDENCE: EvidenceItem[] = [
  {
    id: "1",
    source: "Document: Brain Architecture Overview",
    citation: "The neocortex consists of six distinct layers...",
    confidence: 0.95,
    excerpt:
      "Each layer has specialized functions in processing and transmitting information across the brain.",
  },
  {
    id: "2",
    source: "Research: Knowledge Graph Traversal",
    citation: "Graph-based knowledge representations enable...",
    confidence: 0.88,
    excerpt:
      "By modeling relationships as edges, we can perform deep traversal queries efficiently.",
  },
  {
    id: "3",
    source: "Paper: Emergent Behaviors in Neural Networks",
    citation: "Self-organizing systems demonstrate surprising...",
    confidence: 0.82,
    excerpt: "Complex behaviors emerge from simple local interactions.",
  },
];

/**
 * Mock sub-queries for demo
 */
const MOCK_SUB_QUERIES: SubQuery[] = [
  {
    id: "sq1",
    text: "What are the fundamental properties?",
    status: "complete",
    confidence: 0.93,
  },
  {
    id: "sq2",
    text: "How do these properties interact?",
    status: "complete",
    confidence: 0.87,
  },
  {
    id: "sq3",
    text: "What are the implications?",
    status: "processing",
  },
];

export function BrainGraphAnimationShowcase({
  demoMode = false,
  ...brainGraphProps
}: BrainGraphAnimationShowcaseProps) {
  // State for demo cycling
  const [isResearchMode, setIsResearchMode] = useArrowState(demoMode);
  const [isExpanding, setIsExpanding] = useArrowState(demoMode);
  const [highlightedEvidenceId, setHighlightedEvidenceId] = useArrowState<string | null>(
    null,
  );
  const [iteration, setIteration] = useArrowState(1);
  const [subQueries, setSubQueries] = useArrowState<SubQuery[]>(MOCK_SUB_QUERIES);

  const handleStartResearch = useCallback(() => {
    setIsResearchMode(true);
    setIteration(1);
    setSubQueries([
      {
        id: "sq1",
        text: "What are the fundamental properties?",
        status: "processing",
      },
    ]);

    // Simulate query completion
    setTimeout(() => {
      setSubQueries((prev) => [
        {
          ...prev[0],
          status: "complete",
          confidence: Math.random() * 0.15 + 0.85,
        },
        {
          id: "sq2",
          text: "How do these properties interact?",
          status: "processing",
        },
      ]);
    }, 2000);

    setTimeout(() => {
      setSubQueries((prev) => [
        ...prev.slice(0, 1),
        {
          ...prev[1],
          status: "complete",
          confidence: Math.random() * 0.15 + 0.85,
        },
        {
          id: "sq3",
          text: "What are the implications?",
          status: "processing",
        },
      ]);
    }, 4000);

    setTimeout(() => {
      setSubQueries((prev) => [
        ...prev.slice(0, 2),
        {
          ...prev[2],
          status: "complete",
          confidence: Math.random() * 0.15 + 0.85,
        },
      ]);
      setIsExpanding(false);
      setIteration(2);
    }, 6000);
  }, []);

  const handleStopResearch = useCallback(() => {
    setIsResearchMode(false);
    setSubQueries([]);
    setHighlightedEvidenceId(null);
  }, []);

  const handleEvidenceClick = useCallback((item: EvidenceItem) => {
    setHighlightedEvidenceId(item.id);
    console.log("Evidence clicked:", item);
  }, []);

  const handleTriggerExpansion = useCallback(() => {
    setIsExpanding(true);
    setTimeout(() => setIsExpanding(false), 3000);
  }, []);

  return (
    <div className="relative h-full w-full flex flex-col">
      {/* Main visualization area */}
      <div className="flex-1 relative">
        <BrainGraphAnimatedWrapper
          {...brainGraphProps}
          isResearchMode={isResearchMode}
          isExpanding={isExpanding}
          evidenceCount={isResearchMode ? MOCK_EVIDENCE.length : 0}
        />

        {/* Research mode indicator overlay */}
        {isResearchMode && (
          <div className="absolute left-5 top-20 max-w-xs">
            <AnimatedResearchModeIndicator
              iteration={iteration}
              maxIterations={3}
              subQueries={subQueries}
              isExpanding={isExpanding}
              onSubQueryClick={(id) => {
                console.log("Sub-query clicked:", id);
              }}
            />
          </div>
        )}

        {/* Evidence panel overlay */}
        {isResearchMode && (
          <div className="absolute bottom-5 right-5 max-h-96 w-96">
            <AnimatedEvidencePanel
              items={MOCK_EVIDENCE}
              isHighlighted={highlightedEvidenceId}
              onItemClick={handleEvidenceClick}
              onItemHover={(id) => setHighlightedEvidenceId(id)}
              title="Supporting Evidence"
            />
          </div>
        )}
      </div>

      {/* Demo controls (only in demo mode) */}
      {demoMode && (
        <div className="border-t border-white/10 bg-white/5 px-6 py-4">
          <div className="flex items-center justify-between max-w-3xl">
            <h3 className="text-sm font-semibold text-white">
              Animation Showcase
            </h3>
            <div className="flex items-center gap-3">
              <button
                onClick={handleStartResearch}
                disabled={isResearchMode}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Start Research Mode
              </button>
              <button
                onClick={handleTriggerExpansion}
                disabled={!isResearchMode}
                className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Trigger Query Expansion
              </button>
              <button
                onClick={handleStopResearch}
                disabled={!isResearchMode}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Stop
              </button>
            </div>
          </div>

          {/* Status display */}
          <div className="mt-4 space-y-2 text-xs text-white/60">
            <p>
              Mode: <span className="text-white/80">{isResearchMode ? "Research" : "Normal"}</span>
            </p>
            <p>
              State:{" "}
              <span className="text-white/80">
                {isExpanding
                  ? "Expanding"
                  : isResearchMode
                    ? "Processing"
                    : "Idle"}
              </span>
            </p>
            <p>
              Sub-queries:{" "}
              <span className="text-white/80">
                {subQueries.filter((sq) => sq.status === "complete").length}/
                {subQueries.length}
              </span>
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export default BrainGraphAnimationShowcase;
