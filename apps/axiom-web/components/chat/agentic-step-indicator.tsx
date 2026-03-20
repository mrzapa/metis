"use client";

import type { TraceEvent } from "@/lib/api";
import { cn } from "@/lib/utils";

type StepState = "upcoming" | "active" | "complete";

const STEPS = [
  { label: "Retrieval" },
  { label: "Synthesis" },
  { label: "Validation" },
] as const;

function deriveSteps(events: TraceEvent[], isStreaming: boolean): [StepState, StepState, StepState] {
  const hasRetrieval = events.some((e) =>
    ["retrieval_complete", "retrieval_augmented", "refinement_retrieval"].includes(e.event_type),
  );
  const hasFinal = events.some((e) => e.event_type === "final");
  const hasValidationSignal = events.some((e) =>
    ["iteration_start", "gaps_identified"].includes(e.event_type),
  );

  const retrieval: StepState = hasFinal || hasRetrieval ? "complete" : isStreaming ? "active" : "upcoming";
  const synthesis: StepState = hasFinal ? "complete" : hasRetrieval ? "active" : "upcoming";
  const validation: StepState = hasFinal ? "complete" : hasValidationSignal ? "active" : "upcoming";

  return [retrieval, synthesis, validation];
}

export function AgenticStepIndicator({
  liveTraceEvents,
  isStreaming,
}: {
  liveTraceEvents: TraceEvent[];
  isStreaming: boolean;
}) {
  const states = deriveSteps(liveTraceEvents, isStreaming);

  return (
    <div className="mt-2 flex items-center gap-1 text-[10px]">
      {STEPS.map((step, i) => {
        const state = states[i];
        return (
          <span key={step.label} className="flex items-center gap-1">
            {i > 0 && <span className="text-muted-foreground/40">/</span>}
            <span
              className={cn(
                "flex items-center gap-1 font-medium",
                state === "complete" && "text-emerald-600",
                state === "active" && "text-sky-600",
                state === "upcoming" && "text-muted-foreground/50",
              )}
            >
              {state === "active" && (
                <span className="size-1.5 rounded-full bg-sky-500 animate-pulse" />
              )}
              {step.label}
            </span>
          </span>
        );
      })}
    </div>
  );
}
