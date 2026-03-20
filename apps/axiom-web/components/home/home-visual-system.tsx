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

export function AxiomHomeLogo({
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
        src="/axiom-logo.png"
        alt="Axiom logo"
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

function PulseDot({
  cx,
  cy,
  radius,
  delay = 0,
  fill,
  animated,
}: {
  cx: number;
  cy: number;
  radius: number;
  delay?: number;
  fill: string;
  animated: boolean;
}) {
  const reduceMotion = useReducedMotion();
  const shouldAnimate = animated && !reduceMotion;

  if (!shouldAnimate) {
    return <circle cx={cx} cy={cy} r={radius} fill={fill} />;
  }

  return (
    <motion.circle
      cx={cx}
      cy={cy}
      r={radius}
      fill={fill}
      animate={{ opacity: [0.35, 1, 0.55] }}
      transition={{
        duration: 1.8,
        repeat: Number.POSITIVE_INFINITY,
        repeatType: "mirror",
        ease: "easeInOut",
        delay,
      }}
    />
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
    <svg viewBox="0 0 96 96" className="size-full" aria-hidden="true">
      <defs>
        <linearGradient id={`home-chat-stroke-${idSuffix}`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#f7fbff" />
          <stop offset="55%" stopColor="#adc6ff" />
          <stop offset="100%" stopColor="#6bb8ff" />
        </linearGradient>
      </defs>
      <path
        d="M25 25h42a13 13 0 0 1 13 13v11a13 13 0 0 1-13 13H46l-13 11v-11h-8a13 13 0 0 1-13-13V38a13 13 0 0 1 13-13Z"
        fill="rgba(255,255,255,0.06)"
        stroke={`url(#home-chat-stroke-${idSuffix})`}
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <path
        d="M31 37h34"
        stroke="rgba(255,255,255,0.84)"
        strokeLinecap="round"
        strokeWidth="3"
      />
      <path
        d="M31 47h24"
        stroke="rgba(173,198,255,0.8)"
        strokeLinecap="round"
        strokeWidth="3"
      />
      <path
        d="M56 31c6 4 10 10 10 17"
        fill="none"
        stroke="rgba(173,198,255,0.24)"
        strokeLinecap="round"
        strokeWidth="6"
      />
      {shouldAnimate ? (
        <motion.path
          d="M56 31c6 4 10 10 10 17"
          fill="none"
          stroke="#ffffff"
          strokeLinecap="round"
          strokeWidth="3"
          strokeDasharray="8 18"
          animate={{ strokeDashoffset: [0, -52] }}
          transition={{
            duration: 2.8,
            repeat: Number.POSITIVE_INFINITY,
            ease: "linear",
          }}
        />
      ) : null}
      <PulseDot cx={30} cy={35} radius={2.6} fill="#f7fbff" animated={animated} />
      <PulseDot cx={47} cy={48} radius={2.2} fill="#adc6ff" animated={animated} delay={0.55} />
      <PulseDot cx={63} cy={40} radius={2.1} fill="#7dd3ff" animated={animated} delay={1.0} />
      {shouldAnimate ? (
        <motion.circle
          cx={64}
          cy={33}
          r={4.4}
          fill="rgba(125,211,255,0.35)"
          animate={{ r: [3.8, 5.8, 3.8], opacity: [0.45, 0.9, 0.45] }}
          transition={{
            duration: 2.2,
            repeat: Number.POSITIVE_INFINITY,
            ease: "easeInOut",
          }}
        />
      ) : (
        <circle cx={64} cy={33} r={4.4} fill="rgba(125,211,255,0.35)" />
      )}
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
    <svg viewBox="0 0 96 96" className="size-full" aria-hidden="true">
      <defs>
        <linearGradient id={`home-neuron-core-${idSuffix}`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="50%" stopColor="#bfd0ff" />
          <stop offset="100%" stopColor="#6bb8ff" />
        </linearGradient>
      </defs>
      <g fill="none" strokeLinecap="round" strokeLinejoin="round">
        <path
          d="M48 48 29 28"
          stroke="rgba(173,198,255,0.5)"
          strokeWidth="2.5"
        />
        <path
          d="M48 48 68 26"
          stroke="rgba(173,198,255,0.5)"
          strokeWidth="2.5"
        />
        <path
          d="M48 48 28 65"
          stroke="rgba(173,198,255,0.5)"
          strokeWidth="2.5"
        />
        <path
          d="M48 48 69 67"
          stroke="rgba(173,198,255,0.5)"
          strokeWidth="2.5"
        />
        <path
          d="M48 48 48 22"
          stroke="rgba(125,211,255,0.55)"
          strokeWidth="2.5"
        />
        <path
          d="M48 48 48 76"
          stroke="rgba(125,211,255,0.55)"
          strokeWidth="2.5"
        />
        <path
          d="M29 28c-4 2-8 7-9 12"
          stroke="rgba(173,198,255,0.32)"
          strokeWidth="2"
        />
        <path
          d="M68 26c6 2 10 6 12 12"
          stroke="rgba(173,198,255,0.32)"
          strokeWidth="2"
        />
        <path
          d="M28 65c-4 3-7 7-8 11"
          stroke="rgba(173,198,255,0.32)"
          strokeWidth="2"
        />
        <path
          d="M69 67c5 2 9 6 11 11"
          stroke="rgba(173,198,255,0.32)"
          strokeWidth="2"
        />
      </g>
      <g>
        <motion.circle
          cx={48}
          cy={48}
          r={10}
          fill={`url(#home-neuron-core-${idSuffix})`}
          animate={
            shouldAnimate
              ? { opacity: [0.45, 1, 0.5] }
              : undefined
          }
          transition={
            shouldAnimate
              ? {
                  duration: 1.4,
                  repeat: Number.POSITIVE_INFINITY,
                  repeatType: "mirror",
                  ease: "easeInOut",
                }
              : undefined
          }
        />
        <circle cx={48} cy={48} r={6.4} fill="rgba(7,12,22,0.92)" />
        <circle cx={47.5} cy={46.5} r={2.2} fill="#ffffff" />
      </g>
      <g>
        <PulseDot cx={29} cy={28} radius={2.3} fill="#f7fbff" animated={animated} delay={0.1} />
        <PulseDot cx={68} cy={26} radius={2.1} fill="#adc6ff" animated={animated} delay={0.4} />
        <PulseDot cx={28} cy={65} radius={2.1} fill="#7dd3ff" animated={animated} delay={0.7} />
        <PulseDot cx={69} cy={67} radius={2.2} fill="#f7fbff" animated={animated} delay={1.0} />
        <PulseDot cx={48} cy={22} radius={1.9} fill="#f7fbff" animated={animated} delay={1.3} />
        <PulseDot cx={48} cy={76} radius={1.9} fill="#adc6ff" animated={animated} delay={1.5} />
      </g>
      {shouldAnimate ? (
        <motion.path
          d="M31 34c5 3 10 7 17 14 7 7 12 11 17 14"
          fill="none"
          stroke="rgba(125,211,255,0.75)"
          strokeLinecap="round"
          strokeWidth="2.5"
          strokeDasharray="8 16"
          animate={{ strokeDashoffset: [0, -72] }}
          transition={{
            duration: 3.2,
            repeat: Number.POSITIVE_INFINITY,
            ease: "linear",
          }}
        />
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
    <svg viewBox="0 0 96 96" className="size-full" aria-hidden="true">
      <defs>
        <linearGradient id={`home-brain-fill-${idSuffix}`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#f7fbff" />
          <stop offset="42%" stopColor="#adc6ff" />
          <stop offset="100%" stopColor="#6bb8ff" />
        </linearGradient>
      </defs>
      <path
        d="M35 26c-8 0-14 6-14 14 0 5 2 8 5 11-2 3-3 5-3 9 0 7 5 13 13 13 2 5 6 8 12 8 4 0 8-2 10-5 2 2 5 3 8 3 8 0 14-6 14-14 0-4-2-8-5-10 2-2 3-5 3-9 0-8-6-14-14-14-2-4-6-7-11-7-5 0-9 2-12 5-3-2-6-4-10-4Z"
        fill="rgba(255,255,255,0.06)"
        stroke={`url(#home-brain-fill-${idSuffix})`}
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <path
        d="M43 30c-3 4-4 9-4 14 0 6 2 12 5 16"
        fill="none"
        stroke="rgba(255,255,255,0.8)"
        strokeLinecap="round"
        strokeWidth="2.2"
      />
      <path
        d="M53 30c3 4 4 9 4 14 0 6-2 12-5 16"
        fill="none"
        stroke="rgba(173,198,255,0.8)"
        strokeLinecap="round"
        strokeWidth="2.2"
      />
      <path
        d="M33 46c4 1 7 2 11 6"
        fill="none"
        stroke="rgba(125,211,255,0.64)"
        strokeLinecap="round"
        strokeWidth="2.2"
      />
      <path
        d="M52 52c4-2 8-3 12-3"
        fill="none"
        stroke="rgba(125,211,255,0.64)"
        strokeLinecap="round"
        strokeWidth="2.2"
      />
      <path
        d="M39 60c2-2 5-4 9-4"
        fill="none"
        stroke="rgba(173,198,255,0.44)"
        strokeLinecap="round"
        strokeWidth="2.2"
      />
      <path
        d="M57 42c3 0 6 1 9 4"
        fill="none"
        stroke="rgba(173,198,255,0.44)"
        strokeLinecap="round"
        strokeWidth="2.2"
      />
      <PulseDot cx={38} cy={35} radius={2.4} fill="#f7fbff" animated={animated} delay={0.1} />
      <PulseDot cx={58} cy={34} radius={2.3} fill="#adc6ff" animated={animated} delay={0.4} />
      <PulseDot cx={65} cy={53} radius={2.2} fill="#7dd3ff" animated={animated} delay={0.8} />
      <PulseDot cx={33} cy={59} radius={2.1} fill="#f7fbff" animated={animated} delay={1.1} />
      {shouldAnimate ? (
        <>
          <motion.circle
            cx={39}
            cy={36}
            r={5.2}
            fill="rgba(173,198,255,0.18)"
            animate={{ r: [4.4, 6.8, 4.4], opacity: [0.2, 0.65, 0.2] }}
            transition={{
              duration: 2.6,
              repeat: Number.POSITIVE_INFINITY,
              ease: "easeInOut",
              delay: 0.2,
            }}
          />
          <motion.circle
            cx={64}
            cy={52}
            r={6}
            fill="rgba(125,211,255,0.16)"
            animate={{ r: [5, 7.6, 5], opacity: [0.18, 0.62, 0.18] }}
            transition={{
              duration: 3,
              repeat: Number.POSITIVE_INFINITY,
              ease: "easeInOut",
              delay: 0.6,
            }}
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
