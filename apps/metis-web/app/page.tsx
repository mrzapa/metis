"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import type { LandingStarfieldFrame, LandingWebglStar } from "@/components/home/landing-starfield-webgl.types";

const LandingStarfieldWebgl = dynamic(
  () =>
    import("@/components/home/landing-starfield-webgl").then(
      (m) => ({ default: m.LandingStarfieldWebgl }),
    ),
  { ssr: false, loading: () => null },
);
import { StarDetailsPanel } from "@/components/constellation/star-observatory-dialog";
import { useConstellationStars } from "@/hooks/use-constellation-stars";
import { deleteIndex, fetchIndexes, previewLearningRoute } from "@/lib/api";
import {
  buildBrainPlacementIntent,
  buildFacultyAnchoredPlacement,
  getConstellationPlacementDecision,
} from "@/lib/constellation-brain";
import {
  DEFAULT_BRAIN_GRAPH_HIGHLIGHT_TTL_MS,
  subscribeBrainGraphRagActivity,
  type BrainGraphRagActivity,
} from "@/lib/brain-graph-rag-activity";
import {
  ADD_CANDIDATE_HIT_RADIUS_PX,
  buildOutwardPlacement,
  clampBackgroundZoomFactor,
  CONSTELLATION_FACULTIES,
  CORE_CENTER_X,
  CORE_CENTER_Y,
  CORE_EXCLUSION_RADIUS,
  getBackgroundCameraScale,
  getBackgroundViewportWorldBounds,
  getConstellationCameraScale,
  getFacultyColor,
  getAutoStarFaculty,
  getInfluenceColors,
  getPreviewConnectionNodes,
  isAutonomousStar,
  inferConstellationFaculty,
  isAddableBackgroundStar,
  MAX_BACKGROUND_ZOOM_FACTOR,
  MIN_BACKGROUND_ZOOM_FACTOR,
  MOBILE_ADD_CANDIDATE_HIT_RADIUS_PX,
  mixConstellationColors,
  projectBackgroundStar,
  projectConstellationPoint,
  screenToConstellationPoint,
  screenToWorldPoint,
  type ConstellationFacultyMetadata,
  type ConstellationFieldStar,
  type ConstellationNodePoint,
  type Point,
  type BackgroundCameraState,
} from "@/lib/constellation-home";
import {
  buildProjectedUserStarHitTarget,
  buildStarFocusCamera,
  cloneCameraSnapshot,
  createUserStarVisualProfile,
  findClosestProjectedTarget,
  isCameraSettled,
  type ConstellationCameraSnapshot,
  type ProjectedUserStarHitTarget,
  STAR_FOCUS_CLOSE_LOCK_MS,
  STAR_FOCUS_SETTLE_TIMEOUT_MS,
} from "@/lib/constellation-focus";
import { generateStellarProfile, type StellarProfile } from "@/lib/landing-stars";
import { buildLandingStarRenderPlan } from "@/lib/landing-stars/landing-star-lod";
import {
  buildLandingStarSpatialHash,
  findClosestLandingStarHitTarget,
} from "@/lib/landing-stars/landing-star-spatial-index";
import {
  buildCanvasFont,
  measureSingleLineTextWidth,
  quantizeFontSize,
} from "@/lib/pretext-labels";
import type {
  IndexBuildResult,
  IndexSummary,
  LearningRoutePreviewRequest,
} from "@/lib/api";
import type {
  LandingStarHitTarget,
  LandingStarSpatialHash,
} from "@/lib/landing-stars/landing-star-types";
import type {
  LearningRoute,
  LearningRouteStep,
  LearningRouteStepStatus,
  UserStar,
} from "@/lib/constellation-types";

/* ────────────────────────────── constants ────────────────────────────── */

const FACULTY_CONCEPTS = CONSTELLATION_FACULTIES.map((faculty, index) => ({
  faculty,
  label: `Faculty ${String(index + 1).padStart(2, "0")}`,
  title: faculty.label,
  desc: faculty.description,
}));
const BACKGROUND_BUTTON_ZOOM_STEP = 1.8;
const BACKGROUND_TILE_PADDING_PX = 220;
const BACKGROUND_TILE_SIZE = 960;
const MAX_CACHED_WORLD_TILES = 4096;
const WORLD_STAR_COUNT_BY_LAYER = [4, 7, 10] as const;
const WORLD_STAR_REVEAL_STEPS = [1, 1.35, 1.8, 2.4, 3.2, 4.3, 5.8, 7.8, 10.5, 14.2, 19.2, 26, 35, 47, 64, 86, 116, 156, 200] as const;
const HOVER_EXPAND_DELAY_MS = 600;
const DRAG_DISTANCE_PX = 6;
const ZOOM_UI_RESTORE_DELAY_MS = 240;
const STARFIELD_CAMERA_REBUILD_EPSILON = 0.45;
const USER_STAR_LINK_MAX_DISTANCE = 0.34;
const USER_STAR_FADE_IN_DURATION_MS = 850;
const USER_STAR_EDGE_BREATH_PERIOD_MS = 6200;
const USER_STAR_EDGE_BREATH_AMPLITUDE = 0.14;
const NODE_LABEL_FONT_FAMILY = '"Space Grotesk", sans-serif';
const NODE_LABEL_FONT_WEIGHT = "400";
const NODE_LABEL_PADDING_X = 12;
const NODE_LABEL_PADDING_Y = 8;
const NODE_LABEL_EDGE_MARGIN_PX = 14;
const NODE_LABEL_CENTER_OFFSET_RATIO = 0.28;

type CanvasTool = "select" | "grab";
type StarFocusPhase = "idle" | "focusing" | "details-open" | "returning";

