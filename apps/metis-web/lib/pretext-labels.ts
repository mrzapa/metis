"use client";

import {
  materializeLineRange,
  prepareWithSegments,
  walkLineRanges,
} from "@chenglou/pretext";
import type { PreparedTextWithSegments } from "@chenglou/pretext";

const SINGLE_LINE_MAX_WIDTH = 100_000;
const DEFAULT_FONT_QUANTUM_PX = 0.5;

type CachedPreparedText = {
  prepared: PreparedTextWithSegments;
  width: number;
};

const preparedTextCache = new Map<string, CachedPreparedText>();

let fallbackMeasureContext: CanvasRenderingContext2D | null = null;

function getFallbackMeasureContext(): CanvasRenderingContext2D | null {
  if (fallbackMeasureContext) {
    return fallbackMeasureContext;
  }

  if (typeof document === "undefined") {
    return null;
  }

  fallbackMeasureContext = document.createElement("canvas").getContext("2d");
  return fallbackMeasureContext;
}

function measureWithPretext(text: string, font: string): number {
  const cacheKey = `${font}::${text}`;
  const cached = preparedTextCache.get(cacheKey);
  if (cached) {
    return cached.width;
  }

  const prepared = prepareWithSegments(text, font);
  let maxWidth = 0;
  walkLineRanges(prepared, SINGLE_LINE_MAX_WIDTH, (line) => {
    if (line.width > maxWidth) {
      maxWidth = line.width;
    }
  });

  preparedTextCache.set(cacheKey, {
    prepared,
    width: maxWidth,
  });

  return maxWidth;
}

function measureWithCanvas(text: string, font: string): number {
  const context = getFallbackMeasureContext();
  if (context) {
    context.font = font;
    return context.measureText(text).width;
  }

  const fontSizeMatch = font.match(/(\d+(?:\.\d+)?)px/i);
  const fontSizePx = fontSizeMatch ? Number.parseFloat(fontSizeMatch[1] ?? "0") : 12;
  return text.length * fontSizePx * 0.6;
}

export function quantizeFontSize(fontSizePx: number, quantumPx = DEFAULT_FONT_QUANTUM_PX): number {
  return Math.round(fontSizePx / quantumPx) * quantumPx;
}

export function buildCanvasFont(
  fontSizePx: number,
  fontFamily: string,
  fontWeight: number | string = "400",
): string {
  return `${fontWeight} ${fontSizePx}px ${fontFamily}`;
}

export function measureSingleLineTextWidth(text: string, font: string): number {
  if (text.length === 0) {
    return 0;
  }

  try {
    return measureWithPretext(text, font);
  } catch {
    return measureWithCanvas(text, font);
  }
}

// -- wrapText (multi-line line-breaking via pretext) --------------------------

/** A single visually-rendered line produced by `wrapText`. */
export interface WrappedLine {
  /** The substring that lies on this line (no trailing whitespace from breaks). */
  text: string;
  /** Pixel width of the line in the supplied font. */
  width: number;
}

/**
 * Cached results from `wrapText`. Keyed on `${font}::${maxWidth}::${text}`.
 *
 * Returned arrays are reused on subsequent calls — callers MUST NOT
 * mutate them. The frozen marker via `Object.freeze` is a defensive
 * extra guard rather than the contract; the contract is "treat as
 * read-only".
 */
const wrapTextCache = new Map<string, ReadonlyArray<WrappedLine>>();

/**
 * Wrap `text` to fit within `maxWidth` pixels in the given canvas
 * `font`, returning each line's text + measured width.
 *
 * First-class consumer of pretext's line-breaking surface — uses
 * `prepareWithSegments` + `walkLineRanges` so the wrap respects:
 *   - grapheme cluster boundaries (no splitting ZWJ emoji or
 *     base+combining sequences),
 *   - bidi ordering (LTR-correct here; mixed-script behaviour is
 *     a deferred risk per the design doc's *BiDi* section),
 *   - word-break rules per the active `Intl.Segmenter` locale.
 *
 * Falls back to a word-boundary heuristic if pretext throws (e.g.
 * `Intl.Segmenter` unavailable). Both paths share the cache.
 *
 * Returns an empty array for empty input.
 */
export function wrapText(
  text: string,
  font: string,
  maxWidth: number,
): ReadonlyArray<WrappedLine> {
  if (text.length === 0) return [];

  const key = `${font}::${maxWidth}::${text}`;
  const cached = wrapTextCache.get(key);
  if (cached) return cached;

  let lines: WrappedLine[];
  try {
    const prepared = prepareWithSegments(text, font);
    lines = [];
    walkLineRanges(prepared, maxWidth, (range) => {
      // walkLineRanges hands back LayoutLineRange ({start: LayoutCursor,
      // end: LayoutCursor, width}); materializeLineRange resolves the
      // cursors to a real substring with leading/trailing wrap-whitespace
      // already stripped per pretext's rules.
      const line = materializeLineRange(prepared, range);
      lines.push({ text: line.text, width: line.width });
    });
  } catch {
    lines = wrapTextWordBoundaryFallback(text, font, maxWidth);
  }

  Object.freeze(lines);
  wrapTextCache.set(key, lines);
  return lines;
}

/**
 * Word-boundary heuristic used when pretext is unavailable. Greedy
 * left-to-right packing on whitespace-split tokens; produces visually
 * acceptable LTR wrap. Does not handle CJK or other languages without
 * inter-word whitespace — but neither does the heuristic in
 * `measureWithCanvas`, so callers already accept the same
 * platform-floor behaviour.
 */
function wrapTextWordBoundaryFallback(
  text: string,
  font: string,
  maxWidth: number,
): WrappedLine[] {
  const words = text.split(/(\s+)/).filter((s) => s.length > 0);
  const out: WrappedLine[] = [];
  let curr = "";
  let currW = 0;
  for (const w of words) {
    const trial = curr + w;
    const trialW = measureSingleLineTextWidth(trial, font);
    if (trialW <= maxWidth || curr.length === 0) {
      curr = trial;
      currW = trialW;
    } else {
      out.push({ text: curr.trimEnd(), width: measureSingleLineTextWidth(curr.trimEnd(), font) });
      curr = w.trimStart();
      currW = measureSingleLineTextWidth(curr, font);
    }
  }
  if (curr.length > 0) out.push({ text: curr.trimEnd(), width: currW });
  return out;
}