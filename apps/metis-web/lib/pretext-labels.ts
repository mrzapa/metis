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
 * Both the outer array and each `{text, width}` entry are
 * `Object.freeze`d before being inserted into the cache — accidental
 * mutation by a caller would otherwise corrupt subsequent reads.
 * Returned values are typed `ReadonlyArray<Readonly<WrappedLine>>`
 * so the contract is also visible to TypeScript.
 */
const wrapTextCache = new Map<string, ReadonlyArray<Readonly<WrappedLine>>>();

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
): ReadonlyArray<Readonly<WrappedLine>> {
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

  // Deep-freeze: outer array AND each line. Without freezing the
  // line objects, a caller could mutate `result[0].text` and corrupt
  // every subsequent cache hit on the same key.
  for (const line of lines) Object.freeze(line);
  Object.freeze(lines);
  const frozen = lines as ReadonlyArray<Readonly<WrappedLine>>;
  wrapTextCache.set(key, frozen);
  return frozen;
}

/**
 * Word-boundary heuristic used when pretext is unavailable. Greedy
 * left-to-right packing on whitespace-split tokens; produces visually
 * acceptable LTR wrap. Does not handle CJK or other languages without
 * inter-word whitespace — but neither does the heuristic in
 * `measureWithCanvas`, so callers already accept the same
 * platform-floor behaviour.
 *
 * Hard-break path: when a single token (no whitespace, e.g. a long
 * URL) exceeds `maxWidth` on its own, code-point-split it into
 * pieces that each fit. Without this, the fallback would emit a
 * line wider than `maxWidth`, violating the function's contract.
 * `Array.from(token)` walks code points (handles surrogate pairs);
 * combining marks may still split, which is the same compromise
 * the surrounding heuristics make.
 */
function wrapTextWordBoundaryFallback(
  text: string,
  font: string,
  maxWidth: number,
): WrappedLine[] {
  const words = text.split(/(\s+)/).filter((s) => s.length > 0);
  const out: WrappedLine[] = [];
  let curr = "";

  const pushCurr = () => {
    const trimmed = curr.trimEnd();
    if (trimmed.length > 0) {
      out.push({ text: trimmed, width: measureSingleLineTextWidth(trimmed, font) });
    }
    curr = "";
  };

  for (const w of words) {
    const trial = curr + w;
    const trialW = measureSingleLineTextWidth(trial, font);
    if (trialW <= maxWidth) {
      curr = trial;
      continue;
    }
    if (curr.length === 0) {
      // Lone token exceeds the budget on its own. Code-point-split it
      // into chunks that each fit, emitting a line per chunk.
      for (const piece of hardBreakOverlongToken(w, font, maxWidth)) {
        out.push(piece);
      }
      continue;
    }
    // Otherwise: flush the current line and re-try the token alone.
    pushCurr();
    const trimmed = w.trimStart();
    const trimmedW = measureSingleLineTextWidth(trimmed, font);
    if (trimmedW <= maxWidth) {
      curr = trimmed;
    } else {
      for (const piece of hardBreakOverlongToken(trimmed, font, maxWidth)) {
        out.push(piece);
      }
    }
  }
  pushCurr();
  return out;
}

/**
 * Split a single token wider than `maxWidth` into the longest
 * code-point prefixes that each fit. Returns one WrappedLine per
 * piece. Used by `wrapTextWordBoundaryFallback` to respect its
 * width contract for whitespace-free overlong tokens (URLs etc.).
 */
function hardBreakOverlongToken(
  token: string,
  font: string,
  maxWidth: number,
): WrappedLine[] {
  const pieces: WrappedLine[] = [];
  const codePoints = Array.from(token);
  let buf = "";
  let bufW = 0;
  for (const cp of codePoints) {
    const trial = buf + cp;
    const trialW = measureSingleLineTextWidth(trial, font);
    if (trialW <= maxWidth || buf.length === 0) {
      buf = trial;
      bufW = trialW;
    } else {
      pieces.push({ text: buf, width: bufW });
      buf = cp;
      bufW = measureSingleLineTextWidth(buf, font);
    }
  }
  if (buf.length > 0) pieces.push({ text: buf, width: bufW });
  return pieces;
}