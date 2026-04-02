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
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LearningRoutePanel } from "@/components/constellation/learning-route-panel";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { buildIndexStream, fetchSettings, uploadFiles } from "@/lib/api";
import type { IndexBuildResult, IndexSummary } from "@/lib/api";
import {
  buildBrainPlacementIntent,
  buildFacultyAnchoredPlacement,
  getConstellationPlacementDecision,
} from "@/lib/constellation-brain";
import { CONSTELLATION_FACULTIES, getAutoStarFaculty, getFacultyColor, isAutonomousStar } from "@/lib/constellation-home";
import type {
  LearningRoute,
  LearningRouteStep,
  LearningRouteStepStatus,
  UserStar,
  UserStarStage,
} from "@/lib/constellation-types";
import { cn } from "@/lib/utils";

type BuildStep = "idle" | "active" | "done";
type EntryMode = "new" | "existing";
type StarDialogView = "build" | "overview";
type DialogTone = "default" | "error";

type DetailStar = UserStar & {
  primaryDomainId?: string;
  relatedDomainIds?: string[];
  stage?: UserStarStage;
  intent?: string;
  notes?: string;
  linkedManifestPaths?: string[];
  activeManifestPath?: string;
};

type StarUpdatePayload = Partial<
  Pick<
    UserStar,
    | "label"
    | "primaryDomainId"
    | "relatedDomainIds"
    | "stage"
    | "intent"
    | "notes"
    | "linkedManifestPaths"
    | "activeManifestPath"
    | "linkedManifestPath"
    | "x"
    | "y"
  >
>;

type AttachedIndexSummary = {
  manifest_path: string;
  index_id: string;
  document_count: number;
  chunk_count: number;
  backend: string;
  created_at?: string;
  embedding_signature?: string;
  source: "available" | "build" | "unresolved";
};

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

const STAGE_OPTIONS: Array<{ value: UserStarStage; label: string; description: string }> = [
  {
    value: "seed",
    label: "Seed",
    description: "A new possibility that is just entering the constellation.",
  },
  {
    value: "growing",
    label: "Growing",
    description: "Actively collecting sources, notes, or applied meaning.",
  },
  {
    value: "integrated",
    label: "Integrated",
    description: "A mature star drawing on multiple attached sources.",
  },
];

interface StarDetailsPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  star: UserStar | null;
  entryMode: EntryMode;
  closeLockedUntil?: number;
  availableIndexes: IndexSummary[];
  indexesLoading: boolean;
  onIndexBuilt: (result: IndexBuildResult) => void;
  onUpdateStar: (starId: string, updates: StarUpdatePayload) => Promise<boolean>;
  onRemoveStar: (payload: { starId: string; manifestPaths: string[] }) => Promise<void>;
  onOpenChat: (payload: {
    manifestPath: string;
    label: string;
    selectedMode?: string;
    draft?: string;
  }) => void;
  learningRoutePreview: LearningRoute | null;
  learningRouteLoading: boolean;
  learningRouteError: string | null;
  onStartCourse: () => void;
  onSaveLearningRoutePreview: () => void;
  onDiscardLearningRoutePreview: () => void;
  onRegenerateLearningRoute: () => void;
  onLaunchLearningRouteStep: (step: LearningRouteStep) => void;
  onSetLearningRouteStepStatus: (stepId: string, status: LearningRouteStepStatus) => void;
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

function uniqueStrings(values: Array<string | undefined | null>): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  values.forEach((value) => {
    const trimmed = value?.trim();
    if (!trimmed || seen.has(trimmed)) {
      return;
    }
    seen.add(trimmed);
    result.push(trimmed);
  });
  return result;
}

function resolveDefaultStage(
  linkedManifestPaths: string[],
  notes: string | undefined,
): UserStarStage {
  if (linkedManifestPaths.length >= 2) {
    return "integrated";
  }
  if (linkedManifestPaths.length === 1 || notes?.trim()) {
    return "growing";
  }
  return "seed";
}

