"use client";

import { useCallback, useState } from "react";

/**
 * Three-step progress state for an index-build job: read files →
 * compute embeddings → save manifest. Each step transitions through
 * idle → active → done in order, except on failure during the save
 * step where it falls back to idle so a retry can re-enter cleanly.
 *
 * Centralising the transitions here keeps the dialog body declarative
 * (`progress.startEmbedding()` rather than `setProgress({reading:
 * "done", embedding: "active", saved: "idle"})`) and makes it
 * impossible to put a downstream step in `done` while an upstream
 * step is still `idle`.
 */
export type BuildStep = "idle" | "active" | "done";

export interface IndexBuildProgressState {
  reading: BuildStep;
  embedding: BuildStep;
  saved: BuildStep;
}

const INITIAL: IndexBuildProgressState = {
  reading: "idle",
  embedding: "idle",
  saved: "idle",
};

export interface IndexBuildProgressHandle {
  state: IndexBuildProgressState;
  reset(): void;
  /** Start the read-files step. Earlier state is discarded. */
  startReading(): void;
  /** Mark read complete, start embeddings. */
  startEmbedding(): void;
  /** Mark embeddings complete, start save. */
  startSaving(): void;
  /** Mark save complete — terminal success state. */
  finishSaving(): void;
  /**
   * Save attempt failed. Reverts the saved step to idle if it was
   * mid-flight; leaves earlier completed steps untouched so a retry
   * doesn't replay the read + embed cost.
   */
  failSaving(): void;
}

export function useIndexBuildProgress(): IndexBuildProgressHandle {
  const [state, setState] = useState<IndexBuildProgressState>(INITIAL);

  const reset = useCallback(() => setState(INITIAL), []);
  const startReading = useCallback(
    () => setState({ reading: "active", embedding: "idle", saved: "idle" }),
    [],
  );
  const startEmbedding = useCallback(
    () => setState({ reading: "done", embedding: "active", saved: "idle" }),
    [],
  );
  const startSaving = useCallback(
    () => setState({ reading: "done", embedding: "done", saved: "active" }),
    [],
  );
  const finishSaving = useCallback(
    () => setState({ reading: "done", embedding: "done", saved: "done" }),
    [],
  );
  const failSaving = useCallback(() => {
    setState((current) =>
      current.saved === "active"
        ? { reading: "done", embedding: "done", saved: "idle" }
        : current,
    );
  }, []);

  return {
    state,
    reset,
    startReading,
    startEmbedding,
    startSaving,
    finishSaving,
    failSaving,
  };
}
