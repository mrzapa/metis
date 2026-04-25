"use client";

import { useEffect, useState } from "react";
import {
  Activity,
  BookOpen,
  Code2,
  FlaskConical,
  Grid3x3,
  History,
  Loader2,
  MessageSquare,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";
import { suggestStarArchetypes } from "@/lib/api";
import type { StarArchetypeSuggestion } from "@/lib/api";

// Fallback archetype used when the API cannot detect a match (network error,
// empty file list edge case, etc.).  Matches the "scroll" backend archetype.
const DEFAULT_SCROLL_ARCHETYPE: StarArchetypeSuggestion = {
  id: "scroll",
  name: "Scroll",
  description: "Long-form prose, reports, and academic papers",
  icon_hint: "BookOpen",
  why: "No specific archetype detected — using balanced defaults.",
  settings_overrides: { chunk_size: 650, chunk_overlap: 160, retrieval_mode: "flat" },
  score: 0,
};

// ---------------------------------------------------------------------------
// Icon lookup
// ---------------------------------------------------------------------------

const ICON_MAP: Record<string, React.ElementType> = {
  BookOpen,
  Grid3x3,
  Code2,
  History,
  Activity,
  MessageSquare,
  FlaskConical,
};

function ArchetypeIcon({
  iconHint,
  className,
}: {
  iconHint: string;
  className?: string;
}) {
  const Icon = ICON_MAP[iconHint] ?? BookOpen;
  return <Icon className={className} />;
}

// ---------------------------------------------------------------------------
// Per-archetype accent colour
// ---------------------------------------------------------------------------

const ACCENT: Record<string, { ring: string; icon: string; badge: string }> = {
  scroll: {
    ring: "ring-sky-500/60",
    icon: "text-sky-300",
    badge: "bg-sky-500/12 text-sky-300 border-sky-500/20",
  },
  ledger: {
    ring: "ring-emerald-500/60",
    icon: "text-emerald-300",
    badge: "bg-emerald-500/12 text-emerald-300 border-emerald-500/20",
  },
  codex: {
    ring: "ring-violet-500/60",
    icon: "text-violet-300",
    badge: "bg-violet-500/12 text-violet-300 border-violet-500/20",
  },
  chronicle: {
    ring: "ring-amber-500/60",
    icon: "text-amber-300",
    badge: "bg-amber-500/12 text-amber-300 border-amber-500/20",
  },
  signal: {
    ring: "ring-rose-500/60",
    icon: "text-rose-300",
    badge: "bg-rose-500/12 text-rose-300 border-rose-500/20",
  },
  dispatch: {
    ring: "ring-teal-500/60",
    icon: "text-teal-300",
    badge: "bg-teal-500/12 text-teal-300 border-teal-500/20",
  },
  theorem: {
    ring: "ring-purple-500/60",
    icon: "text-purple-300",
    badge: "bg-purple-500/12 text-purple-300 border-purple-500/20",
  },
};

const DEFAULT_ACCENT = {
  ring: "ring-white/30",
  icon: "text-slate-300",
  badge: "bg-white/6 text-slate-300 border-white/12",
};

function accent(id: string) {
  return ACCENT[id] ?? DEFAULT_ACCENT;
}

// ---------------------------------------------------------------------------
// Settings badge helpers
// ---------------------------------------------------------------------------

function retrievalModeLabel(mode: unknown): string {
  if (mode === "hierarchical") return "hierarchical";
  return "flat";
}

function chunkLabel(overrides: Record<string, unknown>): string | null {
  const size = overrides.chunk_size;
  if (typeof size === "number") return `${size} tok chunks`;
  return null;
}

function specialBadge(overrides: Record<string, unknown>): string | null {
  if (overrides.build_comprehension_index && overrides.build_digest_index) return "digest + comprehension";
  if (overrides.build_comprehension_index) return "comprehension";
  if (overrides.build_digest_index) return "digest";
  return null;
}

// ---------------------------------------------------------------------------
// Single archetype card
// ---------------------------------------------------------------------------

function ArchetypeCard({
  suggestion,
  selected,
  onSelect,
  index,
}: {
  suggestion: StarArchetypeSuggestion;
  selected: boolean;
  onSelect: () => void;
  index: number;
}) {
  const a = accent(suggestion.id);
  const chunk = chunkLabel(suggestion.settings_overrides);
  const special = specialBadge(suggestion.settings_overrides);
  const mode = retrievalModeLabel(suggestion.settings_overrides.retrieval_mode);
  const reducedMotion = useReducedMotion();

  return (
    <motion.button
      type="button"
      initial={reducedMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, delay: index * 0.06, ease: [0.22, 1, 0.36, 1] }}
      onClick={onSelect}
      className={cn(
        "group relative w-full rounded-2xl border p-4 text-left transition-all duration-200",
        "border-white/8 bg-white/3 hover:bg-white/6",
        selected && [
          "ring-2",
          a.ring,
          "border-transparent",
          "bg-white/6",
        ],
      )}
    >
      {/* Score bar — subtle top stripe */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-0.5 rounded-t-2xl opacity-50 transition-opacity duration-200 group-hover:opacity-80"
        style={{
          background: `linear-gradient(90deg, currentColor ${Math.round(suggestion.score * 100)}%, transparent 100%)`,
        }}
      />

      <div className="mb-3 flex items-center justify-between gap-2">
        <div className={cn("rounded-xl border border-white/8 bg-white/5 p-2", selected && "bg-white/10")}>
          <ArchetypeIcon iconHint={suggestion.icon_hint} className={cn("size-4", a.icon)} />
        </div>
        <span className="text-[10px] font-medium tracking-[0.18em] uppercase text-slate-500">
          {Math.round(suggestion.score * 100)}% match
        </span>
      </div>

      <h5 className="font-display text-base font-semibold tracking-[-0.03em] text-white">
        {suggestion.name}
      </h5>

      <p className="mt-1 text-[12px] leading-5 text-slate-400">{suggestion.why}</p>

      {/* Indexing param badges */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        <span className={cn("rounded-md border px-2 py-0.5 text-[10px] font-medium", a.badge)}>
          {mode}
        </span>
        {chunk ? (
          <span className={cn("rounded-md border px-2 py-0.5 text-[10px] font-medium", a.badge)}>
            {chunk}
          </span>
        ) : null}
        {special ? (
          <span className={cn("rounded-md border px-2 py-0.5 text-[10px] font-medium", a.badge)}>
            {special}
          </span>
        ) : null}
      </div>
    </motion.button>
  );
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

interface StarArchetypePickerProps {
  filePaths: string[];
  selectedId: string | null;
  onSelect: (suggestion: StarArchetypeSuggestion) => void;
}

export function StarArchetypePicker({ filePaths, selectedId, onSelect }: StarArchetypePickerProps) {
  const [suggestions, setSuggestions] = useState<StarArchetypeSuggestion[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (filePaths.length === 0) {
      setSuggestions([]);
      return;
    }

    let cancelled = false;

    async function load() {
      setLoading(true);
      const results = await suggestStarArchetypes(filePaths);
      if (cancelled) return;
      setLoading(false);
      setSuggestions(results);

      // Auto-select if a clear winner (≥85% match) or only one candidate
      if (results.length > 0 && !selectedId) {
        if (results[0].score >= 0.85 || results.length === 1) {
          onSelect(results[0]);
        }
      }

      // Fallback: if no archetypes could be detected (API error or unknown
      // file type), silently adopt the default Scroll archetype so the build
      // button is never permanently blocked.
      if (results.length === 0 && !selectedId) {
        onSelect(DEFAULT_SCROLL_ARCHETYPE);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filePaths.join(",")]);

  if (filePaths.length === 0) return null;

  return (
    <div className="rounded-[1.6rem] border border-white/10 bg-black/18 p-4 sm:p-5">
      <div className="mb-4 flex items-center justify-between gap-2">
        <div>
          <h4 className="font-display text-xl font-semibold tracking-[-0.04em] text-white">
            Choose an indexing archetype
          </h4>
          <p className="mt-1 text-sm leading-6 text-slate-400">
            Each archetype tunes chunk size, overlap, and retrieval mode for your content.
          </p>
        </div>
        {loading ? <Loader2 className="size-4 animate-spin text-slate-500" /> : null}
      </div>

      {!loading && suggestions.length === 0 ? (
        <p className="text-sm text-slate-500">Could not detect a suitable archetype — a Scroll index will be used.</p>
      ) : null}

      {suggestions.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {suggestions.map((s, i) => (
            <ArchetypeCard
              key={s.id}
              suggestion={s}
              selected={selectedId === s.id}
              onSelect={() => onSelect(s)}
              index={i}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
