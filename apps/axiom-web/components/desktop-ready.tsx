"use client";

import { useEffect, useState } from "react";
import { getApiBase } from "@/lib/api";
import { AlertCircle, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

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

  useEffect(() => {
    // Only apply in Tauri environment
    if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) {
      setState("ready");
      return;
    }

    let mounted = true;

    async function checkReady() {
      try {
        const baseUrl = await getApiBase();
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

    // Listen for sidecar errors from Tauri
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

  async function handleRetry() {
    setState("loading");
    setErrorMessage(null);
    setRetryCount((c) => c + 1);
  }

  // In web mode, render children immediately
  if (state === "ready") {
    return <>{children}</>;
  }

  // In loading state
  if (state === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4 text-center">
          <Loader2 className="size-8 animate-spin text-primary" />
          <div className="space-y-1">
            <p className="font-medium">Starting Axiom...</p>
            <p className="text-sm text-muted-foreground">
              Initializing local API server
            </p>
          </div>
        </div>
      </div>
    );
  }

  // In error state
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-4 text-center max-w-md px-4">
        <div className="rounded-full bg-destructive/10 p-3">
          <AlertCircle className="size-8 text-destructive" />
        </div>
        <div className="space-y-2">
          <p className="font-semibold text-lg">Unable to Start</p>
          <p className="text-sm text-muted-foreground">
            {errorMessage || "The local API server failed to start. This may be a configuration issue."}
          </p>
        </div>
        <div className="flex gap-2">
          <Button onClick={handleRetry} variant="outline" className="gap-1.5">
            <RefreshCw className="size-4" />
            Try Again
          </Button>
        </div>
        <p className="text-xs text-muted-foreground mt-4">
          If this persists, check the application logs or restart the application.
        </p>
      </div>
    </div>
  );
}
