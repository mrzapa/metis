"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, useReducedMotion } from "motion/react";
import {
  BookOpen,
  CheckCircle2,
  FlaskConical,
  GitBranch,
  Lightbulb,
  Loader2,
  Plus,
  Tag,
  TestTube2,
  TriangleAlert,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { PageChrome } from "@/components/shell/page-chrome";
import { AnimatedLucideIcon } from "@/components/ui/animated-lucide-icon";
import { cn } from "@/lib/utils";
import {
  listImprovements,
  createImprovement,
  type ArtifactType,
  type CreateImprovementRequest,
  type ImprovementEntry,
  type ImprovementStatus,
} from "@/lib/api";

// ── Constants ────────────────────────────────────────────────────────────────

const ARTIFACT_TYPES: ArtifactType[] = [
  "source",
  "idea",
  "hypothesis",
  "experiment",
  "algorithm",
  "result",
];

const STATUSES: ImprovementStatus[] = [
  "draft",
  "active",
  "testing",
  "complete",
  "archived",
];

const ARTIFACT_ICONS: Record<ArtifactType, React.ElementType> = {
  source: BookOpen,
  idea: Lightbulb,
  hypothesis: FlaskConical,
  experiment: TestTube2,
  algorithm: GitBranch,
  result: CheckCircle2,
};

const ARTIFACT_COLORS: Record<ArtifactType, string> = {
  source: "text-sky-400 bg-sky-400/10 border-sky-400/20",
  idea: "text-yellow-400 bg-yellow-400/10 border-yellow-400/20",
  hypothesis: "text-violet-400 bg-violet-400/10 border-violet-400/20",
  experiment: "text-orange-400 bg-orange-400/10 border-orange-400/20",
  algorithm: "text-emerald-400 bg-emerald-400/10 border-emerald-400/20",
  result: "text-primary bg-primary/10 border-primary/20",
};

const STATUS_COLORS: Record<ImprovementStatus, string> = {
  draft: "border-white/10 bg-white/5 text-muted-foreground",
  active: "border-primary/25 bg-primary/15 text-primary",
  testing: "border-amber-400/25 bg-amber-400/10 text-amber-400",
  complete: "border-emerald-500/25 bg-emerald-500/10 text-emerald-400",
  archived: "border-white/8 bg-white/4 text-muted-foreground/60",
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

// ── Sub-components ───────────────────────────────────────────────────────────

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1 text-xs font-medium transition-all",
        active
          ? "border-primary/40 bg-primary/15 text-primary"
          : "border-white/10 bg-white/4 text-muted-foreground hover:border-white/20 hover:text-foreground",
      )}
    >
      {label}
    </button>
  );
}

function TypeChip({
  type,
  selected,
  onClick,
}: {
  type: ArtifactType;
  selected: boolean;
  onClick: () => void;
}) {
  const Icon = ARTIFACT_ICONS[type];
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-all",
        selected
          ? ARTIFACT_COLORS[type]
          : "border-white/10 bg-white/4 text-muted-foreground hover:border-white/20 hover:text-foreground",
      )}
    >
      <Icon className="size-3" />
      {type}
    </button>
  );
}

function EntryCard({ entry }: { entry: ImprovementEntry }) {
  const Icon = ARTIFACT_ICONS[entry.artifact_type];
  const reducedMotion = useReducedMotion();
  return (
    <motion.div
      layout
      initial={reducedMotion ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="group flex flex-col rounded-2xl border border-white/8 bg-white/3 p-4 transition-colors hover:border-white/14 hover:bg-white/5"
    >
      {/* Type badge */}
      <div
        className={cn(
          "mb-3 inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
          ARTIFACT_COLORS[entry.artifact_type],
        )}
      >
        <Icon className="size-3" />
        {entry.artifact_type}
      </div>

      {/* Title */}
      <h3 className="mb-1.5 font-display text-sm font-semibold leading-snug text-foreground/90">
        {entry.title}
      </h3>

      {/* Summary */}
      {entry.summary && (
        <p className="mb-3 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
          {entry.summary}
        </p>
      )}

      <div className="mt-auto flex items-center justify-between gap-2">
        {/* Status */}
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-xs font-medium",
            STATUS_COLORS[entry.status],
          )}
        >
          {entry.status}
        </span>

        {/* Tags */}
        {entry.tags.length > 0 && (
          <div className="flex items-center gap-1 overflow-hidden">
            <Tag className="size-3 shrink-0 text-muted-foreground/50" />
            <span className="truncate text-xs text-muted-foreground/60">
              {entry.tags.slice(0, 3).join(", ")}
              {entry.tags.length > 3 ? ` +${entry.tags.length - 3}` : ""}
            </span>
          </div>
        )}

        {/* Date */}
        <time className="shrink-0 text-xs text-muted-foreground/50">
          {formatDate(entry.created_at)}
        </time>
      </div>
    </motion.div>
  );
}

// ── New Entry Dialog ─────────────────────────────────────────────────────────

const BLANK_FORM: CreateImprovementRequest = {
  artifact_type: "idea",
  title: "",
  summary: "",
  body_md: "",
  tags: [],
};

