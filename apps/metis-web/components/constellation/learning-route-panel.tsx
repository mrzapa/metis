"use client";

import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Circle,
  Loader2,
  RefreshCcw,
  Sparkles,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type {
  LearningRoute,
  LearningRouteStep,
  LearningRouteStepStatus,
} from "@/lib/constellation-types";
import { cn } from "@/lib/utils";

interface LearningRoutePanelProps {
  route: LearningRoute | null;
  previewActive: boolean;
  eligible: boolean;
  loading: boolean;
  error: string | null;
  unavailableManifestPaths: Set<string>;
  onStartCourse: () => void;
  onSaveRoute: () => void;
  onDiscardPreview: () => void;
  onRegenerateRoute: () => void;
  onLaunchStep: (step: LearningRouteStep) => void;
  onSetStepStatus: (stepId: string, status: LearningRouteStepStatus) => void;
}

function getCurrentStepId(route: LearningRoute | null): string | null {
  if (!route || route.steps.length === 0) {
    return null;
  }

  return route.steps.find((step) => step.status !== "done")?.id ?? route.steps[0]?.id ?? null;
}

export function LearningRoutePanel({
  route,
  previewActive,
  eligible,
  loading,
  error,
  unavailableManifestPaths,
  onStartCourse,
  onSaveRoute,
  onDiscardPreview,
  onRegenerateRoute,
  onLaunchStep,
  onSetStepStatus,
}: LearningRoutePanelProps) {
  const currentStepId = getCurrentStepId(route);
  const hasUnavailableSteps = route?.steps.some((step) => unavailableManifestPaths.has(step.manifestPath)) ?? false;

  if (!route) {
    return (
      <div
        className="rounded-[1.5rem] border border-white/10 bg-white/4 p-4"
        data-testid="learning-route-panel"
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Learning route</div>
            <div className="mt-2 text-sm text-slate-300">
              {eligible
                ? "Turn this star into a four-stop course and let METIS guide the route."
                : "Attach a source to this star before plotting a course through the constellation."}
            </div>
          </div>
          <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
            4 stops
          </Badge>
        </div>

        {error ? (
          <div className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
            {error}
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-3">
          <Button onClick={onStartCourse} disabled={!eligible || loading} className="gap-2">
            {loading ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            {loading ? "Plotting route..." : "Start course"}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="rounded-[1.5rem] border border-white/10 bg-white/4 p-4"
      data-testid="learning-route-panel"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">
            {previewActive ? "Course preview" : "Saved route"}
          </div>
          <div className="mt-2 text-lg font-semibold text-white">{route.title}</div>
          <div className="mt-2 text-sm text-slate-300">
            {previewActive
              ? "Preview the route, launch any stop into Tutor mode, then save it when it feels right."
              : "Keep moving through the route manually. METIS highlights the next live stop and remembers what you complete."}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
            {route.steps.length} stops
          </Badge>
          <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
            {previewActive ? "Preview" : "Saved"}
          </Badge>
        </div>
      </div>

      {error ? (
        <div className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
          {error}
        </div>
      ) : null}

      {hasUnavailableSteps && !previewActive ? (
        <div className="mt-4 rounded-2xl border border-amber-400/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
          One or more saved stops lost their source manifest. You can still inspect the route, then regenerate it from the remaining attached sources.
        </div>
      ) : null}

      <div className="mt-4 space-y-3">
        {route.steps.map((step, index) => {
          const unavailable = unavailableManifestPaths.has(step.manifestPath);
          const isDone = step.status === "done";
          const isCurrent = currentStepId === step.id;

          return (
            <div
              key={step.id}
              className={cn(
                "rounded-[1.35rem] border px-4 py-4 transition-colors",
                isCurrent
                  ? "border-[#d6b361]/28 bg-[#d6b361]/10"
                  : "border-white/10 bg-black/18",
                isDone && "opacity-70",
                unavailable && "border-dashed border-amber-400/24",
              )}
              data-testid={`learning-route-step-${index + 1}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-full border border-white/12 bg-white/8 text-sm font-semibold text-white">
                    {index + 1}
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="text-sm font-semibold text-white">{step.title}</div>
                      {isCurrent ? (
                        <Badge variant="outline" className="border-[#d6b361]/28 bg-[#d6b361]/10 text-[#f5d899]">
                          Current
                        </Badge>
                      ) : null}
                      {isDone ? (
                        <Badge variant="outline" className="border-emerald-400/20 bg-emerald-400/10 text-emerald-100">
                          Complete
                        </Badge>
                      ) : null}
                      {unavailable ? (
                        <Badge variant="outline" className="border-amber-400/20 bg-amber-400/10 text-amber-100">
                          Source missing
                        </Badge>
                      ) : null}
                    </div>
                    <div className="mt-2 text-sm leading-7 text-slate-300">{step.objective}</div>
                    <div className="mt-2 text-sm leading-7 text-slate-400">{step.rationale}</div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-400">
                      <span>{step.kind}</span>
                      <span>{step.estimatedMinutes} min</span>
                      <span className="truncate">{step.manifestPath}</span>
                    </div>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2 text-slate-400">
                  {isDone ? <CheckCircle2 className="size-4 text-emerald-300" /> : <Circle className="size-4" />}
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  onClick={() => onLaunchStep(step)}
                  disabled={unavailable}
                  className="gap-2"
                  variant={unavailable ? "outline" : "default"}
                >
                  <BookOpen className="size-4" />
                  {unavailable ? "Tutor unavailable" : "Open in Tutor"}
                </Button>
                {!previewActive ? (
                  <Button
                    variant="outline"
                    onClick={() => onSetStepStatus(step.id, isDone ? "todo" : "done")}
                    className="gap-2"
                  >
                    {isDone ? <RefreshCcw className="size-4" /> : <ArrowRight className="size-4" />}
                    {isDone ? "Reopen step" : "Mark complete"}
                  </Button>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 flex flex-wrap gap-3">
        {previewActive ? (
          <>
            <Button onClick={onSaveRoute} className="gap-2">
              <Sparkles className="size-4" />
              Save route
            </Button>
            <Button variant="outline" onClick={onDiscardPreview}>
              Discard
            </Button>
          </>
        ) : null}
        <Button variant="outline" onClick={onRegenerateRoute} disabled={!eligible || loading} className="gap-2">
          {loading ? <Loader2 className="size-4 animate-spin" /> : <RefreshCcw className="size-4" />}
          {loading ? "Regenerating..." : "Regenerate route"}
        </Button>
      </div>
    </div>
  );
}
