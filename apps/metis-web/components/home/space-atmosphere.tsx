"use client";

import Particles, { initParticlesEngine } from "@tsparticles/react";
import { loadSlim } from "@tsparticles/slim";
import { motion, useReducedMotion } from "motion/react";
import type { CSSProperties } from "react";
import { useEffect, useMemo } from "react";
import { useArrowState } from "@/hooks/use-arrow-state";
import type { Engine, ISourceOptions } from "@tsparticles/engine";

import { cn } from "@/lib/utils";

type SpaceAtmosphereProps = {
  className?: string;
};

type ShootingStar = {
  left: string;
  top: string;
  dx: string;
  dy: string;
  delay: number;
  duration: number;
};

const TWINKLE_STARS = [
  { left: "5%", top: "8%", delay: 0.1, duration: 2.8 },
  { left: "10%", top: "14%", delay: 0.5, duration: 3.1 },
  { left: "16%", top: "26%", delay: 0.7, duration: 3.1 },
  { left: "28%", top: "12%", delay: 1.3, duration: 2.5 },
  { left: "35%", top: "6%", delay: 0.2, duration: 3.4 },
  { left: "38%", top: "22%", delay: 0.4, duration: 3.3 },
  { left: "52%", top: "18%", delay: 0.9, duration: 2.7 },
  { left: "60%", top: "9%", delay: 1.8, duration: 3.0 },
  { left: "66%", top: "12%", delay: 1.6, duration: 3.2 },
  { left: "75%", top: "5%", delay: 0.3, duration: 2.6 },
  { left: "78%", top: "26%", delay: 0.2, duration: 2.9 },
  { left: "86%", top: "16%", delay: 1.1, duration: 3.5 },
  { left: "92%", top: "10%", delay: 0.8, duration: 2.4 },
  { left: "7%", top: "42%", delay: 1.0, duration: 3.2 },
  { left: "18%", top: "48%", delay: 0.6, duration: 2.7 },
  { left: "30%", top: "38%", delay: 1.4, duration: 3.0 },
  { left: "45%", top: "44%", delay: 0.3, duration: 2.9 },
  { left: "62%", top: "40%", delay: 1.1, duration: 3.3 },
  { left: "80%", top: "42%", delay: 0.5, duration: 2.8 },
  { left: "90%", top: "36%", delay: 1.5, duration: 3.1 },
  { left: "12%", top: "66%", delay: 0.5, duration: 3.4 },
  { left: "22%", top: "56%", delay: 1.2, duration: 2.6 },
  { left: "38%", top: "72%", delay: 0.3, duration: 3.1 },
  { left: "54%", top: "60%", delay: 1.4, duration: 2.8 },
  { left: "72%", top: "68%", delay: 0.8, duration: 3.3 },
  { left: "84%", top: "56%", delay: 1.7, duration: 2.9 },
  { left: "94%", top: "70%", delay: 0.6, duration: 3.2 },
  { left: "8%", top: "82%", delay: 0.9, duration: 2.5 },
  { left: "25%", top: "88%", delay: 1.3, duration: 3.0 },
  { left: "48%", top: "85%", delay: 0.7, duration: 2.8 },
  { left: "68%", top: "90%", delay: 1.0, duration: 3.2 },
  { left: "88%", top: "84%", delay: 0.4, duration: 2.7 },
  { left: "95%", top: "50%", delay: 1.6, duration: 3.1 },
  { left: "3%", top: "55%", delay: 0.2, duration: 2.9 },
];

const SHOOTING_STARS: ShootingStar[] = [
  { left: "14%", top: "18%", dx: "22vw", dy: "8vh", delay: 0, duration: 2.2 },
  { left: "68%", top: "10%", dx: "18vw", dy: "7vh", delay: 4.2, duration: 2.1 },
  { left: "46%", top: "28%", dx: "16vw", dy: "6vh", delay: 7.6, duration: 2.3 },
];

let particlesEngineInitPromise: Promise<void> | null = null;

function ensureParticlesEngineInit() {
  if (!particlesEngineInitPromise) {
    particlesEngineInitPromise = initParticlesEngine(async (engine: Engine) => {
      await loadSlim(engine);
    });
  }
  return particlesEngineInitPromise;
}

