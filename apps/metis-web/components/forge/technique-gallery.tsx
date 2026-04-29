"use client";

import { useMemo } from "react";
import { motion, useReducedMotion } from "motion/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { TechniqueCard } from "@/components/forge/technique-card";
import type { ForgePillar, ForgeTechnique } from "@/lib/api";
import { PILLAR_LABEL } from "@/components/forge/pillar";

interface TechniqueGalleryProps {
  techniques: ForgeTechnique[];
  onToggle?: (technique: ForgeTechnique, enabled: boolean) => Promise<void>;
}

// Render order: keep the registry's declared order so Cortex's
// retrieval/synthesis stack walks down the gallery in the same shape
// the engine walks during a query, then Companion techniques follow.
// Within that order, active techniques appear first inside each
// pillar block — the gallery's job is to make absorption visible, so
// what's already absorbed leads.
//
// The summary header counts active vs total across pillars; per-pillar
// counts go beside the section title so the user can see, at a glance,
// how much of each pillar METIS has lit up.
export function TechniqueGallery({ techniques, onToggle }: TechniqueGalleryProps) {
  const reducedMotion = useReducedMotion();
  const grouped = useMemo(() => groupByPillar(techniques), [techniques]);
  const totalActive = techniques.filter((t) => t.enabled).length;

  return (
    <TooltipProvider delay={150}>
      <motion.div
        initial={reducedMotion ? false : { opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="flex flex-col gap-8"
      >
        <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm text-muted-foreground">
          <span className="font-display text-base font-medium text-foreground">
            {techniques.length} techniques
          </span>
          <span className="opacity-60">live in this METIS today</span>
          <span className="ml-auto rounded-full border border-emerald-400/25 bg-emerald-400/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.16em] text-emerald-200">
            {totalActive} active
          </span>
        </header>

        {grouped.map(({ pillar, items, active }) => (
          <section key={pillar} className="flex flex-col gap-3">
            <div className="flex items-baseline gap-2">
              <h2 className="font-display text-sm font-semibold uppercase tracking-[0.18em] text-foreground/80">
                {PILLAR_LABEL[pillar]}
              </h2>
              <span className="text-[11px] text-muted-foreground/70">
                {active} of {items.length} active
              </span>
            </div>
            <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {items.map((technique) => (
                <li key={technique.id} className="contents">
                  <TechniqueCard technique={technique} onToggle={onToggle} />
                </li>
              ))}
            </ul>
          </section>
        ))}
      </motion.div>
    </TooltipProvider>
  );
}

interface PillarGroup {
  pillar: ForgePillar;
  items: ForgeTechnique[];
  active: number;
}

const PILLAR_ORDER: ForgePillar[] = [
  "cortex",
  "companion",
  "cosmos",
  "cross-cutting",
];

function groupByPillar(techniques: ForgeTechnique[]): PillarGroup[] {
  const buckets = new Map<ForgePillar, ForgeTechnique[]>();
  for (const technique of techniques) {
    const bucket = buckets.get(technique.pillar) ?? [];
    bucket.push(technique);
    buckets.set(technique.pillar, bucket);
  }
  // Sort each bucket so active techniques appear first while
  // preserving the registry order within active/standby groups.
  for (const bucket of buckets.values()) {
    bucket.sort((a, b) => {
      if (a.enabled === b.enabled) return 0;
      return a.enabled ? -1 : 1;
    });
  }
  return PILLAR_ORDER.flatMap((pillar) => {
    const items = buckets.get(pillar);
    if (!items || items.length === 0) return [];
    const active = items.filter((t) => t.enabled).length;
    return [{ pillar, items, active }];
  });
}