function StarMiniPreview({
  primaryDomainId,
  relatedDomainIds,
  stage,
  size,
}: {
  primaryDomainId?: string;
  relatedDomainIds?: string[];
  stage?: UserStarStage;
  size?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const DPR = Math.min(typeof window !== "undefined" ? (window.devicePixelRatio ?? 1) : 1, 2);
    const PX = 180;
    canvas.width = PX * DPR;
    canvas.height = PX * DPR;
    canvas.style.width = `${PX}px`;
    canvas.style.height = `${PX}px`;
    ctx.scale(DPR, DPR);

    const cx = PX / 2;
    const cy = PX / 2;
    const [r, g, b] = getFacultyColor(primaryDomainId);
    const relatedColors = (relatedDomainIds ?? []).slice(0, 2).map((id) => getFacultyColor(id));
    const sz = Math.max(38, Math.min(52, (size ?? 1.2) * 36));
    const hasDiffraction = stage === "integrated" || stage === "growing";
    let startTime: number | null = null;

    function draw(ts: number) {
      if (!startTime) startTime = ts;
      const elapsed = ts - startTime;
      ctx!.clearRect(0, 0, PX, PX);

      ctx!.fillStyle = "rgb(8,11,20)";
      ctx!.fillRect(0, 0, PX, PX);

      ctx!.save();

      const twinkle = 0.85 + Math.sin(elapsed * 0.002) * 0.1 + Math.cos(elapsed * 0.0014) * 0.05;

      // Outer halo
      const haloR = sz * 5.8;
      const halo = ctx!.createRadialGradient(cx, cy, sz * 0.3, cx, cy, haloR);
      halo.addColorStop(0, `rgba(${r},${g},${b},${0.22 * twinkle})`);
      halo.addColorStop(0.55, `rgba(${r},${g},${b},${0.07 * twinkle})`);
      halo.addColorStop(1, "rgba(0,0,0,0)");
      ctx!.fillStyle = halo;
      ctx!.beginPath();
      ctx!.arc(cx, cy, haloR, 0, Math.PI * 2);
      ctx!.fill();

      // Secondary colour halos
      relatedColors.forEach(([sr, sg, sb], i) => {
        const drift = i % 2 === 0 ? 1 : -1;
        const accentR = haloR * 0.72;
        const ox = cx + drift * sz * 0.9;
        const oy = cy - sz * 0.5;
        const ag = ctx!.createRadialGradient(ox, oy, sz * 0.1, cx, cy, accentR);
        ag.addColorStop(0, `rgba(${sr},${sg},${sb},${0.10 * twinkle})`);
        ag.addColorStop(1, "rgba(0,0,0,0)");
        ctx!.fillStyle = ag;
        ctx!.beginPath();
        ctx!.arc(cx, cy, accentR, 0, Math.PI * 2);
        ctx!.fill();
      });

      // Aura
      const auraR = sz * 3.4;
      const aura = ctx!.createRadialGradient(cx, cy, sz * 0.2, cx, cy, auraR);
      aura.addColorStop(0, `rgba(${r},${g},${b},${0.24 * twinkle})`);
      aura.addColorStop(1, "rgba(0,0,0,0)");
      ctx!.fillStyle = aura;
      ctx!.beginPath();
      ctx!.arc(cx, cy, auraR, 0, Math.PI * 2);
      ctx!.fill();

      // Diffraction spikes
      if (hasDiffraction) {
        const spikeLen = sz * 5.5;
        const spikeAngle = elapsed * 0.00004;
        ctx!.save();
        ctx!.translate(cx, cy);
        ctx!.rotate(spikeAngle);
        ctx!.strokeStyle = `rgba(${r},${g},${b},${0.28 * twinkle})`;
        ctx!.lineWidth = 0.85;
        ctx!.beginPath();
        ctx!.moveTo(-spikeLen, 0);
        ctx!.lineTo(spikeLen, 0);
        ctx!.moveTo(0, -spikeLen * 0.76);
        ctx!.lineTo(0, spikeLen * 0.76);
        ctx!.stroke();
        ctx!.restore();
      }

      // Star body
      const coreR2 = Math.round(r * 0.7 + 255 * 0.3);
      const coreG2 = Math.round(g * 0.82 + 210 * 0.18);
      const coreB2 = Math.round(b * 0.7 + 230 * 0.3);
      const bodyGrad = ctx!.createRadialGradient(cx - sz * 0.35, cy - sz * 0.38, sz * 0.12, cx, cy, sz * 1.45);
      bodyGrad.addColorStop(0, `rgba(255,255,255,${0.97 * twinkle})`);
      bodyGrad.addColorStop(0.16, `rgba(${coreR2},${coreG2},${coreB2},${0.98 * twinkle})`);
      bodyGrad.addColorStop(0.52, `rgba(${r},${g},${b},${0.82 * twinkle})`);
      bodyGrad.addColorStop(1, `rgba(${r},${g},${b},0)`);
      ctx!.fillStyle = bodyGrad;
      ctx!.beginPath();
      ctx!.arc(cx, cy, sz * 1.45, 0, Math.PI * 2);
      ctx!.fill();

      // Bright white core
      const coreGrad = ctx!.createRadialGradient(cx, cy, 0, cx, cy, sz * 0.82);
      coreGrad.addColorStop(0, `rgba(255,255,255,${twinkle})`);
      coreGrad.addColorStop(0.6, `rgba(255,255,255,${0.6 * twinkle})`);
      coreGrad.addColorStop(1, "rgba(255,255,255,0)");
      ctx!.fillStyle = coreGrad;
      ctx!.beginPath();
      ctx!.arc(cx, cy, sz * 0.82, 0, Math.PI * 2);
      ctx!.fill();

      ctx!.restore();
      rafRef.current = requestAnimationFrame(draw);
    }

    rafRef.current = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(rafRef.current); };
  }, [primaryDomainId, relatedDomainIds, stage, size]);

  return <canvas ref={canvasRef} style={{ display: "block", borderRadius: "50%" }} />;
}

