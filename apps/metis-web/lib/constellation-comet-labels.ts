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
export function placeCharactersAlongPath(
  label: string,
  font: string,
  tail: ReadonlyArray<TailPoint>,
): PlacedChar[] {
  if (tail.length < 2 || label.length === 0) return [];

  const arcLengths = computeArcLengths(tail);
  const total = arcLengths[arcLengths.length - 1];

  const out: PlacedChar[] = [];
  let s = 0;
  for (const ch of label) {
    const w = measureSingleLineTextWidth(ch, font);
    const center = s + w / 2;
    if (center > total) break;
    const sample = samplePathAt(arcLengths, tail, center);
    out.push({ char: ch, x: sample.x, y: sample.y, tangent: sample.tangent });
    s += w;
  }
  return out;
}

// -- Canvas rendering ---------------------------------------------------------

const LABEL_FONT_FAMILY =
  '"Space Grotesk", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
const LABEL_FONT_SIZE_PX = 11;
const LABEL_FONT_WEIGHT = 400;
/** Phase 1 ambient opacity multiplier; multiplied by `comet.opacity`. */
const LABEL_BASE_OPACITY = 0.65;

export interface DrawCometLabelOpts {
  /** Reserved for Phase 2 fade animations. Phase 1 ignores it. */
  ts?: number;
}

/**
 * Render a comet's full title as path-text along its tail.
 *
 * Phase 1 contract: per-character position from `placeCharactersAlongPath`,
 * per-character rotation from raw segment tangent. No truncation, no
 * orientation flip, no collision suppression, no reduced-motion clamp,
 * no faculty-color tweaks beyond a constant opacity multiplier.
 *
 * `tailHistory` from `tickComet` is in oldest-first order (each tick
 * pushes the current head to the END of the array; `shift()` drops the
 * oldest from the FRONT). `placeCharactersAlongPath` walks from index
 * 0 outward, so we reverse the input here so characters lay along the
 * trail from the head back into the past.
 */
export function drawCometLabel(
  ctx: CanvasRenderingContext2D,
  comet: CometData,
  _opts: DrawCometLabelOpts = {},
): void {
  if (comet.tailHistory.length < 2 || comet.title.length === 0) return;

  // tailHistory: [oldest, ..., current_head]. We want head-first for layout.
  const tail: TailPoint[] = comet.tailHistory
    .slice()
    .reverse()
    .map((p) => ({ x: p.x, y: p.y }));

  const font = buildCanvasFont(LABEL_FONT_SIZE_PX, LABEL_FONT_FAMILY, LABEL_FONT_WEIGHT);
  const placed = placeCharactersAlongPath(comet.title, font, tail);
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
