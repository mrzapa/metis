"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { StarObservatoryDialog } from "@/components/constellation/star-observatory-dialog";
import { useConstellationStars } from "@/hooks/use-constellation-stars";
import { fetchIndexes, type IndexBuildResult, type IndexSummary } from "@/lib/api";
import {
  ADD_CANDIDATE_HIT_RADIUS_PX,
  MOBILE_ADD_CANDIDATE_HIT_RADIUS_PX,
  CONSTELLATION_FACULTIES,
  CORE_CENTER_X,
  CORE_CENTER_Y,
  CORE_EXCLUSION_RADIUS,
  buildOutwardPlacement,
  findHoveredAddCandidate,
  getPreviewConnectionNodes,
  inferConstellationFaculty,
  isAddableBackgroundStar,
  projectBackgroundStar,
  type ConstellationFacultyMetadata,
  type ConstellationFieldStar,
  type ConstellationNodePoint,
} from "@/lib/constellation-home";
import type { UserStar } from "@/lib/constellation-types";

/* ────────────────────────────── constants ────────────────────────────── */

const FACULTY_CONCEPTS = CONSTELLATION_FACULTIES.map((faculty, index) => ({
  faculty,
  label: `Faculty ${String(index + 1).padStart(2, "0")}`,
  title: faculty.label,
  desc: faculty.description,
}));
const FACULTY_PALETTE: Record<string, [number, number, number]> = {
  perception: [119, 181, 235],
  knowledge: [232, 184, 74],
  memory: [160, 133, 228],
  reasoning: [129, 220, 198],
  skills: [104, 219, 170],
  strategy: [232, 128, 103],
  personality: [232, 144, 198],
  values: [214, 108, 120],
  synthesis: [136, 209, 238],
  autonomy: [199, 218, 121],
  emergence: [148, 153, 239],
};
const KNOWLEDGE_FACULTY = CONSTELLATION_FACULTIES.find((faculty) => faculty.id === "knowledge") ?? CONSTELLATION_FACULTIES[1];
const HOVER_EXPAND_DELAY_MS = 600;
const DRAG_DISTANCE_PX = 6;

/* ────────────────────────────── helpers ──────────────────────────────── */

type StarData = ConstellationFieldStar;
type FacultyConcept = typeof FACULTY_CONCEPTS[number];

interface NodeData extends ConstellationNodePoint {
  baseSize: number;
  brightness: number; targetBrightness: number;
  concept: FacultyConcept; connections: number[];
  awakenDelay: number; parallax: number;
  hoverBoost: number; targetHoverBoost: number;
  _sx: number; _sy: number;
}

interface DustData {
  x: number; y: number; vx: number; vy: number;
  size: number; opacity: number;
}

function makeStar(layer: number, index: number): StarData {
  const baseSize = Math.random() * (layer === 0 ? 1.2 : layer === 1 ? 0.8 : 0.5) + 0.2;
  return {
    id: `field-star-${layer}-${index}`,
    nx: Math.random(),
    ny: Math.random(),
    layer,
    baseSize,
    brightness: Math.random() * 0.4 + 0.1,
    twinkle: Math.random() > 0.92,
    twinkleSpeed: Math.random() * 0.02 + 0.005,
    twinklePhase: Math.random() * Math.PI * 2,
    parallaxFactor: layer === 0 ? 0.02 : layer === 1 ? 0.008 : 0.003,
    hasDiffraction: baseSize > 1.0 && Math.random() > 0.5,
  };
}

function makeDust(W: number, H: number): DustData {
  return {
    x: Math.random() * W, y: Math.random() * H,
    vx: (Math.random() - 0.5) * 0.15, vy: (Math.random() - 0.5) * 0.1,
    size: Math.random() * 1.2 + 0.3, opacity: Math.random() * 0.06 + 0.02,
  };
}

function buildOptimisticIndexSummary(result: IndexBuildResult): IndexSummary {
  return {
    index_id: result.index_id,
    manifest_path: result.manifest_path,
    document_count: result.document_count,
    chunk_count: result.chunk_count,
    backend: result.vector_backend,
    created_at: new Date().toISOString(),
    embedding_signature: result.embedding_signature,
  };
}

function upsertIndexSummary(current: IndexSummary[], next: IndexSummary): IndexSummary[] {
  return [
    next,
    ...current.filter(
      (index) => index.manifest_path !== next.manifest_path && index.index_id !== next.index_id,
    ),
  ];
}

function getIndexSummaryKey(index: Pick<IndexSummary, "index_id" | "manifest_path">): string {
  return `${index.manifest_path}::${index.index_id}`;
}

function mergeFetchedIndexes(
  current: IndexSummary[],
  fetched: IndexSummary[],
  optimisticKeys: Set<string>,
): IndexSummary[] {
  let next = fetched;

  current.forEach((index) => {
    const key = getIndexSummaryKey(index);
    if (optimisticKeys.has(key) && !next.some((item) => getIndexSummaryKey(item) === key)) {
      next = upsertIndexSummary(next, index);
    }
  });

  fetched.forEach((index) => {
    optimisticKeys.delete(getIndexSummaryKey(index));
  });

  return next;
}

