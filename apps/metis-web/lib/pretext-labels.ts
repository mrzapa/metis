"use client";

import { prepareWithSegments, walkLineRanges } from "@chenglou/pretext";
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