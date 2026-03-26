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
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          observer.unobserve(entry.target);
        }
      },
      { threshold: 0.5 },
    );

    if (ref.current) {
      observer.observe(ref.current);
    }

    return () => observer.disconnect();
  }, []);

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
    return () => {
      // Clean up all pending timeouts on unmount
      timeoutRefs.current.forEach((timeout) => clearTimeout(timeout));
      timeoutRefs.current.clear();
    };
  }, []);

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
  const startRef = useRef(Date.now());
  const startValueRef = useRef(displayValue);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    startRef.current = Date.now();
    startValueRef.current = displayValue;

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

  useEffect(() => {
    if (isExpanding && !hasExpanded) {
      setHasExpanded(true);
      const timer = setTimeout(() => setHasExpanded(false), 3000);
      return () => clearTimeout(timer);
    }
  }, [isExpanding, hasExpanded]);

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