function getCountLabel(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

function getStarManifestPaths(star: UserStar): string[] {
  if (star.linkedManifestPaths && star.linkedManifestPaths.length > 0) {
    return star.linkedManifestPaths;
  }
  return star.linkedManifestPath ? [star.linkedManifestPath] : [];
}

function getStarAttachmentCount(star: UserStar): number {
  return getStarManifestPaths(star).length;
}

function getFacultyColor(facultyId?: string): [number, number, number] {
  if (facultyId && FACULTY_PALETTE[facultyId]) {
    return FACULTY_PALETTE[facultyId];
  }
  return [208, 216, 232];
}

function getFacultyById(facultyId?: string): ConstellationFacultyMetadata | null {
  if (!facultyId) {
    return null;
  }
  return CONSTELLATION_FACULTIES.find((faculty) => faculty.id === facultyId) ?? null;
}

function resolveStarFaculty(star: Pick<UserStar, "x" | "y" | "primaryDomainId">) {
  const inferred = inferConstellationFaculty({ x: star.x, y: star.y });
  return getFacultyById(star.primaryDomainId) ?? inferred.primary.faculty;
}

function getStageRingCount(stage: UserStar["stage"]): number {
  switch (stage) {
    case "integrated":
      return 3;
    case "growing":
      return 2;
    default:
      return 1;
  }
}

function clampPointToOrbit(x: number, y: number): [number, number] {
  const clampedX = Math.min(0.96, Math.max(0.04, x));
  const clampedY = Math.min(0.95, Math.max(0.06, y));
  const dx = clampedX - CORE_CENTER_X;
  const dy = clampedY - CORE_CENTER_Y;
  const distance = Math.hypot(dx, dy);
  if (distance >= CORE_EXCLUSION_RADIUS + 0.02) {
    return [clampedX, clampedY];
  }
  const fallbackAngle = distance === 0 ? -Math.PI / 2 : Math.atan2(dy, dx);
  return buildOutwardPlacement(
    CORE_CENTER_X + Math.cos(fallbackAngle) * (CORE_EXCLUSION_RADIUS + 0.045),
    CORE_CENTER_Y + Math.sin(fallbackAngle) * (CORE_EXCLUSION_RADIUS + 0.045),
    0,
  );
}

function describeFacultyDrop(faculty: ConstellationFacultyMetadata, bridgeFaculty: ConstellationFacultyMetadata | null): string {
  if (bridgeFaculty) {
    return `${faculty.label} primary with a bridge toward ${bridgeFaculty.label}. Release to persist the reassignment.`;
  }
  return `${faculty.label} now leads this star. Release to anchor it here.`;
}

function applyNodeLayout(nodes: NodeData[], W: number, H: number) {
  FACULTY_CONCEPTS.forEach((concept, i) => {
    if (!nodes[i]) {
      return;
    }
    nodes[i].x = concept.faculty.x * W;
    nodes[i].y = concept.faculty.y * H;
  });
}

/* ────────────────────────────── component ────────────────────────────── */

export default function Home() {
  const router = useRouter();
  const {
    userStars,
    syncError,
    addUserStar,
    addUserStars,
    removeUserStarById,
    resetUserStars,
    updateUserStarById,
    starLimit,
  } = useConstellationStars();
  const [addMessage, setAddMessage] = useState<string | null>(null);
  const [selectedUserStarId, setSelectedUserStarId] = useState<string | null>(null);
  const [starDialogOpen, setStarDialogOpen] = useState(false);
  const [starDialogMode, setStarDialogMode] = useState<"new" | "existing">("new");
  const [pendingDialogStar, setPendingDialogStar] = useState<UserStar | null>(null);
  const [queuedObservatoryMode, setQueuedObservatoryMode] = useState<"new" | "existing" | null>(null);
  const [dialogCloseLockedUntil, setDialogCloseLockedUntil] = useState(0);
  const [availableIndexes, setAvailableIndexes] = useState<IndexSummary[]>([]);
  const [indexesLoading, setIndexesLoading] = useState(true);
  const [indexLoadError, setIndexLoadError] = useState<string | null>(null);
  const [hoveredAddCandidateId, setHoveredAddCandidateId] = useState<string | null>(null);
  const [dragMessage, setDragMessage] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [toastTone, setToastTone] = useState<"default" | "error">("default");
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const conceptCardRef = useRef<HTMLDivElement>(null);
  const cLabelRef = useRef<HTMLDivElement>(null);
  const cTitleRef = useRef<HTMLDivElement>(null);
  const cDescRef = useRef<HTMLDivElement>(null);
  const activeNodeRef = useRef(-1);
  const hoveredNodeRef = useRef(-1);
  const hoverStartRef = useRef(0);
  const hoverExpandedRef = useRef(false);
  const coarsePointerRef = useRef(false);
  const mouseRef = useRef({ x: -1000, y: -1000 });
  const userStarsRef = useRef<UserStar[]>(userStars);
  const selectedUserStarIdRef = useRef<string | null>(selectedUserStarId);
  const hoveredAddCandidateRef = useRef<StarData | null>(null);
  const armedAddCandidateIdRef = useRef<string | null>(null);
  const availableIndexesRef = useRef<IndexSummary[]>(availableIndexes);
  const optimisticIndexKeysRef = useRef<Set<string>>(new Set());
  const conceptHideTimeoutRef = useRef<number | null>(null);
  const dragPreviewPositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const dragStateRef = useRef<{
    pointerId: number;
    starId: string;
    startClientX: number;
    startClientY: number;
    startX: number;
    startY: number;
    moved: boolean;
  } | null>(null);

  useEffect(() => {
    userStarsRef.current = userStars;
  }, [userStars]);

  useEffect(() => {
    availableIndexesRef.current = availableIndexes;
  }, [availableIndexes]);

  useEffect(() => {
    selectedUserStarIdRef.current = selectedUserStarId;
  }, [selectedUserStarId]);

  useEffect(() => {
    const previewPositions = dragPreviewPositionsRef.current;
    const validIds = new Set(userStars.map((star) => star.id));
    [...previewPositions.keys()].forEach((starId) => {
      if (!validIds.has(starId)) {
        previewPositions.delete(starId);
      }
    });
  }, [userStars]);

  useEffect(() => () => {
    if (conceptHideTimeoutRef.current !== null) {
      window.clearTimeout(conceptHideTimeoutRef.current);
    }
  }, []);

  const selectedUserStar = useMemo(
    () => userStars.find((star) => star.id === selectedUserStarId) ?? null,
    [selectedUserStarId, userStars],
  );
  const observatoryStar = selectedUserStar ?? pendingDialogStar;
  const mappedManifestPaths = useMemo(
    () =>
      new Set(
        userStars.flatMap((star) => getStarManifestPaths(star)).filter(Boolean),
      ),
    [userStars],
  );
  const unmappedIndexes = useMemo(
    () => availableIndexes.filter((index) => !mappedManifestPaths.has(index.manifest_path)),
    [availableIndexes, mappedManifestPaths],
  );
  const attachmentCount = useMemo(
    () => userStars.reduce((sum, star) => sum + getStarAttachmentCount(star), 0),
    [userStars],
  );
  const selectedStarAttachmentCount = useMemo(
    () => (selectedUserStar ? getStarAttachmentCount(selectedUserStar) : 0),
    [selectedUserStar],
  );
  const selectedStarFaculty = useMemo(
    () => (selectedUserStar ? resolveStarFaculty(selectedUserStar) : null),
    [selectedUserStar],
  );
  const starCountLabel = useMemo(
    () => (starLimit === null ? `${userStars.length} added stars` : `${userStars.length}/${starLimit} added stars`),
    [starLimit, userStars.length],
  );
  const detectedSourceCountLabel = useMemo(
    () => getCountLabel(availableIndexes.length, "indexed source"),
    [availableIndexes.length],
  );
  const readyToMapCountLabel = useMemo(
    () => `${getCountLabel(unmappedIndexes.length, "source")} ready to map`,
    [unmappedIndexes.length],
  );
  const attachmentsCountLabel = useMemo(
    () => getCountLabel(attachmentCount, "attachment"),
    [attachmentCount],
  );
  const fieldGuideMessage = useMemo(() => {
    if (dragMessage) {
      return dragMessage;
    }

    if (starLimit !== null && userStars.length >= starLimit) {
      return "Constellation at capacity. Remove a star or reset the orbit to pull in another.";
    }

    if (hoveredAddCandidateId) {
      return "Field star acquired. Click once to claim it, then give it meaning in its observatory.";
    }

    if (selectedUserStar && selectedStarFaculty) {
      if (selectedStarAttachmentCount > 0) {
        return `${selectedUserStar.label ?? "Selected star"} currently leans into ${selectedStarFaculty.label}. Open its observatory to inspect attached sources or launch grounded chat.`;
      }
      return `${selectedUserStar.label ?? "Selected star"} is orbiting ${selectedStarFaculty.label}. Drag it toward another faculty or open its observatory to feed it.`;
    }

    if (!indexesLoading && unmappedIndexes.length > 0) {
      return `${getCountLabel(unmappedIndexes.length, "indexed source")} ${unmappedIndexes.length === 1 ? "is" : "are"} ready to seed into Knowledge from the control rail below.`;
    }

    return "Follow the faculty ring: claim a field star, drag it toward the faculty it should strengthen, and let the observatory deepen it.";
  }, [dragMessage, hoveredAddCandidateId, indexesLoading, selectedStarAttachmentCount, selectedStarFaculty, selectedUserStar, starLimit, unmappedIndexes.length, userStars.length]);
  const selectedStarSummary = useMemo(() => {
    if (!selectedUserStar || !selectedStarFaculty) {
      return "No star selected. Click a claimed star to open its observatory, or drag one to reassign its faculty.";
    }
    return `${selectedUserStar.label ?? "Selected star"} is aligned with ${selectedStarFaculty.label} and holds ${getCountLabel(selectedStarAttachmentCount, "attached source")}.`;
  }, [selectedStarAttachmentCount, selectedStarFaculty, selectedUserStar]);
  const addMessageTone = useMemo(() => {
    if (!addMessage) {
      return "accent";
    }
    return /unable|failed|error|limit/i.test(addMessage) ? "error" : "accent";
  }, [addMessage]);
  const buildNoteTone = indexLoadError ? "error" : addMessage ? addMessageTone : "accent";
  const buildNoteMessage = indexLoadError ?? addMessage ?? fieldGuideMessage;

  const openChatWithIndex = useCallback(
    (manifestPath: string, label: string) => {
      window.localStorage.setItem(
        "metis_active_index",
        JSON.stringify({ manifest_path: manifestPath, label }),
      );
      router.push("/chat");
    },
    [router],
  );

  const closeConcept = useCallback(() => {
    if (conceptHideTimeoutRef.current !== null) {
      window.clearTimeout(conceptHideTimeoutRef.current);
      conceptHideTimeoutRef.current = null;
    }

    activeNodeRef.current = -1;
    const el = conceptCardRef.current;
    if (el) {
      el.classList.remove("active");
      conceptHideTimeoutRef.current = window.setTimeout(() => {
        el.style.display = "none";
        conceptHideTimeoutRef.current = null;
      }, 400);
    }
  }, []);

  const refreshAvailableIndexes = useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false;
    if (!silent) {
      setIndexesLoading(true);
    }
    setIndexLoadError(null);

    try {
      const indexes = await fetchIndexes();
      const mergedIndexes = mergeFetchedIndexes(
        availableIndexesRef.current,
        indexes,
        optimisticIndexKeysRef.current,
      );
      availableIndexesRef.current = mergedIndexes;
      setAvailableIndexes(mergedIndexes);
      return mergedIndexes;
    } catch (error) {
      console.error("Failed to refresh indexed sources for the constellation", error);
      setIndexLoadError(error instanceof Error ? error.message : "Failed to load indexed sources.");
      return null;
    } finally {
      if (!silent) {
        setIndexesLoading(false);
      }
    }
  }, []);

  const handleIndexBuilt = useCallback((result: IndexBuildResult) => {
    const optimisticIndex = buildOptimisticIndexSummary(result);
    optimisticIndexKeysRef.current.add(getIndexSummaryKey(optimisticIndex));
    setIndexLoadError(null);
    setAddMessage(null);
    setAvailableIndexes((current) => {
      const next = upsertIndexSummary(current, optimisticIndex);
      availableIndexesRef.current = next;
      return next;
    });
    setToastTone("default");
    setToastMessage(`Index ready: ${result.index_id}. It is now available to map into orbit.`);
    void refreshAvailableIndexes({ silent: true });
  }, [refreshAvailableIndexes]);
  const openStarObservatory = useCallback((star: UserStar, mode: "new" | "existing") => {
    setPendingDialogStar(star);
    setSelectedUserStarId(star.id);
    setStarDialogMode(mode);
    setQueuedObservatoryMode(mode);
    setDialogCloseLockedUntil(Date.now() + 450);
  }, []);

  useEffect(() => {
    if (!queuedObservatoryMode || !observatoryStar) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setStarDialogMode(queuedObservatoryMode);
      setStarDialogOpen(true);
      setQueuedObservatoryMode((current) => (current === queuedObservatoryMode ? null : current));
    }, 180);

    return () => window.clearTimeout(timeoutId);
  }, [observatoryStar, queuedObservatoryMode]);

  const mapIndexedSources = useCallback(async () => {
    let indexesForMapping = availableIndexes;
    const refreshedIndexes = await refreshAvailableIndexes();
    if (refreshedIndexes) {
      indexesForMapping = refreshedIndexes;
    }

    const currentMappedPaths = new Set(
      userStars.flatMap((star) => getStarManifestPaths(star)).filter(Boolean),
    );
    const candidateIndexes = indexesForMapping.filter((index) => !currentMappedPaths.has(index.manifest_path));

    if (candidateIndexes.length === 0) {
      setAddMessage(
        indexesForMapping.length === 0
          ? "No indexed sources are available to map yet."
          : "All indexed sources already have constellation stars.",
      );
      return;
    }

    const room = starLimit === null ? candidateIndexes.length : Math.max(0, starLimit - userStars.length);
    if (starLimit !== null && room === 0) {
      setAddMessage(`Star limit reached (${starLimit}/${starLimit}).`);
      return;
    }

    const starsToAdd = candidateIndexes.slice(0, room).map((index, indexOffset) => {
      const orbitIndex = userStars.length + indexOffset;
      const shell = Math.floor(orbitIndex / 6) + 1;
      const slot = orbitIndex % 6;
      const sweep = -0.42 + (slot / 5) * 0.84;
      const angle = KNOWLEDGE_FACULTY.angle + sweep;
      const radius = CORE_EXCLUSION_RADIUS + 0.08 + shell * 0.055;
      const targetX = CORE_CENTER_X + Math.cos(angle) * radius;
      const targetY = CORE_CENTER_Y + Math.sin(angle) * radius * 0.82;
      const [x, y] = buildOutwardPlacement(targetX, targetY, orbitIndex);

      return {
        x,
        y,
        size: 0.95,
        label: index.index_id,
        primaryDomainId: KNOWLEDGE_FACULTY.id,
        stage: "seed" as const,
        intent: "Seeded from indexed source",
        linkedManifestPaths: [index.manifest_path],
        activeManifestPath: index.manifest_path,
        linkedManifestPath: index.manifest_path,
      };
    });

    const addedCount = await addUserStars(starsToAdd);
    if (addedCount > 0) {
      setAddMessage(null);
      setToastTone("default");
      setToastMessage(`Seeded ${addedCount} indexed source${addedCount === 1 ? "" : "s"} into the constellation.`);
    }
  }, [addUserStars, availableIndexes, refreshAvailableIndexes, starLimit, userStars]);

  useEffect(() => {
    void refreshAvailableIndexes();
  }, [refreshAvailableIndexes]);

  useEffect(() => {
    if (selectedUserStar && pendingDialogStar?.id === selectedUserStar.id) {
      setPendingDialogStar(null);
    }
  }, [pendingDialogStar, selectedUserStar]);

  useEffect(() => {
    if (!syncError && !addMessage) {
      return;
    }
    const message = syncError ?? addMessage;
    if (!message) {
      return;
    }
    setToastMessage(message);
    setToastTone(syncError ? "error" : "default");
    const timeoutId = window.setTimeout(() => {
      setToastMessage((current) => (current === message ? null : current));
    }, syncError ? 4200 : 2400);
    return () => window.clearTimeout(timeoutId);
  }, [addMessage, syncError]);

  useEffect(() => {
    if (starLimit !== null && userStars.length >= starLimit) {
      hoveredAddCandidateRef.current = null;
      armedAddCandidateIdRef.current = null;
      setHoveredAddCandidateId(null);
    }
  }, [starLimit, userStars.length]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let W = window.innerWidth;
    let H = window.innerHeight;
    function resize() {
      W = canvas!.width = window.innerWidth;
      H = canvas!.height = window.innerHeight;
    }
    resize();

    /* build stars */
    const stars: StarData[] = [];
    for (let i = 0; i < 400; i++) stars.push(makeStar(2, i));
    for (let i = 0; i < 200; i++) stars.push(makeStar(1, i));
    for (let i = 0; i < 60; i++) stars.push(makeStar(0, i));

    /* nebulae */
    const nebulae = [
      { x: W * 0.72, y: H * 0.35, rx: 380, ry: 260, angle: 0.3, color: [14, 22, 60], opacity: 0.25 },
      { x: W * 0.25, y: H * 0.65, rx: 300, ry: 200, angle: -0.4, color: [20, 15, 35], opacity: 0.2 },
      { x: W * 0.55, y: H * 0.2, rx: 220, ry: 150, angle: 0.8, color: [10, 18, 48], opacity: 0.15 },
    ];

    const motionPreviewEnabled = document.documentElement.dataset.uiVariant === "motion";
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const enhancedHoverMotion = motionPreviewEnabled && !reducedMotion;
    coarsePointerRef.current = window.matchMedia("(pointer: coarse)").matches;

    function syncHoveredCandidate(candidate: StarData | null) {
      const nextId = candidate?.id ?? null;
      if (hoveredAddCandidateRef.current?.id === nextId) {
        hoveredAddCandidateRef.current = candidate;
        return;
      }
      hoveredAddCandidateRef.current = candidate;
      if (!candidate) {
        armedAddCandidateIdRef.current = null;
      }
      setHoveredAddCandidateId((current) => (current === nextId ? current : nextId));
    }

    function clearHoveredCandidate() {
      hoveredAddCandidateRef.current = null;
      armedAddCandidateIdRef.current = null;
      setHoveredAddCandidateId((current) => (current === null ? current : null));
    }

    function showConceptAtNode(idx: number) {
      const c = nodes[idx].concept;
      if (cLabelRef.current) cLabelRef.current.textContent = c.label;
      if (cTitleRef.current) cTitleRef.current.textContent = c.title;
      if (cDescRef.current) cDescRef.current.textContent = c.desc;
      activeNodeRef.current = idx;
      const card = conceptCardRef.current;
      if (!card) return;
      if (conceptHideTimeoutRef.current !== null) {
        window.clearTimeout(conceptHideTimeoutRef.current);
        conceptHideTimeoutRef.current = null;
      }
      let cx = nodes[idx]._sx + 24;
      let cy = nodes[idx]._sy - 60;
      if (cx + 280 > W) cx = nodes[idx]._sx - 300;
      if (cy < 20) cy = 20;
      if (cy + 200 > H) cy = H - 220;
      card.style.left = cx + "px";
      card.style.top = cy + "px";
      card.style.display = "block";
      requestAnimationFrame(() => card.classList.add("active"));
    }

    /* nodes */
    const nodes: NodeData[] = FACULTY_CONCEPTS.map((concept) => ({
      x: 0, y: 0,
      baseSize: 1.5 + Math.random() * 1.5,
      brightness: 0.15, targetBrightness: 0.15,
      concept, connections: [],
      awakenDelay: 2000 + Math.random() * 1500,
      parallax: 0.015,
      hoverBoost: 0,
      targetHoverBoost: 0,
      _sx: 0, _sy: 0,
    }));
    applyNodeLayout(nodes, W, H);
    nodes.forEach((n, i) => {
      const dists = nodes.map((m, j) => ({ idx: j, d: Math.hypot(n.x - m.x, n.y - m.y) }))
        .filter(d => d.idx !== i).sort((a, b) => a.d - b.d);
      n.connections = dists.slice(0, i === 0 ? 5 : 3).map(d => d.idx);
    });

    /* dust */
    const dust: DustData[] = [];
    for (let i = 0; i < 40; i++) dust.push(makeDust(W, H));

    const mouse = mouseRef.current;
    let awakened = false;
    let awakenStart = 0;
    let animFrame = 0;

    function drawNebulae() {
      nebulae.forEach(n => {
        const nx = n.x + (mouse.x - W / 2) * 0.005;
        const ny = n.y + (mouse.y - H / 2) * 0.005;
        ctx!.save();
        ctx!.translate(nx, ny);
        ctx!.rotate(n.angle);
        const grad = ctx!.createRadialGradient(0, 0, 0, 0, 0, n.rx);
        grad.addColorStop(0, `rgba(${n.color[0]},${n.color[1]},${n.color[2]},${n.opacity})`);
        grad.addColorStop(0.5, `rgba(${n.color[0]},${n.color[1]},${n.color[2]},${n.opacity * 0.4})`);
        grad.addColorStop(1, "rgba(0,0,0,0)");
        ctx!.fillStyle = grad;
        ctx!.scale(1, n.ry / n.rx);
        ctx!.beginPath();
        ctx!.arc(0, 0, n.rx, 0, Math.PI * 2);
        ctx!.fill();
        ctx!.restore();
      });
    }

    function drawStar(s: StarData, t: number) {
      const projected = projectBackgroundStar(s, W, H, mouse);
      const px = projected.x;
      const py = projected.y;
      const addable = isAddableBackgroundStar(s, nodes, userStarsRef.current, W, H);
      const hoveredCandidate = hoveredAddCandidateRef.current?.id === s.id;
      let b = s.brightness;
      if (s.twinkle) b += Math.sin(t * s.twinkleSpeed + s.twinklePhase) * 0.15;
      if (addable) {
        const beaconPulse = reducedMotion ? 0.58 : 0.54 + Math.sin(t * 0.0018 + s.twinklePhase) * 0.1;
        b += hoveredCandidate ? 0.22 : 0.08 + beaconPulse * 0.04;
      }
      b = Math.max(0.05, Math.min(1, b));
      let sz = s.baseSize;
      const dx = px - mouse.x, dy = py - mouse.y, dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 200) { const prox = 1 - dist / 200; b += prox * 0.3; sz += prox * 0.5; }
      if (addable) {
        sz += hoveredCandidate ? 0.45 : 0.18;
      }
      const r = addable
        ? 194 + Math.round(b * 36)
        : 180 + Math.round(b * 40);
      const g = addable
        ? 202 + Math.round(b * 28)
        : 195 + Math.round(b * 30);
      const bl = addable
        ? 222 + Math.round(b * 14)
        : 220 + Math.round(b * 20);
      if (addable) {
        const beaconPulse = reducedMotion ? 0.58 : 0.54 + Math.sin(t * 0.0018 + s.twinklePhase) * 0.1;
        const beaconRadius = sz * (hoveredCandidate ? 13 : 8.5) + beaconPulse * 3;
        const candidateGlow = ctx!.createRadialGradient(px, py, 0, px, py, beaconRadius);
        candidateGlow.addColorStop(
          0,
          `rgba(215,187,112,${hoveredCandidate ? 0.18 + beaconPulse * 0.05 : 0.06 + beaconPulse * 0.04})`,
        );
        candidateGlow.addColorStop(1, "rgba(0,0,0,0)");
        ctx!.fillStyle = candidateGlow;
        ctx!.beginPath();
        ctx!.arc(px, py, beaconRadius, 0, Math.PI * 2);
        ctx!.fill();

        if (!hoveredCandidate && sz > 0.5) {
          ctx!.beginPath();
          ctx!.arc(px, py, sz * 2.1 + beaconPulse * 1.3, 0, Math.PI * 2);
          ctx!.strokeStyle = `rgba(219,193,132,${0.08 + beaconPulse * 0.05})`;
          ctx!.lineWidth = 0.4;
          ctx!.stroke();
        }
      }
      ctx!.beginPath(); ctx!.arc(px, py, sz, 0, Math.PI * 2);
      ctx!.fillStyle = `rgba(${r},${g},${bl},${b})`; ctx!.fill();
      if (b > 0.4) {
        ctx!.beginPath(); ctx!.arc(px, py, sz * 3, 0, Math.PI * 2);
        ctx!.fillStyle = `rgba(${r},${g},${bl},${b * 0.08})`; ctx!.fill();
      }
      if (s.hasDiffraction && b > 0.3) {
        const spikeLen = sz * 8 * b;
        ctx!.strokeStyle = `rgba(${r},${g},${bl},${b * 0.15})`; ctx!.lineWidth = 0.5;
        ctx!.beginPath(); ctx!.moveTo(px - spikeLen, py); ctx!.lineTo(px + spikeLen, py);
        ctx!.moveTo(px, py - spikeLen); ctx!.lineTo(px, py + spikeLen); ctx!.stroke();
      }
    }

    function drawUserStars(t: number) {
      const currentUserStars = userStarsRef.current;
      const currentSelectedStarId = selectedUserStarIdRef.current;
      const previewPositions = dragPreviewPositionsRef.current;

      currentUserStars.forEach((s, i) => {
        const previewPosition = previewPositions.get(s.id);
        const starX = previewPosition?.x ?? s.x;
        const starY = previewPosition?.y ?? s.y;
        const faculty = resolveStarFaculty({ x: starX, y: starY, primaryDomainId: s.primaryDomainId });
        const [r, g, b] = getFacultyColor(faculty.id);
        const px = starX * W + (mouse.x - W / 2) * 0.006;
        const py = starY * H + (mouse.y - H / 2) * 0.006;
        const twinkle = 0.75 + Math.sin(t * 0.003 + i * 1.7) * 0.15;
        const selected = currentSelectedStarId === s.id;
        const attachmentCount = getStarAttachmentCount(s);
        const ringCount = getStageRingCount(s.stage);
        const dragging = dragStateRef.current?.starId === s.id && dragStateRef.current.moved;
        const sz = s.size * 1.4 + (selected ? 1.2 : 0) + (dragging ? 0.8 : 0);
        const halo = ctx!.createRadialGradient(px, py, 0, px, py, sz * 5.2);
        halo.addColorStop(0, `rgba(${r},${g},${b},${selected ? 0.22 : 0.12})`);
        halo.addColorStop(1, "rgba(0,0,0,0)");
        ctx!.fillStyle = halo;
        ctx!.beginPath();
        ctx!.arc(px, py, sz * 5.2, 0, Math.PI * 2);
        ctx!.fill();

        const fill = ctx!.createRadialGradient(px - sz * 0.35, py - sz * 0.35, sz * 0.15, px, py, sz * 1.3);
        fill.addColorStop(0, "rgba(255,255,255,0.96)");
        fill.addColorStop(0.28, `rgba(${r},${g},${b},0.92)`);
        fill.addColorStop(1, `rgba(${Math.max(20, r - 78)},${Math.max(20, g - 78)},${Math.max(28, b - 78)},0.98)`);
        ctx!.fillStyle = fill;
        ctx!.beginPath();
        ctx!.arc(px, py, sz, 0, Math.PI * 2);
        ctx!.fill();

        for (let ringIndex = 0; ringIndex < ringCount; ringIndex += 1) {
          const ringRadius = sz + 4 + ringIndex * 4.5;
          ctx!.beginPath();
          ctx!.arc(px, py, ringRadius, 0, Math.PI * 2);
          ctx!.strokeStyle = `rgba(${r},${g},${b},${0.22 + ringIndex * 0.07})`;
          ctx!.lineWidth = ringIndex === ringCount - 1 && selected ? 1.25 : 0.85;
          ctx!.stroke();
        }

        const satelliteCount = Math.min(attachmentCount, 3);
        for (let satelliteIndex = 0; satelliteIndex < satelliteCount; satelliteIndex += 1) {
          const angle = t * 0.001 + (Math.PI * 2 * satelliteIndex) / Math.max(1, satelliteCount);
          const orbitRadius = sz + 11 + satelliteIndex * 2;
          const satelliteX = px + Math.cos(angle) * orbitRadius;
          const satelliteY = py + Math.sin(angle) * orbitRadius * 0.8;
          ctx!.beginPath();
          ctx!.arc(satelliteX, satelliteY, 1.3 + satelliteIndex * 0.25, 0, Math.PI * 2);
          ctx!.fillStyle = `rgba(${r},${g},${b},0.85)`;
          ctx!.fill();
        }

        ctx!.beginPath();
        ctx!.arc(px, py, sz * 0.34, 0, Math.PI * 2);
        ctx!.fillStyle = `rgba(255,255,255,${0.88 + twinkle * 0.08})`;
        ctx!.fill();
      });
    }

    function drawDust() {
      dust.forEach(d => {
        d.x += d.vx + (mouse.x - W / 2) * 0.00008;
        d.y += d.vy + (mouse.y - H / 2) * 0.00008;
        if (d.x < -10) d.x = W + 10; if (d.x > W + 10) d.x = -10;
        if (d.y < -10) d.y = H + 10; if (d.y > H + 10) d.y = -10;
        ctx!.beginPath(); ctx!.arc(d.x, d.y, d.size, 0, Math.PI * 2);
        ctx!.fillStyle = `rgba(160,170,200,${d.opacity})`; ctx!.fill();
      });
    }

    function drawNodes(t: number) {
      const aNode = activeNodeRef.current;
      const hasAddCandidate = hoveredAddCandidateRef.current !== null;
      nodes.forEach((n, i) => {
        const [r, g, bl] = getFacultyColor(n.concept.faculty.id);
        const px = n.x + (mouse.x - W / 2) * n.parallax;
        const py = n.y + (mouse.y - H / 2) * n.parallax;
        const dx = px - mouse.x, dy = py - mouse.y, dist = Math.sqrt(dx * dx + dy * dy);
        const proximity = dist < 180 ? 1 - dist / 180 : 0;
        let nodeAwakenProg = 0;
        if (awakened && t - awakenStart > n.awakenDelay) {
          nodeAwakenProg = Math.min(1, (t - awakenStart - n.awakenDelay) / 1500);
        }
        n.targetBrightness = 0.1 + nodeAwakenProg * 0.2 + proximity * 0.5;
        if (i === aNode) n.targetBrightness = 0.9;
        n.brightness += (n.targetBrightness - n.brightness) * 0.06;
        n.targetHoverBoost = hasAddCandidate ? 0 : hoveredNodeRef.current === i ? 1 : 0;
        n.hoverBoost += (n.targetHoverBoost - n.hoverBoost) * (enhancedHoverMotion ? 0.12 : 0.25);
        const b = n.brightness;
        const hoverScale = enhancedHoverMotion ? n.hoverBoost * 2.6 : 0;
        const s = n.baseSize + proximity * 2 + (i === aNode ? 1 : 0) + hoverScale;

        if (proximity > 0.05 || i === aNode || nodeAwakenProg > 0.5) {
          const lineAlpha = Math.max(proximity * 0.25, nodeAwakenProg * 0.06, i === aNode ? 0.2 : 0);
          n.connections.forEach(ci => {
            const cn = nodes[ci];
            const cpx = cn.x + (mouse.x - W / 2) * cn.parallax;
            const cpy = cn.y + (mouse.y - H / 2) * cn.parallax;
            ctx!.beginPath(); ctx!.moveTo(px, py); ctx!.lineTo(cpx, cpy);
            ctx!.strokeStyle = `rgba(160,175,210,${lineAlpha})`; ctx!.lineWidth = 0.5; ctx!.stroke();
          });
        }
        if (b > 0.25 || n.hoverBoost > 0.1) {
          const grad = ctx!.createRadialGradient(px, py, 0, px, py, s * 12);
          grad.addColorStop(0, `rgba(${r},${g},${bl},${b * 0.08 + n.hoverBoost * 0.12})`);
          grad.addColorStop(1, "rgba(0,0,0,0)");
          ctx!.fillStyle = grad; ctx!.beginPath();
          ctx!.arc(px, py, s * 12, 0, Math.PI * 2); ctx!.fill();
        }
        ctx!.beginPath(); ctx!.arc(px, py, s, 0, Math.PI * 2);
        ctx!.fillStyle = b > 0.36 ? `rgba(${r},${g},${bl},${Math.max(0.42, b)})` : `rgba(200,210,230,${b})`;
        ctx!.fill();
        if (proximity > 0.2) {
          ctx!.beginPath(); ctx!.arc(px, py, s + 4 + proximity * 4, 0, Math.PI * 2);
          ctx!.strokeStyle = `rgba(${r},${g},${bl},${proximity * 0.22})`; ctx!.lineWidth = 0.5; ctx!.stroke();
        }
        ctx!.font = '11px "Space Grotesk", sans-serif';
        ctx!.textAlign = "center";
        ctx!.fillStyle = `rgba(${r},${g},${bl},${0.36 + b * 0.22})`;
        ctx!.fillText(n.concept.title, px, py + s + 18);
        n._sx = px; n._sy = py;
      });
    }

    function drawAddCandidatePreview(ts: number) {
      const candidate = hoveredAddCandidateRef.current;
      if (!candidate) {
        return;
      }

      const previewNodes = getPreviewConnectionNodes(candidate, nodes, W, H);
      const projected = projectBackgroundStar(candidate, W, H, mouse);
      const px = projected.x;
      const py = projected.y;
      const pulse = reducedMotion ? 0.72 : 0.7 + Math.sin(ts * 0.008) * 0.18;

      ctx!.save();
      if (!reducedMotion) {
        ctx!.setLineDash([8, 10]);
        ctx!.lineDashOffset = -ts * 0.018;
      }

      previewNodes.forEach((node, index) => {
        const grad = ctx!.createLinearGradient(node._sx, node._sy, px, py);
        grad.addColorStop(0, `rgba(232,184,74,${0.18 + pulse * 0.08})`);
        grad.addColorStop(1, `rgba(240,244,255,${0.28 + pulse * 0.12})`);
        ctx!.strokeStyle = grad;
        ctx!.lineWidth = index === 0 ? 1.15 : 0.75;
        ctx!.beginPath();
        ctx!.moveTo(node._sx, node._sy);
        ctx!.lineTo(px, py);
        ctx!.stroke();
      });
      ctx!.restore();

      const halo = candidate.baseSize * 10 + 12 + pulse * 4;
      const glow = ctx!.createRadialGradient(px, py, 0, px, py, halo);
      glow.addColorStop(0, `rgba(240,244,255,${0.34 + pulse * 0.12})`);
      glow.addColorStop(0.45, `rgba(196,149,58,${0.18 + pulse * 0.08})`);
      glow.addColorStop(1, "rgba(0,0,0,0)");
      ctx!.fillStyle = glow;
      ctx!.beginPath();
      ctx!.arc(px, py, halo, 0, Math.PI * 2);
      ctx!.fill();

      ctx!.beginPath();
      ctx!.arc(px, py, candidate.baseSize + 2 + pulse * 0.8, 0, Math.PI * 2);
      ctx!.fillStyle = `rgba(245,248,255,${0.9})`;
      ctx!.fill();

      ctx!.beginPath();
      ctx!.arc(px, py, candidate.baseSize * 3.5 + pulse * 2.5, 0, Math.PI * 2);
      ctx!.strokeStyle = `rgba(196,149,58,${0.32 + pulse * 0.12})`;
      ctx!.lineWidth = 0.8;
      ctx!.stroke();

      if (!reducedMotion && previewNodes.length > 0) {
        const lead = previewNodes[0];
        const travel = (Math.sin(ts * 0.004) + 1) / 2;
        const sparkX = lead._sx + (px - lead._sx) * travel;
        const sparkY = lead._sy + (py - lead._sy) * travel;
        ctx!.beginPath();
        ctx!.arc(sparkX, sparkY, 1.6, 0, Math.PI * 2);
        ctx!.fillStyle = "rgba(255,246,222,0.92)";
        ctx!.fill();
      }
    }

    function render(ts: number) {
      ctx!.fillStyle = "rgba(6,8,14,1)";
      ctx!.fillRect(0, 0, W, H);
      if (!awakened && ts > 2000) {
        awakened = true; awakenStart = ts;
      }
      drawNebulae();
      stars.forEach(s => drawStar(s, ts));
      drawDust();
      drawNodes(ts);
      drawAddCandidatePreview(ts);
      drawUserStars(ts);
      animFrame = requestAnimationFrame(render);
    }
    animFrame = requestAnimationFrame(render);

    function onResize() {
      resize();
      applyNodeLayout(nodes, W, H);
      nebulae[0].x = W * 0.72; nebulae[0].y = H * 0.35;
      nebulae[1].x = W * 0.25; nebulae[1].y = H * 0.65;
      nebulae[2].x = W * 0.55; nebulae[2].y = H * 0.2;
    }

    function getHitStar(clientX: number, clientY: number): UserStar | null {
      const rect = canvas!.getBoundingClientRect();
      const cx = clientX - rect.left;
      const cy = clientY - rect.top;
      const previewPositions = dragPreviewPositionsRef.current;
      const hitRadiusBoost = coarsePointerRef.current ? 12 : 0;
      let selectedStar: UserStar | null = null;
      let hitDistance = Infinity;

      userStarsRef.current.forEach((star) => {
        const previewPosition = previewPositions.get(star.id);
        const px = (previewPosition?.x ?? star.x) * rect.width;
        const py = (previewPosition?.y ?? star.y) * rect.height;
        const hitRadius = star.size * 10 + 8 + hitRadiusBoost;
        const distance = Math.hypot(px - cx, py - cy);
        if (distance < hitRadius && distance < hitDistance) {
          selectedStar = star;
          hitDistance = distance;
        }
      });

      return selectedStar;
    }

    function clearDragState(clearMessage = false) {
      const currentDrag = dragStateRef.current;
      if (currentDrag) {
        dragPreviewPositionsRef.current.delete(currentDrag.starId);
      }
      dragStateRef.current = null;
      if (clearMessage) {
        setDragMessage(null);
      }
    }

    function onPointerMove(e: PointerEvent) {
      mouse.x = e.clientX;
      mouse.y = e.clientY;

      const dragState = dragStateRef.current;
      if (dragState && dragState.pointerId === e.pointerId) {
        const rect = canvas!.getBoundingClientRect();
        const nx = (e.clientX - rect.left) / rect.width;
        const ny = (e.clientY - rect.top) / rect.height;
        const travelDistance = Math.hypot(e.clientX - dragState.startClientX, e.clientY - dragState.startClientY);
        if (!dragState.moved && travelDistance >= DRAG_DISTANCE_PX) {
          dragState.moved = true;
        }
        if (!dragState.moved) {
          return;
        }
        const [nextX, nextY] = clampPointToOrbit(nx, ny);
        dragPreviewPositionsRef.current.set(dragState.starId, { x: nextX, y: nextY });
        const inference = inferConstellationFaculty({ x: nextX, y: nextY });
        setDragMessage(
          describeFacultyDrop(
            inference.primary.faculty,
            inference.bridgeSuggestion?.faculty ?? null,
          ),
        );
        clearHoveredCandidate();
        closeConcept();
        return;
      }

      const topElement = document.elementFromPoint(e.clientX, e.clientY);
      const pointerOnCanvas = topElement === canvas;
      if (!pointerOnCanvas) {
        hoveredNodeRef.current = -1;
        hoverExpandedRef.current = false;
        clearHoveredCandidate();
        return;
      }

      const canAddMoreStars = starLimit === null || userStarsRef.current.length < starLimit;
      if (canAddMoreStars) {
        const candidate = findHoveredAddCandidate(
          stars,
          nodes,
          userStarsRef.current,
          { x: e.clientX, y: e.clientY },
          mouse,
          W,
          H,
          coarsePointerRef.current ? MOBILE_ADD_CANDIDATE_HIT_RADIUS_PX : ADD_CANDIDATE_HIT_RADIUS_PX,
        );

        syncHoveredCandidate(candidate);
        if (candidate) {
          hoveredNodeRef.current = -1;
          hoverExpandedRef.current = false;
          closeConcept();
          return;
        }
      } else {
        clearHoveredCandidate();
      }

      let hover = -1;
      nodes.forEach((n, i) => {
        if (Math.hypot(n._sx - e.clientX, n._sy - e.clientY) < 28) {
          hover = i;
        }
      });
      if (hover !== hoveredNodeRef.current) {
        hoveredNodeRef.current = hover;
        hoverStartRef.current = hover >= 0 ? performance.now() : 0;
        hoverExpandedRef.current = false;
      }
      if (
        enhancedHoverMotion &&
        hover >= 0 &&
        !hoverExpandedRef.current &&
        performance.now() - hoverStartRef.current >= HOVER_EXPAND_DELAY_MS
      ) {
        hoverExpandedRef.current = true;
        showConceptAtNode(hover);
      }
    }

    function onCanvasPointerDown(e: PointerEvent) {
      const hitStar = getHitStar(e.clientX, e.clientY);
      if (!hitStar) {
        return;
      }

      dragStateRef.current = {
        pointerId: e.pointerId,
        starId: hitStar.id,
        startClientX: e.clientX,
        startClientY: e.clientY,
        startX: hitStar.x,
        startY: hitStar.y,
        moved: false,
      };
      setSelectedUserStarId(hitStar.id);
      setPendingDialogStar(null);
      setQueuedObservatoryMode(null);
      setAddMessage(null);
      setDragMessage(null);
      clearHoveredCandidate();
      closeConcept();
      try {
        canvas!.setPointerCapture(e.pointerId);
      } catch {
        // Ignore capture failures; drag still works via document listeners.
      }
    }

    function onCanvasPress(e: PointerEvent) {
      const dragState = dragStateRef.current;
      if (dragState && dragState.pointerId === e.pointerId) {
        const selectedStar = userStarsRef.current.find((star) => star.id === dragState.starId) ?? null;
        const previewPosition = dragPreviewPositionsRef.current.get(dragState.starId);

        if (dragState.moved && selectedStar && previewPosition) {
          const inference = inferConstellationFaculty(previewPosition);
          void updateUserStarById(dragState.starId, {
            x: previewPosition.x,
            y: previewPosition.y,
            primaryDomainId: inference.primary.faculty.id,
            relatedDomainIds: inference.bridgeSuggestion ? [inference.bridgeSuggestion.faculty.id] : undefined,
          });
          setToastTone("default");
          setToastMessage(
            `${selectedStar.label ?? "Star"} settled into ${inference.primary.faculty.label}.`,
          );
          setAddMessage(null);
          clearDragState(true);
          return;
        }

        clearDragState(true);
        if (selectedStar) {
          openStarObservatory(selectedStar, "existing");
        }
        return;
      }

      const topElement = document.elementFromPoint(e.clientX, e.clientY);
      if (topElement !== canvas) {
        return;
      }

      const currentUserStars = userStarsRef.current;
      const currentSelectedStarId = selectedUserStarIdRef.current;
      const candidate = (starLimit === null || currentUserStars.length < starLimit)
        ? findHoveredAddCandidate(
            stars,
            nodes,
            currentUserStars,
            { x: e.clientX, y: e.clientY },
            mouse,
            W,
            H,
            coarsePointerRef.current ? MOBILE_ADD_CANDIDATE_HIT_RADIUS_PX : ADD_CANDIDATE_HIT_RADIUS_PX,
          )
        : null;

      if (candidate) {
        if (coarsePointerRef.current && armedAddCandidateIdRef.current !== candidate.id) {
          armedAddCandidateIdRef.current = candidate.id;
          hoveredAddCandidateRef.current = candidate;
          setHoveredAddCandidateId((current) => (current === candidate.id ? current : candidate.id));
          setAddMessage("Tap the same star again to pull it in and open its observatory.");
          closeConcept();
          return;
        }

        const inference = inferConstellationFaculty({ x: candidate.nx, y: candidate.ny });
        addUserStar({
          x: candidate.nx,
          y: candidate.ny,
          size: 0.82 + Math.random() * 0.55,
          primaryDomainId: inference.primary.faculty.id,
          relatedDomainIds: inference.bridgeSuggestion ? [inference.bridgeSuggestion.faculty.id] : undefined,
          stage: "seed",
        }).then((createdStar) => {
          if (!createdStar) {
            setAddMessage(
              starLimit !== null && userStarsRef.current.length >= starLimit
                ? `Star limit reached (${starLimit}/${starLimit}).`
                : "Unable to place another star right now.",
            );
            return;
          }

          setAddMessage(null);
          setToastTone("default");
          setToastMessage("Star added to the constellation. Its observatory is open.");
          openStarObservatory(createdStar, "new");
          clearHoveredCandidate();
        });
        closeConcept();
        return;
      }

      armedAddCandidateIdRef.current = null;
      if (currentSelectedStarId) {
        setSelectedUserStarId(null);
        setPendingDialogStar(null);
        setQueuedObservatoryMode(null);
      }
      let hit = -1;
      nodes.forEach((n, i) => {
        const nodeHitRadius = coarsePointerRef.current ? 34 : 24;
        if (Math.hypot(n._sx - e.clientX, n._sy - e.clientY) < nodeHitRadius) hit = i;
      });
      if (hit >= 0) {
        if (activeNodeRef.current === hit) { closeConcept(); return; }
        showConceptAtNode(hit);
      } else {
        closeConcept();
      }
    }

    function onPointerLeave() {
      if (dragStateRef.current) {
        return;
      }
      hoveredNodeRef.current = -1;
      hoverExpandedRef.current = false;
      clearHoveredCandidate();
      setDragMessage(null);
    }

    function onBlur() {
      clearDragState(true);
      onPointerLeave();
    }

    window.addEventListener("resize", onResize);
    canvas.addEventListener("pointerdown", onCanvasPointerDown);
    document.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onCanvasPress);
    canvas.addEventListener("pointerleave", onPointerLeave);
    window.addEventListener("blur", onBlur);

    return () => {
      cancelAnimationFrame(animFrame);
      window.removeEventListener("resize", onResize);
      canvas.removeEventListener("pointerdown", onCanvasPointerDown);
      document.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onCanvasPress);
      canvas.removeEventListener("pointerleave", onPointerLeave);
      window.removeEventListener("blur", onBlur);
    };
  }, [addUserStar, closeConcept, openStarObservatory, starLimit, updateUserStarById]);

  /* card scroll animation */
  useEffect(() => {
    const cards = document.querySelectorAll<HTMLElement>(".metis-card");
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const card = entry.target as HTMLElement;
          const idx = Array.from(cards).indexOf(card);
          setTimeout(() => card.classList.add("card-visible"), idx * 180);
          observer.unobserve(card);
        }
      });
    }, { threshold: 0.15 });
    cards.forEach(c => observer.observe(c));
    return () => observer.disconnect();
  }, []);

  return (
    <>
      <style>{metisStyles}</style>

      <nav className="metis-nav">
        <div className="metis-nav-left">
          <div className="metis-logo">METIS<sup>AI</sup></div>
          <Link href="/chat" className="metis-nav-link">Chat</Link>
          <Link href="/settings" className="metis-nav-link">Settings</Link>
        </div>
        <div className="metis-nav-right" />
      </nav>

      <canvas ref={canvasRef} id="universe" className="metis-universe" />

      <div className="metis-hero-overlay">
        <div className="metis-hero-shell">
          <div className="metis-hero-kicker">Cognitive Constellation</div>
          <h1 className="metis-hero-headline">Give the night sky a mind.</h1>
          <p className="metis-hero-copy">
            METIS now arranges the landing field around cognitive faculties. Seed knowledge,
            drag stars into the faculty they should strengthen, and keep the observatory magic
            while every claim starts to mean something.
          </p>
          <div className="metis-hero-actions">
            <a href="#build-map" className="metis-cta-btn">Build the constellation</a>
            <Link href="/chat" className="metis-secondary-link">Enter chat</Link>
          </div>
          <div className="metis-field-guide">
            <div className="metis-field-guide-label">Field guide</div>
            <div className="metis-field-guide-text">{fieldGuideMessage}</div>
          </div>
        </div>
      </div>

      <section id="build-map" className="metis-build-section">
        <div className="metis-build-intro">
          <div className="metis-section-kicker">Build And Control</div>
          <h2 className="metis-section-title">Tune the faculties METIS keeps in orbit.</h2>
          <p className="metis-section-copy">
            Indexed sources now seed into <span className="metis-inline-accent">Knowledge</span> by
            default. Claimed stars can be dragged across the faculty ring to persist a new domain,
            while observatories still handle naming, source attachment, and grounded chat.
          </p>
        </div>

        <div className="metis-build-toolbar">
          <div className="metis-build-stats">
            <div className="metis-build-stat">{detectedSourceCountLabel} detected</div>
            <div className="metis-build-stat">{readyToMapCountLabel}</div>
            <div className="metis-build-stat">{starCountLabel}</div>
            <div className="metis-build-stat">{attachmentsCountLabel} in orbit</div>
          </div>

          <div className="metis-star-controls-actions">
            <button
              type="button"
              className="metis-star-btn"
              onClick={() => void mapIndexedSources()}
              disabled={indexesLoading || unmappedIndexes.length === 0}
            >
              Seed indexed sources
            </button>
            <button
              type="button"
              className="metis-star-btn danger"
              onClick={() => {
                if (!selectedUserStarId) {
                  return;
                }
                void removeUserStarById(selectedUserStarId).then(() => {
                  setSelectedUserStarId(null);
                  setPendingDialogStar(null);
                  setQueuedObservatoryMode(null);
                  setToastTone("default");
                  setToastMessage("Selected star removed from the constellation.");
                });
              }}
              disabled={!selectedUserStarId}
            >
              Remove selected
            </button>
            <button
              type="button"
              className="metis-star-btn"
              onClick={() => {
                void resetUserStars().then(() => {
                  setSelectedUserStarId(null);
                  setPendingDialogStar(null);
                  setQueuedObservatoryMode(null);
                  setToastTone("default");
                  setToastMessage("Orbit reset. The field is open again.");
                });
              }}
              disabled={userStars.length === 0}
            >
              Reset orbit
            </button>
          </div>
        </div>

        <div className={`metis-build-note ${buildNoteTone}`}>
          {buildNoteMessage}
        </div>
        <div className="metis-build-note">
          {selectedStarSummary}
        </div>
      </section>

      <section className="metis-cards-section" aria-label="Constellation guide">
        <article className="metis-card">
          <div className="metis-card-label">Seed</div>
          <h3 className="metis-card-title">Knowledge enters first</h3>
          <p className="metis-card-desc">
            Indexed sources map in as seed stars inside the Knowledge arc so the constellation starts
            from evidence, not abstraction.
          </p>
        </article>
        <article className="metis-card">
          <div className="metis-card-label">Steer</div>
          <h3 className="metis-card-title">Move stars toward the right faculty</h3>
          <p className="metis-card-desc">
            Drag a claimed star until the field guide feels right. Drop to persist the new faculty,
            with soft bridge hints when a star sits between domains.
          </p>
        </article>
        <article className="metis-card">
          <div className="metis-card-label">Claim</div>
          <h3 className="metis-card-title">Each star opens its own observatory</h3>
          <p className="metis-card-desc">
            Click-to-claim remains intact. Every star can still be named, fed, linked to sources,
            and opened directly into grounded chat.
          </p>
        </article>
      </section>

      {toastMessage ? (
        <div className={`metis-toast ${toastTone === "error" ? "error" : ""}`} aria-live="polite">
          {toastMessage}
        </div>
      ) : null}

      <StarObservatoryDialog
        open={starDialogOpen}
        onOpenChange={setStarDialogOpen}
        star={observatoryStar}
        entryMode={starDialogMode}
        closeLockedUntil={dialogCloseLockedUntil}
        availableIndexes={availableIndexes}
        indexesLoading={indexesLoading}
        onIndexBuilt={handleIndexBuilt}
        onUpdateStar={updateUserStarById}
        onRemoveStar={async (starId) => {
          await removeUserStarById(starId);
          setSelectedUserStarId((current) => (current === starId ? null : current));
          setPendingDialogStar((current) => (current?.id === starId ? null : current));
          setQueuedObservatoryMode(null);
          setToastTone("default");
          setToastMessage("Star removed from the constellation.");
        }}
        onOpenChat={openChatWithIndex}
      />

      {/* Concept tooltip card */}
      <div ref={conceptCardRef} className="metis-concept-card" id="conceptCard">
        <button className="metis-c-close" onClick={closeConcept}>×</button>
        <div ref={cLabelRef} className="metis-c-label" />
        <div ref={cTitleRef} className="metis-c-title" />
        <div ref={cDescRef} className="metis-c-desc" />
      </div>

      {/* Chat bubble */}
      <Link href="/chat" className="metis-chat-bubble" aria-label="Open chat">
        <svg className="metis-celestial-star-svg" viewBox="0 0 44 44" fill="none" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <radialGradient id="starGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#fff5dc" stopOpacity={0.95} />
              <stop offset="35%" stopColor="#e8c882" stopOpacity={0.6} />
              <stop offset="100%" stopColor="#c4953a" stopOpacity={0} />
            </radialGradient>
            <radialGradient id="outerHalo" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#c4953a" stopOpacity={0.12} />
              <stop offset="100%" stopColor="#c4953a" stopOpacity={0} />
            </radialGradient>
          </defs>
          <circle cx="22" cy="22" r="20" fill="url(#outerHalo)" />
          <polygon points="22,2 23.5,18 42,22 23.5,26 22,42 20.5,26 2,22 20.5,18" fill="url(#starGlow)" opacity={0.55} />
          <polygon points="22,8 24,18.5 36,10 25.5,20 36,34 24,25.5 22,36 20,25.5 8,34 18.5,20 8,10 20,18.5" fill="url(#starGlow)" opacity={0.3} />
          <circle cx="22" cy="22" r="3" fill="#fff5dc" opacity={0.9} />
          <circle cx="22" cy="22" r="1.5" fill="#ffffff" opacity={0.95} />
          <circle cx="22" cy="10" r="0.7" fill="#d4c3a0" opacity={0.45} />
          <circle cx="32" cy="28" r="0.5" fill="#d4c3a0" opacity={0.35} />
          <circle cx="13" cy="30" r="0.6" fill="#d4c3a0" opacity={0.4} />
        </svg>
      </Link>
    </>
  );
}

