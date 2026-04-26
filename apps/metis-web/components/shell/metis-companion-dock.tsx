"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import {
  bootstrapAssistant,
  clearAssistantMemory,
  decideAtlasCandidate,
  fetchAssistant,
  fetchAtlasCandidate,
  fetchAutonomousStatus,
  fetchSeedlingStatus,
  recordCompanionReflection,
  reflectAssistant,
  saveAtlasEntry,
  subscribeCompanionActivity,
  triggerAutonomousResearchStream,
  updateAssistant,
  updateSettings,
} from "@/lib/api";
import type { AssistantSnapshot, AtlasEntry, CompanionActivityEvent, GrowthStage, SeedlingStatus } from "@/lib/api";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ProgressIndicator } from "@/components/ui/progress-indicator";
import { cn } from "@/lib/utils";
import {
  Bot,
  Search,
  Zap,
  ChevronDown,
  ChevronUp,
  Loader2,
  Monitor,
  Pause,
  Play,
  RefreshCw,
  Trash2,
  Cpu,
  Send,
  Square,
  AlertTriangle,
} from "lucide-react";
import { BrainIcon } from "@/components/icons";
import { HermesHud } from "@/components/shell/hud";
import { SeedlingPulseWidget } from "@/components/shell/seedling-pulse-widget";
import { useArrowState } from "@/hooks/use-arrow-state";
import { useWebGPUCompanionContext } from "@/lib/webgpu-companion/webgpu-companion-context";

interface MetisCompanionDockProps {
  sessionId?: string | null;
  runId?: string | null;
  className?: string;
}

