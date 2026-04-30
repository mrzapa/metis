"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, FileText, Loader2, Sparkles, TriangleAlert, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  acceptForgeProposal,
  listForgeProposals,
  rejectForgeProposal,
  type ForgeProposalRecord,
} from "@/lib/api";
import { PILLAR_LABEL, PILLAR_TONE } from "@/components/forge/pillar";

// M14 Phase 4b — review pane for proposals the absorb pipeline
// persisted. Lists pending proposals newest-first; "Accept" drafts
// a `skills/<slug>/SKILL.md` and marks the row accepted; "Dismiss"
// marks rejected without writing a file.
//
// Mounted between the absorb form and the technique gallery on
// `/forge`. Receives a `refreshKey` from the page so the absorb
// form can request a re-fetch after a successful absorption.
//
// Phase 4b boundaries:
// * The pane only shows pending proposals — accepted / rejected
//   rows fall out of view (Phase 4c can add an audit-history
//   section).
// * Accept writes a draft skill file but does NOT activate it.
//   `enabled_by_default: false` is hard-coded by the writer; the
//   user opens the file in their editor and opts in.

interface ProposalReviewPaneProps {
  /** Bumping this re-fetches the list — used by the absorb form
   *  after a successful proposal is persisted. */
  refreshKey?: number;
}

export function ProposalReviewPane({ refreshKey = 0 }: ProposalReviewPaneProps) {
  const [proposals, setProposals] = useState<ForgeProposalRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const payload = await listForgeProposals("pending");
      setProposals(payload.proposals);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to load proposals.";
      setError(message);
      setProposals([]);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh, refreshKey]);

  const handleAccept = async (proposal: ForgeProposalRecord) => {
    if (pendingId !== null) return;
    setActionError(null);
    setPendingId(proposal.id);
    try {
      await acceptForgeProposal(proposal.id);
      await refresh();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Accept failed.";
      setActionError(message);
    } finally {
      setPendingId(null);
    }
  };

  const handleReject = async (proposal: ForgeProposalRecord) => {
    if (pendingId !== null) return;
    setActionError(null);
    setPendingId(proposal.id);
    try {
      await rejectForgeProposal(proposal.id);
      await refresh();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Dismiss failed.";
      setActionError(message);
    } finally {
      setPendingId(null);
    }
  };

  if (proposals === null) {
    // Don't crowd the page on first paint — the gallery cards
    // already give the user something to look at while we fetch.
    return null;
  }

  if (error) {
    return (
      <div
        role="alert"
        data-testid="forge-proposal-review-error"
        className="flex items-start gap-2 rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs text-destructive"
      >
        <TriangleAlert className="mt-0.5 size-4 shrink-0" />
        <span>{error}</span>
      </div>
    );
  }

  if (proposals.length === 0) {
    // No pending proposals — render nothing so the page chrome
    // stays quiet for the steady-state user.
    return null;
  }

  return (
    <section
      data-testid="forge-proposal-review-pane"
      className="flex flex-col gap-3 rounded-2xl border border-violet-400/15 bg-violet-400/[0.04] p-5"
    >
      <header className="flex items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-base font-semibold text-foreground">
            Pending proposals
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {proposals.length === 1
              ? "One paper is waiting on your review."
              : `${proposals.length} papers are waiting on your review.`}
          </p>
        </div>
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
        {proposals.map((proposal) => (
          <li key={proposal.id}>
            <ProposalRow
              proposal={proposal}
              pending={pendingId === proposal.id}
              actionsDisabled={pendingId !== null}
              onAccept={() => handleAccept(proposal)}
              onReject={() => handleReject(proposal)}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

interface ProposalRowProps {
  proposal: ForgeProposalRecord;
  pending: boolean;
  actionsDisabled: boolean;
  onAccept: () => void;
  onReject: () => void;
}

function ProposalRow({
  proposal,
  pending,
  actionsDisabled,
  onAccept,
  onReject,
}: ProposalRowProps) {
  return (
    <div
      data-testid="forge-proposal-row"
      data-proposal-id={proposal.id}
      className="flex flex-col gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-3"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="flex flex-wrap items-baseline gap-2">
          <h3 className="font-display text-sm font-semibold text-foreground">
            {proposal.proposal_name}
          </h3>
          {proposal.source === "comet" ? (
            <span
              data-testid="forge-proposal-comet-badge"
              title="Auto-generated from your news-comet feed"
              className="inline-flex items-center gap-1 rounded-full border border-amber-300/30 bg-amber-300/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-amber-200"
            >
              <Sparkles className="size-2.5" aria-hidden="true" />
              From comet feed
            </span>
          ) : null}
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em]",
            PILLAR_TONE[proposal.proposal_pillar],
          )}
        >
          {PILLAR_LABEL[proposal.proposal_pillar]}
        </span>
      </header>
      <p className="text-xs leading-relaxed text-foreground/85">
        {proposal.proposal_claim}
      </p>
      <p className="text-[11px] leading-relaxed text-muted-foreground/85">
        <span className="text-muted-foreground/60">Sketch — </span>
        {proposal.proposal_sketch}
      </p>
      <footer className="flex flex-wrap items-center justify-between gap-2">
        <a
          href={proposal.source_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-[11px] text-muted-foreground/75 underline-offset-2 hover:text-foreground/85 hover:underline"
        >
          <FileText className="size-3" aria-hidden="true" />
          {proposal.title}
        </a>
        <div className="flex items-center gap-2">
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
            disabled={actionsDisabled}
            className="inline-flex items-center gap-1 rounded-md border border-emerald-400/35 bg-emerald-400/12 px-2.5 py-1 text-xs font-medium text-emerald-100 transition-colors hover:border-emerald-400/55 hover:bg-emerald-400/18 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending ? (
              <Loader2 className="size-3 animate-spin" aria-hidden="true" />
            ) : (
              <Check className="size-3" aria-hidden="true" />
            )}
            {pending ? "Drafting…" : "Accept (draft skill)"}
          </button>
        </div>
      </footer>
    </div>
  );
}
