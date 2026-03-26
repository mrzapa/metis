"use client";

import { AnimatePresence, motion } from "motion/react";
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
    className,
}: {
  liveTraceEvents: TraceEvent[];
  isStreaming: boolean;
    className?: string;
}) {
  const states = deriveSteps(liveTraceEvents, isStreaming);

  return (
     <div className={cn("mt-2 flex items-center gap-1 text-[10px]", className)}>
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
                <motion.span
                  className="size-1.5 rounded-full bg-sky-500"
                  animate={{ scale: [1, 1.45, 1], opacity: [0.65, 1, 0.65] }}
                  transition={{ duration: 1.2, ease: "easeInOut", repeat: Infinity }}
                />
              )}
              <AnimatePresence mode="wait" initial={false}>
                <motion.span
                  key={`${step.label}-${state}`}
                  initial={{ opacity: 0, y: 2 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -2 }}
                  transition={{ duration: 0.18, ease: "easeOut" }}
                >
                  {step.label}
                </motion.span>
              </AnimatePresence>
            </span>
          </span>
        );
      })}
    </div>
  );
}
