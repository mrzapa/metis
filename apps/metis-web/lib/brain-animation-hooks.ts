"use client";

/**
 * Custom hooks for managing Framer Motion animations in brain graph contexts
 */

import { useEffect, useRef, useState } from "react";

/**
 * Hook to manage scroll-based animations for evidence panels
 * Tracks when evidence becomes visible and triggers highlight animation
 */
export function useEvidenceHighlight(elementId: string) {
  const ref = useRef<HTMLElement>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const target = ref.current ?? (elementId ? document.getElementById(elementId) : null);
    if (!target) {
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          observer.unobserve(entry.target);
        }
      },
      { threshold: 0.5 },
    );

    observer.observe(target);

    return () => observer.disconnect();
  }, [elementId]);

  return { ref, isVisible };
}

/**
 * Hook to debounce animation triggers (e.g., on hover state changes)
 */
export function useAnimationDebounce(
  value: unknown,
  delay: number = 150,
): unknown {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => clearTimeout(handler);
  }, [value, delay]);

  return debouncedValue;
}

/**
 * Hook to manage cascading sub-query animations with proper cleanup
 */
export function useSubQueryAnimation(
  subQueries: Array<{ id: string; status: string }>,
) {
  const timeoutRefs = useRef<Map<string, NodeJS.Timeout>>(new Map());

  useEffect(() => {
    const timeoutMap = timeoutRefs.current;
    return () => {
      // Clean up all pending timeouts on unmount
      timeoutMap.forEach((timeout) => clearTimeout(timeout));
      timeoutMap.clear();
    };
  }, []);

  useEffect(() => {
    const activeIds = new Set(subQueries.map(({ id }) => id));

    timeoutRefs.current.forEach((timeout, id) => {
      if (activeIds.has(id)) {
        return;
      }

      clearTimeout(timeout);
      timeoutRefs.current.delete(id);
    });
  }, [subQueries]);

  const scheduleAnimation = (id: string, delay: number, callback: () => void) => {
    // Clear existing timeout for this ID
    const existing = timeoutRefs.current.get(id);
    if (existing) clearTimeout(existing);

    // Schedule new animation
    const timeout = setTimeout(() => {
      callback();
      timeoutRefs.current.delete(id);
    }, delay);

    timeoutRefs.current.set(id, timeout);
  };

  return { scheduleAnimation };
}

/**
 * Hook for smooth numeric animation (e.g., confidence scores, progress)
 */
export function useNumericAnimation(
  targetValue: number,
  duration: number = 1000,
): number {
  const [displayValue, setDisplayValue] = useState(targetValue);
  const startRef = useRef(0);
  const startValueRef = useRef(displayValue);
  const currentValueRef = useRef(targetValue);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    startRef.current = Date.now();
    startValueRef.current = currentValueRef.current;

    const animate = () => {
      const elapsed = Date.now() - startRef.current;
      const progress = Math.min(elapsed / duration, 1);

      // Easing function: easeInOutQuad
      const easeProgress =
        progress < 0.5
          ? 2 * progress * progress
          : -1 + (4 - 2 * progress) * progress;

      const newValue =
        startValueRef.current +
        (targetValue - startValueRef.current) * easeProgress;
      currentValueRef.current = newValue;
      setDisplayValue(newValue);

      if (progress < 1) {
        frameRef.current = requestAnimationFrame(animate);
      }
    };

    frameRef.current = requestAnimationFrame(animate);

    return () => {
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
      }
    };
  }, [targetValue, duration]);

  return displayValue;
}

/**
 * Hook to detect when research mode is expanding and trigger expansion animation
 */
export function useResearchExpansion(isExpanding: boolean) {
  const [hasExpanded, setHasExpanded] = useState(false);
  const activateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const previousExpandingRef = useRef(false);

  useEffect(() => {
    const isRisingEdge = isExpanding && !previousExpandingRef.current;
    previousExpandingRef.current = isExpanding;

    if (!isRisingEdge) {
      return;
    }

    if (activateTimerRef.current !== null) {
      clearTimeout(activateTimerRef.current);
    }
    if (resetTimerRef.current !== null) {
      clearTimeout(resetTimerRef.current);
    }

    activateTimerRef.current = setTimeout(() => {
      setHasExpanded(true);
      activateTimerRef.current = null;
    }, 0);

    resetTimerRef.current = setTimeout(() => {
      setHasExpanded(false);
      resetTimerRef.current = null;
    }, 3000);
  }, [isExpanding]);

  useEffect(() => {
    return () => {
      if (activateTimerRef.current !== null) {
        clearTimeout(activateTimerRef.current);
      }
      if (resetTimerRef.current !== null) {
        clearTimeout(resetTimerRef.current);
      }
    };
  }, []);

  return hasExpanded || isExpanding;
}

/**
 * Hook to manage animation performance with frame rate throttling
 */
export function useAnimationThrottle(
  callback: () => void,
  targetFps: number = 60,
): void {
  const frameRef = useRef<number | null>(null);
  const lastFrameRef = useRef(0);

  useEffect(() => {
    const frameInterval = 1000 / targetFps;

    const handleFrame = () => {
      const now = performance.now();
      if (now - lastFrameRef.current >= frameInterval) {
        callback();
        lastFrameRef.current = now;
      }
      frameRef.current = requestAnimationFrame(handleFrame);
    };

    frameRef.current = requestAnimationFrame(handleFrame);

    return () => {
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
      }
    };
  }, [callback, targetFps]);
}
