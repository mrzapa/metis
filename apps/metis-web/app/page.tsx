"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useReducedMotion } from "motion/react";
import { MetisMark } from "@/components/brand";
import { NetworkAuditFirstRunCard } from "@/components/network-audit/first-run-card";
import { FirstRunBanner } from "@/components/home/first-run-banner";
import { ForgeStarsKeyboardNav } from "@/components/forge/forge-stars-keyboard-nav";
import { ShootingStarLayer } from "@/components/home/shooting-star-layer";
import {
  CosmicAtmosphere,
  type CosmicAtmosphereFocusFrame,
} from "@/components/home/cosmic-atmosphere";
import type { LandingStarfieldFrame, LandingWebglStar } from "@/components/home/landing-starfield-webgl.types";

const LandingStarfieldWebgl = dynamic(
  () =>
    import("@/components/home/landing-starfield-webgl").then(
      (m) => ({ default: m.LandingStarfieldWebgl }),
    ),
  { ssr: false, loading: () => null },
);
import { StarDetailsPanel } from "@/components/constellation/star-observatory-dialog";
import {
  CatalogueStarInspector,
  type CatalogueStarInspectorStar,
} from "@/components/constellation/catalogue-star-inspector";
import { CatalogueFilterPanel } from "@/components/constellation/catalogue-filter-panel";
import { HomeActionFab } from "@/components/home/home-action-fab";
import { AddStarDialog, type AddDecision } from "@/components/home/add-star-dialog";
import type { CatalogueFilterState } from "@/lib/star-catalogue";
import {
  CATALOGUE_FILTER_DEFAULT,
  CATALOGUE_FILTER_DIM_BRIGHTNESS,
  buildPromotedUserStarPayload,
  catalogueStarToConstellationPoint,
  decodeFilterFromHash,
  isCatalogueFilterActive,
  matchesCatalogueFilter,
  mergeFilterIntoHash,
} from "@/lib/star-catalogue";
import { BorderBeam } from "@/components/ui/border-beam";
import { useConstellationCamera } from "@/hooks/use-constellation-camera";
import { useStarFocusPhase, type StarFocusPhase } from "@/hooks/use-star-focus-phase";
import { useConstellationStars } from "@/hooks/use-constellation-stars";
import { useCometNews } from "@/hooks/use-news-comets";
import { deleteIndex, fetchBrainScaffold, fetchIndexes, fetchSettings, fetchStarClusters, previewLearningRoute, subscribeCompanionActivity } from "@/lib/api";
import type { BrainScaffoldEdge, BrainScaffoldResponse, StarClusterAssignment } from "@/lib/api";
import { noise2D } from "@/lib/simplex-noise";
import gsap from "gsap";
import type { CometData, CometEvent } from "@/lib/comet-types";
import {
  makeCometData,
  tickComet,
  drawComets as drawCometSprites,
  drawPolarisTendril,
  drawAbsorptionBurst,
} from "@/lib/constellation-comets";
import {
  drawCometHoverCard,
  drawPreparedLabel,
  findHoveredComet,
  prepareCometLabel,
  pruneCometLabelState,
  rectsOverlap,
  suppressCollidingLabels,
  tickHoverPersistence,
  type Rect as CometCardRect,
} from "@/lib/constellation-comet-labels";
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
  findStarDiveFocusTarget,
  getBackgroundCameraScale,
  getBackgroundViewportWorldBounds,
  getConstellationCameraScale,
  getFacultyColor,
  getAutoStarFaculty,
  getInfluenceColors,
  getPreviewConnectionNodes,
  getStarDiveFocusStrength,
  isAutonomousStar,
  inferConstellationFaculty,
  isAddableBackgroundStar,
  MAX_BACKGROUND_ZOOM_FACTOR,
  MIN_BACKGROUND_ZOOM_FACTOR,
  MOBILE_ADD_CANDIDATE_HIT_RADIUS_PX,
  mixConstellationColors,
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
import {
  deriveStarAnnotations,
  generateStellarProfile,
  type StarContentType,
  type StellarProfile,
} from "@/lib/landing-stars";
import { deriveUserStarContentType } from "@/lib/user-star-content-type";
import { buildLandingStarRenderPlan } from "@/lib/landing-stars/landing-star-lod";
import { generateNebulae, getCosmosSeed, nebulaPositionAt } from "@/lib/landing-nebulae";
import {
  getLandingStarInteractionHitRadius,
  getLandingStarSelectableApparentSize,
} from "@/lib/landing-stars/landing-star-interaction";
import {
  buildLandingStarSpatialHash,
  findClosestLandingStarHitTarget,
} from "@/lib/landing-stars/landing-star-spatial-index";
import { StarCatalogue, DEFAULT_CATALOGUE_CONFIG, generateStarName } from "@/lib/star-catalogue";
import type { CatalogueStar } from "@/lib/star-catalogue";
import {
  buildCanvasFont,
  measureSingleLineTextWidth,
  quantizeFontSize,
} from "@/lib/pretext-labels";
import {
  buildSemanticSearchState,
  buildSemanticShiftOffsets,
  type SemanticSearchState,
} from "@/lib/semantic-constellation";
import { getFacultyArtDefinition } from "@/lib/constellation-faculty-art";
import type {
  IndexBuildResult,
  IndexSummary,
  LearningRoutePreviewRequest,
} from "@/lib/api";
import { useForgeStars, type ForgeStar } from "@/lib/forge-stars";
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

// M24 Phase 3 — when true, user stars are placed using embedding-cluster
// projections fetched from `GET /v1/stars/clusters`. When false, the
// legacy faculty-anchored layout is used. TODO(M24-Task-3.4, deferred to
// post-Phase-4): once `AddStarDialog` lands and the 5 verified-TRUE
// faculty-anchor consumers (comet targeting, RAG pulse highlighting,
// showConceptAtNode click-to-add, focus camera + brain-graph activity,
// buildFacultyAnchoredPlacement seed) are migrated, delete this flag and
// the entire `FACULTY_CONCEPTS` placement path.
const USE_CLUSTER_PLACEMENT = true;

// Cluster coordinates from the backend are in [-1, 1] centred on the
// origin. UserStar.x/y is in [0, 1] centred on (0.5, 0.5). This factor
// scales the cluster output into the home-page coordinate system; we
// keep it well below 0.5 so projected stars stay clear of the canvas
// edges (the existing layout clamps to roughly [0.04, 0.96]).
const CLUSTER_COORD_SCALE = 0.4;

const FACULTY_CONCEPTS = CONSTELLATION_FACULTIES.map((faculty, index) => ({
  faculty,
  label: `Faculty ${String(index + 1).padStart(2, "0")}`,
  title: faculty.label,
  desc: faculty.description,
}));

// Audit item 8 (2026-04-25) consolidated three floating affordances on the
// home page into a single gold FAB (`HomeActionFab`). The catalogue-search
// overlay (top-right gold sparkle) was folded conceptually into Threads
// search; its landmark-name index lived here and has been removed alongside
// the overlay component itself. Reinstate from git history if you bring
// catalogue-search back as its own affordance.
const BACKGROUND_BUTTON_ZOOM_STEP = 1.8;
const BACKGROUND_TILE_PADDING_PX = 220;
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

type CanvasTool = "select" | "grab" | "add";
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
  hitRadius: number;
  screenX: number;
  screenY: number;
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

interface FacultyArtRenderState {
  errored: boolean;
  image: HTMLImageElement;
  loaded: boolean;
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
  profile: StellarProfile;
  catalogueName: string | null;
  apparentMagnitude: number;
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
  catalogueName?: string | null;
  profile: StellarProfile;
}