export function StarDetailsPanel({
  open,
  onOpenChange,
  star,
  entryMode,
  closeLockedUntil = 0,
  availableIndexes,
  indexesLoading,
  onIndexBuilt,
  onUpdateStar,
  onRemoveStar,
  onOpenChat,
  learningRoutePreview,
  learningRouteLoading,
  learningRouteError,
  onStartCourse,
  onSaveLearningRoutePreview,
  onDiscardLearningRoutePreview,
  onRegenerateLearningRoute,
  onLaunchLearningRouteStep,
  onSetLearningRouteStepStatus,
}: StarDetailsPanelProps) {
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
  const [primaryDomainIdDraft, setPrimaryDomainIdDraft] = useState("");
  const [relatedDomainIdsDraft, setRelatedDomainIdsDraft] = useState("");
  const [manualStageOverride, setManualStageOverride] = useState<UserStarStage | "">("");
  const [intentDraft, setIntentDraft] = useState("");
  const [notesDraft, setNotesDraft] = useState("");
  const [attachedManifestPaths, setAttachedManifestPaths] = useState<string[]>([]);
  const [activeManifestPath, setActiveManifestPath] = useState("");
  const [view, setView] = useState<StarDialogView>("build");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [statusTone, setStatusTone] = useState<DialogTone>("default");
  const [savingMeta, setSavingMeta] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

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

    const activeStar = star as DetailStar;
    const nextAttachedManifestPaths = uniqueStrings([
      ...(activeStar.linkedManifestPaths ?? []),
      activeStar.activeManifestPath,
      activeStar.linkedManifestPath,
    ]);

    setLabelDraft(activeStar.label ?? "");
    setPrimaryDomainIdDraft(activeStar.primaryDomainId ?? "");
    setRelatedDomainIdsDraft((activeStar.relatedDomainIds ?? []).join(", "));
    const derivedStage = resolveDefaultStage(nextAttachedManifestPaths, activeStar.notes);
    setManualStageOverride(
      activeStar.stage && activeStar.stage !== derivedStage ? activeStar.stage : "",
    );
    setIntentDraft(activeStar.intent ?? "");
    setNotesDraft(activeStar.notes ?? "");
    setAttachedManifestPaths(nextAttachedManifestPaths);
    setActiveManifestPath(
      activeStar.activeManifestPath
        || nextAttachedManifestPaths[nextAttachedManifestPaths.length - 1]
        || activeStar.linkedManifestPath
        || "",
    );
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
    setDeleteConfirmOpen(false);
    setView(entryMode === "new" || nextAttachedManifestPaths.length === 0 ? "build" : "overview");
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

  const activeManifestPathForChat = activeManifestPath
    || attachedManifestPaths[attachedManifestPaths.length - 1]
    || buildResult?.manifest_path
    || "";
  const derivedStage = resolveDefaultStage(attachedManifestPaths, notesDraft);
  const effectiveStage = manualStageOverride || derivedStage;
  const availableIndexByManifestPath = useMemo(
    () => new Map(
      availableIndexes.map((index) => [
        index.manifest_path,
        { ...index, source: "available" as const },
      ]),
    ),
    [availableIndexes],
  );
  const buildResultSummary = useMemo<AttachedIndexSummary | null>(() => {
    if (!buildResult) {
      return null;
    }

    return {
      manifest_path: buildResult.manifest_path,
      index_id: buildResult.index_id,
      document_count: buildResult.document_count,
      chunk_count: buildResult.chunk_count,
      backend: buildResult.vector_backend,
      created_at: undefined,
      embedding_signature: buildResult.embedding_signature,
      source: "build",
    };
  }, [buildResult]);

  const resolveAttachedIndex = useCallback((manifestPath: string): AttachedIndexSummary => {
    const foundIndex = availableIndexByManifestPath.get(manifestPath);
    if (foundIndex) {
      return foundIndex;
    }

    if (buildResultSummary?.manifest_path === manifestPath) {
      return buildResultSummary;
    }

    return {
      manifest_path: manifestPath,
      index_id: manifestPath,
      document_count: 0,
      chunk_count: 0,
      backend: "unknown",
      source: "unresolved",
    };
  }, [availableIndexByManifestPath, buildResultSummary]);

  const activeIndex = activeManifestPathForChat ? resolveAttachedIndex(activeManifestPathForChat) : null;
  const attachedIndexes = useMemo(
    () => attachedManifestPaths.map((manifestPath) => resolveAttachedIndex(manifestPath)),
    [attachedManifestPaths, resolveAttachedIndex],
  );
  const attachedManifestPathSet = useMemo(
    () => new Set(attachedManifestPaths),
    [attachedManifestPaths],
  );
  const suggestedIndexes = useMemo(
    () => availableIndexes
      .filter((index) => !attachedManifestPathSet.has(index.manifest_path))
      .slice(0, 5),
    [attachedManifestPathSet, availableIndexes],
  );

  const handleOpenChange = useCallback((nextOpen: boolean) => {
    if (!nextOpen && (building || uploading || removing)) {
      return;
    }
    if (!nextOpen && Date.now() < closeLockedUntil) {
      return;
    }
    onOpenChange(nextOpen);
  }, [building, closeLockedUntil, onOpenChange, removing, uploading]);

  if (!star) {
    return null;
  }

  const activeStar = star as DetailStar;
  const savedLearningRoute = activeStar.learningRoute ?? null;
  const displayedLearningRoute = learningRoutePreview ?? savedLearningRoute;
  const hasCourseSource = Boolean(activeManifestPathForChat) || attachedManifestPaths.length > 0;
  const unavailableManifestPaths = new Set(
    (displayedLearningRoute?.steps ?? [])
      .map((step) => step.manifestPath)
      .filter((manifestPath) => resolveAttachedIndex(manifestPath).source === "unresolved"),
  );

  function buildStarUpdate(
    nextAttachedManifestPaths = attachedManifestPaths,
    nextActiveManifestPath = activeManifestPath,
    labelOverride?: string,
    extraUpdates?: Partial<StarUpdatePayload>,
  ): StarUpdatePayload {
    const label = extraUpdates?.label ?? ((labelOverride ?? labelDraft.trim()) || activeStar.label || undefined);
    const notes = extraUpdates?.notes ?? (notesDraft.trim() || undefined);
    const relatedDomainIds = extraUpdates?.relatedDomainIds
      ? uniqueStrings(extraUpdates.relatedDomainIds)
      : uniqueStrings(relatedDomainIdsDraft.split(/[\n,]/g));
    const linkedManifestPaths = uniqueStrings([
      ...nextAttachedManifestPaths,
      nextActiveManifestPath,
    ]);
    const activePath = extraUpdates?.activeManifestPath ?? (nextActiveManifestPath || linkedManifestPaths[linkedManifestPaths.length - 1] || undefined);

    return {
      label,
      primaryDomainId: extraUpdates?.primaryDomainId ?? (primaryDomainIdDraft.trim() || undefined),
      relatedDomainIds: relatedDomainIds.length > 0 ? relatedDomainIds : undefined,
      stage: extraUpdates?.stage ?? (manualStageOverride || undefined),
      intent: extraUpdates?.intent ?? (intentDraft.trim() || undefined),
      notes,
      linkedManifestPaths: linkedManifestPaths.length > 0 ? linkedManifestPaths : undefined,
      activeManifestPath: activePath,
      linkedManifestPath: extraUpdates?.linkedManifestPath ?? activePath,
      x: extraUpdates?.x,
      y: extraUpdates?.y,
    };
  }

  async function commitStarUpdate({
    nextAttachedManifestPaths = attachedManifestPaths,
    nextActiveManifestPath = activeManifestPath,
    labelOverride,
    extraUpdates,
    successMessage = "Star details updated.",
    showSavingState = true,
  }: {
    nextAttachedManifestPaths?: string[];
    nextActiveManifestPath?: string;
    labelOverride?: string;
    extraUpdates?: Partial<StarUpdatePayload>;
    successMessage?: string;
    showSavingState?: boolean;
  } = {}) {
    if (showSavingState) {
      setSavingMeta(true);
    }

    try {
      const payload = buildStarUpdate(
        nextAttachedManifestPaths,
        nextActiveManifestPath,
        labelOverride,
        extraUpdates,
      );
      const updated = await onUpdateStar(activeStar.id, payload as Parameters<typeof onUpdateStar>[1]);
      if (!updated) {
        throw new Error("This star is no longer available.");
      }

      setLabelDraft(payload.label ?? "");
      setPrimaryDomainIdDraft(payload.primaryDomainId ?? "");
      setRelatedDomainIdsDraft((payload.relatedDomainIds ?? []).join(", "));
      setIntentDraft(payload.intent ?? "");
      setNotesDraft(payload.notes ?? "");
      setAttachedManifestPaths(payload.linkedManifestPaths ?? []);
      setActiveManifestPath(payload.activeManifestPath ?? "");
      const nextDerivedStage = resolveDefaultStage(payload.linkedManifestPaths ?? [], payload.notes);
      setManualStageOverride(
        payload.stage && payload.stage !== nextDerivedStage ? payload.stage : "",
      );
      setStatusTone("default");
      setStatusMessage(successMessage);
      return true;
    } catch (error) {
      setStatusTone("error");
      setStatusMessage(error instanceof Error ? error.message : "Unable to save star details.");
      return false;
    } finally {
      if (showSavingState) {
        setSavingMeta(false);
      }
    }
  }

  function handleSetActiveManifestPath(manifestPath: string) {
    setActiveManifestPath(manifestPath);
    const summary = resolveAttachedIndex(manifestPath);
    setStatusTone("default");
    setStatusMessage(`Active chat index staged to ${summary.index_id}. Save to keep it.`);
  }

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

  async function handleSaveMeta() {
    await commitStarUpdate();
  }

  async function handleLinkExistingIndex(index: IndexSummary) {
    const nextLabel = labelDraft.trim() || activeStar.label || index.index_id;
    const nextAttachedManifestPaths = uniqueStrings([
      ...attachedManifestPaths.filter((manifestPath) => manifestPath !== index.manifest_path),
      index.manifest_path,
    ]);
    const updated = await commitStarUpdate({
      nextAttachedManifestPaths,
      nextActiveManifestPath: index.manifest_path,
      labelOverride: nextLabel,
      successMessage: `${index.index_id} is now attached and active.`,
      showSavingState: false,
    });

    if (updated) {
      setView("overview");
    }
  }

  async function handleDetachIndex(manifestPath: string) {
    const nextAttachedManifestPaths = attachedManifestPaths.filter(
      (attachedManifestPath) => attachedManifestPath !== manifestPath,
    );
    const nextActiveManifestPath = manifestPath === activeManifestPathForChat
      ? (nextAttachedManifestPaths[nextAttachedManifestPaths.length - 1] ?? "")
      : activeManifestPathForChat;
    const detachedIndex = resolveAttachedIndex(manifestPath);
    const updated = await commitStarUpdate({
      nextAttachedManifestPaths,
      nextActiveManifestPath,
      successMessage:
        nextAttachedManifestPaths.length > 0
          ? `${detachedIndex.index_id} detached. Remaining sources stay in orbit.`
          : `${detachedIndex.index_id} detached. This star is ready for new material.`,
      showSavingState: false,
    });

    if (updated && nextAttachedManifestPaths.length === 0) {
      setView("build");
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
      const nextAttachedManifestPaths = uniqueStrings([
        ...attachedManifestPaths.filter((manifestPath) => manifestPath !== result.manifest_path),
        result.manifest_path,
      ]);
      const placement = getConstellationPlacementDecision(result);
      const facultyLabel = CONSTELLATION_FACULTIES.find(
        (faculty) => faculty.id === placement.facultyId,
      )?.label ?? placement.facultyId;
      const placementSeed = Math.abs(Math.trunc(activeStar.createdAt % 24));
      const { x, y } = buildFacultyAnchoredPlacement(placement.facultyId, placementSeed);
      const nextRelatedDomainIds = uniqueStrings([
        ...relatedDomainIdsDraft.split(/[\n,]/g),
        ...placement.secondaryFacultyIds,
      ]);
      const updated = await commitStarUpdate({
        nextAttachedManifestPaths,
        nextActiveManifestPath: result.manifest_path,
        labelOverride: nextLabel,
        extraUpdates: {
          primaryDomainId: placement.facultyId,
          relatedDomainIds: nextRelatedDomainIds.length > 0 ? nextRelatedDomainIds : undefined,
          intent: intentDraft.trim() || buildBrainPlacementIntent(placement.provider),
          notes: notesDraft.trim() || placement.rationale || undefined,
          x,
          y,
        },
        successMessage: `Built ${result.index_id} and filed it near ${facultyLabel}.`,
        showSavingState: false,
      });
      if (!updated) {
        throw new Error("Index built, but the star could not be linked.");
      }

      setProgress({ reading: "done", embedding: "done", saved: "done" });
      setView("overview");
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
      await onRemoveStar({
        starId: activeStar.id,
        manifestPaths: uniqueStrings([
          ...attachedManifestPaths,
          activeManifestPathForChat,
        ]),
      });
      setDeleteConfirmOpen(false);
    } catch (error) {
      setStatusTone("error");
      setStatusMessage(error instanceof Error ? error.message : "Unable to delete this star right now.");
    } finally {
      setRemoving(false);
    }
  }

  const dialogTitle = view === "build"
    ? (entryMode === "new" ? "Add to this star" : "Attach sources")
    : "Star details";
  const dialogDescription = view === "build"
    ? "Upload files, add local paths, or attach an existing index to deepen this star's memory."
    : "Edit the star's meaning, switch the active chat index, or bring in more attached indexes.";

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="left-1/2 top-auto bottom-3 flex h-[calc(100vh-1.5rem)] max-h-[calc(100vh-1.5rem)] w-[calc(100%-1.5rem)] max-w-[calc(100%-1.5rem)] -translate-x-1/2 translate-y-0 flex-col gap-0 overflow-hidden rounded-[1.75rem] border-white/12 bg-[linear-gradient(180deg,rgba(14,20,34,0.98),rgba(8,11,20,0.96))] p-0 sm:left-auto sm:right-4 sm:top-4 sm:bottom-4 sm:h-[calc(100vh-2rem)] sm:max-h-[calc(100vh-2rem)] sm:w-[min(460px,calc(100vw-2rem))] sm:max-w-[460px] sm:translate-x-0 sm:translate-y-0"
        data-testid="star-details-panel"
        showCloseButton={!building && !uploading && !removing}
        showOverlay={false}
      >
        <div className="border-b border-white/10 bg-[linear-gradient(180deg,rgba(14,20,34,0.98),rgba(10,13,23,0.92))] px-5 py-5 sm:px-6">
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
                {isAutonomousStar(activeIndex?.index_id) && (
                  <div className="flex items-center gap-1.5 text-[11px] text-violet-300/80">
                    <span>✦</span>
                    <span>
                      Added autonomously by METIS
                      {getAutoStarFaculty(activeIndex?.index_id)
                        ? ` · ${getAutoStarFaculty(activeIndex?.index_id)}`
                        : ""}
                    </span>
                  </div>
                )}
              </div>

              <div className="shrink-0 overflow-hidden rounded-full border border-[#d6b361]/30 ring-1 ring-white/5">
                <StarMiniPreview
                  primaryDomainId={primaryDomainIdDraft || activeStar.primaryDomainId}
                  relatedDomainIds={
                    relatedDomainIdsDraft
                      ? relatedDomainIdsDraft.split(",").map((s) => s.trim()).filter(Boolean)
                      : activeStar.relatedDomainIds
                  }
                  stage={effectiveStage}
                  size={activeStar.size}
                />
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
                Add and build
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
                Attached sources
              </button>
            </div>
          </DialogHeader>
        </div>

        <div className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="px-5 py-5 sm:px-6 sm:py-6">
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
                        Turn the selected material into a searchable index and attach it to this star.
                      </p>
                    </div>
                    <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                      {building ? "Building" : readyPaths.length > 0 ? "Ready" : "Waiting on docs"}
                    </Badge>
                  </div>

                  <div className="mt-5 flex flex-wrap gap-3">
                    <Button onClick={handleBuild} disabled={building || readyPaths.length === 0} className="gap-2">
                      {building ? <Loader2 className="size-4 animate-spin" /> : <Database className="size-4" />}
                      {building ? "Building..." : "Add and build"}
                    </Button>
                    {buildResult ? (
                      <Button
                        variant="outline"
                        onClick={() => {
                          const nextLabel = labelDraft.trim() || activeStar.label || buildResult.index_id;
                          onOpenChat({
                            manifestPath: activeManifestPathForChat || buildResult.manifest_path,
                            label: nextLabel,
                          });
                        }}
                      >
                        Open chat
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
                {attachedIndexes.length > 0 ? (
                  <div className="space-y-6">
                    <div className="rounded-[1.6rem] border border-white/10 bg-black/18 p-5">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Active chat index</div>
                          <h3 className="mt-2 font-display text-2xl font-semibold tracking-[-0.04em] text-white">
                            {activeIndex?.index_id || activeManifestPathForChat || "No active index"}
                          </h3>
                        </div>
                        {activeIndex ? (
                          <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                            Active
                          </Badge>
                        ) : null}
                      </div>

                      {activeIndex ? (
                        <div className="mt-5 grid gap-3 sm:grid-cols-3">
                          <div className="rounded-2xl border border-white/8 bg-white/4 px-4 py-3">
                            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Documents</div>
                            <div className="mt-2 text-2xl font-semibold text-white">{activeIndex.document_count}</div>
                          </div>
                          <div className="rounded-2xl border border-white/8 bg-white/4 px-4 py-3">
                            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Chunks</div>
                            <div className="mt-2 text-2xl font-semibold text-white">{activeIndex.chunk_count}</div>
                          </div>
                          <div className="rounded-2xl border border-white/8 bg-white/4 px-4 py-3">
                            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Backend</div>
                            <div className="mt-2 text-base font-medium text-white">{activeIndex.backend}</div>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-5 rounded-2xl border border-dashed border-white/12 bg-black/10 px-4 py-4 text-sm leading-7 text-slate-300">
                          No active index is selected yet. Pick one from the attached rail to launch grounded chat.
                        </div>
                      )}

                      <p className="mt-5 text-sm leading-7 text-slate-300">
                        This star routes chat through one active index at a time, while keeping every attached source in orbit.
                      </p>
                    </div>

                    <div className="rounded-[1.6rem] border border-white/10 bg-black/18 p-5">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Attached indexes</div>
                          <div className="mt-2 text-sm text-slate-300">
                            {attachedIndexes.length} source{attachedIndexes.length === 1 ? "" : "s"} are attached to this star.
                          </div>
                        </div>
                        <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                          {attachedIndexes.length}
                        </Badge>
                      </div>

                      <div className="mt-4 space-y-2">
                        {attachedIndexes.map((index) => {
                          const isActive = index.manifest_path === activeManifestPathForChat;
                          return (
                            <div
                              key={index.manifest_path}
                              className={cn(
                                "flex items-start justify-between gap-3 rounded-2xl border px-4 py-3 transition-colors",
                                isActive
                                  ? "border-[#d6b361]/30 bg-[#d6b361]/8"
                                  : "border-white/8 bg-white/4 hover:border-primary/30 hover:bg-primary/8",
                              )}
                            >
                              <div className="min-w-0">
                                <div className="truncate font-medium text-white">{index.index_id}</div>
                                <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-400">
                                  <span>{index.document_count} docs</span>
                                  <span>{index.chunk_count} chunks</span>
                                  {index.created_at ? <span>{formatDate(index.created_at)}</span> : null}
                                </div>
                              </div>
                              <div className="flex flex-wrap items-center justify-end gap-2">
                                <button
                                  type="button"
                                  onClick={() => handleSetActiveManifestPath(index.manifest_path)}
                                  className={cn(
                                    "rounded-full px-3 py-1.5 text-xs transition-all",
                                    isActive
                                      ? "bg-[#d6b361]/18 text-[#f5d899]"
                                      : "bg-white/8 text-slate-200 hover:bg-white/12",
                                  )}
                                >
                                  {isActive ? "Active" : "Set active"}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => void handleDetachIndex(index.manifest_path)}
                                  className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-slate-200 transition-all hover:bg-white/12 hover:text-white"
                                >
                                  Detach
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {suggestedIndexes.length > 0 ? (
                      <div className="rounded-[1.6rem] border border-white/10 bg-black/18 p-5">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">More to attach</div>
                            <div className="mt-2 text-sm text-slate-300">
                              Add one of these indexes to the star without replacing anything already attached.
                            </div>
                          </div>
                          <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                            {suggestedIndexes.length}
                          </Badge>
                        </div>

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
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="rounded-[1.6rem] border border-dashed border-white/12 bg-black/18 p-5">
                    <div className="flex items-center gap-3 text-white">
                      <Orbit className="size-5 text-[#d6b361]" />
                      <span className="font-medium">This star is not attached to an index yet.</span>
                    </div>
                    <p className="mt-3 text-sm leading-7 text-slate-300">
                      Build a new index or attach one of the indexed sources from the source rail.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          <aside className="border-t border-white/10 bg-[linear-gradient(180deg,rgba(12,16,28,0.98),rgba(8,11,20,0.96))] px-5 py-5 sm:px-6 sm:py-6">
            <div className="space-y-5">
              <div className="rounded-[1.5rem] border border-white/10 bg-white/4 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Star meaning</div>
                    <div className="mt-2 text-sm text-slate-300">
                      Label the star, give it a domain, and describe the kind of thinking it should hold.
                    </div>
                  </div>
                  <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                    {activeManifestPathForChat ? "Grounded" : "Unbound"}
                  </Badge>
                </div>

                <div className="mt-4 space-y-4">
                  <label className="space-y-2">
                    <span className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Star label</span>
                    <Input
                      value={labelDraft}
                      onChange={(event) => setLabelDraft(event.target.value)}
                      placeholder="Name this star"
                    />
                  </label>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="space-y-2">
                      <span className="text-[11px] uppercase tracking-[0.26em] text-slate-400">What part of METIS does this strengthen?</span>
                      <Input
                        value={primaryDomainIdDraft}
                        onChange={(event) => setPrimaryDomainIdDraft(event.target.value)}
                        placeholder="knowledge"
                        list="constellation-faculties"
                      />
                    </label>

                    <label className="space-y-2">
                      <span className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Growth stage</span>
                      <select
                        value={effectiveStage}
                        onChange={(event) => {
                          const nextStage = event.target.value as UserStarStage;
                          setManualStageOverride(nextStage === derivedStage ? "" : nextStage);
                        }}
                        className="flex h-10 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-white shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                      >
                        {STAGE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value} className="bg-slate-950 text-white">
                            {option.label}
                          </option>
                        ))}
                      </select>
                      <p className="text-xs leading-6 text-slate-400">
                        {STAGE_OPTIONS.find((option) => option.value === effectiveStage)?.description}
                      </p>
                    </label>
                  </div>

                  <label className="space-y-2">
                    <span className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Bridge faculties</span>
                    <Input
                      value={relatedDomainIdsDraft}
                      onChange={(event) => setRelatedDomainIdsDraft(event.target.value)}
                      placeholder="memory, strategy"
                      list="constellation-faculties"
                    />
                    <p className="text-xs leading-6 text-slate-400">
                      Optional bridge faculties, comma-separated. Use one when a star should sit between domains.
                    </p>
                  </label>

                  <label className="space-y-2">
                    <span className="text-[11px] uppercase tracking-[0.26em] text-slate-400">What is this star for?</span>
                    <Textarea
                      value={intentDraft}
                      onChange={(event) => setIntentDraft(event.target.value)}
                      rows={3}
                      placeholder="What should this star help you decide, remember, or compare?"
                    />
                  </label>

                  <label className="space-y-2">
                    <span className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Supporting notes</span>
                    <Textarea
                      value={notesDraft}
                      onChange={(event) => setNotesDraft(event.target.value)}
                      rows={4}
                      placeholder="Extra reminders, caveats, or context that keeps the star grounded."
                    />
                  </label>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                    {attachedManifestPaths.length} attached
                  </Badge>
                  <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                    {activeManifestPathForChat ? "Active chat selected" : "No active chat"}
                  </Badge>
                </div>

                <datalist id="constellation-faculties">
                  {CONSTELLATION_FACULTIES.map((faculty) => (
                    <option key={faculty.id} value={faculty.id}>
                      {faculty.label}
                    </option>
                  ))}
                </datalist>
              </div>

              <div className="rounded-[1.5rem] border border-white/10 bg-white/4 p-4">
                <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Source rail</div>
                <div className="mt-3 flex items-center gap-3">
                  <div className="size-3 rounded-full bg-[#d6b361] shadow-[0_0_24px_rgba(214,179,97,0.7)]" />
                  <div>
                    <div className="text-sm font-medium text-white">
                      {labelDraft.trim() || star.label || "Untitled star"}
                    </div>
                    <div className="text-sm text-slate-300">
                      {activeIndex ? "Linked and chat-ready" : "Awaiting an index"}
                    </div>
                  </div>
                </div>
              </div>

              <LearningRoutePanel
                route={displayedLearningRoute}
                previewActive={learningRoutePreview !== null}
                eligible={hasCourseSource}
                loading={learningRouteLoading}
                error={learningRouteError}
                unavailableManifestPaths={unavailableManifestPaths}
                onStartCourse={onStartCourse}
                onSaveRoute={onSaveLearningRoutePreview}
                onDiscardPreview={onDiscardLearningRoutePreview}
                onRegenerateRoute={onRegenerateLearningRoute}
                onLaunchStep={onLaunchLearningRouteStep}
                onSetStepStatus={onSetLearningRouteStepStatus}
              />

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
                  <div className="mt-4 text-sm leading-7 text-emerald-100/85">
                    This build is attached to the star and set active until you choose another orbit.
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
                      : "No other indexed sources are available yet. Build one here to give the star grounded memory."}
                  </p>
                )}
              </div>

            </div>
          </aside>
          </div>

          <div
            className="border-t border-white/10 bg-[linear-gradient(180deg,rgba(12,16,28,0.98),rgba(8,11,20,0.98))] px-5 py-4 sm:px-6"
            data-testid="star-details-actions"
          >
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => void handleSaveMeta()} disabled={savingMeta || removing} className="gap-2">
                {savingMeta ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                Save meaning
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  if (!activeManifestPathForChat) {
                    return;
                  }
                  const linkedLabel = labelDraft.trim() || activeStar.label || activeIndex?.index_id || "Mapped star";
                  onOpenChat({
                    manifestPath: activeManifestPathForChat,
                    label: linkedLabel,
                  });
                }}
                disabled={!activeManifestPathForChat || removing}
              >
                Open chat
              </Button>
              <Button variant="outline" onClick={() => setView("build")} disabled={removing}>
                Add another source
              </Button>
              {entryMode === "existing" ? (
                <Button
                  variant="destructive"
                  onClick={() => setDeleteConfirmOpen(true)}
                  disabled={removing}
                  className="gap-2"
                >
                  <Trash2 className="size-4" />
                  Delete star and sources
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      </DialogContent>

      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent className="max-w-md" data-testid="star-delete-confirmation">
          <DialogHeader className="gap-3">
            <DialogTitle className="font-display text-2xl tracking-[-0.04em] text-white">
              Delete this star and its sources?
            </DialogTitle>
            <DialogDescription className="text-sm leading-7 text-slate-300">
              This will delete the star and purge every METIS-managed index attached to it. Your original local files will remain on disk, but the indexed sources and chat-ready artifacts will be removed permanently.
            </DialogDescription>
          </DialogHeader>

          <div className="rounded-[1.3rem] border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm leading-7 text-rose-100">
            This action cannot be undone.
          </div>

          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)} disabled={removing}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => void handleRemoveStar()}
              disabled={removing}
              className="gap-2"
            >
              {removing ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
              {removing ? "Deleting..." : "Delete star and sources"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Dialog>
  );
}

/* ─────────────────── Faculty concept panel ─────────────────────────── */

interface FacultyConceptPanelProps {
  open: boolean;
  onClose: () => void;
  concept: { label: string; title: string; desc: string } | null;
}

export function FacultyConceptPanel({ open, onClose, concept }: FacultyConceptPanelProps) {
  if (!concept) return null;
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent
        className="left-1/2 top-auto bottom-3 flex h-[calc(100vh-1.5rem)] max-h-[calc(100vh-1.5rem)] w-[calc(100%-1.5rem)] max-w-[calc(100%-1.5rem)] -translate-x-1/2 translate-y-0 flex-col gap-0 overflow-hidden rounded-[1.75rem] border-white/12 bg-[linear-gradient(180deg,rgba(14,20,34,0.98),rgba(8,11,20,0.96))] p-0 sm:left-auto sm:right-4 sm:top-4 sm:bottom-4 sm:h-[calc(100vh-2rem)] sm:max-h-[calc(100vh-2rem)] sm:w-[min(460px,calc(100vw-2rem))] sm:max-w-[460px] sm:translate-x-0 sm:translate-y-0"
        showOverlay={false}
      >
        <div className="border-b border-white/10 bg-[linear-gradient(180deg,rgba(14,20,34,0.98),rgba(10,13,23,0.92))] px-5 py-5 sm:px-6">
          <DialogHeader className="gap-3 pr-10">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.32em] text-[#d6b361]">
              <Orbit className="size-3.5" />
              {concept.label}
            </div>
            <DialogTitle className="font-display text-3xl font-semibold tracking-[-0.05em] text-white">
              {concept.title}
            </DialogTitle>
            <DialogDescription className="text-sm leading-7 text-slate-300">
              {concept.desc}
            </DialogDescription>
          </DialogHeader>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-5 sm:px-6">
          <p className="text-sm leading-relaxed text-slate-400">
            Faculty nodes are the gravitational poles of the constellation. Drag your stars toward{" "}
            <span className="text-slate-200">{concept.title}</span> to align them with this domain, or add a new star near this node to begin building knowledge here.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
