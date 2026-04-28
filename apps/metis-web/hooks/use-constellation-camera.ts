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

/**
 * Idle drift — once the user has been silent for `IDLE_DRIFT_DELAY_MS`
 * the camera origin gets a tiny sinusoidal wander so the cosmos never
 * looks frozen. Two superimposed sine waves at incommensurable
 * frequencies give a quasi-Lissajous pattern, no obvious loop.
 */
const IDLE_DRIFT_DELAY_MS = 1_200;
const IDLE_DRIFT_RAMP_MS = 1_800;
const IDLE_DRIFT_AMPLITUDE_X = 14; // world units
const IDLE_DRIFT_AMPLITUDE_Y = 9;
const IDLE_DRIFT_FREQ_X_HZ = 0.018; // ~55s period
const IDLE_DRIFT_FREQ_Y_HZ = 0.013; // ~77s period — mutually irrational

export interface ConstellationCameraConfig {
  /** Easing factor for origin drift when outside dive. 0..1 per frame. */
  baseOriginEase?: number;
  /** Easing factor for zoom change below dive threshold. */
  baseZoomEase?: number;
  /** Easing factor for zoom change once in the dive zone. */
  diveZoomEase?: number;
  /** Cubic-out dive duration (ms), reserved for time-based callers. */
  diveDurationMs?: number;
  /**
   * Opt-in: replace the linear-lerp zoom easing with a slightly under-
   * damped spring so the camera carries a felt sense of weight.
   * Default false to preserve the existing behavior + test contract.
   * The dive-zone path is unaffected — its time-based easing already
   * has its own arc.
   */
  zoomSpring?: boolean;
  /** Spring stiffness when `zoomSpring` is on. */
  zoomSpringStiffness?: number;
  /** Spring damping (0..1) when `zoomSpring` is on. <1 → mild overshoot. */
  zoomSpringDamping?: number;
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
  /**
   * Notify the camera that the user just interacted (drag, wheel,
   * pinch, etc.). Resets the idle-drift timer so the cosmos doesn't
   * fight the user's input.
   */
  notifyInteraction: () => void;
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
  const zoomSpring = config.zoomSpring ?? false;
  const zoomSpringStiffness = config.zoomSpringStiffness ?? 0.085;
  const zoomSpringDamping = config.zoomSpringDamping ?? 0.82;

  const originRef = useRef<Point>({ x: 0, y: 0 });
  const targetOriginRef = useRef<Point>({ x: 0, y: 0 });
  const zoomRef = useRef(1);
  const zoomTargetRef = useRef(1);
  const zoomVelocityRef = useRef(0);
  const scrollVelocityRef = useRef(0);
  const lastInteractionAtMsRef = useRef(0);

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
          zoomVelocityRef.current = 0;
        } else if (zoomSpring && zoomRef.current <= STAR_DIVE_ZOOM_THRESHOLD) {
          // Slightly under-damped spring — gives the camera a felt sense
          // of weight on zoom changes (overshoots ~5–8% and settles).
          // Skipped inside the dive zone so the dive's bespoke time-based
          // arc keeps full control.
          zoomVelocityRef.current =
            zoomVelocityRef.current * zoomSpringDamping
            + zoomDelta * zoomSpringStiffness;
          const nextZoom = zoomRef.current + zoomVelocityRef.current;
          const clampedZoom = clampBackgroundZoomFactor(nextZoom);
          zoomRef.current = clampedZoom;
          // If the spring would have overshot the catalogue clamp,
          // kill the velocity so the spring doesn't keep pushing past
          // the wall — otherwise downstream math (e.g.
          // `Math.log2(zoomFactor + 1)`) would receive a stale velocity
          // hint while the position is pinned.
          if (clampedZoom !== nextZoom) {
            zoomVelocityRef.current = 0;
          }
        } else {
          const zoomEase = zoomRef.current > STAR_DIVE_ZOOM_THRESHOLD
            ? diveZoomEase
            : baseZoomEase;
          zoomRef.current = zoomRef.current + zoomDelta * zoomEase;
          zoomVelocityRef.current = 0;
        }
      } else {
        zoomRef.current = zoomTargetRef.current;
        zoomVelocityRef.current *= 0.65;
        if (Math.abs(zoomVelocityRef.current) < ZOOM_EASE_SETTLE_EPSILON) {
          zoomVelocityRef.current = 0;
        }
      }

      // --- Scroll velocity decay (cheap inertia channel for callers) --------
      scrollVelocityRef.current *= 0.85;
      if (Math.abs(scrollVelocityRef.current) < 1e-4) {
        scrollVelocityRef.current = 0;
      }

      // --- Idle drift: tiny sinusoidal wander so the cosmos never freezes.
      // Skipped under reduced motion. Ramps in over IDLE_DRIFT_RAMP_MS so
      // there's no jarring snap when the user releases input. The drift is
      // additive on top of the eased origin — never overrides user intent.
      let driftX = 0;
      let driftY = 0;
      if (!reducedMotion) {
        const nowMs = typeof performance !== "undefined"
          ? performance.now()
          : Date.now();
        const idleMs = nowMs - lastInteractionAtMsRef.current;
        if (idleMs > IDLE_DRIFT_DELAY_MS) {
          const ramp = Math.min(
            1,
            (idleMs - IDLE_DRIFT_DELAY_MS) / IDLE_DRIFT_RAMP_MS,
          );
          const tSec = nowMs / 1000;
          driftX =
            Math.sin(tSec * IDLE_DRIFT_FREQ_X_HZ * Math.PI * 2)
            * IDLE_DRIFT_AMPLITUDE_X
            * ramp;
          driftY =
            Math.cos(tSec * IDLE_DRIFT_FREQ_Y_HZ * Math.PI * 2)
            * IDLE_DRIFT_AMPLITUDE_Y
            * ramp;
        }
      }

      return {
        x: originRef.current.x + driftX,
        y: originRef.current.y + driftY,
        zoomFactor: zoomRef.current,
      };
    };

    const notifyInteraction = () => {
      lastInteractionAtMsRef.current = typeof performance !== "undefined"
        ? performance.now()
        : Date.now();
    };

    const setTargetOrigin = (point: Point) => {
      targetOriginRef.current = { x: point.x, y: point.y };
      notifyInteraction();
    };

    const setZoomTarget = (zoom: number) => {
      zoomTargetRef.current = clampBackgroundZoomFactor(zoom);
      notifyInteraction();
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
      notifyInteraction();
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
      notifyInteraction,
      easeDive,
    };
  }, [
    baseOriginEase,
    baseZoomEase,
    diveZoomEase,
    diveDurationMs,
    zoomSpring,
    zoomSpringStiffness,
    zoomSpringDamping,
  ]);
}
