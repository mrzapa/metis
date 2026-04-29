"use client";

import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { Hammer, Loader2, TriangleAlert } from "lucide-react";
import { PageChrome } from "@/components/shell/page-chrome";
import { EmptyState } from "@/components/ui/empty-state";
import { AnimatedLucideIcon } from "@/components/ui/animated-lucide-icon";
import { cn } from "@/lib/utils";
import { fetchForgeTechniques, type ForgeTechnique } from "@/lib/api";
import { useHashScroll } from "@/lib/use-hash-scroll";

const PILLAR_LABEL: Record<ForgeTechnique["pillar"], string> = {
  cosmos: "Cosmos",
  companion: "Companion",
  cortex: "Cortex",
  "cross-cutting": "Cross-cutting",
};

const PILLAR_TONE: Record<ForgeTechnique["pillar"], string> = {
  cosmos: "border-sky-400/25 bg-sky-400/10 text-sky-300",
  companion: "border-emerald-400/25 bg-emerald-400/10 text-emerald-300",
  cortex: "border-violet-400/25 bg-violet-400/10 text-violet-300",
  "cross-cutting": "border-white/10 bg-white/5 text-muted-foreground",
};

export default function ForgePage() {
  const [techniques, setTechniques] = useState<ForgeTechnique[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    let cancelled = false;
    fetchForgeTechniques()
      .then((payload) => {
        if (cancelled) return;
        setTechniques(payload.techniques);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load Forge techniques.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Honour `/forge#<technique-id>` deep-links once the inventory has
  // rendered. Browsers run automatic fragment navigation before the
  // client-side fetch completes, so without this the constellation's
  // Skills-sector stars (Phase 2) and the dock's "absorbed X" event
  // copy (Phase 3) would land at the top of the page on first load.
  useHashScroll(techniques !== null);

  const enabledCount = techniques?.filter((t) => t.enabled).length ?? 0;
  const totalCount = techniques?.length ?? 0;

  return (
    <PageChrome
      eyebrow="METIS · The Forge"
      title="The Forge"
      description="Every frontier technique your METIS already carries. Phase 2 will turn each one into a card you can light up; today's surface confirms the gallery is live and the inventory is honest."
    >
      <div className="mx-auto flex max-w-4xl flex-col gap-6 py-2">
        {error ? (
          <div className="flex items-center gap-2 rounded-xl border border-destructive/25 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <TriangleAlert className="size-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : techniques === null ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="size-6 animate-spin text-muted-foreground/50" />
          </div>
        ) : techniques.length === 0 ? (
          <EmptyState
            icon={<AnimatedLucideIcon icon={Hammer} mode="idlePulse" className="size-6" />}
            title="No techniques registered yet"
            description="The Forge inventory is empty in this build. Phase 2 will populate the registry."
          />
        ) : (
          <motion.div
            initial={reducedMotion ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: "easeOut" }}
            className="flex flex-col gap-4"
          >
            <div className="flex items-baseline gap-2 text-sm text-muted-foreground">
              <span className="font-display text-base font-medium text-foreground">
                {totalCount} techniques
              </span>
              <span className="opacity-60">live in this METIS today</span>
              <span className="ml-auto text-xs uppercase tracking-[0.18em] text-muted-foreground/60">
                {enabledCount} on by default
              </span>
            </div>
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {techniques.map((technique) => (
                <li
                  key={technique.id}
                  id={technique.id}
                  className="rounded-xl border border-white/8 bg-white/3 px-4 py-3 transition-colors hover:border-white/14"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-display text-sm font-semibold text-foreground/90">
                      {technique.name}
                    </span>
                    <span
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em]",
                        PILLAR_TONE[technique.pillar],
                      )}
                    >
                      {PILLAR_LABEL[technique.pillar]}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                    {technique.description}
                  </p>
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground/60">
              Phase 1 ships the inventory and the route. Phase 2 introduces interactive cards,
              pillar-coloured archetypes, and a star per active technique in the constellation&apos;s
              Skills sector.
            </p>
          </motion.div>
        )}
      </div>
    </PageChrome>
  );
}
