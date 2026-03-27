"use client";

import { motion, useReducedMotion } from "motion/react";
import type { CSSProperties } from "react";
import { cn } from "@/lib/utils";

interface StarscapeBackdropProps {
  className?: string;
  dense?: boolean;
}

const TWINKLE_STARS = [
  { left: "5%", top: "8%", delay: 0.1, duration: 2.8, size: 1 },
  { left: "10%", top: "14%", delay: 0.5, duration: 3.1, size: 1 },
  { left: "16%", top: "26%", delay: 0.7, duration: 3.1, size: 1 },
  { left: "28%", top: "12%", delay: 1.3, duration: 2.5, size: 1 },
  { left: "35%", top: "6%", delay: 0.2, duration: 3.4, size: 1 },
  { left: "38%", top: "22%", delay: 0.4, duration: 3.3, size: 1 },
  { left: "52%", top: "18%", delay: 0.9, duration: 2.7, size: 1 },
  { left: "60%", top: "9%", delay: 1.8, duration: 3.0, size: 1 },
  { left: "66%", top: "12%", delay: 1.6, duration: 3.2, size: 1 },
  { left: "75%", top: "5%", delay: 0.3, duration: 2.6, size: 1 },
  { left: "78%", top: "26%", delay: 0.2, duration: 2.9, size: 1 },
  { left: "86%", top: "16%", delay: 1.1, duration: 3.5, size: 1 },
  { left: "92%", top: "10%", delay: 0.8, duration: 2.4, size: 1 },
  { left: "7%", top: "42%", delay: 1.0, duration: 3.2, size: 1 },
  { left: "18%", top: "48%", delay: 0.6, duration: 2.7, size: 1 },
  { left: "30%", top: "38%", delay: 1.4, duration: 3.0, size: 1 },
  { left: "45%", top: "44%", delay: 0.3, duration: 2.9, size: 1.2 },
  { left: "62%", top: "40%", delay: 1.1, duration: 3.3, size: 1 },
  { left: "80%", top: "42%", delay: 0.5, duration: 2.8, size: 1 },
  { left: "90%", top: "36%", delay: 1.5, duration: 3.1, size: 1 },
  { left: "12%", top: "66%", delay: 0.5, duration: 3.4, size: 1 },
  { left: "22%", top: "56%", delay: 1.2, duration: 2.6, size: 1 },
  { left: "38%", top: "72%", delay: 0.3, duration: 3.1, size: 1 },
  { left: "54%", top: "60%", delay: 1.4, duration: 2.8, size: 1.2 },
  { left: "72%", top: "68%", delay: 0.8, duration: 3.3, size: 1 },
  { left: "84%", top: "56%", delay: 1.7, duration: 2.9, size: 1 },
  { left: "94%", top: "70%", delay: 0.6, duration: 3.2, size: 1 },
  { left: "8%", top: "82%", delay: 0.9, duration: 2.5, size: 1 },
  { left: "25%", top: "88%", delay: 1.3, duration: 3.0, size: 1 },
  { left: "48%", top: "85%", delay: 0.7, duration: 2.8, size: 1.2 },
  { left: "68%", top: "90%", delay: 1.0, duration: 3.2, size: 1 },
  { left: "88%", top: "84%", delay: 0.4, duration: 2.7, size: 1 },
  { left: "95%", top: "50%", delay: 1.6, duration: 3.1, size: 1 },
  { left: "3%", top: "55%", delay: 0.2, duration: 2.9, size: 1 },
];

