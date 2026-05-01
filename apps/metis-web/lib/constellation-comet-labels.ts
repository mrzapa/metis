"use client";

import type { CometData } from "./comet-types";
import { buildCanvasFont, measureSingleLineTextWidth } from "./pretext-labels";

/**
 * Path-text rendering for comet headline labels.
 *
 * Phase 1 (this file's current state) ships a tracer-bullet path-text
 * implementation: per-character position by arc length walk along the
 * comet's tail polyline, raw per-character spline tangent, no
 * truncation/flip/collision/reduced-motion mitigations. Those land in
 * Phase 2.
 *
 * See `docs/plans/2026-05-01-comet-headline-labels-design.md` for the
 * full design and `docs/plans/2026-05-01-comet-headline-labels-implementation.md`
 * for the phase boundaries.
 */

export interface TailPoint {
  x: number;
  y: number;
}

/**
 * Cumulative arc length along the tail-history polyline.
 *
 * Indexing matches the input array's order: index 0 corresponds to the
 * first point in `tail`, and the returned value at index `i` is the total
 * length of the polyline from index 0 up to index `i`.
 *
 * @param tail Polyline points in any consistent order. Empty allowed.
 */
export function computeArcLengths(tail: ReadonlyArray<TailPoint>): number[] {
  if (tail.length === 0) return [];
  const out: number[] = [0];
  for (let i = 1; i < tail.length; i += 1) {
    const dx = tail[i].x - tail[i - 1].x;
    const dy = tail[i].y - tail[i - 1].y;
    out.push(out[i - 1] + Math.hypot(dx, dy));
  }
  return out;
}

export interface PathSample {
  x: number;
  y: number;
  /** Tangent angle in radians, measured from +x axis. */
  tangent: number;
}

/**
 * Sample the polyline at a given arc length `s`.
 *
 * Linear interpolation within the segment that contains `s`. If `s` is
 * past the polyline's total length, clamps to the last point and uses
 * the last segment's tangent. Empty / single-point tails degrade to a
 * zero-tangent origin sample.
 *
 * @param arcLengths Cumulative arc lengths from `computeArcLengths`.
 * @param tail Polyline points; must be the same array used to compute `arcLengths`.
 * @param s Arc length from index 0 outward.
 */
export function samplePathAt(
  arcLengths: ReadonlyArray<number>,
  tail: ReadonlyArray<TailPoint>,
  s: number,
): PathSample {
  if (tail.length === 0) return { x: 0, y: 0, tangent: 0 };
  if (tail.length === 1) return { x: tail[0].x, y: tail[0].y, tangent: 0 };

  // Find the segment [i, i+1] that contains s. If s is past the end,
  // clamp to the last segment.
  let i = arcLengths.length - 2;
  for (let k = 0; k < arcLengths.length - 1; k += 1) {
    if (s <= arcLengths[k + 1]) {
      i = k;
      break;
    }
  }

  const segLen = arcLengths[i + 1] - arcLengths[i];
  const tRaw = segLen === 0 ? 0 : (s - arcLengths[i]) / segLen;
  const t = Math.min(1, Math.max(0, tRaw));
  const dx = tail[i + 1].x - tail[i].x;
  const dy = tail[i + 1].y - tail[i].y;
  return {
    x: tail[i].x + dx * t,
    y: tail[i].y + dy * t,
    tangent: Math.atan2(dy, dx),
  };
}

/** Half-window used by `smoothedTangentAt` to compute the secant tangent. */
const TANGENT_SMOOTHING_DELTA_PX = 5;

/** Enter the flipped state when |tangent| crosses 95° (hysteresis upper bound). */
const FLIP_ENTER_RAD = (95 * Math.PI) / 180;
/** Exit the flipped state when |tangent| drops to 90° or below (hysteresis lower bound). */
const FLIP_EXIT_RAD = Math.PI / 2;

/**
 * Decide whether a label baseline should be flipped 180° given the
 * current dominant tangent.
 *
 * Hysteresis prevents flicker when the tangent oscillates near the
 * threshold:
 *   - From unflipped: only flip once `|tangent| > 95°` (the enter band).
 *   - From flipped:   only unflip once `|tangent| ≤ 90°` (the exit band).
 *
 * Tangents are taken in their full [-π, π] range; `Math.abs` collapses
 * the symmetric pair (e.g. ±100° both indicate upside-down content).
 */
export function shouldFlipOrientation(tangent: number, currentlyFlipped: boolean): boolean {
  const mag = Math.abs(tangent);
  if (currentlyFlipped) {
    return mag > FLIP_EXIT_RAD;
  }
  return mag > FLIP_ENTER_RAD;
}

