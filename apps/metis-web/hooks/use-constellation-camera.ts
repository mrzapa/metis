"use client";

import { useMemo, useRef } from "react";
import type { MutableRefObject } from "react";
import {
  clampBackgroundZoomFactor,
  STAR_DIVE_ZOOM_THRESHOLD,
  type BackgroundCameraState,
  type Point,
} from "@/lib/constellation-home";

/**
 * Phase-2 cinematic 2D camera. Owns the four refs that used to live in
 * `page.tsx` (origin, target origin, zoom, target zoom) and exposes a single
 * per-frame `stepCamera` call that applies the easing we previously ran inline
 * in the render loop.
 *
 * The hook intentionally stays side-effect-free and `useMemo`-stable so
 * callers can read the refs directly (existing code patterns) *or* drive the
 * camera through the returned imperative API.
 */

/** Default cubic-out dive duration (ms) per ADR 0006 Phase 2.2. */
export const CONSTELLATION_DIVE_DURATION_MS = 700;

/** Galaxy-view pullback threshold (zoom factor below which we tug toward origin). */
const GALAXY_PULLBACK_ZOOM = 0.15;
const GALAXY_PULLBACK_RANGE = 0.13;
const GALAXY_PULLBACK_MAX_STRENGTH = 0.06;

const ORIGIN_EASE_SETTLE_EPSILON = 0.05;
const ZOOM_EASE_SETTLE_EPSILON = 0.0005;

const BASE_ORIGIN_EASE = 0.14;
const BASE_ZOOM_EASE = 0.12;
const DIVE_ZOOM_EASE = 0.18;
/** Additional origin pull once dive focus takes over (scales 0→focusStrength). */
const DIVE_ORIGIN_EASE_BOOST = 0.08;

export interface ConstellationCameraConfig {
  /** Easing factor for origin drift when outside dive. 0..1 per frame. */
  baseOriginEase?: number;
  /** Easing factor for zoom change below dive threshold. */
  baseZoomEase?: number;
  /** Easing factor for zoom change once in the dive zone. */
  diveZoomEase?: number;
  /** Cubic-out dive duration (ms), reserved for time-based callers. */
  diveDurationMs?: number;
}

export interface ConstellationCameraStepOptions {
  reducedMotion: boolean;
  /** Current dive focus strength (0..1). Drives origin-ease boost. */
  focusStrength?: number;
}

export interface ConstellationCameraHandle {
  originRef: MutableRefObject<Point>;
  targetOriginRef: MutableRefObject<Point>;
  zoomRef: MutableRefObject<number>;
  zoomTargetRef: MutableRefObject<number>;
  /** Latest wheel delta (resets each frame via decay). */
  scrollVelocityRef: MutableRefObject<number>;
  stepCamera: (options: ConstellationCameraStepOptions) => BackgroundCameraState;
  setTargetOrigin: (point: Point) => void;
  setZoomTarget: (zoom: number) => void;
  jumpTo: (snapshot: { x: number; y: number; zoomFactor: number }) => void;
  getState: () => BackgroundCameraState;
  getTargetState: () => BackgroundCameraState;
  registerScrollVelocity: (delta: number) => void;
  /** Cubic-out easing in 0..1 for a time-based dive. */
  easeDive: (elapsedMs: number, durationMs?: number) => number;
}

/**
 * Clamp a value to [0, 1] and apply the cubic-out curve used by dive
 * animations. Exposed standalone so callers and tests can reference it.
 */
export function cubicOutEasing(t: number): number {
  const clamped = t < 0 ? 0 : t > 1 ? 1 : t;
  const f = 1 - clamped;
  return 1 - f * f * f;
}

