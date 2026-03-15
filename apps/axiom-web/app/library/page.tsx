"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  buildIndexStream,
  fetchIndexes,
  fetchSettings,
  uploadFiles,
} from "@/lib/api";
import type { IndexBuildResult, IndexSummary } from "@/lib/api";
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Circle,
  Database,
  FolderOpen,
  Loader2,
  UploadCloud,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";

type BuildStep = "idle" | "active" | "done";

interface ProgressState {
  started: BuildStep;
  reading: BuildStep;
  embedding: BuildStep;
  saved: BuildStep;
}

const INITIAL_PROGRESS: ProgressState = {
  started: "idle",
  reading: "idle",
  embedding: "idle",
  saved: "idle",
};

export default function LibraryPage() {
  const router = useRouter();

  // --- desktop detection (SSR-safe; Tauri v2 injects __TAURI_INTERNALS__) ---
  const [isDesktop, setIsDesktop] = useState(false);
  useEffect(() => {
    if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
      setIsDesktop(true);
      setTab("desktop");
    }
  }, []);

  // --- tab state ---
  const [tab, setTab] = useState<"upload" | "paths" | "desktop">("upload");
  const [pathsConsent, setPathsConsent] = useState(false);

  // --- upload tab ---
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadedPaths, setUploadedPaths] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // --- paths tab ---
  const [rawPaths, setRawPaths] = useState("");

  // --- desktop tab ---
  const [desktopPaths, setDesktopPaths] = useState<string[]>([]);
  const [pickError, setPickError] = useState<string | null>(null);

  // --- ready paths (for building) ---
  const readyPaths =
    tab === "upload"
      ? uploadedPaths
      : tab === "desktop"
        ? desktopPaths
        : rawPaths
            .split("\n")
            .map((p) => p.trim())
            .filter(Boolean);

  // --- build state ---
  const [building, setBuilding] = useState(false);
  const [buildError, setBuildError] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressState>(INITIAL_PROGRESS);
  const [buildResult, setBuildResult] = useState<IndexBuildResult | null>(null);

  // --- index list ---
  const [indexes, setIndexes] = useState<IndexSummary[]>([]);
  const [loadingIndexes, setLoadingIndexes] = useState(false);
  const [indexError, setIndexError] = useState<string | null>(null);

  const loadIndexes = useCallback(() => {
    setLoadingIndexes(true);
    setIndexError(null);
    fetchIndexes()
      .then(setIndexes)
      .catch((err) =>
        setIndexError(err instanceof Error ? err.message : "Failed to load indexes")
      )
      .finally(() => setLoadingIndexes(false));
  }, []);

  useEffect(() => {
    loadIndexes();
  }, [loadIndexes]);

  // --- desktop file-picker handler ---
  async function handlePickFiles() {
    setPickError(null);
    try {
      const { open } = await import("@tauri-apps/plugin-dialog");
      const selected = await open({ multiple: true });
      if (selected === null) return; // user cancelled
      const paths = Array.isArray(selected) ? selected : [selected];
      setDesktopPaths(paths);
    } catch (err) {
      setPickError(err instanceof Error ? err.message : "File picker failed");
    }
  }

  // --- upload handler ---
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

  // --- build handler ---
  async function handleBuild() {
    if (!readyPaths.length) return;
    setBuilding(true);
    setBuildError(null);
    setBuildResult(null);
    setProgress({ started: "active", reading: "idle", embedding: "idle", saved: "idle" });

    try {
      const settings = await fetchSettings();
      const result = await buildIndexStream(readyPaths, settings, (event) => {
        const type = event.type as string;
        if (type === "build_started") {
          setProgress({ started: "done", reading: "active", embedding: "idle", saved: "idle" });
        } else if (type === "status") {
          const text = String(event.text ?? "");
          if (text.toLowerCase().includes("embedding")) {
            setProgress({ started: "done", reading: "done", embedding: "active", saved: "idle" });
          } else if (text.toLowerCase().includes("reading") || text.toLowerCase().includes("loading") || text.toLowerCase().includes("preparing")) {
            setProgress((p) =>
              p.embedding === "idle" && p.reading === "idle"
                ? { ...p, started: "done", reading: "active" }
                : p
            );
          }
        }
      });
      setProgress({ started: "done", reading: "done", embedding: "done", saved: "done" });
      setBuildResult(result);
      loadIndexes();
    } catch (err) {
      setBuildError(err instanceof Error ? err.message : "Build failed");
      setProgress((p) => ({ ...p }));
    } finally {
      setBuilding(false);
    }
  }

  function handleUseInChat(idx: IndexSummary) {
    localStorage.setItem(
      "axiom_active_index",
      JSON.stringify({ manifest_path: idx.manifest_path, label: idx.index_id })
    );
    router.push("/chat");
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Nav */}
      <header className="flex h-12 items-center gap-4 border-b px-6">
        <Link href="/" className="text-sm font-semibold tracking-tight">
          Axiom
        </Link>
        <ChevronRight className="size-3.5 text-muted-foreground" />
        <span className="text-sm text-muted-foreground">Library</span>
        <div className="ml-auto flex items-center gap-4">
          <Link
            href="/settings"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            Settings
          </Link>
          <Link
            href="/chat"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            Chat →
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-2xl space-y-8 px-4 py-8">
        {/* Section A — Add documents */}
        <section className="space-y-4">
          <h2 className="text-lg font-semibold">Add documents</h2>

          {/* Tab selector */}
          <div className="flex gap-1 rounded-lg border p-1 w-fit">
            {isDesktop && (
              <button
                type="button"
                onClick={() => setTab("desktop")}
                className={cn(
                  "rounded px-3 py-1 text-sm font-medium transition-colors",
                  tab === "desktop"
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                Choose files
              </button>
            )}
            <button
              type="button"
              onClick={() => setTab("upload")}
              className={cn(
                "rounded px-3 py-1 text-sm font-medium transition-colors",
                tab === "upload"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              Upload files
            </button>
            <button
              type="button"
              onClick={() => setTab("paths")}
              className={cn(
                "rounded px-3 py-1 text-sm font-medium transition-colors",
                tab === "paths"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              Local paths
            </button>
          </div>

          {/* Desktop tab — native file picker (Tauri only) */}
          {tab === "desktop" && (
            <div className="space-y-3">
              <Button
                variant="outline"
                onClick={handlePickFiles}
                className="gap-1.5"
              >
                <FolderOpen className="size-4" />
                Choose files…
              </Button>

              {pickError && (
                <p className="flex items-center gap-1.5 text-sm text-destructive">
                  <AlertCircle className="size-3.5" />
                  {pickError}
                </p>
              )}

              {desktopPaths.length > 0 && (
                <div className="space-y-1">
                  {desktopPaths.map((p, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between rounded border px-3 py-1.5 text-sm font-mono"
                    >
                      <span className="truncate text-xs">{p}</span>
                      <button
                        type="button"
                        onClick={() =>
                          setDesktopPaths((prev) => prev.filter((_, j) => j !== i))
                        }
                      >
                        <X className="size-3.5 text-muted-foreground hover:text-foreground" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Upload tab */}
          {tab === "upload" && (
            <div className="space-y-3">
              {/* Drop zone */}
              <div
                onClick={() => fileInputRef.current?.click()}
                className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed border-muted-foreground/30 px-6 py-8 text-center transition-colors hover:border-primary/50 hover:bg-muted/30"
              >
                <UploadCloud className="size-8 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  Click to select files
                </p>
                <p className="text-xs text-muted-foreground">
                  Any document format (txt, md, pdf, docx, …)
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    setSelectedFiles(Array.from(e.target.files ?? []));
                    setUploadedPaths([]);
                    setUploadError(null);
                  }}
                />
              </div>

              {/* Selected file list */}
              {selectedFiles.length > 0 && (
                <div className="space-y-1">
                  {selectedFiles.map((f, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between rounded border px-3 py-1.5 text-sm"
                    >
                      <span className="truncate">{f.name}</span>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedFiles((prev) => prev.filter((_, j) => j !== i));
                          setUploadedPaths([]);
                        }}
                      >
                        <X className="size-3.5 text-muted-foreground hover:text-foreground" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {uploadError && (
                <p className="flex items-center gap-1.5 text-sm text-destructive">
                  <AlertCircle className="size-3.5" />
                  {uploadError}
                </p>
              )}

              {uploadedPaths.length > 0 && (
                <p className="flex items-center gap-1.5 text-sm text-green-600 dark:text-green-400">
                  <CheckCircle2 className="size-3.5" />
                  {uploadedPaths.length} file{uploadedPaths.length !== 1 ? "s" : ""} uploaded
                </p>
              )}

              {selectedFiles.length > 0 && uploadedPaths.length === 0 && (
                <Button
                  size="sm"
                  onClick={handleUpload}
                  disabled={uploading}
                  className="gap-1.5"
                >
                  {uploading ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <UploadCloud className="size-3.5" />
                  )}
                  {uploading ? "Uploading…" : "Upload files"}
                </Button>
              )}
            </div>
          )}

          {/* Paths tab */}
          {tab === "paths" && (
            <div className="space-y-3">
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-400">
                Local paths only work when the Axiom API server can read those
                paths directly (e.g. a desktop container or self-hosted instance).
                Browsers cannot access arbitrary local files this way.
              </div>
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={pathsConsent}
                  onChange={(e) => setPathsConsent(e.target.checked)}
                  className="rounded"
                />
                I understand — the server can access these paths
              </label>
              {pathsConsent && (
                <Textarea
                  placeholder={"/home/user/docs/report.pdf\n/home/user/docs/notes.md"}
                  value={rawPaths}
                  onChange={(e) => setRawPaths(e.target.value)}
                  rows={5}
                  className="font-mono text-xs"
                />
              )}
            </div>
          )}
        </section>

        {/* Section B — Build index */}
        <section className="space-y-4">
          <h2 className="text-lg font-semibold">Build index</h2>

          {readyPaths.length > 0 && (
            <p className="text-sm text-muted-foreground">
              {readyPaths.length} document{readyPaths.length !== 1 ? "s" : ""} ready to index
            </p>
          )}

          <Button
            onClick={handleBuild}
            disabled={building || readyPaths.length === 0}
            className="gap-1.5"
          >
            {building ? <Loader2 className="size-4 animate-spin" /> : <Database className="size-4" />}
            {building ? "Building…" : "Build index"}
          </Button>

          {/* Progress steps */}
          {progress.started !== "idle" && (
            <div className="space-y-2 rounded-lg border px-4 py-3">
              {(
                [
                  ["started", "Build started"],
                  ["reading", "Reading docs"],
                  ["embedding", "Computing embeddings"],
                  ["saved", "Saved"],
                ] as const
              ).map(([key, label]) => (
                <div key={key} className="flex items-center gap-2 text-sm">
                  {progress[key] === "done" ? (
                    <CheckCircle2 className="size-4 text-green-500" />
                  ) : progress[key] === "active" ? (
                    <Loader2 className="size-4 animate-spin text-primary" />
                  ) : (
                    <Circle className="size-4 text-muted-foreground/40" />
                  )}
                  <span
                    className={cn(
                      progress[key] === "done"
                        ? "text-foreground"
                        : progress[key] === "active"
                          ? "font-medium text-foreground"
                          : "text-muted-foreground"
                    )}
                  >
                    {label}
                  </span>
                </div>
              ))}
            </div>
          )}

          {buildError && (
            <p className="flex items-center gap-1.5 text-sm text-destructive">
              <AlertCircle className="size-3.5" />
              {buildError}
            </p>
          )}

          {buildResult && (
            <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm dark:border-green-800 dark:bg-green-950/30">
              <p className="font-medium text-green-800 dark:text-green-400">
                Index built: {buildResult.index_id}
              </p>
              <p className="mt-0.5 text-green-700 dark:text-green-500">
                {buildResult.document_count} doc{buildResult.document_count !== 1 ? "s" : ""},{" "}
                {buildResult.chunk_count} chunks
              </p>
              <button
                type="button"
                onClick={() => {
                  localStorage.setItem(
                    "axiom_active_index",
                    JSON.stringify({
                      manifest_path: buildResult.manifest_path,
                      label: buildResult.index_id,
                    })
                  );
                  router.push("/chat");
                }}
                className="mt-2 font-medium text-green-800 underline-offset-2 hover:underline dark:text-green-400"
              >
                Go to Chat →
              </button>
            </div>
          )}
        </section>

        {/* Section C — Existing indexes */}
        <section className="space-y-4">
          <h2 className="text-lg font-semibold">Existing indexes</h2>

          {loadingIndexes && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading indexes…
            </div>
          )}

          {!loadingIndexes && indexError && (
            <div className="flex items-center gap-1.5 text-sm text-destructive">
              <AlertCircle className="size-4" />
              {indexError}
            </div>
          )}

          {!loadingIndexes && !indexError && indexes.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No indexes yet. Build one above.
            </p>
          )}

          {!loadingIndexes && !indexError && indexes.length > 0 && (
            <ScrollArea className="max-h-80">
              <div className="space-y-2 pr-1">
                {indexes.map((idx) => (
                  <div
                    key={idx.index_id}
                    className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium">
                          {idx.index_id}
                        </span>
                        <Badge variant="secondary" className="shrink-0 text-[10px]">
                          {idx.backend}
                        </Badge>
                      </div>
                      <div className="mt-0.5 flex gap-3 text-[11px] text-muted-foreground">
                        <span>
                          {idx.document_count} doc{idx.document_count !== 1 ? "s" : ""}
                        </span>
                        <span>{idx.chunk_count} chunks</span>
                        <span>{formatDate(idx.created_at)}</span>
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      className="shrink-0 text-xs"
                      onClick={() => handleUseInChat(idx)}
                    >
                      Use in Chat →
                    </Button>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </section>
      </main>
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