/**
 * Tangent at arc length `s`, smoothed via central finite difference.
 *
 * Where `samplePathAt(...).tangent` jumps abruptly at segment boundaries
 * (because each segment has its own constant tangent), this function
 * returns the angle of the secant from `s - δ` to `s + δ` along the
 * polyline. The secant is continuous in `s`, so character orientations
 * along the trail vary smoothly even at corners.
 *
 * Near the polyline endpoints (`s < δ` or `s > total - δ`) the window
 * clamps to the available range, degrading to a one-sided difference.
 *
 * Sub-2-point tails return 0 (no segment to take a tangent of).
 */
export function smoothedTangentAt(
  arcLengths: ReadonlyArray<number>,
  tail: ReadonlyArray<TailPoint>,
  s: number,
): number {
  if (tail.length < 2) return 0;
  const total = arcLengths[arcLengths.length - 1];
  const s0 = Math.max(0, s - TANGENT_SMOOTHING_DELTA_PX);
  const s1 = Math.min(total, s + TANGENT_SMOOTHING_DELTA_PX);
  if (s1 - s0 <= 0) {
    // Both endpoints clamp to the same place (zero-length tail or
    // s exactly at a degenerate point) — fall back to the raw tangent.
    return samplePathAt(arcLengths, tail, s).tangent;
  }
  const p0 = samplePathAt(arcLengths, tail, s0);
  const p1 = samplePathAt(arcLengths, tail, s1);
  return Math.atan2(p1.y - p0.y, p1.x - p0.x);
}

export interface PlacedChar {
  char: string;
  x: number;
  y: number;
  /** Tangent angle in radians at this character's center. */
  tangent: number;
}

/**
 * Place each character of `label` along the polyline `tail`, walking
 * from index 0 outward. Each character occupies its measured advance
 * width; the character's center is at the cumulative arc-length offset.
 *
 * Phase 1: raw per-character tangent from `samplePathAt`. Phase 2 will
 * smooth this with a Catmull-Rom spline + temporal lowpass.
 *
 * Phase 1: per-character measurement via `measureSingleLineTextWidth`.
 * That sums per-glyph widths and ignores kerning between glyphs. For
 * tracer-bullet purposes that's fine — characters look slightly looser
 * than CSS-rendered text but consistently so. Phase 3's `wrapText` adds
 * pretext's segment cursors which give kerning-aware advances.
 *
 * Characters that don't fit in the remaining arc length are dropped
 * (Phase 1: silently; Phase 2 adds an ellipsis fallback under the
 * truncation budget).
 */
export interface PlaceCharactersOpts {
  /**
   * When true, every character's tangent is rotated by π so the label
   * reads the other way along the path. Used by `drawCometLabel` when
   * `shouldFlipOrientation(...)` is on, which keeps text right-side-up
   * for tails diving down-and-left across the screen.
   */
  flipped?: boolean;
}

export function placeCharactersAlongPath(
  label: string,
  font: string,
  tail: ReadonlyArray<TailPoint>,
  opts: PlaceCharactersOpts = {},
): PlacedChar[] {
  if (tail.length < 2 || label.length === 0) return [];

  const arcLengths = computeArcLengths(tail);
  const total = arcLengths[arcLengths.length - 1];
  const flipOffset = opts.flipped ? Math.PI : 0;

  const out: PlacedChar[] = [];
  let s = 0;
  for (const grapheme of segmentGraphemes(label)) {
    const w = measureSingleLineTextWidth(grapheme, font);
    const center = s + w / 2;
    if (center > total) break;
    const sample = samplePathAt(arcLengths, tail, center);
    // Position from the polyline-linear sample; tangent from the
    // secant-smoothed window so character rotations vary continuously
    // even at segment corners.
    const tangent = smoothedTangentAt(arcLengths, tail, center) + flipOffset;
    out.push({ char: grapheme, x: sample.x, y: sample.y, tangent });
    s += w;
  }
  return out;
}

/**
 * Iterate `label` by user-visible characters (grapheme clusters), not
 * Unicode code points. ZWJ emoji like 👨‍👩‍👧 (5 code points, 1 grapheme)
 * and base+combining sequences like "é" (e + U+0301, 2 code points, 1
 * grapheme) yield ONE entry per visible character.
 *
 * Falls back to per-code-point iteration if `Intl.Segmenter` is
 * unavailable. Pretext requires `Intl.Segmenter`, so any browser/runtime
 * that successfully runs `lib/pretext-labels.ts` will hit the
 * Segmenter path.
 */
function segmentGraphemes(label: string): string[] {
  if (typeof Intl !== "undefined" && typeof Intl.Segmenter === "function") {
    const seg = new Intl.Segmenter(undefined, { granularity: "grapheme" });
    const out: string[] = [];
    for (const { segment } of seg.segment(label)) {
      out.push(segment);
    }
    return out;
  }
  // Code-point fallback (no grapheme awareness; ZWJ sequences will split).
  return Array.from(label);
}

