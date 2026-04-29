"use client";

import { motion, useReducedMotion } from "motion/react";
import { CircleDashed, CircleDot } from "lucide-react";
import { AnimatedLucideIcon } from "@/components/ui/animated-lucide-icon";
import { BorderBeam } from "@/components/ui/border-beam";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { ForgeTechnique } from "@/lib/api";
import {
  PILLAR_GLYPH_TONE,
  PILLAR_ICON,
  PILLAR_LABEL,
  PILLAR_TONE,
} from "@/components/forge/pillar";

interface TechniqueCardProps {
  technique: ForgeTechnique;
}

// One technique = one card. Read-only in Phase 2a — the visual
// difference between an active and standby technique is the moving
// `BorderBeam` and the live status badge, not a toggle (Phase 3).
//
// The card's DOM `id` matches the technique slug so deep-links from
// `/forge#<technique-id>` (Phase 1's `useHashScroll`, Phase 2b's
// constellation Skills-sector stars) land directly on the right card.
export function TechniqueCard({ technique }: TechniqueCardProps) {
  const reducedMotion = useReducedMotion();
  const Icon = PILLAR_ICON[technique.pillar];
  const isActive = technique.enabled;

  const body = (
    <motion.article
      id={technique.id}
      data-active={isActive ? "true" : "false"}
      className={cn(
        "group relative flex h-full flex-col gap-4 rounded-2xl border bg-white/3 p-5 transition-colors",
        isActive
          ? "border-white/14 bg-white/[0.045]"
          : "border-white/8 hover:border-white/12",
      )}
      whileHover={reducedMotion ? undefined : { y: -1 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
    >
      <header className="flex items-start gap-3">
        <div
          className={cn(
            "flex size-10 shrink-0 items-center justify-center rounded-xl border",
            PILLAR_GLYPH_TONE[technique.pillar],
          )}
          aria-hidden="true"
        >
          <AnimatedLucideIcon
            icon={Icon}
            mode={isActive ? "idlePulse" : "hoverLift"}
            className="size-5"
          />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="font-display text-base font-semibold leading-tight text-foreground">
            {technique.name}
          </h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em]",
                PILLAR_TONE[technique.pillar],
              )}
            >
              {PILLAR_LABEL[technique.pillar]}
            </span>
            <StatusBadge active={isActive} />
          </div>
        </div>
      </header>

      <p className="text-sm leading-relaxed text-muted-foreground">
        {technique.description}
      </p>

      {technique.setting_keys.length > 0 ? (
        <Tooltip>
          <TooltipTrigger
            render={
              <button
                type="button"
                aria-label={`Settings keys for ${technique.name}`}
                className="self-start rounded-md border border-white/8 bg-white/4 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground/70 transition-colors hover:border-white/16 hover:text-foreground/90"
              />
            }
          >
            {technique.setting_keys.length === 1
              ? "1 setting key"
              : `${technique.setting_keys.length} setting keys`}
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-sm">
            <div className="flex flex-col gap-1">
              <span className="text-[10px] uppercase tracking-[0.12em] opacity-70">
                Wired to
              </span>
              <code className="font-mono text-[11px] leading-snug">
                {technique.setting_keys.join(", ")}
              </code>
            </div>
          </TooltipContent>
        </Tooltip>
      ) : null}
    </motion.article>
  );

  if (isActive) {
    return (
      <BorderBeam size="md" colorVariant="mono" strength={0.55}>
        {body}
      </BorderBeam>
    );
  }
  return body;
}

function StatusBadge({ active }: { active: boolean }) {
  if (active) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-emerald-200">
        <CircleDot className="size-2.5" aria-hidden="true" />
        Active
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/4 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
      <CircleDashed className="size-2.5" aria-hidden="true" />
      Standby
    </span>
  );
}
