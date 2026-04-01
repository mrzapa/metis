"use client";

import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

interface AmbientBackdropProps {
  className?: string;
  dense?: boolean;
}

export function AmbientBackdrop({ className, dense = false }: AmbientBackdropProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const reduceMotionRaw = useReducedMotion();
  // Before mount, match SSR: useReducedMotion() returns null server-side (!null = true)
  const shouldAnimate = mounted ? !reduceMotionRaw : true;

  return (
    <div
      className={cn(
        "pointer-events-none absolute inset-0 overflow-hidden",
        dense ? "opacity-95" : "opacity-100",
        className,
      )}
      aria-hidden="true"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="absolute inset-0"
      >
        <div
          className={cn(
            "absolute inset-0",
            "bg-[radial-gradient(circle_at_50%_18%,rgba(14,116,144,0.18),transparent_28%),radial-gradient(circle_at_16%_24%,rgba(37,99,235,0.14),transparent_22%),radial-gradient(circle_at_84%_18%,rgba(56,189,248,0.1),transparent_20%),linear-gradient(180deg,rgba(3,5,8,0.98),rgba(3,6,10,0.94)_42%,rgba(3,6,10,0.98))]",
          )}
        />
        <div className="absolute inset-0 hero-grid opacity-45" />

        {/* Animated blobs: only rendered client-side to avoid SSR/hydration style mismatch.
            Safe because the parent wrapper starts at opacity:0 and fades in. */}
        {mounted && (
          <>
            <motion.div
              aria-hidden="true"
              initial={false}
              animate={
                shouldAnimate
                  ? { x: [0, 22, 0], y: [0, 14, 0], opacity: dense ? 0.7 : 0.82 }
                  : undefined
              }
              transition={
                shouldAnimate
                  ? { duration: 18, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }
                  : undefined
              }
              className="absolute left-[-18%] top-[-18%] h-[38rem] w-[38rem] rounded-full bg-primary/16 blur-[150px]"
            />
            <motion.div
              aria-hidden="true"
              initial={false}
              animate={
                shouldAnimate
                  ? { x: [0, -18, 0], y: [0, 18, 0], opacity: dense ? 0.58 : 0.72 }
                  : undefined
              }
              transition={
                shouldAnimate
                  ? { duration: 21, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }
                  : undefined
              }
              className="absolute right-[-14%] top-[10%] h-[30rem] w-[30rem] rounded-full bg-chart-2/14 blur-[140px]"
            />
            <motion.div
              aria-hidden="true"
              initial={false}
              animate={
                shouldAnimate
                  ? { x: [0, 14, 0], y: [0, -10, 0], opacity: dense ? 0.42 : 0.56 }
                  : undefined
              }
              transition={
                shouldAnimate
                  ? { duration: 24, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }
                  : undefined
              }
              className="absolute bottom-[-30%] left-[14%] h-[30rem] w-[30rem] rounded-full bg-chart-4/12 blur-[150px]"
            />
          </>
        )}
        <div className="absolute inset-x-0 top-[15%] h-[1px] bg-gradient-to-r from-transparent via-white/8 to-transparent opacity-70" />
        <div className="absolute inset-x-[12%] top-[8%] h-[22rem] rounded-[50%] bg-[radial-gradient(circle_at_center,rgba(173,198,255,0.09),transparent_65%)] blur-3xl" />
        <div className="absolute inset-x-0 bottom-0 h-72 bg-gradient-to-t from-background via-background/84 to-transparent" />
        {!dense ? (
          <div className="absolute inset-y-0 right-0 w-[min(26vw,24rem)] bg-[linear-gradient(180deg,transparent,rgba(173,198,255,0.02)_20%,transparent_75%)] opacity-70" />
        ) : null}
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,transparent_0%,rgba(0,0,0,0.18)_100%)]" />
      </motion.div>
    </div>
  );
}