/**
 * Build a head-first polyline for label layout from a comet's current
 * position plus its tail history.
 *
 * `tickComet` in `constellation-comets.ts` records each frame's
 * pre-update `comet.x/y` into `tailHistory` BEFORE advancing the
 * position. So at render time:
 *   - `comet.x/y` = the head position the head sprite is drawn at.
 *   - `tailHistory[length - 1]` = the position one frame ago.
 * The existing `drawComets` bridges this gap with `ctx.lineTo(comet.x,
 * comet.y)` after stroking the recorded history; the label path needs
 * the same bridge or characters render lagging the head.
 *
 * Output is head-first (index 0 = current head, last index = oldest).
 * Returned array is a copy — callers may mutate without affecting the
 * comet.
 */
export function buildHeadFirstPath(
  comet: Pick<CometData, "x" | "y" | "tailHistory">,
): TailPoint[] {
  const path: TailPoint[] = [{ x: comet.x, y: comet.y }];
  // tailHistory order: oldest first, most-recent last. We want
  // most-recent first after the current head, so iterate in reverse.
  for (let i = comet.tailHistory.length - 1; i >= 0; i -= 1) {
    path.push({ x: comet.tailHistory[i].x, y: comet.tailHistory[i].y });
  }
  return path;
}

// -- Canvas rendering ---------------------------------------------------------

const LABEL_FONT_FAMILY =
  '"Space Grotesk", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
const LABEL_FONT_SIZE_PX = 11;
const LABEL_FONT_WEIGHT = 400;
/** Phase 1 ambient opacity multiplier; multiplied by `comet.opacity`. */
const LABEL_BASE_OPACITY = 0.65;

/**
 * Per-comet flip state. Module-level so that hysteresis carries across
 * frames without the caller having to plumb state. Cleaned by
 * `pruneCometLabelState(activeIds)` whenever the active comet set
 * shrinks; otherwise grows monotonically.
 */
const flipState = new Map<string, boolean>();

/**
 * Drop flip-state entries for comets no longer in the active set.
 * Caller should invoke once per frame (or whenever the active comet
 * list changes) with the currently-rendered comet IDs to prevent the
 * module-level Map from leaking across long sessions.
 */
export function pruneCometLabelState(activeCometIds: Iterable<string>): void {
  const active = new Set<string>();
  for (const id of activeCometIds) active.add(id);
  for (const id of flipState.keys()) {
    if (!active.has(id)) flipState.delete(id);
  }
}

/**
 * Render a comet's full title as path-text along its tail.
 *
 * Phase 2: spatially-smoothed per-character tangent (Task 2.1), and
 * orientation flip with hysteresis tracked per `comet.comet_id`
 * (Task 2.3). When `|dominant tangent| > 95°` the label baseline flips
 * 180° so text stays right-side-up; it unflips when `|dominant tangent|
 * ≤ 90°`. Hysteresis prevents flicker as a comet's trajectory wobbles
 * near the threshold.
 *
 * `tailHistory` from `tickComet` is in oldest-first order. The current
 * `comet.x/y` is prepended via `buildHeadFirstPath` so the label starts
 * at the rendered head, not one frame behind it.
 */
export function drawCometLabel(
  ctx: CanvasRenderingContext2D,
  comet: CometData,
): void {
  if (comet.title.length === 0) return;

  const tail = buildHeadFirstPath(comet);
  if (tail.length < 2) return;

  // Dominant tangent: use the path's mid-arc tangent as a stable proxy
  // for "which way is this label pointing right now." Cheaper than
  // averaging per-char tangents and equivalent for hysteresis decisions.
  const arcLengths = computeArcLengths(tail);
  const total = arcLengths[arcLengths.length - 1];
  const dominantTangent = smoothedTangentAt(arcLengths, tail, total / 2);

  const wasFlipped = flipState.get(comet.comet_id) ?? false;
  const isFlipped = shouldFlipOrientation(dominantTangent, wasFlipped);
  if (isFlipped !== wasFlipped) flipState.set(comet.comet_id, isFlipped);

  const font = buildCanvasFont(LABEL_FONT_SIZE_PX, LABEL_FONT_FAMILY, LABEL_FONT_WEIGHT);
  const placed = placeCharactersAlongPath(comet.title, font, tail, { flipped: isFlipped });
  if (placed.length === 0) return;

  const [r, g, b] = comet.color;
  const alpha = LABEL_BASE_OPACITY * comet.opacity;

  ctx.save();
  ctx.font = font;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${alpha})`;
  for (const p of placed) {
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(p.tangent);
    ctx.fillText(p.char, 0, 0);
    ctx.restore();
  }
  ctx.restore();
}
