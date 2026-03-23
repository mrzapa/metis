"use client";

/**
 * Vendored from react-bits.
 * Source URL: https://github.com/DavidHDev/react-bits/blob/2731842071978a8e0076b870d97f5c65f2a13482/src/ts-default/TextAnimations/ShinyText/ShinyText.tsx
 * Commit SHA: 2731842071978a8e0076b870d97f5c65f2a13482
 * Original path: src/ts-default/TextAnimations/ShinyText/ShinyText.tsx
 * License: MIT + Commons Clause License Condition v1.0
 * License file: apps/axiom-web/third_party/licenses/react-bits-LICENSE.md
 * Local modifications:
 * - Removed upstream CSS import and use inline block class for self-contained styling.
 * - Retained TypeScript implementation while adapting import quote/style conventions.
 */

import {
  motion,
  useAnimationFrame,
  useMotionValue,
  useTransform,
} from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";

export interface ShinyTextProps {
  text: string;
  disabled?: boolean;
  speed?: number;
  className?: string;
  color?: string;
  shineColor?: string;
  spread?: number;
  yoyo?: boolean;
  pauseOnHover?: boolean;
  direction?: "left" | "right";
  delay?: number;
}

export function ShinyText({
  text,
  disabled = false,
  speed = 2,
  className = "",
  color = "#b5b5b5",
  shineColor = "#ffffff",
  spread = 120,
  yoyo = false,
  pauseOnHover = false,
  direction = "left",
  delay = 0,
}: ShinyTextProps) {
  const [isPaused, setIsPaused] = useState(false);
  const progress = useMotionValue(0);
  const elapsedRef = useRef(0);
  const lastTimeRef = useRef<number | null>(null);
  const directionRef = useRef(direction === "left" ? 1 : -1);

  const animationDuration = speed * 1000;
  const delayDuration = delay * 1000;

  useAnimationFrame((time) => {
    if (disabled || isPaused) {
      lastTimeRef.current = null;
      return;
    }

    if (lastTimeRef.current === null) {
      lastTimeRef.current = time;
      return;
    }

    const deltaTime = time - lastTimeRef.current;
    lastTimeRef.current = time;

    elapsedRef.current += deltaTime;

    if (yoyo) {
      const cycleDuration = animationDuration + delayDuration;
      const fullCycle = cycleDuration * 2;
      const cycleTime = elapsedRef.current % fullCycle;

      if (cycleTime < animationDuration) {
        const value = (cycleTime / animationDuration) * 100;
        progress.set(directionRef.current === 1 ? value : 100 - value);
      } else if (cycleTime < cycleDuration) {
        progress.set(directionRef.current === 1 ? 100 : 0);
      } else if (cycleTime < cycleDuration + animationDuration) {
        const reverseTime = cycleTime - cycleDuration;
        const value = 100 - (reverseTime / animationDuration) * 100;
        progress.set(directionRef.current === 1 ? value : 100 - value);
      } else {
        progress.set(directionRef.current === 1 ? 0 : 100);
      }
    } else {
      const cycleDuration = animationDuration + delayDuration;
      const cycleTime = elapsedRef.current % cycleDuration;

      if (cycleTime < animationDuration) {
        const value = (cycleTime / animationDuration) * 100;
        progress.set(directionRef.current === 1 ? value : 100 - value);
      } else {
        progress.set(directionRef.current === 1 ? 100 : 0);
      }
    }
  });

  useEffect(() => {
    directionRef.current = direction === "left" ? 1 : -1;
    elapsedRef.current = 0;
    progress.set(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [direction]);

  const backgroundPosition = useTransform(
    progress,
    (value) => `${150 - value * 2}% center`,
  );

  const handleMouseEnter = useCallback(() => {
    if (pauseOnHover) setIsPaused(true);
  }, [pauseOnHover]);

  const handleMouseLeave = useCallback(() => {
    if (pauseOnHover) setIsPaused(false);
  }, [pauseOnHover]);

  const gradientStyle: React.CSSProperties = {
    backgroundImage: `linear-gradient(${spread}deg, ${color} 0%, ${color} 35%, ${shineColor} 50%, ${color} 65%, ${color} 100%)`,
    backgroundSize: "200% auto",
    WebkitBackgroundClip: "text",
    backgroundClip: "text",
    WebkitTextFillColor: "transparent",
  };

  return (
    <motion.span
      className={`inline-block ${className}`.trim()}
      style={{ ...gradientStyle, backgroundPosition }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {text}
    </motion.span>
  );
}