interface ProjectedUserStarRenderState {
  attachmentCount: number;
  dragging: boolean;
  fadeIn: number;
  /**
   * One-shot 0..1 flash applied during the spawn window — drives the
   * "ignition" feel by briefly bumping core + halo brightness right
   * after a star is added. Decays to 0 outside the spawn window.
   */
  spawnFlash: number;
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

/**
 * Camera focus state projected to screen-space for the 2D starfield shader.
 * Populated every frame while a star dive is in progress; consumed by
 * `landing-starfield-webgl` via the focus uniforms to drive depth-of-field
 * falloff around the focused star. Previously also fed the 3D
 * `StarDiveOverlay` sphere, which was retired in M02 Phase 5. The screen-
 * space projection is still required for the 2D focus falloff and stays here.
 */
interface StarDiveFocusView {
  screenX: number;
  screenY: number;
  focusStrength: number;
  profile: StellarProfile;
  starName?: string;
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

function clampToRange(value: number, min: number, max: number): number {
  if (value < min) {
    return min;
  }
  if (value > max) {
    return max;
  }
  return value;
}

function formatBackgroundZoom(zoomFactor: number): string {
  if (zoomFactor >= 10) {
    return `${Math.round(zoomFactor)}x`;
  }
  if (zoomFactor >= 1) {
    return `${zoomFactor.toFixed(1)}x`;
  }
  if (zoomFactor >= 0.1) {
    return `${zoomFactor.toFixed(2)}x`;
  }
  return `${zoomFactor.toFixed(3)}x`;
}

function buildStarInfluenceColors(star: Pick<UserStar, "primaryDomainId" | "relatedDomainIds">) {
  return getInfluenceColors(star.primaryDomainId, star.relatedDomainIds);
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
  clusterPositions?: ReadonlyMap<string, { x: number; y: number }> | null,
): Point {
  const previewPosition = previewPositions.get(starId);
  if (previewPosition) {
    return { x: previewPosition.x, y: previewPosition.y };
  }
  // M24 Phase 3 — when cluster placement is active and the star has a
  // cluster-projected position, use it as the anchor instead of the
  // persisted x/y. This is what swaps the constellation from
  // faculty-anchored to embedding-cluster-anchored layout.
  const clusterPosition = clusterPositions?.get(starId);
  if (clusterPosition) {
    return { x: clusterPosition.x, y: clusterPosition.y };
  }
  return { x: star.x, y: star.y };
}

/**
 * Linear progress 0..1 for a star's spawn animation.
 * Used as the input to easing functions below.
 */
function getStarSpawnLinear(
  star: Pick<UserStar, "createdAt">,
  nowMs: number,
): number {
  return Math.max(
    0,
    Math.min(1, (nowMs - star.createdAt) / USER_STAR_FADE_IN_DURATION_MS),
  );
}

/**
 * Star opacity curve. Eased with `expo.out` so a freshly-added star
 * pops into view fast and settles — replaces the previous linear ramp
 * that felt like a fade-in instead of an ignition.
 */
function getStarFadeProgress(star: Pick<UserStar, "createdAt">, nowMs: number): number {
  const t = getStarSpawnLinear(star, nowMs);
  if (t >= 1) return 1;
  return 1 - Math.pow(2, -10 * t);
}

/**
 * One-shot brightness flash applied to a star's core + halo during
 * spawn. Spikes to 1 during the first ~12% of the spawn window then
 * decays to 0 — gives the "ignition" feel without scaling geometry.
 * Returns 0 once the spawn window has elapsed.
 */
function getStarSpawnFlash(
  star: Pick<UserStar, "createdAt">,
  nowMs: number,
): number {
  const t = getStarSpawnLinear(star, nowMs);
  if (t >= 1) return 0;
  const peak = 0.12;
  if (t < peak) return t / peak;
  // Ease-out to zero across the rest of the window.
  const after = (t - peak) / (1 - peak);
  return Math.max(0, 1 - Math.pow(after, 2));
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

/**
 * M22 Phase 4 — resolve a cached fixed-UI element's bounding rect for
 * the hover-card safe-area clamp. Lazy: refreshes the cached ref if
 * the previous element got detached (HMR / re-mount). Returns null if
 * no element matches OR the rect is degenerate (zero area). Lives at
 * module scope so the per-frame render loop doesn't re-allocate the
 * closure each animation frame.
 */
function rectFromCachedElement(
  ref: { current: HTMLElement | null },
  selector: string,
): { x: number; y: number; w: number; h: number } | null {
  if (!ref.current || !document.body.contains(ref.current)) {
    ref.current = document.querySelector<HTMLElement>(selector);
  }
  if (!ref.current) return null;
  const r = ref.current.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) return null;
  return { x: r.left, y: r.top, w: r.width, h: r.height };
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
  // M22 Phase 2 — read prefers-reduced-motion once at the top of Home and
  // pipe into the canvas render loop via a ref so changes propagate without
  // re-running the loop's useEffect.
  const reducedMotion = useReducedMotion() ?? false;
  const reducedMotionRef = useRef(reducedMotion);
  useEffect(() => {
    reducedMotionRef.current = reducedMotion;
  }, [reducedMotion]);

  // M22 Phase 3+5 — hover state for the canvas-rendered comet card.
  // Mutated by the canvas pointermove handler; read by the render loop.
  // - cometId       : the currently-tracked comet, if any.
  // - cardBbox      : last drawn rect, used by pointerdown for click
  //                   hit-testing.
  // - lastSeenAtMs  : timestamp of the most recent pointermove that
  //                   found a comet under the cursor. The render loop
  //                   clears cometId after HOVER_PERSISTENCE_MS so the
  //                   card persists briefly after mouseleave (per the
  //                   design's "card persists ~600ms after mouseleave
  //                   to allow cursor transit toward the card").
  const cometHoverStateRef = useRef<{
    cometId: string | null;
    cardBbox: CometCardRect | null;
    lastSeenAtMs: number;
  }>({ cometId: null, cardBbox: null, lastSeenAtMs: 0 });
  // M22 Phase 3+4 — cache fixed-UI DOM refs so the render loop avoids
  // querySelector calls per frame. Each ref is set lazily on first
  // lookup and refreshed if the cached element is detached (e.g.
  // dev-mode HMR remount). The hover-card's clampToSafeArea reads
  // these rects each frame to keep the card from overlapping chrome.
  const zoomPillRef = useRef<HTMLElement | null>(null);
  const homeFabRef = useRef<HTMLElement | null>(null);
  const heroOverlayRef = useRef<HTMLElement | null>(null);

  // Comet-news: subscribe to live news events rendered as comets.
  // Start enabled to preserve the pre-settings-wiring UX, then reconcile to
  // the stored value (news_comets_enabled) once fetchSettings resolves.
  const [cometsEnabled, setCometsEnabled] = useState(true);
  useEffect(() => {
    let cancelled = false;
    fetchSettings()
      .then((settings) => {
        if (cancelled) return;
        const raw = settings["news_comets_enabled"];
        if (typeof raw === "boolean") setCometsEnabled(raw);
      })
      .catch(() => {
        // Keep the default-on fallback when the API is unreachable.
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const { comets: serverComets } = useCometNews(cometsEnabled);
  const serverCometsRef = useRef(serverComets);
  serverCometsRef.current = serverComets;

  const [addMessage, setAddMessage] = useState<string | null>(null);
  const [selectedUserStarId, setSelectedUserStarId] = useState<string | null>(null);
  const [starDetailsOpen, setStarDetailsOpen] = useState(false);
  // Atmosphere pulse token — bumped when the dialog opens after a dive
  // so the cosmic atmosphere fires an expanding ring at the focus
  // centre, bridging the dive → dialog transition visually.
  const [atmospherePulseToken, setAtmospherePulseToken] = useState(0);
  const [starDetailsMode, setStarDetailsMode] = useState<"new" | "existing">("new");
  const [pendingDetailStar, setPendingDetailStar] = useState<UserStar | null>(null);
  const [starDetailCloseLockedUntil, setStarDetailCloseLockedUntil] = useState(0);
  const focusPhaseHandle = useStarFocusPhase("idle");
  const starFocusPhase = focusPhaseHandle.phase;
  const [starDiveFocusStrength, setStarDiveFocusStrength] = useState(0);
  // M24 Phase 3 — cluster placement: fetch cluster assignments on mount and
  // store the resulting list. `null` means we haven't received a response
  // yet (loading); an empty array means we've received a response with no
  // assignments OR the request failed (graceful degrade — render falls
  // through to the legacy faculty-anchor layout in that case).
  const [clusters, setClusters] = useState<StarClusterAssignment[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetchStarClusters()
      .then((result) => {
        if (cancelled) return;
        setClusters(result);
      })
      .catch(() => {
        if (cancelled) return;
        setClusters([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  // Session-only override for the migration toast's "Undo" affordance
  // (Task 3.3). When set, we treat cluster placement as disabled until
  // the next page load — localStorage is *not* updated, so the next visit
  // still uses cluster placement.
  const [sessionDisableClusterPlacement, setSessionDisableClusterPlacement] =
    useState(false);
  // Map of star_id -> normalised (x, y) in the [0, 1] home-page coordinate
  // space, derived from the cluster API's [-1, 1] output. `null` while
  // clusters are loading or when the placement path is disabled, so
  // `getResolvedStarPoint` can fall through to the persisted star.x/y.
  const clusterPositions = useMemo<ReadonlyMap<string, { x: number; y: number }> | null>(() => {
    if (!USE_CLUSTER_PLACEMENT || sessionDisableClusterPlacement) return null;
    if (!clusters || clusters.length === 0) return null;
    const map = new Map<string, { x: number; y: number }>();
    for (const assignment of clusters) {
      map.set(assignment.star_id, {
        x: 0.5 + assignment.x * CLUSTER_COORD_SCALE,
        y: 0.5 + assignment.y * CLUSTER_COORD_SCALE,
      });
    }
    return map;
  }, [clusters, sessionDisableClusterPlacement]);
  // Ref mirror of clusterPositions so the canvas render-loop closure (which
  // is wrapped in a useEffect with stable deps) reads the latest map without
  // tearing down and rebuilding the loop on every cluster fetch.
  const clusterPositionsRef = useRef<ReadonlyMap<string, { x: number; y: number }> | null>(null);
  useEffect(() => {
    clusterPositionsRef.current = clusterPositions;
  }, [clusterPositions]);
  const [availableIndexes, setAvailableIndexes] = useState<IndexSummary[]>([]);
  const [indexesLoading, setIndexesLoading] = useState(true);
  const [indexLoadError, setIndexLoadError] = useState<string | null>(null);
  const [hoveredAddCandidateId, setHoveredAddCandidateId] = useState<string | null>(null);
  const [hoveredUserStarId, setHoveredUserStarId] = useState<string | null>(null);
  const [inspectedCatalogueStar, setInspectedCatalogueStar] =
    useState<CatalogueStarInspectorStar | null>(null);
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
  const [semanticQuery, setSemanticQuery] = useState("");
  const [semanticSearchExpanded, setSemanticSearchExpanded] = useState(false);
  // Audit item 8 (2026-04-25): the three previously-separate floating
  // affordances on the home page (chat bubble, semantic-search toggle,
  // catalogue-search sparkle) are consolidated into a single gold FAB
  // (`HomeActionFab`) with a radial menu. `fabOpen` controls the menu
  // visibility; `filterPanelOpen` gates the catalogue filter panel which
  // used to render unconditionally. `catalogueSearchExpanded`/`Query`
  // and `handleCatalogueSearchSelect` were dropped in the same pass —
  // catalogue search is no longer a separate affordance.
  const [fabOpen, setFabOpen] = useState(false);
  const [filterPanelOpen, setFilterPanelOpen] = useState(false);
  // M24 Phase 4 — AddStarDialog open state. Replaces the canvas-pick add
  // affordance: clicking +Add now opens the content-first dialog instead
  // of entering `tool === "add"` mode. The legacy canvas-pick branch
  // (lines ~5610–5664 here, plus ADD_CANDIDATE_HIT_RADIUS_PX) is now
  // unreachable but left in place per Phase 4 spec; Phase 6 deletes it.
  // TODO(M24-Task-3.4 + Phase-6): remove tool === "add" branch + ADD_CANDIDATE_HIT_RADIUS_PX
  const [addStarDialogOpen, setAddStarDialogOpen] = useState(false);
  const [catalogueFilterState, setCatalogueFilterState] = useState<CatalogueFilterState>(
    () => CATALOGUE_FILTER_DEFAULT,
  );
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const semanticSearchInputRef = useRef<HTMLInputElement>(null);
  const starTooltipCardRef = useRef<HTMLDivElement>(null);
  const starTooltipDomainRef = useRef<HTMLDivElement>(null);
  const starTooltipTitleRef = useRef<HTMLDivElement>(null);
  const starTooltipDescRef = useRef<HTMLDivElement>(null);
  const catalogueTooltipRef = useRef<HTMLDivElement>(null);
  const activeNodeRef = useRef(-1);
  const hoveredNodeRef = useRef(-1);
  const hoverStartRef = useRef(0);
  const hoverExpandedRef = useRef(false);
  const coarsePointerRef = useRef(false);
  const mouseRef = useRef({ x: -1000, y: -1000 });
  const userStarsRef = useRef<UserStar[]>(userStars);
  // M14 Phase 2b — active Forge techniques projected as canvas stars
  // in the Skills sector. Re-fetches on visibility-change so toggles
  // made elsewhere reflect when the user returns to the home page.
  const forgeStars = useForgeStars();
  const forgeStarsRef = useRef<ForgeStar[]>(forgeStars);
  const selectedUserStarIdRef = useRef<string | null>(selectedUserStarId);
  const hoveredUserStarIdRef = useRef<string | null>(hoveredUserStarId);
  const hoveredAddCandidateRef = useRef<StarData | null>(null);
  const armedAddCandidateIdRef = useRef<string | null>(null);
  const availableIndexesRef = useRef<IndexSummary[]>(availableIndexes);
  // M12 Phase 3 — current filter state, mirrored into a ref so the render
  // loop (which lives inside a single long-lived effect) can read the latest
  // value without remounting on every state update.
  const catalogueFilterStateRef = useRef<CatalogueFilterState>(catalogueFilterState);
  const scaffoldEdgesRef = useRef<BrainScaffoldEdge[]>([]);
  const scaffoldResponseRef = useRef<BrainScaffoldResponse | null>(null);
  // Smooth animated topology strength — GSAP tweens this from old→new value
  const topoStrengthAnimRef = useRef({ value: 0 });
  // Offscreen canvas for Polaris bloom composite
  const bloomCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const bloomCtxRef = useRef<CanvasRenderingContext2D | null>(null);
  const canvasBoundsRef = useRef<CanvasBounds>({
    left: 0,
    top: 0,
    right: 0,
    bottom: 0,
    width: 0,
    height: 0,
  });
  // Opt into spring-eased zoom. Linear lerp felt mechanical — the spring
  // gives the camera a small overshoot + settle so zoom changes carry
  // weight. Tuned for ~5-8% overshoot before settling. Dive-zone arcs
  // are unaffected (the spring branch only fires below the dive zoom
  // threshold).
  const constellationCamera = useConstellationCamera({ zoomSpring: true });
  const backgroundCameraOriginRef = constellationCamera.originRef;
  const backgroundCameraTargetOriginRef = constellationCamera.targetOriginRef;
  const backgroundZoomRef = constellationCamera.zoomRef;
  const backgroundZoomTargetRef = constellationCamera.zoomTargetRef;
  const starFocusPhaseRef = focusPhaseHandle.phaseRef;
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
    zoomScale: 0,
  });
  // Mirrored focus state consumed by CosmicAtmosphere's focus bloom.
  // Updated per-frame from `syncFocusUniformsForFrame` so the bloom
  // tracks the focused star without driving React re-renders.
  const atmosphereFocusFrameRef = useRef<CosmicAtmosphereFocusFrame>({
    centerX: 0,
    centerY: 0,
    strength: 0,
  });
  const optimisticIndexKeysRef = useRef<Set<string>>(new Set());
  const starDiveFocusedStarIdRef = useRef<string | null>(null);
  const starDiveFocusStrengthRef = useRef(0);
  // Hover spotlight — dims ambient stars when the user is inspecting one
  // of their own stars. Lower target (~0.4) than the dive focus so the
  // effect is "lean in" rather than full immersion. Tween-driven so the
  // spotlight fades in/out cleanly.
  const hoverFocusStrengthRef = useRef(0);
  const hoverFocusTweenRef = useRef<gsap.core.Tween | null>(null);
  const starDiveFocusWorldPosRef = useRef<Point | null>(null);
  const starDiveFocusProfileRef = useRef<StellarProfile | null>(null);
  const starDiveFocusNameRef = useRef<string | null>(null);
  const starDiveFocusViewRef = useRef<StarDiveFocusView | null>(null);
  const starDivePanSuppressedRef = useRef(false);
  const starTooltipHideTimeoutRef = useRef<number | null>(null);
  const toastDismissTimeoutRef = useRef<number | null>(null);
  const zoomInteractionTimeoutRef = useRef<number | null>(null);
  const dragPreviewPositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const ragPulseStateRef = useRef<HomeRagPulseState | null>(null);
  const starfieldRevisionRef = useRef(0);
  const learningRouteRequestIdRef = useRef(0);
  const semanticSearchStateRef = useRef<SemanticSearchState>({ active: false, links: [], matchedIds: new Set(), rankedIds: [] });
  const semanticOffsetAnimRef = useRef<Map<string, Point>>(new Map());
  const semanticOffsetTweensRef = useRef<Map<string, gsap.core.Tween>>(new Map());
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
    forgeStarsRef.current = forgeStars;
    // Bumping the starfield revision invalidates any cached star
    // catalogues that the renderer keeps; the same lever the
    // user-star sync above pulls.
    starfieldRevisionRef.current += 1;
  }, [forgeStars]);

  useEffect(() => {
    availableIndexesRef.current = availableIndexes;
    starfieldRevisionRef.current += 1;
  }, [availableIndexes]);

  useEffect(() => {
    selectedUserStarIdRef.current = selectedUserStarId;
  }, [selectedUserStarId]);

  useEffect(() => {
    hoveredUserStarIdRef.current = hoveredUserStarId;
    // Drive the hover-spotlight strength via GSAP so the dimming
    // ramps in/out smoothly. Skip while a dive is active so the dive's
    // own focus animation owns the uniforms.
    const reduced =
      typeof window !== "undefined"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const target = hoveredUserStarId ? 0.42 : 0;
    hoverFocusTweenRef.current?.kill();
    if (reduced) {
      hoverFocusStrengthRef.current = target;
      return;
    }
    hoverFocusTweenRef.current = gsap.to(hoverFocusStrengthRef, {
      current: target,
      duration: hoveredUserStarId ? 0.32 : 0.6,
      ease: hoveredUserStarId ? "power2.out" : "power2.inOut",
      overwrite: true,
    });
  }, [hoveredUserStarId]);

  // M12 Phase 3 — read URL hash on mount, restore filter state if present.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const decoded = decodeFilterFromHash(window.location.hash);
    if (isCatalogueFilterActive(decoded)) {
      setCatalogueFilterState(decoded);
    }
    // Mount-only — explicit empty deps; URL is the initial source of truth.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // M12 Phase 3 — sync filter state into the render-loop ref + URL hash.
  // Triggers a starfield revision bump so the next frame re-runs the dim pass.
  // `mergeFilterIntoHash` preserves unrelated hash segments (anchors like
  // `#build-map`, other persisted query keys) — only the `fams=`/`mag=`
  // pieces are owned by the filter.
  useEffect(() => {
    catalogueFilterStateRef.current = catalogueFilterState;
    starfieldRevisionRef.current += 1;
    if (typeof window === "undefined") return;
    const merged = mergeFilterIntoHash(window.location.hash, catalogueFilterState);
    const nextHash = merged.length > 0 ? `#${merged}` : "";
    if (window.location.hash !== nextHash) {
      // Use replaceState to avoid polluting browser history per slider tick.
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${window.location.search}${nextHash}`,
      );
    }
  }, [catalogueFilterState]);

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

  // M24 Phase 3 — one-time migration toast. Fires the first time a user
  // sees the constellation after cluster placement is enabled. Persists
  // a localStorage flag so subsequent visits stay quiet. The "Undo for
  // this session" action restores the legacy faculty-anchored layout
  // for the remainder of the tab; localStorage is *not* cleared, so
  // the next visit resumes cluster placement.
  const migrationToastFiredRef = useRef(false);
  useEffect(() => {
    if (migrationToastFiredRef.current) return;
    if (typeof window === "undefined") return;
    if (!USE_CLUSTER_PLACEMENT) return;
    if (sessionDisableClusterPlacement) return;
    if (!clusters || clusters.length === 0) return;
    if (userStars.length === 0) return;
    let alreadyMigrated = false;
    try {
      alreadyMigrated = window.localStorage.getItem("m24_layout_migrated_v1") !== null;
    } catch {
      // localStorage may be blocked (private mode); treat as migrated to
      // avoid re-firing the toast on every mount in that edge case.
      alreadyMigrated = true;
    }
    if (alreadyMigrated) {
      migrationToastFiredRef.current = true;
      return;
    }
    try {
      window.localStorage.setItem("m24_layout_migrated_v1", String(Date.now()));
    } catch {
      // Ignore — see comment above; we'll still fire once per session.
    }
    migrationToastFiredRef.current = true;
    showToast({
      tone: "default",
      message: "Your constellation has been re-laid out by content.",
      actionLabel: "Undo for this session",
      dismissMs: 8000,
      onAction: () => {
        setSessionDisableClusterPlacement(true);
      },
    });
  }, [clusters, sessionDisableClusterPlacement, showToast, userStars.length]);

  // M24 Phase 4 / Task 4.2 — onConfirm callback for AddStarDialog. The
  // dialog is purely presentational; this is where side effects land.
  //
  //  - kind === "create_new": call addUserStar with a placeholder
  //    coordinate (cluster placement will reposition it on next mount /
  //    cluster refresh) and the user's suggested label.
  //  - kind === "attach": no-op for the user-stars store today (the
  //    backend index-build endpoints + manifest-attach are reachable
  //    via the Star Observatory dialog and will be wired into this
  //    callback when file-upload + buildIndexStream from this entry
  //    point lands. For now the attach branch fires a toast so the
  //    user sees acknowledgement; full attach-content integration is
  //    Task 4.3 / file-extraction is Phase-6).
  //
  // Re-fetches clusters after a successful add so the new star animates
  // into its cluster on the next render frame.
  const handleAddStarConfirm = useCallback(
    async (decision: AddDecision) => {
      try {
        if (decision.kind === "create_new") {
          const label = decision.suggested_label?.trim() || undefined;
          // Placeholder placement — cluster recompute will move it.
          // Use a slight random offset so multiple new stars don't
          // collide while the cluster fetch is in flight.
          const created = await addUserStar({
            x: 0.5 + (Math.random() - 0.5) * 0.04,
            y: 0.5 + (Math.random() - 0.5) * 0.04,
            size: 0.9,
            label,
            stage: "seed",
          });
          if (!created) {
            showToast({
              tone: "error",
              message: "Couldn't add a new star — capacity reached or sync failed.",
              dismissMs: 3000,
            });
            return;
          }
          showToast({
            tone: "default",
            message: `${created.label ?? "New star"} added to your constellation.`,
            dismissMs: 2400,
          });
        } else {
          // attach
          showToast({
            tone: "default",
            message:
              "Attached. Open the star to upload files or build its index.",
            dismissMs: 2800,
          });
        }
      } catch (error) {
        showToast({
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Add failed. Try again or open the star manually.",
          dismissMs: 3200,
        });
      } finally {
        // Refresh cluster placement so the new star (if any) snaps into
        // its cluster on the next render. Best-effort — silent on error.
        fetchStarClusters()
          .then((next) => setClusters(next))
          .catch(() => {/* keep existing layout */});
      }
    },
    [addUserStar, showToast],
  );

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
    semanticOffsetTweensRef.current.forEach((tween) => tween.kill());
    semanticOffsetTweensRef.current.clear();
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
  const semanticSearchState = useMemo<SemanticSearchState>(
    () => buildSemanticSearchState(semanticQuery, userStars),
    [semanticQuery, userStars],
  );

  useEffect(() => {
    if (!semanticSearchExpanded) {
      return;
    }
    semanticSearchInputRef.current?.focus();
  }, [semanticSearchExpanded]);

  useEffect(() => {
    semanticSearchStateRef.current = semanticSearchState;
  }, [semanticSearchState]);

  useEffect(() => {
    const targetOffsets = buildSemanticShiftOffsets(userStarsRef.current, semanticSearchState);
    const offsetAnimMap = semanticOffsetAnimRef.current;
    const tweenMap = semanticOffsetTweensRef.current;
    const activeIds = new Set(userStarsRef.current.map((star) => star.id));

    offsetAnimMap.forEach((_offset, starId) => {
      if (activeIds.has(starId)) {
        return;
      }
      tweenMap.get(starId)?.kill();
      tweenMap.delete(starId);
      offsetAnimMap.delete(starId);
    });

    userStarsRef.current.forEach((star) => {
      const current = offsetAnimMap.get(star.id) ?? { x: 0, y: 0 };
      offsetAnimMap.set(star.id, current);
      tweenMap.get(star.id)?.kill();
      const target = targetOffsets.get(star.id) ?? { x: 0, y: 0 };
      const tween = gsap.to(current, {
        duration: semanticSearchState.active ? 0.86 : 0.62,
        ease: semanticSearchState.active ? "power3.out" : "power2.inOut",
        overwrite: true,
        x: target.x,
        y: target.y,
      });
      tweenMap.set(star.id, tween);
    });
  }, [semanticSearchState, userStars]);
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

    if (activeCanvasTool === "add") {
      if (starLimit !== null && userStars.length >= starLimit) {
        return "Constellation at capacity. Remove a star or reset the orbit to pull in another.";
      }
      if (hoveredAddCandidateId) {
        return "Field star acquired. Click once to claim it, then name it and attach sources.";
      }
      return "Add mode active. Hover an empty spot in the constellation, then click to place a new star.";
    }

    if (dragMessage) {
      return dragMessage;
    }

    if (starLimit !== null && userStars.length >= starLimit) {
      return "Constellation at capacity. Remove a star or reset the orbit to pull in another.";
    }

    if (hoveredAddCandidateId) {
      return "Field star acquired. Switch to Add mode to claim it.";
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
    const originPoint = getResolvedStarPoint(detailsStar, previewPositions, detailsStar.id, clusterPositions);
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
        ? getResolvedStarPoint(connectedStar, previewPositions, connectedStar.id, clusterPositions)
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
    clusterPositions,
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

  const setStarFocusPhaseValue = focusPhaseHandle.setPhase;

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
    } else {
      // Dive → dialog handoff: fire the atmosphere pulse so the dialog
      // reads as blooming out of the focused star rather than appearing
      // as a hard cut.
      setAtmospherePulseToken((n) => n + 1);
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

  /**
   * M12 Phase 4a — promote a catalogue star into the user's constellation.
   *
   * Bridges the catalogue's world-space (`wx/wy`) coordinate system into the
   * user-star normalised constellation-point (`x/y`) space. Prefers the
   * star's currently-projected screen position when available (so the
   * promoted star lands exactly where the user clicked, regardless of
   * parallax or zoom mid-frame). Falls back to a direct world→constellation
   * conversion when the star has been panned out of view since the
   * inspector opened.
   *
   * Phase 4a relaxes the adjacency gate: ANY catalogue star, including
   * distant field stars and any catalogue star while the user has zero
   * existing user stars (the "first star anywhere" onboarding case), can
   * be promoted from the inspector. The legacy adjacency-gated armed-tap /
   * immediate-promote path on the canvas is unchanged.
   */
  const handlePromoteCatalogueStar = useCallback(
    (inspected: CatalogueStarInspectorStar) => {
      const viewportWidth = canvasBoundsRef.current.width || window.innerWidth;
      const viewportHeight = canvasBoundsRef.current.height || window.innerHeight;
      const camera: BackgroundCameraState = {
        x: backgroundCameraOriginRef.current.x,
        y: backgroundCameraOriginRef.current.y,
        zoomFactor: backgroundZoomRef.current,
      };

      // Look up the live screen position from the render-loop ref, if the
      // star is still in the visible projection.
      const projected = visibleStarsRef.current.find(
        (star) => star.id === inspected.id,
      );
      const point = catalogueStarToConstellationPoint(
        {
          worldX: inspected.worldX,
          worldY: inspected.worldY,
          screenX: projected?.screenX ?? null,
          screenY: projected?.screenY ?? null,
        },
        { width: viewportWidth, height: viewportHeight, camera },
      );

      const inference = inferConstellationFaculty(point);
      const anchorStarId = (() => {
        if (userStarsRef.current.length === 0) return null;
        let nearest: { id: string; d: number } | null = null;
        for (const us of userStarsRef.current) {
          const d = Math.hypot(us.x - point.x, us.y - point.y);
          if (!nearest || d < nearest.d) nearest = { id: us.id, d };
        }
        return nearest && nearest.d <= USER_STAR_LINK_MAX_DISTANCE ? nearest.id : null;
      })();

      const payload = buildPromotedUserStarPayload({
        point,
        primaryDomainId: inference.primary.faculty.id,
        relatedDomainId: inference.bridgeSuggestion?.faculty.id ?? null,
        anchorStarId,
      });

      void addUserStar(payload).then((createdStar) => {
        if (!createdStar) {
          setAddMessage(
            starLimit !== null && userStarsRef.current.length >= starLimit
              ? `Star limit reached (${starLimit}/${starLimit}).`
              : "Unable to place another star right now.",
          );
          return;
        }
        showToast({
          dismissMs: 2400,
          message: anchorStarId
            ? "Star promoted from the catalogue and linked into your constellation."
            : "Star promoted from the catalogue. Its details are open.",
          tone: "default",
        });
        setAddMessage(null);
        openStarDetails(createdStar, "new");
      });

      setInspectedCatalogueStar(null);
    },
    [
      addUserStar,
      backgroundCameraOriginRef,
      backgroundZoomRef,
      canvasBoundsRef,
      openStarDetails,
      showToast,
      starLimit,
    ],
  );

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
      direction === "in"
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

  // Auto-refresh constellation when autonomous research completes a new star
  useEffect(() => {
    return subscribeCompanionActivity((event) => {
      if (
        event.source === "autonomous_research" &&
        event.state === "completed"
      ) {
        void refreshAvailableIndexes({ silent: true });
      }
    });
  }, [refreshAvailableIndexes]);

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

  // Fetch scaffold topology for semantic star wiring
  useEffect(() => {
    let cancelled = false;
    fetchBrainScaffold()
      .then((data) => {
        if (!cancelled) {
          scaffoldEdgesRef.current = data.scaffold_edges;
          scaffoldResponseRef.current = data;
          // Compute raw data strength and GSAP-tween to it for smooth visual transition
          const b0 = data.betti_0 ?? 0;
          const b1 = data.betti_1 ?? 0;
          const ec = data.scaffold_edges.length;
          const rawStrength = Math.min(1,
            Math.min(1, Math.max(0, (b0 - 1) / 5)) * 0.4 +
            Math.min(1, b1 / 3) * 0.35 +
            Math.min(1, ec / 12) * 0.25,
          );
          gsap.to(topoStrengthAnimRef.current, {
            value: rawStrength,
            duration: 1.8,
            ease: "power2.inOut",
          });
        }
      })
      .catch(() => {
        // Scaffold is optional — silently degrade
      });
    return () => { cancelled = true; };
  }, []);

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
    let ctx = canvas.getContext("2d");
    if (!ctx) return;

    let W = window.innerWidth;
    let H = window.innerHeight;
    // Cap DPR at 2 — beyond that the buffer cost outweighs visible gain on
    // canvases that already cover the whole viewport.
    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    const projectedUserStarTargets: ProjectedUserStarHitTarget[] = [];
    let projectedUserStarRenderState = new Map<string, ProjectedUserStarRenderState>();
    const projectedCandidateById = new Map<string, StarData>();
    let landingStarSpatialHash: LandingStarSpatialHash<LandingWorldStarRenderState> | null = null;

    function syncCanvasBounds() {
      const fallbackWidth = window.innerWidth;
      const fallbackHeight = window.innerHeight;
      const rect = canvas!.getBoundingClientRect();
      const width = rect.width || fallbackWidth;
      const height = rect.height || fallbackHeight;
      const left = rect.left ?? 0;
      const top = rect.top ?? 0;
      // Sample DPR live so pinch-zoom / window-drag-between-monitors keeps
      // the buffer crisp. Cap at 2 to bound memory.
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = width;
      H = height;
      canvas!.width = Math.round(width * dpr);
      canvas!.height = Math.round(height * dpr);
      canvas!.style.width = `${width}px`;
      canvas!.style.height = `${height}px`;
      // setTransform (not scale) — we own the matrix here, so re-apply
      // unconditionally on every resize to avoid compounding scales.
      // Guard for environments (JSDOM tests) that don't implement
      // setTransform on the canvas mock.
      if (typeof ctx?.setTransform === "function") {
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }
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

    backgroundZoomRef.current = clampBackgroundZoomFactor(backgroundZoomRef.current);
    backgroundZoomTargetRef.current = clampBackgroundZoomFactor(backgroundZoomTargetRef.current);

    /* nebulae — procedurally generated, seeded per user. */
    const cosmosSeed = getCosmosSeed();
    let nebulae = generateNebulae(cosmosSeed, W, H);

    /* Star catalogue – lazy initialisation inside this effect closure */
    const catalogue = new StarCatalogue(DEFAULT_CATALOGUE_CONFIG, generateStellarProfile);

    const motionPreviewEnabled = document.documentElement.dataset.uiVariant === "motion";
    // Phase 7.3: track `prefers-reduced-motion` live so a user toggling the OS
    // preference mid-session halts the ongoing pulses without a reload. All
    // per-frame reads below close over these `let` bindings; the mediaquery
    // change handler below mutates them in place.
    let reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let enhancedHoverMotion = motionPreviewEnabled && !reducedMotion;
    coarsePointerRef.current = window.matchMedia("(pointer: coarse)").matches;
    const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handleReducedMotionChange = (event: MediaQueryListEvent) => {
      reducedMotion = event.matches;
      enhancedHoverMotion = motionPreviewEnabled && !reducedMotion;
    };
    if (typeof reducedMotionQuery.addEventListener === "function") {
      reducedMotionQuery.addEventListener("change", handleReducedMotionChange);
    } else {
      reducedMotionQuery.addListener(handleReducedMotionChange);
    }

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
      const conceptPoint: Point = { x: c.faculty.x, y: c.faculty.y };
      const autoAnchor = getNearestUserStar(conceptPoint);
      void addUserStar({
        x: c.faculty.x,
        y: c.faculty.y,
        size: 0.82 + Math.random() * 0.55,
        primaryDomainId: c.faculty.id,
        connectedUserStarIds: autoAnchor ? [autoAnchor.id] : undefined,
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
    const facultyArtImages = new Map<string, FacultyArtRenderState>();
    CONSTELLATION_FACULTIES.forEach((faculty) => {
      const art = getFacultyArtDefinition(faculty.id);
      if (!art) {
        return;
      }

      const image = new Image();
      const renderState: FacultyArtRenderState = {
        errored: false,
        image,
        loaded: false,
      };

      image.decoding = "async";
      image.onload = () => {
        renderState.loaded = true;
      };
      image.onerror = () => {
        renderState.errored = true;
      };
      image.src = art.src;
      facultyArtImages.set(faculty.id, renderState);
    });

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

    /* comets — news items rendered as comets across the constellation */
    const cometSprites: CometData[] = [];
    const absorbBursts: { x: number; y: number; color: [number, number, number]; startedAt: number }[] = [];
    /** Reconcile server-side comet events into the closure-scoped cometSprites array. */
    function syncComets(serverComets: CometEvent[]) {
      const existing = new Set(cometSprites.map((c) => c.comet_id));
      for (const evt of serverComets) {
        if (existing.has(evt.comet_id)) continue;
        // Find the target faculty node position
        const targetNode = nodes.find((n) => n.concept.faculty.id === evt.faculty_id);
        const tx = targetNode ? targetNode.x : W / 2;
        const ty = targetNode ? targetNode.y : H / 2;
        const color = getFacultyColor(evt.faculty_id);
        cometSprites.push(makeCometData(evt, W, H, color, tx, ty));
      }
      // Remove comets no longer on server (dismissed/absorbed externally)
      const serverIds = new Set(serverComets.map((c) => c.comet_id));
      for (let i = cometSprites.length - 1; i >= 0; i--) {
        if (!serverIds.has(cometSprites[i].comet_id) && cometSprites[i].phase !== "fading" && cometSprites[i].phase !== "absorbed") {
          cometSprites[i].phase = "fading";
          cometSprites[i].phaseStartedAt = performance.now();
        }
      }
    }

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
    let lastVisibleWorldZoom = Number.NaN;
    let visibleWorldStars: WorldStarData[] = [];
    const visibleStarNameMap = new Map<string, string | null>();
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

    function getCachedStellarProfile(
      starId: string,
      contentType: StarContentType | null = null,
    ): StellarProfile {
      // Include content type in the cache key so a user star whose content
      // type changes (e.g. a learning route is attached) re-derives a fresh
      // archetype on next read instead of returning a stale profile.
      const cacheKey = `${starId}|${contentType ?? ""}`;
      const cachedProfile = landingStarProfileCacheRef.current.get(cacheKey);
      if (cachedProfile) {
        return cachedProfile;
      }

      const nextProfile = generateStellarProfile(starId, { contentType });
      landingStarProfileCacheRef.current.set(cacheKey, nextProfile);
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
      candidate: Pick<StarData, "screenX" | "screenY">,
      backgroundCamera: BackgroundCameraState,
    ): Point {
      return screenToConstellationPoint(
        {
          x: candidate.screenX,
          y: candidate.screenY,
        },
        W,
        H,
        backgroundCamera,
      );
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
        clusterPositionsRef.current,
      );
      const distance = Math.hypot(selectedPoint.x - candidatePoint.x, selectedPoint.y - candidatePoint.y);
      if (distance > USER_STAR_LINK_MAX_DISTANCE) {
        return null;
      }

      return selectedStar;
    }

    /** Find the nearest existing user star to auto-link when no anchor is explicitly selected. */
    function getNearestUserStar(candidatePoint: Point): UserStar | null {
      const existing = userStarsRef.current;
      if (existing.length === 0) return null;
      let nearest: UserStar | null = null;
      let nearestDist = Infinity;
      for (const star of existing) {
        const p = getResolvedStarPoint(star, dragPreviewPositionsRef.current, star.id, clusterPositionsRef.current);
        const d = Math.hypot(p.x - candidatePoint.x, p.y - candidatePoint.y);
        if (d < nearestDist) {
          nearestDist = d;
          nearest = star;
        }
      }
      return nearest;
    }

    /**
     * Compute the WebGL focus uniforms (centre, strength, radius,
     * falloff) for the current frame. Drives the depth-of-field-like
     * dim/spotlight on the ambient star field. Star dive always wins;
     * the hover spotlight is the fallback when no dive is active.
     *
     * Pulled out of `refreshVisibleStars` so it runs every frame —
     * the spotlight tween needs to drive uniforms continuously even
     * when the camera is settled and the visible-star rebuild gate
     * blocks the rest of the frame work.
     */
    function computeFocusUniforms(viewportW: number, viewportH: number): {
      centerX: number;
      centerY: number;
      strength: number;
      radius: number;
      falloff: number;
    } {
      const diveView = starDiveFocusViewRef.current;
      let strength = diveView ? diveView.focusStrength : 0;
      let centerX = diveView ? diveView.screenX : 0;
      let centerY = diveView ? diveView.screenY : 0;
      if (!diveView && hoverFocusStrengthRef.current > 0.01) {
        const hoveredId = hoveredUserStarIdRef.current;
        const hoveredState = hoveredId
          ? projectedUserStarRenderState.get(hoveredId)
          : null;
        if (hoveredState) {
          strength = hoverFocusStrengthRef.current;
          centerX = hoveredState.target.x;
          centerY = hoveredState.target.y;
        }
      }
      const minViewportDim = Math.min(viewportW, viewportH);
      // Focus sharp-zone shrinks as the strength climbs so more ambient
      // stars drift into bokeh; widen from ~40% down to ~12%.
      const radius = minViewportDim * (0.4 - 0.28 * strength);
      const falloff = minViewportDim * 0.55;
      return { centerX, centerY, strength, radius, falloff };
    }

    /**
     * Compute mouse-driven parallax offset for the WebGL backdrop.
     * Returns a small (x, y) shift in shader-space pixels that the
     * vertex shader subtracts (scaled per tier) so background stars
     * appear to drift opposite to the cursor — fakes 3D depth without
     * any geometry change. Disabled under reduced motion.
     */
    function computeMouseParallax(
      viewportW: number,
      viewportH: number,
      reducedMotionFlag: boolean,
    ): { x: number; y: number } {
      if (reducedMotionFlag) return { x: 0, y: 0 };
      // Sentinel guard — `mouse` is initialized to {-1000, -1000} until
      // the first pointermove fires. Coarse / touch-only sessions and
      // initial renders never see a real position; treating that as a
      // valid offset would clamp the parallax to its maximum and leave
      // the WebGL backdrop permanently shifted (Codex review on PR
      // #568). Bail to zero parallax until we actually see the pointer
      // inside the viewport.
      if (
        mouse.x < 0
        || mouse.y < 0
        || mouse.x > viewportW
        || mouse.y > viewportH
      ) {
        return { x: 0, y: 0 };
      }
      // Normalize the cursor offset from centre to roughly -1..1 across
      // the viewport diagonal, then scale to produce a max ~12px shift
      // on the field tier (which receives the full parallax). Sprite,
      // hero, and closeup tiers attenuate this in the vertex shader.
      const half = Math.max(viewportW, viewportH) * 0.5 || 1;
      const PARALLAX_MAX_PX = 14;
      const dx = ((mouse.x - viewportW * 0.5) / half) * PARALLAX_MAX_PX;
      const dy = ((mouse.y - viewportH * 0.5) / half) * PARALLAX_MAX_PX;
      // Clamp so corner-of-screen mouse positions don't punch the shift
      // outside the intended envelope.
      const clamp = (v: number) =>
        v < -PARALLAX_MAX_PX
          ? -PARALLAX_MAX_PX
          : v > PARALLAX_MAX_PX
            ? PARALLAX_MAX_PX
            : v;
      return { x: clamp(dx), y: clamp(dy) };
    }

    /**
     * Apply the latest focus uniforms to the WebGL frame ref without
     * rebuilding the whole frame. Cheap — does not bump revision, so
     * the WebGL geometry pass is skipped. Runs every animation frame
     * so the hover-spotlight tween reaches the GPU at every step.
     */
    function syncFocusUniformsForFrame(viewportW: number, viewportH: number) {
      const frame = landingStarfieldFrameRef.current;
      if (!frame) return;
      const focus = computeFocusUniforms(viewportW, viewportH);
      frame.focusCenterX = focus.centerX;
      frame.focusCenterY = focus.centerY;
      frame.focusStrength = focus.strength;
      frame.focusRadius = focus.radius;
      frame.focusFalloff = focus.falloff;
      // Mirror to the atmosphere bloom ref so the CSS overlay tracks
      // the focused star centre. Single shared source of truth — the
      // ref is read by CosmicAtmosphere's internal RAF.
      const atmFocus = atmosphereFocusFrameRef.current;
      atmFocus.centerX = focus.centerX;
      atmFocus.centerY = focus.centerY;
      atmFocus.strength = focus.strength;
      // Mouse parallax also lives outside the geometry-rebuild gate so
      // pointer moves on a settled camera still translate field stars.
      const parallax = computeMouseParallax(viewportW, viewportH, reducedMotion);
      frame.mouseParallaxX = parallax.x;
      frame.mouseParallaxY = parallax.y;
    }

    function refreshVisibleStars(backgroundCamera: BackgroundCameraState) {
      const worldBounds = getBackgroundViewportWorldBounds(
        W,
        H,
        backgroundCamera,
        BACKGROUND_TILE_PADDING_PX,
      );

      /* Magnitude-based reveal: brightest stars (mag≈0) visible from galaxy zoom (0.002×),
         faintest stars (mag≈6.5) only appear around zoom 5–6×.
         Formula: revealZoom = 10^(mag × 0.7 − 3.5)
           mag 0   → 10^−3.5 ≈ 0.0003  → visible from 0.002× ✓
           mag 3   → 10^−1.4 ≈ 0.04    → visible from 0.04×
           mag 6.5 → 10^+1.05 ≈ 11     → visible from ~11× */
      const zoomFactor = backgroundCamera.zoomFactor;
      const shouldRebuildVisibleWorldStars =
        lastVisibleStarfieldRevision !== starfieldRevisionRef.current
        || Math.abs(lastVisibleWorldZoom - zoomFactor) > 0.001;

      if (shouldRebuildVisibleWorldStars) {
        const catStars = catalogue.getVisibleStars(
          worldBounds.left,
          worldBounds.right,
          worldBounds.top,
          worldBounds.bottom,
          1,
        );
        const nextVisibleWorldStars: WorldStarData[] = [];

        for (let i = 0; i < catStars.length; i++) {
          const cat = catStars[i];
          const mag = cat.apparentMagnitude;
          const revealZoomFactor = Math.pow(10, mag * 0.7 - 3.5);
          if (zoomFactor + 1e-6 < revealZoomFactor) continue;

          const layer = cat.depthLayer < 0.33 ? 2 : cat.depthLayer < 0.66 ? 1 : 0;
          const brightness = 0.15 + (1 - mag / 6.5) * 0.72;
          const baseSize = 0.3 + (1 - mag / 6.5) * 2.2;
          const twinkle = mag > 2;
          const twinkleSpeed = 0.002 + (cat.profile.visual?.twinkleSpeed ?? 0.004);
          const twinklePhase = cat.profile.visual?.twinklePhase ?? 0;
          const hasDiffraction = layer <= 1 && baseSize > 1.25 && mag < 3;

          nextVisibleWorldStars.push({
            id: cat.id,
            worldX: cat.wx,
            worldY: cat.wy,
            layer,
            baseSize,
            brightness,
            twinkle,
            twinkleSpeed,
            twinklePhase,
            parallaxFactor: layer === 0 ? 0.026 : layer === 1 ? 0.013 : 0.006,
            hasDiffraction,
            revealZoomFactor,
            profile: cat.profile,
            catalogueName: cat.name,
            apparentMagnitude: mag,
          });
        }

        visibleWorldStars = nextVisibleWorldStars;
        lastVisibleWorldZoom = zoomFactor;
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
      const visibleStarProfiles = new Map<string, StellarProfile>();
      // M12 Phase 3 — id → { profile, apparentMagnitude } for the filter pass.
      // Built alongside the existing visibleStarProfiles map below.
      const visibleStarFilterMap = new Map<string, { profile: StellarProfile; apparentMagnitude: number }>();

      // Pan parallax — background layers drift slower than foreground.
      // Layer 0 = closest (full camera follow), layer 2 = farthest
      // (~74% follow). Gives the cosmos a felt sense of depth on pan
      // without touching zoom (foreground/background still scale
      // together so the relative size hierarchy stays intact).
      const PARALLAX_FOLLOW = [1, 0.86, 0.74] as const;
      visibleWorldStars.forEach((worldStar) => {
        const follow =
          PARALLAX_FOLLOW[worldStar.layer] ?? PARALLAX_FOLLOW[0];
        const screenX = (worldStar.worldX - backgroundCamera.x * follow) * scale + W / 2;
        const screenY = (worldStar.worldY - backgroundCamera.y * follow) * scale + H / 2;

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
        const interactionStar = {
          apparentSize: projectedSize,
          brightness,
          id: worldStar.id,
          x: screenX,
          y: screenY,
        };
        const hitRadius = getLandingStarInteractionHitRadius(
          interactionStar,
          backgroundCamera.zoomFactor,
        );
        const selectableApparentSize = getLandingStarSelectableApparentSize(
          interactionStar,
          backgroundCamera.zoomFactor,
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
          hitRadius,
          screenX,
          screenY,
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
        star.hitRadius = hitRadius;
        star.screenX = screenX;
        star.screenY = screenY;
        const hasLinkedSourceContent = userStarsRef.current.some(
          (userStar) => getStarManifestPaths(userStar).length > 0,
        );
        // Allow star adding if the user has any available index (even from prior sessions),
        // not just one built in the current session — restores the ability to add the first
        // star when indexes exist but no user stars have been mapped yet.
        const hasUserContent = hasLinkedSourceContent
          || hasSessionIndexedContentRef.current
          || availableIndexesRef.current.length > 0;
        star.isAddable = isAddableBackgroundStar(
          {
            ...star,
            baseSize: selectableApparentSize,
          },
          allConstellationStarPx,
          projectedUserStars,
          W,
          H,
          hasUserContent,
        );
        nextVisibleStars[visibleStarCount] = star;
        visibleStarProfiles.set(worldStar.id, worldStar.profile);
        visibleStarFilterMap.set(worldStar.id, {
          profile: worldStar.profile,
          apparentMagnitude: worldStar.apparentMagnitude,
        });
        visibleStarNameMap.set(worldStar.id, worldStar.catalogueName);
        visibleStarCount += 1;
      });

      nextVisibleStars.length = visibleStarCount;
      projectedCandidateById.clear();

      // M12 Phase 3 — read latest filter state into a per-frame snapshot.
      // Dim factor is multiplicative with the existing star-dive focus dim;
      // stars failing the filter get scaled to CATALOGUE_FILTER_DIM_BRIGHTNESS,
      // matching ones stay at their natural brightness.
      const filterStateForFrame = catalogueFilterStateRef.current;
      const filterActiveForFrame = isCatalogueFilterActive(filterStateForFrame);

      const landingRenderableStars: LandingWorldStarRenderState[] = nextVisibleStars.map((star) => {
        const profile = visibleStarProfiles.get(star.id) ?? getCachedStellarProfile(star.id);
        const focusStr = starDiveFocusStrengthRef.current;
        const isFocused = starDiveFocusedStarIdRef.current === star.id;
        // Dim non-focused stars proportionally to focus strength
        const dimFactor = focusStr > 0 && !isFocused ? 1 - focusStr * 0.85 : 1;
        // Grow focused star toward ~60% of viewport height as focus strength → 1
        const focusedSizeBoost = isFocused && focusStr > 0
          ? star.baseSize + (H * 0.6 - star.baseSize) * focusStr
          : star.baseSize;

        let filterDimFactor = 1;
        if (filterActiveForFrame && !isFocused) {
          const worldData = visibleStarFilterMap.get(star.id);
          if (worldData && !matchesCatalogueFilter(worldData, filterStateForFrame)) {
            filterDimFactor = CATALOGUE_FILTER_DIM_BRIGHTNESS;
          }
        }

        const projectedStar: LandingWorldStarRenderState = {
          addable: star.isAddable,
          apparentSize: isFocused ? focusedSizeBoost : star.baseSize,
          brightness: star.brightness * dimFactor * filterDimFactor,
          catalogueName: visibleStarNameMap.get(star.id),
          hitRadius: star.hitRadius,
          id: star.id,
          profile,
          x: star.screenX,
          y: star.screenY,
        };

        if (star.isAddable) {
          projectedCandidateById.set(star.id, star);
        }

        return projectedStar;
      });
      const renderPlan = buildLandingStarRenderPlan(
        landingRenderableStars,
        backgroundCamera.zoomFactor,
        undefined,
        starDiveFocusedStarIdRef.current,
      );
      const flattenedRenderPlan = [
        ...renderPlan.batches.point,
        ...renderPlan.batches.sprite,
        ...renderPlan.batches.hero,
        ...renderPlan.batches.closeup,
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

      // Hash ALL renderable stars for interaction (hover/click), not just addable ones
      landingStarSpatialHash = landingRenderableStars.length > 0
        ? buildLandingStarSpatialHash(landingRenderableStars)
        : null;
      const zoomNorm = Math.log2(Math.max(0.002, backgroundCamera.zoomFactor) + 1) / Math.log2(2001);
      const focus = computeFocusUniforms(W, H);
      // Mouse parallax — pointer offset from viewport centre, scaled
      // down so even fast mouse moves only shift background stars by
      // ~12px. Reduced motion disables it entirely (skip computation
      // since the shader will subtract zero anyway).
      const parallax = computeMouseParallax(W, H, reducedMotion);
      landingStarfieldFrameRef.current = {
        height: H,
        revision: landingStarfieldFrameRef.current.revision + 1,
        stars: nextWebglStars,
        width: W,
        zoomScale: zoomNorm,
        focusCenterX: focus.centerX,
        focusCenterY: focus.centerY,
        focusStrength: focus.strength,
        focusRadius: focus.radius,
        focusFalloff: focus.falloff,
        mouseParallaxX: parallax.x,
        mouseParallaxY: parallax.y,
        reducedMotion,
      };
      lastVisibleStarfieldWidth = W;
      lastVisibleStarfieldHeight = H;
      lastVisibleStarfieldRevision = starfieldRevisionRef.current;
      lastVisibleStarfieldZoom = backgroundCamera.zoomFactor;
      lastVisibleStarfieldX = backgroundCamera.x;
      lastVisibleStarfieldY = backgroundCamera.y;
    }

    /**
     * Soft galactic spiral structure at the cosmic centre. Two
     * logarithmic-spiral arms wrap from the bright core outward,
     * each rendered as a chain of overlapping radial dust blobs that
     * trace the arm path. Combined with the warm core puff this
     * sells the "you're looking at a galaxy from inside" feel at low
     * zoom — replaces the previous flat elliptical band.
     *
     * Geometry: r(θ) = innerR * exp(b * θ) for two arms 180° apart.
     * Slow rotation around the core (period ~10min) so the arms
     * drift over time without ever obviously looping.
     *
     * Visibility envelope: full at zoom < 0.5, ramps down to 0 past
     * zoom 4× so closeup work isn't competing with it.
     */
    function drawGalacticSpiral(tMs: number, zoomFactor: number) {
      let envelope: number;
      if (zoomFactor < 0.5) envelope = 1;
      else if (zoomFactor < 4) envelope = 1 - (zoomFactor - 0.5) / 3.5;
      else envelope = 0;
      if (envelope < 0.02) return;

      const cx = W / 2 + (mouse.x - W / 2) * 0.003;
      const cy = H / 2 + (mouse.y - H / 2) * 0.003;
      // Slow rotation — one cycle per ~10 min. Arms drift across the
      // viewport without obviously looping.
      const rotation = (tMs / 600_000) * Math.PI * 2;

      // Spiral parameters tuned to feel Milky-Way-ish at default zoom.
      const innerRadius = Math.min(W, H) * 0.08;
      const outerRadius = Math.max(W, H) * 0.78;
      const armCount = 2;
      const blobsPerArm = 16;
      // Pitch in radians — controls how tight the arms wrap.
      const pitch = 0.34;

      // Slow ambient breath on the arms — period ~36s, ±9% amplitude.
      // Reads as "the galaxy has a heartbeat" without ever being
      // distracting. Galactic core gets the same modulation so the
      // structure pulses as a unit.
      const breath = 1 + Math.sin((tMs / 36_000) * Math.PI * 2) * 0.09;
      const armBaseAlpha = 0.12 * envelope * breath;

      for (let armIdx = 0; armIdx < armCount; armIdx++) {
        const armOffset = (armIdx / armCount) * Math.PI * 2;
        for (let i = 0; i < blobsPerArm; i++) {
          // t = 0 at the core, 1 at the outer tip of the arm.
          const t = i / (blobsPerArm - 1);
          // Logarithmic spiral: radius grows exponentially with angle.
          // Map t → angular sweep of ~2.6 radians per arm so arms
          // wrap roughly 150° from core to tip.
          const sweep = t * 2.6;
          const r =
            innerRadius
            + (outerRadius - innerRadius) * (1 - Math.exp(-sweep / pitch / 2.5)) / (1 - Math.exp(-2.6 / pitch / 2.5));
          const theta = armOffset + sweep + rotation;
          const x = cx + Math.cos(theta) * r;
          const y = cy + Math.sin(theta) * r;
          // Blobs are bigger but dimmer toward the outer arm; brightest
          // density mid-arm where the core dust meets the open arms.
          const blobRadius = Math.min(W, H) * (0.06 + t * 0.12);
          // Alpha falls off near the tip so arms don't hard-end; ramps
          // up briefly from the core so the inner band reads.
          const innerRamp = Math.min(1, t / 0.12);
          const tipFalloff = Math.max(0, 1 - Math.pow(Math.max(0, t - 0.55) / 0.45, 1.5));
          const alpha = armBaseAlpha * innerRamp * tipFalloff;
          if (alpha < 0.005) continue;

          // Cool blue-violet dust shading toward the outer rim, warmer
          // toward the core — matches the chromatic break of real
          // galaxy imagery.
          const warm = 1 - t; // 1 near core → 0 at tip
          const r0 = Math.round(120 + warm * 60);
          const g0 = Math.round(135 + warm * 30);
          const b0 = Math.round(220 - warm * 20);

          const grad = ctx!.createRadialGradient(x, y, 0, x, y, blobRadius);
          grad.addColorStop(0, `rgba(${r0}, ${g0}, ${b0}, ${alpha})`);
          grad.addColorStop(0.5, `rgba(${r0}, ${g0}, ${b0}, ${alpha * 0.45})`);
          grad.addColorStop(1, "rgba(0,0,0,0)");
          ctx!.fillStyle = grad;
          ctx!.beginPath();
          ctx!.arc(x, y, blobRadius, 0, Math.PI * 2);
          ctx!.fill();
        }
      }

      // Galactic core — small bright puff anchored at the centre.
      // Drawn after the arms so the core sits cleanly on top of any
      // arm dust that intersects the centre region. Same breath as
      // the arms so the galaxy modulates as a unit.
      const coreAlpha = 0.32 * envelope * breath;
      const coreRadius = Math.min(W, H) * 0.13;
      const coreGrad = ctx!.createRadialGradient(cx, cy, 0, cx, cy, coreRadius);
      coreGrad.addColorStop(0, `rgba(255, 226, 178, ${coreAlpha})`);
      coreGrad.addColorStop(0.32, `rgba(195, 168, 232, ${coreAlpha * 0.45})`);
      coreGrad.addColorStop(0.7, `rgba(80, 110, 180, ${coreAlpha * 0.18})`);
      coreGrad.addColorStop(1, "rgba(0,0,0,0)");
      ctx!.fillStyle = coreGrad;
      ctx!.beginPath();
      ctx!.arc(cx, cy, coreRadius, 0, Math.PI * 2);
      ctx!.fill();
    }

    function drawNebulae(tMs: number) {
      const tSec = tMs / 1000;
      nebulae.forEach(n => {
        const drifted = nebulaPositionAt(n, tSec);
        // Subtle parallax response to the cursor preserved from the
        // previous renderer — keeps the nebulae feeling slightly
        // depth-aware when the user moves the mouse.
        const nx = drifted.x + (mouse.x - W / 2) * 0.005;
        const ny = drifted.y + (mouse.y - H / 2) * 0.005;
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
      const animatedSemanticOffsets = semanticOffsetAnimRef.current;
      projectedUserStarTargets.length = 0;
      projectedUserStarRenderState = new Map();

      userStarsRef.current.forEach((star) => {
        const resolvedPoint = getResolvedStarPoint(star, previewPositions, star.id, clusterPositionsRef.current);
        const easedOffset = animatedSemanticOffsets.get(star.id) ?? { x: 0, y: 0 };
        const [shiftedX, shiftedY] = clampPointToOrbit(
          resolvedPoint.x + easedOffset.x,
          resolvedPoint.y + easedOffset.y,
        );
        const shiftedPoint = { x: shiftedX, y: shiftedY };
        const faculty = resolveStarFaculty({
          x: shiftedPoint.x,
          y: shiftedPoint.y,
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
            x: shiftedPoint.x,
            y: shiftedPoint.y,
            size: star.size,
          },
          W,
          H,
          backgroundCamera,
          coarsePointerRef.current ? 12 : 0,
          mouse,
        );

        projectedUserStarTargets.push(target);
        const cachedStellarProfile = getCachedStellarProfile(
          star.id,
          deriveUserStarContentType(star),
        );
        // Phase 6 — layer user-star annotations (halo / ring / satellites)
        // onto the stellar profile copy used for rendering. The cache
        // entry itself stays profile-pure; we spread a shallow copy
        // so successive frames do not accumulate stale annotations.
        const userStarAnnotations = deriveStarAnnotations(star);
        const stellarProfileForRender: StellarProfile = userStarAnnotations
          ? { ...cachedStellarProfile, annotations: userStarAnnotations }
          : cachedStellarProfile;
        projectedUserStarRenderState.set(star.id, {
          attachmentCount: getStarAttachmentCount(star),
          dragging: dragStateRef.current?.starId === star.id && dragStateRef.current.moved,
          fadeIn: getStarFadeProgress(star, renderTimeMs),
          spawnFlash: getStarSpawnFlash(star, renderTimeMs),
          influenceColors,
          mixed,
          profile: createUserStarVisualProfile(star.id),
          ringCount: getStageRingCount(star.stage),
          selected: currentSelectedStarId === star.id,
          star,
          stellarProfile: stellarProfileForRender,
          target,
        });
      });
    }

    function drawUserStarEdges(ts: number) {
      const currentUserStars = userStarsRef.current;
      if (currentUserStars.length === 0 || projectedUserStarRenderState.size === 0) {
        return;
      }

      // Lines between user stars are now *intent-driven*: they appear
      // when the user signals interest (hover, select, semantic search,
      // or RAG pulse) rather than rendering by default. The earlier
      // always-on web of faculty-anchor + connection + scaffold lines
      // read as decorative noise to new users; gating on intent makes
      // every line carry meaning. Per ADR 0006 the faculty cluster
      // metaphor is "nebula, no sharp core" — we lean into that by
      // keeping ambient stars uncluttered and revealing structure on
      // demand.
      const selectedStarId = selectedUserStarIdRef.current;
      const hoveredStarId = hoveredUserStarIdRef.current;
      const focusedStarId = selectedStarId ?? hoveredStarId;
      const renderTimeMs = getRenderEpochMs(ts);
      const ragPulseState = ragPulseStateRef.current;
      const ragPulseStrength = getHomeRagPulseStrength(ragPulseState, renderTimeMs);
      const edgeBreath = reducedMotion
        ? 1
        : 1 + USER_STAR_EDGE_BREATH_AMPLITUDE * Math.sin((Math.PI * 2 * ts) / USER_STAR_EDGE_BREATH_PERIOD_MS);
      const semanticState = semanticSearchStateRef.current;
      const semanticActive = semanticState.active && semanticState.links.length > 0;

      // No focus, no search, no pulse → no connecting lines. Skip the
      // whole pass; faculty constellation patterns are drawn elsewhere.
      if (!focusedStarId && !semanticActive && ragPulseStrength <= 0) {
        return;
      }

      // Build the set of "lit" star ids — these are the only stars whose
      // edges we'll render. A user-defined edge is shown when at least
      // one endpoint is lit; a scaffold edge follows the same rule.
      const litStarIds = new Set<string>();
      if (focusedStarId) {
        litStarIds.add(focusedStarId);
      }
      if (semanticActive) {
        for (const id of semanticState.matchedIds) litStarIds.add(id);
        for (const link of semanticState.links) {
          litStarIds.add(link.fromId);
          litStarIds.add(link.toId);
        }
      }
      if (ragPulseState && ragPulseStrength > 0) {
        for (const id of ragPulseState.starIds) litStarIds.add(id);
      }

      const renderedLinks = new Set<string>();

      // --- Focused star: thin faculty-tint anchor to its faculty hub.
      // Drawn only for the focused star (not every star) so the user
      // can see which faculty cluster their attention belongs to.
      if (focusedStarId) {
        const focusedStar = currentUserStars.find((s) => s.id === focusedStarId);
        const from = focusedStar ? projectedUserStarRenderState.get(focusedStar.id) : undefined;
        if (focusedStar?.primaryDomainId && from) {
          const facultyNode = nodes.find(
            (n) => n.concept.faculty.id === focusedStar.primaryDomainId,
          );
          if (facultyNode) {
            const [fr, fg, fb] = getFacultyColor(focusedStar.primaryDomainId);
            const alpha = 0.34 * Math.min(1, from.fadeIn);
            const grad = ctx!.createLinearGradient(
              from.target.x, from.target.y, facultyNode.x, facultyNode.y,
            );
            grad.addColorStop(0, `rgba(${fr},${fg},${fb},${alpha})`);
            grad.addColorStop(1, `rgba(${fr},${fg},${fb},${alpha * 0.25})`);
            ctx!.strokeStyle = grad;
            ctx!.lineWidth = 0.75;
            ctx!.setLineDash([4, 6]);
            ctx!.beginPath();
            ctx!.moveTo(from.target.x, from.target.y);
            ctx!.lineTo(facultyNode.x, facultyNode.y);
            ctx!.stroke();
            ctx!.setLineDash([]);
          }
        }
      }

      // --- Inter-star edges (user-defined connections) gated on lit set.
      currentUserStars.forEach((star) => {
        const from = projectedUserStarRenderState.get(star.id);
        if (!from || !star.connectedUserStarIds || star.connectedUserStarIds.length === 0) {
          return;
        }

        star.connectedUserStarIds.forEach((linkedStarId) => {
          const to = projectedUserStarRenderState.get(linkedStarId);
          if (!to) return;

          // Show only edges touching at least one lit star.
          const eitherLit = litStarIds.has(star.id) || litStarIds.has(linkedStarId);
          if (!eitherLit) return;

          const edgeKey = star.id < linkedStarId
            ? `${star.id}:${linkedStarId}`
            : `${linkedStarId}:${star.id}`;
          if (renderedLinks.has(edgeKey)) return;
          renderedLinks.add(edgeKey);

          const alphaMultiplier = Math.max(0, Math.min(1, Math.min(from.fadeIn, to.fadeIn) * edgeBreath));
          const ragHighlighted = ragPulseStrength > 0
            && (ragPulseState?.starIds.has(star.id) || ragPulseState?.starIds.has(linkedStarId));
          const focusedEdge = focusedStarId !== null
            && (star.id === focusedStarId || linkedStarId === focusedStarId);
          const ragBoost = ragHighlighted ? ragPulseStrength : 0;
          const edgeAlpha = focusedEdge ? 0.42 : ragHighlighted ? 0.28 : 0.22;
          const gradient = ctx!.createLinearGradient(from.target.x, from.target.y, to.target.x, to.target.y);
          gradient.addColorStop(0, `rgba(${from.mixed[0]},${from.mixed[1]},${from.mixed[2]},${(edgeAlpha + ragBoost * 0.34) * alphaMultiplier})`);
          gradient.addColorStop(1, `rgba(${to.mixed[0]},${to.mixed[1]},${to.mixed[2]},${(edgeAlpha + ragBoost * 0.34) * alphaMultiplier})`);
          ctx!.strokeStyle = gradient;
          ctx!.lineWidth = (focusedEdge ? 1.15 : 0.95) + ragBoost * 1.35;
          ctx!.beginPath();
          ctx!.moveTo(from.target.x, from.target.y);
          ctx!.lineTo(to.target.x, to.target.y);
          ctx!.stroke();
        });
      });

      // --- Scaffold-derived semantic edges (cyan) gated on lit set.
      // Map scaffold edges (brain graph node IDs) back to user stars via
      // manifest paths. Same lit-set gate as inter-star edges.
      const scaffoldEdges = scaffoldEdgesRef.current;
      if (scaffoldEdges.length > 0 && currentUserStars.length >= 2 && litStarIds.size > 0) {
        const nodeIdToManifest = new Map<string, string>();
        for (const idx of availableIndexesRef.current) {
          nodeIdToManifest.set(`index:${idx.index_id}`, idx.manifest_path);
        }

        const manifestToStarIds = new Map<string, string[]>();
        for (const star of currentUserStars) {
          for (const mp of getStarManifestPaths(star)) {
            if (!mp) continue;
            const list = manifestToStarIds.get(mp);
            if (list) list.push(star.id);
            else manifestToStarIds.set(mp, [star.id]);
          }
        }

        for (const edge of scaffoldEdges) {
          const srcManifest = nodeIdToManifest.get(edge.source_id);
          const tgtManifest = nodeIdToManifest.get(edge.target_id);
          if (!srcManifest || !tgtManifest) continue;

          const srcStarIds = manifestToStarIds.get(srcManifest) ?? [];
          const tgtStarIds = manifestToStarIds.get(tgtManifest) ?? [];

          for (const srcStarId of srcStarIds) {
            for (const tgtStarId of tgtStarIds) {
              if (srcStarId === tgtStarId) continue;

              if (!litStarIds.has(srcStarId) && !litStarIds.has(tgtStarId)) continue;

              const edgeKey = srcStarId < tgtStarId
                ? `${srcStarId}:${tgtStarId}`
                : `${tgtStarId}:${srcStarId}`;
              if (renderedLinks.has(edgeKey)) continue;
              renderedLinks.add(edgeKey);

              const fromState = projectedUserStarRenderState.get(srcStarId);
              const toState = projectedUserStarRenderState.get(tgtStarId);
              if (!fromState || !toState) continue;

              const alphaMultiplier = Math.max(0, Math.min(1, Math.min(fromState.fadeIn, toState.fadeIn) * edgeBreath));
              const scaffoldAlpha = 0.18 + Math.min(edge.persistence_weight, 1.0) * 0.26;
              const scaffoldWidth = 0.85 + Math.min(edge.persistence_weight, 1.0) * 1.25;

              const gradient = ctx!.createLinearGradient(
                fromState.target.x, fromState.target.y,
                toState.target.x, toState.target.y,
              );
              gradient.addColorStop(0, `rgba(120,220,255,${scaffoldAlpha * alphaMultiplier})`);
              gradient.addColorStop(1, `rgba(120,220,255,${scaffoldAlpha * 0.6 * alphaMultiplier})`);
              ctx!.strokeStyle = gradient;
              ctx!.lineWidth = scaffoldWidth;
              ctx!.setLineDash([6, 4]);
              ctx!.beginPath();
              ctx!.moveTo(fromState.target.x, fromState.target.y);
              ctx!.lineTo(toState.target.x, toState.target.y);
              ctx!.stroke();
              ctx!.setLineDash([]);
            }
          }
        }
      }

      // --- Semantic-search links (purple/cyan dashed). Already explicit.
      if (semanticActive) {
        semanticState.links.forEach((link, index) => {
          const fromState = projectedUserStarRenderState.get(link.fromId);
          const toState = projectedUserStarRenderState.get(link.toId);
          if (!fromState || !toState) {
            return;
          }
          const alphaMultiplier = Math.max(0, Math.min(1, Math.min(fromState.fadeIn, toState.fadeIn) * edgeBreath));
          const emphasis = Math.min(1, 0.5 + link.sharedTerms * 0.2);
          const gradient = ctx!.createLinearGradient(
            fromState.target.x,
            fromState.target.y,
            toState.target.x,
            toState.target.y,
          );
          gradient.addColorStop(0, `rgba(180,112,255,${(0.28 + emphasis * 0.16) * alphaMultiplier})`);
          gradient.addColorStop(1, `rgba(120,210,255,${(0.2 + emphasis * 0.12) * alphaMultiplier})`);
          ctx!.strokeStyle = gradient;
          ctx!.lineWidth = 1.2 + emphasis * 1.3;
          ctx!.setLineDash([8, 8 + (index % 3)]);
          ctx!.beginPath();
          ctx!.moveTo(fromState.target.x, fromState.target.y);
          ctx!.lineTo(toState.target.x, toState.target.y);
          ctx!.stroke();
          ctx!.setLineDash([]);
        });
      }
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
          spawnFlash,
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
        const semanticHighlighted = semanticSearchStateRef.current.matchedIds.has(star.id);
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
        const sz = (star.size * 1.5 + (selected ? 1.2 : 0) + (dragging ? 0.8 : 0) + (semanticHighlighted ? 0.65 : 0))
          * userStarScale;
        const twinkle = 0.84
          + Math.sin(t * 0.003 + profile.twinklePhase) * 0.1
          + Math.cos(t * 0.0016 + profile.twinklePhase * 0.72) * 0.05;
        const haloRadius = sz * (4.7 + profile.haloFalloff * 2.4 + ringCount * 0.16) * richness;
        const haloCenterX = px + profile.asymmetryOffset.x * sz * 2.1;
        const haloCenterY = py + profile.asymmetryOffset.y * sz * 1.8;
        const auraRadius = sz * (2.8 + profile.coreIntensity * 0.72 + ringCount * 0.14);

        // Spawn shockwave — two concentric rings expand outward from the
        // new star's position during the ignition window. Drawn first so
        // the halo + core paint over the rings near the centre, leaving
        // only the expanding outer arc visible. Skipped when spawnFlash
        // has decayed (steady-state rendering byte-identical).
        if (spawnFlash > 0.001) {
          // Map the existing spawnFlash 0..1 envelope onto an expansion
          // 0..1 by undoing its peak: t≈0 at peak (just after spawn) so
          // rings start small, reach max at t≈1 as flash decays.
          const expand = 1 - spawnFlash;
          for (let ringIdx = 0; ringIdx < 2; ringIdx++) {
            const ringDelay = ringIdx * 0.18;
            const ringExpand = Math.max(0, expand - ringDelay) / Math.max(0.0001, 1 - ringDelay);
            if (ringExpand <= 0 || ringExpand >= 1) continue;
            const ringRadius = sz * (1.4 + ringExpand * 7.5);
            const ringAlpha = (1 - ringExpand) * (1 - ringExpand) * 0.55 * fadeIn;
            ctx!.strokeStyle = `rgba(${haloColor[0]},${haloColor[1]},${haloColor[2]},${ringAlpha})`;
            ctx!.lineWidth = 1.4;
            ctx!.beginPath();
            ctx!.arc(px, py, ringRadius, 0, Math.PI * 2);
            ctx!.stroke();
          }
        }

        // Spawn-flash bonus on halo brightness — kicks in only during the
        // ignition window and decays to zero, so steady-state rendering is
        // identical to before the cinematic landed.
        const haloFlashBonus = spawnFlash * 0.34;
        const halo = ctx!.createRadialGradient(haloCenterX, haloCenterY, sz * 0.22, px, py, haloRadius);
        halo.addColorStop(0, `rgba(${haloColor[0]},${haloColor[1]},${haloColor[2]},${(0.14 + profile.coreIntensity * 0.04 + (selected ? 0.08 : 0) + (semanticHighlighted ? 0.08 : 0) + (ragHighlighted ? ragPulseStrength * 0.12 : 0) + haloFlashBonus) * fadeIn})`);
        halo.addColorStop(Math.min(0.76, 0.48 + profile.haloFalloff * 0.18), `rgba(${fillColor[0]},${fillColor[1]},${fillColor[2]},${(0.05 + richness * 0.02 + haloFlashBonus * 0.6) * fadeIn})`);
        halo.addColorStop(1, "rgba(0,0,0,0)");
        ctx!.fillStyle = halo;
        ctx!.beginPath();
        ctx!.arc(px, py, haloRadius * (1 + spawnFlash * 0.18), 0, Math.PI * 2);
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
        if (semanticHighlighted) {
          ctx!.beginPath();
          ctx!.arc(px, py, sz * 4.6, 0, Math.PI * 2);
          ctx!.strokeStyle = "rgba(178, 122, 255, 0.34)";
          ctx!.lineWidth = 1.15;
          ctx!.setLineDash([5, 6]);
          ctx!.stroke();
          ctx!.setLineDash([]);
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
        // During spawn the core inflates briefly (max ~22%) for an
        // ignition feel — independent of fadeIn opacity so steady-state
        // size is unchanged once the flash decays.
        const coreSpawnScale = 1 + spawnFlash * 0.22;
        fill.addColorStop(0, `rgba(255,255,255,${Math.min(1, (0.95 + profile.coreIntensity * 0.08) * fadeIn)})`);
        fill.addColorStop(0.16, `rgba(${coreColor[0]},${coreColor[1]},${coreColor[2]},${0.98 * fadeIn})`);
        fill.addColorStop(0.24, `rgba(${fillColor[0]},${fillColor[1]},${fillColor[2]},${0.94 * fadeIn})`);
        fill.addColorStop(0.68, `rgba(${haloColor[0]},${haloColor[1]},${haloColor[2]},${0.88 * fadeIn})`);
        fill.addColorStop(1, `rgba(${shadowColor[0]},${shadowColor[1]},${shadowColor[2]},${0.98 * fadeIn})`);
        ctx!.fillStyle = fill;
        ctx!.beginPath();
        ctx!.arc(px, py, sz * coreSpawnScale, 0, Math.PI * 2);
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

    // ── Forge technique stars (M14 Phase 2b) ──────────────────────────
    //
    // One canvas star per active Forge technique, projected through the
    // same camera transform user stars use so they pan/zoom alongside
    // the rest of the constellation. Drawn after `drawUserStars` so
    // they sit visually on the same layer.
    //
    // Hit-tested in `getHitForgeStar`; clicks deep-link to
    // `/forge#<id>` (handled in the pointer-down branch below). The
    // star observatory dialog is **not** opened — the Forge gallery is
    // the single source of UI truth for technique state per ADR 0014.

    function projectForgeStars(): { star: ForgeStar; target: ProjectedUserStarHitTarget }[] {
      const camera = readBackgroundCamera();
      return forgeStarsRef.current.map((star) => ({
        star,
        target: buildProjectedUserStarHitTarget(
          { id: star.id, x: star.x, y: star.y, size: star.size },
          W,
          H,
          camera,
          coarsePointerRef.current ? 12 : 0,
          mouse,
        ),
      }));
    }

    function drawForgeStars(t: number) {
      const projected = projectForgeStars();
      if (projected.length === 0) return;

      const constellationScale = getConstellationCameraScale(backgroundZoomRef.current);
      const baseScale = Math.max(0.58, 0.36 + Math.pow(constellationScale, 0.72) * 0.64);

      projected.forEach(({ star, target }) => {
        const px = target.x;
        const py = target.y;
        const [r, g, b] = star.paletteRgb;
        const sz = star.size * 1.5 * baseScale;
        // Gentle shared twinkle keyed off the star id so adjacent
        // technique stars do not pulse in lockstep.
        const phaseSeed = star.id.length * 0.41;
        const twinkle = 0.86
          + Math.sin(t * 0.0028 + phaseSeed) * 0.08
          + Math.cos(t * 0.0017 + phaseSeed * 0.6) * 0.04;

        const haloRadius = sz * 6.5;
        const halo = ctx!.createRadialGradient(px, py, sz * 0.22, px, py, haloRadius);
        halo.addColorStop(0, `rgba(${r},${g},${b},0.18)`);
        halo.addColorStop(0.5, `rgba(${r},${g},${b},0.07)`);
        halo.addColorStop(1, "rgba(0,0,0,0)");
        ctx!.fillStyle = halo;
        ctx!.beginPath();
        ctx!.arc(px, py, haloRadius, 0, Math.PI * 2);
        ctx!.fill();

        // Inner glow ring — gives the star a defined edge against the
        // halo without painting a hard core dot.
        ctx!.strokeStyle = `rgba(${r},${g},${b},${0.55 * twinkle})`;
        ctx!.lineWidth = 1.2;
        ctx!.beginPath();
        ctx!.arc(px, py, sz * 1.7, 0, Math.PI * 2);
        ctx!.stroke();

        // Bright core.
        ctx!.fillStyle = `rgba(${Math.min(255, r + 32)},${Math.min(255, g + 32)},${Math.min(255, b + 32)},${0.92 * twinkle})`;
        ctx!.beginPath();
        ctx!.arc(px, py, sz * 0.78, 0, Math.PI * 2);
        ctx!.fill();
      });
    }

    function getHitForgeStar(clientX: number, clientY: number): ForgeStar | null {
      const projected = projectForgeStars();
      if (projected.length === 0) return null;
      const pointer = getCanvasPointer(clientX, clientY);
      const targets = projected.map(({ target }) => target);
      const hit = findClosestProjectedTarget(targets, pointer);
      if (!hit) return null;
      return projected.find(({ target }) => target.id === hit.id)?.star ?? null;
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
      // Round to half-pixel so the core disk, halo gradients, orbit ring,
      // and diffraction rays all rasterize with the same sub-pixel rounding
      // — otherwise small filled arcs and thin strokes can land on different
      // pixel boundaries at high zoom and appear visually misaligned.
      const ppx = Math.round(projected.x + (mouse.x - W / 2) * 0.015) + 0.5;
      const ppy = Math.round(projected.y + (mouse.y - H / 2) * 0.015) + 0.5;
      const sc = getZoomResponsiveNodeScale(backgroundZoomRef.current);
      const coreR = 5 * sc;

      // ── Topology activity strength (0–1) derived from scaffold data ───────────
      const scaffResp = scaffoldResponseRef.current;
      const topoEdgeCount = scaffoldEdgesRef.current.length;
      const topoBetti0 = scaffResp?.betti_0 ?? 0; // connected components
      const topoBetti1 = scaffResp?.betti_1 ?? 0; // loops / cross-references
      // Normalise: betti_0 ≥ 1 means at least one index, each additional component adds;
      // betti_1 > 0 means deep cross-references found. Edge count contributes volume.
      const topoComponentStrength = Math.min(1, Math.max(0, (topoBetti0 - 1) / 5));
      const topoLoopStrength = Math.min(1, topoBetti1 / 3);
      const topoEdgeStrength = Math.min(1, topoEdgeCount / 12);
      // Use GSAP-tweened data strength for smooth transitions (falls back to raw calc)
      const topoDataStrength = topoStrengthAnimRef.current.value > 0
        ? topoStrengthAnimRef.current.value
        : Math.min(1, topoComponentStrength * 0.4 + topoLoopStrength * 0.35 + topoEdgeStrength * 0.25);

      // Polaris always feels alive — organic noise baseline + topology amplification
      // Simplex noise replaces mechanical Math.sin for natural, never-repeating drift
      const noiseT = ts * 0.00008; // slow-moving noise time coordinate
      const idleBreath = reducedMotion ? 0.25 : 0.25 + noise2D(noiseT, 0.0) * 0.10;
      // topoStrength: blends idle baseline with actual data, clamped 0–1
      const topoStrength = Math.min(1, idleBreath + topoDataStrength * 0.75);

      // Pulse rate accelerates with knowledge — idle 3010ms → active ~2000ms
      const pulseFreq = 0.00209 + topoStrength * 0.00105;
      const pulseAmp = 0.12 + topoStrength * 0.06; // 12% → 18% amplitude
      // Noise-modulated pulse with subtle frequency drift
      const pulseDrift = noise2D(noiseT * 1.7, 3.0) * 0.0003;
      const pulse = reducedMotion ? 1 : (0.88 - topoStrength * 0.06) + noise2D(ts * (pulseFreq + pulseDrift), 1.0) * pulseAmp;

      // ── Satellite micro-node positions (dx, dy from centre, pre-scaled) ───────
      // Modelled on the Sketchfab "Mini Constellation Lines Stylized Effect":
      // a small organic constellation of 6 peripheral nodes surrounding the core,
      // connected by animated lines that trace, hold, then fade in a looping cycle.
      const MICRO: [number, number][] = [
        [  0,          0       ], // 0 — METIS core (drawn separately below)
        [-22 * sc,  -20 * sc  ], // 1 — upper-left
        [  2 * sc,  -35 * sc  ], // 2 — apex (topmost)
        [ 25 * sc,  -17 * sc  ], // 3 — upper-right
        [ 34 * sc,    9 * sc  ], // 4 — right
        [ -5 * sc,   28 * sc  ], // 5 — lower
        [-28 * sc,   12 * sc  ], // 6 — left
      ];

      // Edge pairs (indices into MICRO) — outer ring + inner cross-spokes
      const EDGES: [number, number][] = [
        [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 1], // outer constellation ring
        [0, 2], [0, 4], [2, 5], [1, 4],                  // hub spokes + diagonals
      ];

      // Spawn-loop timing (mirrors the looping/spawning feel in the Sketchfab VFX)
      const CYCLE_MS = 7200; // full respawn period
      const TRACE_MS = 640;  // line traces from source to target
      const HOLD_MS  = 680;  // line holds fully drawn
      const FADE_MS  = 960;  // line fades out
      const TOTAL_MS = TRACE_MS + HOLD_MS + FADE_MS;
      const STEP_MS  = 580;  // stagger between successive edge starts

      // ── 1. Animated constellation lines ──────────────────────────────────────
      ctx!.save();
      ctx!.lineCap = "round";

      EDGES.forEach(([ai, bi], eIdx) => {
        const [ax, ay] = MICRO[ai];
        const [bx, by] = MICRO[bi];

        if (reducedMotion) {
          // Reduced motion: static dim lines, no trace animation
          ctx!.beginPath();
          ctx!.moveTo(ppx + ax, ppy + ay);
          ctx!.lineTo(ppx + bx, ppy + by);
          ctx!.strokeStyle = "rgba(180,210,255,0.18)";
          ctx!.lineWidth = 0.7;
          ctx!.stroke();
          return;
        }

        const startOffset = eIdx * STEP_MS;
        const t = ts % CYCLE_MS;
        const edgeT = (t - startOffset + CYCLE_MS) % CYCLE_MS;
        if (edgeT > TOTAL_MS) return;

        // Ease-in squared trace progress
        const traceP = Math.min(1, edgeT / TRACE_MS);
        let alpha: number;
        if (edgeT <= TRACE_MS + HOLD_MS) {
          alpha = edgeT < TRACE_MS ? traceP * traceP : 1;
        } else {
          const fP = (edgeT - TRACE_MS - HOLD_MS) / FADE_MS;
          alpha = 1 - fP * fP; // ease-out squared
        }
        alpha = Math.max(0, alpha) * pulse;
        if (alpha < 0.01) return;

        const sx = ppx + ax,                    sy = ppy + ay;
        const ex = ppx + ax + (bx - ax) * traceP, ey = ppy + ay + (by - ay) * traceP;

        // Micro-constellation color warmth shifts with topology activity
        // Idle: cool blue (110,165,255) → Active: warm gold (210,195,120)
        const tw = topoStrength; // 0 = cool, 1 = warm
        const glowR = Math.round(110 + tw * 100);
        const glowG = Math.round(165 + tw * 30);
        const glowB = Math.round(255 - tw * 135);
        const coreLineR = Math.round(215 + tw * 40);
        const coreLineG = Math.round(232 + tw * 8);
        const coreLineB = Math.round(255 - tw * 105);

        // Soft outer glow (wide, low-opacity)
        ctx!.beginPath();
        ctx!.moveTo(sx, sy);
        ctx!.lineTo(ex, ey);
        ctx!.strokeStyle = `rgba(${glowR},${glowG},${glowB},${alpha * 0.14})`;
        ctx!.lineWidth = 5 * sc;
        ctx!.stroke();

        // Inner bright core line
        ctx!.beginPath();
        ctx!.moveTo(sx, sy);
        ctx!.lineTo(ex, ey);
        ctx!.strokeStyle = `rgba(${coreLineR},${coreLineG},${coreLineB},${alpha * 0.82})`;
        ctx!.lineWidth = 0.85 * sc;
        ctx!.stroke();

        // Travelling particle at the line tip (only while tracing)
        if (traceP < 0.999 && alpha > 0.05) {
          const tg = ctx!.createRadialGradient(ex, ey, 0, ex, ey, 5.5 * sc);
          tg.addColorStop(0,   `rgba(${Math.round(240 + tw * 15)},${Math.round(250 - tw * 20)},${Math.round(255 - tw * 80)},${alpha})`);
          tg.addColorStop(0.4, `rgba(${Math.round(150 + tw * 60)},${Math.round(205 - tw * 10)},${Math.round(255 - tw * 100)},${alpha * 0.5})`);
          tg.addColorStop(1,   "rgba(0,0,0,0)");
          ctx!.fillStyle = tg;
          ctx!.beginPath();
          ctx!.arc(ex, ey, 5.5 * sc, 0, Math.PI * 2);
          ctx!.fill();
        }
      });

      ctx!.restore();

      // ── 2. Peripheral micro-star nodes (nodes 1–6) ───────────────────────────
      MICRO.slice(1).forEach(([dx, dy], i) => {
        const nx = ppx + dx;
        const ny = ppy + dy;
        const nodePulse = reducedMotion
          ? 0.80
          : 0.62 + noise2D(ts * 0.0006 + i * 1.31, 5.0 + i) * 0.38;
        const mr = (1.55 + (i % 3) * 0.28) * sc;

        // Soft halo — warms toward gold with topology
        const haloR = Math.round(145 + topoStrength * 80);
        const haloG = Math.round(195 + topoStrength * 20);
        const haloB = Math.round(255 - topoStrength * 100);
        const hg = ctx!.createRadialGradient(nx, ny, 0, nx, ny, mr * 5.5);
        hg.addColorStop(0, `rgba(${haloR},${haloG},${haloB},${0.18 * nodePulse})`);
        hg.addColorStop(1, "rgba(0,0,0,0)");
        ctx!.fillStyle = hg;
        ctx!.beginPath();
        ctx!.arc(nx, ny, mr * 5.5, 0, Math.PI * 2);
        ctx!.fill();

        // Outer dot
        const dotR = Math.round(200 + topoStrength * 40);
        const dotG = Math.round(222 + topoStrength * 12);
        const dotB = Math.round(255 - topoStrength * 80);
        ctx!.beginPath();
        ctx!.arc(nx, ny, mr, 0, Math.PI * 2);
        ctx!.fillStyle = `rgba(${dotR},${dotG},${dotB},${0.88 * nodePulse})`;
        ctx!.fill();

        // Bright inner core
        ctx!.beginPath();
        ctx!.arc(nx, ny, mr * 0.36, 0, Math.PI * 2);
        ctx!.fillStyle = "rgba(248,252,255,1)";
        ctx!.fill();
      });

      // ── 3. Main Polaris / METIS core ─────────────────────────────────────────
      // Outer gold-blue ambient glow — expands with topology knowledge
      const outerR = (52 + topoStrength * 18) * sc; // 52 → 70 with full topology
      const outerGrad = ctx!.createRadialGradient(ppx, ppy, 0, ppx, ppy, outerR);
      const outerWarmth = topoStrength * 40; // shift toward warmer gold with activity
      outerGrad.addColorStop(0,   `rgba(${210 + outerWarmth},${228},${255 - outerWarmth},${(0.10 + topoStrength * 0.06) * pulse})`);
      outerGrad.addColorStop(0.4, `rgba(255,${240 - outerWarmth * 0.3},${180 - outerWarmth},${(0.08 + topoStrength * 0.05) * pulse})`);
      outerGrad.addColorStop(1,   "rgba(0,0,0,0)");
      ctx!.fillStyle = outerGrad;
      ctx!.beginPath();
      ctx!.arc(ppx, ppy, outerR, 0, Math.PI * 2);
      ctx!.fill();

      // Inner corona — grows with connected components
      const coronaR = (20 + topoStrength * 10) * sc; // 20 → 30 with full topology
      const midGrad = ctx!.createRadialGradient(ppx, ppy, 0, ppx, ppy, coronaR);
      midGrad.addColorStop(0, `rgba(255,252,${220 - topoStrength * 30},${(0.38 + topoStrength * 0.12) * pulse})`);
      midGrad.addColorStop(1, "rgba(0,0,0,0)");
      ctx!.fillStyle = midGrad;
      ctx!.beginPath();
      ctx!.arc(ppx, ppy, coronaR, 0, Math.PI * 2);
      ctx!.fill();

      // 2026-05-01 (M21 Phase 5): the rotating orbit ring (3a), orbiting
      // particles (3b), and the 8-point diffraction spike pattern + tertiary
      // spikes were removed per user critique — together they read as a
      // generic "JJ Abrams lens flare" rather than a meaningful element of
      // the constellation. The core star, halo, micro-nodes, and animated
      // constellation lines remain — those carry the actual visual story.
      //
      // M10's H₁ topology amplification used to ride on the orbit-ring alpha
      // + diffraction-spike length; that signal now needs another surface if
      // it ever becomes load-bearing. See `plans/ui-critical-triage/plan.md`
      // (Phase 5 entry) and `docs/adr/0006-constellation-design-2d-primary.md`
      // (2026-05-01 addendum) for context.
      //
      // Reinstate by reverting this section against git history — every
      // removed primitive is recoverable.

      // Core disk (warm white)
      ctx!.beginPath();
      ctx!.arc(ppx, ppy, coreR, 0, Math.PI * 2);
      ctx!.fillStyle = `rgba(255,252,230,${0.96 * pulse})`;
      ctx!.fill();

      // Bright inner core
      ctx!.beginPath();
      ctx!.arc(ppx, ppy, coreR * 0.4, 0, Math.PI * 2);
      ctx!.fillStyle = "rgba(255,255,255,1)";
      ctx!.fill();

      // ── 4. METIS label (above the topmost micro-node) ────────────────────────
      const topNodeY  = ppy + MICRO[2][1]; // apex node absolute Y
      const fontSize  = Math.round(10 + sc * 4);
      ctx!.font       = buildCanvasFont(fontSize, NODE_LABEL_FONT_FAMILY, "600");
      ctx!.textAlign  = "center";
      ctx!.fillStyle  = `rgba(255,235,140,${0.72 * pulse})`;
      ctx!.fillText("METIS", ppx, topNodeY - 8 * sc);
    }

    function drawFacultyGlyph(
      node: NodeData,
      px: number,
      py: number,
      brightness: number,
      active: boolean,
      proximity: number,
      nodeAwakenProg: number,
      ragFacultyHighlighted: boolean,
      ragPulseStrength: number,
    ) {
      const art = getFacultyArtDefinition(node.concept.faculty.id);
      const artState = art ? facultyArtImages.get(node.concept.faculty.id) : null;
      if (!art || !artState || artState.errored || !artState.loaded) {
        return;
      }

      let artOpacity = art.idleOpacity;
      artOpacity += nodeAwakenProg * 0.03;
      artOpacity += Math.max(0, brightness - 0.18) * 0.04;
      artOpacity += proximity * 0.06;
      artOpacity += node.hoverBoost * (art.activeOpacity - art.idleOpacity);
      if (active) {
        artOpacity = Math.max(artOpacity, art.activeOpacity);
      }

      if (ragFacultyHighlighted) {
        artOpacity = Math.max(artOpacity, 0.24 + ragPulseStrength * 0.04);
      }

      if (artOpacity <= 0.01) {
        return;
      }

      const cScale = getConstellationCameraScale(backgroundZoomRef.current);
      const artSize = Math.min(W, H) * cScale * art.scale;
      const drawX = px - artSize / 2;
      const drawY = py - artSize / 2 + artSize * art.offsetY;

      ctx!.save();
      ctx!.globalAlpha = Math.min(0.28, artOpacity);
      ctx!.drawImage(artState.image, drawX, drawY, artSize, artSize);
      ctx!.restore();
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
        drawFacultyGlyph(
          n,
          px,
          py,
          b,
          i === aNode,
          proximity,
          nodeAwakenProg,
          ragFacultyHighlighted,
          ragPulseStrength,
        );

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
        // 2026-05-01 (M21 Phase 5): faculty title text under each anchor is
        // suppressed per user critique — labels read as confusing "function"
        // declarations rather than navigation aids. Hit-zone bookkeeping
        // still runs (semantic-search, drag-to-reassign etc. depend on it),
        // we just stop painting the text. Reinstate by un-commenting the
        // fillText below if a future agent decides to surface labels again.
        syncNodeLabelLayout(n, px, py, s, nodeGalaxyScale);
        // (label fillText intentionally omitted — see comment above)
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
      const px = candidate.screenX;
      const py = candidate.screenY;
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
          clusterPositionsRef.current,
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
      const backgroundCamera = constellationCamera.stepCamera({
        reducedMotion,
        focusStrength: starDiveFocusStrengthRef.current,
      });

      // --- Star Dive: focus detection + auto-drift ---
      const diveFocusStrength = getStarDiveFocusStrength(backgroundCamera.zoomFactor);
      starDiveFocusStrengthRef.current = diveFocusStrength;

      if (diveFocusStrength > 0 && !starDivePanSuppressedRef.current) {
        // Acquire or maintain focus target
        if (!starDiveFocusedStarIdRef.current) {
          // Use projectedUserStarRenderState for screen positions — avoids re-projecting world coords
          // and stays consistent with the render pass. Positions are from the previous frame,
          // which is acceptable since target acquisition is a one-time event per zoom-in.
          const userStarTargets = userStarsRef.current.flatMap((star) => {
            const proj = projectedUserStarRenderState.get(star.id);
            if (!proj) return [];
            return [{ id: star.id, screenX: proj.target.x, screenY: proj.target.y, brightness: star.size }];
          });
          let target = findStarDiveFocusTarget(userStarTargets, W, H);

          // Fall back to catalogue stars when no user star is near the viewport centre
          if (!target) {
            const catalogueTargets = visibleStarsRef.current.map((star) => ({
              id: star.id,
              screenX: star.screenX,
              screenY: star.screenY,
              brightness: star.brightness,
            }));
            target = findStarDiveFocusTarget(catalogueTargets, W, H);
          }

          if (target) {
            const scale = getBackgroundCameraScale(backgroundCamera.zoomFactor);
            starDiveFocusedStarIdRef.current = target.id;
            starDiveFocusWorldPosRef.current = {
              x: backgroundCamera.x + (target.screenX - W / 2) / scale,
              y: backgroundCamera.y + (target.screenY - H / 2) / scale,
            };
            const focusedUserStar = userStarsRef.current.find((star) => star.id === target.id);
            const focusedContentType = focusedUserStar
              ? deriveUserStarContentType(focusedUserStar)
              : null;
            const focusedProfile = getCachedStellarProfile(
              target.id,
              focusedContentType,
            );
            // Phase 6 — attach user-star annotations to the dive focus
            // profile so the closeup-tier shader sees halo / ring /
            // satellite attributes when the focused target is a user
            // star. Catalogue fallback stars have no user metadata, so
            // annotations stay undefined.
            const focusedAnnotations = focusedUserStar
              ? deriveStarAnnotations(focusedUserStar)
              : undefined;
            starDiveFocusProfileRef.current = focusedAnnotations
              ? { ...focusedProfile, annotations: focusedAnnotations }
              : focusedProfile;
            starDiveFocusNameRef.current = visibleStarNameMap.get(target.id) ?? null;
          }
        }

        // Auto-drift camera toward focused star
        if (starDiveFocusWorldPosRef.current) {
          const wp = starDiveFocusWorldPosRef.current;
          const driftEasing = reducedMotion ? 1 : 0.04 + diveFocusStrength * 0.08;
          const driftDx = wp.x - backgroundCameraTargetOriginRef.current.x;
          const driftDy = wp.y - backgroundCameraTargetOriginRef.current.y;
          if (Math.abs(driftDx) > 0.01 || Math.abs(driftDy) > 0.01) {
            backgroundCameraTargetOriginRef.current = {
              x: backgroundCameraTargetOriginRef.current.x + driftDx * driftEasing,
              y: backgroundCameraTargetOriginRef.current.y + driftDy * driftEasing,
            };
          }
        }
      } else if (diveFocusStrength <= 0 && starDiveFocusedStarIdRef.current) {
        // Clear focus when zoomed back out
        starDiveFocusedStarIdRef.current = null;
        starDiveFocusWorldPosRef.current = null;
        starDiveFocusProfileRef.current = null;
        starDiveFocusNameRef.current = null;
        starDivePanSuppressedRef.current = false;
      }

      // Project focused star world position to screen coords for the 2D
      // starfield focus uniforms (depth-of-field falloff around the dive star).
      if (
        diveFocusStrength > 0
        && starDiveFocusWorldPosRef.current
        && starDiveFocusProfileRef.current
      ) {
        const wp = starDiveFocusWorldPosRef.current;
        const scale = getBackgroundCameraScale(backgroundCamera.zoomFactor);
        starDiveFocusViewRef.current = {
          screenX: (wp.x - backgroundCamera.x) * scale + W / 2,
          screenY: (wp.y - backgroundCamera.y) * scale + H / 2,
          focusStrength: diveFocusStrength,
          profile: starDiveFocusProfileRef.current,
          starName: starDiveFocusNameRef.current ?? undefined,
        };
      } else {
        starDiveFocusViewRef.current = null;
      }

      // Update reactive state (throttled — only when integer percentage changes)
      const roundedStrength = Math.round(diveFocusStrength * 100) / 100;
      if (Math.abs(roundedStrength - starDiveFocusStrength) > 0.009) {
        setStarDiveFocusStrength(roundedStrength);
      }

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

        // Throttled sector eviction (~once per viewport change, not per frame)
        const scale = getBackgroundCameraScale(backgroundCamera.zoomFactor);
        const sectorSize = DEFAULT_CATALOGUE_CONFIG.sectorSize;
        const camSx = Math.floor(backgroundCamera.x / sectorSize);
        const camSy = Math.floor(backgroundCamera.y / sectorSize);
        const maxDist = Math.ceil(((W + H) / scale) / sectorSize) + 4;
        catalogue.evictDistantSectors(camSx, camSy, maxDist);
      }
      rebuildProjectedUserStarRenderState(backgroundCamera, getRenderEpochMs(ts));

      // Update WebGL focus uniforms every frame — gating on
      // `shouldRefreshVisibleStars` would freeze the hover-spotlight
      // tween whenever the camera is settled. Cheap: just five number
      // assignments on the frame ref; revision is intentionally not
      // bumped so the geometry pass stays gated.
      syncFocusUniformsForFrame(W, H);

      ctx!.clearRect(0, 0, W, H);
      if (!awakened && ts > 2000) {
        awakened = true; awakenStart = ts;
      }

      // Fade canvas overlay elements during Star Dive
      const canvasOverlayAlpha = 1 - starDiveFocusStrengthRef.current * 0.92;
      if (canvasOverlayAlpha < 0.99) {
        ctx!.save();
        ctx!.globalAlpha = Math.max(0, canvasOverlayAlpha);
      }

      // Galactic spiral sits underneath nebulae and dust so they
      // layer on top — spiral is the deepest backdrop element on
      // the 2D canvas.
      drawGalacticSpiral(ts, backgroundZoomRef.current);
      drawNebulae(ts);
      drawDust();

      // ── Comet lifecycle: tick, draw, burst effects ──
      syncComets(serverCometsRef.current);
      for (let i = cometSprites.length - 1; i >= 0; i--) {
        const shouldRemove = tickComet(cometSprites[i], ts);
        if (shouldRemove) {
          if (cometSprites[i].phase === "absorbed") {
            absorbBursts.push({ x: cometSprites[i].targetX, y: cometSprites[i].targetY, color: cometSprites[i].color, startedAt: ts });
          }
          cometSprites.splice(i, 1);
        }
      }
      if (cometSprites.length > 0 && ctx) {
        drawCometSprites(ctx, cometSprites, ts);
        // M22 Phase 1+2+4 — path-text headline labels with collision
        // suppression. Pipeline: prepare every comet's label (math
        // only) → suppressCollidingLabels keeps the highest-relevance
        // labels when AABBs overlap >40% → drawPreparedLabel renders
        // the survivors. Splitting prepare from draw means we can
        // do suppression on bbox math without doing canvas work for
        // labels that won't render.
        const labelOpts = { reducedMotion: reducedMotionRef.current };
        const prepared = cometSprites
          .map((c) => prepareCometLabel(c, labelOpts))
          .filter((p): p is NonNullable<typeof p> => p !== null);
        const survivors = suppressCollidingLabels(
          prepared.map((p) => ({ id: p.cometId, relevance: p.relevance, bbox: p.bbox })),
        );
        const survivorIds = new Set(survivors.map((s) => s.id));
        for (const p of prepared) {
          if (survivorIds.has(p.cometId)) drawPreparedLabel(ctx, p);
        }
        // Drop module-level flip state for comets that left the active set.
        pruneCometLabelState(cometSprites.map((c) => c.comet_id));

        // M22 Phase 3+5 — hovered comet gets a canvas-rendered card
        // with title/summary/faculty pill/footer. Card stays canvas
        // to keep the visual language consistent.
        //
        // tickHoverPersistence keeps the card alive while the cursor
        // is still over the comet head OR over the previously-drawn
        // card bbox (necessary because pointermove doesn't fire while
        // the cursor is stationary — a timer-only expiry would dismiss
        // the card mid-read). Once the cursor actually leaves both,
        // the 600ms grace window starts counting down.
        const hoverState = cometHoverStateRef.current;
        const nextHover = tickHoverPersistence(
          hoverState,
          { x: mouse.x, y: mouse.y },
          cometSprites,
          performance.now(),
        );
        hoverState.cometId = nextHover.cometId;
        hoverState.lastSeenAtMs = nextHover.lastSeenAtMs;
        const hovered = hoverState.cometId
          ? cometSprites.find((c) => c.comet_id === hoverState.cometId)
          : null;
        if (hovered) {
          // rectFromCachedElement is module-scoped (above) — no
          // per-frame closure allocation in the hot loop. Each call
          // returns the cached element's bbox or null on miss.
          const fixedRects: CometCardRect[] = [];
          const pillRect = rectFromCachedElement(zoomPillRef, ".metis-zoom-pill");
          if (pillRect) fixedRects.push(pillRect);
          const fabRect = rectFromCachedElement(homeFabRef, ".metis-home-fab-root");
          if (fabRect) fixedRects.push(fabRect);
          const heroRect = rectFromCachedElement(heroOverlayRef, ".metis-hero-overlay");
          if (heroRect) fixedRects.push(heroRect);
          // The page-chrome top bar doesn't have a single stable
          // class selector (cn-composed in page-chrome.tsx). A
          // synthetic 64px-tall band at the top of the viewport is
          // a robust fallback that doesn't depend on the chrome's
          // class structure changing.
          fixedRects.push({ x: 0, y: 0, w: window.innerWidth, h: 64 });
          // Comet positions are computed in CSS-pixel viewport space
          // (see makeCometData(evt, W, H, …) where W/H come from
          // window.innerWidth/Height). Pass the same coordinate space
          // to drawCometHoverCard so its clampToSafeArea aligns.
          hoverState.cardBbox = drawCometHoverCard(
            ctx,
            hovered,
            { x: hovered.x, y: hovered.y },
            {
              viewport: { w: window.innerWidth, h: window.innerHeight },
              fixedRects,
            },
          );
        } else {
          hoverState.cardBbox = null;
        }
      }
      // Absorption burst effects (persists briefly after comet absorbed)
      for (let i = absorbBursts.length - 1; i >= 0; i--) {
        const b = absorbBursts[i];
        const progress = (ts - b.startedAt) / 600;
        if (progress >= 1) { absorbBursts.splice(i, 1); continue; }
        if (ctx) drawAbsorptionBurst(ctx, b.x, b.y, b.color, progress);
      }

      drawNodes(ts);
      drawUserStarEdges(ts);
      drawAddCandidatePreview(ts);
      drawUserStars(ts);
      drawForgeStars(ts);

      // ── Offscreen bloom composite for Polaris ────────────────────────────────
      // Draw Polaris to an offscreen canvas, then composite back with a soft
      // blur layer underneath for a real glow effect.
      if (!reducedMotion && ctx) {
        // Lazy-init offscreen canvas at matching size. The bloom buffer is
        // sized in physical pixels (W * dpr × H * dpr) so it matches the
        // main canvas backing store, then its 2D context is pre-scaled so
        // draw calls use the same CSS-pixel coordinate space as the main ctx.
        const bufferW = Math.round(W * dpr);
        const bufferH = Math.round(H * dpr);
        if (
          !bloomCanvasRef.current
          || bloomCanvasRef.current.width !== bufferW
          || bloomCanvasRef.current.height !== bufferH
        ) {
          bloomCanvasRef.current = document.createElement("canvas");
          bloomCanvasRef.current.width = bufferW;
          bloomCanvasRef.current.height = bufferH;
          bloomCtxRef.current = bloomCanvasRef.current.getContext("2d");
          if (typeof bloomCtxRef.current?.setTransform === "function") {
            bloomCtxRef.current.setTransform(dpr, 0, 0, dpr, 0, 0);
          }
        }
        const bCtx = bloomCtxRef.current;
        if (bCtx) {
          bCtx.clearRect(0, 0, W, H);
          // Temporarily redirect drawing context so drawPolarisMetis renders offscreen.
          // swapCtx is an arrow indirection that bypasses Turbopack's incorrect
          // const-detection on closure-captured let variables (Turbopack bug).
          const swapCtx = (next: CanvasRenderingContext2D) => { ctx = next; };
          const mainCtx = ctx!;
          swapCtx(bCtx);
          drawPolarisMetis(ts);
          swapCtx(mainCtx);

          // Pass explicit destination size so the bloom is painted into CSS
          // pixels (the main ctx is already scaled by dpr, so the implicit
          // 1:1 pixel copy would otherwise draw at half the intended size).
          // Layer 1: blurred glow underneath (additive blend)
          mainCtx.save();
          mainCtx.filter = "blur(6px)";
          mainCtx.globalCompositeOperation = "lighter";
          mainCtx.globalAlpha = 0.35;
          mainCtx.drawImage(bloomCanvasRef.current, 0, 0, W, H);
          mainCtx.restore();

          // Layer 2: crisp original on top
          mainCtx.drawImage(bloomCanvasRef.current, 0, 0, W, H);
        } else {
          drawPolarisMetis(ts);
        }
      } else {
        drawPolarisMetis(ts);
      }

      // ── Polaris tendrils reaching toward approaching/absorbing comets ──
      if (cometSprites.length > 0 && ctx) {
        const polCam = readBackgroundCamera();
        const polProj = projectConstellationPoint({ x: CORE_CENTER_X, y: CORE_CENTER_Y }, W, H, polCam);
        const polPx = polProj.x + (mouse.x - W / 2) * 0.015;
        const polPy = polProj.y + (mouse.y - H / 2) * 0.015;
        for (const comet of cometSprites) {
          drawPolarisTendril(ctx, polPx, polPy, comet, ts);
        }
      }

      if (canvasOverlayAlpha < 0.99) {
        ctx!.restore();
      }

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
      // Regenerate nebulae for the new viewport. Same seed → same
      // arrangement, just rescaled to the new W/H.
      nebulae = generateNebulae(cosmosSeed, W, H);
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
            const resolvedPoint = getResolvedStarPoint(star, previewPositions, star.id, clusterPositionsRef.current);
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
      // Phase 1.4: route user-star naming through generateStarName so the
      // tier policy is enforced in one place. User stars without an explicit
      // label fall back to their id rather than a fabricated classical
      // designation — ADR 0006 reserves classical names for landmark tier.
      const userName = generateStarName({
        tier: "user",
        userSuppliedName: star.label,
      });
      const title = userName.name ?? star.id;
      const description = getStarTooltipDescription(star, faculty);
      const domainLabel = faculty.label;

      if (starTooltipDomainRef.current) {
        starTooltipDomainRef.current.textContent = `Domain: ${domainLabel}`;
      }
      if (starTooltipTitleRef.current) {
        starTooltipTitleRef.current.textContent = title;
        starTooltipTitleRef.current.setAttribute(
          "data-name-kind",
          userName.kind ?? "none",
        );
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

    // 2026-05-01 (M21 Phase 5): `showCatalogueTooltip` and the matching
    // `getHoveredLandmarkStar` hit-test below were removed because the
    // landmark hover surfaced an auto-generated classical name plus a
    // "Bayer/Flamsteed convention" footer that read as AI slop. The
    // tooltip element stays in the JSX (and `hideCatalogueTooltip`
    // remains as a defensive no-op called from many cleanup paths) — it
    // simply has no producer anymore. ADR 0006 still mandates tiered
    // naming at the *data* level; only the hover *surface* is gone. See
    // `docs/adr/0006-constellation-design-2d-primary.md` (2026-05-01
    // addendum).
    function hideCatalogueTooltip() {
      const el = catalogueTooltipRef.current;
      if (el) el.style.display = "none";
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
            hitRadius: star.hitRadius,
            id: star.id,
            profile: getCachedStellarProfile(star.id),
            x: star.screenX,
            y: star.screenY,
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

    function getHoveredCatalogueStar(clientX: number, clientY: number): LandingWorldStarRenderState | null {
      if (!landingStarSpatialHash) return null;
      const pointer = getCanvasPointer(clientX, clientY);
      return findClosestLandingStarHitTarget(
        landingStarSpatialHash,
        pointer.x,
        pointer.y,
        { queryPaddingPx: 12 },
      ) ?? null;
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

      // M22 Phase 3+5 — update hovered-comet state on pointer moves
      // that are actually interacting with the canvas. The pointermove
      // listener is on `document`, so it fires for every move including
      // those over the star tooltip, settings popovers, the chrome,
      // etc. Without this gate we'd render comet hover cards under
      // overlay UI. The same gate is used by the existing
      // hoveredNode / starTooltip pipeline below at line ~5318+.
      //
      // Phase 5: when the cursor IS on the canvas but no longer over a
      // comet, leave cometId set — the render loop will clear it after
      // HOVER_PERSISTENCE_MS so the card persists during cursor transit.
      // Going OUT of the canvas (overlay UI, off-screen) clears
      // immediately so a stuck card never blocks other UI.
      if (isClientPointInsideCanvas(e.clientX, e.clientY)) {
        const targetElement = getPointerTargetElement(e.target, e.clientX, e.clientY);
        const onCanvas = targetElement === canvas;
        const onStarTooltip = Boolean(targetElement?.closest("#starTooltipCard"));
        if (onCanvas && !onStarTooltip) {
          const hovered = findHoveredComet(cometSprites, { x: e.clientX, y: e.clientY });
          if (hovered) {
            cometHoverStateRef.current.cometId = hovered.comet_id;
            cometHoverStateRef.current.lastSeenAtMs = performance.now();
          }
          // else: leave cometId — render loop expires after persistence window.
        } else {
          cometHoverStateRef.current.cometId = null;
        }
      } else {
        cometHoverStateRef.current.cometId = null;
      }

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
        hideCatalogueTooltip();
        return;
      }

      if (!isClientPointInsideCanvas(e.clientX, e.clientY)) {
        hoveredNodeRef.current = -1;
        hoverExpandedRef.current = false;
        clearHoveredCandidate();
        hideStarTooltip();
        hideCatalogueTooltip();
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
        hideCatalogueTooltip();
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
          hideCatalogueTooltip();
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
        hideCatalogueTooltip();
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

      // 2026-05-01 (M21 Phase 5): hover-tooltip for `classical`-tier stars
      // (faculty landmarks + named catalogue stars) is silenced per user
      // critique — the auto-generated Bayer/Flamsteed names + the
      // "Classical star name (Bayer/Flamsteed convention)" footer combined
      // to read as AI slop. Names still exist (deterministic via
      // `generateStarName`) and surface on click via the catalogue
      // inspector / observatory dialog. ADR 0006's tiered-naming policy is
      // preserved at the *data* layer; only the hover surface is removed.
      // See `docs/adr/0006-constellation-design-2d-primary.md` (2026-05-01
      // addendum).
      hideCatalogueTooltip();
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
        // Suppress Star Dive auto-drift during manual pan
        if (starDiveFocusStrengthRef.current > 0) {
          starDivePanSuppressedRef.current = true;
        }
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

      // M14 Phase 2b — forge stars take precedence over user-star
      // hit-tests since they sit in the Skills sector at a fixed
      // ring radius and there is no drag affordance for them. A hit
      // routes to /forge#<id>; the rest of the click pipeline (drag
      // arming, observatory dialog) stays untouched.
      const hitForgeStar = getHitForgeStar(e.clientX, e.clientY);
      if (hitForgeStar) {
        clearHoveredCandidate();
        hideStarTooltip();
        closeConcept();
        router.push(`/forge#${hitForgeStar.id}`);
        return;
      }

      // M22 Phase 3 — clicks on a comet head (within 16px) or its
      // hover card open the article in a new tab. We check head-radius
      // explicitly here (not the 24px hover radius) so a click that
      // *just* triggers hover doesn't also open the URL — the user
      // has to commit. Card clicks honour the saved bbox from the
      // last frame; if it's still drawn, it's still hittable.
      const COMET_CLICK_RADIUS = 16;
      const hitComet = cometSprites.find((c) =>
        Math.hypot(c.x - e.clientX, c.y - e.clientY) <= COMET_CLICK_RADIUS,
      );
      const cardBbox = cometHoverStateRef.current.cardBbox;
      const cardClicked =
        cardBbox &&
        rectsOverlap(
          { x: e.clientX - 1, y: e.clientY - 1, w: 2, h: 2 },
          cardBbox,
        );
      const cometIdToOpen =
        hitComet?.comet_id ??
        (cardClicked ? cometHoverStateRef.current.cometId : null);
      if (cometIdToOpen) {
        const target = cometSprites.find((c) => c.comet_id === cometIdToOpen);
        if (target?.url) {
          clearHoveredCandidate();
          hideStarTooltip();
          closeConcept();
          window.open(target.url, "_blank", "noopener,noreferrer");
          return;
        }
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

      // Audit fix #39: only the explicit "+Add" tool may create new user stars
      // from a canvas click. SELECT mode now never silently materialises stars
      // out of empty space — clicks on empty space fall through to catalogue-
      // star inspection or selection-clear, matching what casual exploration
      // expects.
      const candidate = activeCanvasTool === "add" && (starLimit === null || currentUserStars.length < starLimit)
        ? getHoveredCandidate(e.clientX, e.clientY)
        : null;

      if (candidate) {
        const backgroundCamera = readBackgroundCamera();
        const candidatePoint = getCandidateConstellationPoint(candidate, backgroundCamera);
        const selectedAnchor = getSelectedLinkAnchor(candidatePoint) ?? getNearestUserStar(candidatePoint);
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

      // M12 Phase 1: no add-candidate + no node hit = check for a catalogue-
      // star hit (any star, addable or not). If present, open the Catalogue
      // Star Inspector. The addable path above is untouched — addable stars
      // preserve the existing immediate-promote / armed-tap UX; the inspector
      // only lights up clicks that are currently no-ops.
      const catalogueHit = getHoveredCatalogueStar(e.clientX, e.clientY);
      if (catalogueHit) {
        const worldData = visibleWorldStars.find((ws) => ws.id === catalogueHit.id);
        if (worldData) {
          setInspectedCatalogueStar({
            id: worldData.id,
            name: worldData.catalogueName,
            profile: worldData.profile,
            apparentMagnitude: worldData.apparentMagnitude,
            worldX: worldData.worldX,
            worldY: worldData.worldY,
          });
          armedAddCandidateIdRef.current = null;
          if (currentSelectedStarId) {
            setSelectedUserStarId(null);
            setPendingDetailStar(null);
          }
          closeConcept();
          hideCatalogueTooltip();
          return;
        }
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
      const zoomMultiplier = Math.exp(-e.deltaY * 0.0014);
      const rawNextZoomFactor = currentCamera.zoomFactor * zoomMultiplier;
      const nextZoomFactor = clampBackgroundZoomFactor(rawNextZoomFactor);

      // Dead-zone: skip trivial float noise, but always pass through when
      // the raw value differs from the clamped value (i.e. we are at a boundary
      // and the user is scrolling away from it).
      const relativeChange = Math.abs(nextZoomFactor - currentCamera.zoomFactor) / currentCamera.zoomFactor;
      if (relativeChange < 0.002 && Math.abs(rawNextZoomFactor - nextZoomFactor) < 1e-9) {
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

      constellationCamera.registerScrollVelocity(e.deltaY);
      clearConstellationHoverState();
      setBackgroundZoomTarget(nextZoomFactor);
    }

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && starDiveFocusStrengthRef.current > 0) {
        // Exit Star Dive: zoom back to 1×
        setBackgroundZoomTarget(1);
        starDivePanSuppressedRef.current = false;
        starDiveFocusedStarIdRef.current = null;
        starDiveFocusWorldPosRef.current = null;
        starDiveFocusProfileRef.current = null;
        starDiveFocusNameRef.current = null;
      }
    }

    window.addEventListener("resize", onResize);
    // ResizeObserver covers the cases the window `resize` event misses —
    // iframe parents that grow without firing a window resize on the
    // inner window, devtools-driven viewport emulation, container
    // layouts that reflow without a window-level resize, etc. Without
    // this, the 2D canvas can stay at its initial 300×150 default
    // backing buffer even after the page renders at full viewport,
    // producing ~4× pixelation on everything painted to it.
    const canvasResizeObserver =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => onResize())
        : null;
    canvasResizeObserver?.observe(canvas);
    canvas.addEventListener("pointerdown", onCanvasPointerDown);
    canvas.addEventListener("lostpointercapture", onCanvasLostPointerCapture);
    document.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointercancel", onPointerCancel);
    window.addEventListener("pointerup", onCanvasPress);
    canvas.addEventListener("pointerleave", onPointerLeave);
    window.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("blur", onBlur);

    return () => {
      cancelAnimationFrame(animFrame);
      cometSprites.length = 0;
      absorbBursts.length = 0;
      facultyArtImages.forEach((artState) => {
        artState.image.onload = null;
        artState.image.onerror = null;
      });
      window.removeEventListener("resize", onResize);
      canvasResizeObserver?.disconnect();
      canvas.removeEventListener("pointerdown", onCanvasPointerDown);
      canvas.removeEventListener("lostpointercapture", onCanvasLostPointerCapture);
      document.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointercancel", onPointerCancel);
      window.removeEventListener("pointerup", onCanvasPress);
      canvas.removeEventListener("pointerleave", onPointerLeave);
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("blur", onBlur);
      if (typeof reducedMotionQuery.removeEventListener === "function") {
        reducedMotionQuery.removeEventListener("change", handleReducedMotionChange);
      } else {
        reducedMotionQuery.removeListener(handleReducedMotionChange);
      }
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
          <Link href="/" aria-label="Metis home" className="metis-logo">
            <MetisMark size={32} title="Metis home" />
          </Link>
          {/* Mirror the canonical nav from <PageChrome>. The home page
              uses an inline starscape-styled nav (it can't use PageChrome
              because the constellation takes over the viewport) — but
              the items must match or Forge / Research log become
              invisible from the very first surface a user lands on.
              See M21 #4. */}
          <Link href="/chat" className="metis-nav-link">Chat</Link>
          <Link href="/forge" className="metis-nav-link">Forge</Link>
          <Link href="/settings" className="metis-nav-link">Settings</Link>
          <Link href="/improvements" className="metis-nav-link">Research log</Link>
        </div>
        <div className="metis-nav-right" />
      </nav>

      <FirstRunBanner />

      <NetworkAuditFirstRunCard />

      <LandingStarfieldWebgl
        className="metis-starfield-webgl"
        frameRef={landingStarfieldFrameRef}
      />

      <ShootingStarLayer className="z-[1]" />

      <CosmicAtmosphere
        zoomFactor={backgroundZoomFactor}
        focusFrameRef={atmosphereFocusFrameRef}
        pulseToken={atmospherePulseToken}
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

      {/* M14 Phase 2b — keyboard / screen-reader access path for the
          canvas-rendered technique stars. Visually hidden until
          focused; reveals as a small pinned card in the bottom-right
          when a sighted keyboard user tabs in. Same data source as
          the canvas projection, so it cannot drift out of sync. */}
      <ForgeStarsKeyboardNav stars={forgeStars} />

      <div className="metis-hero-overlay">
        <BorderBeam size="md" colorVariant="sunset" strength={0.8}>
          <div className={`metis-hero-shell ${zoomInteracting || canvasInteractionsLocked ? "is-muted" : ""}`}>
            <h1 className="metis-hero-headline">Discover everything</h1>
          </div>
        </BorderBeam>
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
          <button
            type="button"
            // M24 Phase 4 / Task 4.2 — +Add now opens AddStarDialog instead
            // of entering `tool === "add"` canvas-pick mode. The aria-pressed
            // hookup against activeCanvasTool is preserved for the brief
            // window between the dialog opening and Phase 6's cleanup of
            // the canvas-pick path; the legacy mode is no longer reachable
            // through the UI but the state plumbing still exists.
            className={`metis-zoom-pill-btn metis-zoom-pill-tool-btn ${addStarDialogOpen ? "is-active" : ""}`}
            onClick={() => setAddStarDialogOpen(true)}
            disabled={canvasInteractionsLocked}
            aria-label="Add star"
            aria-pressed={addStarDialogOpen}
            title="Add a star — drop in content and let Metis place it"
          >
            +Add
          </button>
        </div>
        <div className="metis-zoom-pill-actions">
          <button
            type="button"
            className="metis-zoom-pill-btn"
            onClick={() => nudgeBackgroundZoom("out")}
            disabled={canvasInteractionsLocked || backgroundZoomFactor <= MIN_BACKGROUND_ZOOM_FACTOR + 0.001}
            aria-label="Zoom out"
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
            onClick={() => nudgeBackgroundZoom("in")}
            disabled={canvasInteractionsLocked || backgroundZoomFactor >= MAX_BACKGROUND_ZOOM_FACTOR - 0.5}
            aria-label="Zoom in"
          >
            +
          </button>
        </div>
      </div>

      {/* Semantic-link search across the user's own added stars.
          Render gates:
            1. At least one user star — search has nothing to index until
               the user has added content.
            2. Expanded via the FAB Search satellite. Previously this
               pill rendered collapsed at 54px with the inner toggle
               button removed, leaving a blank stub on the canvas
               (audit item, 2026-04-26). The FAB satellite is now the
               sole entry point and the pill mounts only when in use. */}
      {userStars.length > 0 && semanticSearchExpanded && (
        <div className="metis-semantic-search is-expanded">
          <input
            ref={semanticSearchInputRef}
            className="metis-semantic-search-input"
            value={semanticQuery}
            onChange={(event) => setSemanticQuery(event.target.value)}
            placeholder="Type to thread your stars by meaning…"
            aria-label="Semantic star search"
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setSemanticQuery("");
                setSemanticSearchExpanded(false);
              }
            }}
          />
        </div>
      )}

      {/* M12 Phase 3 — Catalogue filter (spectral class chips + magnitude
          slider). Active filter dims (does not hide) non-matching stars to
          20% so the galactic structure stays visible per the plan doc's
          contract. State is URL-hash-persisted (transient view state — not
          in settings). Audit item 8 (2026-04-25) — render gated on the
          FAB's Filters satellite; previously rendered unconditionally. */}
      {filterPanelOpen && (
        <CatalogueFilterPanel
          state={catalogueFilterState}
          onStateChange={setCatalogueFilterState}
        />
      )}

      {(detailsStar || addMessage) && (
        <section id="build-map" className="metis-build-section">
          <div className="metis-build-studio-shell">
            <button
              type="button"
              className="metis-build-dismiss"
              aria-label="Dismiss"
              onClick={() => {
                closeStarDetails({ clearSelection: true, restoreCamera: "none" });
                setAddMessage(null);
              }}
            >
              ✕
            </button>
            {addMessage && (
              <div className={`metis-build-note ${buildNoteTone}`}>{buildNoteMessage}</div>
            )}
            {detailsStar && (
              <div className="metis-star-editor">
                <div className="metis-star-editor-head">{detailsStar.label ?? detailsStar.id}</div>
                <p className="metis-star-editor-copy">{selectedStarSummary}</p>
                {isAutonomousStar(selectedStarActiveIndex?.index_id) && (
                  <p className="metis-star-editor-copy" style={{ color: "rgb(196, 181, 253)", fontSize: "0.75rem" }}>
                    ✦ Added autonomously by METIS
                    {getAutoStarFaculty(selectedStarActiveIndex?.index_id)
                      ? ` · ${getAutoStarFaculty(selectedStarActiveIndex?.index_id)}`
                      : ""}
                  </p>
                )}
              </div>
            )}
          </div>
        </section>
      )}
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

      {/* M12 Phase 1 — Catalogue Star Inspector. Opens on click of a
          non-addable catalogue star (field stars out of adjacency, or any
          catalogue star when the user has no indexed content yet).
          Addable stars keep the existing canvas armed-tap / immediate-
          promote UX untouched.

          Phase 4a — `addable={true}` is now passed unconditionally. The
          inspector path explicitly bypasses the canvas-level adjacency
          gate: a user can attach a document to any catalogue star,
          including a brand-new user's first star anywhere in the galaxy.
          `handlePromoteCatalogueStar` does the world→constellation
          coordinate conversion + faculty inference + addUserStar call. */}
      <CatalogueStarInspector
        open={inspectedCatalogueStar !== null}
        star={inspectedCatalogueStar}
        addable
        onClose={() => setInspectedCatalogueStar(null)}
        onPromote={() => {
          if (inspectedCatalogueStar) {
            handlePromoteCatalogueStar(inspectedCatalogueStar);
          }
        }}
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

      {/* Catalogue star tooltip (lightweight, no actions).
          Phase 1.4: surfaces tiered names per ADR 0006 —
          field = nothing; landmark = classical Bayer/Flamsteed + footer;
          user = user-supplied label in bold. */}
      <div
        ref={catalogueTooltipRef}
        className="metis-catalogue-tooltip"
        data-kind="classical"
        style={{ display: "none", position: "fixed", pointerEvents: "none", zIndex: 50 }}
      >
        <span data-field="name" />
        <span data-field="class" />
        <span data-field="footer" />
      </div>

      {/* Audit item 8 (2026-04-25) — single gold FAB consolidating the
          previous chat-bubble link, the purple semantic-search toggle, and
          the top-right catalogue-search sparkle into one radial menu. The
          Threads-search satellite is gated on the user having added at
          least one star, matching commit 607d802. */}
      <HomeActionFab
        open={fabOpen}
        onOpenChange={setFabOpen}
        filtersOpen={filterPanelOpen}
        onFiltersOpenChange={setFilterPanelOpen}
        searchOpen={semanticSearchExpanded}
        onSearchOpenChange={setSemanticSearchExpanded}
        showSearchSatellite={userStars.length > 0}
      />

      {/* M24 Phase 4 / Task 4.2 — content-first Add flow. The +Add
          tool-pill in the zoom rail opens this dialog instead of the
          legacy canvas-pick mode (which is now unreachable; Phase 6
          deletes the dead code). */}
      <AddStarDialog
        open={addStarDialogOpen}
        onOpenChange={setAddStarDialogOpen}
        onConfirm={handleAddStarConfirm}
      />
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
.metis-logo { display: inline-flex; align-items: center; }
.metis-nav-link {
  font-size: 13px; font-weight: 400;
  color: var(--text-dim); text-decoration: none;
  letter-spacing: 0.5px; transition: color 0.4s ease;
}
.metis-nav-link:hover { color: var(--text-bright); }
.metis-nav-right { display: flex; align-items: center; gap: 32px; }

/* M17 Phase 7 — first-run network-audit discoverability card.
   Fixed top-right, below the nav. Unobtrusive, dismissible, one-shot.

   M21 #18: tightened backdrop separation (darker bg + heavier shadow)
   so the card no longer reads as floating over the Knowledge
   constellation's stars on desktop, and shrunk the max-width on
   narrow viewports so it stops consuming ~25 % of mobile screen real
   estate. */
.metis-network-audit-first-run-card {
  position: fixed;
  top: 72px;
  right: 24px;
  z-index: 45;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 280px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(6, 8, 14, 0.94);
  border: 1px solid rgba(120, 140, 190, 0.24);
  box-shadow:
    0 16px 44px rgba(0, 0, 0, 0.6),
    0 0 0 1px rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(20px) saturate(140%);
  -webkit-backdrop-filter: blur(20px) saturate(140%);
  font-size: 12px;
  color: var(--text-dim);
  letter-spacing: 0.2px;
}
@media (max-width: 640px) {
  .metis-network-audit-first-run-card {
    top: 68px;
    right: 12px;
    left: auto;
    max-width: min(220px, calc(100vw - 24px));
    padding: 10px 12px;
    font-size: 11px;
  }
}
.metis-network-audit-first-run-card-body { display: flex; flex-direction: column; gap: 4px; }
.metis-network-audit-first-run-card-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-bright);
  margin: 0;
}
.metis-network-audit-first-run-card-subtitle { margin: 0; line-height: 1.45; }
.metis-network-audit-first-run-card-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 2px;
}
.metis-network-audit-first-run-card-primary {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-bright);
  text-decoration: none;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid rgba(160, 200, 255, 0.28);
  background: rgba(160, 200, 255, 0.08);
  transition: background 0.25s ease, border-color 0.25s ease;
}
.metis-network-audit-first-run-card-primary:hover {
  background: rgba(160, 200, 255, 0.16);
  border-color: rgba(160, 200, 255, 0.5);
}
.metis-network-audit-first-run-card-dismiss {
  font-size: 12px;
  color: var(--text-dim);
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 6px 8px;
  border-radius: 6px;
  transition: color 0.2s ease;
}
.metis-network-audit-first-run-card-dismiss:hover { color: var(--text-bright); }

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
  cursor: default;
  touch-action: none;
}

.metis-universe[data-canvas-tool="grab"] {
  cursor: grab;
}

.metis-universe[data-canvas-tool="add"] {
  cursor: crosshair;
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
  /* Slide + fade in from above so toasts read as arriving from the
     top frame rather than blinking into existence. */
  animation: metis-toast-enter 280ms cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes metis-toast-enter {
  from {
    transform: translate(-50%, -12px);
    opacity: 0;
  }
  to {
    transform: translateX(-50%);
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .metis-toast {
    animation: none;
  }
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
.metis-semantic-search {
  position: fixed;
  left: 50%;
  bottom: 84px;
  transform: translateX(-50%);
  z-index: 145;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  width: 54px;
  padding: 8px;
  border-radius: 999px;
  border: 1px solid rgba(188, 168, 255, 0.2);
  background: linear-gradient(180deg, rgba(14,19,32,0.92), rgba(8,12,22,0.95));
  box-shadow: 0 14px 30px rgba(0,0,0,0.34);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  overflow: hidden;
  transition: width 340ms cubic-bezier(0.16, 1, 0.3, 1), border-color 260ms ease;
}
.metis-semantic-search.is-expanded {
  width: min(460px, calc(100vw - 36px));
  border-color: rgba(190, 138, 255, 0.38);
}
.metis-semantic-search-toggle {
  width: 36px;
  height: 36px;
  border-radius: 999px;
  border: 1px solid rgba(185, 148, 255, 0.34);
  background: radial-gradient(circle at 30% 30%, rgba(197,145,255,0.44), rgba(104,64,172,0.76));
  color: rgba(245, 239, 255, 0.98);
  cursor: pointer;
  font-size: 14px;
  flex-shrink: 0;
}
.metis-semantic-search-input {
  width: 100%;
  min-width: 0;
  border: none;
  background: transparent;
  color: rgba(235, 239, 250, 0.95);
  opacity: 0;
  font-size: 13px;
  letter-spacing: 0.01em;
  pointer-events: none;
  transition: opacity 240ms ease;
  outline: none;
}
.metis-semantic-search.is-expanded .metis-semantic-search-input {
  opacity: 1;
  pointer-events: auto;
}
.metis-semantic-search-input::placeholder {
  color: rgba(186, 194, 220, 0.66);
}

/* M12 Phase 2 — CATALOGUE SEARCH OVERLAY.
   Mirrors the semantic-search pill shape but anchored top-right with a
   warm (gold) accent rather than the semantic-search purple. Result list
   hangs below the input on expand. */
.metis-catalogue-search {
  position: fixed;
  top: 24px;
  right: 24px;
  z-index: 146;
  display: inline-flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 10px;
  width: 54px;
  padding: 8px;
  border-radius: 22px;
  border: 1px solid rgba(196, 149, 58, 0.22);
  background: linear-gradient(180deg, rgba(14,19,32,0.92), rgba(8,12,22,0.95));
  box-shadow: 0 14px 30px rgba(0,0,0,0.34);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  overflow: hidden;
  transition: width 320ms cubic-bezier(0.16, 1, 0.3, 1), border-color 240ms ease;
}
.metis-catalogue-search.is-expanded {
  width: min(360px, calc(100vw - 48px));
  border-color: rgba(196, 149, 58, 0.48);
}
.metis-catalogue-search-toggle {
  width: 36px;
  height: 36px;
  border-radius: 999px;
  border: 1px solid rgba(196, 149, 58, 0.34);
  background: radial-gradient(circle at 30% 30%, rgba(232, 184, 74, 0.46), rgba(156, 108, 40, 0.74));
  color: rgba(245, 240, 220, 0.98);
  cursor: pointer;
  font-size: 16px;
  flex-shrink: 0;
  line-height: 1;
}
.metis-catalogue-search-input {
  flex: 1 1 auto;
  min-width: 0;
  height: 36px;
  border: none;
  background: transparent;
  color: rgba(235, 239, 250, 0.95);
  opacity: 0;
  font-size: 13px;
  letter-spacing: 0.01em;
  pointer-events: none;
  transition: opacity 240ms ease;
  outline: none;
}
.metis-catalogue-search.is-expanded .metis-catalogue-search-input {
  opacity: 1;
  pointer-events: auto;
}
.metis-catalogue-search-input::placeholder {
  color: rgba(186, 194, 220, 0.58);
}
.metis-catalogue-search-results {
  list-style: none;
  margin: 0;
  padding: 4px 0 0;
  width: 100%;
  max-height: min(60vh, 420px);
  overflow-y: auto;
}
.metis-catalogue-search-result-row {
  list-style: none;
}
.metis-catalogue-search-result {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: transparent;
  text-align: left;
  font: inherit;
  color: inherit;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
}
.metis-catalogue-search-result:hover,
.metis-catalogue-search-result:focus-visible {
  background: rgba(196, 149, 58, 0.12);
  border-color: rgba(196, 149, 58, 0.4);
  outline: none;
}
.metis-catalogue-search-result-name {
  color: rgba(245, 240, 220, 0.98);
  font-size: 13px;
  font-weight: 500;
  font-family: "Space Grotesk", sans-serif;
}
.metis-catalogue-search-result-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  letter-spacing: 0.06em;
  color: rgba(200, 210, 240, 0.7);
  font-variant-numeric: tabular-nums;
}
.metis-catalogue-search-result-kind {
  padding: 2px 6px;
  border-radius: 999px;
  border: 1px solid rgba(196, 149, 58, 0.3);
  background: rgba(196, 149, 58, 0.08);
  color: rgba(232, 184, 74, 0.9);
  text-transform: uppercase;
  font-size: 9px;
  letter-spacing: 0.1em;
}
.metis-catalogue-search-result-class,
.metis-catalogue-search-result-mag {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  opacity: 0.78;
}
.metis-catalogue-search-empty {
  width: 100%;
  padding: 10px 12px;
  font-size: 12px;
  color: rgba(200, 210, 240, 0.6);
  text-align: left;
}

/* M12 Phase 3 — CATALOGUE FILTER PANEL.
   Sits directly below the catalogue-search pill, top-right. Spectral
   class chip row + magnitude slider + reset link. */
.metis-catalogue-filter {
  position: fixed;
  top: 84px;
  right: 24px;
  z-index: 145;
  width: min(320px, calc(100vw - 48px));
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 18px;
  border: 1px solid rgba(196, 149, 58, 0.16);
  background: linear-gradient(180deg, rgba(14, 19, 32, 0.86), rgba(8, 12, 22, 0.92));
  box-shadow: 0 14px 30px rgba(0, 0, 0, 0.32);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  font-size: 12px;
  color: rgba(220, 228, 246, 0.92);
}
.metis-catalogue-filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.metis-catalogue-filter-chip {
  min-width: 28px;
  padding: 4px 9px;
  border-radius: 999px;
  border: 1px solid rgba(196, 149, 58, 0.22);
  background: rgba(255, 255, 255, 0.03);
  color: rgba(220, 228, 246, 0.85);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease;
}
.metis-catalogue-filter-chip:hover {
  background: rgba(196, 149, 58, 0.1);
  border-color: rgba(196, 149, 58, 0.36);
}
.metis-catalogue-filter-chip[aria-pressed="true"] {
  background: rgba(232, 184, 74, 0.18);
  border-color: rgba(232, 184, 74, 0.62);
  color: rgba(245, 240, 220, 1);
}
.metis-catalogue-filter-slider-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.metis-catalogue-filter-slider-text {
  font-size: 11px;
  letter-spacing: 0.04em;
  color: rgba(200, 210, 240, 0.7);
}
.metis-catalogue-filter-slider-label input[type="range"] {
  width: 100%;
  accent-color: rgba(232, 184, 74, 0.95);
}
.metis-catalogue-filter-reset {
  align-self: flex-start;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: transparent;
  color: rgba(220, 228, 246, 0.78);
  font-size: 11px;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
}
.metis-catalogue-filter-reset:hover {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(245, 240, 220, 0.98);
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
.metis-build-dismiss {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(200,210,225,0.12);
  border-radius: 50%;
  background: rgba(10,14,28,0.56);
  color: var(--text-mid);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.metis-build-dismiss:hover {
  border-color: rgba(200,210,225,0.3);
  color: var(--text-bright);
  background: rgba(10,14,28,0.78);
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
.metis-star-tooltip-title[data-name-kind="user"] {
  font-weight: 700;
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

/* CATALOGUE STAR TOOLTIP */
.metis-catalogue-tooltip {
  display: none;
  align-items: flex-start;
  flex-direction: column;
  gap: 2px;
  padding: 6px 10px;
  border-radius: 6px;
  background: rgba(12,18,35,0.88);
  border: 1px solid rgba(196,149,58,0.15);
  backdrop-filter: blur(8px);
  font-size: 11px;
  color: rgba(200,210,240,0.85);
  white-space: nowrap;
}
.metis-catalogue-tooltip .metis-catalogue-tooltip-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.metis-catalogue-tooltip [data-field="name"] {
  font-weight: 500;
  color: rgba(220,225,245,0.95);
}
.metis-catalogue-tooltip[data-kind="user"] [data-field="name"] {
  font-weight: 700;
  color: rgba(245,240,220,1);
}
.metis-catalogue-tooltip [data-field="class"] {
  opacity: 0.7;
  font-family: monospace;
  font-size: 10px;
}
.metis-catalogue-tooltip [data-field="footer"] {
  display: none;
  font-size: 10px;
  font-style: italic;
  opacity: 0.6;
  color: rgba(196,170,108,0.9);
}
.metis-catalogue-tooltip[data-kind="classical"][data-footer="true"] [data-field="footer"] {
  display: inline;
}

/* M12 Phase 1 — CATALOGUE STAR INSPECTOR.
   Edge-anchored side pane, non-modal (constellation stays pannable
   behind). Right-anchored on desktop; slides up from the bottom on
   narrow viewports. Lightweight counterpart to StarDetailsPanel. */
.metis-catalogue-inspector {
  position: fixed;
  top: 50%;
  right: 24px;
  transform: translateY(-50%);
  width: min(360px, calc(100vw - 48px));
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  z-index: 45;
  padding: 20px 22px 22px;
  border-radius: 18px;
  background: rgba(12, 18, 35, 0.92);
  border: 1px solid rgba(196, 149, 58, 0.22);
  box-shadow: 0 18px 48px -16px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(14px);
  color: rgba(220, 228, 246, 0.95);
  font-size: 13px;
  line-height: 1.5;
}
.metis-catalogue-inspector-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.metis-catalogue-inspector-title {
  margin: 0;
  font-size: 16px;
  font-weight: 500;
  letter-spacing: 0.01em;
  color: rgba(245, 240, 220, 1);
  font-family: "Space Grotesk", sans-serif;
}
.metis-catalogue-inspector-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(220, 228, 246, 0.85);
  font-size: 18px;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
}
.metis-catalogue-inspector-close:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(196, 149, 58, 0.3);
}
.metis-catalogue-inspector-preview {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;
}
.metis-catalogue-inspector-preview-disc {
  width: 96px;
  height: 96px;
  border-radius: 50%;
  box-shadow: 0 0 24px -6px rgba(255, 255, 255, 0.22);
}
.metis-catalogue-inspector-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin: 0 0 18px;
}
.metis-catalogue-inspector-field {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
}
.metis-catalogue-inspector-field dt {
  margin: 0;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(200, 210, 240, 0.62);
}
.metis-catalogue-inspector-field dd {
  margin: 6px 0 0;
  font-size: 13px;
  color: rgba(230, 236, 250, 0.98);
  font-variant-numeric: tabular-nums;
}
.metis-catalogue-inspector-foot {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.metis-catalogue-inspector-promote {
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid rgba(196, 149, 58, 0.28);
  background: rgba(196, 149, 58, 0.12);
  color: rgba(245, 240, 220, 1);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
}
.metis-catalogue-inspector-promote:hover:not(:disabled) {
  background: rgba(196, 149, 58, 0.2);
  border-color: rgba(196, 149, 58, 0.5);
}
.metis-catalogue-inspector-promote:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.metis-catalogue-inspector-reason {
  margin: 0;
  font-size: 11px;
  line-height: 1.4;
  color: rgba(200, 210, 240, 0.6);
}

/* CHAT BUBBLE */
.metis-chat-bubble {
  position: fixed; bottom: 32px; right: 32px;
  z-index: 150; width: 48px; height: 48px;
  border-radius: 50%;
  /* Soft warm-gold glow that fades to transparent — replaces the hard
     blue-white lens-flare ring (audit item 5). No fixed-radius edge,
     no border, no inset cobalt disc. */
  background: radial-gradient(circle at 50% 50%, rgba(232,184,74,0.18) 0%, rgba(196,149,58,0.08) 35%, rgba(196,149,58,0) 70%);
  border: none;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: all 0.5s cubic-bezier(0.16,1,0.3,1);
  box-shadow: none;
}
.metis-chat-bubble:hover {
  transform: scale(1.08);
  background: radial-gradient(circle at 50% 50%, rgba(232,184,74,0.28) 0%, rgba(196,149,58,0.12) 40%, rgba(196,149,58,0) 75%);
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

/* HOME-PAGE ACTION FAB — audit item 8 (2026-04-25).
   Container is positioned where the chat-bubble used to live; satellites
   are absolutely-positioned children whose offsets are driven by GSAP at
   runtime. Initial state is opacity:0 + scale(0.4) so they don't flash
   visible on mount before the GSAP effect lands. */
.metis-home-fab-root {
  position: fixed;
  bottom: 32px;
  right: 32px;
  z-index: 150;
  width: 48px;
  height: 48px;
}
.metis-home-fab-trigger.metis-chat-bubble {
  /* Anchor the FAB at 0,0 of the root rather than the chat bubble's own
     fixed positioning. The .metis-chat-bubble class already sets
     position:fixed, so we override with absolute inside the container. */
  position: absolute;
  inset: 0;
  bottom: auto;
  right: auto;
}
.metis-home-fab-trigger.is-open .metis-celestial-star-svg {
  /* Subtle "open" cue — pause the slow spin so the visual settles while
     the menu is up. */
  animation-play-state: paused;
}
.metis-home-fab-satellite {
  position: absolute;
  left: 4px;
  top: 4px;
  width: 40px;
  height: 40px;
  border-radius: 999px;
  border: 1px solid rgba(196, 149, 58, 0.34);
  background: radial-gradient(circle at 30% 30%, rgba(232, 184, 74, 0.32), rgba(156, 108, 40, 0.62));
  color: rgba(245, 240, 220, 0.96);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  /* Hidden until GSAP animates them in. pointer-events:none keeps them
     non-clickable while collapsed. transform-origin matches the FAB
     centre so the spawn/collapse motion looks anchored. */
  opacity: 0;
  transform: scale(0.4);
  pointer-events: none;
  text-decoration: none;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.32);
  transition: background 220ms ease, border-color 220ms ease, box-shadow 220ms ease;
}
.metis-home-fab-satellite:hover,
.metis-home-fab-satellite:focus-visible {
  background: radial-gradient(circle at 30% 30%, rgba(232, 184, 74, 0.5), rgba(196, 149, 58, 0.78));
  border-color: rgba(232, 184, 74, 0.6);
  box-shadow: 0 8px 22px rgba(196, 149, 58, 0.34);
  outline: none;
}
@media (prefers-reduced-motion: reduce) {
  .metis-home-fab-satellite {
    transition: none;
  }
}

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

  /* M21 #11: at narrow viewports the fixed .metis-zoom-pill toolbar
     wraps and can stretch to ~100px tall. The hero headline (Discover
     everything) used to live at bottom 48px of the overlay and
     overlapped the toolbar. Pad enough below it to clear the wrapped
     toolbar plus a small breathing margin. */
  .metis-hero-overlay {
    padding: 0 20px 120px;
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
