"use client";

import type { ReactNode } from "react";
import { motion } from "motion/react";
import { AmbientBackdrop } from "@/components/shell/ambient-backdrop";
import { StatusPill } from "@/components/shell/status-pill";

interface LaunchStageProps {
  eyebrow?: string;
  title: string;
  description: string;
  statusLabel?: string;
  statusTone?: "connected" | "checking" | "disconnected" | "warning" | "neutral";
  actions?: ReactNode;
  aside?: ReactNode;
}

export function LaunchStage({
  eyebrow = "METIS",
  title,
  description,
  statusLabel,
  statusTone = "neutral",
  actions,
  aside,
}: LaunchStageProps) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10">
      <AmbientBackdrop dense />
      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.56, ease: "easeOut" }}
        className="glass-panel-strong relative z-10 w-full max-w-5xl overflow-hidden rounded-[2rem]"
      >
        <div className="grid gap-8 p-6 sm:p-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(280px,0.85fr)] lg:p-10">
          <div className="space-y-6">
            <div className="space-y-3">
              <p className="font-display text-xs uppercase tracking-[0.32em] text-primary/90">
                {eyebrow}
              </p>
              <h1 className="font-display text-balance text-4xl font-semibold tracking-[-0.04em] text-foreground sm:text-5xl">
                {title}
              </h1>
              <p className="max-w-2xl text-pretty text-base leading-7 text-muted-foreground sm:text-lg">
                {description}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {statusLabel ? (
                <StatusPill label={statusLabel} tone={statusTone} animate={statusTone === "checking"} />
              ) : null}
              <StatusPill label="Private by default" tone="neutral" />
              <StatusPill label="Desktop-first" tone="neutral" />
            </div>

            {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
          </div>

          <div className="glass-panel rounded-[1.75rem] p-5 sm:p-6">
            {aside}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