interface CanvasBounds {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

/* ────────────────────────────── helpers ──────────────────────────────── */

interface VisibleStarData extends ConstellationFieldStar {
  isAddable: boolean;
}

type StarData = VisibleStarData;
type FacultyConcept = typeof FACULTY_CONCEPTS[number];

interface NodeData extends ConstellationNodePoint {
  anchorX: number;
  anchorY: number;
  baseSize: number;
  brightness: number; targetBrightness: number;
  concept: FacultyConcept;
  awakenDelay: number; parallax: number;
  hoverBoost: number; targetHoverBoost: number;
  _labelBottom: number;
  _labelLeft: number;
  _labelRight: number;
  _labelTop: number;
  _sx: number; _sy: number;
}

interface DustData {
  x: number; y: number; vx: number; vy: number;
  size: number; opacity: number;
}

interface WorldStarData {
  id: string;
  worldX: number;
  worldY: number;
  layer: number;
  baseSize: number;
  brightness: number;
  twinkle: boolean;
  twinkleSpeed: number;
  twinklePhase: number;
  parallaxFactor: number;
  hasDiffraction: boolean;
  revealZoomFactor: number;
}

interface HomeRagPulseState {
  startedAt: number;
  expiresAt: number;
  ttlMs: number;
  manifestPaths: Set<string>;
  facultyIds: Set<string>;
  starIds: Set<string>;
}

interface HomeToastState {
  actionLabel?: string;
  dismissMs?: number | null;
  id: number;
  message: string;
  onAction?: (() => void) | null;
  tone: "default" | "error";
}

interface LandingWorldStarRenderState extends LandingStarHitTarget {
  addable: boolean;
  profile: StellarProfile;
}

interface ProjectedUserStarRenderState {
  attachmentCount: number;
  dragging: boolean;
  fadeIn: number;
  influenceColors: ReturnType<typeof buildStarInfluenceColors>;
  mixed: [number, number, number];
  profile: ReturnType<typeof createUserStarVisualProfile>;
  ringCount: number;
  selected: boolean;
  star: UserStar;
  stellarProfile: StellarProfile;
  target: ProjectedUserStarHitTarget;
}

interface ChatLaunchPayload {
  manifestPath: string;
  label: string;
  selectedMode?: string;
  draft?: string;
}

interface LearningRouteOverlayStop {
  current: boolean;
  done: boolean;
  id: string;
  title: string;
  unavailable: boolean;
  x: number;
  y: number;
}

function nextDeterministicSeed(seed: number): number {
  return (Math.imul(seed, 1664525) + 1013904223) >>> 0;
}

function getWorldRevealBucket(zoomFactor: number): number {
  let bucket = 0;

  while (
    bucket < WORLD_STAR_REVEAL_STEPS.length
    && zoomFactor + 1e-6 >= WORLD_STAR_REVEAL_STEPS[bucket]
  ) {
    bucket += 1;
  }

  return bucket;
}

function createTileSeed(tileX: number, tileY: number, layer: number, index: number): number {
  let seed = 2166136261;

  seed ^= Math.imul(tileX, 374761393);
  seed = Math.imul(seed, 668265263) >>> 0;
  seed ^= Math.imul(tileY, 1442695041);
  seed = Math.imul(seed, 2246822519) >>> 0;
  seed ^= Math.imul(layer + 1, 3266489917);
  seed = Math.imul(seed, 668265263) >>> 0;
  seed ^= Math.imul(index + 1, 1597334677);
  seed = Math.imul(seed, 2246822519) >>> 0;

  return seed >>> 0;
}

function clampToRange(value: number, min: number, max: number): number {
  if (value < min) {
    return min;
  }
  if (value > max) {
    return max;
  }
  return value;
}

function sampleDeterministicRatio(seed: number): [number, number] {
  const nextSeed = nextDeterministicSeed(seed);
  return [nextSeed, nextSeed / 4294967296];
}

function formatBackgroundZoom(zoomFactor: number): string {
  if (zoomFactor >= 10) {
    return `${Math.round(zoomFactor)}x`;
  }

  return `${zoomFactor.toFixed(1)}x`;
}

function buildStarInfluenceColors(star: Pick<UserStar, "primaryDomainId" | "relatedDomainIds">) {
  return getInfluenceColors(star.primaryDomainId, star.relatedDomainIds);
}

function getWorldTileStars(
  tileCache: Map<string, WorldStarData[]>,
  layer: number,
  tileX: number,
  tileY: number,
): WorldStarData[] {
  const cacheKey = `${layer}:${tileX}:${tileY}`;
  const cached = tileCache.get(cacheKey);
  if (cached) {
    tileCache.delete(cacheKey);
    tileCache.set(cacheKey, cached);
    return cached;
  }

  const starCount = WORLD_STAR_COUNT_BY_LAYER[layer] ?? WORLD_STAR_COUNT_BY_LAYER[WORLD_STAR_COUNT_BY_LAYER.length - 1];
  const tileStars: WorldStarData[] = [];

  for (let index = 0; index < starCount; index += 1) {
    let seed = createTileSeed(tileX, tileY, layer, index);
    let value: number;

    [seed, value] = sampleDeterministicRatio(seed);
    const offsetX = value;
    [seed, value] = sampleDeterministicRatio(seed);
    const offsetY = value;
    [seed, value] = sampleDeterministicRatio(seed);
    const brightness = 0.12 + value * (layer === 0 ? 0.55 : layer === 1 ? 0.42 : 0.28);
    [seed, value] = sampleDeterministicRatio(seed);
    const baseSize = layer === 0 ? 1.12 + value * 1.55 : layer === 1 ? 0.72 + value * 0.96 : 0.28 + value * 0.58;
    [seed, value] = sampleDeterministicRatio(seed);
    const revealZoomFactor = WORLD_STAR_REVEAL_STEPS[Math.floor(value * WORLD_STAR_REVEAL_STEPS.length)] ?? 1;
    [seed, value] = sampleDeterministicRatio(seed);
    const twinkle = value > (layer === 0 ? 0.58 : 0.76);
    [seed, value] = sampleDeterministicRatio(seed);
    const twinkleSpeed = 0.0018 + value * 0.0065;
    [seed, value] = sampleDeterministicRatio(seed);
    const twinklePhase = value * Math.PI * 2;
    [seed, value] = sampleDeterministicRatio(seed);
    const hasDiffraction = layer <= 1 && baseSize > (layer === 0 ? 1.75 : 1.25) && value > 0.34;

    tileStars.push({
      id: `field-star-${layer}-${tileX}-${tileY}-${index}`,
      worldX: tileX * BACKGROUND_TILE_SIZE + offsetX * BACKGROUND_TILE_SIZE,
      worldY: tileY * BACKGROUND_TILE_SIZE + offsetY * BACKGROUND_TILE_SIZE,
      layer,
      baseSize,
      brightness,
      twinkle,
      twinkleSpeed,
      twinklePhase,
      parallaxFactor: layer === 0 ? 0.026 : layer === 1 ? 0.013 : 0.006,
      hasDiffraction,
      revealZoomFactor,
    });
  }

  tileCache.set(cacheKey, tileStars);
  if (tileCache.size > MAX_CACHED_WORLD_TILES) {
    const oldestCacheKey = tileCache.keys().next().value;
    if (oldestCacheKey) {
      tileCache.delete(oldestCacheKey);
    }
  }
  return tileStars;
}

function getZoomResponsiveNodeScale(zoomFactor: number): number {
  return Math.max(0.46, Math.pow(getConstellationCameraScale(zoomFactor), 0.62));
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
    brain_pass: result.brain_pass,
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

function uniqueManifestPaths(values: Array<string | undefined | null>): string[] {
  const seen = new Set<string>();
  const result: string[] = [];

  values.forEach((value) => {
    const trimmed = typeof value === "string" ? value.trim() : "";
    if (!trimmed || seen.has(trimmed)) {
      return;
    }
    seen.add(trimmed);
    result.push(trimmed);
  });

  return result;
}

function getStarManifestPaths(star: UserStar): string[] {
  return uniqueManifestPaths([
    ...(star.linkedManifestPaths ?? []),
    star.activeManifestPath,
    star.linkedManifestPath,
  ]);
}

function convertLearningRoutePreviewToRoute(
  preview: Awaited<ReturnType<typeof previewLearningRoute>>,
): LearningRoute {
  return {
    id: preview.route_id,
    title: preview.title,
    originStarId: preview.origin_star_id,
    createdAt: preview.created_at,
    updatedAt: preview.updated_at,
    steps: preview.steps.map((step) => ({
      id: step.id,
      kind: step.kind,
      title: step.title,
      objective: step.objective,
      rationale: step.rationale,
      manifestPath: step.manifest_path,
      sourceStarId: step.source_star_id ?? undefined,
      tutorPrompt: step.tutor_prompt,
      estimatedMinutes: step.estimated_minutes,
      status: "todo",
    })),
  };
}

function cloneLearningRoute(route: LearningRoute): LearningRoute {
  return {
    ...route,
    steps: route.steps.map((step) => ({ ...step })),
  };
}

function hasEligibleCourseSource(star: UserStar | null): boolean {
  return star !== null && getStarManifestPaths(star).length > 0;
}

function buildLearningRoutePreviewRequest(
  star: UserStar,
  allStars: readonly UserStar[],
  indexes: readonly IndexSummary[],
): LearningRoutePreviewRequest {
  const connectedStars = (star.connectedUserStarIds ?? [])
    .map((starId) => allStars.find((candidate) => candidate.id === starId) ?? null)
    .filter((candidate): candidate is UserStar => candidate !== null);
  const relevantManifestPathSet = new Set<string>([
    ...getStarManifestPaths(star),
    ...connectedStars.flatMap((connectedStar) => uniqueManifestPaths([connectedStar.activeManifestPath])),
  ]);

  return {
    origin_star: {
      id: star.id,
      label: star.label,
      intent: star.intent,
      notes: star.notes,
      active_manifest_path: star.activeManifestPath,
      linked_manifest_paths: star.linkedManifestPaths ?? [],
      connected_user_star_ids: star.connectedUserStarIds ?? [],
    },
    connected_stars: connectedStars.map((connectedStar) => ({
      id: connectedStar.id,
      label: connectedStar.label,
      intent: connectedStar.intent,
      notes: connectedStar.notes,
      active_manifest_path: connectedStar.activeManifestPath,
      linked_manifest_paths: connectedStar.linkedManifestPaths ?? [],
      connected_user_star_ids: connectedStar.connectedUserStarIds ?? [],
    })),
    indexes: indexes
      .filter((index) => relevantManifestPathSet.has(index.manifest_path))
      .map((index) => ({
        index_id: index.index_id,
        manifest_path: index.manifest_path,
        document_count: index.document_count,
        chunk_count: index.chunk_count,
        created_at: index.created_at,
        embedding_signature: index.embedding_signature,
        brain_pass: index.brain_pass,
      })),
  };
}

function getCurrentLearningRouteStepId(route: LearningRoute | null): string | null {
  if (!route || route.steps.length === 0) {
    return null;
  }
  return route.steps.find((step) => step.status !== "done")?.id ?? route.steps[0]?.id ?? null;
}

function buildLearningRouteWaypoint(origin: Point, stepIndex: number, totalSteps: number): Point {
  const safeTotalSteps = Math.max(1, totalSteps);
  const angle = (-Math.PI / 2.4) + (stepIndex / safeTotalSteps) * Math.PI * 0.92;
  const radius = 0.075 + stepIndex * 0.028;

  return {
    x: clampToRange(origin.x + Math.cos(angle) * radius, 0.08, 0.92),
    y: clampToRange(origin.y + Math.sin(angle) * radius, 0.08, 0.92),
  };
}

function removeDeletedManifestPathsFromStar(
  star: UserStar,
  deletedManifestPaths: ReadonlySet<string>,
): UserStar {
  const nextManifestPaths = getStarManifestPaths(star).filter(
    (manifestPath) => !deletedManifestPaths.has(manifestPath),
  );
  const nextActiveManifestPath =
    star.activeManifestPath && !deletedManifestPaths.has(star.activeManifestPath)
      ? star.activeManifestPath
      : (nextManifestPaths.at(-1) ?? undefined);

  return {
    ...star,
    linkedManifestPaths: nextManifestPaths.length > 0 ? nextManifestPaths : undefined,
    activeManifestPath: nextActiveManifestPath,
    linkedManifestPath: nextManifestPaths.at(-1) ?? undefined,
  };
}

function clearPersistedActiveIndexIfDeleted(deletedManifestPaths: ReadonlySet<string>) {
  try {
    const raw = window.localStorage.getItem("metis_active_index");
    if (!raw) {
      return;
    }
    const parsed = JSON.parse(raw) as { manifest_path?: unknown };
    const manifestPath =
      typeof parsed?.manifest_path === "string" ? parsed.manifest_path : "";
    if (manifestPath && deletedManifestPaths.has(manifestPath)) {
      window.localStorage.removeItem("metis_active_index");
    }
  } catch {
    window.localStorage.removeItem("metis_active_index");
  }
}

function normalizeText(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function getRagManifestPath(source: BrainGraphRagActivity["sources"][number]): string | null {
  const metadata = source.metadata && typeof source.metadata === "object"
    ? source.metadata as Record<string, unknown>
    : null;
  return (
    normalizeText(metadata?.manifest_path)
    ?? normalizeText(metadata?.source_manifest_path)
    ?? normalizeText(metadata?.file_path)
    ?? normalizeText(source.file_path)
  );
}

function getIndexFacultyId(index: IndexSummary): string | null {
  const placement = index.brain_pass?.placement;
  return normalizeText(placement?.faculty_id);
}

function getHomeRagPulseStrength(pulseState: HomeRagPulseState | null, nowMs: number): number {
  if (!pulseState || nowMs >= pulseState.expiresAt) {
    return 0;
  }

  const remainingMs = Math.max(0, pulseState.expiresAt - nowMs);
  const decay = remainingMs / Math.max(1, pulseState.ttlMs);
  const pulse = 0.82 + 0.18 * Math.sin(nowMs / 160);
  return Math.max(0, Math.min(1, decay * pulse));
}

function getStarAttachmentCount(star: UserStar): number {
  return getStarManifestPaths(star).length;
}

function getStarTooltipDescription(
  star: Pick<UserStar, "intent" | "notes">,
  faculty: Pick<ConstellationFacultyMetadata, "description">,
): string {
  if (star.intent && star.intent.trim().length > 0) {
    return star.intent;
  }
  if (star.notes && star.notes.trim().length > 0) {
    return star.notes;
  }
  return faculty.description;
}

function getFacultyById(facultyId?: string): ConstellationFacultyMetadata | null {
  if (!facultyId) {
    return null;
  }
  return CONSTELLATION_FACULTIES.find((faculty) => faculty.id === facultyId) ?? null;
}

function buildIndexStarDraft(index: IndexSummary, placementSeed: number): Omit<UserStar, "id" | "createdAt"> {
  const placement = getConstellationPlacementDecision(index);
  const { x, y } = buildFacultyAnchoredPlacement(placement.facultyId, placementSeed);

  return {
    x,
    y,
    size: 0.95,
    label: index.index_id,
    primaryDomainId: placement.facultyId,
    relatedDomainIds:
      placement.secondaryFacultyIds.length > 0 ? placement.secondaryFacultyIds : undefined,
    stage: "seed",
    intent: buildBrainPlacementIntent(placement.provider),
    notes: placement.rationale || undefined,
    linkedManifestPaths: [index.manifest_path],
    activeManifestPath: index.manifest_path,
    linkedManifestPath: index.manifest_path,
  };
}

function describeIndexedFaculty(index: Pick<IndexSummary | IndexBuildResult, "brain_pass">): string {
  const placement = getConstellationPlacementDecision(index);
  return getFacultyById(placement.facultyId)?.label ?? "Knowledge";
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

function getResolvedStarPoint(
  star: Pick<UserStar, "x" | "y">,
  previewPositions: ReadonlyMap<string, { x: number; y: number }>,
  starId: string,
): Point {
  const previewPosition = previewPositions.get(starId);
  return {
    x: previewPosition?.x ?? star.x,
    y: previewPosition?.y ?? star.y,
  };
}

function getStarFadeProgress(star: Pick<UserStar, "createdAt">, nowMs: number): number {
  return Math.max(0, Math.min(1, (nowMs - star.createdAt) / USER_STAR_FADE_IN_DURATION_MS));
}

function cloneUserStarSnapshot(stars: readonly UserStar[]): UserStar[] {
  return stars.map((star) => ({
    ...star,
    connectedUserStarIds: star.connectedUserStarIds ? [...star.connectedUserStarIds] : undefined,
    learningRoute: star.learningRoute ? cloneLearningRoute(star.learningRoute) : undefined,
    linkedManifestPaths: star.linkedManifestPaths ? [...star.linkedManifestPaths] : undefined,
    relatedDomainIds: star.relatedDomainIds ? [...star.relatedDomainIds] : undefined,
  }));
}

function clampColorChannel(value: number): number {
  return Math.max(0, Math.min(255, Math.round(value)));
}

function applyTintBias(
  color: readonly [number, number, number],
  tintBias: number,
): [number, number, number] {
  const [red, green, blue] = color;

  return [
    clampColorChannel(red + tintBias * 16),
    clampColorChannel(green + tintBias * 6),
    clampColorChannel(blue - tintBias * 14),
  ];
}

function mixRgbColors(
  left: readonly [number, number, number],
  right: readonly [number, number, number],
  amount: number,
): [number, number, number] {
  const clampedAmount = Math.max(0, Math.min(1, amount));

  return [
    clampColorChannel(left[0] + (right[0] - left[0]) * clampedAmount),
    clampColorChannel(left[1] + (right[1] - left[1]) * clampedAmount),
    clampColorChannel(left[2] + (right[2] - left[2]) * clampedAmount),
  ];
}

function getRenderEpochMs(frameTimestampMs: number): number {
  const timeOrigin = typeof performance !== "undefined" ? performance.timeOrigin : Number.NaN;
  return Number.isFinite(timeOrigin) ? timeOrigin + frameTimestampMs : Date.now();
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

function applyNodeLayout(nodes: NodeData[], W: number, H: number, camera: BackgroundCameraState) {
  nodes.forEach((node) => {
    const projected = projectConstellationPoint(
      { x: node.anchorX, y: node.anchorY },
      W,
      H,
      camera,
    );
    node.x = projected.x;
    node.y = projected.y;
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
    replaceUserStars,
    updateUserStarById,
    starLimit,
  } = useConstellationStars();
  const [addMessage, setAddMessage] = useState<string | null>(null);
  const [selectedUserStarId, setSelectedUserStarId] = useState<string | null>(null);
  const [starDetailsOpen, setStarDetailsOpen] = useState(false);
  const [starDetailsMode, setStarDetailsMode] = useState<"new" | "existing">("new");
  const [pendingDetailStar, setPendingDetailStar] = useState<UserStar | null>(null);
  const [starDetailCloseLockedUntil, setStarDetailCloseLockedUntil] = useState(0);
  const [starFocusPhase, setStarFocusPhase] = useState<StarFocusPhase>("idle");
  const [availableIndexes, setAvailableIndexes] = useState<IndexSummary[]>([]);
  const [indexesLoading, setIndexesLoading] = useState(true);
  const [indexLoadError, setIndexLoadError] = useState<string | null>(null);
  const [hoveredAddCandidateId, setHoveredAddCandidateId] = useState<string | null>(null);
  const [hoveredUserStarId, setHoveredUserStarId] = useState<string | null>(null);
  const [dragMessage, setDragMessage] = useState<string | null>(null);
  const [toastState, setToastState] = useState<HomeToastState | null>(null);
  const [activeCanvasTool, setActiveCanvasTool] = useState<CanvasTool>("select");
  const [backgroundZoomFactor, setBackgroundZoomFactor] = useState(1);
  const [isCanvasPanning, setIsCanvasPanning] = useState(false);
  const [zoomInteracting, setZoomInteracting] = useState(false);
  const [learningRoutePreview, setLearningRoutePreview] = useState<LearningRoute | null>(null);
  const [learningRoutePreviewStarId, setLearningRoutePreviewStarId] = useState<string | null>(null);
  const [learningRouteLoading, setLearningRouteLoading] = useState(false);
  const [learningRouteError, setLearningRouteError] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const starTooltipCardRef = useRef<HTMLDivElement>(null);
  const starTooltipDomainRef = useRef<HTMLDivElement>(null);
  const starTooltipTitleRef = useRef<HTMLDivElement>(null);
  const starTooltipDescRef = useRef<HTMLDivElement>(null);
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
  const canvasBoundsRef = useRef<CanvasBounds>({
    left: 0,
    top: 0,
    right: 0,
    bottom: 0,
    width: 0,
    height: 0,
  });
  const backgroundCameraOriginRef = useRef<Point>({ x: 0, y: 0 });
  const backgroundCameraTargetOriginRef = useRef<Point>({ x: 0, y: 0 });
  const backgroundZoomRef = useRef(1);
  const backgroundZoomTargetRef = useRef(1);
  const starFocusPhaseRef = useRef<StarFocusPhase>("idle");
  const starFocusSessionRef = useRef<{
    starId: string | null;
    focusTarget: ConstellationCameraSnapshot | null;
    snapshot: ConstellationCameraSnapshot | null;
    startedAt: number;
  }>({
    starId: null,
    focusTarget: null,
    snapshot: null,
    startedAt: 0,
  });
  const projectedUserStarTargetsRef = useRef<ProjectedUserStarHitTarget[]>([]);
  const visibleStarsRef = useRef<StarData[]>([]);
  const landingStarProfileCacheRef = useRef<Map<string, StellarProfile>>(new Map());
  const hasSessionIndexedContentRef = useRef(false);
  const landingStarfieldFrameRef = useRef<LandingStarfieldFrame>({
    height: 0,
    revision: 0,
    stars: [],
    width: 0,
  });
  const optimisticIndexKeysRef = useRef<Set<string>>(new Set());
  const starTooltipHideTimeoutRef = useRef<number | null>(null);
  const toastDismissTimeoutRef = useRef<number | null>(null);
  const zoomInteractionTimeoutRef = useRef<number | null>(null);
  const dragPreviewPositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const ragPulseStateRef = useRef<HomeRagPulseState | null>(null);
  const starfieldRevisionRef = useRef(0);
  const learningRouteRequestIdRef = useRef(0);
  const dragStateRef = useRef<{
    pointerId: number;
    starId: string;
    startClientX: number;
    startClientY: number;
    moved: boolean;
  } | null>(null);
  const panStateRef = useRef<{
    pointerId: number;
    startClientX: number;
    startClientY: number;
    startOrigin: Point;
    zoomFactor: number;
    moved: boolean;
  } | null>(null);

  useEffect(() => {
    userStarsRef.current = userStars;
    starfieldRevisionRef.current += 1;
  }, [userStars]);

  useEffect(() => {
    availableIndexesRef.current = availableIndexes;
    starfieldRevisionRef.current += 1;
  }, [availableIndexes]);

  useEffect(() => {
    selectedUserStarIdRef.current = selectedUserStarId;
  }, [selectedUserStarId]);

  const clearToast = useCallback(() => {
    if (toastDismissTimeoutRef.current !== null) {
      window.clearTimeout(toastDismissTimeoutRef.current);
      toastDismissTimeoutRef.current = null;
    }

    setToastState(null);
  }, []);

  const showToast = useCallback((
    options: Omit<HomeToastState, "id">,
  ) => {
    if (toastDismissTimeoutRef.current !== null) {
      window.clearTimeout(toastDismissTimeoutRef.current);
      toastDismissTimeoutRef.current = null;
    }

    const nextToast: HomeToastState = {
      dismissMs: 2400,
      onAction: null,
      ...options,
      id: Date.now(),
    };

    setToastState(nextToast);

    if (nextToast.dismissMs !== null) {
      toastDismissTimeoutRef.current = window.setTimeout(() => {
        setToastState((current) => (current?.id === nextToast.id ? null : current));
        toastDismissTimeoutRef.current = null;
      }, nextToast.dismissMs);
    }
  }, []);

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
    if (starTooltipHideTimeoutRef.current !== null) {
      window.clearTimeout(starTooltipHideTimeoutRef.current);
    }
    if (toastDismissTimeoutRef.current !== null) {
      window.clearTimeout(toastDismissTimeoutRef.current);
    }
    if (zoomInteractionTimeoutRef.current !== null) {
      window.clearTimeout(zoomInteractionTimeoutRef.current);
    }
  }, []);

  const selectedUserStar = useMemo(
    () => userStars.find((star) => star.id === selectedUserStarId) ?? null,
    [selectedUserStarId, userStars],
  );
  const detailsStar = selectedUserStar ?? pendingDetailStar;
  const canvasInteractionsLocked = starFocusPhase !== "idle";
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
  const removeStarWithUndo = useCallback(async (
    starId: string,
    options?: {
      afterRemove?: () => void;
      removedMessage?: string;
      restoredMessage?: string;
    },
  ) => {
    const snapshot = cloneUserStarSnapshot(userStarsRef.current);
    const removedStar = snapshot.find((star) => star.id === starId) ?? null;
    if (!removedStar) {
      return false;
    }

    await removeUserStarById(starId);
    options?.afterRemove?.();
    setAddMessage(null);
    setDragMessage(null);

    const removedLabel = removedStar.label ?? "Star";
    showToast({
      actionLabel: "Undo",
      dismissMs: 4200,
      message: options?.removedMessage ?? `${removedLabel} removed from the constellation.`,
      onAction: () => {
        void (async () => {
          try {
            await replaceUserStars(snapshot);
            showToast({
              dismissMs: 2400,
              message: options?.restoredMessage ?? `${removedLabel} restored to the constellation.`,
              tone: "default",
            });
          } catch (error) {
            console.error("Failed to restore constellation stars", error);
            showToast({
              dismissMs: 4200,
              message: "Unable to restore the removed star right now.",
              tone: "error",
            });
          }
        })();
      },
      tone: "default",
    });

    return true;
  }, [removeUserStarById, replaceUserStars, showToast]);
  const starCountLabel = useMemo(
    () => (starLimit === null ? `${userStars.length} added stars` : `${userStars.length}/${starLimit} added stars`),
    [starLimit, userStars.length],
  );
  const detectedSourceCountLabel = useMemo(
    () => `${getCountLabel(availableIndexes.length, "indexed source")} detected`,
    [availableIndexes.length],
  );
  const readyToMapCountLabel = useMemo(
    () => `${getCountLabel(unmappedIndexes.length, "source")} ready to map`,
    [unmappedIndexes.length],
  );
  const attachmentsCountLabel = useMemo(
    () => `${getCountLabel(attachmentCount, "attachment")} in orbit`,
    [attachmentCount],
  );
  const fieldGuideMessage = useMemo(() => {
    if (activeCanvasTool === "grab") {
      if (isCanvasPanning) {
        return "Panning constellation. Release to stop, then switch back to Select to claim or move stars.";
      }

      return "Hand tool active. Drag the constellation to pan, then switch back to Select to claim, inspect, or reposition stars.";
    }

    if (dragMessage) {
      return dragMessage;
    }

    if (starLimit !== null && userStars.length >= starLimit) {
      return "Constellation at capacity. Remove a star or reset the orbit to pull in another.";
    }

    if (hoveredAddCandidateId) {
      return "Field star acquired. Click once to claim it, then name it and attach sources.";
    }

    if (selectedUserStar && selectedStarFaculty) {
      if (selectedStarAttachmentCount > 0) {
        return `${selectedUserStar.label ?? "Selected star"} currently leans into ${selectedStarFaculty.label}. Open its details to inspect attached sources or launch grounded chat.`;
      }
      return `${selectedUserStar.label ?? "Selected star"} is orbiting ${selectedStarFaculty.label}. Drag it toward another faculty or open its details to feed it.`;
    }

    if (!indexesLoading && unmappedIndexes.length > 0) {
      return `${getCountLabel(unmappedIndexes.length, "indexed source")} ${unmappedIndexes.length === 1 ? "is" : "are"} ready to file into the constellation from the control rail below.`;
    }

    return "Follow the faculty ring: claim a field star, drag it toward the faculty it should strengthen, and let its attached sources deepen it.";
  }, [activeCanvasTool, dragMessage, hoveredAddCandidateId, indexesLoading, isCanvasPanning, selectedStarAttachmentCount, selectedStarFaculty, selectedUserStar, starLimit, unmappedIndexes.length, userStars.length]);
  const selectedStarSummary = useMemo(() => {
    if (!selectedUserStar || !selectedStarFaculty) {
      return "No star selected. Click a claimed star to open its details, or drag one to reassign its faculty.";
    }
    return `${selectedUserStar.label ?? "Selected star"} is aligned with ${selectedStarFaculty.label} and holds ${getCountLabel(selectedStarAttachmentCount, "attached source")}.`;
  }, [selectedStarAttachmentCount, selectedStarFaculty, selectedUserStar]);
  const selectedStarActiveIndex = useMemo(() => {
    if (!selectedUserStar?.activeManifestPath) return null;
    return availableIndexes.find((idx) => idx.manifest_path === selectedUserStar.activeManifestPath) ?? null;
  }, [availableIndexes, selectedUserStar]);
  const activeLearningRoutePreview = useMemo(() => {
    if (!detailsStar || learningRoutePreviewStarId !== detailsStar.id) {
      return null;
    }
    return learningRoutePreview;
  }, [detailsStar, learningRoutePreview, learningRoutePreviewStarId]);
  const displayedLearningRoute = activeLearningRoutePreview ?? detailsStar?.learningRoute ?? null;
  const displayedLearningRouteUnavailableManifestPaths = useMemo(() => (
    new Set(
      (displayedLearningRoute?.steps ?? [])
        .map((step) => step.manifestPath)
        .filter((manifestPath) => !availableIndexes.some((index) => index.manifest_path === manifestPath)),
    )
  ), [availableIndexes, displayedLearningRoute]);
  const learningRouteOverlay = useMemo(() => {
    if (!starDetailsOpen || !detailsStar || !displayedLearningRoute) {
      return null;
    }

    const viewportWidth = canvasBoundsRef.current.width || window.innerWidth;
    const viewportHeight = canvasBoundsRef.current.height || window.innerHeight;
    if (viewportWidth <= 0 || viewportHeight <= 0) {
      return null;
    }

    const backgroundCamera: BackgroundCameraState = {
      x: backgroundCameraOriginRef.current.x,
      y: backgroundCameraOriginRef.current.y,
      zoomFactor: backgroundZoomRef.current,
    };
    const previewPositions = dragPreviewPositionsRef.current;
    const connectedStarIds = new Set(detailsStar.connectedUserStarIds ?? []);
    const originPoint = getResolvedStarPoint(detailsStar, previewPositions, detailsStar.id);
    const currentStepId = getCurrentLearningRouteStepId(displayedLearningRoute);
    const origin = projectConstellationPoint(originPoint, viewportWidth, viewportHeight, backgroundCamera);
    const stops: LearningRouteOverlayStop[] = displayedLearningRoute.steps.map((step, index) => {
      const connectedStar = step.sourceStarId && connectedStarIds.has(step.sourceStarId)
        ? userStars.find((candidate) =>
          candidate.id === step.sourceStarId
          && candidate.activeManifestPath === step.manifestPath,
        ) ?? null
        : null;
      const waypoint = connectedStar
        ? getResolvedStarPoint(connectedStar, previewPositions, connectedStar.id)
        : buildLearningRouteWaypoint(originPoint, index, displayedLearningRoute.steps.length);
      const projected = projectConstellationPoint(waypoint, viewportWidth, viewportHeight, backgroundCamera);

      return {
        current: currentStepId === step.id,
        done: step.status === "done",
        id: step.id,
        title: step.title,
        unavailable: displayedLearningRouteUnavailableManifestPaths.has(step.manifestPath),
        x: projected.x,
        y: projected.y,
      };
    });

    return { origin, stops };
  }, [
    backgroundZoomFactor,
    detailsStar,
    displayedLearningRoute,
    displayedLearningRouteUnavailableManifestPaths,
    starDetailsOpen,
    userStars,
  ]);

  const clearLearningRoutePreview = useCallback(() => {
    learningRouteRequestIdRef.current += 1;
    setLearningRoutePreview(null);
    setLearningRoutePreviewStarId(null);
    setLearningRouteLoading(false);
    setLearningRouteError(null);
  }, []);
  const addMessageTone = useMemo(() => {
    if (!addMessage) {
      return "accent";
    }
    return /unable|failed|error|limit/i.test(addMessage) ? "error" : "accent";
  }, [addMessage]);
  const buildNoteTone = indexLoadError ? "error" : addMessage ? addMessageTone : "accent";
  const buildNoteMessage = indexLoadError ?? addMessage ?? fieldGuideMessage;
  const backgroundZoomLabel = useMemo(
    () => formatBackgroundZoom(backgroundZoomFactor),
    [backgroundZoomFactor],
  );

  const closeConcept = useCallback(() => {
    activeNodeRef.current = -1;
  }, []);

  const closeStarTooltip = useCallback(() => {
    if (starTooltipHideTimeoutRef.current !== null) {
      window.clearTimeout(starTooltipHideTimeoutRef.current);
      starTooltipHideTimeoutRef.current = null;
    }

    setHoveredUserStarId((current) => (current === null ? current : null));
    const card = starTooltipCardRef.current;
    if (card) {
      card.classList.remove("active");
      starTooltipHideTimeoutRef.current = window.setTimeout(() => {
        card.style.display = "none";
        starTooltipHideTimeoutRef.current = null;
      }, 220);
    }
  }, []);

  const clearConstellationHoverState = useCallback(() => {
    hoveredAddCandidateRef.current = null;
    armedAddCandidateIdRef.current = null;
    hoveredNodeRef.current = -1;
    hoverExpandedRef.current = false;
    setHoveredAddCandidateId(null);
    closeStarTooltip();
    closeConcept();
  }, [closeConcept, closeStarTooltip]);

  useEffect(() => {
    const currentDrag = dragStateRef.current;
    if (currentDrag) {
      dragPreviewPositionsRef.current.delete(currentDrag.starId);
      dragStateRef.current = null;
    }

    panStateRef.current = null;
    setIsCanvasPanning(false);
    clearConstellationHoverState();
    setAddMessage(null);
    setDragMessage(null);
  }, [activeCanvasTool, clearConstellationHoverState]);

  const registerZoomInteraction = useCallback(() => {
    setZoomInteracting(true);
    if (zoomInteractionTimeoutRef.current !== null) {
      window.clearTimeout(zoomInteractionTimeoutRef.current);
    }
    zoomInteractionTimeoutRef.current = window.setTimeout(() => {
      setZoomInteracting(false);
      zoomInteractionTimeoutRef.current = null;
    }, ZOOM_UI_RESTORE_DELAY_MS);
  }, []);

  const openChatWithIndex = useCallback(
    ({ manifestPath, label, draft, selectedMode }: ChatLaunchPayload) => {
      window.localStorage.setItem(
        "metis_active_index",
        JSON.stringify({ manifest_path: manifestPath, label }),
      );
      if (draft && draft.trim().length > 0) {
        window.localStorage.setItem("metis_chat_seed_prompt", draft.trim());
      } else {
        window.localStorage.removeItem("metis_chat_seed_prompt");
      }
      if (selectedMode && selectedMode.trim().length > 0) {
        window.localStorage.setItem("metis_chat_seed_mode", selectedMode.trim());
      } else {
        window.localStorage.removeItem("metis_chat_seed_mode");
      }
      router.push("/chat");
    },
    [router],
  );

  const setStarFocusPhaseValue = useCallback((nextPhase: StarFocusPhase) => {
    if (starFocusPhaseRef.current === nextPhase) {
      return;
    }
    starFocusPhaseRef.current = nextPhase;
    setStarFocusPhase(nextPhase);
  }, []);

  const setBackgroundZoomTarget = useCallback((
    nextZoomFactor: number,
    options?: { registerInteraction?: boolean },
  ) => {
    const clampedZoomFactor = clampBackgroundZoomFactor(nextZoomFactor);
    if (options?.registerInteraction !== false) {
      registerZoomInteraction();
    }
    backgroundZoomTargetRef.current = clampedZoomFactor;
    setBackgroundZoomFactor((current) => (
      Math.abs(current - clampedZoomFactor) < 0.001 ? current : clampedZoomFactor
    ));
  }, [registerZoomInteraction]);

  function prefersReducedMotion(): boolean {
    return (
      typeof window !== "undefined"
      && typeof window.matchMedia === "function"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  const jumpToBackgroundCamera = useCallback((snapshot: ConstellationCameraSnapshot) => {
    const nextSnapshot = cloneCameraSnapshot(snapshot);
    backgroundCameraOriginRef.current = { x: nextSnapshot.x, y: nextSnapshot.y };
    backgroundCameraTargetOriginRef.current = { x: nextSnapshot.x, y: nextSnapshot.y };
    backgroundZoomRef.current = nextSnapshot.zoomFactor;
    backgroundZoomTargetRef.current = nextSnapshot.zoomFactor;
    setBackgroundZoomFactor(nextSnapshot.zoomFactor);
  }, []);

  const closeStarDetails = useCallback((options?: {
    clearSelection?: boolean;
    restoreCamera?: "animate" | "jump" | "none";
  }) => {
    const clearSelection = options?.clearSelection ?? false;
    const restoreCamera = options?.restoreCamera ?? "animate";
    const snapshot = starFocusSessionRef.current.snapshot;

    setStarDetailsOpen(false);
    setPendingDetailStar(null);
    setStarDetailCloseLockedUntil(0);
    if (clearSelection) {
      setSelectedUserStarId(null);
    }

    if (!snapshot || restoreCamera === "none") {
      starFocusSessionRef.current = {
        starId: null,
        focusTarget: null,
        snapshot: null,
        startedAt: 0,
      };
      setStarFocusPhaseValue("idle");
      return;
    }

    if (restoreCamera === "jump" || prefersReducedMotion()) {
      jumpToBackgroundCamera(snapshot);
      starFocusSessionRef.current = {
        starId: null,
        focusTarget: null,
        snapshot: null,
        startedAt: 0,
      };
      setStarFocusPhaseValue("idle");
      return;
    }

    starFocusSessionRef.current = {
      ...starFocusSessionRef.current,
      startedAt: performance.now(),
    };
    backgroundCameraTargetOriginRef.current = { x: snapshot.x, y: snapshot.y };
    setBackgroundZoomTarget(snapshot.zoomFactor, { registerInteraction: false });
    setStarFocusPhaseValue("returning");
  }, [jumpToBackgroundCamera, setBackgroundZoomTarget, setStarFocusPhaseValue]);

  const openStarDetails = useCallback((
    star: UserStar,
    mode: "new" | "existing",
    options?: { fromFocus?: boolean },
  ) => {
    setPendingDetailStar(star);
    setSelectedUserStarId(star.id);
    setStarDetailsMode(mode);
    setStarDetailCloseLockedUntil(Date.now() + STAR_FOCUS_CLOSE_LOCK_MS);
    setStarDetailsOpen(true);
    if (!options?.fromFocus) {
      starFocusSessionRef.current = {
        starId: star.id,
        focusTarget: null,
        snapshot: null,
        startedAt: performance.now(),
      };
    }
    setStarFocusPhaseValue("details-open");
  }, [setStarFocusPhaseValue]);

  const focusExistingStar = useCallback((star: UserStar) => {
    const viewportWidth = canvasBoundsRef.current.width || window.innerWidth;
    const viewportHeight = canvasBoundsRef.current.height || window.innerHeight;
    const snapshot = cloneCameraSnapshot({
      x: backgroundCameraTargetOriginRef.current.x,
      y: backgroundCameraTargetOriginRef.current.y,
      zoomFactor: backgroundZoomTargetRef.current,
    });
    const focusTarget = buildStarFocusCamera(star, viewportWidth, viewportHeight);

    clearConstellationHoverState();
    setAddMessage(null);
    setDragMessage(null);
    setPendingDetailStar(star);
    setSelectedUserStarId(star.id);
    setStarDetailsMode("existing");
    setStarDetailCloseLockedUntil(Date.now() + STAR_FOCUS_CLOSE_LOCK_MS);
    setStarDetailsOpen(false);
    starFocusSessionRef.current = {
      starId: star.id,
      focusTarget,
      snapshot,
      startedAt: performance.now(),
    };

    if (prefersReducedMotion()) {
      jumpToBackgroundCamera(focusTarget);
      openStarDetails(star, "existing", { fromFocus: true });
      return;
    }

    backgroundCameraTargetOriginRef.current = { x: focusTarget.x, y: focusTarget.y };
    setBackgroundZoomTarget(focusTarget.zoomFactor, { registerInteraction: false });
    setStarFocusPhaseValue("focusing");
  }, [
    clearConstellationHoverState,
    jumpToBackgroundCamera,
    openStarDetails,
    setBackgroundZoomTarget,
    setStarFocusPhaseValue,
  ]);

  const handleStarDetailsOpenChange = useCallback((nextOpen: boolean) => {
    if (nextOpen) {
      setStarDetailsOpen(true);
      setStarFocusPhaseValue("details-open");
      return;
    }
    closeStarDetails();
  }, [closeStarDetails, setStarFocusPhaseValue]);

  const handleRemoveSelectedStar = useCallback(async () => {
    if (!selectedUserStar) {
      return;
    }

    await removeStarWithUndo(selectedUserStar.id, {
      afterRemove: () => closeStarDetails({ clearSelection: true, restoreCamera: "jump" }),
    });
  }, [closeStarDetails, removeStarWithUndo, selectedUserStar]);

  const handleRemoveHoveredStar = useCallback(async () => {
    if (!hoveredUserStarId) {
      return;
    }

    await removeStarWithUndo(hoveredUserStarId, {
      afterRemove: () => {
        closeStarTooltip();
        closeConcept();
      },
    });
  }, [closeConcept, closeStarTooltip, hoveredUserStarId, removeStarWithUndo]);

  const handleResetOrbit = useCallback(async () => {
    if (userStars.length === 0) {
      return;
    }

    await resetUserStars();
    closeStarDetails({ clearSelection: true, restoreCamera: "jump" });
    setDragMessage(null);
    setAddMessage(null);
    showToast({
      dismissMs: 2400,
      message: "Constellation orbit reset.",
      tone: "default",
    });
  }, [closeStarDetails, resetUserStars, showToast, userStars.length]);

  const nudgeBackgroundZoom = useCallback((direction: "in" | "out") => {
    const nextZoomFactor =
      direction === "out"
        ? backgroundZoomTargetRef.current * BACKGROUND_BUTTON_ZOOM_STEP
        : backgroundZoomTargetRef.current / BACKGROUND_BUTTON_ZOOM_STEP;
    clearConstellationHoverState();
    setBackgroundZoomTarget(nextZoomFactor);
  }, [clearConstellationHoverState, setBackgroundZoomTarget]);

  const resetBackgroundZoom = useCallback(() => {
    backgroundCameraOriginRef.current = { x: 0, y: 0 };
    backgroundCameraTargetOriginRef.current = { x: 0, y: 0 };
    clearConstellationHoverState();
    setBackgroundZoomTarget(1);
  }, [clearConstellationHoverState, setBackgroundZoomTarget]);

  const handleOpenHoveredStarDetails = useCallback(() => {
    if (!hoveredUserStarId) {
      return;
    }
    const hoveredStar = userStars.find((star) => star.id === hoveredUserStarId) ?? null;
    if (!hoveredStar) {
      return;
    }
    closeStarTooltip();
    focusExistingStar(hoveredStar);
  }, [closeStarTooltip, focusExistingStar, hoveredUserStarId, userStars]);

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
    const facultyLabel = describeIndexedFaculty(result);
    optimisticIndexKeysRef.current.add(getIndexSummaryKey(optimisticIndex));
    setIndexLoadError(null);
    setAddMessage(null);
    setAvailableIndexes((current) => {
      const next = upsertIndexSummary(current, optimisticIndex);
      availableIndexesRef.current = next;
      return next;
    });
    showToast({
      dismissMs: 2400,
      message: `Index ready: ${result.index_id}. METIS filed it near ${facultyLabel} and it is now available to map into orbit.`,
      tone: "default",
    });
      hasSessionIndexedContentRef.current = true;
    void refreshAvailableIndexes({ silent: true });
  }, [refreshAvailableIndexes, showToast]);

  const handleDeleteStarAndSources = useCallback(async ({
    starId,
    manifestPaths,
  }: {
    starId: string;
    manifestPaths: string[];
  }) => {
    const currentStars = userStarsRef.current;
    const starToDelete = currentStars.find((star) => star.id === starId) ?? null;
    if (!starToDelete) {
      throw new Error("This star is no longer available.");
    }

    const manifestPathsToDelete = uniqueManifestPaths(manifestPaths);
    const deletedManifestPaths = new Set<string>();

    try {
      for (const manifestPath of manifestPathsToDelete) {
        const result = await deleteIndex(manifestPath);
        deletedManifestPaths.add(result.manifest_path);
      }
    } catch (error) {
      if (deletedManifestPaths.size > 0) {
        await replaceUserStars(
          userStarsRef.current.map((star) =>
            removeDeletedManifestPathsFromStar(star, deletedManifestPaths)
          ),
        );
        clearPersistedActiveIndexIfDeleted(deletedManifestPaths);
        setAvailableIndexes((current) => {
          current.forEach((index) => {
            if (deletedManifestPaths.has(index.manifest_path)) {
              optimisticIndexKeysRef.current.delete(getIndexSummaryKey(index));
            }
          });
          const next = current.filter(
            (index) => !deletedManifestPaths.has(index.manifest_path),
          );
          availableIndexesRef.current = next;
          return next;
        });
        void refreshAvailableIndexes({ silent: true });
      }
      throw error;
    }

    await replaceUserStars(
      currentStars
        .filter((star) => star.id !== starId)
        .map((star) => removeDeletedManifestPathsFromStar(star, deletedManifestPaths)),
    );
    clearPersistedActiveIndexIfDeleted(deletedManifestPaths);
    setAvailableIndexes((current) => {
      current.forEach((index) => {
        if (deletedManifestPaths.has(index.manifest_path)) {
          optimisticIndexKeysRef.current.delete(getIndexSummaryKey(index));
        }
      });
      const next = current.filter(
        (index) => !deletedManifestPaths.has(index.manifest_path),
      );
      availableIndexesRef.current = next;
      return next;
    });
    closeStarDetails({ clearSelection: true, restoreCamera: "jump" });
    setAddMessage(null);
    setDragMessage(null);
    showToast({
      dismissMs: 3200,
      message: `${starToDelete.label ?? "Star"} and ${getCountLabel(deletedManifestPaths.size, "attached source")} deleted.`,
      tone: "default",
    });
    await refreshAvailableIndexes({ silent: true });
  }, [closeStarDetails, refreshAvailableIndexes, replaceUserStars, showToast]);

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

    const starsToAdd = candidateIndexes.slice(0, room).map((index, indexOffset) => (
      buildIndexStarDraft(index, userStars.length + indexOffset)
    ));

    const addedCount = await addUserStars(starsToAdd);
    if (addedCount > 0) {
      setAddMessage(null);
      showToast({
        dismissMs: 2400,
        message: `Seeded ${addedCount} indexed source${addedCount === 1 ? "" : "s"} into the constellation.`,
        tone: "default",
      });
    }
  }, [addUserStars, availableIndexes, refreshAvailableIndexes, showToast, starLimit, userStars]);

  useEffect(() => {
    void refreshAvailableIndexes();
  }, [refreshAvailableIndexes]);

  useEffect(() => {
    if (selectedUserStar && pendingDetailStar?.id === selectedUserStar.id) {
      setPendingDetailStar(null);
    }
  }, [pendingDetailStar, selectedUserStar]);

  useEffect(() => {
    const detailStarId = detailsStar?.id ?? null;
    if (!detailStarId) {
      clearLearningRoutePreview();
      return;
    }

    if (learningRoutePreviewStarId && learningRoutePreviewStarId !== detailStarId) {
      clearLearningRoutePreview();
    }
  }, [clearLearningRoutePreview, detailsStar, learningRoutePreviewStarId]);

  useEffect(() => {
    const focusedStarId = starFocusSessionRef.current.starId;
    if (!focusedStarId) {
      return;
    }
    const stillExists = userStars.some((star) => star.id === focusedStarId);
    if (stillExists) {
      return;
    }
    closeStarDetails({ clearSelection: true, restoreCamera: "jump" });
  }, [closeStarDetails, userStars]);

  useEffect(() => {
    if (!syncError && !addMessage) {
      return;
    }
    const message = syncError ?? addMessage;
    if (!message) {
      return;
    }
    showToast({
      dismissMs: syncError ? 4200 : 2400,
      message,
      tone: syncError ? "error" : "default",
    });
  }, [addMessage, showToast, syncError]);

  useEffect(() => {
    if (starLimit !== null && userStars.length >= starLimit) {
      hoveredAddCandidateRef.current = null;
      armedAddCandidateIdRef.current = null;
      setHoveredAddCandidateId(null);
    }
  }, [starLimit, userStars.length]);

  const requestLearningRoutePreview = useCallback(async (star: UserStar) => {
    if (!hasEligibleCourseSource(star)) {
      setLearningRouteError("Attach a source to this star before starting a course.");
      return;
    }

    const requestId = learningRouteRequestIdRef.current + 1;
    learningRouteRequestIdRef.current = requestId;
    setLearningRoutePreviewStarId(star.id);
    setLearningRouteLoading(true);
    setLearningRouteError(null);

    try {
      const preview = await previewLearningRoute(
        buildLearningRoutePreviewRequest(
          star,
          userStarsRef.current,
          availableIndexesRef.current,
        ),
      );
      if (learningRouteRequestIdRef.current !== requestId) {
        return;
      }
      setLearningRoutePreview(convertLearningRoutePreviewToRoute(preview));
    } catch (error) {
      if (learningRouteRequestIdRef.current !== requestId) {
        return;
      }
      console.error("Failed to preview learning route", error);
      setLearningRoutePreview(null);
      setLearningRouteError(
        error instanceof Error ? error.message : "Unable to plot a course right now.",
      );
    } finally {
      if (learningRouteRequestIdRef.current === requestId) {
        setLearningRouteLoading(false);
      }
    }
  }, []);

  const handleStartCourse = useCallback(() => {
    if (!detailsStar) {
      return;
    }
    void requestLearningRoutePreview(detailsStar);
  }, [detailsStar, requestLearningRoutePreview]);

  const handleSaveLearningRoutePreview = useCallback(async () => {
    if (!detailsStar || !activeLearningRoutePreview) {
      return;
    }

    const savedRoute = {
      ...cloneLearningRoute(activeLearningRoutePreview),
      updatedAt: new Date().toISOString(),
    };
    const updated = await updateUserStarById(detailsStar.id, {
      learningRoute: savedRoute,
    });
    if (!updated) {
      showToast({
        dismissMs: 3200,
        message: "Unable to save this learning route. Try again in a moment.",
        tone: "error",
      });
      return;
    }

    clearLearningRoutePreview();
    showToast({
      dismissMs: 2400,
      message: "Learning route saved to this star.",
      tone: "default",
    });
  }, [
    activeLearningRoutePreview,
    clearLearningRoutePreview,
    detailsStar,
    showToast,
    updateUserStarById,
  ]);

  const handleRegenerateLearningRoute = useCallback(() => {
    if (!detailsStar) {
      return;
    }
    void requestLearningRoutePreview(detailsStar);
  }, [detailsStar, requestLearningRoutePreview]);

  const handleLaunchLearningRouteStep = useCallback((step: LearningRouteStep) => {
    const sourceIndex = availableIndexesRef.current.find(
      (index) => index.manifest_path === step.manifestPath,
    );
    openChatWithIndex({
      manifestPath: step.manifestPath,
      label: sourceIndex?.index_id ?? detailsStar?.label ?? "Course source",
      selectedMode: "Tutor",
      draft: step.tutorPrompt,
    });
  }, [detailsStar, openChatWithIndex]);

  const handleSetLearningRouteStepStatus = useCallback(async (
    stepId: string,
    status: LearningRouteStepStatus,
  ) => {
    if (!detailsStar?.learningRoute) {
      return;
    }

    const completedAt = status === "done" ? new Date().toISOString() : undefined;
    const nextRoute = {
      ...cloneLearningRoute(detailsStar.learningRoute),
      updatedAt: completedAt ?? new Date().toISOString(),
      steps: detailsStar.learningRoute.steps.map((step) => (
        step.id === stepId
          ? {
            ...step,
            status,
            completedAt,
          }
          : step
      )),
    };
    const updated = await updateUserStarById(detailsStar.id, {
      learningRoute: nextRoute,
    });
    if (!updated) {
      showToast({
        dismissMs: 3200,
        message: "Unable to update route progress right now.",
        tone: "error",
      });
    }
  }, [detailsStar, showToast, updateUserStarById]);

  useEffect(() => {
    return subscribeBrainGraphRagActivity((activity) => {
      const timestamp = Number.isFinite(activity.timestamp) ? activity.timestamp : Date.now();
      const ttlMs = Math.max(1500, Math.round(activity.ttlMs ?? DEFAULT_BRAIN_GRAPH_HIGHLIGHT_TTL_MS));
      const manifestPaths = new Set<string>();
      const facultyIds = new Set<string>();
      const starIds = new Set<string>();

      const topLevelManifestPath = normalizeText(activity.manifestPath);
      if (topLevelManifestPath) {
        manifestPaths.add(topLevelManifestPath);
      }

      for (const source of activity.sources) {
        const manifestPath = getRagManifestPath(source);
        if (manifestPath) {
          manifestPaths.add(manifestPath);
        }
      }

      if (manifestPaths.size === 0) {
        ragPulseStateRef.current = null;
        return;
      }

      for (const star of userStarsRef.current) {
        const starManifestPaths = getStarManifestPaths(star);
        if (!starManifestPaths.some((manifestPath) => manifestPaths.has(manifestPath))) {
          continue;
        }

        starIds.add(star.id);
        facultyIds.add(resolveStarFaculty(star).id);
      }

      for (const index of availableIndexesRef.current) {
        if (!manifestPaths.has(index.manifest_path)) {
          continue;
        }
        const facultyId = getIndexFacultyId(index);
        if (facultyId) {
          facultyIds.add(facultyId);
        }
      }

      ragPulseStateRef.current = {
        startedAt: timestamp,
        expiresAt: timestamp + ttlMs,
        ttlMs,
        manifestPaths,
        facultyIds,
        starIds,
      };
    });
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let W = window.innerWidth;
    let H = window.innerHeight;
    const projectedUserStarTargets: ProjectedUserStarHitTarget[] = [];
    let projectedUserStarRenderState = new Map<string, ProjectedUserStarRenderState>();
    const projectedCandidateById = new Map<string, StarData>();
    let landingStarSpatialHash: LandingStarSpatialHash<LandingWorldStarRenderState> | null = null;

    function syncCanvasBounds() {
      const fallbackWidth = window.innerWidth;
      const fallbackHeight = window.innerHeight;
      W = canvas!.width = fallbackWidth;
      H = canvas!.height = fallbackHeight;
      const rect = canvas!.getBoundingClientRect();
      const width = rect.width || fallbackWidth;
      const height = rect.height || fallbackHeight;
      const left = rect.left ?? 0;
      const top = rect.top ?? 0;
      canvasBoundsRef.current = {
        left,
        top,
        width,
        height,
        right: rect.right || left + width,
        bottom: rect.bottom || top + height,
      };
    }

    function resize() {
      syncCanvasBounds();
    }

    function readCanvasBounds(): CanvasBounds {
      const currentBounds = canvasBoundsRef.current;
      if (currentBounds.width <= 0 || currentBounds.height <= 0) {
        syncCanvasBounds();
      }
      return canvasBoundsRef.current;
    }

    function isClientPointInsideCanvas(clientX: number, clientY: number): boolean {
      const bounds = readCanvasBounds();
      return (
        clientX >= bounds.left
        && clientX <= bounds.right
        && clientY >= bounds.top
        && clientY <= bounds.bottom
      );
    }

    function getCanvasPointer(clientX: number, clientY: number): Point {
      const bounds = readCanvasBounds();
      return {
        x: clientX - bounds.left,
        y: clientY - bounds.top,
      };
    }

    function getPointerTargetElement(eventTarget: EventTarget | null, clientX: number, clientY: number): Element | null {
      if (eventTarget instanceof Element) {
        return eventTarget;
      }

      if (typeof document.elementFromPoint === "function") {
        return document.elementFromPoint(clientX, clientY);
      }

      return null;
    }
    resize();

    const tileCache = new Map<string, WorldStarData[]>();
    backgroundZoomRef.current = clampBackgroundZoomFactor(backgroundZoomRef.current);
    backgroundZoomTargetRef.current = clampBackgroundZoomFactor(backgroundZoomTargetRef.current);

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

    function isPointInsideNodeLabel(node: NodeData, clientX: number, clientY: number): boolean {
      return clientX >= node._labelLeft
        && clientX <= node._labelRight
        && clientY >= node._labelTop
        && clientY <= node._labelBottom;
    }

    function isPointInsideNodeTarget(
      node: NodeData,
      clientX: number,
      clientY: number,
      nodeHitRadius: number,
    ): boolean {
      if (Math.hypot(node._sx - clientX, node._sy - clientY) < nodeHitRadius) {
        return true;
      }

      return isPointInsideNodeLabel(node, clientX, clientY);
    }

    function getHitNodeIndex(clientX: number, clientY: number): number {
      let hit = -1;
      nodes.forEach((node, index) => {
        const nodeHitRadius = coarsePointerRef.current ? 34 : 24;
        if (isPointInsideNodeTarget(node, clientX, clientY, nodeHitRadius)) {
          hit = index;
        }
      });

      return hit;
    }

    function showConceptAtNode(idx: number) {
      activeNodeRef.current = idx;
      const c = nodes[idx].concept;
      void addUserStar({
        x: c.faculty.x,
        y: c.faculty.y,
        size: 0.82 + Math.random() * 0.55,
        primaryDomainId: c.faculty.id,
        stage: "seed",
      }).then((createdStar) => {
        if (!createdStar) return;
        openStarDetails(createdStar, "new");
        clearHoveredCandidate();
      });
    }

    /* nodes */
    const nodes: NodeData[] = FACULTY_CONCEPTS.map((concept) => ({
      x: 0, y: 0,
      anchorX: concept.faculty.x,
      anchorY: concept.faculty.y,
      baseSize: 1.5 + Math.random() * 1.5,
      brightness: 0.15, targetBrightness: 0.15,
      concept,
      awakenDelay: 2000 + Math.random() * 1500,
      parallax: 0.015,
      hoverBoost: 0,
      targetHoverBoost: 0,
      _labelBottom: 0,
      _labelLeft: 0,
      _labelRight: 0,
      _labelTop: 0,
      _sx: 0, _sy: 0,
    }));

    function syncNodeLabelLayout(
      node: NodeData,
      screenX: number,
      screenY: number,
      nodeRadius: number,
      nodeGalaxyScale: number,
    ) {
      const labelFontSize = quantizeFontSize(10 + nodeGalaxyScale * 3.4);
      const labelFont = buildCanvasFont(labelFontSize, NODE_LABEL_FONT_FAMILY, NODE_LABEL_FONT_WEIGHT);
      const labelLineHeight = Math.max(
        labelFontSize + NODE_LABEL_PADDING_Y * 2,
        Math.ceil(labelFontSize * 1.45),
      );
      const labelWidth = measureSingleLineTextWidth(node.concept.title, labelFont);
      const labelHalfWidth = labelWidth / 2 + NODE_LABEL_PADDING_X;
      const labelY = screenY + nodeRadius + 18 * nodeGalaxyScale;
      const labelX = clampToRange(
        screenX,
        labelHalfWidth + NODE_LABEL_EDGE_MARGIN_PX,
        W - labelHalfWidth - NODE_LABEL_EDGE_MARGIN_PX,
      );
      const labelCenterY = labelY - labelFontSize * NODE_LABEL_CENTER_OFFSET_RATIO;
      const labelHalfHeight = labelLineHeight / 2;

      node._labelBottom = labelCenterY + labelHalfHeight;
      node._labelLeft = labelX - labelHalfWidth;
      node._labelRight = labelX + labelHalfWidth;
      node._labelTop = labelCenterY - labelHalfHeight;
      node._sx = screenX;
      node._sy = screenY;

      return {
        font: labelFont,
        x: labelX,
        y: labelY,
      };
    }

    function syncStaticNodeHitZones() {
      const nodeGalaxyScale = getZoomResponsiveNodeScale(backgroundZoomRef.current);
      nodes.forEach((node) => {
        const nodeRadius = node.baseSize * 2.9 * nodeGalaxyScale;
        syncNodeLabelLayout(node, node.x, node.y, nodeRadius, nodeGalaxyScale);
      });
    }

    applyNodeLayout(nodes, W, H, {
      x: backgroundCameraOriginRef.current.x,
      y: backgroundCameraOriginRef.current.y,
      zoomFactor: backgroundZoomRef.current,
    });
    syncStaticNodeHitZones();
    /* dust */
    const dust: DustData[] = [];
    for (let i = 0; i < 40; i++) dust.push(makeDust(W, H));

    const mouse = mouseRef.current;
    let awakened = false;
    let awakenStart = 0;
    let animFrame = 0;
    let lastVisibleStarfieldWidth = -1;
    let lastVisibleStarfieldHeight = -1;
    let lastVisibleStarfieldRevision = -1;
    let lastVisibleStarfieldZoom = Number.NaN;
    let lastVisibleStarfieldX = Number.NaN;
    let lastVisibleStarfieldY = Number.NaN;
    let lastVisibleWorldMinTileX = Number.NaN;
    let lastVisibleWorldMaxTileX = Number.NaN;
    let lastVisibleWorldMinTileY = Number.NaN;
    let lastVisibleWorldMaxTileY = Number.NaN;
    let lastVisibleWorldRevealBucket = -1;
    let visibleWorldStars: WorldStarData[] = [];
    let lastConstellationProjectionWidth = -1;
    let lastConstellationProjectionHeight = -1;
    let lastConstellationProjectionZoom = Number.NaN;
    let lastConstellationProjectionX = Number.NaN;
    let lastConstellationProjectionY = Number.NaN;

    function readBackgroundCamera(): BackgroundCameraState {
      return {
        x: backgroundCameraOriginRef.current.x,
        y: backgroundCameraOriginRef.current.y,
        zoomFactor: backgroundZoomRef.current,
      };
    }

    function getCachedStellarProfile(starId: string): StellarProfile {
      const cachedProfile = landingStarProfileCacheRef.current.get(starId);
      if (cachedProfile) {
        return cachedProfile;
      }

      const nextProfile = generateStellarProfile(starId);
      landingStarProfileCacheRef.current.set(starId, nextProfile);
      return nextProfile;
    }

    function syncConstellationLayout(backgroundCamera: BackgroundCameraState) {
      const shouldReproject =
        lastConstellationProjectionWidth !== W
        || lastConstellationProjectionHeight !== H
        || Math.abs(lastConstellationProjectionZoom - backgroundCamera.zoomFactor) > 0.0005
        || Math.abs(lastConstellationProjectionX - backgroundCamera.x) > STARFIELD_CAMERA_REBUILD_EPSILON
        || Math.abs(lastConstellationProjectionY - backgroundCamera.y) > STARFIELD_CAMERA_REBUILD_EPSILON;

      if (!shouldReproject) {
        return;
      }

      applyNodeLayout(nodes, W, H, backgroundCamera);
      syncStaticNodeHitZones();
      lastConstellationProjectionWidth = W;
      lastConstellationProjectionHeight = H;
      lastConstellationProjectionZoom = backgroundCamera.zoomFactor;
      lastConstellationProjectionX = backgroundCamera.x;
      lastConstellationProjectionY = backgroundCamera.y;
    }

    function getCandidateConstellationPoint(
      candidate: Pick<StarData, "nx" | "ny" | "parallaxFactor">,
      backgroundCamera: BackgroundCameraState,
    ): Point {
      const projected = projectBackgroundStar(candidate, W, H, mouse);

      return screenToConstellationPoint(projected, W, H, backgroundCamera);
    }

    function getSelectedLinkAnchor(candidatePoint: Point): UserStar | null {
      const selectedStarId = selectedUserStarIdRef.current;
      if (!selectedStarId) {
        return null;
      }

      const selectedStar = userStarsRef.current.find((star) => star.id === selectedStarId) ?? null;
      if (!selectedStar) {
        return null;
      }

      const selectedPoint = getResolvedStarPoint(
        selectedStar,
        dragPreviewPositionsRef.current,
        selectedStar.id,
      );
      const distance = Math.hypot(selectedPoint.x - candidatePoint.x, selectedPoint.y - candidatePoint.y);
      if (distance > USER_STAR_LINK_MAX_DISTANCE) {
        return null;
      }

      return selectedStar;
    }

    function refreshVisibleStars(backgroundCamera: BackgroundCameraState) {
      const worldBounds = getBackgroundViewportWorldBounds(
        W,
        H,
        backgroundCamera,
        BACKGROUND_TILE_PADDING_PX,
      );
      const minTileX = Math.floor(worldBounds.left / BACKGROUND_TILE_SIZE) - 1;
      const maxTileX = Math.floor(worldBounds.right / BACKGROUND_TILE_SIZE) + 1;
      const minTileY = Math.floor(worldBounds.top / BACKGROUND_TILE_SIZE) - 1;
      const maxTileY = Math.floor(worldBounds.bottom / BACKGROUND_TILE_SIZE) + 1;
      const revealBucket = getWorldRevealBucket(backgroundCamera.zoomFactor);
      const shouldRebuildVisibleWorldStars =
        lastVisibleStarfieldRevision !== starfieldRevisionRef.current
        || minTileX !== lastVisibleWorldMinTileX
        || maxTileX !== lastVisibleWorldMaxTileX
        || minTileY !== lastVisibleWorldMinTileY
        || maxTileY !== lastVisibleWorldMaxTileY
        || revealBucket !== lastVisibleWorldRevealBucket;

      if (shouldRebuildVisibleWorldStars) {
        const nextVisibleWorldStars: WorldStarData[] = [];

        for (let layer = 2; layer >= 0; layer -= 1) {
          for (let tileX = minTileX; tileX <= maxTileX; tileX += 1) {
            for (let tileY = minTileY; tileY <= maxTileY; tileY += 1) {
              const tileStars = getWorldTileStars(tileCache, layer, tileX, tileY);

              tileStars.forEach((worldStar) => {
                if (backgroundCamera.zoomFactor + 1e-6 < worldStar.revealZoomFactor) {
                  return;
                }

                nextVisibleWorldStars.push(worldStar);
              });
            }
          }
        }

        visibleWorldStars = nextVisibleWorldStars;
        lastVisibleWorldMinTileX = minTileX;
        lastVisibleWorldMaxTileX = maxTileX;
        lastVisibleWorldMinTileY = minTileY;
        lastVisibleWorldMaxTileY = maxTileY;
        lastVisibleWorldRevealBucket = revealBucket;
      }

      const projectedUserStars = userStarsRef.current.map((star) => {
        const projected = projectConstellationPoint(
          { x: star.x, y: star.y },
          W,
          H,
          backgroundCamera,
        );

        return {
          x: projected.x / W,
          y: projected.y / H,
        };
      });

      const constellationCameraScale = getConstellationCameraScale(backgroundCamera.zoomFactor);
      const allConstellationStarPx = nodes.flatMap((node) =>
        node.concept.faculty.shape.stars.map((shapeStar) => {
          const anchorX = node.x + (mouse.x - W / 2) * node.parallax;
          const anchorY = node.y + (mouse.y - H / 2) * node.parallax;

          return {
            x: anchorX + shapeStar.dx * W * constellationCameraScale,
            y: anchorY + shapeStar.dy * H * constellationCameraScale,
          };
        })
      );

      const scale = getBackgroundCameraScale(backgroundCamera.zoomFactor);
      const nextVisibleStars = visibleStarsRef.current;
      let visibleStarCount = 0;

      visibleWorldStars.forEach((worldStar) => {
        const screenX = (worldStar.worldX - backgroundCamera.x) * scale + W / 2;
        const screenY = (worldStar.worldY - backgroundCamera.y) * scale + H / 2;

        if (
          screenX < -BACKGROUND_TILE_PADDING_PX
          || screenX > W + BACKGROUND_TILE_PADDING_PX
          || screenY < -BACKGROUND_TILE_PADDING_PX
          || screenY > H + BACKGROUND_TILE_PADDING_PX
        ) {
          return;
        }

        const normalizedX = screenX / W;
        const normalizedY = screenY / H;
        const sizeMultiplier =
          worldStar.layer === 0
            ? 0.48 + scale * 0.98
            : worldStar.layer === 1
              ? 0.42 + scale * 0.82
              : 0.34 + scale * 0.68;
        const projectedSize = Math.max(0.12, worldStar.baseSize * sizeMultiplier);
        const brightness = Math.min(
          0.94,
          worldStar.brightness + Math.min(0.16, Math.log2(backgroundCamera.zoomFactor + 1) * 0.03),
        );
        const star = nextVisibleStars[visibleStarCount] ?? {
          id: worldStar.id,
          nx: normalizedX,
          ny: normalizedY,
          layer: worldStar.layer,
          baseSize: projectedSize,
          brightness,
          twinkle: worldStar.twinkle,
          twinkleSpeed: worldStar.twinkleSpeed,
          twinklePhase: worldStar.twinklePhase,
          parallaxFactor: worldStar.parallaxFactor,
          hasDiffraction: worldStar.hasDiffraction,
          isAddable: false,
        };

        star.id = worldStar.id;
        star.nx = normalizedX;
        star.ny = normalizedY;
        star.layer = worldStar.layer;
        star.baseSize = projectedSize;
        star.brightness = brightness;
        star.twinkle = worldStar.twinkle;
        star.twinkleSpeed = worldStar.twinkleSpeed;
        star.twinklePhase = worldStar.twinklePhase;
        star.parallaxFactor = worldStar.parallaxFactor;
        star.hasDiffraction = worldStar.hasDiffraction;
        const hasLinkedSourceContent = userStarsRef.current.some(
          (userStar) => getStarManifestPaths(userStar).length > 0,
        );
        // Allow star adding if the user has any available index (even from prior sessions),
        // not just one built in the current session — restores the ability to add the first
        // star when indexes exist but no user stars have been mapped yet.
        const hasUserContent = hasLinkedSourceContent
          || hasSessionIndexedContentRef.current
          || availableIndexesRef.current.length > 0;
        star.isAddable = isAddableBackgroundStar(star, allConstellationStarPx, projectedUserStars, W, H, hasUserContent);
        nextVisibleStars[visibleStarCount] = star;
        visibleStarCount += 1;
      });

      nextVisibleStars.length = visibleStarCount;
      projectedCandidateById.clear();

      const landingRenderableStars: LandingWorldStarRenderState[] = nextVisibleStars.map((star) => {
        const profile = getCachedStellarProfile(star.id);
        const projectedStar: LandingWorldStarRenderState = {
          addable: star.isAddable,
          apparentSize: star.baseSize,
          brightness: star.brightness,
          hitRadius: Math.max(8, star.baseSize * 5.5),
          id: star.id,
          profile,
          x: star.nx * W,
          y: star.ny * H,
        };

        if (star.isAddable) {
          projectedCandidateById.set(star.id, star);
        }

        return projectedStar;
      });
      const renderPlan = buildLandingStarRenderPlan(landingRenderableStars, backgroundCamera.zoomFactor);
      const flattenedRenderPlan = [
        ...renderPlan.batches.point,
        ...renderPlan.batches.sprite,
        ...renderPlan.batches.hero,
      ];
      const nextWebglStars: LandingWebglStar[] = flattenedRenderPlan.map((star) => ({
        addable: star.addable,
        apparentSize: star.apparentSize,
        brightness: star.brightness,
        id: star.id,
        profile: star.profile,
        renderTier: star.renderTier,
        x: star.x,
        y: star.y,
      }));
      const addableTargets = landingRenderableStars.filter((star) => star.addable);

      landingStarSpatialHash = addableTargets.length > 0
        ? buildLandingStarSpatialHash(addableTargets)
        : null;
      landingStarfieldFrameRef.current = {
        height: H,
        revision: landingStarfieldFrameRef.current.revision + 1,
        stars: nextWebglStars,
        width: W,
      };
      lastVisibleStarfieldWidth = W;
      lastVisibleStarfieldHeight = H;
      lastVisibleStarfieldRevision = starfieldRevisionRef.current;
      lastVisibleStarfieldZoom = backgroundCamera.zoomFactor;
      lastVisibleStarfieldX = backgroundCamera.x;
      lastVisibleStarfieldY = backgroundCamera.y;
    }

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

    function rebuildProjectedUserStarRenderState(
      backgroundCamera: BackgroundCameraState,
      renderTimeMs: number,
    ) {
      const currentSelectedStarId = selectedUserStarIdRef.current;
      const previewPositions = dragPreviewPositionsRef.current;
      projectedUserStarTargets.length = 0;
      projectedUserStarRenderState = new Map();

      userStarsRef.current.forEach((star) => {
        const resolvedPoint = getResolvedStarPoint(star, previewPositions, star.id);
        const faculty = resolveStarFaculty({
          x: resolvedPoint.x,
          y: resolvedPoint.y,
          primaryDomainId: star.primaryDomainId,
        });
        const influenceColors = buildStarInfluenceColors({
          primaryDomainId: faculty.id,
          relatedDomainIds: star.relatedDomainIds,
        });
        const mixed = mixConstellationColors(influenceColors);
        const target = buildProjectedUserStarHitTarget(
          {
            id: star.id,
            x: resolvedPoint.x,
            y: resolvedPoint.y,
            size: star.size,
          },
          W,
          H,
          backgroundCamera,
          coarsePointerRef.current ? 12 : 0,
          mouse,
        );

        projectedUserStarTargets.push(target);
        projectedUserStarRenderState.set(star.id, {
          attachmentCount: getStarAttachmentCount(star),
          dragging: dragStateRef.current?.starId === star.id && dragStateRef.current.moved,
          fadeIn: getStarFadeProgress(star, renderTimeMs),
          influenceColors,
          mixed,
          profile: createUserStarVisualProfile(star.id),
          ringCount: getStageRingCount(star.stage),
          selected: currentSelectedStarId === star.id,
          star,
          stellarProfile: getCachedStellarProfile(star.id),
          target,
        });
      });
    }

    function drawUserStarEdges(ts: number) {
      const currentUserStars = userStarsRef.current;
      if (currentUserStars.length === 0 || projectedUserStarRenderState.size === 0) {
        return;
      }

      const selectedStarId = selectedUserStarIdRef.current;
      const renderTimeMs = getRenderEpochMs(ts);
      const ragPulseState = ragPulseStateRef.current;
      const ragPulseStrength = getHomeRagPulseStrength(ragPulseState, renderTimeMs);
      const edgeBreath = reducedMotion
        ? 1
        : 1 + USER_STAR_EDGE_BREATH_AMPLITUDE * Math.sin((Math.PI * 2 * ts) / USER_STAR_EDGE_BREATH_PERIOD_MS);

      const renderedLinks = new Set<string>();
      currentUserStars.forEach((star) => {
        const from = projectedUserStarRenderState.get(star.id);
        if (!from || !star.connectedUserStarIds || star.connectedUserStarIds.length === 0) {
          return;
        }

        star.connectedUserStarIds.forEach((linkedStarId) => {
          const to = projectedUserStarRenderState.get(linkedStarId);
          if (!to) {
            return;
          }

          const edgeKey = star.id < linkedStarId
            ? `${star.id}:${linkedStarId}`
            : `${linkedStarId}:${star.id}`;
          if (renderedLinks.has(edgeKey)) {
            return;
          }
          renderedLinks.add(edgeKey);

          const alphaMultiplier = Math.max(0, Math.min(1, Math.min(from.fadeIn, to.fadeIn) * edgeBreath));
          const ragHighlighted = ragPulseStrength > 0
            && (ragPulseState?.starIds.has(star.id) || ragPulseState?.starIds.has(linkedStarId));
          const selectedEdge = selectedStarId !== null
            && (star.id === selectedStarId || linkedStarId === selectedStarId);
          const ragBoost = ragHighlighted ? ragPulseStrength : 0;
          // Always render edges so the constellation structure stays visible;
          // boost alpha on selection to signal which branches belong to the picked star.
          const edgeAlpha = selectedEdge ? 0.32 : ragHighlighted ? 0.21 : 0.13;
          const gradient = ctx!.createLinearGradient(from.target.x, from.target.y, to.target.x, to.target.y);
          gradient.addColorStop(0, `rgba(${from.mixed[0]},${from.mixed[1]},${from.mixed[2]},${(edgeAlpha + ragBoost * 0.34) * alphaMultiplier})`);
          gradient.addColorStop(1, `rgba(${to.mixed[0]},${to.mixed[1]},${to.mixed[2]},${(edgeAlpha + ragBoost * 0.34) * alphaMultiplier})`);
          ctx!.strokeStyle = gradient;
          ctx!.lineWidth = 0.95 + ragBoost * 1.35;
          ctx!.beginPath();
          ctx!.moveTo(from.target.x, from.target.y);
          ctx!.lineTo(to.target.x, to.target.y);
          ctx!.stroke();
        });
      });
    }

    function drawUserStars(t: number) {
      if (projectedUserStarRenderState.size === 0) {
        return;
      }

      const renderTimeMs = getRenderEpochMs(t);
      const ragPulseState = ragPulseStateRef.current;
      const ragPulseStrength = getHomeRagPulseStrength(ragPulseState, renderTimeMs);
      const constellationScale = getConstellationCameraScale(backgroundZoomRef.current);
      const userStarScale = Math.max(0.58, 0.36 + Math.pow(constellationScale, 0.72) * 0.64);

      projectedUserStarRenderState.forEach((projectedState) => {
        const {
          attachmentCount,
          dragging,
          fadeIn,
          influenceColors,
          mixed,
          profile,
          ringCount,
          selected,
          star,
          stellarProfile,
          target,
        } = projectedState;
        const ragHighlighted = ragPulseStrength > 0 && Boolean(ragPulseState?.starIds.has(star.id));
        const richness = 1 + Math.max(0, influenceColors.length - 1) * 0.18;
        const haloColor = mixRgbColors(
          applyTintBias(mixed, profile.tintBias * 1.05),
          stellarProfile.palette.halo,
          0.52,
        );
        const fillColor = mixRgbColors(
          applyTintBias(mixed, profile.tintBias * 0.48),
          stellarProfile.palette.surface,
          0.44,
        );
        const coreColor = mixRgbColors(fillColor, stellarProfile.palette.core, 0.72);
        const accentColor = mixRgbColors(stellarProfile.palette.accent, mixed, 0.38);
        const shadowColor = applyTintBias(
          mixRgbColors(stellarProfile.palette.rim, fillColor, 0.28),
          profile.tintBias * 0.12,
        );
        const px = target.x;
        const py = target.y;
        const sz = (star.size * 1.5 + (selected ? 1.2 : 0) + (dragging ? 0.8 : 0)) * userStarScale;
        const twinkle = 0.84
          + Math.sin(t * 0.003 + profile.twinklePhase) * 0.1
          + Math.cos(t * 0.0016 + profile.twinklePhase * 0.72) * 0.05;
        const haloRadius = sz * (4.7 + profile.haloFalloff * 2.4 + ringCount * 0.16) * richness;
        const haloCenterX = px + profile.asymmetryOffset.x * sz * 2.1;
        const haloCenterY = py + profile.asymmetryOffset.y * sz * 1.8;
        const auraRadius = sz * (2.8 + profile.coreIntensity * 0.72 + ringCount * 0.14);

        const halo = ctx!.createRadialGradient(haloCenterX, haloCenterY, sz * 0.22, px, py, haloRadius);
        halo.addColorStop(0, `rgba(${haloColor[0]},${haloColor[1]},${haloColor[2]},${(0.14 + profile.coreIntensity * 0.04 + (selected ? 0.08 : 0) + (ragHighlighted ? ragPulseStrength * 0.12 : 0)) * fadeIn})`);
        halo.addColorStop(Math.min(0.76, 0.48 + profile.haloFalloff * 0.18), `rgba(${fillColor[0]},${fillColor[1]},${fillColor[2]},${(0.05 + richness * 0.02) * fadeIn})`);
        halo.addColorStop(1, "rgba(0,0,0,0)");
        ctx!.fillStyle = halo;
        ctx!.beginPath();
        ctx!.arc(px, py, haloRadius, 0, Math.PI * 2);
        ctx!.fill();

        if (influenceColors.length > 1) {
          influenceColors.slice(1, 3).forEach(([sr, sg, sb], influenceIndex) => {
            const drift = influenceIndex % 2 === 0 ? 1 : -1;
            const accentX = px - profile.asymmetryOffset.x * sz * (1.8 + influenceIndex * 0.5) + drift * sz * 0.42;
            const accentY = py + profile.asymmetryOffset.y * sz * (1.5 + influenceIndex * 0.45);
            const accentRadius = haloRadius * (0.64 + influenceIndex * 0.12);
            const accentGlow = ctx!.createRadialGradient(accentX, accentY, sz * 0.14, px, py, accentRadius);
            accentGlow.addColorStop(0, `rgba(${sr},${sg},${sb},${(0.07 + (selected ? 0.03 : 0)) * fadeIn})`);
            accentGlow.addColorStop(1, "rgba(0,0,0,0)");
            ctx!.fillStyle = accentGlow;
            ctx!.beginPath();
            ctx!.arc(px, py, accentRadius, 0, Math.PI * 2);
            ctx!.fill();
          });
        }

        const aura = ctx!.createRadialGradient(px, py, sz * 0.2, px, py, auraRadius);
        aura.addColorStop(0, `rgba(${fillColor[0]},${fillColor[1]},${fillColor[2]},${(0.14 + profile.coreIntensity * 0.05 + (ragHighlighted ? ragPulseStrength * 0.12 : 0)) * fadeIn})`);
        aura.addColorStop(1, "rgba(0,0,0,0)");
        ctx!.fillStyle = aura;
        ctx!.beginPath();
        ctx!.arc(px, py, auraRadius, 0, Math.PI * 2);
        ctx!.fill();

        if (ragHighlighted) {
          ctx!.beginPath();
          ctx!.arc(px, py, sz * (4.1 + ragPulseStrength * 1.1), 0, Math.PI * 2);
          ctx!.strokeStyle = `rgba(${haloColor[0]},${haloColor[1]},${haloColor[2]},${0.26 + ragPulseStrength * 0.34})`;
          ctx!.lineWidth = 1.15 + ragPulseStrength * 0.7;
          ctx!.stroke();
        }

        if (profile.hasDiffraction) {
          const spikeLength = sz * (4.2 + profile.coreIntensity * 1.8 + ringCount * 0.28);
          ctx!.save();
          ctx!.translate(px, py);
          ctx!.rotate(profile.spikeAngle);
          ctx!.strokeStyle = `rgba(${fillColor[0]},${fillColor[1]},${fillColor[2]},${(selected ? 0.22 : 0.12) * fadeIn})`;
          ctx!.lineWidth = selected ? 0.95 : 0.7;
          ctx!.beginPath();
          ctx!.moveTo(-spikeLength, 0);
          ctx!.lineTo(spikeLength, 0);
          ctx!.moveTo(0, -spikeLength * 0.72);
          ctx!.lineTo(0, spikeLength * 0.72);
          ctx!.stroke();
          ctx!.restore();
        }

        const fill = ctx!.createRadialGradient(
          px - sz * (0.36 + profile.asymmetryOffset.x * 0.18),
          py - sz * (0.38 - profile.asymmetryOffset.y * 0.18),
          sz * (0.14 + profile.coreIntensity * 0.08),
          px,
          py,
          sz * 1.42,
        );
        fill.addColorStop(0, `rgba(255,255,255,${Math.min(1, (0.95 + profile.coreIntensity * 0.08) * fadeIn)})`);
        fill.addColorStop(0.16, `rgba(${coreColor[0]},${coreColor[1]},${coreColor[2]},${0.98 * fadeIn})`);
        fill.addColorStop(0.24, `rgba(${fillColor[0]},${fillColor[1]},${fillColor[2]},${0.94 * fadeIn})`);
        fill.addColorStop(0.68, `rgba(${haloColor[0]},${haloColor[1]},${haloColor[2]},${0.88 * fadeIn})`);
        fill.addColorStop(1, `rgba(${shadowColor[0]},${shadowColor[1]},${shadowColor[2]},${0.98 * fadeIn})`);
        ctx!.fillStyle = fill;
        ctx!.beginPath();
        ctx!.arc(px, py, sz, 0, Math.PI * 2);
        ctx!.fill();

        const satelliteCount = Math.min(attachmentCount, 3);
        for (let satelliteIndex = 0; satelliteIndex < satelliteCount; satelliteIndex += 1) {
          const angle = t * 0.001 + profile.twinklePhase * 0.2 + (Math.PI * 2 * satelliteIndex) / Math.max(1, satelliteCount);
          const orbitRadius = sz + 11 + satelliteIndex * 2;
          const satelliteX = px + Math.cos(angle) * orbitRadius;
          const satelliteY = py + Math.sin(angle) * orbitRadius * 0.8;
          ctx!.beginPath();
          ctx!.arc(satelliteX, satelliteY, 1.3 + satelliteIndex * 0.25, 0, Math.PI * 2);
          ctx!.fillStyle = `rgba(${accentColor[0]},${accentColor[1]},${accentColor[2]},${0.85 * fadeIn})`;
          ctx!.fill();
        }

        ctx!.beginPath();
        ctx!.arc(px, py, sz * 0.34, 0, Math.PI * 2);
        ctx!.fillStyle = `rgba(${coreColor[0]},${coreColor[1]},${coreColor[2]},${Math.min(1, (0.9 + twinkle * 0.09) * fadeIn)})`;
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

    function drawPolarisMetis(ts: number) {
      const polarisCam = readBackgroundCamera();
      const projected = projectConstellationPoint(
        { x: CORE_CENTER_X, y: CORE_CENTER_Y },
        W,
        H,
        polarisCam,
      );
      // Match the parallax applied to constellation nodes so Polaris drifts
      // in sync with the surrounding star field on mouse movement.
      const ppx = projected.x + (mouse.x - W / 2) * 0.015;
      const ppy = projected.y + (mouse.y - H / 2) * 0.015;
      const pulse = reducedMotion ? 1 : 0.88 + Math.sin(ts * 0.00209) * 0.12;
      const nodeGalaxyScale = getZoomResponsiveNodeScale(backgroundZoomRef.current);
      const coreR = 5 * nodeGalaxyScale;

      // Outer gold glow
      const outerGrad = ctx!.createRadialGradient(ppx, ppy, 0, ppx, ppy, 44 * nodeGalaxyScale);
      outerGrad.addColorStop(0, `rgba(255,240,180,${0.14 * pulse})`);
      outerGrad.addColorStop(0.5, `rgba(220,190,80,${0.06 * pulse})`);
      outerGrad.addColorStop(1, "rgba(0,0,0,0)");
      ctx!.fillStyle = outerGrad;
      ctx!.beginPath(); ctx!.arc(ppx, ppy, 44 * nodeGalaxyScale, 0, Math.PI * 2); ctx!.fill();

      // Mid corona
      const midGrad = ctx!.createRadialGradient(ppx, ppy, 0, ppx, ppy, 20 * nodeGalaxyScale);
      midGrad.addColorStop(0, `rgba(255,252,220,${0.32 * pulse})`);
      midGrad.addColorStop(1, "rgba(0,0,0,0)");
      ctx!.fillStyle = midGrad;
      ctx!.beginPath(); ctx!.arc(ppx, ppy, 20 * nodeGalaxyScale, 0, Math.PI * 2); ctx!.fill();

      // 6-point diffraction spikes (very slowly rotating)
      const spikeAngle = ts * 0.00008;
      ctx!.save();
      ctx!.strokeStyle = `rgba(255,240,160,${0.48 * pulse})`;
      ctx!.lineWidth = 0.85;
      for (let ii = 0; ii < 6; ii++) {
        const a = spikeAngle + (Math.PI / 3) * ii;
        ctx!.beginPath();
        ctx!.moveTo(ppx + Math.cos(a) * coreR * 1.2, ppy + Math.sin(a) * coreR * 1.2);
        ctx!.lineTo(ppx + Math.cos(a) * 28 * nodeGalaxyScale, ppy + Math.sin(a) * 28 * nodeGalaxyScale);
        ctx!.stroke();
      }
      ctx!.restore();

      // Core disk
      ctx!.beginPath(); ctx!.arc(ppx, ppy, coreR, 0, Math.PI * 2);
      ctx!.fillStyle = `rgba(255,252,230,${0.96 * pulse})`; ctx!.fill();
      ctx!.beginPath(); ctx!.arc(ppx, ppy, coreR * 0.4, 0, Math.PI * 2);
      ctx!.fillStyle = "rgba(255,255,255,1)"; ctx!.fill();

      // METIS label
      const fontSize = Math.round(10 + nodeGalaxyScale * 4);
      ctx!.font = buildCanvasFont(fontSize, NODE_LABEL_FONT_FAMILY, "600");
      ctx!.textAlign = "center";
      ctx!.fillStyle = `rgba(255,235,140,${0.72 * pulse})`;
      ctx!.fillText("METIS", ppx, ppy - coreR - 10 * nodeGalaxyScale);
    }

    function drawNodes(t: number) {
      const aNode = activeNodeRef.current;
      const hasAddCandidate = hoveredAddCandidateRef.current !== null;
      const renderTimeMs = getRenderEpochMs(t);
      const ragPulseState = ragPulseStateRef.current;
      const ragPulseStrength = getHomeRagPulseStrength(ragPulseState, renderTimeMs);
      const nodeGalaxyScale = getZoomResponsiveNodeScale(backgroundZoomRef.current);
      const lineWidth = 0.38 + nodeGalaxyScale * 0.34;
      nodes.forEach((n, i) => {
        const ragFacultyHighlighted = ragPulseStrength > 0 && Boolean(ragPulseState?.facultyIds.has(n.concept.faculty.id));
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
        if (ragFacultyHighlighted) {
          n.targetBrightness = Math.max(n.targetBrightness, 0.56 + ragPulseStrength * 0.34);
        }
        if (i === aNode) n.targetBrightness = 0.9;
        n.brightness += (n.targetBrightness - n.brightness) * 0.06;
        n.targetHoverBoost = hasAddCandidate ? 0 : hoveredNodeRef.current === i ? 1 : 0;
        n.hoverBoost += (n.targetHoverBoost - n.hoverBoost) * (enhancedHoverMotion ? 0.12 : 0.25);
        const b = n.brightness;
        const hoverScale = enhancedHoverMotion ? n.hoverBoost * 2.6 : 0;
        const s = (n.baseSize * 2.9 + proximity * 2.6 + (i === aNode ? 1.35 : 0) + hoverScale) * nodeGalaxyScale;

        // Intra-constellation stick-figure lines
        const cScale = getConstellationCameraScale(backgroundZoomRef.current);
        const edgeAlpha = Math.max(
          nodeAwakenProg * 0.18,
          i === aNode ? 0.28 : proximity * 0.30,
          ragFacultyHighlighted ? 0.26 + ragPulseStrength * 0.40 : 0,
        );
        if (edgeAlpha > 0.02) {
          n.concept.faculty.shape.edges.forEach(([si, sj]) => {
            const sa = n.concept.faculty.shape.stars[si];
            const sb = n.concept.faculty.shape.stars[sj];
            const ragBoost = ragFacultyHighlighted ? ragPulseStrength : 0;
            ctx!.beginPath();
            ctx!.moveTo(px + sa.dx * W * cScale, py + sa.dy * H * cScale);
            ctx!.lineTo(px + sb.dx * W * cScale, py + sb.dy * H * cScale);
            ctx!.strokeStyle = `rgba(${r},${g},${bl},${Math.min(0.85, edgeAlpha * (0.72 + ragBoost * 0.70))})`;
            ctx!.lineWidth = lineWidth + ragBoost * 1.2;
            ctx!.stroke();
          });
        }

        // Secondary constellation stars (shape.stars[1..])
        n.concept.faculty.shape.stars.slice(1).forEach((shapeStar) => {
          const spx = px + shapeStar.dx * W * cScale;
          const spy = py + shapeStar.dy * H * cScale;
          const ss = s * 0.55;
          if (b > 0.18 || nodeAwakenProg > 0.3) {
            const sg = ctx!.createRadialGradient(spx, spy, 0, spx, spy, ss * 9);
            sg.addColorStop(0, `rgba(${r},${g},${bl},${b * 0.06})`);
            sg.addColorStop(1, "rgba(0,0,0,0)");
            ctx!.fillStyle = sg;
            ctx!.beginPath(); ctx!.arc(spx, spy, ss * 9, 0, Math.PI * 2); ctx!.fill();
          }
          ctx!.beginPath(); ctx!.arc(spx, spy, ss, 0, Math.PI * 2);
          ctx!.fillStyle = `rgba(${r},${g},${bl},${Math.max(0.55, b)})`;
          ctx!.fill();
          ctx!.beginPath(); ctx!.arc(spx, spy, Math.max(0.7, ss * 0.38), 0, Math.PI * 2);
          ctx!.fillStyle = "rgba(255,255,255,0.82)";
          ctx!.fill();
        });
        if (b > 0.25 || n.hoverBoost > 0.1) {
          const grad = ctx!.createRadialGradient(px, py, 0, px, py, s * 12);
          grad.addColorStop(0, `rgba(${r},${g},${bl},${b * 0.08 + n.hoverBoost * 0.12})`);
          grad.addColorStop(1, "rgba(0,0,0,0)");
          ctx!.fillStyle = grad; ctx!.beginPath();
          ctx!.arc(px, py, s * 12, 0, Math.PI * 2); ctx!.fill();
        }
        ctx!.beginPath(); ctx!.arc(px, py, s, 0, Math.PI * 2);
        ctx!.fillStyle = `rgba(${r},${g},${bl},${Math.max(0.72, b + 0.06)})`;
        ctx!.fill();
        ctx!.beginPath();
        ctx!.arc(px, py, Math.max(1.25, s * 0.38), 0, Math.PI * 2);
        ctx!.fillStyle = `rgba(255,255,255,${0.9 + Math.min(0.08, proximity * 0.08)})`;
        ctx!.fill();
        if (proximity > 0.2) {
          ctx!.beginPath(); ctx!.arc(px, py, s + 4 + proximity * 4, 0, Math.PI * 2);
          ctx!.strokeStyle = `rgba(${r},${g},${bl},${proximity * 0.22})`; ctx!.lineWidth = 0.5; ctx!.stroke();
        }
        const labelLayout = syncNodeLabelLayout(n, px, py, s, nodeGalaxyScale);

        ctx!.font = labelLayout.font;
        ctx!.textAlign = "center";
        ctx!.fillStyle = `rgba(${r},${g},${bl},${0.48 + b * 0.24})`;
        ctx!.fillText(n.concept.title, labelLayout.x, labelLayout.y);
      });
    }

    function drawAddCandidatePreview(ts: number) {
      const candidate = hoveredAddCandidateRef.current;
      if (!candidate) {
        return;
      }

      const backgroundCamera = readBackgroundCamera();
      const candidatePoint = getCandidateConstellationPoint(candidate, backgroundCamera);
      const previewInfluence = inferConstellationFaculty(candidatePoint);
      const primaryNode = nodes.find(
        (node) => node.concept.faculty.id === previewInfluence.primary.faculty.id,
      );
      const cScale = getConstellationCameraScale(backgroundZoomRef.current);
      const previewNodes = primaryNode
        ? getPreviewConnectionNodes(
            candidate,
            primaryNode.concept.faculty.shape.stars
              .map((shapeStar) => {
                const anchorX = primaryNode.x + (mouse.x - W / 2) * primaryNode.parallax;
                const anchorY = primaryNode.y + (mouse.y - H / 2) * primaryNode.parallax;

                return {
                  _sx: anchorX + shapeStar.dx * W * cScale,
                  _sy: anchorY + shapeStar.dy * H * cScale,
                  x: anchorX + shapeStar.dx * W * cScale,
                  y: anchorY + shapeStar.dy * H * cScale,
                };
              }),
            W,
            H,
          )
        : [];
      const previewColors = getInfluenceColors(
        previewInfluence.primary.faculty.id,
        previewInfluence.bridgeSuggestion ? [previewInfluence.bridgeSuggestion.faculty.id] : undefined,
      );
      const [primaryPreviewR, primaryPreviewG, primaryPreviewB] = previewColors[0];
      const [mixedPreviewR, mixedPreviewG, mixedPreviewB] = mixConstellationColors(previewColors);
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
        grad.addColorStop(0, `rgba(${primaryPreviewR},${primaryPreviewG},${primaryPreviewB},${0.24 + pulse * 0.1})`);
        grad.addColorStop(1, `rgba(${mixedPreviewR},${mixedPreviewG},${mixedPreviewB},${0.32 + pulse * 0.12})`);
        ctx!.strokeStyle = grad;
        ctx!.lineWidth = index === 0 ? 1.15 : 0.75;
        ctx!.beginPath();
        ctx!.moveTo(node._sx, node._sy);
        ctx!.lineTo(px, py);
        ctx!.stroke();
      });

      const selectedAnchor = getSelectedLinkAnchor(candidatePoint);
      if (selectedAnchor) {
        const anchorPoint = getResolvedStarPoint(
          selectedAnchor,
          dragPreviewPositionsRef.current,
          selectedAnchor.id,
        );
        const anchorProjected = projectedUserStarRenderState.get(selectedAnchor.id)?.target
          ?? buildProjectedUserStarHitTarget(
            {
              id: selectedAnchor.id,
              size: selectedAnchor.size,
              x: anchorPoint.x,
              y: anchorPoint.y,
            },
            W,
            H,
            backgroundCamera,
            coarsePointerRef.current ? 12 : 0,
            mouse,
          );
        const anchorFaculty = resolveStarFaculty({
          x: anchorPoint.x,
          y: anchorPoint.y,
          primaryDomainId: selectedAnchor.primaryDomainId,
        });
        const [anchorR, anchorG, anchorB] = getFacultyColor(anchorFaculty.id);
        const anchorGradient = ctx!.createLinearGradient(anchorProjected.x, anchorProjected.y, px, py);
        anchorGradient.addColorStop(0, `rgba(${anchorR},${anchorG},${anchorB},${0.26 + pulse * 0.08})`);
        anchorGradient.addColorStop(1, `rgba(${mixedPreviewR},${mixedPreviewG},${mixedPreviewB},${0.32 + pulse * 0.1})`);
        ctx!.strokeStyle = anchorGradient;
        ctx!.lineWidth = 0.95;
        ctx!.beginPath();
        ctx!.moveTo(anchorProjected.x, anchorProjected.y);
        ctx!.lineTo(px, py);
        ctx!.stroke();
      }
      ctx!.restore();

      const halo = candidate.baseSize * 10 + 12 + pulse * 4;
      const glow = ctx!.createRadialGradient(px, py, 0, px, py, halo);
      glow.addColorStop(0, `rgba(240,244,255,${0.34 + pulse * 0.12})`);
      glow.addColorStop(0.45, `rgba(${mixedPreviewR},${mixedPreviewG},${mixedPreviewB},${0.22 + pulse * 0.1})`);
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
      ctx!.strokeStyle = `rgba(${primaryPreviewR},${primaryPreviewG},${primaryPreviewB},${0.36 + pulse * 0.12})`;
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
      const originDeltaX = backgroundCameraTargetOriginRef.current.x - backgroundCameraOriginRef.current.x;
      const originDeltaY = backgroundCameraTargetOriginRef.current.y - backgroundCameraOriginRef.current.y;
      if (Math.abs(originDeltaX) > 0.05 || Math.abs(originDeltaY) > 0.05) {
        backgroundCameraOriginRef.current = reducedMotion
          ? { ...backgroundCameraTargetOriginRef.current }
          : {
              x: backgroundCameraOriginRef.current.x + originDeltaX * 0.14,
              y: backgroundCameraOriginRef.current.y + originDeltaY * 0.14,
            };
      } else {
        backgroundCameraOriginRef.current = { ...backgroundCameraTargetOriginRef.current };
      }

      const zoomDelta = backgroundZoomTargetRef.current - backgroundZoomRef.current;
      if (Math.abs(zoomDelta) > 0.0005) {
        backgroundZoomRef.current = reducedMotion
          ? backgroundZoomTargetRef.current
          : backgroundZoomRef.current + zoomDelta * 0.12;
      } else {
        backgroundZoomRef.current = backgroundZoomTargetRef.current;
      }

      const backgroundCamera: BackgroundCameraState = {
        x: backgroundCameraOriginRef.current.x,
        y: backgroundCameraOriginRef.current.y,
        zoomFactor: backgroundZoomRef.current,
      };

      const starFocusSession = starFocusSessionRef.current;
      if (
        starFocusPhaseRef.current === "focusing"
        && starFocusSession.focusTarget
        && starFocusSession.starId
      ) {
        const focusedStar = userStarsRef.current.find((star) => star.id === starFocusSession.starId) ?? null;
        const focusTimedOut = ts - starFocusSession.startedAt >= STAR_FOCUS_SETTLE_TIMEOUT_MS;

        if (!focusedStar) {
          closeStarDetails({ clearSelection: true, restoreCamera: "jump" });
        } else if (focusTimedOut || isCameraSettled(backgroundCamera, starFocusSession.focusTarget)) {
          jumpToBackgroundCamera(starFocusSession.focusTarget);
          openStarDetails(focusedStar, "existing", { fromFocus: true });
        }
      }

      if (
        starFocusPhaseRef.current === "returning"
        && starFocusSession.snapshot
      ) {
        const returnTimedOut = ts - starFocusSession.startedAt >= STAR_FOCUS_SETTLE_TIMEOUT_MS;

        if (returnTimedOut || isCameraSettled(backgroundCamera, starFocusSession.snapshot)) {
          jumpToBackgroundCamera(starFocusSession.snapshot);
          starFocusSessionRef.current = {
            starId: null,
            focusTarget: null,
            snapshot: null,
            startedAt: 0,
          };
          setStarFocusPhaseValue("idle");
        }
      }

      syncConstellationLayout(backgroundCamera);
      const shouldRefreshVisibleStars =
        lastVisibleStarfieldWidth !== W
        || lastVisibleStarfieldHeight !== H
        || lastVisibleStarfieldRevision !== starfieldRevisionRef.current
        || Math.abs(lastVisibleStarfieldZoom - backgroundCamera.zoomFactor) > 0.0005
        || Math.abs(lastVisibleStarfieldX - backgroundCamera.x) > STARFIELD_CAMERA_REBUILD_EPSILON
        || Math.abs(lastVisibleStarfieldY - backgroundCamera.y) > STARFIELD_CAMERA_REBUILD_EPSILON;
      if (shouldRefreshVisibleStars) {
        refreshVisibleStars(backgroundCamera);
      }
      rebuildProjectedUserStarRenderState(backgroundCamera, getRenderEpochMs(ts));

      ctx!.clearRect(0, 0, W, H);
      if (!awakened && ts > 2000) {
        awakened = true; awakenStart = ts;
      }
      drawNebulae();
      drawDust();
      drawNodes(ts);
      drawUserStarEdges(ts);
      drawAddCandidatePreview(ts);
      drawUserStars(ts);
      drawPolarisMetis(ts);
      projectedUserStarTargetsRef.current = projectedUserStarTargets;
      animFrame = requestAnimationFrame(render);
    }
    animFrame = requestAnimationFrame(render);

    function onResize() {
      resize();
      applyNodeLayout(nodes, W, H, {
        x: backgroundCameraOriginRef.current.x,
        y: backgroundCameraOriginRef.current.y,
        zoomFactor: backgroundZoomRef.current,
      });
      syncStaticNodeHitZones();
      nebulae[0].x = W * 0.72; nebulae[0].y = H * 0.35;
      nebulae[1].x = W * 0.25; nebulae[1].y = H * 0.65;
      nebulae[2].x = W * 0.55; nebulae[2].y = H * 0.2;
      lastVisibleStarfieldWidth = -1;
      lastConstellationProjectionWidth = -1;
    }

    function getHoveredUserStar(clientX: number, clientY: number): {
      star: UserStar;
      target: ProjectedUserStarHitTarget;
    } | null {
      const pointer = getCanvasPointer(clientX, clientY);
      const previewPositions = dragPreviewPositionsRef.current;
      const backgroundCamera = readBackgroundCamera();
      const cachedTargets = projectedUserStarTargetsRef.current;
      const availableTargets = cachedTargets.length > 0
        ? cachedTargets
        : userStarsRef.current.map((star) => {
            const resolvedPoint = getResolvedStarPoint(star, previewPositions, star.id);
            return buildProjectedUserStarHitTarget(
              {
                id: star.id,
                x: resolvedPoint.x,
                y: resolvedPoint.y,
                size: star.size,
              },
              W,
              H,
              backgroundCamera,
              coarsePointerRef.current ? 12 : 0,
              mouse,
            );
          });
      const target = findClosestProjectedTarget(availableTargets, pointer);
      if (!target) {
        return null;
      }
      const star = userStarsRef.current.find((entry) => entry.id === target.id) ?? null;
      if (!star) {
        return null;
      }
      return {
        star,
        target,
      };
    }

    function getHitStar(clientX: number, clientY: number): UserStar | null {
      return getHoveredUserStar(clientX, clientY)?.star ?? null;
    }

    function showStarTooltip(star: UserStar, target: ProjectedUserStarHitTarget) {
      const card = starTooltipCardRef.current;
      if (!card) {
        return;
      }

      if (starTooltipHideTimeoutRef.current !== null) {
        window.clearTimeout(starTooltipHideTimeoutRef.current);
        starTooltipHideTimeoutRef.current = null;
      }

      const faculty = resolveStarFaculty(star);
      const title = star.label?.trim() || "Untitled Star";
      const description = getStarTooltipDescription(star, faculty);
      const domainLabel = faculty.label;

      if (starTooltipDomainRef.current) {
        starTooltipDomainRef.current.textContent = `Domain: ${domainLabel}`;
      }
      if (starTooltipTitleRef.current) {
        starTooltipTitleRef.current.textContent = title;
      }
      if (starTooltipDescRef.current) {
        starTooltipDescRef.current.textContent = description;
      }

      const bounds = readCanvasBounds();
      const anchorX = bounds.left + target.x;
      const anchorY = bounds.top + target.y;

      card.style.display = "block";
      const cardWidth = card.offsetWidth || 280;
      const cardHeight = card.offsetHeight || 178;
      let cx = anchorX + 20;
      let cy = anchorY - Math.min(38, cardHeight * 0.24);

      if (cx + cardWidth + 16 > window.innerWidth) {
        cx = anchorX - cardWidth - 20;
      }
      if (cx < 16) {
        cx = 16;
      }
      if (cy + cardHeight + 16 > window.innerHeight) {
        cy = window.innerHeight - cardHeight - 16;
      }
      if (cy < 16) {
        cy = 16;
      }

      card.style.left = `${cx}px`;
      card.style.top = `${cy}px`;
      requestAnimationFrame(() => card.classList.add("active"));

      setHoveredUserStarId((current) => (current === star.id ? current : star.id));
    }

    function hideStarTooltip() {
      if (starTooltipHideTimeoutRef.current !== null) {
        window.clearTimeout(starTooltipHideTimeoutRef.current);
        starTooltipHideTimeoutRef.current = null;
      }

      setHoveredUserStarId((current) => (current === null ? current : null));
      const card = starTooltipCardRef.current;
      if (!card) {
        return;
      }

      card.classList.remove("active");
      starTooltipHideTimeoutRef.current = window.setTimeout(() => {
        card.style.display = "none";
        starTooltipHideTimeoutRef.current = null;
      }, 180);
    }

    function getHoveredCandidate(clientX: number, clientY: number): StarData | null {
      const pointer = getCanvasPointer(clientX, clientY);
      const spatialHash = landingStarSpatialHash ?? (() => {
        const addableTargets = visibleStarsRef.current
          .filter((star) => star.isAddable)
          .map<LandingWorldStarRenderState>((star) => ({
            addable: true,
            apparentSize: star.baseSize,
            brightness: star.brightness,
            hitRadius: Math.max(8, star.baseSize * 5.5),
            id: star.id,
            profile: getCachedStellarProfile(star.id),
            x: star.nx * W,
            y: star.ny * H,
          }));

        return addableTargets.length > 0 ? buildLandingStarSpatialHash(addableTargets) : null;
      })();
      if (!spatialHash) {
        return null;
      }

      const target = findClosestLandingStarHitTarget(
        spatialHash,
        pointer.x,
        pointer.y,
        {
          queryPaddingPx: coarsePointerRef.current
            ? MOBILE_ADD_CANDIDATE_HIT_RADIUS_PX
            : ADD_CANDIDATE_HIT_RADIUS_PX,
        },
      );
      if (!target) {
        return null;
      }
      return projectedCandidateById.get(target.id)
        ?? visibleStarsRef.current.find((star) => star.id === target.id)
        ?? null;
    }

    function releaseCanvasPointerCapture(pointerId?: number | null) {
      if (pointerId === undefined || pointerId === null || !canvas) {
        return;
      }

      try {
        canvas.releasePointerCapture(pointerId);
      } catch {
        // Ignore release failures when the pointer is already gone.
      }
    }

    function clearDragState(clearMessage = false, pointerId?: number | null) {
      const currentDrag = dragStateRef.current;
      const nextPointerId = pointerId ?? currentDrag?.pointerId;
      if (currentDrag) {
        dragPreviewPositionsRef.current.delete(currentDrag.starId);
      }
      dragStateRef.current = null;
      releaseCanvasPointerCapture(nextPointerId);
      if (clearMessage) {
        setDragMessage(null);
      }
    }

    function clearPanState(pointerId?: number | null) {
      const nextPointerId = pointerId ?? panStateRef.current?.pointerId;
      panStateRef.current = null;
      releaseCanvasPointerCapture(nextPointerId);
      setIsCanvasPanning(false);
    }

    function onPointerMove(e: PointerEvent) {
      mouse.x = e.clientX;
      mouse.y = e.clientY;

      const panState = panStateRef.current;
      if (panState && panState.pointerId === e.pointerId) {
        const travelDistance = Math.hypot(e.clientX - panState.startClientX, e.clientY - panState.startClientY);
        if (!panState.moved && travelDistance >= DRAG_DISTANCE_PX) {
          panState.moved = true;
          setIsCanvasPanning(true);
          clearHoveredCandidate();
          hideStarTooltip();
          closeConcept();
          setDragMessage(null);
        }
        if (!panState.moved) {
          return;
        }

        const scale = getBackgroundCameraScale(panState.zoomFactor);
        const nextOrigin = {
          x: panState.startOrigin.x - (e.clientX - panState.startClientX) / scale,
          y: panState.startOrigin.y - (e.clientY - panState.startClientY) / scale,
        };
        backgroundCameraOriginRef.current = nextOrigin;
        backgroundCameraTargetOriginRef.current = nextOrigin;
        return;
      }

      const dragState = dragStateRef.current;
      if (dragState && dragState.pointerId === e.pointerId) {
        const bounds = readCanvasBounds();
        const constellationPoint = screenToConstellationPoint(
          getCanvasPointer(e.clientX, e.clientY),
          bounds.width,
          bounds.height,
          readBackgroundCamera(),
        );
        const travelDistance = Math.hypot(e.clientX - dragState.startClientX, e.clientY - dragState.startClientY);
        if (!dragState.moved && travelDistance >= DRAG_DISTANCE_PX) {
          dragState.moved = true;
        }
        if (!dragState.moved) {
          return;
        }
        const [nextX, nextY] = clampPointToOrbit(constellationPoint.x, constellationPoint.y);
        dragPreviewPositionsRef.current.set(dragState.starId, { x: nextX, y: nextY });
        const inference = inferConstellationFaculty({ x: nextX, y: nextY });
        setDragMessage(
          describeFacultyDrop(
            inference.primary.faculty,
            inference.bridgeSuggestion?.faculty ?? null,
          ),
        );
        clearHoveredCandidate();
        hideStarTooltip();
        closeConcept();
        return;
      }

      if (activeCanvasTool === "grab") {
        hoveredNodeRef.current = -1;
        hoverExpandedRef.current = false;
        clearHoveredCandidate();
        hideStarTooltip();
        closeConcept();
        return;
      }

      if (starFocusPhaseRef.current !== "idle") {
        hoveredNodeRef.current = -1;
        hoverExpandedRef.current = false;
        clearHoveredCandidate();
        hideStarTooltip();
        return;
      }

      if (!isClientPointInsideCanvas(e.clientX, e.clientY)) {
        hoveredNodeRef.current = -1;
        hoverExpandedRef.current = false;
        clearHoveredCandidate();
        hideStarTooltip();
        return;
      }

      const targetElement = getPointerTargetElement(e.target, e.clientX, e.clientY);
      const pointerOnCanvas = targetElement === canvas;
      const pointerOnStarTooltip = Boolean(targetElement?.closest("#starTooltipCard"));
      if (!pointerOnCanvas && !pointerOnStarTooltip) {
        hoveredNodeRef.current = -1;
        hoverExpandedRef.current = false;
        clearHoveredCandidate();
        hideStarTooltip();
        return;
      }
      if (pointerOnStarTooltip) {
        hoveredNodeRef.current = -1;
        hoverExpandedRef.current = false;
        clearHoveredCandidate();
        closeConcept();
        return;
      }

      const canAddMoreStars = starLimit === null || userStarsRef.current.length < starLimit;
      if (canAddMoreStars) {
        const candidate = getHoveredCandidate(e.clientX, e.clientY);

        syncHoveredCandidate(candidate);
        if (candidate) {
          hoveredNodeRef.current = -1;
          hoverExpandedRef.current = false;
          hideStarTooltip();
          closeConcept();
          return;
        }
      } else {
        clearHoveredCandidate();
      }

      const hoveredUserStar = getHoveredUserStar(e.clientX, e.clientY);
      if (hoveredUserStar) {
        hoveredNodeRef.current = -1;
        hoverExpandedRef.current = false;
        showStarTooltip(hoveredUserStar.star, hoveredUserStar.target);
        closeConcept();
        return;
      }

      hideStarTooltip();

      let hover = -1;
      nodes.forEach((n, i) => {
        if (isPointInsideNodeTarget(n, e.clientX, e.clientY, 28)) {
          hover = i;
        }
      });
      if (hover !== hoveredNodeRef.current) {
        hoveredNodeRef.current = hover;
        hoverStartRef.current = hover >= 0 ? performance.now() : 0;
        hoverExpandedRef.current = false;
      }
      if (hover >= 0 && !hoverExpandedRef.current && performance.now() - hoverStartRef.current >= HOVER_EXPAND_DELAY_MS) {
        hoverExpandedRef.current = true;
      }
    }

    function onCanvasPointerDown(e: PointerEvent) {
      if (starFocusPhaseRef.current !== "idle") {
        return;
      }

      if (activeCanvasTool === "grab") {
        const currentCamera = readBackgroundCamera();
        const snappedOrigin = { x: currentCamera.x, y: currentCamera.y };

        backgroundCameraOriginRef.current = snappedOrigin;
        backgroundCameraTargetOriginRef.current = snappedOrigin;
        backgroundZoomTargetRef.current = currentCamera.zoomFactor;
        setBackgroundZoomFactor((current) => (
          Math.abs(current - currentCamera.zoomFactor) < 0.001 ? current : currentCamera.zoomFactor
        ));
        panStateRef.current = {
          pointerId: e.pointerId,
          startClientX: e.clientX,
          startClientY: e.clientY,
          startOrigin: snappedOrigin,
          zoomFactor: currentCamera.zoomFactor,
          moved: false,
        };
        setAddMessage(null);
        setDragMessage(null);
        clearHoveredCandidate();
        hideStarTooltip();
        closeConcept();
        try {
          canvas!.setPointerCapture(e.pointerId);
        } catch {
          // Ignore capture failures; pan still works via document listeners.
        }
        return;
      }

      const hitStar = getHitStar(e.clientX, e.clientY);
      if (!hitStar) {
        return;
      }

      dragStateRef.current = {
        pointerId: e.pointerId,
        starId: hitStar.id,
        startClientX: e.clientX,
        startClientY: e.clientY,
        moved: false,
      };
      setSelectedUserStarId(hitStar.id);
      setPendingDetailStar(null);
      setAddMessage(null);
      setDragMessage(null);
      clearHoveredCandidate();
      hideStarTooltip();
      closeConcept();
      try {
        canvas!.setPointerCapture(e.pointerId);
      } catch {
        // Ignore capture failures; drag still works via document listeners.
      }
    }

    function onCanvasPress(e: PointerEvent) {
      if (starFocusPhaseRef.current !== "idle") {
        clearDragState(true);
        clearPanState();
        return;
      }

      const panState = panStateRef.current;
      if (panState && panState.pointerId === e.pointerId) {
        clearPanState();
        return;
      }

      if (activeCanvasTool === "grab") {
        clearPanState();
        return;
      }

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
          showToast({
            dismissMs: 2400,
            message: `${selectedStar.label ?? "Star"} settled into ${inference.primary.faculty.label}.`,
            tone: "default",
          });
          setAddMessage(null);
          clearDragState(true);
          return;
        }

        clearDragState(true);
        if (selectedStar) {
          focusExistingStar(selectedStar);
        }
        return;
      }

      if (!isClientPointInsideCanvas(e.clientX, e.clientY)) {
        return;
      }
      const targetElement = getPointerTargetElement(e.target, e.clientX, e.clientY);
      if (targetElement !== canvas) {
        return;
      }

      const currentUserStars = userStarsRef.current;
      const currentSelectedStarId = selectedUserStarIdRef.current;
      const hitNodeIndex = getHitNodeIndex(e.clientX, e.clientY);

      if (hitNodeIndex >= 0) {
        armedAddCandidateIdRef.current = null;
        if (currentSelectedStarId) {
          setSelectedUserStarId(null);
          setPendingDetailStar(null);
        }
        if (activeNodeRef.current === hitNodeIndex) {
          closeConcept();
          return;
        }
        showConceptAtNode(hitNodeIndex);
        return;
      }

      const candidate = (starLimit === null || currentUserStars.length < starLimit)
        ? getHoveredCandidate(e.clientX, e.clientY)
        : null;

      if (candidate) {
        const backgroundCamera = readBackgroundCamera();
        const candidatePoint = getCandidateConstellationPoint(candidate, backgroundCamera);
        const selectedAnchor = getSelectedLinkAnchor(candidatePoint);
        const selectedStarId = selectedUserStarIdRef.current;
        if (coarsePointerRef.current && armedAddCandidateIdRef.current !== candidate.id) {
          armedAddCandidateIdRef.current = candidate.id;
          hoveredAddCandidateRef.current = candidate;
          setHoveredAddCandidateId((current) => (current === candidate.id ? current : candidate.id));
          setAddMessage("Tap the same star again to pull it in and open its details.");
          closeConcept();
          return;
        }

        const inference = inferConstellationFaculty(candidatePoint);
        addUserStar({
          x: candidatePoint.x,
          y: candidatePoint.y,
          size: 0.82 + Math.random() * 0.55,
          primaryDomainId: inference.primary.faculty.id,
          relatedDomainIds: inference.bridgeSuggestion ? [inference.bridgeSuggestion.faculty.id] : undefined,
          connectedUserStarIds: selectedAnchor ? [selectedAnchor.id] : undefined,
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
          let message = "Star added to the constellation. Its details are open.";
          if (selectedStarId && !selectedAnchor) {
            message = "Star added to the constellation. The selected anchor was too far to link.";
          } else if (selectedAnchor) {
            message = "Star added and linked into the selected constellation branch.";
          }
          showToast({
            dismissMs: 2400,
            message,
            tone: "default",
          });
          openStarDetails(createdStar, "new");
          clearHoveredCandidate();
        });
        closeConcept();
        return;
      }

      armedAddCandidateIdRef.current = null;
      if (currentSelectedStarId) {
        setSelectedUserStarId(null);
        setPendingDetailStar(null);
      }
      closeConcept();
    }

    function clearPointerHoverState() {
      if (dragStateRef.current || panStateRef.current) {
        return;
      }
      hoveredNodeRef.current = -1;
      hoverExpandedRef.current = false;
      clearHoveredCandidate();
      hideStarTooltip();
      setDragMessage(null);
    }

    function onPointerLeave(e: PointerEvent) {
      const relatedTarget = e.relatedTarget instanceof Element ? e.relatedTarget : null;
      if (relatedTarget?.closest("#starTooltipCard")) {
        return;
      }
      clearPointerHoverState();
    }

    function onPointerCancel(e: PointerEvent) {
      const isDragPointer = dragStateRef.current?.pointerId === e.pointerId;
      const isPanPointer = panStateRef.current?.pointerId === e.pointerId;

      if (!isDragPointer && !isPanPointer) {
        return;
      }

      clearDragState(true, e.pointerId);
      clearPanState(e.pointerId);
      clearPointerHoverState();
    }

    function onCanvasLostPointerCapture(e: PointerEvent) {
      const isDragPointer = dragStateRef.current?.pointerId === e.pointerId;
      const isPanPointer = panStateRef.current?.pointerId === e.pointerId;

      if (!isDragPointer && !isPanPointer) {
        return;
      }

      clearDragState(true, e.pointerId);
      clearPanState(e.pointerId);
      clearPointerHoverState();
    }

    function onBlur() {
      clearDragState(true);
      clearPanState();
      clearPointerHoverState();
    }

    function onWheel(e: WheelEvent) {
      if (dragStateRef.current || panStateRef.current || starFocusPhaseRef.current !== "idle") {
        return;
      }

      const targetElement = e.target instanceof Element ? e.target : null;
      const wheelInsideZoomUi = Boolean(targetElement?.closest(".metis-zoom-pill"));
      if (!isClientPointInsideCanvas(e.clientX, e.clientY) && !wheelInsideZoomUi) {
        return;
      }

      e.preventDefault();

      const bounds = readCanvasBounds();
      const pointer = getCanvasPointer(e.clientX, e.clientY);
      const currentCamera: BackgroundCameraState = {
        x: backgroundCameraOriginRef.current.x,
        y: backgroundCameraOriginRef.current.y,
        zoomFactor: backgroundZoomTargetRef.current,
      };
      const worldBeforeZoom = screenToWorldPoint(pointer, bounds.width, bounds.height, currentCamera);
      const zoomMultiplier = Math.exp(e.deltaY * 0.0014);
      const nextZoomFactor = clampBackgroundZoomFactor(currentCamera.zoomFactor * zoomMultiplier);

      if (Math.abs(nextZoomFactor - currentCamera.zoomFactor) < 0.0005) {
        registerZoomInteraction();
        return;
      }

      const worldAfterZoom = screenToWorldPoint(
        pointer,
        bounds.width,
        bounds.height,
        { ...currentCamera, zoomFactor: nextZoomFactor },
      );
      const nextOrigin = {
        x: currentCamera.x + (worldBeforeZoom.x - worldAfterZoom.x),
        y: currentCamera.y + (worldBeforeZoom.y - worldAfterZoom.y),
      };
      backgroundCameraOriginRef.current = nextOrigin;
      backgroundCameraTargetOriginRef.current = nextOrigin;

      clearConstellationHoverState();
      setBackgroundZoomTarget(nextZoomFactor);
    }

    window.addEventListener("resize", onResize);
    canvas.addEventListener("pointerdown", onCanvasPointerDown);
    canvas.addEventListener("lostpointercapture", onCanvasLostPointerCapture);
    document.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointercancel", onPointerCancel);
    window.addEventListener("pointerup", onCanvasPress);
    canvas.addEventListener("pointerleave", onPointerLeave);
    window.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("blur", onBlur);

    return () => {
      cancelAnimationFrame(animFrame);
      window.removeEventListener("resize", onResize);
      canvas.removeEventListener("pointerdown", onCanvasPointerDown);
      canvas.removeEventListener("lostpointercapture", onCanvasLostPointerCapture);
      document.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointercancel", onPointerCancel);
      window.removeEventListener("pointerup", onCanvasPress);
      canvas.removeEventListener("pointerleave", onPointerLeave);
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("blur", onBlur);
    };
  }, [
    activeCanvasTool,
    addUserStar,
    clearConstellationHoverState,
    closeConcept,
    closeStarDetails,
    focusExistingStar,
    jumpToBackgroundCamera,
    openStarDetails,
    registerZoomInteraction,
    setBackgroundZoomTarget,
    setStarFocusPhaseValue,
    showToast,
    starLimit,
    updateUserStarById,
  ]);

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

      <LandingStarfieldWebgl
        className="metis-starfield-webgl"
        frameRef={landingStarfieldFrameRef}
      />

      <canvas
        ref={canvasRef}
        id="universe"
        className="metis-universe"
        data-canvas-tool={activeCanvasTool}
        data-focus-phase={starFocusPhase}
        data-details-open={starDetailsOpen ? "true" : "false"}
        data-pan-active={isCanvasPanning ? "true" : "false"}
      />

      <div className="metis-hero-overlay">
        <div className={`metis-hero-shell ${zoomInteracting || canvasInteractionsLocked ? "is-muted" : ""}`}>
          <h1 className="metis-hero-headline">Discover everything</h1>
        </div>
      </div>

      <div className={`metis-zoom-pill ${canvasInteractionsLocked ? "is-muted" : ""}`} aria-live="polite">
        <div className="metis-zoom-pill-value">{backgroundZoomLabel}</div>
        <div className="metis-zoom-pill-tools" role="toolbar" aria-label="Constellation tools">
          <button
            type="button"
            className={`metis-zoom-pill-btn metis-zoom-pill-tool-btn ${activeCanvasTool === "select" ? "is-active" : ""}`}
            onClick={() => setActiveCanvasTool("select")}
            disabled={canvasInteractionsLocked}
            aria-label="Select tool"
            aria-pressed={activeCanvasTool === "select"}
            title="Select stars and concepts"
          >
            Select
          </button>
          <button
            type="button"
            className={`metis-zoom-pill-btn metis-zoom-pill-tool-btn ${activeCanvasTool === "grab" ? "is-active" : ""}`}
            onClick={() => setActiveCanvasTool("grab")}
            disabled={canvasInteractionsLocked}
            aria-label="Grab tool"
            aria-pressed={activeCanvasTool === "grab"}
            title="Hand tool for dragging the constellation"
          >
            Hand
          </button>
        </div>
        <div className="metis-zoom-pill-actions">
          <button
            type="button"
            className="metis-zoom-pill-btn"
            onClick={() => nudgeBackgroundZoom("in")}
            disabled={canvasInteractionsLocked || backgroundZoomFactor <= MIN_BACKGROUND_ZOOM_FACTOR + 0.01}
            aria-label="Zoom closer"
          >
            -
          </button>
          <button
            type="button"
            className="metis-zoom-pill-btn metis-zoom-pill-btn-reset"
            onClick={resetBackgroundZoom}
            disabled={canvasInteractionsLocked || Math.abs(backgroundZoomFactor - 1) < 0.01}
            aria-label="Reset zoom"
          >
            1x
          </button>
          <button
            type="button"
            className="metis-zoom-pill-btn"
            onClick={() => nudgeBackgroundZoom("out")}
            disabled={canvasInteractionsLocked || backgroundZoomFactor >= MAX_BACKGROUND_ZOOM_FACTOR - 0.5}
            aria-label="Zoom farther"
          >
            +
          </button>
        </div>
      </div>

      <section id="build-map" className="metis-build-section">
        <div className="metis-build-toolbar">
          <div className="metis-build-stats" aria-live="polite">
            <div className="metis-build-stat">{starCountLabel}</div>
            <div className="metis-build-stat">{detectedSourceCountLabel}</div>
            <div className="metis-build-stat">{readyToMapCountLabel}</div>
            <div className="metis-build-stat">{attachmentsCountLabel}</div>
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
              onClick={() => void handleRemoveSelectedStar()}
              disabled={!selectedUserStar}
            >
              Remove selected
            </button>
            <button
              type="button"
              className="metis-star-btn"
              onClick={() => void handleResetOrbit()}
              disabled={userStars.length === 0}
            >
              Reset orbit
            </button>
          </div>
        </div>

        <div className="metis-build-studio-shell">
          <div className={`metis-build-note ${buildNoteTone}`}>{buildNoteMessage}</div>

          <div className="metis-star-editor">
            <div className="metis-star-editor-head">Star details</div>
            <p className="metis-star-editor-copy">{selectedStarSummary}</p>
            {isAutonomousStar(selectedStarActiveIndex?.index_id) && (
              <p className="metis-star-editor-copy" style={{ color: "rgb(196, 181, 253)", fontSize: "0.75rem" }}>
                ✦ Added autonomously by METIS
                {getAutoStarFaculty(selectedStarActiveIndex?.index_id)
                  ? ` · ${getAutoStarFaculty(selectedStarActiveIndex?.index_id)}`
                  : ""}
              </p>
            )}
            <p className="metis-star-editor-copy">
              Follow the faculty ring when you drag or seed stars. Claimed stars keep their own
              source context, so uploads, attachments, and grounded chat remain aligned to the same
              manifest path.
            </p>
          </div>
        </div>
      </section>
      {toastState ? (
        <div
          className={`metis-toast ${toastState.tone === "error" ? "error" : ""}`}
          aria-live="polite"
          role="status"
        >
          <span className="metis-toast__message">{toastState.message}</span>
          {toastState.onAction ? (
            <button
              type="button"
              className="metis-toast__action"
              onClick={() => {
                const action = toastState.onAction;
                clearToast();
                action?.();
              }}
            >
              {toastState.actionLabel ?? "Undo"}
            </button>
          ) : null}
        </div>
      ) : null}

      {learningRouteOverlay ? (
        <svg
          aria-hidden="true"
          data-testid="learning-route-overlay"
          style={{
            inset: 0,
            pointerEvents: "none",
            position: "fixed",
            zIndex: 12,
          }}
        >
          <polyline
            fill="none"
            points={[
              `${learningRouteOverlay.origin.x},${learningRouteOverlay.origin.y}`,
              ...learningRouteOverlay.stops.map((stop) => `${stop.x},${stop.y}`),
            ].join(" ")}
            stroke="rgba(214, 179, 97, 0.5)"
            strokeDasharray="8 10"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
          />
          {learningRouteOverlay.stops.map((stop, index) => (
            <g key={stop.id} data-testid={`learning-route-marker-${index + 1}`}>
              <circle
                cx={stop.x}
                cy={stop.y}
                fill={stop.done ? "rgba(52, 211, 153, 0.7)" : stop.current ? "rgba(214, 179, 97, 0.9)" : "rgba(15, 23, 42, 0.82)"}
                opacity={stop.unavailable ? 0.48 : 1}
                r={stop.current ? 18 : 14}
                stroke={stop.unavailable ? "rgba(251, 191, 36, 0.5)" : "rgba(255, 255, 255, 0.24)"}
                strokeWidth={stop.current ? 2.5 : 1.5}
              />
              {stop.current ? (
                <circle
                  cx={stop.x}
                  cy={stop.y}
                  fill="none"
                  r={26}
                  stroke="rgba(214, 179, 97, 0.28)"
                  strokeWidth={3}
                />
              ) : null}
              <text
                fill="white"
                fontFamily='"Space Grotesk", sans-serif'
                fontSize={12}
                fontWeight={600}
                textAnchor="middle"
                x={stop.x}
                y={stop.y + 4}
              >
                {index + 1}
              </text>
            </g>
          ))}
        </svg>
      ) : null}

      <StarDetailsPanel
        open={starDetailsOpen}
        onOpenChange={handleStarDetailsOpenChange}
        star={detailsStar}
        entryMode={starDetailsMode}
        closeLockedUntil={starDetailCloseLockedUntil}
        availableIndexes={availableIndexes}
        indexesLoading={indexesLoading}
        onIndexBuilt={handleIndexBuilt}
        onUpdateStar={updateUserStarById}
        onRemoveStar={handleDeleteStarAndSources}
        onOpenChat={openChatWithIndex}
        learningRoutePreview={activeLearningRoutePreview}
        learningRouteLoading={learningRouteLoading}
        learningRouteError={learningRouteError}
        onStartCourse={handleStartCourse}
        onSaveLearningRoutePreview={handleSaveLearningRoutePreview}
        onDiscardLearningRoutePreview={clearLearningRoutePreview}
        onRegenerateLearningRoute={handleRegenerateLearningRoute}
        onLaunchLearningRouteStep={handleLaunchLearningRouteStep}
        onSetLearningRouteStepStatus={handleSetLearningRouteStepStatus}
      />


      {/* Star tooltip card */}
      <div ref={starTooltipCardRef} className="metis-star-tooltip" id="starTooltipCard">
        <div ref={starTooltipDomainRef} className="metis-star-tooltip-domain" />
        <div ref={starTooltipTitleRef} className="metis-star-tooltip-title" />
        <div ref={starTooltipDescRef} className="metis-star-tooltip-desc" />
        <div className="metis-star-tooltip-actions">
          <button
            type="button"
            className="metis-star-tooltip-action"
            onClick={handleOpenHoveredStarDetails}
            disabled={!hoveredUserStarId}
          >
            Open Star Details
          </button>
          <button
            type="button"
            className="metis-star-tooltip-action danger"
            onClick={handleRemoveHoveredStar}
            disabled={!hoveredUserStarId}
          >
            Remove star
          </button>
        </div>
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
.metis-starfield-webgl {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 1;
  pointer-events: none;
}

.metis-universe {
  position: fixed; top: 0; left: 0;
  width: 100vw; height: 100vh; z-index: 2;
  background: transparent;
  cursor: crosshair;
  touch-action: none;
}

.metis-universe[data-canvas-tool="grab"] {
  cursor: grab;
}

.metis-universe[data-pan-active="true"] {
  cursor: grabbing;
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
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  text-align: left;
}

.metis-toast.error {
  border-color: rgba(255,120,120,0.35);
  color: rgba(255,214,214,0.98);
}

.metis-toast__message {
  flex: 1;
}

.metis-toast__action {
  flex-shrink: 0;
  border: 1px solid rgba(232,184,74,0.24);
  background: rgba(28, 40, 72, 0.76);
  color: rgba(255,245,221,0.96);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}

.metis-toast__action:hover {
  transform: translateY(-1px);
  border-color: rgba(232,184,74,0.38);
  background: rgba(34, 49, 88, 0.88);
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
  max-width: 560px;
  opacity: 1;
  transform: translateY(0);
  transition:
    opacity 220ms ease,
    transform 360ms cubic-bezier(0.16, 1, 0.3, 1);
  will-change: opacity, transform;
}
.metis-hero-shell.is-muted {
  opacity: 0;
  transform: translateY(14px);
}
.metis-zoom-pill {
  position: fixed;
  left: 50%;
  bottom: 28px;
  transform: translateX(-50%);
  z-index: 140;
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
  min-width: 0;
  max-width: calc(100vw - 120px);
  padding: 9px 10px 9px 16px;
  border-radius: 999px;
  border: 1px solid rgba(200,210,225,0.12);
  background:
    linear-gradient(180deg, rgba(17,22,36,0.82), rgba(8,12,22,0.9)),
    radial-gradient(circle at left center, rgba(232,184,74,0.14), rgba(232,184,74,0) 38%),
    radial-gradient(circle at right center, rgba(148,153,239,0.14), rgba(148,153,239,0) 48%);
  box-shadow: 0 18px 40px rgba(0,0,0,0.26);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  opacity: 1;
  transition:
    opacity 180ms ease,
    transform 340ms cubic-bezier(0.16, 1, 0.3, 1);
  pointer-events: none;
  will-change: opacity, transform;
}
.metis-zoom-pill.is-muted {
  opacity: 0;
  transform: translateX(-50%) translateY(12px) scale(0.97);
  pointer-events: none;
}
.metis-zoom-pill-value {
  font-family: 'Outfit', sans-serif;
  font-size: clamp(18px, 2vw, 24px);
  line-height: 1;
  color: rgba(240,244,255,0.96);
  letter-spacing: -0.05em;
  flex-shrink: 0;
  white-space: nowrap;
}
.metis-zoom-pill-tools {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 6px;
}
.metis-zoom-pill-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 6px;
}
.metis-zoom-pill-btn {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(200,210,225,0.14);
  background: rgba(19, 28, 54, 0.58);
  color: rgba(236,241,250,0.92);
  border-radius: 999px;
  padding: 0;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.02em;
  cursor: pointer;
  pointer-events: auto;
  transition: border-color 0.24s ease, color 0.24s ease, transform 0.24s ease, background 0.24s ease;
}
.metis-zoom-pill-tool-btn {
  width: auto;
  min-width: 56px;
  padding: 0 12px;
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.metis-zoom-pill-tool-btn.is-active {
  border-color: rgba(232,184,74,0.34);
  color: rgba(255,246,222,0.98);
  background: rgba(36, 48, 88, 0.82);
  box-shadow: inset 0 0 0 1px rgba(232,184,74,0.08);
}
.metis-zoom-pill-btn:hover:not(:disabled) {
  border-color: rgba(232,184,74,0.34);
  color: rgba(255,246,222,0.96);
  transform: translateY(-1px);
  background: rgba(28, 39, 74, 0.72);
}
.metis-zoom-pill-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.metis-zoom-pill-btn-reset {
  width: auto;
  min-width: 44px;
  padding: 0 11px;
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
  animation: metis-fadeUp 1.2s ease 0.6s forwards;
  max-width: 560px; letter-spacing: -0.5px;
  margin-top: 0;
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

.metis-star-tooltip {
  position: fixed;
  z-index: 205;
  width: min(320px, calc(100vw - 32px));
  background: rgba(8, 12, 24, 0.94);
  border: 1px solid rgba(196,149,58,0.16);
  border-radius: 14px;
  padding: 16px 16px 14px;
  box-shadow: 0 16px 38px rgba(2, 5, 12, 0.5);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  display: none;
  opacity: 0;
  transform: translateY(8px) scale(0.97);
  transition: opacity 180ms ease, transform 220ms cubic-bezier(0.16, 1, 0.3, 1);
  pointer-events: auto;
}

.metis-star-tooltip.active {
  display: block;
  opacity: 1;
  transform: translateY(0) scale(1);
}

.metis-star-tooltip-domain {
  color: rgba(232,184,74,0.92);
  font-family: 'Space Grotesk', sans-serif;
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
}

.metis-star-tooltip-title {
  margin-top: 8px;
  color: var(--text-bright);
  font-family: 'Space Grotesk', sans-serif;
  font-size: 18px;
  line-height: 1.25;
}

.metis-star-tooltip-desc {
  margin-top: 10px;
  color: var(--text-mid);
  font-size: 12px;
  line-height: 1.65;
}

.metis-star-tooltip-actions {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.metis-star-tooltip-action {
  border: 1px solid rgba(200,210,225,0.2);
  background: rgba(22, 31, 58, 0.62);
  color: rgba(236,241,250,0.96);
  border-radius: 999px;
  padding: 7px 12px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  cursor: pointer;
  transition: border-color 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.metis-star-tooltip-action:hover:not(:disabled) {
  border-color: rgba(232,184,74,0.36);
  color: rgba(255,246,222,0.96);
  transform: translateY(-1px);
}

.metis-star-tooltip-action.danger {
  border-color: rgba(255,128,128,0.18);
  color: rgba(255,222,222,0.92);
  background: rgba(62, 24, 34, 0.56);
}

.metis-star-tooltip-action.danger:hover:not(:disabled) {
  border-color: rgba(255,128,128,0.34);
  color: rgba(255,238,238,0.98);
}

.metis-star-tooltip-action:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

@media (prefers-reduced-motion: reduce) {
  .metis-star-tooltip {
    transition: none;
  }
}

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
    align-items: flex-start;
    flex-direction: column;
  }

  .metis-zoom-pill {
    bottom: 84px;
    max-width: calc(100vw - 40px);
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
