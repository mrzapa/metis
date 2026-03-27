"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Circle,
  Database,
  FolderOpen,
  Loader2,
  Orbit,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  buildIndexStream,
  fetchSettings,
  uploadFiles,
  type IndexBuildResult,
  type IndexSummary,
} from "@/lib/api";
import type { UserStar } from "@/lib/constellation-types";
import { cn } from "@/lib/utils";

type BuildStep = "idle" | "active" | "done";
type EntryMode = "new" | "existing";
type StarDialogView = "build" | "overview";
type DialogTone = "default" | "error";

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

interface StarObservatoryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  star: UserStar | null;
  entryMode: EntryMode;
  availableIndexes: IndexSummary[];
  indexesLoading: boolean;
  onIndexBuilt: (result: IndexBuildResult) => void;
  onUpdateStar: (
    starId: string,
    updates: Partial<Pick<UserStar, "label" | "linkedManifestPath">>,
  ) => Promise<boolean>;
  onRemoveStar: (starId: string) => Promise<void>;
  onOpenChat: (manifestPath: string, label: string) => void;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

export function StarObservatoryDialog({
  open,
  onOpenChange,
  star,
  entryMode,
  availableIndexes,
  indexesLoading,
  onIndexBuilt,
  onUpdateStar,
  onRemoveStar,
  onOpenChat,
}: StarObservatoryDialogProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDesktop, setIsDesktop] = useState(false);
  const [tab, setTab] = useState<"upload" | "paths" | "desktop">("upload");
  const [pathsConsent, setPathsConsent] = useState(false);

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadedPaths, setUploadedPaths] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [rawPaths, setRawPaths] = useState("");
  const [desktopPaths, setDesktopPaths] = useState<string[]>([]);
  const [pickError, setPickError] = useState<string | null>(null);

  const [building, setBuilding] = useState(false);
  const [buildError, setBuildError] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressState>(INITIAL_PROGRESS);
  const [buildResult, setBuildResult] = useState<IndexBuildResult | null>(null);

  const [labelDraft, setLabelDraft] = useState("");
  const [linkedManifestPath, setLinkedManifestPath] = useState("");
  const [view, setView] = useState<StarDialogView>("build");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [statusTone, setStatusTone] = useState<DialogTone>("default");
  const [savingMeta, setSavingMeta] = useState(false);
  const [removing, setRemoving] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
      setIsDesktop(true);
      setTab("desktop");
    }
  }, []);

  useEffect(() => {
    if (!open || !star) {
      return;
    }

    setLabelDraft(star.label ?? "");
    setLinkedManifestPath(star.linkedManifestPath ?? "");
    setStatusMessage(null);
    setStatusTone("default");
    setBuildError(null);
    setBuildResult(null);
    setProgress(INITIAL_PROGRESS);
    setSelectedFiles([]);
    setUploadedPaths([]);
    setRawPaths("");
    setDesktopPaths([]);
    setUploadError(null);
    setPickError(null);
    setPathsConsent(false);
    setView(entryMode === "new" || !star.linkedManifestPath ? "build" : "overview");
  }, [entryMode, open, star]);

  const readyPaths = useMemo(
    () => (
      tab === "upload"
        ? uploadedPaths
        : tab === "desktop"
          ? desktopPaths
          : rawPaths
              .split("\n")
              .map((path) => path.trim())
              .filter(Boolean)
    ),
    [desktopPaths, rawPaths, tab, uploadedPaths],
  );

  const linkedIndex = useMemo(
    () => availableIndexes.find((index) => index.manifest_path === linkedManifestPath) ?? null,
    [availableIndexes, linkedManifestPath],
  );
  const suggestedIndexes = useMemo(
    () => availableIndexes
      .filter((index) => index.manifest_path !== linkedManifestPath)
      .slice(0, 5),
    [availableIndexes, linkedManifestPath],
  );
  const handleOpenChange = useCallback((nextOpen: boolean) => {
    if (!nextOpen && (building || uploading)) {
      return;
    }
    onOpenChange(nextOpen);
  }, [building, onOpenChange, uploading]);

  if (!star) {
    return null;
  }
  const activeStar = star;

  async function handlePickFiles() {
    setPickError(null);
    try {
      const { open: openPicker } = await import("@tauri-apps/plugin-dialog");
      const selected = await openPicker({ multiple: true });
      if (selected === null) {
        return;
      }
      const paths = Array.isArray(selected) ? selected : [selected];
      setDesktopPaths(paths);
    } catch (error) {
      setPickError(error instanceof Error ? error.message : "File picker failed");
    }
  }

  async function handleUpload() {
    if (selectedFiles.length === 0) {
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const { paths } = await uploadFiles(selectedFiles);
      setUploadedPaths(paths);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleSaveMeta(nextLinkedManifestPath = linkedManifestPath) {
    setSavingMeta(true);
    const trimmedLabel = labelDraft.trim();
    try {
      const updated = await onUpdateStar(activeStar.id, {
        label: trimmedLabel || undefined,
        linkedManifestPath: nextLinkedManifestPath || undefined,
      });
      if (!updated) {
        throw new Error("This star is no longer available.");
      }
      setLinkedManifestPath(nextLinkedManifestPath);
      setStatusTone("default");
      setStatusMessage("Star details updated.");
    } catch (error) {
      setStatusTone("error");
      setStatusMessage(error instanceof Error ? error.message : "Unable to save star details.");
    } finally {
      setSavingMeta(false);
    }
  }

  async function handleLinkExistingIndex(index: IndexSummary) {
    const nextLabel = labelDraft.trim() || activeStar.label || index.index_id;
    try {
      const updated = await onUpdateStar(activeStar.id, {
        label: nextLabel || undefined,
        linkedManifestPath: index.manifest_path,
      });
      if (!updated) {
        throw new Error("This star is no longer available.");
      }
      setLabelDraft(nextLabel);
      setLinkedManifestPath(index.manifest_path);
      setView("overview");
      setStatusTone("default");
      setStatusMessage(`Linked ${index.index_id} to this star.`);
    } catch (error) {
      setStatusTone("error");
      setStatusMessage(error instanceof Error ? error.message : "Unable to link index.");
    }
  }

  async function handleBuild() {
    if (readyPaths.length === 0) {
      return;
    }

    setBuilding(true);
    setBuildError(null);
    setBuildResult(null);
    setStatusMessage(null);
    setProgress({ reading: "active", embedding: "idle", saved: "idle" });

    try {
      const settings = await fetchSettings();
      const result = await buildIndexStream(readyPaths, settings, (event) => {
        const type = String(event.type ?? "");
        if (type === "status") {
          const text = String(event.text ?? "").toLowerCase();
          if (text.includes("embedding")) {
            setProgress({ reading: "done", embedding: "active", saved: "idle" });
          }
        }
      });

      setProgress({ reading: "done", embedding: "done", saved: "active" });
      setBuildResult(result);
      onIndexBuilt(result);

      const nextLabel = labelDraft.trim() || activeStar.label || result.index_id;
      const updated = await onUpdateStar(activeStar.id, {
        label: nextLabel || undefined,
        linkedManifestPath: result.manifest_path,
      });
      if (!updated) {
        throw new Error("Index built, but the star could not be linked.");
      }

      setProgress({ reading: "done", embedding: "done", saved: "done" });
      setLabelDraft(nextLabel);
      setLinkedManifestPath(result.manifest_path);
      setView("overview");
      setStatusTone("default");
      setStatusMessage(`Built ${result.index_id} and linked it to this star.`);
    } catch (error) {
      setBuildError(error instanceof Error ? error.message : "Build failed");
      setProgress((current) =>
        current.saved === "active"
          ? { reading: "done", embedding: "done", saved: "idle" }
          : current,
      );
      setStatusTone("error");
      setStatusMessage(null);
    } finally {
      setBuilding(false);
    }
  }

  async function handleRemoveStar() {
    setRemoving(true);
    try {
      await onRemoveStar(activeStar.id);
      onOpenChange(false);
    } finally {
      setRemoving(false);
    }
  }

  const dialogTitle = view === "build"
    ? (entryMode === "new" ? "Feed this star" : "Bring new material into orbit")
    : "Star observatory";
  const dialogDescription = view === "build"
    ? "Upload files, add local paths, or attach an existing index to turn this star into a grounded workspace."
    : "Rename the star, inspect its linked index, or launch straight into grounded chat.";

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="max-h-[calc(100vh-2rem)] gap-0 overflow-hidden p-0 sm:max-w-5xl"
        showCloseButton={!building && !uploading}
      >
        <div className="border-b border-white/10 bg-[linear-gradient(180deg,rgba(14,20,34,0.98),rgba(10,13,23,0.92))] px-6 py-5">
          <DialogHeader className="gap-3">
            <div className="flex items-start justify-between gap-4 pr-10">
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.32em] text-[#d6b361]">
                  <Sparkles className="size-3.5" />
                  {entryMode === "new" ? "New star selected" : "Existing star selected"}
                </div>
                <DialogTitle className="font-display text-3xl font-semibold tracking-[-0.05em] text-white">
                  {dialogTitle}
                </DialogTitle>
                <DialogDescription className="max-w-2xl text-sm leading-7 text-slate-300">
                  {dialogDescription}
                </DialogDescription>
              </div>

              <div className="rounded-full border border-[#d6b361]/30 bg-[#d6b361]/10 px-4 py-2 text-right">
                <div className="text-[11px] uppercase tracking-[0.28em] text-[#d6b361]">Star</div>
                <div className="mt-1 text-sm font-medium text-white">
                  {labelDraft.trim() || activeStar.label || (entryMode === "new" ? "Unnamed arrival" : "Mapped star")}
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setView("build")}
                className={cn(
                  "rounded-full px-4 py-2 text-sm transition-all",
                  view === "build"
                    ? "bg-primary/18 text-primary"
                    : "bg-white/6 text-slate-300 hover:bg-white/10 hover:text-white",
                )}
              >
                Upload and build
              </button>
              <button
                type="button"
                onClick={() => setView("overview")}
                className={cn(
                  "rounded-full px-4 py-2 text-sm transition-all",
                  view === "overview"
                    ? "bg-primary/18 text-primary"
                    : "bg-white/6 text-slate-300 hover:bg-white/10 hover:text-white",
                )}
              >
                Index overview
              </button>
            </div>
          </DialogHeader>
        </div>

        <div className="grid max-h-[calc(100vh-11rem)] gap-0 overflow-hidden lg:grid-cols-[minmax(0,1.08fr)_minmax(320px,0.92fr)]">
          <div className="overflow-y-auto px-6 py-6">
            {view === "build" ? (
              <div className="space-y-6">
                <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
                  <div>
                    <h3 className="font-display text-2xl font-semibold tracking-[-0.04em] text-white">
                      Bring in source material
                    </h3>
                    <p className="mt-2 text-sm leading-7 text-slate-300">
                      Pick a few files, add server-readable paths, or attach a ready-made index to this star.
                    </p>
                  </div>
                  <div className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-slate-200">
                    {readyPaths.length} ready
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  {isDesktop ? (
                    <button
                      type="button"
                      onClick={() => setTab("desktop")}
                      className={cn(
                        "rounded-full px-4 py-2 text-sm transition-all",
                        tab === "desktop"
                          ? "bg-primary/18 text-primary"
                          : "bg-white/6 text-slate-300 hover:bg-white/10 hover:text-white",
                      )}
                    >
                      Choose files
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => setTab("upload")}
                    className={cn(
                      "rounded-full px-4 py-2 text-sm transition-all",
                      tab === "upload"
                        ? "bg-primary/18 text-primary"
                        : "bg-white/6 text-slate-300 hover:bg-white/10 hover:text-white",
                    )}
                  >
                    Upload files
                  </button>
                  <button
                    type="button"
                    onClick={() => setTab("paths")}
                    className={cn(
                      "rounded-full px-4 py-2 text-sm transition-all",
                      tab === "paths"
                        ? "bg-primary/18 text-primary"
                        : "bg-white/6 text-slate-300 hover:bg-white/10 hover:text-white",
                    )}
                  >
                    Local paths
                  </button>
                </div>

                <div className="rounded-[1.6rem] border border-white/10 bg-black/18 p-4 sm:p-5">
                  {tab === "desktop" ? (
                    <div className="space-y-4">
                      <Button variant="outline" onClick={handlePickFiles} className="gap-2">
                        <FolderOpen className="size-4" />
                        Choose files
                      </Button>

                      {desktopPaths.length > 0 ? (
                        <div className="space-y-2">
                          {desktopPaths.map((path, index) => (
                            <div
                              key={`${path}-${index}`}
                              className="flex items-center justify-between gap-3 rounded-2xl border border-white/8 bg-white/4 px-4 py-3 text-sm"
                            >
                              <span className="truncate font-mono text-xs text-slate-300">{path}</span>
                              <button
                                type="button"
                                onClick={() => setDesktopPaths((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                                className="text-slate-400 transition-colors hover:text-white"
                              >
                                <X className="size-4" />
                              </button>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-slate-300">
                          Use the native picker to bring PDFs, Markdown, notes, or research folders into orbit.
                        </p>
                      )}

                      {pickError ? (
                        <p className="flex items-center gap-2 text-sm text-rose-300">
                          <AlertCircle className="size-4" />
                          {pickError}
                        </p>
                      ) : null}
                    </div>
                  ) : null}

                  {tab === "upload" ? (
                    <div className="space-y-4">
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="flex w-full flex-col items-center justify-center rounded-[1.5rem] border border-dashed border-primary/28 bg-primary/6 px-6 py-12 text-center transition-all duration-200 hover:border-primary/46 hover:bg-primary/10"
                      >
                        <UploadCloud className="size-11 text-primary" />
                        <p className="mt-4 font-medium text-white">Drop or select files to index</p>
                        <p className="mt-2 text-sm text-slate-300">
                          Great for PDFs, Markdown, docs, transcripts, and mixed research sets.
                        </p>
                      </button>
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

                      {selectedFiles.length > 0 ? (
                        <div className="space-y-2">
                          {selectedFiles.map((file, index) => (
                            <div
                              key={`${file.name}-${index}`}
                              className="flex items-center justify-between gap-3 rounded-2xl border border-white/8 bg-white/4 px-4 py-3 text-sm"
                            >
                              <span className="truncate text-slate-100">{file.name}</span>
                              <button
                                type="button"
                                onClick={() => {
                                  setSelectedFiles((current) => current.filter((_, itemIndex) => itemIndex !== index));
                                  setUploadedPaths([]);
                                }}
                                className="text-slate-400 transition-colors hover:text-white"
                              >
                                <X className="size-4" />
                              </button>
                            </div>
                          ))}
                        </div>
                      ) : null}

                      {uploadError ? (
                        <p className="flex items-center gap-2 text-sm text-rose-300">
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
                      <div className="rounded-[1.35rem] border border-[#d6b361]/20 bg-[#d6b361]/8 px-4 py-3 text-sm leading-7 text-[#ebd7a3]">
                        Use this when the METIS API can already read the filesystem paths directly, such as a desktop sidecar or self-hosted workspace.
                      </div>

                      <label className="flex items-center gap-3 text-sm text-slate-300">
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

                <div className="rounded-[1.6rem] border border-white/10 bg-black/18 p-4 sm:p-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h4 className="font-display text-xl font-semibold tracking-[-0.04em] text-white">
                        Build index
                      </h4>
                      <p className="mt-2 text-sm leading-7 text-slate-300">
                        Turn the selected material into a searchable index and link it straight to this star.
                      </p>
                    </div>
                    <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                      {building ? "Building" : readyPaths.length > 0 ? "Ready" : "Waiting on docs"}
                    </Badge>
                  </div>

                  <div className="mt-5 flex flex-wrap gap-3">
                    <Button onClick={handleBuild} disabled={building || readyPaths.length === 0} className="gap-2">
                      {building ? <Loader2 className="size-4 animate-spin" /> : <Database className="size-4" />}
                      {building ? "Building..." : "Build and link"}
                    </Button>
                    {buildResult ? (
                      <Button
                        variant="outline"
                        onClick={() => {
                          const nextLabel = labelDraft.trim() || buildResult.index_id;
                          onOpenChat(buildResult.manifest_path, nextLabel);
                        }}
                      >
                        Open in chat
                      </Button>
                    ) : null}
                  </div>

                  {building || progress.reading !== "idle" ? (
                    <div className="mt-5 space-y-3">
                      {(
                        [
                          ["reading", "Reading documents"],
                          ["embedding", "Computing embeddings"],
                          ["saved", "Linking the star"],
                        ] as const
                      ).map(([key, label]) => (
                        <div key={key} className="flex items-center gap-3 text-sm">
                          {progress[key] === "done" ? (
                            <CheckCircle2 className="size-4 text-emerald-300" />
                          ) : progress[key] === "active" ? (
                            <Loader2 className="size-4 animate-spin text-primary" />
                          ) : (
                            <Circle className="size-4 text-slate-500" />
                          )}
                          <span className={progress[key] === "active" ? "text-white" : "text-slate-300"}>
                            {label}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : null}

                  {buildError ? (
                    <p className="mt-4 flex items-center gap-2 text-sm text-rose-300">
                      <AlertCircle className="size-4" />
                      {buildError}
                    </p>
                  ) : null}
                </div>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(220px,0.7fr)]">
                  <label className="space-y-2">
                    <span className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Star label</span>
                    <Input
                      value={labelDraft}
                      onChange={(event) => setLabelDraft(event.target.value)}
                      placeholder="Name this star"
                    />
                  </label>

                  <label className="space-y-2">
                    <span className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Linked index</span>
                    <select
                      value={linkedManifestPath}
                      onChange={(event) => setLinkedManifestPath(event.target.value)}
                      className="h-9 w-full rounded-xl border border-input/80 bg-card/70 px-3 text-sm text-white outline-none transition-[border-color,box-shadow] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40"
                    >
                      <option value="">Unlinked</option>
                      {availableIndexes.map((index) => (
                        <option key={index.manifest_path} value={index.manifest_path}>
                          {index.index_id}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <div className="flex flex-wrap gap-3">
                  <Button onClick={() => void handleSaveMeta()} disabled={savingMeta} className="gap-2">
                    {savingMeta ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                    Save star
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      if (!linkedManifestPath) {
                        return;
                      }
                      const linkedLabel = labelDraft.trim() || linkedIndex?.index_id || "Mapped star";
                      onOpenChat(linkedManifestPath, linkedLabel);
                    }}
                    disabled={!linkedManifestPath}
                  >
                    Open linked chat
                  </Button>
                  <Button variant="outline" onClick={() => setView("build")}>
                    Build another index
                  </Button>
                  <Button variant="destructive" onClick={() => void handleRemoveStar()} disabled={removing}>
                    {removing ? "Removing..." : "Remove star"}
                  </Button>
                </div>

                {linkedIndex ? (
                  <div className="rounded-[1.6rem] border border-white/10 bg-black/18 p-5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Index overview</div>
                        <h3 className="mt-2 font-display text-2xl font-semibold tracking-[-0.04em] text-white">
                          {linkedIndex.index_id}
                        </h3>
                      </div>
                      <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                        {linkedIndex.backend}
                      </Badge>
                    </div>

                    <div className="mt-5 grid gap-3 sm:grid-cols-3">
                      <div className="rounded-2xl border border-white/8 bg-white/4 px-4 py-3">
                        <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Documents</div>
                        <div className="mt-2 text-2xl font-semibold text-white">{linkedIndex.document_count}</div>
                      </div>
                      <div className="rounded-2xl border border-white/8 bg-white/4 px-4 py-3">
                        <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Chunks</div>
                        <div className="mt-2 text-2xl font-semibold text-white">{linkedIndex.chunk_count}</div>
                      </div>
                      <div className="rounded-2xl border border-white/8 bg-white/4 px-4 py-3">
                        <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Created</div>
                        <div className="mt-2 text-base font-medium text-white">{formatDate(linkedIndex.created_at)}</div>
                      </div>
                    </div>

                    <p className="mt-5 text-sm leading-7 text-slate-300">
                      This star is now a routed entry point into grounded chat. Re-link it, rename it, or build a fresh index if this orbit needs a new source cluster.
                    </p>
                  </div>
                ) : (
                  <div className="rounded-[1.6rem] border border-dashed border-white/12 bg-black/18 p-5">
                    <div className="flex items-center gap-3 text-white">
                      <Orbit className="size-5 text-[#d6b361]" />
                      <span className="font-medium">This star is not linked to an index yet.</span>
                    </div>
                    <p className="mt-3 text-sm leading-7 text-slate-300">
                      Build a new index or attach one of the indexed sources from the observatory rail.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          <aside className="border-t border-white/10 bg-[linear-gradient(180deg,rgba(12,16,28,0.98),rgba(8,11,20,0.96))] px-6 py-6 lg:border-t-0 lg:border-l">
            <div className="space-y-5">
              <div className="rounded-[1.5rem] border border-white/10 bg-white/4 p-4">
                <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Observatory rail</div>
                <div className="mt-3 flex items-center gap-3">
                  <div className="size-3 rounded-full bg-[#d6b361] shadow-[0_0_24px_rgba(214,179,97,0.7)]" />
                  <div>
                    <div className="text-sm font-medium text-white">
                      {labelDraft.trim() || star.label || "Untitled star"}
                    </div>
                    <div className="text-sm text-slate-300">
                      {linkedIndex ? "Linked and chat-ready" : "Awaiting an index"}
                    </div>
                  </div>
                </div>
              </div>

              {statusMessage ? (
                <div
                  className={cn(
                    "rounded-[1.4rem] border px-4 py-3 text-sm",
                    statusTone === "error"
                      ? "border-rose-400/20 bg-rose-400/10 text-rose-200"
                      : "border-emerald-400/20 bg-emerald-400/10 text-emerald-100",
                  )}
                >
                  {statusMessage}
                </div>
              ) : null}

              {buildResult ? (
                <div className="rounded-[1.5rem] border border-emerald-400/20 bg-emerald-400/10 p-4">
                  <div className="text-[11px] uppercase tracking-[0.28em] text-emerald-200">Latest build</div>
                  <div className="mt-2 text-lg font-semibold text-white">{buildResult.index_id}</div>
                  <div className="mt-3 flex flex-wrap gap-3 text-sm text-emerald-100/90">
                    <span>{buildResult.document_count} docs</span>
                    <span>{buildResult.chunk_count} chunks</span>
                  </div>
                </div>
              ) : null}

              <div className="rounded-[1.5rem] border border-white/10 bg-white/4 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Indexed sources</div>
                    <div className="mt-2 text-sm text-slate-300">
                      {indexesLoading ? "Refreshing orbit…" : `${availableIndexes.length} ready to attach`}
                    </div>
                  </div>
                  <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                    {availableIndexes.length}
                  </Badge>
                </div>

                {suggestedIndexes.length > 0 ? (
                  <div className="mt-4 space-y-2">
                    {suggestedIndexes.map((index) => (
                      <button
                        key={index.manifest_path}
                        type="button"
                        onClick={() => void handleLinkExistingIndex(index)}
                        className="flex w-full items-start justify-between gap-3 rounded-2xl border border-white/8 bg-black/18 px-4 py-3 text-left transition-colors hover:border-primary/30 hover:bg-primary/8"
                      >
                        <div className="min-w-0">
                          <div className="truncate font-medium text-white">{index.index_id}</div>
                          <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-400">
                            <span>{index.document_count} docs</span>
                            <span>{index.chunk_count} chunks</span>
                          </div>
                        </div>
                        <span className="text-xs text-primary">Attach</span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="mt-4 text-sm leading-7 text-slate-300">
                    {indexesLoading
                      ? "Loading indexed sources."
                      : "No other indexed sources are available yet. Build one in this observatory to give the star grounded memory."}
                  </p>
                )}
              </div>
            </div>
          </aside>
        </div>
      </DialogContent>
    </Dialog>
  );
}
