"use client";

import Image from "next/image";
import { motion, useReducedMotion } from "motion/react";
import { useId } from "react";
import type { CSSProperties, ReactNode } from "react";
import { cn } from "@/lib/utils";

export type HomeLaunchKind = "chat" | "neuron" | "brain";

export type HomeLaunchIconProps = {
  kind: HomeLaunchKind;
  animated?: boolean;
  className?: string;
  size?: number;
  accent?: string;
  title?: string;
};

const ICON_BASE_CLASS =
  "relative isolate flex items-center justify-center overflow-hidden rounded-full border border-white/10 bg-[radial-gradient(circle_at_50%_36%,rgba(173,198,255,0.22),rgba(10,14,22,0.9)_58%,rgba(4,7,12,0.98)_100%)] shadow-[0_18px_44px_rgba(0,0,0,0.32),inset_0_1px_0_rgba(255,255,255,0.12)]";

function OrbSpecular({
  animated,
  className,
}: {
  animated: boolean;
  className?: string;
}) {
  return (
    <motion.span
      aria-hidden="true"
      className={cn(
        "pointer-events-none absolute rounded-full bg-[radial-gradient(circle_at_30%_28%,rgba(255,255,255,0.85),rgba(255,255,255,0.18)_28%,transparent_56%)]",
        className,
      )}
      animate={animated ? { x: [-1, 1, -1], y: [-1, 1, -1] } : undefined}
      transition={
        animated
          ? {
              duration: 8,
              repeat: Number.POSITIVE_INFINITY,
              ease: "easeInOut",
            }
          : undefined
      }
    />
  );
}

export function MetisHomeLogo({
  className,
  priority = false,
}: {
  className?: string;
  priority?: boolean;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      className={cn("relative isolate", className)}
      animate={
        reduceMotion
          ? undefined
          : {
              y: [0, -4, 0],
              rotate: [0, -0.5, 0],
            }
      }
      transition={
        reduceMotion
          ? undefined
          : {
              duration: 8,
              repeat: Number.POSITIVE_INFINITY,
              ease: "easeInOut",
            }
      }
    >
      <div className="absolute inset-[7%] rounded-full bg-[radial-gradient(circle_at_50%_20%,rgba(255,255,255,0.18),rgba(255,255,255,0)_42%),radial-gradient(circle_at_50%_70%,rgba(9,105,218,0.35),rgba(9,105,218,0)_64%),linear-gradient(180deg,rgba(12,16,27,0.98),rgba(5,8,14,0.96))] shadow-[inset_0_10px_30px_rgba(255,255,255,0.08),inset_0_-28px_42px_rgba(0,0,0,0.44),0_24px_60px_rgba(0,0,0,0.35)]" />
      <div
        aria-hidden="true"
        className="absolute inset-[7%] rounded-full ring-1 ring-white/10"
      />
      <OrbSpecular
        animated={!reduceMotion}
        className="left-[14%] top-[12%] h-[36%] w-[36%] opacity-80 blur-[1px]"
      />
      <motion.span
        aria-hidden="true"
        className="pointer-events-none absolute inset-[12%] rounded-full border border-white/10"
        animate={
          reduceMotion
            ? undefined
            : {
                rotate: 360,
              }
        }
        transition={
          reduceMotion
            ? undefined
            : {
                duration: 28,
                repeat: Number.POSITIVE_INFINITY,
                ease: "linear",
              }
        }
      />
      <motion.span
        aria-hidden="true"
        className="pointer-events-none absolute inset-[18%] rounded-full border border-cyan-300/20"
        animate={
          reduceMotion
            ? undefined
            : {
                rotate: -360,
              }
        }
        transition={
          reduceMotion
            ? undefined
            : {
                duration: 18,
                repeat: Number.POSITIVE_INFINITY,
                ease: "linear",
              }
        }
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-[20%] rounded-full bg-[radial-gradient(circle_at_50%_50%,rgba(173,198,255,0.16),transparent_68%)] blur-md"
      />
      <Image
        src="/metis-logo.png"
        alt="METIS logo"
        fill
        sizes="(max-width: 768px) 160px, 192px"
        priority={priority}
        className="relative z-10 size-full object-contain drop-shadow-[0_0_34px_rgba(9,105,218,0.32)]"
      />
    </motion.div>
  );
}

