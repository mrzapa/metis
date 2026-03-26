"use client";

import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { Textarea } from "@/components/ui/textarea";
import { StatusPill } from "@/components/shell/status-pill";
import { useArrowState } from "@/hooks/use-arrow-state";
import {
  buildIndexStream,
  fetchIndexes,
  fetchSettings,
  uploadFiles,
  type IndexBuildResult,
  type IndexSummary,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  AlertCircle,
  CheckCircle2,
  Circle,
  Database,
  FolderOpen,
  Loader2,
  UploadCloud,
  X,
} from "lucide-react";

type BuildStep = "idle" | "active" | "done";

interface ProgressState {
  reading: BuildStep;
  embedding: BuildStep;
  saved: BuildStep;
}

const INITIAL_PROGRESS: ProgressState = {
  reading: "idle",
  embedding: "idle",
  saved: "idle",
};

interface IndexBuildStudioProps {
  settingsOverrides?: Record<string, unknown>;
  showExistingIndexes?: boolean;
  onBuildComplete?: (result: IndexBuildResult) => void;
  className?: string;
}

export function IndexBuildStudio({
  settingsOverrides,
  showExistingIndexes = true,
  onBuildComplete,
  className,
}: IndexBuildStudioProps) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDesktop, setIsDesktop] = useArrowState(false);
  const [tab, setTab] = useArrowState<"upload" | "paths" | "desktop">("upload");
  const [pathsConsent, setPathsConsent] = useArrowState(false);

  const [selectedFiles, setSelectedFiles] = useArrowState<File[]>([]);
  const [uploadedPaths, setUploadedPaths] = useArrowState<string[]>([]);
  const [uploading, setUploading] = useArrowState(false);
  const [uploadError, setUploadError] = useArrowState<string | null>(null);

  const [rawPaths, setRawPaths] = useArrowState("");
  const [desktopPaths, setDesktopPaths] = useArrowState<string[]>([]);
  const [pickError, setPickError] = useArrowState<string | null>(null);

  const [building, setBuilding] = useArrowState(false);
  const [buildError, setBuildError] = useArrowState<string | null>(null);
  const [progress, setProgress] = useArrowState<ProgressState>(INITIAL_PROGRESS);
  const [buildResult, setBuildResult] = useArrowState<IndexBuildResult | null>(null);

  const [indexes, setIndexes] = useArrowState<IndexSummary[]>([]);
  const [loadingIndexes, setLoadingIndexes] = useArrowState(false);
  const [indexError, setIndexError] = useArrowState<string | null>(null);
  const [displayCount, setDisplayCount] = useArrowState(15);
  const bottomSentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
      setIsDesktop(true);
      setTab("desktop");
    }
  }, [setIsDesktop, setTab]);

  const readyPaths =
    tab === "upload"
      ? uploadedPaths
      : tab === "desktop"
        ? desktopPaths
        : rawPaths
            .split("\n")
            .map((p) => p.trim())
            .filter(Boolean);

  const openChatWithIndex = useCallback(
    (manifestPath: string, label: string) => {
      localStorage.setItem(
        "axiom_active_index",
        JSON.stringify({ manifest_path: manifestPath, label }),
      );
      router.push("/chat");
    },
    [router],
  );

  const loadIndexes = useCallback(() => {
    if (!showExistingIndexes) {
      return;
    }
    setLoadingIndexes(true);
    setIndexError(null);
    fetchIndexes()
      .then(setIndexes)
      .catch((err) =>
        setIndexError(err instanceof Error ? err.message : "Failed to load indexes"),
      )
      .finally(() => setLoadingIndexes(false));
  }, [setIndexError, setIndexes, setLoadingIndexes, showExistingIndexes]);

  useEffect(() => {
    loadIndexes();
  }, [loadIndexes]);

  // Infinite scroll for indexes list
  useEffect(() => {
    const sentinel = bottomSentinelRef.current;
    if (!sentinel) return;
    if (displayCount >= indexes.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setDisplayCount((prev) => prev + 15);
        }
      },
      { root: null, rootMargin: "0px 0px 250px 0px", threshold: 0 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [displayCount, indexes.length, setDisplayCount]);

  async function handlePickFiles() {
    setPickError(null);
    try {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const selected = await open({ multiple: true });
      if (selected === null) return;
      const paths = Array.isArray(selected) ? selected : [selected];
      setDesktopPaths(paths);
    } catch (err) {
      setPickError(err instanceof Error ? err.message : "File picker failed");
    }
  }

  async function handleUpload() {
    if (!selectedFiles.length) return;
    setUploading(true);
    setUploadError(null);
    try {
      const { paths } = await uploadFiles(selectedFiles);
      setUploadedPaths(paths);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleBuild() {
    if (!readyPaths.length) return;
    setBuilding(true);
    setBuildError(null);
    setBuildResult(null);
    setProgress({ reading: "active", embedding: "idle", saved: "idle" });

    try {
      const settings =
        settingsOverrides && Object.keys(settingsOverrides).length > 0
          ? settingsOverrides
          : await fetchSettings();

      const result = await buildIndexStream(readyPaths, settings, (event) => {
        const type = String(event.type ?? "");
        if (type === "status") {
          const text = String(event.text ?? "").toLowerCase();
          if (text.includes("embedding")) {
            setProgress({ reading: "done", embedding: "active", saved: "idle" });
          }
        }
      });

      setProgress({ reading: "done", embedding: "done", saved: "done" });
      setBuildResult(result);
      onBuildComplete?.(result);
      loadIndexes();
    } catch (err) {
      setBuildError(err instanceof Error ? err.message : "Build failed");
    } finally {
      setBuilding(false);
    }
  }

  return (
    <div className={cn("space-y-6", className)}>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.08fr)_minmax(320px,0.92fr)]">
        <section className="glass-panel rounded-[1.7rem] p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-display text-2xl font-semibold tracking-[-0.04em] text-foreground">
                Bring in your source material
              </h2>
              <p className="mt-2 text-sm leading-7 text-muted-foreground">
                Upload files, pick local documents in desktop mode, or provide server-readable paths.
              </p>
            </div>
            <StatusPill
              label={`${readyPaths.length} ready`}
              tone={readyPaths.length > 0 ? "connected" : "neutral"}
            />
          </div>

          <div className="mt-6 flex flex-wrap gap-2">
            {isDesktop ? (
              <button
                type="button"
                onClick={() => setTab("desktop")}
                className={cn(
                  "cursor-pointer rounded-full px-4 py-2 text-sm font-medium transition-all",
                  tab === "desktop"
                    ? "bg-primary/16 text-primary"
                    : "bg-white/6 text-muted-foreground hover:bg-white/10 hover:text-foreground",
                )}
              >
                Choose files
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => setTab("upload")}
              className={cn(
                "cursor-pointer rounded-full px-4 py-2 text-sm font-medium transition-all",
                tab === "upload"
                  ? "bg-primary/16 text-primary"
                  : "bg-white/6 text-muted-foreground hover:bg-white/10 hover:text-foreground",
              )}
            >
              Upload files
            </button>
            <button
              type="button"
              onClick={() => setTab("paths")}
              className={cn(
                "cursor-pointer rounded-full px-4 py-2 text-sm font-medium transition-all",
                tab === "paths"
                  ? "bg-primary/16 text-primary"
                  : "bg-white/6 text-muted-foreground hover:bg-white/10 hover:text-foreground",
              )}
            >
              Local paths
            </button>
          </div>

          <div className="mt-5 rounded-[1.5rem] border border-white/8 bg-black/10 p-4 sm:p-5">
            {tab === "desktop" ? (
              <div className="space-y-4">
                <Button variant="outline" onClick={handlePickFiles} className="gap-2">
                  <FolderOpen className="size-4" />
                  Choose files
                </Button>

                {pickError ? (
                  <p className="flex items-center gap-2 text-sm text-destructive">
                    <AlertCircle className="size-4" />
                    {pickError}
                  </p>
                ) : null}

                {desktopPaths.length > 0 ? (
                  <div className="space-y-2">
                    {desktopPaths.map((path, index) => (
                      <div
                        key={`${path}-${index}`}
                        className="flex items-center justify-between gap-3 rounded-2xl border border-white/8 bg-white/4 px-4 py-3 text-sm"
                      >
                        <span className="truncate font-mono text-xs text-muted-foreground">{path}</span>
                        <button
                          type="button"
                          onClick={() => setDesktopPaths((current) => current.filter((_, entryIndex) => entryIndex !== index))}
                          className="cursor-pointer text-muted-foreground transition-colors hover:text-foreground"
                        >
                          <X className="size-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Use the native picker to bring in PDFs, notes, and folders from your machine.
                  </p>
                )}
              </div>
            ) : null}

            {tab === "upload" ? (
              <div className="space-y-4">
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="cursor-pointer rounded-[1.5rem] border border-dashed border-primary/28 bg-primary/6 px-6 py-10 text-center transition-all duration-200 hover:border-primary/46 hover:bg-primary/10"
                >
                  <UploadCloud className="mx-auto size-10 text-primary" />
                  <p className="mt-4 font-medium text-foreground">Drop or select files to index</p>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Great for PDFs, Markdown, docs, transcripts, and mixed research sets.
                  </p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    className="hidden"
                    onChange={(event) => {
                      setSelectedFiles(Array.from(event.target.files ?? []));
                      setUploadedPaths([]);
                      setUploadError(null);
                    }}
                  />
                </div>

                {selectedFiles.length > 0 ? (
                  <div className="space-y-2">
                    {selectedFiles.map((file, index) => (
                      <div
                        key={`${file.name}-${index}`}
                        className="flex items-center justify-between gap-3 rounded-2xl border border-white/8 bg-white/4 px-4 py-3 text-sm"
                      >
                        <span className="truncate">{file.name}</span>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedFiles((current) => current.filter((_, entryIndex) => entryIndex !== index));
                            setUploadedPaths([]);
                          }}
                          className="cursor-pointer text-muted-foreground transition-colors hover:text-foreground"
                        >
                          <X className="size-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                ) : null}

                {uploadError ? (
                  <p className="flex items-center gap-2 text-sm text-destructive">
                    <AlertCircle className="size-4" />
                    {uploadError}
                  </p>
                ) : null}

                {uploadedPaths.length > 0 ? (
                  <p className="flex items-center gap-2 text-sm text-emerald-300">
                    <CheckCircle2 className="size-4" />
                    {uploadedPaths.length} file{uploadedPaths.length === 1 ? "" : "s"} uploaded and ready.
                  </p>
                ) : null}

                {selectedFiles.length > 0 && uploadedPaths.length === 0 ? (
                  <Button onClick={handleUpload} disabled={uploading} className="gap-2">
                    {uploading ? <Loader2 className="size-4 animate-spin" /> : <UploadCloud className="size-4" />}
                    {uploading ? "Uploading..." : "Upload files"}
                  </Button>
                ) : null}
              </div>
            ) : null}

            {tab === "paths" ? (
              <div className="space-y-4">
                <div className="rounded-[1.35rem] border border-chart-4/20 bg-chart-4/10 px-4 py-3 text-sm leading-7 text-chart-4">
                  Use this when the METIS API can already read the filesystem paths directly, such as a desktop sidecar or self-hosted workspace.
                </div>

                <label className="flex cursor-pointer items-center gap-3 text-sm text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={pathsConsent}
                    onChange={(event) => setPathsConsent(event.target.checked)}
                    className="size-4 rounded accent-primary"
                  />
                  I understand these paths must be accessible to the local API.
                </label>

                {pathsConsent ? (
                  <Textarea
                    placeholder={"/home/user/docs/report.pdf\n/home/user/docs/notes.md"}
                    value={rawPaths}
                    onChange={(event) => setRawPaths(event.target.value)}
                    rows={6}
                    className="font-mono text-xs"
                  />
                ) : null}
              </div>
            ) : null}
          </div>
        </section>

        <aside className="space-y-4">
          <section className="glass-panel rounded-[1.7rem] p-5 sm:p-6">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="font-display text-2xl font-semibold tracking-[-0.04em] text-foreground">
                  Build your first index
                </h2>
                <p className="mt-2 text-sm leading-7 text-muted-foreground">
                  Turn the selected documents into a searchable knowledge base for chat and research mode.
                </p>
              </div>
              <StatusPill
                label={building ? "Building" : readyPaths.length > 0 ? "Ready to build" : "Waiting on docs"}
                tone={building ? "checking" : readyPaths.length > 0 ? "connected" : "neutral"}
                animate={building}
              />
            </div>

            <div className="mt-5 rounded-[1.4rem] border border-white/8 bg-black/10 p-4">
              <p className="text-sm text-muted-foreground">
                {readyPaths.length > 0
                  ? `${readyPaths.length} document${readyPaths.length === 1 ? "" : "s"} prepared`
                  : "Choose at least one file or path to continue."}
              </p>

              <Button
                onClick={handleBuild}
                disabled={building || readyPaths.length === 0}
                className="mt-4 gap-2"
              >
                {building ? <Loader2 className="size-4 animate-spin" /> : <Database className="size-4" />}
                {building ? "Building..." : "Build index"}
              </Button>

              {building || progress.reading !== "idle" ? (
                <div className="mt-5 space-y-3">
                  {(
                    [
                      ["reading", "Reading documents"],
                      ["embedding", "Computing embeddings"],
                      ["saved", "Saved and ready"],
                    ] as const
                  ).map(([key, label]) => (
                    <div key={key} className="flex items-center gap-3 text-sm">
                      <AnimatePresence mode="wait" initial={false}>
                        {progress[key] === "done" ? (
                          <motion.span
                            key="done"
                            className="flex"
                            initial={{ scale: 0.6, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.6, opacity: 0 }}
                            transition={{ duration: 0.18, ease: "easeOut" }}
                          >
                            <CheckCircle2 className="size-4 text-emerald-300" />
                          </motion.span>
                        ) : progress[key] === "active" ? (
                          <motion.span
                            key="active"
                            className="flex"
                            initial={{ scale: 0.6, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.6, opacity: 0 }}
                            transition={{ duration: 0.18, ease: "easeOut" }}
                          >
                            <Loader2 className="size-4 animate-spin text-primary" />
                          </motion.span>
                        ) : (
                          <motion.span
                            key="idle"
                            className="flex"
                            initial={{ scale: 0.6, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.6, opacity: 0 }}
                            transition={{ duration: 0.18, ease: "easeOut" }}
                          >
                            <Circle className="size-4 text-muted-foreground/40" />
                          </motion.span>
                        )}
                      </AnimatePresence>
                      <span
                        className={cn(
                          progress[key] === "done"
                            ? "text-foreground"
                            : progress[key] === "active"
                              ? "font-medium text-foreground"
                              : "text-muted-foreground",
                        )}
                      >
                        {label}
                      </span>
                    </div>
                  ))}
                </div>
              ) : null}

              {buildError ? (
                <p className="mt-4 flex items-center gap-2 text-sm text-destructive">
                  <AlertCircle className="size-4" />
                  {buildError}
                </p>
              ) : null}
            </div>

            {buildResult ? (
              <div className="mt-4 rounded-[1.4rem] border border-emerald-400/20 bg-emerald-400/10 p-4">
                <p className="font-medium text-emerald-200">Index ready: {buildResult.index_id}</p>
                <p className="mt-2 text-sm text-emerald-100/85">
                  {buildResult.document_count} document{buildResult.document_count === 1 ? "" : "s"} and{" "}
                  {buildResult.chunk_count} chunks are available.
                </p>
                {onBuildComplete ? (
                  <p className="mt-3 text-sm text-emerald-100/85">
                    This index is ready for the final launch step.
                  </p>
                ) : (
                  <Button
                    onClick={() => openChatWithIndex(buildResult.manifest_path, buildResult.index_id)}
                    className="mt-4 gap-2"
                    size="sm"
                  >
                    Open in Chat
                  </Button>
                )}
              </div>
            ) : null}
          </section>

          <section className="glass-panel rounded-[1.7rem] p-5 sm:p-6">
            <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground">
              Recommended flow
            </p>
            <div className="mt-4 space-y-3 text-sm leading-7 text-muted-foreground">
              <p>1. Add the smallest useful set of files first so the first run feels quick.</p>
              <p>2. Build the index and open chat immediately to validate retrieval quality.</p>
              <p>3. Add more documents later once the initial workflow feels solid.</p>
            </div>
          </section>
        </aside>
      </div>

      {showExistingIndexes ? (
        <section className="glass-panel rounded-[1.7rem] p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-display text-2xl font-semibold tracking-[-0.04em] text-foreground">
                Existing indexes
              </h2>
              <p className="mt-2 text-sm leading-7 text-muted-foreground">
                Reuse a prior index or jump straight into a grounded chat session.
              </p>
            </div>
            <StatusPill
              label={loadingIndexes ? "Loading" : `${indexes.length} available`}
              tone={loadingIndexes ? "checking" : indexes.length > 0 ? "connected" : "neutral"}
              animate={loadingIndexes}
            />
          </div>

          <div className="mt-5">
            {loadingIndexes ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                Loading indexes...
              </div>
            ) : null}

            {!loadingIndexes && indexError ? (
              <div className="flex items-center gap-2 text-sm text-destructive">
                <AlertCircle className="size-4" />
                {indexError}
              </div>
            ) : null}

            {!loadingIndexes && !indexError && indexes.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No indexes yet. Build one above to unlock grounded chat.
              </p>
            ) : null}

            {!loadingIndexes && !indexError && indexes.length > 0 ? (
              <>
                <div className="space-y-3">
                  {indexes.slice(0, displayCount).map((index) => (
                    <div
                      key={index.index_id}
                      className="flex flex-col gap-4 rounded-[1.4rem] border border-white/8 bg-black/10 p-4 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="truncate font-medium text-foreground">{index.index_id}</span>
                          <Badge variant="outline" className="text-[10px]">
                            {index.backend}
                          </Badge>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
                          <span>
                            {index.document_count} doc{index.document_count === 1 ? "" : "s"}
                          </span>
                          <span>{index.chunk_count} chunks</span>
                          <span>{formatDate(index.created_at)}</span>
                        </div>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        className="sm:shrink-0"
                        onClick={() => openChatWithIndex(index.manifest_path, index.index_id)}
                      >
                        Use in Chat
                      </Button>
                    </div>
                  ))}
                  <div ref={bottomSentinelRef} className="h-0" aria-hidden="true" />
                </div>
                {displayCount < indexes.length ? (
                  <div className="mt-3 flex items-center justify-center gap-1.5 py-3 text-[11px] text-muted-foreground">
                    <Loader2 className="size-3 animate-spin" />
                    Loading more indexes…
                  </div>
                ) : null}
              </>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}