export function MetisCompanionDock({
  sessionId,
  runId,
  className,
}: MetisCompanionDockProps) {
  const [snapshot, setSnapshot] = useArrowState<AssistantSnapshot | null>(null);
  const [loading, setLoading] = useArrowState(true);
  const [busyAction, setBusyAction] = useArrowState<"" | "toggle" | "reflect" | "clear" | "bootstrap" | "research">("");
  const [showWhy, setShowWhy] = useArrowState(false);
  const [error, setError] = useArrowState<string | null>(null);
  const [atlasCandidate, setAtlasCandidate] = useArrowState<AtlasEntry | null>(null);
  const [atlasBusyAction, setAtlasBusyAction] = useArrowState<"" | "save" | "snooze" | "decline">("");
  const [atlasError, setAtlasError] = useArrowState<string | null>(null);
  const requestIdRef = useRef(0);
  const atlasRequestIdRef = useRef(0);
  const previousContextRef = useRef<{ sessionId?: string | null; runId?: string | null } | null>(null);
  const atlasPromptedRunIdRef = useRef("");
  const researchAbortRef = useRef<AbortController | null>(null);

  const [showHud, setShowHud] = useState(false);

  // WebGPU companion – shared instance from context, so the chat pane and dock
  // can drive the same model without loading a second 500 MB worker.
  const webgpu = useWebGPUCompanionContext();
  const [quickAsk, setQuickAsk] = useState("");
  const [thoughts, setThoughts] = useState<CompanionActivityEvent[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      const raw = sessionStorage.getItem("metis:thought-log");
      return raw ? (JSON.parse(raw) as CompanionActivityEvent[]) : [];
    } catch {
      return [];
    }
  });
  const [autonomousEnabled, setAutonomousEnabled] = useState<boolean | null>(null);
  const [seedlingStatus, setSeedlingStatus] = useState<SeedlingStatus | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [researchPhase, setResearchPhase] = useState("");
  const [unseenCount, setUnseenCount] = useState(0);
  const [dockHistory, setDockHistory] = useState<Array<{ role: string; content: string }>>([]);

  // Always-on Bonsai reflection — when enabled, each completed companion
  // activity event triggers a local Bonsai reflection.  The latest few
  // reflections are shown inline in the browser companion panel.
  const [alwaysOn, setAlwaysOn] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem("metis:bonsai-always-on") === "1";
  });
  const [insights, setInsights] = useState<
    Array<{ timestamp: number; trigger: string; response: string }>
  >([]);
  const alwaysOnRef = useRef(alwaysOn);
  const webgpuRef = useRef(webgpu);
  // Phase 4a: hold the originating CompanionActivityEvent (not just its
  // summary string) so when the Bonsai response arrives we can attach
  // provenance to the persisted reflection — see capture effect below.
  const alwaysOnPendingRef = useRef<CompanionActivityEvent | null>(null);
  const prevWebgpuStatusRef = useRef(webgpu.status);
  const prevAlwaysOnRef = useRef(alwaysOn);
  const browserCompanionScopeRef = useRef<HTMLDivElement | null>(null);
  const prefersReducedMotion = useReducedMotion();
  // Phase 5 — mirror the values the activity-subscribe effect cares
  // about into refs so toggling minimize / reduced-motion does not
  // tear the listener down between stage transitions (an event
  // arriving during the gap would be lost). Mirrors the pattern
  // alwaysOn/webgpu already use above.
  const minimizedRef = useRef(false);
  const prefersReducedMotionRef = useRef(false);

  // GSAP flourish on always-on activation — a subtle scale + glow pulse on
  // the browser companion panel the first moment the user opts in.  Honours
  // prefers-reduced-motion by skipping the tween.
  useGSAP(
    () => {
      const wasOn = prevAlwaysOnRef.current;
      prevAlwaysOnRef.current = alwaysOn;
      if (prefersReducedMotion) return;
      if (!alwaysOn || wasOn) return;
      const el = browserCompanionScopeRef.current;
      if (!el) return;
      gsap.fromTo(
        el,
        { scale: 0.985, boxShadow: "0 0 0 0 rgba(139,92,246,0)" },
        {
          scale: 1,
          boxShadow: "0 0 24px 2px rgba(139,92,246,0.35)",
          duration: 0.45,
          ease: "power2.out",
          clearProps: "boxShadow,scale",
        },
      );
    },
    { scope: browserCompanionScopeRef, dependencies: [alwaysOn, prefersReducedMotion] },
  );

  const minimized = Boolean(snapshot?.identity.minimized);
  const showAtlasToast = Boolean(toastMessage?.startsWith("Saved to Atlas"));
  // Phase 5 — visible growth stage. Defaults to "seedling" client-side
  // until the additive backend payload is observed. The dock badge,
  // tooltip copy, and the stage_transition pulse all key off this.
  const growthStage: GrowthStage = snapshot?.status?.growth_stage ?? "seedling";
  const growthStageLabel =
    growthStage === "seedling"
      ? "Seedling"
      : growthStage === "sapling"
        ? "Sapling"
        : growthStage === "bloom"
          ? "Bloom"
          : "Elder";
  const growthStageStyle = (() => {
    switch (growthStage) {
      case "sapling":
        return "border-emerald-400/40 bg-emerald-400/10 text-emerald-200";
      case "bloom":
        return "border-violet-400/40 bg-violet-400/10 text-violet-200";
      case "elder":
        return "border-amber-400/40 bg-amber-400/10 text-amber-200";
      case "seedling":
      default:
        return "border-muted-foreground/40 bg-muted-foreground/10 text-muted-foreground";
    }
  })();
  const growthStageTooltip = (() => {
    switch (growthStage) {
      case "sapling":
        return "Sapling — you've fed the companion enough material that it has shape.";
      case "bloom":
        return "Bloom — the companion now spans many faculties and has captured skills you can promote.";
      case "elder":
        return "Elder — the companion has accumulated significant promoted skills and reflections.";
      case "seedling":
      default:
        return "Seedling — feed the companion stars and reflections to help it grow.";
    }
  })();
  const stageBadgeRef = useRef<HTMLSpanElement | null>(null);
  const seedlingAwake = seedlingStatus?.running === true;
  // Phase 4b: surface the model_status enum in the indicator tooltip so
  // the user knows whether overnight reflection is set up. The label is
  // qualified (no unqualified "while you sleep" copy — see ADR 0013 §3
  // and the marketing-copy-guard test).
  const seedlingModelStatus = seedlingStatus?.model_status ?? "frontend_only";
  const seedlingStatusLabel = (() => {
    if (seedlingStatus === null) return "Seedling status unknown";
    const base = seedlingAwake ? "Seedling awake" : "Seedling resting";
    if (seedlingModelStatus === "backend_configured") {
      return `${base} · backend reflection configured (opt-in, runs while your laptop is awake)`;
    }
    if (seedlingModelStatus === "backend_disabled") {
      return `${base} · backend reflection available but disabled in settings`;
    }
    if (seedlingModelStatus === "backend_unavailable") {
      return `${base} · backend reflection enabled but the configured GGUF cannot load`;
    }
    return `${base} · while-you-work reflection only (configure a GGUF for backend reflection)`;
  })();

  const load = useCallback(async (autoBootstrap: boolean) => {
    const requestId = ++requestIdRef.current;
    try {
      let next = await fetchAssistant();
      if (requestId !== requestIdRef.current) {
        return;
      }
      if (
        autoBootstrap &&
        next.runtime.auto_bootstrap &&
        !next.status.recommended_model_name &&
        ["pending", "fallback", "recommended"].includes(next.status.bootstrap_state)
      ) {
        next = await bootstrapAssistant(false);
        if (requestId !== requestIdRef.current) {
          return;
        }
      }
      setSnapshot(next);
    } catch (err) {
      if (requestId !== requestIdRef.current) {
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to load companion");
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [setError, setLoading, setSnapshot]);

  useEffect(() => {
    const hasPreviousContext = previousContextRef.current !== null;
    previousContextRef.current = { sessionId, runId };
    void load(!hasPreviousContext);
  }, [load, sessionId, runId]);

  const loadAtlasPrompt = useCallback(async () => {
    const nextSessionId = String(sessionId ?? "").trim();
    const nextRunId = String(runId ?? "").trim();
    const requestId = ++atlasRequestIdRef.current;
    if (!nextSessionId || !nextRunId) {
      setAtlasCandidate(null);
      setAtlasError(null);
      return;
    }
    try {
      const candidate = await fetchAtlasCandidate(nextSessionId, nextRunId);
      if (requestId !== atlasRequestIdRef.current) {
        return;
      }
      setAtlasCandidate(candidate);
      setAtlasError(null);
      if (
        candidate &&
        candidate.status === "candidate" &&
        candidate.run_id !== atlasPromptedRunIdRef.current
      ) {
        atlasPromptedRunIdRef.current = candidate.run_id;
        if (minimized) {
          setToastMessage("METIS suggests saving this answer to Atlas");
          setUnseenCount((count) => count + 1);
        }
      }
    } catch (err) {
      if (requestId !== atlasRequestIdRef.current) {
        return;
      }
      setAtlasCandidate(null);
      setAtlasError(err instanceof Error ? err.message : "Failed to load Atlas prompt");
    }
  }, [minimized, runId, sessionId, setAtlasCandidate, setAtlasError, setToastMessage, setUnseenCount]);

  useEffect(() => {
    void loadAtlasPrompt();
  }, [loadAtlasPrompt]);

  // Persist thought log to sessionStorage on every update
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      sessionStorage.setItem("metis:thought-log", JSON.stringify(thoughts));
    } catch {
      // storage may be unavailable in private browsing
    }
  }, [thoughts]);

  // Reset unseen badge when dock expands
  useEffect(() => {
    if (!minimized) setUnseenCount(0);
  }, [minimized]);

  useEffect(() => {
    return subscribeCompanionActivity((event) => {
      setThoughts((prev) => [event, ...prev].slice(0, 8));
      if (minimizedRef.current) setUnseenCount((n) => n + 1);
      if (event.source === "autonomous_research" && event.state === "completed") {
        setToastMessage("New star added to constellation");
      }
      // Phase 5 — one-time stage-transition magic moment. The
      // backend has already persisted the new stage; we surface a
      // toast, fire a GSAP pulse on the badge, and refetch the
      // assistant snapshot so the badge label reflects the new
      // stage without waiting for the next manual reload.
      if (event.kind === "stage_transition" && event.state === "completed") {
        const stagePayload = event.payload as
          | { advanced_from?: string; stage?: string }
          | undefined;
        const newStage = stagePayload?.stage
          ? String(stagePayload.stage).slice(0, 1).toUpperCase() +
            String(stagePayload.stage).slice(1)
          : "next stage";
        setToastMessage(`Companion advanced to ${newStage}`);
        // Refresh the snapshot so the badge updates.
        void load(false);
        // GSAP pulse on the badge — honours prefers-reduced-motion.
        if (!prefersReducedMotionRef.current && stageBadgeRef.current) {
          gsap.fromTo(
            stageBadgeRef.current,
            { scale: 1, boxShadow: "0 0 0 0 rgba(139,92,246,0)" },
            {
              scale: 1.18,
              boxShadow: "0 0 24px 4px rgba(139,92,246,0.55)",
              duration: 0.5,
              ease: "power2.out",
              yoyo: true,
              repeat: 1,
              clearProps: "boxShadow,scale",
            },
          );
        }
      }
      // Always-on: reflect locally on each completed event.  Skip if a
      // reflection is already in flight so we don't stomp the user's chat
      // stream or queue runaway work.
      if (!alwaysOnRef.current) return;
      if (event.state !== "completed") return;
      // Don't reflect on our own completed reflections — would create a
      // self-triggering loop where every persisted reflection causes
      // the next one.
      if (event.source === "reflection") return;
      if (alwaysOnPendingRef.current) return;
      const g = webgpuRef.current;
      if (g.status !== "ready") return;
      alwaysOnPendingRef.current = event;
      g.send([
        {
          role: "system",
          content:
            "You are METIS, a concise research companion. In one or two sentences, note the most useful follow-up for the given event. Be direct and actionable.",
        },
        {
          role: "user",
          content: `Event (${event.source}): ${String(event.summary ?? "").slice(0, 400)}`,
        },
      ]);
    });
  }, [load]);

  // Dismiss toast after 3 seconds
  useEffect(() => {
    if (!toastMessage) return;
    const id = window.setTimeout(() => setToastMessage(null), 3000);
    return () => window.clearTimeout(id);
  }, [toastMessage]);

  // Load autonomous status once on mount
  useEffect(() => {
    fetchAutonomousStatus()
      .then((s) => setAutonomousEnabled(s.enabled))
      .catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadSeedlingStatus() {
      try {
        const status = await fetchSeedlingStatus();
        if (!cancelled) setSeedlingStatus(status);
      } catch {
        if (!cancelled) setSeedlingStatus(null);
      }
    }
    void loadSeedlingStatus();
    const intervalId = window.setInterval(() => {
      void loadSeedlingStatus();
    }, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  // Keep refs mirrored so the (stable) subscribeCompanionActivity callback
  // always sees the latest alwaysOn flag and webgpu handle without forcing a
  // re-subscription on every render.
  useEffect(() => {
    alwaysOnRef.current = alwaysOn;
  }, [alwaysOn]);
  useEffect(() => {
    webgpuRef.current = webgpu;
  }, [webgpu]);
  useEffect(() => {
    minimizedRef.current = minimized;
  }, [minimized]);
  useEffect(() => {
    prefersReducedMotionRef.current = Boolean(prefersReducedMotion);
  }, [prefersReducedMotion]);

  // Persist the always-on toggle across reloads
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("metis:bonsai-always-on", alwaysOn ? "1" : "0");
  }, [alwaysOn]);

  // Auto-load Bonsai when the user opts into always-on
  useEffect(() => {
    if (alwaysOn && webgpu.status === "idle") {
      webgpu.load();
    }
  }, [alwaysOn, webgpu.status, webgpu.load]);

  // Capture the finished Bonsai response when an always-on reflection finishes.
  // Runs on every status change; only commits on the "generating" → "ready"
  // edge while a reflection is pending. Phase 4a also POSTs the response to
  // the backend so the reflection lands in the companion memory list and
  // updates `AssistantStatus.latest_summary`. Backend cooldown is the source
  // of truth — a 4xx-style "cooldown" reason is treated as a soft skip.
  useEffect(() => {
    const prev = prevWebgpuStatusRef.current;
    prevWebgpuStatusRef.current = webgpu.status;
    if (prev !== "generating" || webgpu.status !== "ready") return;
    const sourceEvent = alwaysOnPendingRef.current;
    if (!sourceEvent) return;
    alwaysOnPendingRef.current = null;
    const response = webgpu.output.trim();
    if (!response) return;
    const triggerLabel = sourceEvent.summary || sourceEvent.source;
    setInsights((list) =>
      [{ timestamp: Date.now(), trigger: triggerLabel, response }, ...list].slice(0, 5),
    );
    // Persist to the backend. Don't await — UX should not block on the
    // round-trip. Surface failures only at debug level so a transient
    // network blip doesn't flash an error toast for an opt-in feature.
    void recordCompanionReflection({
      summary: response,
      trigger: sourceEvent.source,
      kind: "while_you_work",
      source_event: {
        source: sourceEvent.source,
        state: sourceEvent.state,
        summary: sourceEvent.summary,
        timestamp: sourceEvent.timestamp,
        ...(sourceEvent.payload ?? {}),
      },
    }).catch((err) => {
      if (typeof console !== "undefined") {
        console.debug("Phase 4a reflection POST failed", err);
      }
    });
  }, [webgpu.status, webgpu.output]);

  // Abort any in-flight research stream on unmount
  useEffect(() => {
    return () => {
      researchAbortRef.current?.abort();
    };
  }, []);

  const latestMemory = useMemo(
    () => snapshot?.memory?.[0] ?? null,
    [snapshot],
  );

  // True when no dedicated runtime is wired up on the server side.
  // WebGPU fills this gap with a fully in-browser model.
  const noRuntime =
    !loading &&
    snapshot?.identity.companion_enabled === true &&
    !snapshot?.status.runtime_source;

  /** Build the prompt fed to the WebGPU model for a context-aware reflection. */
  function buildReflectionMessages(): Array<{ role: string; content: string }> {
    const ctx =
      snapshot?.status.latest_summary ??
      snapshot?.memory?.[0]?.summary ??
      "";
    return [
      {
        role: "system",
        content:
          "You are METIS, a concise research companion. Give 2-3 sentence replies. Be direct and actionable. Never use lists or headers.",
      },
      {
        role: "user",
        content: ctx
          ? `Context: "${ctx.slice(0, 400)}"\n\nGiven that context, what is the single most useful next step or insight right now?`
          : "What is one high-leverage question a researcher should ask themselves at the start of a new session?",
      },
    ];
  }

  if (snapshot && !snapshot.identity.docked) {
    return null;
  }

  async function handleTogglePause() {
    if (!snapshot) return;
    setBusyAction("toggle");
    setError(null);
    try {
      const next = await updateAssistant({
        status: { paused: !snapshot.status.paused },
      });
      setSnapshot(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update companion");
    } finally {
      setBusyAction("");
    }
  }

  async function handleReflect() {
    setBusyAction("reflect");
    setError(null);
    try {
      await reflectAssistant({
        trigger: "manual",
        session_id: sessionId ?? "",
        run_id: runId ?? "",
        force: true,
      });
      await load(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reflection failed");
    } finally {
      setBusyAction("");
    }
  }

  async function handleClearMemory() {
    setBusyAction("clear");
    setError(null);
    try {
      await clearAssistantMemory(5);
      await load(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clear memory");
    } finally {
      setBusyAction("");
    }
  }

  async function handleBootstrap() {
    setBusyAction("bootstrap");
    setError(null);
    try {
      const next = await bootstrapAssistant(true);
      setSnapshot(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to install companion runtime");
    } finally {
      setBusyAction("");
    }
  }

  async function handleSaveAtlas() {
    const candidate = atlasCandidate;
    if (!candidate) return;
    setAtlasBusyAction("save");
    setAtlasError(null);
    try {
      const saved = await saveAtlasEntry({
        session_id: candidate.session_id,
        run_id: candidate.run_id,
        title: candidate.title,
        summary: candidate.summary,
      });
      setAtlasCandidate(saved);
      setToastMessage(
        saved.markdown_path
          ? `Saved to Atlas · ${formatAtlasPath(saved.markdown_path)}`
          : "Saved to Atlas",
      );
    } catch (err) {
      setAtlasError(err instanceof Error ? err.message : "Failed to save Atlas entry");
    } finally {
      setAtlasBusyAction("");
    }
  }

  async function handleAtlasDecision(decision: "snoozed" | "declined") {
    const candidate = atlasCandidate;
    if (!candidate) return;
    setAtlasBusyAction(decision === "snoozed" ? "snooze" : "decline");
    setAtlasError(null);
    try {
      await decideAtlasCandidate({
        session_id: candidate.session_id,
        run_id: candidate.run_id,
        decision,
      });
      setAtlasCandidate(null);
    } catch (err) {
      setAtlasError(err instanceof Error ? err.message : "Failed to update Atlas prompt");
    } finally {
      setAtlasBusyAction("");
    }
  }

  async function handleResearchNow() {
    // Cancel any previous in-flight request
    researchAbortRef.current?.abort();
    const abortController = new AbortController();
    researchAbortRef.current = abortController;
    setBusyAction("research");
    setResearchPhase("starting…");
    setError(null);
    try {
      await triggerAutonomousResearchStream({
        signal: abortController.signal,
        onEvent: (ev) => {
          const label: Record<string, string> = {
            scanning: "scanning…",
            formulating: "formulating…",
            searching: "searching…",
            synthesizing: "synthesising…",
            indexing: "indexing…",
            complete: "done",
            skipped: "up to date",
          };
          if (ev.type in label) setResearchPhase(label[ev.type]);
        },
      });
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError(err instanceof Error ? err.message : "Autonomous research failed");
      }
    } finally {
      setBusyAction("");
      setResearchPhase("");
    }
  }

  async function handleToggleAutonomous() {
    if (autonomousEnabled === null) return;
    const next = !autonomousEnabled;
    setAutonomousEnabled(next);
    try {
      await updateSettings({ assistant_policy: { autonomous_research_enabled: next } });
    } catch {
      // Revert optimistic update on failure
      setAutonomousEnabled(!next);
    }
  }

  async function handleMinimizeToggle() {
    if (!snapshot) return;
    try {
      const next = await updateAssistant({
        identity: { minimized: !snapshot.identity.minimized },
      });
      setSnapshot(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update dock state");
    }
  }

  return (
    <aside
      className={cn(
        "pointer-events-auto fixed bottom-4 right-4 z-40",
        minimized ? "w-auto" : "w-[min(24rem,calc(100vw-2rem))]",
        className,
      )}
      aria-label="METIS companion"
    >
      {showAtlasToast ? (
        <div className="absolute bottom-full right-0 mb-3 w-[min(22rem,calc(100vw-2rem))] rounded-[1.1rem] border border-emerald-400/20 bg-[rgba(7,24,20,0.95)] px-3 py-2.5 shadow-2xl shadow-black/35 backdrop-blur-xl">
          <p className="text-xs font-medium text-emerald-300">{toastMessage}</p>
        </div>
      ) : null}
      {atlasCandidate?.status === "candidate" ? (
        <div className="absolute bottom-full right-0 mb-3 w-[min(22rem,calc(100vw-2rem))] rounded-[1.35rem] border border-sky-400/20 bg-[rgba(8,16,28,0.94)] p-3.5 shadow-2xl shadow-black/35 backdrop-blur-xl">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-sky-500/14 text-sky-300">
              <Bot className="size-4" />
            </span>
            <div className="min-w-0 flex-1 space-y-2">
              <div>
                <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-sky-300">
                  Atlas Suggestion
                </p>
                <p className="mt-1 text-sm leading-6 text-foreground">
                  This answer looks worth keeping. Save it to Atlas?
                </p>
              </div>
              <div className="rounded-[1rem] border border-white/8 bg-white/4 px-3 py-2">
                <p className="truncate text-xs font-medium text-foreground">
                  {atlasCandidate.title}
                </p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  {atlasCandidate.summary || atlasCandidate.rationale}
                </p>
                <p className="mt-1 text-[11px] text-muted-foreground/80">
                  {atlasCandidate.rationale}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  className="h-8 gap-2"
                  onClick={() => void handleSaveAtlas()}
                  disabled={atlasBusyAction !== ""}
                >
                  {atlasBusyAction === "save" ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : null}
                  Save to Atlas
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-8"
                  onClick={() => void handleAtlasDecision("snoozed")}
                  disabled={atlasBusyAction !== ""}
                >
                  {atlasBusyAction === "snooze" ? "Saving…" : "Not now"}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="h-8 px-2 text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => void handleAtlasDecision("declined")}
                  disabled={atlasBusyAction !== ""}
                >
                  {atlasBusyAction === "decline" ? "Saving…" : "Don't ask again"}
                </Button>
              </div>
              {atlasError ? (
                <p className="text-xs text-destructive">{atlasError}</p>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
      <div className={cn(
        "home-liquid-glass border border-white/10 shadow-2xl shadow-black/40",
        minimized ? "rounded-full" : "rounded-[1.6rem]",
      )}>
        <div className={cn(
          "flex items-center",
          minimized ? "gap-2 px-2.5 py-1.5" : "gap-3 border-b border-white/8 px-4 py-3",
        )}>
          <span className={cn(
            "relative flex items-center justify-center rounded-full bg-primary/15 text-primary",
            minimized ? "size-7" : "size-9",
          )}>
            <Bot className={minimized ? "size-3.5" : "size-4"} />
            <span
              role="status"
              aria-label={seedlingStatusLabel}
              title={seedlingStatusLabel}
              className={cn(
                "absolute -bottom-0.5 -right-0.5 flex size-2.5 items-center justify-center rounded-full border border-background",
                seedlingAwake ? "bg-emerald-400" : "bg-muted-foreground/70",
              )}
            >
              <motion.span
                className={cn(
                  "size-1.5 rounded-full",
                  seedlingAwake ? "bg-emerald-100" : "bg-muted",
                )}
                animate={
                  seedlingAwake && !prefersReducedMotion
                    ? { scale: [0.85, 1.25, 0.85], opacity: [0.65, 1, 0.65] }
                    : undefined
                }
                transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
              />
            </span>
          </span>
          {!minimized && (
            <div className="min-w-0">
              <p className="flex min-w-0 items-center gap-2 truncate font-display text-lg font-semibold tracking-[-0.03em] text-foreground">
                <span className="truncate">{snapshot?.identity.name ?? "METIS"}</span>
                {/* Phase 5 — visible growth-stage badge. Defaults to
                    Seedling on first render; bumps when the backend
                    decision lands or a stage_transition event fires. */}
                <span
                  ref={stageBadgeRef}
                  data-testid="companion-stage-badge"
                  aria-label={`Growth stage: ${growthStageLabel}`}
                  title={growthStageTooltip}
                  className={cn(
                    "shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.14em]",
                    growthStageStyle,
                  )}
                >
                  {growthStageLabel}
                </span>
              </p>
              <p className="truncate text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                {snapshot?.status.runtime_source === "dedicated_local"
                  ? "Dedicated local companion"
                  : "Companion overlay"}
              </p>
            </div>
          )}
          {minimized && (
            <span className="flex items-center gap-1.5 text-sm font-medium text-foreground">
              {snapshot?.identity.name ?? "METIS"}
              {unseenCount > 0 && (
                <span className="flex size-4 items-center justify-center rounded-full bg-violet-500 text-[9px] font-bold text-white">
                  {unseenCount > 9 ? "9+" : unseenCount}
                </span>
              )}
            </span>
          )}
          {!minimized && (
            <button
              type="button"
              onClick={() => setShowHud((v) => !v)}
              className={cn(
                "rounded-full p-1.5 text-muted-foreground transition-colors hover:bg-white/8 hover:text-foreground",
                showHud && "bg-white/8 text-foreground",
              )}
              aria-label="Open Hermes HUD"
              title="Hermes HUD"
            >
              <Monitor className="size-3.5" />
            </button>
          )}
          <button
            type="button"
            onClick={() => void handleMinimizeToggle()}
            className={cn(
              "rounded-full text-muted-foreground transition-colors hover:bg-white/8 hover:text-foreground",
              minimized ? "ml-0.5 p-1" : "ml-auto p-1.5",
            )}
            aria-label={minimized ? "Expand companion" : "Minimize companion"}
          >
            {minimized ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-4" />}
          </button>
        </div>

        {!minimized ? (
          <div className="space-y-4 px-4 py-4">
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                Loading companion state…
              </div>
            ) : (
              <>
                <div className="space-y-1">
                  <p className="text-sm leading-6 text-foreground">
                    {latestMemory?.summary || snapshot?.identity.greeting || "I’m here and ready to guide the next step."}
                  </p>
                  <p className="text-xs leading-5 text-muted-foreground">
                    {snapshot?.status.bootstrap_message || "I keep local reflections and learned links while leaving normal chat and RAG flows alone."}
                  </p>
                </div>

                {latestMemory?.why || snapshot?.status.latest_why ? (
                  <div className="rounded-[1.15rem] border border-white/8 bg-white/4 px-3 py-2.5 backdrop-blur-sm">
                    <button
                      type="button"
                      onClick={() => setShowWhy((current) => !current)}
                      className="flex w-full items-center justify-between gap-2 text-left text-xs font-medium uppercase tracking-[0.18em] text-primary"
                    >
                      Why this suggestion?
                      {showWhy ? <ChevronDown className="size-3.5" /> : <ChevronUp className="size-3.5" />}
                    </button>
                    {showWhy ? (
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">
                        {latestMemory?.why || snapshot?.status.latest_why}
                      </p>
                    ) : null}
                  </div>
                ) : null}

                {/* ── Activity surface ──────────────────────────────────────
                    Seedling lifecycle is represented by the ambient
                    SeedlingPulseWidget (replaces the previous text-heavy
                    "Seedling heartbeat" entries).  Other CompanionActivityEvent
                    sources (rag_stream, index_build, autonomous_research,
                    reflection, news_comet) still render as the recent-activity
                    text log alongside the widget. ── */}
                {(() => {
                  const nonSeedlingThoughts = thoughts.filter(
                    (t) => t.source !== "seedling",
                  );
                  const showWidget = seedlingStatus !== null;
                  const showList = nonSeedlingThoughts.length > 0;
                  if (!showWidget && !showList) return null;
                  const sourceColors: Record<string, string> = {
                    rag_stream: "text-blue-400",
                    index_build: "text-green-400",
                    autonomous_research: "text-violet-400",
                    reflection: "text-amber-400",
                    seedling: "text-emerald-400",
                    news_comet: "text-orange-400",
                  };
                  return (
                    <div className="rounded-[1.15rem] border border-white/8 bg-white/4 px-3 py-2.5 backdrop-blur-sm">
                      <div className="flex items-start gap-3">
                        {showWidget ? (
                          <SeedlingPulseWidget
                            status={seedlingStatus}
                            onActivate={() => {
                              if (minimized) {
                                void handleMinimizeToggle();
                              }
                            }}
                            className="shrink-0"
                          />
                        ) : null}
                        <div className="min-w-0 flex-1">
                          <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                            Recent activity
                          </p>
                          {showList ? (
                            <ul className="max-h-40 space-y-1.5 overflow-y-auto">
                              {nonSeedlingThoughts.map((t, i) => {
                                const stateIcon =
                                  t.state === "running"
                                    ? "▸"
                                    : t.state === "completed"
                                      ? "✓"
                                      : "⚠";
                                return (
                                  <li
                                    key={i}
                                    className="flex items-start gap-2 text-xs leading-5"
                                  >
                                    <span
                                      className={cn(
                                        "mt-0.5 shrink-0 text-[10px]",
                                        sourceColors[t.source] ??
                                          "text-muted-foreground",
                                      )}
                                    >
                                      {stateIcon}
                                    </span>
                                    <span className="min-w-0 text-foreground/80">
                                      {t.summary}
                                    </span>
                                  </li>
                                );
                              })}
                            </ul>
                          ) : (
                            <p className="text-xs leading-5 text-muted-foreground">
                              {seedlingStatus?.running
                                ? "METIS is breathing — waiting on new signals."
                                : "Seedling resting. METIS will resume on its own."}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })()}

                <div className="grid grid-cols-2 gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="justify-start gap-2"
                    onClick={() => void handleTogglePause()}
                    disabled={busyAction !== ""}
                  >
                    {busyAction === "toggle" ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : snapshot?.status.paused ? (
                      <Play className="size-4" />
                    ) : (
                      <Pause className="size-4" />
                    )}
                    {snapshot?.status.paused ? "Resume" : "Pause"}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="justify-start gap-2"
                    onClick={() => void handleReflect()}
                    disabled={busyAction !== ""}
                  >
                    {busyAction === "reflect" ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <RefreshCw className="size-4" />
                    )}
                    Reflect Now
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="justify-start gap-2"
                    onClick={() => void handleClearMemory()}
                    disabled={busyAction !== ""}
                  >
                    {busyAction === "clear" ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Trash2 className="size-4" />
                    )}
                    Clear Recent
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="justify-start gap-2"
                    onClick={() => void load(false)}
                    disabled={busyAction !== ""}
                  >
                    <BrainIcon size={16} className="shrink-0" />
                    Refresh
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="col-span-2 justify-start gap-2"
                    onClick={() => void handleResearchNow()}
                    disabled={busyAction !== ""}
                  >
                    {busyAction === "research" ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Search className="size-4" />
                    )}
                    Research Now
                    {busyAction === "research" && researchPhase && (
                      <span className="ml-auto text-[10px] font-normal text-muted-foreground">
                        {researchPhase}
                      </span>
                    )}
                  </Button>
                </div>

                {/* Autonomous research enabled toggle */}
                {autonomousEnabled !== null && (
                  <button
                    type="button"
                    onClick={() => void handleToggleAutonomous()}
                    className="flex w-full items-center justify-between gap-2 rounded-[1rem] border border-white/8 bg-white/4 px-3 py-2 text-left backdrop-blur-sm transition-colors hover:bg-white/8"
                  >
                    <div className="flex min-w-0 flex-col">
                      <div className="flex items-center gap-2">
                        <Zap className={cn("size-3.5 shrink-0", autonomousEnabled ? "text-violet-400" : "text-muted-foreground")} />
                        <span className="text-xs font-medium text-foreground">
                          Auto-research
                        </span>
                      </div>
                      {(() => {
                        const last = thoughts.find(
                          (t) => t.source === "autonomous_research" && t.state === "completed",
                        );
                        if (!last) return null;
                        const mins = Math.round((Date.now() - last.timestamp) / 60_000);
                        const label = mins < 1 ? "just now" : mins === 1 ? "1 min ago" : `${mins} mins ago`;
                        return (
                          <span className="ml-5.5 text-[10px] text-muted-foreground">
                            Last run: {label}
                          </span>
                        );
                      })()}
                    </div>
                    <span className={cn(
                      "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em]",
                      autonomousEnabled
                        ? "bg-violet-400/15 text-violet-400"
                        : "bg-white/8 text-muted-foreground",
                    )}>
                      {autonomousEnabled ? "On" : "Off"}
                    </span>
                  </button>
                )}

{/* Toast notification for new star – taps through to /brain */}
                {toastMessage && !showAtlasToast && (
                  <Link
                    href="/brain"
                    className="flex items-center gap-2 rounded-[1rem] border border-violet-400/20 bg-violet-400/10 px-3 py-2 transition-colors hover:bg-violet-400/15"
                  >
                    <Zap className="size-3.5 shrink-0 text-violet-400" />
                    <p className="text-xs text-violet-300">{toastMessage}</p>
                    <span className="ml-auto text-[10px] text-violet-400/60">View →</span>
                  </Link>
                )}

                {/* ── WebGPU browser-local companion ─────────────────────────
                    Shown only when no server runtime is configured.
                    All inference runs client-side via @huggingface/transformers
                    + WebGPU.  Bonsai 1.7B (~500 MB, q1) is cached in IndexedDB
                    after the first download. ──────────────────────────────── */}
                {noRuntime && (
                  <div
                    ref={browserCompanionScopeRef}
                    className="rounded-[1.2rem] border border-white/10 bg-white/4 px-3 py-3 backdrop-blur-sm"
                  >
                    <div className="flex items-center gap-2">
                      <Cpu className="size-3.5 shrink-0 text-primary" />
                      <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">
                        Browser companion
                      </p>
                      {/* Live pulse while an always-on reflection is generating */}
                      <AnimatePresence>
                        {alwaysOn && webgpu.status === "generating" && (
                          <motion.span
                            key="reflecting"
                            initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.6 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.6 }}
                            transition={{ duration: 0.2 }}
                            className="ml-auto flex items-center gap-1.5 text-[10px] text-violet-300"
                            aria-live="polite"
                          >
                            <motion.span
                              className="size-1.5 rounded-full bg-violet-400"
                              animate={prefersReducedMotion ? undefined : { scale: [1, 1.6, 1], opacity: [0.6, 1, 0.6] }}
                              transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
                            />
                            reflecting
                          </motion.span>
                        )}
                      </AnimatePresence>
                    </div>

                    {/* Always-on toggle — reflects locally on every completed
                        companion activity event.  Hidden when WebGPU isn't
                        available at all. */}
                    {webgpu.status !== "unsupported" && (
                      <motion.button
                        type="button"
                        onClick={() => setAlwaysOn((v) => !v)}
                        whileHover={prefersReducedMotion ? undefined : { scale: 1.01 }}
                        whileTap={prefersReducedMotion ? undefined : { scale: 0.985 }}
                        transition={{ type: "spring", stiffness: 380, damping: 26 }}
                        className={cn(
                          "mt-3 flex w-full items-center justify-between gap-2 rounded-[1rem] border px-3 py-2 text-left transition-colors",
                          alwaysOn
                            ? "border-primary/25 bg-primary/8 hover:bg-primary/12"
                            : "border-white/8 bg-white/4 hover:bg-white/8",
                        )}
                        aria-pressed={alwaysOn}
                      >
                        <div className="flex min-w-0 flex-col">
                          <div className="flex items-center gap-2">
                            <motion.span
                              animate={alwaysOn && !prefersReducedMotion ? { rotate: [0, -8, 8, 0] } : { rotate: 0 }}
                              transition={{ duration: 0.5, ease: "easeInOut" }}
                              className="flex"
                            >
                              <Bot className={cn("size-3.5 shrink-0", alwaysOn ? "text-primary" : "text-muted-foreground")} />
                            </motion.span>
                            <span className="text-xs font-medium text-foreground">Always-on reflection</span>
                          </div>
                          <span className="ml-5.5 text-[10px] text-muted-foreground">
                            {alwaysOn
                              ? "Bonsai reflects on every completed event"
                              : "Reflect locally on each completed event"}
                          </span>
                        </div>
                        {/* Pill switch with a sliding indicator via shared layoutId */}
                        <span
                          className={cn(
                            "relative flex h-5 w-10 shrink-0 items-center rounded-full px-0.5 transition-colors",
                            alwaysOn ? "justify-end bg-primary/25" : "justify-start bg-white/10",
                          )}
                        >
                          <motion.span
                            layout
                            transition={{ type: "spring", stiffness: 500, damping: 34 }}
                            className={cn(
                              "size-4 rounded-full shadow-sm",
                              alwaysOn ? "bg-primary" : "bg-muted-foreground/60",
                            )}
                          />
                        </span>
                      </motion.button>
                    )}

                    {/* Latest always-on insights — shown only when the feature
                        is on and Bonsai has produced at least one response.
                        AnimatePresence keyed on the timestamp so every fresh
                        reflection cross-fades + slides in cleanly. */}
                    <AnimatePresence mode="wait">
                      {alwaysOn && insights.length > 0 && (
                        <motion.div
                          key={insights[0].timestamp}
                          initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 8, filter: "blur(4px)" }}
                          animate={prefersReducedMotion ? { opacity: 1 } : { opacity: 1, y: 0, filter: "blur(0px)" }}
                          exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: -4, filter: "blur(4px)" }}
                          transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                          className="mt-3 overflow-hidden rounded-[1rem] border border-primary/15 bg-gradient-to-br from-primary/10 via-primary/5 to-transparent px-3 py-2.5"
                        >
                          <p className="mb-1.5 flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.18em] text-primary">
                            <motion.span
                              animate={prefersReducedMotion ? undefined : { opacity: [0.7, 1, 0.7] }}
                              transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
                              className="inline-block size-1.5 rounded-full bg-primary"
                            />
                            Latest insight
                          </p>
                          <p className="text-xs leading-5 text-foreground/90">
                            {insights[0].response}
                          </p>
                          <p className="mt-1.5 text-[10px] text-muted-foreground">
                            on: {insights[0].trigger.slice(0, 80)}
                          </p>
                        </motion.div>
                      )}
                    </AnimatePresence>

                    {/* Unsupported browser */}
                    {webgpu.status === "unsupported" && (
                      <p className="mt-2 text-xs leading-5 text-muted-foreground">
                        In-browser AI requires{" "}
                        <a
                          href="https://caniuse.com/webgpu"
                          target="_blank"
                          rel="noreferrer"
                          className="underline underline-offset-2 hover:text-foreground"
                        >
                          Chrome / Edge 113+
                        </a>{" "}
                        or Firefox Nightly with WebGPU enabled.
                      </p>
                    )}

                    {/* Idle – invite the user to enable */}
                    {webgpu.status === "idle" && (
                      <>
                        <p className="mt-2 text-xs leading-5 text-muted-foreground">
                          Bonsai runs entirely in your browser via WebGPU — no API key or server needed.
                          The model (~500 MB) is downloaded once and cached.
                        </p>
                        <Button
                          type="button"
                          size="sm"
                          className="mt-3 gap-2"
                          onClick={webgpu.load}
                        >
                          <Cpu className="size-4 shrink-0" />
                          Enable browser companion
                        </Button>
                      </>
                    )}

                    {/* Loading / downloading */}
                    {webgpu.status === "loading" && (
                      <div className="mt-3 space-y-2">
                        <ProgressIndicator
                          value={webgpu.progress?.pct ?? undefined}
                          label={
                            webgpu.progress && webgpu.progress.totalBytes > 0
                              ? `${(webgpu.progress.loadedBytes / 1e6).toFixed(0)} MB of ${(webgpu.progress.totalBytes / 1e6).toFixed(0)} MB`
                              : "Downloading Bonsai…"
                          }
                        />
                        <p className="text-[11px] text-muted-foreground">
                          Cached in your browser — won&apos;t re-download next time.
                        </p>
                      </div>
                    )}

                    {/* Ready or generating – show quick-ask interface */}
                    {(webgpu.status === "ready" || webgpu.status === "generating") && (
                      <div className="mt-3 space-y-2">
                        {/* Conversation thread */}
                        {(dockHistory.length > 0 || (webgpu.status === "generating" && webgpu.output)) && (
                          <div className="max-h-52 space-y-2 overflow-y-auto">
                            {dockHistory.map((msg, i) => (
                              <div
                                key={i}
                                className={cn(
                                  "rounded-[0.9rem] px-3 py-2 text-xs leading-5",
                                  msg.role === "user"
                                    ? "ml-4 bg-primary/10 text-foreground"
                                    : "mr-4 border border-white/8 bg-black/20 text-foreground/90",
                                )}
                              >
                                {msg.content}
                              </div>
                            ))}
                            {/* Live streaming token */}
                            {webgpu.status === "generating" && webgpu.output && (
                              <div className="mr-4 rounded-[0.9rem] border border-white/8 bg-black/20 px-3 py-2 text-xs leading-5 text-foreground/90">
                                {webgpu.output}
                                <span className="ml-0.5 inline-block w-1.5 animate-pulse rounded-sm bg-primary align-middle">
                                  &nbsp;
                                </span>
                              </div>
                            )}
                          </div>
                        )}

                        {/* Quick-reflect button */}
                        {webgpu.status === "ready" && dockHistory.length === 0 && (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="w-full justify-start gap-2"
                            onClick={() => webgpu.send(buildReflectionMessages())}
                          >
                            <RefreshCw className="size-4" />
                            Reflect on session
                          </Button>
                        )}

                        {/* Quick-ask input */}
                        <div className="flex gap-2">
                          <Textarea
                            value={quickAsk}
                            onChange={(e) => setQuickAsk(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && !e.shiftKey && quickAsk.trim()) {
                                e.preventDefault();
                                const userContent = quickAsk.trim();
                                const systemMsg = { role: "system", content: "You are METIS, a concise research companion. Be direct. Keep replies under 3 sentences." };
                                const nextHistory = [...dockHistory, { role: "user", content: userContent }];
                                setDockHistory(nextHistory);
                                webgpu.send([systemMsg, ...nextHistory]);
                                setQuickAsk("");
                              }
                            }}
                            placeholder="Ask anything… (Enter to send)"
                            className="min-h-0 resize-none py-1.5 text-xs"
                            disabled={webgpu.status === "generating"}
                            rows={1}
                          />
                          {webgpu.status === "generating" ? (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="shrink-0 self-end"
                              onClick={webgpu.stop}
                              aria-label="Stop generation"
                            >
                              <Square className="size-4" />
                            </Button>
                          ) : (
                            <Button
                              type="button"
                              size="sm"
                              className="shrink-0 self-end"
                              disabled={!quickAsk.trim()}
                              onClick={() => {
                                if (!quickAsk.trim()) return;
                                const userContent = quickAsk.trim();
                                const systemMsg = { role: "system", content: "You are METIS, a concise research companion. Be direct. Keep replies under 3 sentences." };
                                const nextHistory = [...dockHistory, { role: "user", content: userContent }];
                                setDockHistory(nextHistory);
                                webgpu.send([systemMsg, ...nextHistory]);
                                setQuickAsk("");
                              }}
                              aria-label="Send"
                            >
                              <Send className="size-4" />
                            </Button>
                          )}
                        </div>
                        <p className="text-[11px] text-muted-foreground">
                          Running locally · Bonsai 1.7B · WebGPU
                        </p>
                      </div>
                    )}

                    {/* OOM – targeted advice */}
                    {webgpu.status === "oom" && (
                      <div className="mt-2 space-y-2">
                        <div className="flex items-start gap-2 text-xs text-amber-400">
                          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                          <span>
                            GPU memory full. Close other GPU-heavy tabs or browser windows, then retry.
                          </span>
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="gap-2"
                          onClick={webgpu.reset}
                        >
                          <RefreshCw className="size-4" />
                          Retry
                        </Button>
                      </div>
                    )}

                    {/* Generic error */}
                    {webgpu.status === "error" && (
                      <div className="mt-2 space-y-2">
                        <p className="text-xs text-destructive line-clamp-3">
                          {webgpu.error}
                        </p>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="gap-2"
                          onClick={webgpu.reset}
                        >
                          <RefreshCw className="size-4" />
                          Retry
                        </Button>
                      </div>
                    )}
                  </div>
                )}

                {snapshot &&
                snapshot.status.runtime_source !== "dedicated_local" &&
                snapshot.status.recommended_model_name ? (                  <div className="rounded-[1.2rem] border border-primary/20 bg-primary/6 px-3 py-3 backdrop-blur-sm">
                    <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">
                      Lightweight local runtime
                    </p>
                    <p className="mt-1 text-sm leading-6 text-foreground">
                      Recommended: {snapshot.status.recommended_model_name}
                      {snapshot.status.recommended_quant ? ` · ${snapshot.status.recommended_quant}` : ""}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    Install a small dedicated GGUF model so I can handle reflections locally without changing the main chat runtime.
                    </p>
                    <Button
                      type="button"
                      size="sm"
                      className="mt-3 gap-2"
                      onClick={() => void handleBootstrap()}
                      disabled={busyAction !== ""}
                    >
                      {busyAction === "bootstrap" ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <BrainIcon size={16} className="shrink-0" />
                      )}
                      Install Local Companion
                    </Button>
                  </div>
                ) : null}

                {error ? (
                  <p className="text-sm text-destructive">{error}</p>
                ) : null}
              </>
            )}
          </div>
        ) : null}
      </div>
      {showHud && (
        <HermesHud
          snapshot={snapshot}
          thoughtLog={thoughts}
          sessionId={sessionId}
          onClose={() => setShowHud(false)}
        />
      )}
    </aside>
  );
}

function formatAtlasPath(value: string): string {
  const tokens = String(value || "").split(/[\\/]/).filter(Boolean);
  if (tokens.length <= 2) {
    return tokens.join("/");
  }
  return tokens.slice(-2).join("/");
}
