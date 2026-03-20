"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  bootstrapAssistant,
  clearAssistantMemory,
  fetchAssistant,
  reflectAssistant,
  updateAssistant,
  type AssistantSnapshot,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  Bot,
  Brain,
  ChevronDown,
  ChevronUp,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  Trash2,
} from "lucide-react";

interface AxiomCompanionDockProps {
  sessionId?: string | null;
  runId?: string | null;
  className?: string;
}

export function AxiomCompanionDock({
  sessionId,
  runId,
  className,
}: AxiomCompanionDockProps) {
  const [snapshot, setSnapshot] = useState<AssistantSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<"" | "toggle" | "reflect" | "clear" | "bootstrap">("");
  const [showWhy, setShowWhy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);
  const previousContextRef = useRef<{ sessionId?: string | null; runId?: string | null } | null>(null);

  async function load(autoBootstrap = true) {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
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
  }

  useEffect(() => {
    const hasPreviousContext = previousContextRef.current !== null;
    previousContextRef.current = { sessionId, runId };
    void load(!hasPreviousContext);
  }, [sessionId, runId]);

  const latestMemory = useMemo(
    () => snapshot?.memory?.[0] ?? null,
    [snapshot],
  );
  const minimized = Boolean(snapshot?.identity.minimized);

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
        "pointer-events-auto fixed bottom-4 right-4 z-40 w-[min(24rem,calc(100vw-2rem))]",
        className,
      )}
      aria-label="Axiom companion"
    >
      <div className="glass-panel-strong rounded-[1.6rem] border border-white/10 shadow-2xl shadow-black/30">
        <div className="flex items-center gap-3 border-b border-white/8 px-4 py-3">
          <span className="flex size-9 items-center justify-center rounded-full bg-primary/15 text-primary">
            <Bot className="size-4" />
          </span>
          <div className="min-w-0">
            <p className="truncate font-display text-lg font-semibold tracking-[-0.03em] text-foreground">
              {snapshot?.identity.name ?? "Axiom"}
            </p>
            <p className="truncate text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              {snapshot?.status.runtime_source === "dedicated_local"
                ? "Dedicated local companion"
                : "Companion overlay"}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void handleMinimizeToggle()}
            className="ml-auto rounded-full p-1.5 text-muted-foreground transition-colors hover:bg-white/8 hover:text-foreground"
            aria-label={minimized ? "Expand companion" : "Minimize companion"}
          >
            {minimized ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
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
                  <div className="rounded-[1.15rem] border border-white/8 bg-black/10 px-3 py-2.5">
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
                    <Brain className="size-4" />
                    Refresh
                  </Button>
                </div>

                {snapshot &&
                snapshot.status.runtime_source !== "dedicated_local" &&
                snapshot.status.recommended_model_name ? (
                  <div className="rounded-[1.2rem] border border-primary/20 bg-primary/8 px-3 py-3">
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
                        <Brain className="size-4" />
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
        ) : (
          <div className="px-4 py-3 text-sm text-muted-foreground">
            {snapshot?.status.latest_summary || "Companion minimized"}
          </div>
        )}
      </div>
    </aside>
  );
}
