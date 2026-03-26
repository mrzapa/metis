"use client";

import type { ReactNode } from "react";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";

interface OnboardingStepProps {
  index: number;
  total: number;
  title: string;
  description: string;
  children: ReactNode;
  hint?: ReactNode;
  className?: string;
}

export function OnboardingStep({
  index,
  total,
  title,
  description,
  children,
  hint,
  className,
}: OnboardingStepProps) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.52, ease: "easeOut" }}
      className={cn("glass-panel-strong rounded-[1.8rem] p-5 sm:p-7", className)}
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px] lg:gap-8">
        <div className="space-y-6">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-primary/16 font-display text-sm font-semibold text-primary">
                {index + 1}
              </span>
              <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground">
                Step {index + 1} of {total}
              </p>
            </div>
            <div className="space-y-2">
              <h2 className="font-display text-3xl font-semibold tracking-[-0.04em] text-foreground">
                {title}
              </h2>
              <p className="max-w-2xl text-pretty text-sm leading-7 text-muted-foreground sm:text-base">
                {description}
              </p>
            </div>
          </div>
          {children}
        </div>

        <aside className="glass-panel rounded-[1.5rem] p-5">
          <div className="space-y-3">
            <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
              What this unlocks
            </p>
            <div className="text-sm leading-7 text-muted-foreground">
              {hint}
            </div>
          </div>
        </aside>
      </div>
    </motion.section>
  );
}
