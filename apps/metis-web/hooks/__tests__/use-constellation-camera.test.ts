import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  CONSTELLATION_DIVE_DURATION_MS,
  cubicOutEasing,
  useConstellationCamera,
} from "@/hooks/use-constellation-camera";

describe("cubicOutEasing", () => {
  it("clamps to [0, 1]", () => {
    expect(cubicOutEasing(-1)).toBe(0);
    expect(cubicOutEasing(2)).toBe(1);
  });

  it("matches the cubic-out curve at key control points", () => {
    expect(cubicOutEasing(0)).toBe(0);
    expect(cubicOutEasing(1)).toBe(1);
    // Cubic-out is 1 - (1-t)^3, so t=0.5 → 0.875.
    expect(cubicOutEasing(0.5)).toBeCloseTo(0.875, 5);
  });
});

describe("useConstellationCamera", () => {
  it("initialises refs at origin with zoom 1", () => {
    const { result } = renderHook(() => useConstellationCamera());

    expect(result.current.originRef.current).toEqual({ x: 0, y: 0 });
    expect(result.current.targetOriginRef.current).toEqual({ x: 0, y: 0 });
    expect(result.current.zoomRef.current).toBe(1);
    expect(result.current.zoomTargetRef.current).toBe(1);
    expect(result.current.scrollVelocityRef.current).toBe(0);
  });

  it("eases the origin toward the target when reduced motion is off", () => {
    const { result } = renderHook(() => useConstellationCamera());

    act(() => {
      result.current.setTargetOrigin({ x: 100, y: 200 });
      result.current.stepCamera({ reducedMotion: false });
    });

    const origin = result.current.originRef.current;
    expect(origin.x).toBeGreaterThan(0);
    expect(origin.x).toBeLessThan(100);
    expect(origin.y).toBeGreaterThan(0);
    expect(origin.y).toBeLessThan(200);
  });

  it("snaps instantly when reduced motion is requested", () => {
    const { result } = renderHook(() => useConstellationCamera());

    act(() => {
      result.current.setTargetOrigin({ x: 100, y: 200 });
      result.current.setZoomTarget(4);
      result.current.stepCamera({ reducedMotion: true });
    });

    expect(result.current.originRef.current).toEqual({ x: 100, y: 200 });
    expect(result.current.zoomRef.current).toBe(4);
  });

  it("eases zoom more aggressively once inside the star-dive zone", () => {
    const { result } = renderHook(() => useConstellationCamera());

    act(() => {
      result.current.jumpTo({ x: 0, y: 0, zoomFactor: 300 });
      result.current.setZoomTarget(500);
      result.current.stepCamera({ reducedMotion: false });
    });

    // One step at dive zoom ease (0.18) pulls ~18% of the delta (200 * 0.18 = 36).
    const zoomed = result.current.zoomRef.current;
    expect(zoomed).toBeGreaterThan(330);
    expect(zoomed).toBeLessThan(360);
  });

  it("jumpTo clamps extreme zoom targets to the catalogue limits", () => {
    const { result } = renderHook(() => useConstellationCamera());

    act(() => {
      result.current.jumpTo({ x: 5, y: 7, zoomFactor: 1e9 });
    });

    // Upper bound from MAX_BACKGROUND_ZOOM_FACTOR (2000).
    expect(result.current.zoomRef.current).toBeLessThanOrEqual(2000);
    expect(result.current.zoomTargetRef.current).toBeLessThanOrEqual(2000);
    expect(result.current.originRef.current).toEqual({ x: 5, y: 7 });
  });

  it("decays scroll velocity each step", () => {
    const { result } = renderHook(() => useConstellationCamera());

    act(() => {
      result.current.registerScrollVelocity(100);
      result.current.stepCamera({ reducedMotion: false });
    });

    expect(result.current.scrollVelocityRef.current).toBeLessThan(100);
    expect(result.current.scrollVelocityRef.current).toBeGreaterThan(0);
  });

  it("easeDive uses the configured dive duration", () => {
    const { result } = renderHook(() => useConstellationCamera());

    expect(result.current.easeDive(0)).toBe(0);
    expect(result.current.easeDive(CONSTELLATION_DIVE_DURATION_MS)).toBe(1);
    // Halfway through 0.7s matches cubicOutEasing(0.5) = 0.875.
    expect(result.current.easeDive(CONSTELLATION_DIVE_DURATION_MS / 2)).toBeCloseTo(0.875, 5);
  });

  describe("zoom spring (opt-in)", () => {
    it("starts moving slowly on the first step (velocity ramps up)", () => {
      const { result } = renderHook(() =>
        useConstellationCamera({ zoomSpring: true }),
      );
      act(() => {
        result.current.setZoomTarget(2);
        result.current.stepCamera({ reducedMotion: false });
      });
      // Spring's first step delta = stiffness * delta = 0.085 * 1 = 0.085.
      const firstStep = result.current.zoomRef.current - 1;
      expect(firstStep).toBeGreaterThan(0);
      expect(firstStep).toBeLessThan(0.12);
    });

    it("eventually settles at the target after many steps", () => {
      const { result } = renderHook(() =>
        useConstellationCamera({ zoomSpring: true }),
      );
      act(() => {
        result.current.setZoomTarget(2);
        for (let i = 0; i < 400; i++) {
          result.current.stepCamera({ reducedMotion: false });
        }
      });
      expect(result.current.zoomRef.current).toBeCloseTo(2, 3);
    });

    it("can briefly overshoot the target (felt weight)", () => {
      const { result } = renderHook(() =>
        useConstellationCamera({
          zoomSpring: true,
          zoomSpringStiffness: 0.12,
          zoomSpringDamping: 0.78,
        }),
      );
      act(() => {
        result.current.setZoomTarget(2);
      });
      let peak = 1;
      for (let i = 0; i < 80; i++) {
        act(() => {
          result.current.stepCamera({ reducedMotion: false });
        });
        peak = Math.max(peak, result.current.zoomRef.current);
      }
      // Loose bounds — assert overshoot exists without pinning down the
      // exact stiffness/damping curve. Cap at 35% to catch wild tuning.
      expect(peak).toBeGreaterThan(2);
      expect(peak).toBeLessThan(2.7);
    });

    it("snaps under reduced motion even when spring is enabled", () => {
      const { result } = renderHook(() =>
        useConstellationCamera({ zoomSpring: true }),
      );
      act(() => {
        result.current.setZoomTarget(5);
        result.current.stepCamera({ reducedMotion: true });
      });
      expect(result.current.zoomRef.current).toBe(5);
    });
  });
});
