"use client";

import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";

interface WelcomeHeroStat {
  label: string;
  value: string;
}

interface WelcomeHeroProps {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
  stats?: WelcomeHeroStat[];
  preview?: ReactNode;
}

export function WelcomeHero({
  eyebrow,
  title,
  description,
  actions,
  stats = [],
  preview,
}: WelcomeHeroProps) {
  const reducedMotion = useReducedMotion();
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1.08fr)_minmax(320px,0.92fr)] lg:items-end">
      <motion.div
        initial={reducedMotion ? false : { opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, ease: "easeOut" }}
        className="space-y-8"
      >
        <div className="space-y-4">
          <p className="font-display text-xs uppercase tracking-[0.34em] text-primary/90">
            {eyebrow}
          </p>
          <h1 className="font-display text-balance text-5xl font-semibold tracking-[-0.05em] text-foreground sm:text-6xl xl:text-7xl">
            {title}
          </h1>
          <p className="max-w-2xl text-pretty text-lg leading-8 text-muted-foreground">
            {description}
          </p>
        </div>

        {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}

        {stats.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-3">
            {stats.map((stat) => (
              <div key={stat.label} className="glass-panel rounded-[1.35rem] p-4">
                <div className="font-display text-2xl font-semibold text-foreground">{stat.value}</div>
                <div className="mt-1 text-xs uppercase tracking-[0.24em] text-muted-foreground">
                  {stat.label}
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </motion.div>

      <motion.div
        initial={reducedMotion ? false : { opacity: 0, y: 22 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.65, ease: "easeOut", delay: 0.08 }}
        className="glass-panel-strong rounded-[2rem] p-5 sm:p-6"
      >
        {preview}
      </motion.div>
    </div>
  );
}
