"use client";

/**
 * React hook that owns the WebGPU companion worker lifecycle.
 *
 * Constraint mitigations baked in:
 *
 * - navigator.gpu guard      — checked at initialisation time (SSR-safe).
 *                              Returns `status: "unsupported"` on older browsers.
 * - Opt-in download          — worker is created only when `load()` is called
 *                              so the ~500 MB network request never fires silently.
 * - Progress reporting       — `progress` streams GB loaded/total for a UI bar.
 * - OOM vs other errors      — `status: "oom"` is returned when the error looks
 *                              like device out-of-memory so the UI can give
 *                              targeted advice ("close other GPU-heavy tabs").
 * - Stop / interrupt         — `stop()` sends an interrupt to the stopper so
 *                              generation ends cleanly after the current token.
 * - Worker cleanup           — worker is terminated on component unmount.
 * - Re-use across re-renders — a single worker instance is kept in a ref;
 *                              `load()` is idempotent if already loaded/loading.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type WebGPUCompanionStatus =
  | "unsupported" // navigator.gpu absent
  | "idle" // ready to load
  | "loading" // downloading / compiling model
  | "ready" // model in VRAM, waiting for input
  | "generating" // token stream in progress
  | "oom" // GPU out of memory
  | "error"; // other failure

export interface WebGPUProgress {
  loadedBytes: number;
  totalBytes: number;
  /** 0 – 100 */
  pct: number;
}

export interface UseWebGPUCompanion {
  status: WebGPUCompanionStatus;
  progress: WebGPUProgress | null;
  /** Streamed generation output, reset on each new `send()` call */
  output: string;
  error: string | null;
  /** Downloads and compiles the model (idempotent) */
  load: () => void;
  /** Sends a chat history to the model; clears previous output */
  send: (messages: Array<{ role: string; content: string }>) => void;
  /** Interrupts the current generation */
  stop: () => void;
  /** Resets error state back to idle so the user can retry */
  reset: () => void;
}

/** Detect WebGPU availability without importing @webgpu/types */
function detectWebGPU(): boolean {
  if (typeof navigator === "undefined") return false; // SSR guard
  return "gpu" in navigator;
}

type WorkerMsg =
  | { type: "progress"; loaded: number; total: number; pct: number }
  | { type: "ready" }
  | { type: "token"; token: string }
  | { type: "done" }
  | { type: "error"; message: string };

const OOM_PATTERN = /out.of.memory|oom|allocation failed|device.lost|not enough memory/i;

export function useWebGPUCompanion(): UseWebGPUCompanion {
  const [status, setStatus] = useState<WebGPUCompanionStatus>(() =>
    detectWebGPU() ? "idle" : "unsupported",
  );
  const [progress, setProgress] = useState<WebGPUProgress | null>(null);
  const [output, setOutput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const workerRef = useRef<Worker | null>(null);

  // Clean up the worker on unmount
  useEffect(() => {
    return () => {
      workerRef.current?.terminate();
      workerRef.current = null;
    };
  }, []);

  const handleError = useCallback((message: string, worker: Worker) => {
    const isOom = OOM_PATTERN.test(message);
    setStatus(isOom ? "oom" : "error");
    setError(message);
    worker.terminate();
    workerRef.current = null;
  }, []);

  const load = useCallback(() => {
    // Idempotent: if we already have a worker (loading or ready), do nothing.
    if (workerRef.current) return;
    if (status !== "idle") return;

    setStatus("loading");
    setProgress(null);
    setError(null);

    const worker = new Worker(new URL("./worker.ts", import.meta.url), {
      type: "module",
    });
    workerRef.current = worker;

    worker.onmessage = (e: MessageEvent<WorkerMsg>) => {
      const msg = e.data;
      switch (msg.type) {
        case "progress":
          setProgress({ loadedBytes: msg.loaded, totalBytes: msg.total, pct: msg.pct });
          break;
        case "ready":
          setStatus("ready");
          setProgress(null);
          break;
        case "token":
          setOutput((prev) => prev + msg.token);
          break;
        case "done":
          setStatus("ready");
          break;
        case "error":
          handleError(msg.message, worker);
          break;
      }
    };

    worker.onerror = (e) => {
      handleError(e.message ?? "Worker error", worker);
    };

    worker.postMessage({ type: "load" });
  }, [status, handleError]);

  const send = useCallback(
    (messages: Array<{ role: string; content: string }>) => {
      if (!workerRef.current || status !== "ready") return;
      setOutput("");
      setError(null);
      setStatus("generating");
      workerRef.current.postMessage({ type: "generate", messages });
    },
    [status],
  );

  const stop = useCallback(() => {
    workerRef.current?.postMessage({ type: "stop" });
  }, []);

  const reset = useCallback(() => {
    if (status !== "oom" && status !== "error") return;
    // Ensure the old worker is gone before allowing a re-load
    workerRef.current?.terminate();
    workerRef.current = null;
    setStatus(detectWebGPU() ? "idle" : "unsupported");
    setError(null);
    setProgress(null);
    setOutput("");
  }, [status]);

  return { status, progress, output, error, load, send, stop, reset };
}