function MotionWrapper({
  animated,
  children,
  className,
}: {
  animated: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      className={className}
      animate={
        animated
          ? { scale: [1, 1.045, 1], rotate: [0, -1.6, 0] }
          : undefined
      }
      transition={
        animated
          ? {
              duration: 7.5,
              repeat: Number.POSITIVE_INFINITY,
              ease: "easeInOut",
            }
          : undefined
      }
    >
      {children}
    </motion.div>
  );
}

function ChatGlyph({
  animated,
  idSuffix,
}: {
  animated: boolean;
  idSuffix: string;
}) {
  const reduceMotion = useReducedMotion();
  const shouldAnimate = animated && !reduceMotion;

  return (
    <svg viewBox="0 0 100 100" className="size-full" aria-hidden="true">
      <defs>
        <radialGradient id={`home-chat-fill-${idSuffix}`} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#3B82F6" stopOpacity="0.8" />
          <stop offset="100%" stopColor="#1E3A8A" stopOpacity="0.9" />
        </radialGradient>
        <filter id={`home-chat-glow-${idSuffix}`}>
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {/* Outer glow */}
      {shouldAnimate ? (
        <motion.circle
          cx={50} cy={50} r={38}
          fill="rgba(59,130,246,0.1)"
          animate={{ opacity: [0.06, 0.16, 0.06] }}
          transition={{ duration: 3, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
        />
      ) : null}
      {/* Main bubble shape */}
      <path
        d="M25 50C25 36.19 36.19 25 50 25C63.81 25 75 36.19 75 50C75 63.81 63.81 75 50 75C45.36 75 41.02 73.74 37.33 71.56C36.66 71.16 35.83 71.02 35.08 71.2L26.67 73.12C25.47 73.4 24.36 72.16 24.77 71.01L27.63 62.92C27.92 62.12 27.82 61.23 27.38 60.51C25.86 58.04 25 55.11 25 50Z"
        fill={`url(#home-chat-fill-${idSuffix})`}
        stroke="#60A5FA"
        strokeWidth="2"
        filter={`url(#home-chat-glow-${idSuffix})`}
      />
      {/* Three dots */}
      <circle cx={38} cy={50} r={4} fill="#E0F2FE" />
      <circle cx={50} cy={50} r={4} fill="#E0F2FE" />
      <circle cx={62} cy={50} r={4} fill="#E0F2FE" />
      {/* Specular highlight */}
      <ellipse cx={44} cy={38} rx={12} ry={6} fill="rgba(255,255,255,0.12)" />
      {/* Animated pulse on dots */}
      {shouldAnimate ? (
        <>
          <motion.circle cx={38} cy={50} r={5.5} fill="rgba(224,242,254,0.35)"
            animate={{ opacity: [0.2, 0.6, 0.2] }}
            transition={{ duration: 1.8, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut", delay: 0 }}
          />
          <motion.circle cx={50} cy={50} r={5.5} fill="rgba(224,242,254,0.35)"
            animate={{ opacity: [0.2, 0.6, 0.2] }}
            transition={{ duration: 1.8, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut", delay: 0.3 }}
          />
          <motion.circle cx={62} cy={50} r={5.5} fill="rgba(224,242,254,0.35)"
            animate={{ opacity: [0.2, 0.6, 0.2] }}
            transition={{ duration: 1.8, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut", delay: 0.6 }}
          />
        </>
      ) : null}
    </svg>
  );
}

function NeuronGlyph({
  animated,
  idSuffix,
}: {
  animated: boolean;
  idSuffix: string;
}) {
  const reduceMotion = useReducedMotion();
  const shouldAnimate = animated && !reduceMotion;

  return (
    <svg viewBox="0 0 100 100" className="size-full" aria-hidden="true">
      <defs>
        <radialGradient id={`home-neuron-core-${idSuffix}`} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#DBEAFE" />
          <stop offset="100%" stopColor="#60A5FA" />
        </radialGradient>
        <filter id={`home-neuron-glow-${idSuffix}`}>
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {/* Dendrite branches */}
      <path d="M50 40 C45 25, 30 15, 20 20" stroke="#93C5FD" strokeLinecap="round" strokeWidth="2" fill="none" />
      <path d="M50 40 C55 25, 70 15, 80 20" stroke="#93C5FD" strokeLinecap="round" strokeWidth="2" fill="none" />
      <path d="M40 50 C25 45, 15 60, 20 70" stroke="#93C5FD" strokeLinecap="round" strokeWidth="2" fill="none" />
      <path d="M60 50 C75 45, 85 60, 80 70" stroke="#93C5FD" strokeLinecap="round" strokeWidth="2" fill="none" />
      <path d="M50 60 C45 75, 50 90, 50 90" stroke="#93C5FD" strokeLinecap="round" strokeWidth="2" fill="none" />
      {/* Synapse endpoints */}
      <circle cx={20} cy={20} r={3} fill="#BFDBFE" />
      <circle cx={80} cy={20} r={3} fill="#BFDBFE" />
      <circle cx={20} cy={70} r={3} fill="#BFDBFE" />
      <circle cx={80} cy={70} r={3} fill="#BFDBFE" />
      <circle cx={50} cy={90} r={3} fill="#BFDBFE" />
      {/* Core glow */}
      <circle cx={50} cy={50} r={10} fill="#60A5FA" filter={`url(#home-neuron-glow-${idSuffix})`} opacity="0.7" />
      {/* Core body */}
      <circle cx={50} cy={50} r={8} fill={`url(#home-neuron-core-${idSuffix})`} />
      {/* Specular highlight */}
      <ellipse cx={48} cy={46} rx={4} ry={2.5} fill="rgba(255,255,255,0.4)" />
      {/* Animated pulse */}
      {shouldAnimate ? (
        <>
          <motion.circle cx={50} cy={50} r={14} fill="rgba(96,165,250,0.15)"
            animate={{ opacity: [0.1, 0.35, 0.1] }}
            transition={{ duration: 2.4, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
          />
          <motion.circle cx={20} cy={20} r={4.5} fill="rgba(191,219,254,0.4)"
            animate={{ opacity: [0.3, 0.8, 0.3] }}
            transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut", delay: 0.2 }}
          />
          <motion.circle cx={80} cy={20} r={4.5} fill="rgba(191,219,254,0.4)"
            animate={{ opacity: [0.3, 0.8, 0.3] }}
            transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut", delay: 0.6 }}
          />
          <motion.circle cx={20} cy={70} r={4.5} fill="rgba(191,219,254,0.4)"
            animate={{ opacity: [0.3, 0.8, 0.3] }}
            transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut", delay: 1.0 }}
          />
          <motion.circle cx={80} cy={70} r={4.5} fill="rgba(191,219,254,0.4)"
            animate={{ opacity: [0.3, 0.8, 0.3] }}
            transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut", delay: 1.4 }}
          />
          <motion.path
            d="M50 40 C45 25, 30 15, 20 20"
            fill="none" stroke="rgba(147,197,253,0.7)" strokeLinecap="round" strokeWidth="2"
            strokeDasharray="6 12"
            animate={{ strokeDashoffset: [0, -36] }}
            transition={{ duration: 2.8, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
          />
          <motion.path
            d="M60 50 C75 45, 85 60, 80 70"
            fill="none" stroke="rgba(147,197,253,0.7)" strokeLinecap="round" strokeWidth="2"
            strokeDasharray="6 12"
            animate={{ strokeDashoffset: [0, -36] }}
            transition={{ duration: 2.8, repeat: Number.POSITIVE_INFINITY, ease: "linear", delay: 0.8 }}
          />
        </>
      ) : null}
    </svg>
  );
}

function BrainGlyph({
  animated,
  idSuffix,
}: {
  animated: boolean;
  idSuffix: string;
}) {
  const reduceMotion = useReducedMotion();
  const shouldAnimate = animated && !reduceMotion;

  return (
    <svg viewBox="0 0 100 100" className="size-full" aria-hidden="true">
      <defs>
        <radialGradient id={`home-brain-fill-${idSuffix}`} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#3B82F6" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#1E3A8A" stopOpacity="0.8" />
        </radialGradient>
        <filter id={`home-brain-glow-${idSuffix}`}>
          <feGaussianBlur stdDeviation="2.5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {/* Outer glow */}
      {shouldAnimate ? (
        <motion.path
          d="M30 40 C20 40, 20 60, 30 70 C30 80, 45 85, 50 75 C55 85, 70 80, 70 70 C80 60, 80 40, 70 40 C75 25, 60 20, 50 30 C40 20, 25 25, 30 40 Z"
          fill="rgba(59,130,246,0.06)" stroke="none"
          animate={{ scale: [1, 1.04, 1], opacity: [0.06, 0.14, 0.06] }}
          transition={{ duration: 3.2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
          style={{ transformOrigin: "50px 52px" }}
        />
      ) : null}
      {/* Main brain shape */}
      <path
        d="M30 40 C20 40, 20 60, 30 70 C30 80, 45 85, 50 75 C55 85, 70 80, 70 70 C80 60, 80 40, 70 40 C75 25, 60 20, 50 30 C40 20, 25 25, 30 40 Z"
        fill={`url(#home-brain-fill-${idSuffix})`}
        stroke="#93C5FD"
        strokeWidth="2"
        filter={`url(#home-brain-glow-${idSuffix})`}
      />
      {/* Hemispheric divide */}
      <path d="M50 30 L50 75" stroke="#60A5FA" strokeDasharray="2 2" strokeWidth="2" fill="none" />
      {/* Neural nodes inside brain */}
      <circle cx={40} cy={45} r={2} fill="#E0F2FE" />
      <circle cx={60} cy={45} r={2} fill="#E0F2FE" />
      <circle cx={35} cy={55} r={2} fill="#E0F2FE" />
      <circle cx={65} cy={55} r={2} fill="#E0F2FE" />
      <circle cx={45} cy={65} r={2} fill="#E0F2FE" />
      <circle cx={55} cy={65} r={2} fill="#E0F2FE" />
      {/* Specular highlight */}
      <ellipse cx={42} cy={38} rx={10} ry={5} fill="rgba(255,255,255,0.08)" />
      {/* Animated pulses on neural nodes */}
      {shouldAnimate ? (
        <>
          <motion.circle cx={40} cy={45} r={3.5} fill="rgba(224,242,254,0.35)"
            animate={{ opacity: [0.2, 0.7, 0.2] }}
            transition={{ duration: 2.2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut", delay: 0 }}
          />
          <motion.circle cx={60} cy={45} r={3.5} fill="rgba(224,242,254,0.35)"
            animate={{ opacity: [0.2, 0.7, 0.2] }}
            transition={{ duration: 2.2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut", delay: 0.5 }}
          />
          <motion.circle cx={35} cy={55} r={3.5} fill="rgba(224,242,254,0.35)"
            animate={{ opacity: [0.2, 0.7, 0.2] }}
            transition={{ duration: 2.2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut", delay: 1.0 }}
          />
          <motion.circle cx={65} cy={55} r={3.5} fill="rgba(224,242,254,0.35)"
            animate={{ opacity: [0.2, 0.7, 0.2] }}
            transition={{ duration: 2.2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut", delay: 1.5 }}
          />
        </>
      ) : null}
    </svg>
  );
}

function launchFrame(kind: HomeLaunchKind, animated: boolean, idSuffix: string) {
  switch (kind) {
    case "chat":
      return <ChatGlyph animated={animated} idSuffix={idSuffix} />;
    case "neuron":
      return <NeuronGlyph animated={animated} idSuffix={idSuffix} />;
    case "brain":
      return <BrainGlyph animated={animated} idSuffix={idSuffix} />;
    default:
      return null;
  }
}

export function HomeLaunchIcon({
  kind,
  animated = false,
  className,
  size = 64,
  accent = "#adc6ff",
  title,
}: HomeLaunchIconProps) {
  const reduceMotion = useReducedMotion();
  const shouldAnimate = animated && !reduceMotion;
  const idSuffix = useId().replace(/:/g, "");

  return (
    <motion.div
      className={cn(ICON_BASE_CLASS, className)}
      style={
        {
          width: size,
          height: size,
          color: accent,
        } as CSSProperties
      }
      animate={
        shouldAnimate
          ? {
              y: [0, -1.5, 0],
              scale: [1, 1.018, 1],
            }
          : undefined
      }
      transition={
        shouldAnimate
          ? {
              duration: 5.8,
              repeat: Number.POSITIVE_INFINITY,
              ease: "easeInOut",
            }
          : undefined
      }
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      aria-label={title}
    >
      <motion.span
        aria-hidden="true"
        className="pointer-events-none absolute inset-[-8%] rounded-full border border-[rgba(143,179,255,0.14)]"
        animate={
          shouldAnimate
            ? {
                scale: [0.94, 1.04, 0.96],
                opacity: [0.16, 0.42, 0.16],
              }
            : undefined
        }
        transition={
          shouldAnimate
            ? {
                duration: 3.6,
                repeat: Number.POSITIVE_INFINITY,
                ease: "easeInOut",
              }
            : undefined
        }
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-[10%] rounded-full bg-[radial-gradient(circle_at_50%_20%,rgba(255,255,255,0.22),rgba(255,255,255,0)_42%),radial-gradient(circle_at_50%_72%,rgba(9,105,218,0.28),rgba(9,105,218,0)_64%)] opacity-90 blur-[1px]"
      />
      <motion.span
        aria-hidden="true"
        className="pointer-events-none absolute inset-[13%] rounded-full border border-white/10"
        animate={
          shouldAnimate
            ? {
                rotate: 360,
              }
            : undefined
        }
        transition={
          shouldAnimate
            ? {
                duration: 24,
                repeat: Number.POSITIVE_INFINITY,
                ease: "linear",
              }
            : undefined
        }
      />
      <motion.span
        aria-hidden="true"
        className="pointer-events-none absolute inset-[20%]"
        animate={
          shouldAnimate
            ? {
                rotate: 360,
              }
            : undefined
        }
        transition={
          shouldAnimate
            ? {
                duration: 11,
                repeat: Number.POSITIVE_INFINITY,
                ease: "linear",
              }
            : undefined
        }
      >
        <span className="absolute left-1/2 top-0 size-1.5 -translate-x-1/2 rounded-full bg-[#d7e7ff] shadow-[0_0_14px_rgba(173,198,255,0.85)]" />
      </motion.span>
      <motion.span
        aria-hidden="true"
        className="pointer-events-none absolute left-[20%] top-[16%] h-[34%] w-[34%] rounded-full bg-[radial-gradient(circle_at_35%_28%,rgba(255,255,255,0.75),rgba(255,255,255,0.12)_34%,transparent_66%)] blur-[1px]"
        animate={
          shouldAnimate
            ? {
                x: [-1.5, 1.5, -1.5],
                y: [-1, 1, -1],
              }
            : undefined
        }
        transition={
          shouldAnimate
            ? {
                duration: 6.5,
                repeat: Number.POSITIVE_INFINITY,
                ease: "easeInOut",
              }
            : undefined
        }
      />
      <MotionWrapper
        animated={shouldAnimate}
        className="relative z-10 flex size-[80%] items-center justify-center"
      >
        {launchFrame(kind, shouldAnimate, idSuffix)}
      </MotionWrapper>
    </motion.div>
  );
}