export function useConstellationCamera(
  config: ConstellationCameraConfig = {},
): ConstellationCameraHandle {
  const baseOriginEase = config.baseOriginEase ?? BASE_ORIGIN_EASE;
  const baseZoomEase = config.baseZoomEase ?? BASE_ZOOM_EASE;
  const diveZoomEase = config.diveZoomEase ?? DIVE_ZOOM_EASE;
  const diveDurationMs = config.diveDurationMs ?? CONSTELLATION_DIVE_DURATION_MS;

  const originRef = useRef<Point>({ x: 0, y: 0 });
  const targetOriginRef = useRef<Point>({ x: 0, y: 0 });
  const zoomRef = useRef(1);
  const zoomTargetRef = useRef(1);
  const scrollVelocityRef = useRef(0);

  return useMemo<ConstellationCameraHandle>(() => {
    const stepCamera = ({
      reducedMotion,
      focusStrength = 0,
    }: ConstellationCameraStepOptions): BackgroundCameraState => {
      // --- Origin easing ----------------------------------------------------
      const originDeltaX = targetOriginRef.current.x - originRef.current.x;
      const originDeltaY = targetOriginRef.current.y - originRef.current.y;
      if (
        Math.abs(originDeltaX) > ORIGIN_EASE_SETTLE_EPSILON
        || Math.abs(originDeltaY) > ORIGIN_EASE_SETTLE_EPSILON
      ) {
        if (reducedMotion) {
          originRef.current = { ...targetOriginRef.current };
        } else {
          const boost = focusStrength > 0 ? focusStrength * DIVE_ORIGIN_EASE_BOOST : 0;
          const ease = Math.min(1, baseOriginEase + boost);
          originRef.current = {
            x: originRef.current.x + originDeltaX * ease,
            y: originRef.current.y + originDeltaY * ease,
          };
        }
      } else {
        originRef.current = { ...targetOriginRef.current };
      }

      // --- Galaxy pullback --------------------------------------------------
      const zoomNow = zoomRef.current;
      if (zoomNow < GALAXY_PULLBACK_ZOOM) {
        const pullStrength = Math.min(
          1,
          (GALAXY_PULLBACK_ZOOM - zoomNow) / GALAXY_PULLBACK_RANGE,
        ) * GALAXY_PULLBACK_MAX_STRENGTH;
        originRef.current = {
          x: originRef.current.x * (1 - pullStrength),
          y: originRef.current.y * (1 - pullStrength),
        };
        targetOriginRef.current = {
          x: targetOriginRef.current.x * (1 - pullStrength),
          y: targetOriginRef.current.y * (1 - pullStrength),
        };
      }

      // --- Zoom easing ------------------------------------------------------
      const zoomDelta = zoomTargetRef.current - zoomRef.current;
      if (Math.abs(zoomDelta) > ZOOM_EASE_SETTLE_EPSILON) {
        if (reducedMotion) {
          zoomRef.current = zoomTargetRef.current;
        } else {
          const zoomEase = zoomRef.current > STAR_DIVE_ZOOM_THRESHOLD
            ? diveZoomEase
            : baseZoomEase;
          zoomRef.current = zoomRef.current + zoomDelta * zoomEase;
        }
      } else {
        zoomRef.current = zoomTargetRef.current;
      }

      // --- Scroll velocity decay (cheap inertia channel for callers) --------
      scrollVelocityRef.current *= 0.85;
      if (Math.abs(scrollVelocityRef.current) < 1e-4) {
        scrollVelocityRef.current = 0;
      }

      return {
        x: originRef.current.x,
        y: originRef.current.y,
        zoomFactor: zoomRef.current,
      };
    };

    const setTargetOrigin = (point: Point) => {
      targetOriginRef.current = { x: point.x, y: point.y };
    };

    const setZoomTarget = (zoom: number) => {
      zoomTargetRef.current = clampBackgroundZoomFactor(zoom);
    };

    const jumpTo = (snapshot: { x: number; y: number; zoomFactor: number }) => {
      const clampedZoom = clampBackgroundZoomFactor(snapshot.zoomFactor);
      originRef.current = { x: snapshot.x, y: snapshot.y };
      targetOriginRef.current = { x: snapshot.x, y: snapshot.y };
      zoomRef.current = clampedZoom;
      zoomTargetRef.current = clampedZoom;
    };

    const getState = (): BackgroundCameraState => ({
      x: originRef.current.x,
      y: originRef.current.y,
      zoomFactor: zoomRef.current,
    });

    const getTargetState = (): BackgroundCameraState => ({
      x: targetOriginRef.current.x,
      y: targetOriginRef.current.y,
      zoomFactor: zoomTargetRef.current,
    });

    const registerScrollVelocity = (delta: number) => {
      scrollVelocityRef.current = delta;
    };

    const easeDive = (elapsedMs: number, durationMs = diveDurationMs) => {
      if (durationMs <= 0) return 1;
      return cubicOutEasing(elapsedMs / durationMs);
    };

    return {
      originRef,
      targetOriginRef,
      zoomRef,
      zoomTargetRef,
      scrollVelocityRef,
      stepCamera,
      setTargetOrigin,
      setZoomTarget,
      jumpTo,
      getState,
      getTargetState,
      registerScrollVelocity,
      easeDive,
    };
  }, [baseOriginEase, baseZoomEase, diveZoomEase, diveDurationMs]);
}
