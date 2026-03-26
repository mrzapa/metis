"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getApiBase } from "@/lib/api";
import { LaunchStage } from "@/components/shell/launch-stage";
import { Button } from "@/components/ui/button";
import { AnimatedLucideIcon } from "@/components/ui/animated-lucide-icon";
import { AlertCircle, CheckCircle2, Loader2, RefreshCw } from "lucide-react";

export type DesktopReadyState = "loading" | "ready" | "error";

interface DesktopReadyGuardProps {
  children: React.ReactNode;
}

/**
 * DesktopReadyGuard monitors the sidecar/API readiness state in Tauri builds.
 * 
 * In desktop mode:
 *   - Shows a loading spinner while the sidecar initializes
 *   - Shows an error screen if the sidecar fails to start
 *   - Transitions to the normal UI once the API is healthy
 * 
 * In web/dev mode:
 *   - Passes through immediately (no effect)
 */
export function DesktopReadyGuard({ children }: DesktopReadyGuardProps) {
  const [state, setState] = useState<DesktopReadyState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [launchPhase, setLaunchPhase] = useState(0);

  useEffect(() => {
    if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) {
      setState("ready");
      return;
    }

    let mounted = true;

    async function checkReady() {
      try {
        await getApiBase();
        if (mounted) {
          setState("ready");
        }
      } catch {
        if (mounted) {
          setState("error");
          setErrorMessage("Failed to connect to the API server");
        }
      }
    }

    checkReady();

    async function setupListener() {
      try {
        const { listen } = await import("@tauri-apps/api/event");
        const unlisten = await listen<string>("sidecar-error", (event) => {
          if (mounted) {
            setState("error");
            setErrorMessage(event.payload);
          }
        });
        return unlisten;
      } catch {
        // Not in Tauri environment or listen failed
        return undefined;
      }
    }

    const promise = setupListener();

    return () => {
      mounted = false;
      promise.then((unlisten) => unlisten?.());
    };
  }, [retryCount]);

  useEffect(() => {
    if (state !== "loading") {
      return;
    }
    const id = window.setInterval(() => {
      setLaunchPhase((current) => (current + 1) % 3);
    }, 1400);
    return () => window.clearInterval(id);
  }, [state]);

  async function handleRetry() {
    setState("loading");
    setErrorMessage(null);
    setLaunchPhase(0);
    setRetryCount((c) => c + 1);
  }

  if (state === "ready") {
    return <>{children}</>;
  }

  const phases = [
    "Bootstrapping the local sidecar",
    "Negotiating a local API port",
    "Verifying workspace health",
  ];

  if (state === "loading") {
    return (
      <LaunchStage
        eyebrow="METIS Launch"
        title="Bringing your local workspace online."
        description="METIS is starting its desktop sidecar, checking the local API, and preparing the workspace shell."
        statusLabel="Starting services"
        statusTone="checking"
        aside={
          <div className="space-y-4">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
                Launch phases
              </p>
              <div className="mt-4 space-y-3">
                {phases.map((phase, index) => {
                  const active = index === launchPhase;
                  const completed = index < launchPhase;
                  return (
                    <div
                      key={phase}
                      className="flex items-center gap-3 rounded-2xl border border-white/8 bg-black/10 px-4 py-3"
                    >
                      {completed ? (
                        <AnimatedLucideIcon icon={CheckCircle2} className="size-4 text-emerald-300" />
                      ) : active ? (
                        <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4 text-primary" />
                      ) : (
                        <span className="size-4 rounded-full border border-white/12 bg-white/4" />
                      )}
                      <span className={active ? "text-foreground" : "text-muted-foreground"}>
                        {phase}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
            <p className="text-sm leading-7 text-muted-foreground">
              This usually takes a few seconds. If it stalls, diagnostics stays available and you can retry without restarting the whole UI.
            </p>
          </div>
        }
      />
    );
  }

  return (
    <LaunchStage
      eyebrow="METIS Launch"
      title="The local API did not come up cleanly."
      description="The desktop shell is running, but the local service failed its startup checks. You can retry immediately or inspect diagnostics for logs and version compatibility."
      statusLabel="Launch interrupted"
      statusTone="disconnected"
      actions={
        <>
          <Button onClick={handleRetry} variant="outline" className="gap-2">
            <AnimatedLucideIcon icon={RefreshCw} mode="hoverLift" className="size-4" />
            Try again
          </Button>
          <Link href="/diagnostics">
            <Button>Open diagnostics</Button>
          </Link>
        </>
      }
      aside={
        <div className="space-y-4">
          <div className="inline-flex size-12 items-center justify-center rounded-2xl bg-destructive/10 text-destructive">
            <AnimatedLucideIcon icon={AlertCircle} mode="idlePulse" className="size-6" />
          </div>
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
              Startup message
            </p>
            <p className="mt-3 text-sm leading-7 text-muted-foreground">
              {errorMessage || "The local API server failed to start. This is usually caused by configuration or compatibility issues."}
            </p>
          </div>
          <p className="text-sm leading-7 text-muted-foreground">
            Diagnostics surfaces safe settings, versions, and a redacted log tail so startup failures are easier to recover from.
          </p>
        </div>
      }
    />
  );
}