/* ──────────── inline styles (mirrors the raw HTML design verbatim) ──────────── */

const metisStyles = `
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500&family=Space+Grotesk:wght@300;400;500;600&family=Outfit:wght@200;300;400;500&display=swap');

:root {
  --bg-deep: #06080e;
  --bg-navy: #0a0f1e;
  --cobalt: #1a3a6e;
  --cobalt-light: #2a5a9e;
  --gold: #c4953a;
  --gold-dim: #8a6a2a;
  --gold-bright: #e8b84a;
  --star-white: #d0d8e8;
  --text-dim: rgba(180, 190, 210, 0.4);
  --text-mid: rgba(200, 210, 225, 0.6);
  --text-bright: rgba(220, 228, 240, 0.85);
}

html {
  scroll-behavior: smooth;
}

body {
  background: var(--bg-deep) !important;
  color: var(--text-mid);
  font-family: 'Inter', sans-serif;
  overflow-x: hidden;
  cursor: crosshair;
}

/* NAV */
.metis-nav {
  position: fixed;
  top: 0; left: 0; right: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28px 48px;
  background: transparent;
}
.metis-nav-left { display: flex; align-items: center; gap: 40px; }
.metis-logo {
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 600; font-size: 15px;
  letter-spacing: 3px; color: var(--text-bright);
  text-transform: uppercase;
}
.metis-logo sup { font-size: 8px; opacity: 0.4; vertical-align: super; margin-left: 2px; }
.metis-nav-link {
  font-size: 13px; font-weight: 400;
  color: var(--text-dim); text-decoration: none;
  letter-spacing: 0.5px; transition: color 0.4s ease;
}
.metis-nav-link:hover { color: var(--text-bright); }
.metis-nav-right { display: flex; align-items: center; gap: 32px; }

/* HERO CANVAS */
.metis-universe {
  position: fixed; top: 0; left: 0;
  width: 100vw; height: 100vh; z-index: 1;
  touch-action: none;
}

.metis-toast {
  position: fixed;
  left: 50%;
  top: 90px;
  transform: translateX(-50%);
  z-index: 170;
  min-width: min(420px, calc(100vw - 32px));
  max-width: calc(100vw - 32px);
  padding: 10px 14px;
  border-radius: 12px;
  background: rgba(16, 23, 42, 0.92);
  border: 1px solid rgba(200,210,225,0.14);
  color: var(--text-bright);
  box-shadow: 0 12px 30px rgba(0,0,0,0.24);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  font-size: 12px;
  line-height: 1.45;
  text-align: center;
}

.metis-toast.error {
  border-color: rgba(255,120,120,0.35);
  color: rgba(255,214,214,0.98);
}

/* HERO OVERLAY */
.metis-hero-overlay {
  position: relative; z-index: 10;
  min-height: 100vh;
  display: flex;
  align-items: flex-end;
  padding: 0 48px 88px;
  pointer-events: none;
}
.metis-hero-shell {
  max-width: 620px;
}
.metis-hero-kicker {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 12px;
  letter-spacing: 0.44em;
  text-transform: uppercase;
  color: rgba(232,184,74,0.75);
  opacity: 0;
  transform: translateY(16px);
  animation: metis-fadeUp 1.2s ease 2.25s forwards;
}
.metis-hero-headline {
  font-family: 'Outfit', sans-serif;
  font-weight: 200;
  font-size: clamp(42px, 5.5vw, 72px);
  line-height: 1.1; color: var(--text-bright);
  opacity: 0; transform: translateY(20px);
  animation: metis-fadeUp 1.8s ease 2.8s forwards;
  max-width: 560px; letter-spacing: -0.5px;
  margin-top: 12px;
}
.metis-hero-copy {
  margin-top: 20px;
  max-width: 520px;
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-mid);
  opacity: 0;
  transform: translateY(16px);
  animation: metis-fadeUp 1.4s ease 3.25s forwards;
}
.metis-hero-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 18px;
  margin-top: 30px;
  pointer-events: all;
  opacity: 0;
  transform: translateY(16px);
  animation: metis-fadeUp 1.25s ease 3.7s forwards;
}
.metis-cta-btn {
  display: inline-block;
  padding: 12px 32px;
  border: 1px solid rgba(200, 210, 225, 0.1);
  border-radius: 40px; color: var(--text-mid);
  font-size: 12px; font-weight: 400;
  letter-spacing: 1.5px; text-transform: uppercase;
  text-decoration: none; pointer-events: all;
  transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
  background: rgba(20, 30, 60, 0.35);
  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  cursor: pointer; font-family: 'Inter', sans-serif;
  box-shadow: 0 0 20px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.04);
}
.metis-cta-btn:hover {
  border-color: rgba(196, 149, 58, 0.2); color: var(--gold-bright);
  background: rgba(25, 38, 75, 0.45);
  box-shadow: 0 0 40px rgba(196,149,58,0.08), inset 0 1px 0 rgba(255,255,255,0.06);
  transform: translateY(-1px);
}
.metis-secondary-link {
  color: var(--text-mid);
  text-decoration: none;
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  transition: color 0.3s ease, opacity 0.3s ease;
}
.metis-secondary-link:hover {
  color: var(--text-bright);
}
.metis-field-guide {
  margin-top: 22px;
  max-width: 470px;
  display: grid;
  gap: 6px;
  opacity: 0;
  transform: translateY(16px);
  animation: metis-fadeUp 1.25s ease 4.05s forwards;
}
.metis-field-guide-label,
.metis-section-kicker,
.metis-star-editor-head,
.metis-star-field-label {
  color: rgba(232,184,74,0.82);
  font-family: 'Space Grotesk', sans-serif;
  font-size: 11px;
  letter-spacing: 0.28em;
  text-transform: uppercase;
}
.metis-field-guide-text {
  color: var(--text-mid);
  font-size: 13px;
  line-height: 1.7;
}

/* BUILD SECTION */
.metis-build-section {
  position: relative;
  z-index: 10;
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 48px 96px;
}
.metis-build-intro {
  max-width: 820px;
}
.metis-section-title {
  margin-top: 12px;
  font-family: 'Space Grotesk', sans-serif;
  font-size: clamp(32px, 3vw, 48px);
  line-height: 1.08;
  color: var(--text-bright);
  letter-spacing: -0.04em;
}
.metis-section-copy {
  margin-top: 16px;
  max-width: 760px;
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-mid);
}
.metis-inline-accent {
  color: rgba(236, 204, 128, 0.98);
}
.metis-build-toolbar {
  margin-top: 28px;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px 24px;
  padding: 20px 0 24px;
  border-top: 1px solid rgba(200,210,225,0.09);
  border-bottom: 1px solid rgba(200,210,225,0.09);
}
.metis-build-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.metis-build-stat {
  display: inline-flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid rgba(200,210,225,0.1);
  background: rgba(10,14,28,0.38);
  color: var(--text-mid);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
.metis-star-controls-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.metis-star-btn {
  border: 1px solid rgba(200, 210, 225, 0.16);
  background: rgba(17, 24, 46, 0.56);
  color: var(--text-bright);
  border-radius: 999px;
  padding: 8px 13px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  cursor: pointer;
  transition: all 0.25s ease;
}
.metis-star-btn:hover:not(:disabled) {
  border-color: rgba(196,149,58,0.34);
  color: var(--gold-bright);
}
.metis-star-btn.danger:hover:not(:disabled) {
  border-color: rgba(255,120,120,0.45);
  color: rgba(255,180,180,0.95);
}
.metis-star-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.metis-build-note {
  margin-top: 14px;
  padding: 13px 16px;
  border-radius: 16px;
  border: 1px solid rgba(200,210,225,0.08);
  background: rgba(10,14,28,0.46);
  font-size: 13px;
  line-height: 1.65;
  color: var(--text-mid);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
.metis-build-note.accent {
  border-color: rgba(196,149,58,0.18);
  color: rgba(236,221,188,0.96);
}
.metis-build-note.error {
  border-color: rgba(255,120,120,0.24);
  color: rgba(255,214,214,0.98);
}
.metis-star-editor {
  margin-top: 18px;
  padding: 22px 0 0;
  border-top: 1px solid rgba(200,210,225,0.08);
}
.metis-star-editor-copy {
  margin-top: 10px;
  max-width: 780px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-mid);
}
.metis-star-editor-grid {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.metis-star-field {
  display: grid;
  gap: 6px;
}
.metis-star-input {
  width: 100%;
  border: 1px solid rgba(200, 210, 225, 0.12);
  background: rgba(15, 22, 40, 0.78);
  color: var(--text-bright);
  border-radius: 12px;
  padding: 10px 12px;
  font-size: 12px;
  outline: none;
}
.metis-star-input:focus {
  border-color: rgba(196,149,58,0.4);
  box-shadow: 0 0 0 1px rgba(196,149,58,0.16);
}
.metis-build-studio-shell {
  position: relative;
  margin-top: 26px;
  z-index: 2;
}

/* CARDS */
.metis-cards-section {
  position: relative; z-index: 10;
  padding: 0 48px 120px;
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 20px; max-width: 1400px; margin: 0 auto;
}
.metis-card {
  background: rgba(12, 18, 35, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(200, 210, 225, 0.04);
  border-radius: 4px; padding: 44px 36px;
  min-height: 280px; display: flex;
  flex-direction: column; transition: all 0.6s ease;
  position: relative; overflow: hidden;
  opacity: 0; transform: translateY(40px);
}
.metis-card.card-visible {
  opacity: 1; transform: translateY(0);
  transition: opacity 0.9s cubic-bezier(0.16,1,0.3,1), transform 0.9s cubic-bezier(0.16,1,0.3,1), border-color 0.6s ease, box-shadow 0.6s ease;
}
.metis-card::before {
  content: ''; position: absolute;
  top: 0; left: 0; right: 0; height: 1px;
  background: linear-gradient(90deg, transparent, rgba(196,149,58,0), transparent);
  transition: background 0.8s ease;
}
.metis-card:hover::before { background: linear-gradient(90deg, transparent, rgba(196,149,58,0.3), transparent); }
.metis-card:hover { border-color: rgba(196,149,58,0.1); transform: translateY(-2px); }
.metis-card-label {
  font-size: 11px; letter-spacing: 2px;
  text-transform: uppercase; color: var(--gold-dim);
  font-weight: 500; margin-bottom: 8px;
}
.metis-card-title {
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 400; font-size: 22px;
  color: var(--text-bright); line-height: 1.3; margin-bottom: 20px;
}
.metis-card-desc {
  font-size: 13px; line-height: 1.7;
  color: var(--text-dim); font-weight: 300; margin-top: auto;
}

/* CONCEPT CARD */
.metis-concept-card {
  position: fixed; z-index: 200;
  background: rgba(8,12,24,0.92);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(196,149,58,0.12);
  border-radius: 14px; padding: 28px 30px;
  max-width: 280px; pointer-events: all;
  opacity: 0; transform: translateY(8px) scale(0.97);
  transition: all 0.5s cubic-bezier(0.16,1,0.3,1);
  display: none;
}
.metis-concept-card.active { display: block; opacity: 1; transform: translateY(0) scale(1); }
.metis-c-label { font-size: 10px; letter-spacing: 2.5px; text-transform: uppercase; color: var(--gold); margin-bottom: 10px; }
.metis-c-title { font-family: 'Space Grotesk', sans-serif; font-size: 20px; font-weight: 400; color: var(--text-bright); margin-bottom: 12px; }
.metis-c-desc { font-size: 12px; line-height: 1.75; color: var(--text-dim); font-weight: 300; }
.metis-c-close {
  position: absolute; top: 14px; right: 16px;
  width: 20px; height: 20px; cursor: pointer;
  opacity: 0.3; transition: opacity 0.3s;
  background: none; border: none;
  color: var(--text-mid); font-size: 16px; font-family: 'Inter';
}
.metis-c-close:hover { opacity: 0.8; }

/* CHAT BUBBLE */
.metis-chat-bubble {
  position: fixed; bottom: 32px; right: 32px;
  z-index: 150; width: 48px; height: 48px;
  border-radius: 50%;
  background: radial-gradient(circle at 40% 40%, rgba(40,52,90,0.7), rgba(12,18,35,0.85));
  border: 1px solid rgba(196,149,58,0.1);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: all 0.5s cubic-bezier(0.16,1,0.3,1);
  box-shadow: 0 0 20px rgba(196,149,58,0.04), inset 0 0 12px rgba(196,149,58,0.03);
}
.metis-chat-bubble:hover {
  border-color: rgba(196,149,58,0.25); transform: scale(1.08);
  box-shadow: 0 0 30px rgba(196,149,58,0.1), inset 0 0 16px rgba(196,149,58,0.06);
}
.metis-celestial-star-svg {
  width: 22px; height: 22px;
  animation: metis-celestialPulse 3s ease-in-out infinite, metis-celestialSpin 20s linear infinite;
  filter: drop-shadow(0 0 4px rgba(196,149,58,0.4)) drop-shadow(0 0 8px rgba(196,149,58,0.15));
}

@keyframes metis-celestialPulse {
  0%, 100% { opacity: 0.75; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.12); }
}
@keyframes metis-celestialSpin { from { rotate: 0deg; } to { rotate: 360deg; } }
@keyframes metis-fadeUp { to { opacity: 1; transform: translateY(0); } }

@media (max-width: 1100px) {
  .metis-star-editor-grid,
  .metis-cards-section {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .metis-nav {
    padding: 22px 18px;
  }

  .metis-nav-left {
    gap: 22px;
  }

  .metis-hero-overlay {
    padding: 0 20px 48px;
  }

  .metis-hero-copy,
  .metis-field-guide,
  .metis-section-copy {
    max-width: none;
  }

  .metis-hero-actions {
    flex-direction: column;
    align-items: flex-start;
    gap: 14px;
  }

  .metis-toast {
    top: 78px;
  }

  .metis-build-section,
  .metis-cards-section {
    padding-left: 20px;
    padding-right: 20px;
  }

  .metis-build-toolbar {
    flex-direction: column;
  }

  .metis-star-editor-grid {
    grid-template-columns: 1fr;
  }

  .metis-chat-bubble {
    bottom: 20px;
    right: 20px;
  }
}

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(200,210,225,0.08); border-radius: 2px; }
`;
