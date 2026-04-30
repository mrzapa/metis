"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Loader2, Sparkles, TriangleAlert, X } from "lucide-react";
import {
  acceptForgeCandidate,
  listForgeCandidates,
  rejectForgeCandidate,
  type ForgeCandidateRecord,
} from "@/lib/api";

// M14 Phase 5 — review pane for the seedling's skill candidates.
// M06 already populates ``skill_candidates.db`` whenever a
// high-convergence agentic run looks like a generalisable pattern;
// this pane lets the user accept (drafts a SKILL.md, flips the
// settings override that activates it) or dismiss (marks promoted +
// rejected so the auto-promotion path skips it too).
//
// Mounted between the proposal review pane and the technique
// gallery on /forge. Hidden when there are no pending candidates
// so steady-state users don't see noise.

interface CandidateSkillsPaneProps {
  /** Bumping this prop refetches — useful after M06 emits a new
   *  candidate and the parent wants to surface it without a manual
   *  reload. */
  refreshKey?: number;
}

export function CandidateSkillsPane({ refreshKey = 0 }: CandidateSkillsPaneProps) {
  const [candidates, setCandidates] = useState<ForgeCandidateRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [slugDrafts, setSlugDrafts] = useState<Record<number, string>>({});

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const payload = await listForgeCandidates();
      setCandidates(payload.candidates);
      // Reset slug drafts when the list changes; default each row's
      // slug to the server-supplied default.
      const next: Record<number, string> = {};
      for (const candidate of payload.candidates) {
        next[candidate.id] = candidate.default_slug;
      }
      setSlugDrafts(next);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to load candidates.";
      setError(message);
      setCandidates([]);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh, refreshKey]);

  const handleAccept = async (candidate: ForgeCandidateRecord) => {
    if (pendingId !== null) return;
    setActionError(null);
    setPendingId(candidate.id);
    try {
      const slug = slugDrafts[candidate.id] || candidate.default_slug;
      await acceptForgeCandidate(
        candidate.id,
        slug !== candidate.default_slug ? slug : undefined,
      );
      await refresh();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Accept failed.";
      setActionError(message);
    } finally {
      setPendingId(null);
    }
  };

  const handleReject = async (candidate: ForgeCandidateRecord) => {
    if (pendingId !== null) return;
    setActionError(null);
    setPendingId(candidate.id);
    try {
      await rejectForgeCandidate(candidate.id);
      await refresh();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Dismiss failed.";
      setActionError(message);
    } finally {
      setPendingId(null);
    }
  };

  if (candidates === null) {
    return null; // Initial fetch — keep the page quiet.
  }

  if (error) {
    return (
      <div
        role="alert"
        data-testid="forge-candidate-pane-error"
        className="flex items-start gap-2 rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs text-destructive"
      >
        <TriangleAlert className="mt-0.5 size-4 shrink-0" />
        <span>{error}</span>
      </div>
    );
  }

  if (candidates.length === 0) {
    return null;
  }

  return (
    <section
      data-testid="forge-candidate-pane"
      className="flex flex-col gap-3 rounded-2xl border border-emerald-400/15 bg-emerald-400/[0.03] p-5"
    >
      <header>
        <div className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="flex size-8 items-center justify-center rounded-xl border border-emerald-400/30 bg-emerald-400/10 text-emerald-200"
          >
            <Sparkles className="size-4" />
          </span>
          <h2 className="font-display text-base font-semibold text-foreground">
            Candidate skills
          </h2>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          High-convergence patterns the seedling captured overnight.{" "}
          {candidates.length === 1
            ? "One pattern is waiting on your review."
            : `${candidates.length} patterns are waiting on your review.`}{" "}
          Accept drafts a <code className="font-mono">SKILL.md</code> and
          turns the skill on for you.
        </p>
      </header>

      {actionError ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/25 bg-destructive/10 px-3 py-2 text-[11px] text-destructive"
        >
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          <span>{actionError}</span>
        </div>
      ) : null}

      <ul className="flex flex-col gap-2">
        {candidates.map((candidate) => (
          <li key={candidate.id}>
            <CandidateRow
              candidate={candidate}
              slugDraft={slugDrafts[candidate.id] ?? candidate.default_slug}
              onSlugChange={(next) =>
                setSlugDrafts((current) => ({ ...current, [candidate.id]: next }))
              }
              pending={pendingId === candidate.id}
              actionsDisabled={pendingId !== null}
              onAccept={() => handleAccept(candidate)}
              onReject={() => handleReject(candidate)}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

interface CandidateRowProps {
  candidate: ForgeCandidateRecord;
  slugDraft: string;
  onSlugChange: (next: string) => void;
  pending: boolean;
  actionsDisabled: boolean;
  onAccept: () => void;
  onReject: () => void;
}

function CandidateRow({
  candidate,
  slugDraft,
  onSlugChange,
  pending,
  actionsDisabled,
  onAccept,
  onReject,
}: CandidateRowProps) {
  const scorePct = (candidate.convergence_score * 100).toFixed(0);
  return (
    <div
      data-testid="forge-candidate-row"
      data-candidate-id={candidate.id}
      className="flex flex-col gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-3"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="font-display text-sm font-medium text-foreground">
          {candidate.query_text}
        </h3>
        <span
          className="shrink-0 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-emerald-200"
          title="Agentic-loop convergence score from the originating run"
        >
          {scorePct}% converged
        </span>
      </header>

      {candidate.trace_excerpt ? (
        <p className="rounded-md border border-white/8 bg-white/4 px-2 py-1 font-mono text-[10.5px] leading-snug text-muted-foreground/85">
          {candidate.trace_excerpt}
        </p>
      ) : null}

      <div className="flex flex-col gap-1">
        <label
          className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground/70"
          htmlFor={`forge-candidate-slug-${candidate.id}`}
        >
          Skill slug
        </label>
        <input
          id={`forge-candidate-slug-${candidate.id}`}
          type="text"
          value={slugDraft}
          onChange={(event) => onSlugChange(event.target.value)}
          disabled={actionsDisabled}
          spellCheck={false}
          autoComplete="off"
          className="rounded-md border border-white/10 bg-black/25 px-2 py-1 font-mono text-xs text-foreground/90 outline-none placeholder:text-muted-foreground/55 focus:border-emerald-300/40 focus-visible:ring-2 focus-visible:ring-emerald-300/30 disabled:opacity-60"
        />
      </div>

      <footer className="flex flex-wrap items-center justify-end gap-2">
        <button
          type="button"
          onClick={onReject}
          disabled={actionsDisabled}
          className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-white/4 px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-white/20 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
        >
          <X className="size-3" aria-hidden="true" />
          Dismiss
        </button>
        <button
          type="button"
          onClick={onAccept}
          disabled={actionsDisabled || slugDraft.trim().length === 0}
          className="inline-flex items-center gap-1 rounded-md border border-emerald-400/35 bg-emerald-400/12 px-2.5 py-1 text-xs font-medium text-emerald-100 transition-colors hover:border-emerald-400/55 hover:bg-emerald-400/18 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending ? (
            <Loader2 className="size-3 animate-spin" aria-hidden="true" />
          ) : (
            <Check className="size-3" aria-hidden="true" />
          )}
          {pending ? "Drafting…" : "Accept (draft skill)"}
        </button>
      </footer>
    </div>
  );
}
