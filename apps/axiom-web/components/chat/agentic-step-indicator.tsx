"use client";

import { ChevronRight } from "lucide-react";
import type { TraceEvent } from "@/lib/api";
import { cn } from "@/lib/utils";

type AgenticStepStatus = "complete" | "active" | "upcoming";

interface AgenticStepIndicatorProps {
  assistantHasContent: boolean;
  events: TraceEvent[];
}

interface AgenticStep {
  key: string;
  label: string;
  status: AgenticStepStatus;
}

const STEP_LABELS = [
  { key: "retrieval", label: "Retrieval" },
  { key: "synthesis", label: "Synthesis" },
  { key: "validation", label: "Validation" },
] as const;

function deriveAgenticSteps(
  events: TraceEvent[],
  assistantHasContent: boolean,
): AgenticStep[] {
  const hasRetrievalComplete = events.some((event) => {
    const stage = event.stage.toLowerCase();
    return stage === "retrieval" && event.event_type === "retrieval_complete";
  });
  const hasValidationActivity = events.some((event) => {
    const stage = event.stage.toLowerCase();
    return stage === "validation" || stage === "grounding";
  });
  const hasSynthesisActivity =
    hasValidationActivity ||
    hasRetrievalComplete ||
    assistantHasContent ||
    events.some((event) => event.stage.toLowerCase() === "synthesis");

  let activeIndex = 0;
  if (hasValidationActivity) {
    activeIndex = 2;
  } else if (hasSynthesisActivity) {
    activeIndex = 1;
  }

  return STEP_LABELS.map((step, index) => ({
    ...step,
    status:
      index < activeIndex
        ? "complete"
        : index === activeIndex
          ? "active"
          : "upcoming",
  }));
}

function stepClasses(status: AgenticStepStatus): string {
  switch (status) {
    case "complete":
      return "border-emerald-500/30 bg-emerald-500/12 text-emerald-700";
    case "active":
      return "border-sky-500/30 bg-sky-500/12 text-sky-700";
    default:
      return "border-border bg-background/70 text-muted-foreground";
  }
}

function dotClasses(status: AgenticStepStatus): string {
  switch (status) {
    case "complete":
      return "bg-emerald-500";
    case "active":
      return "bg-sky-500 animate-pulse";
    default:
      return "bg-border";
  }
}

export function AgenticStepIndicator({
  assistantHasContent,
  events,
}: AgenticStepIndicatorProps) {
  const steps = deriveAgenticSteps(events, assistantHasContent);

  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px]">
      {steps.map((step, index) => (
        <div key={step.key} className="flex items-center gap-1.5">
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium",
              stepClasses(step.status),
            )}
          >
            <span className={cn("size-1.5 rounded-full", dotClasses(step.status))} />
            {step.label}
          </span>
          {index < steps.length - 1 && (
            <ChevronRight className="size-3 text-muted-foreground/50" />
          )}
        </div>
      ))}
    </div>
  );
}