function NewEntryDialog({ onCreated }: { onCreated: (entry: ImprovementEntry) => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<CreateImprovementRequest>(BLANK_FORM);
  const [tagsRaw, setTagsRaw] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setForm(BLANK_FORM);
    setTagsRaw("");
    setError(null);
  }

  async function handleSubmit() {
    if (!form.title.trim()) {
      setError("Title is required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const tags = tagsRaw
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const entry = await createImprovement({ ...form, tags });
      onCreated(entry);
      reset();
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create entry.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) reset(); }}>
      <DialogTrigger render={<Button variant="default" size="sm" />}>
        <AnimatedLucideIcon icon={Plus} mode="hoverLift" />
        New Entry
      </DialogTrigger>

      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New Improvement Entry</DialogTitle>
          <DialogDescription>
            Capture a source, idea, hypothesis, experiment, algorithm, or result.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          {/* Artifact type */}
          <div>
            <span className="mb-1.5 block text-xs font-medium text-muted-foreground">Type</span>
            <div className="flex flex-wrap gap-1.5">
              {ARTIFACT_TYPES.map((t) => (
                <TypeChip
                  key={t}
                  type={t}
                  selected={form.artifact_type === t}
                  onClick={() => setForm((f) => ({ ...f, artifact_type: t }))}
                />
              ))}
            </div>
          </div>

          {/* Title */}
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Title <span className="text-destructive">*</span>
            </label>
            <Input
              placeholder="Short descriptive title"
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
          </div>

          {/* Summary */}
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Summary</label>
            <Textarea
              placeholder="One-sentence description"
              rows={2}
              value={form.summary ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, summary: e.target.value }))}
            />
          </div>

          {/* Tags */}
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Tags <span className="opacity-50">(comma-separated)</span>
            </label>
            <Input
              placeholder="retrieval, rag, reranking"
              value={tagsRaw}
              onChange={(e) => setTagsRaw(e.target.value)}
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 rounded-lg border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              <TriangleAlert className="size-3.5 shrink-0" />
              {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="default"
            size="sm"
            disabled={submitting}
            onClick={handleSubmit}
          >
            {submitting ? <Loader2 className="size-3.5 animate-spin" /> : null}
            {submitting ? "Saving…" : "Save Entry"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function ImprovementsPage() {
  const [entries, setEntries] = useState<ImprovementEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<ArtifactType | null>(null);
  const [filterStatus, setFilterStatus] = useState<ImprovementStatus | null>(null);
  const reducedMotion = useReducedMotion();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listImprovements();
      setEntries(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load improvements.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = entries.filter((e) => {
    if (filterType && e.artifact_type !== filterType) return false;
    if (filterStatus && e.status !== filterStatus) return false;
    return true;
  });

  function handleCreated(entry: ImprovementEntry) {
    setEntries((prev) => [entry, ...prev]);
  }

  const actions = <NewEntryDialog onCreated={handleCreated} />;

  return (
    <PageChrome
      title="Improvement Pipeline"
      description="Track sources, ideas, hypotheses, experiments, algorithms, and results."
      eyebrow="METIS"
      actions={actions}
    >
      <div className="mx-auto max-w-5xl space-y-6 py-2">
        {/* ── Filters ── */}
        <motion.div
          initial={reducedMotion ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="flex flex-wrap items-center gap-2"
        >
          <span className="text-xs font-medium text-muted-foreground/60 uppercase tracking-wide">
            Type
          </span>
          {ARTIFACT_TYPES.map((t) => (
            <TypeChip
              key={t}
              type={t}
              selected={filterType === t}
              onClick={() => setFilterType((prev) => (prev === t ? null : t))}
            />
          ))}

          <span className="mx-1 h-4 w-px bg-white/10" />

          <span className="text-xs font-medium text-muted-foreground/60 uppercase tracking-wide">
            Status
          </span>
          {STATUSES.map((s) => (
            <FilterChip
              key={s}
              label={s}
              active={filterStatus === s}
              onClick={() => setFilterStatus((prev) => (prev === s ? null : s))}
            />
          ))}

          {(filterType || filterStatus) && (
            <button
              onClick={() => { setFilterType(null); setFilterStatus(null); }}
              className="ml-1 text-xs text-muted-foreground/60 hover:text-foreground underline underline-offset-2 transition-colors"
            >
              Clear filters
            </button>
          )}
        </motion.div>

        {/* ── Content ── */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="size-6 animate-spin text-muted-foreground/50" />
          </div>
        ) : error ? (
          <div className="flex items-center justify-center py-20">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <TriangleAlert className="size-4 text-amber-400" />
              {error}
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<AnimatedLucideIcon icon={Lightbulb} mode="idlePulse" className="size-6" />}
            title={filterType || filterStatus ? "No matching entries" : "No entries yet"}
            description={
              filterType || filterStatus
                ? "Try removing filters to see all entries."
                : "Create your first improvement entry using the button above."
            }
          />
        ) : (
          <motion.div
            layout
            className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
          >
            {filtered.map((entry) => (
              <EntryCard key={entry.entry_id} entry={entry} />
            ))}
          </motion.div>
        )}
      </div>
    </PageChrome>
  );
}