export function SpaceAtmosphere({ className }: SpaceAtmosphereProps) {
  const reduceMotion = useReducedMotion();
  const [particlesReady, setParticlesReady] = useArrowState(false);

  useEffect(() => {
    let mounted = true;

    ensureParticlesEngineInit().then(() => {
      if (mounted) {
        setParticlesReady(true);
      }
    });

    return () => {
      mounted = false;
    };
  }, []);

  const particleOptions = useMemo<ISourceOptions>(() => {
    const particleCount = reduceMotion ? 48 : 72;

    return {
      fullScreen: {
        enable: false,
      },
      detectRetina: true,
      fpsLimit: reduceMotion ? 30 : 60,
      background: {
        color: {
          value: "transparent",
        },
      },
      interactivity: {
        events: {
          onHover: {
            enable: false,
          },
          onClick: {
            enable: false,
          },
          resize: {
            enable: true,
          },
        },
      },
      particles: {
        color: {
          value: ["#ffffff", "#adc6ff"],
        },
        number: {
          value: particleCount,
          density: {
            enable: true,
            width: 1600,
            height: 900,
          },
        },
        opacity: {
          value: { min: 0.16, max: 0.58 },
          animation: {
            enable: !reduceMotion,
            speed: 0.2,
            minimumValue: 0.14,
            sync: false,
          },
        },
        size: {
          value: { min: 0.55, max: 1.9 },
        },
        move: {
          enable: !reduceMotion,
          speed: 0.22,
          direction: "none",
          straight: false,
          outModes: {
            default: "out",
          },
        },
        twinkle: {
          particles: {
            enable: !reduceMotion,
            color: "#ffffff",
            frequency: 0.008,
            opacity: 0.85,
          },
        },
      },
      pauseOnOutsideViewport: true,
    };
  }, [reduceMotion]);

  return (
    <div
      aria-hidden="true"
      className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)}
    >
      {/* Deep-space base with dark gradient */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_38%_20%,rgba(15,39,72,0.44),transparent_28%),radial-gradient(circle_at_72%_66%,rgba(9,105,218,0.18),transparent_38%),linear-gradient(180deg,rgba(3,5,8,0.98),rgba(3,5,8,0.92)_58%,rgba(3,5,8,1))]" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_14%_18%,rgba(173,198,255,0.08),transparent_14%),radial-gradient(circle_at_84%_18%,rgba(125,211,255,0.08),transparent_16%),radial-gradient(circle_at_60%_78%,rgba(9,105,218,0.08),transparent_20%)]" />

      {/* Nebula clouds */}
      <div className="home-nebula home-nebula--one" />
      <div className="home-nebula home-nebula--two" />
      <div className="home-nebula home-nebula--three" />

      {/* Procedural starfield (home route only) */}
      {particlesReady ? (
        <Particles
          id="home-space-particles"
          className="absolute inset-0 opacity-80"
          options={particleOptions}
        />
      ) : null}

      {/* Static micro-star field */}
      <div className="absolute inset-0 bg-[radial-gradient(circle,rgba(255,255,255,0.55)_0.6px,transparent_0.8px)] bg-size-[180px_180px] opacity-20" />
      <div className="absolute inset-0 bg-[radial-gradient(circle,rgba(173,198,255,0.5)_0.5px,transparent_0.7px)] bg-size-[280px_280px] opacity-15" />

      {/* Twinkling stars */}
      <div className="absolute inset-0">
        {TWINKLE_STARS.map((star, index) => (
          <motion.span
            key={`${star.left}-${star.top}`}
            className="absolute h-1 w-1 rounded-full bg-white/80 shadow-[0_0_10px_rgba(255,255,255,0.9)]"
            style={{ left: star.left, top: star.top } as CSSProperties}
            animate={
              reduceMotion
                ? undefined
                : { opacity: [0.3, 1, 0.45], scale: [0.8, 1.2, 0.85] }
            }
            transition={
              reduceMotion
                ? undefined
                : {
                    duration: star.duration,
                    repeat: Number.POSITIVE_INFINITY,
                    repeatType: "mirror",
                    delay: star.delay + index * 0.1,
                    ease: "easeInOut",
                  }
            }
          />
        ))}
      </div>

      {/* Shooting stars */}
      {!reduceMotion ? (
        <div className="absolute inset-0" data-testid="shooting-stars-layer">
          {SHOOTING_STARS.map((star, index) => (
            <motion.span
              key={`shooting-star-${index}`}
              className="absolute h-px rounded-full bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.98),rgba(173,198,255,0.7),transparent)] shadow-[0_0_18px_rgba(173,198,255,0.65)]"
              style={
                {
                  left: star.left,
                  top: star.top,
                  width: 96,
                } as CSSProperties
              }
              initial={{ opacity: 0, x: 0, y: 0, scaleX: 0.12 }}
              animate={{
                opacity: [0, 1, 0],
                x: [0, star.dx],
                y: [0, star.dy],
                scaleX: [0.12, 1, 0.12],
              }}
              transition={{
                duration: star.duration,
                delay: star.delay,
                repeat: Number.POSITIVE_INFINITY,
                repeatDelay: 8,
                ease: "easeOut",
              }}
            />
          ))}
        </div>
      ) : null}

      {/* Vignette */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_44%,transparent_0%,rgba(0,0,0,0.52)_100%)]" />
    </div>
  );
}
