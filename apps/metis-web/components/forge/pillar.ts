import type { LucideIcon } from "lucide-react";
import { Brain, Network, Sparkles, Sprout } from "lucide-react";
import type { ForgePillar } from "@/lib/api";

// Pillar-level identity for the Forge gallery. Phase 1 inlined the
// label and tone strings on the page; lifting them here keeps the
// card component reusable when later phases (toggle wiring, candidate
// review, technique detail) need the same vocabulary.
export const PILLAR_LABEL: Record<ForgePillar, string> = {
  cosmos: "Cosmos",
  companion: "Companion",
  cortex: "Cortex",
  "cross-cutting": "Cross-cutting",
};

// Pill-style tone classes — the muted variant the Phase 1 page used.
// Values trace back to ADR 0006's 2D constellation palette: each
// pillar's accent matches the constellation faculty colour family.
export const PILLAR_TONE: Record<ForgePillar, string> = {
  cosmos: "border-sky-400/25 bg-sky-400/10 text-sky-300",
  companion: "border-emerald-400/25 bg-emerald-400/10 text-emerald-300",
  cortex: "border-violet-400/25 bg-violet-400/10 text-violet-300",
  "cross-cutting": "border-white/10 bg-white/5 text-muted-foreground",
};

// Stronger tone for the technique card's archetype glyph well — same
// hue family as the pill, but with enough contrast to read against
// the card's glass background.
export const PILLAR_GLYPH_TONE: Record<ForgePillar, string> = {
  cosmos: "border-sky-400/35 bg-sky-400/12 text-sky-200",
  companion: "border-emerald-400/35 bg-emerald-400/12 text-emerald-200",
  cortex: "border-violet-400/35 bg-violet-400/12 text-violet-200",
  "cross-cutting": "border-white/14 bg-white/6 text-foreground/80",
};

// One archetype icon per pillar. Per-technique icon overrides are
// possible later, but the pillar-level mapping is what makes the
// gallery feel like a *gallery* (visually grouped) instead of a
// settings list.
export const PILLAR_ICON: Record<ForgePillar, LucideIcon> = {
  cosmos: Sparkles,
  companion: Sprout,
  cortex: Brain,
  "cross-cutting": Network,
};