export function StarscapeBackdrop({
  className,
  dense = false,
}: StarscapeBackdropProps) {
  const reduceMotion = useReducedMotion();
  const shouldAnimate = !reduceMotion;

  return (
    <div
      aria-hidden="true"
      className={cn(
        "pointer-events-none absolute inset-0 overflow-hidden",
        dense ? "opacity-95" : "opacity-100",
        className,
      )}
      data-testid="starscape-backdrop"
    >
      <div className="absolute inset-0 bg-[linear-gradient(180deg,#04060d_0%,#050811_44%,#04050c_100%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_38%_20%,rgba(15,39,72,0.44),transparent_28%),radial-gradient(circle_at_72%_66%,rgba(9,105,218,0.18),transparent_38%),linear-gradient(180deg,rgba(3,5,8,0.18),transparent)]" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_14%_18%,rgba(173,198,255,0.08),transparent_14%),radial-gradient(circle_at_84%_18%,rgba(125,211,255,0.08),transparent_16%),radial-gradient(circle_at_60%_78%,rgba(9,105,218,0.08),transparent_20%)]" />

      <motion.div
        aria-hidden="true"
        initial={false}
        animate={
          shouldAnimate
            ? { x: [0, 20, 0], y: [0, 14, 0], opacity: dense ? 0.5 : 0.62 }
            : undefined
        }
        transition={
          shouldAnimate
            ? { duration: 24, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }
            : undefined
        }
        className="absolute left-[-18%] top-[-12%] h-[34rem] w-[34rem] rounded-full bg-[rgba(42,90,158,0.16)] blur-[145px]"
      />
      <motion.div
        aria-hidden="true"
        initial={false}
        animate={
          shouldAnimate
            ? { x: [0, -18, 0], y: [0, 18, 0], opacity: dense ? 0.34 : 0.46 }
            : undefined
        }
        transition={
          shouldAnimate
            ? { duration: 28, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }
            : undefined
        }
        className="absolute right-[-12%] top-[12%] h-[28rem] w-[28rem] rounded-full bg-[rgba(14,55,116,0.12)] blur-[138px]"
      />
      <motion.div
        aria-hidden="true"
        initial={false}
        animate={
          shouldAnimate
            ? { x: [0, 12, 0], y: [0, -10, 0], opacity: dense ? 0.26 : 0.34 }
            : undefined
        }
        transition={
          shouldAnimate
            ? { duration: 32, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }
            : undefined
        }
        className="absolute bottom-[-24%] left-[12%] h-[30rem] w-[30rem] rounded-full bg-[rgba(24,44,96,0.12)] blur-[150px]"
      />

      <div className="absolute inset-0 bg-[radial-gradient(circle,rgba(255,255,255,0.52)_0.6px,transparent_0.8px)] bg-size-[180px_180px] opacity-20" />
      <div className="absolute inset-0 bg-[radial-gradient(circle,rgba(173,198,255,0.5)_0.5px,transparent_0.7px)] bg-size-[280px_280px] opacity-15" />
      <div className="absolute inset-0 bg-[radial-gradient(circle,rgba(255,255,255,0.38)_0.45px,transparent_0.7px)] bg-size-[132px_132px] opacity-12" />

      <div className="absolute inset-0">
        {TWINKLE_STARS.map((star, index) => (
          <motion.span
            key={`${star.left}-${star.top}`}
            className="absolute rounded-full bg-white/80 shadow-[0_0_10px_rgba(255,255,255,0.75)]"
            style={
              {
                left: star.left,
                top: star.top,
                width: `${star.size}px`,
                height: `${star.size}px`,
              } as CSSProperties
            }
            animate={
              shouldAnimate
                ? { opacity: [0.28, 0.96, 0.42], scale: [0.84, 1.18, 0.9] }
                : undefined
            }
            transition={
              shouldAnimate
                ? {
                    duration: star.duration,
                    repeat: Number.POSITIVE_INFINITY,
                    repeatType: "mirror",
                    delay: star.delay + index * 0.08,
                    ease: "easeInOut",
                  }
                : undefined
            }
          />
        ))}
      </div>

      <div className="absolute inset-x-0 top-[15%] h-px bg-gradient-to-r from-transparent via-white/8 to-transparent opacity-70" />
      <div className="absolute inset-x-[10%] top-[8%] h-[20rem] rounded-[50%] bg-[radial-gradient(circle_at_center,rgba(173,198,255,0.08),transparent_65%)] blur-3xl" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_44%,transparent_0%,rgba(0,0,0,0.5)_100%)]" />
      <div className="absolute inset-x-0 bottom-0 h-72 bg-gradient-to-t from-[#04060d] via-[#04060d]/88 to-transparent" />
    </div>
  );
}
