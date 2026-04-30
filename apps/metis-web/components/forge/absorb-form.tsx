"use client";

import { useState } from "react";
import { Loader2, Send, Sparkles, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  absorbForgeUrl,
  type ForgeAbsorbResponse,
  type ForgePillar,
} from "@/lib/api";
import { PILLAR_LABEL, PILLAR_TONE } from "@/components/forge/pillar";

// M14 Phase 4a — "Absorb a technique" form at the top of the Forge
// gallery. Accepts an arxiv URL, POSTs it to ``/v1/forge/absorb``,
// and renders the response inline. The server side runs the
// fetch → cross-reference → LLM-summary pipeline; the UI is just
// "submit, render result, show errors honestly".
//
// Phase 4a explicit boundaries:
// * No persistence — the result is in-memory only. Refreshing the
//   page loses it. Phase 4b adds the proposals.db review pane.
// * arxiv-only — non-arxiv URLs come back with
//   ``source_kind="unsupported"`` and we show the user a clear
//   message rather than pretending to process them.
// * The pipeline NEVER writes engine code. The proposal is a
//   structured *document*; per ADR 0014 the user must hand-review
//   before any engine change ships.

export function AbsorbForm() {
  const [url, setUrl] = useState("");
  const [result, setResult] = useState<ForgeAbsorbResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending) return;
    const trimmed = url.trim();
    if (!trimmed) return;
    setError(null);
    setPending(true);
    try {
      const payload = await absorbForgeUrl(trimmed);
      setResult(payload);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Absorb request failed.";
      setError(message);
      setResult(null);
    } finally {
      setPending(false);
    }
  };

  return (
    <section
      data-testid="forge-absorb-form-section"
      className="flex flex-col gap-4 rounded-2xl border border-amber-300/15 bg-gradient-to-br from-amber-300/[0.06] via-transparent to-violet-400/[0.05] p-5"
    >
      <header className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="flex size-9 items-center justify-center rounded-xl border border-amber-300/30 bg-amber-300/10 text-amber-200"
        >
          <Sparkles className="size-4" />
        </span>
        <div>
          <h2 className="font-display text-base font-semibold text-foreground">
            Absorb a technique
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Paste an arxiv URL — your METIS will read the abstract, surface anything
            it already does, and propose a name + claim + pillar for genuinely new
            techniques. No code is written; the proposal is yours to review.
          </p>
        </div>
      </header>

      <form
        data-testid="forge-absorb-form"
        onSubmit={handleSubmit}
        className="flex flex-col gap-2 sm:flex-row sm:items-stretch"
      >
        <label className="sr-only" htmlFor="forge-absorb-url">
          Paper or article URL
        </label>
        <input
          id="forge-absorb-url"
          type="url"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder="https://arxiv.org/abs/2501.12345"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          disabled={pending}
          className="flex-1 rounded-xl border border-white/10 bg-black/25 px-3 py-2 text-sm text-foreground/95 outline-none placeholder:text-muted-foreground/55 focus:border-amber-300/40 focus-visible:ring-2 focus-visible:ring-amber-300/40 disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={pending || url.trim().length === 0}
          className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-amber-300/35 bg-amber-300/10 px-4 py-2 text-sm font-medium text-amber-100 transition-colors hover:border-amber-300/55 hover:bg-amber-300/16 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:ring-2 focus-visible:ring-amber-300/55 focus-visible:outline-none"
        >
          {pending ? (
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          ) : (
            <Send className="size-4" aria-hidden="true" />
          )}
          {pending ? "Absorbing…" : "Absorb"}
        </button>
      </form>

      {error ? (
        <div
          role="alert"
          data-testid="forge-absorb-error"
          className="flex items-start gap-2 rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs text-destructive"
        >
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      {result ? <AbsorbResult result={result} /> : null}
    </section>
  );
}

function AbsorbResult({ result }: { result: ForgeAbsorbResponse }) {
  if (result.source_kind === "error") {
    return (
      <div
        data-testid="forge-absorb-result"
        className="rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs text-destructive"
      >
        {result.error ?? "Could not process that URL."}
      </div>
    );
  }
  if (result.source_kind === "unsupported") {
    return (
      <div
        data-testid="forge-absorb-result"
        className="rounded-xl border border-amber-300/20 bg-amber-300/5 px-3 py-2 text-xs text-amber-100/80"
      >
        Phase 4a only ingests <code className="font-mono">arxiv.org</code>{" "}
        URLs. Non-arxiv ingestion is a follow-up phase.
      </div>
    );
  }

  return (
    <div
      data-testid="forge-absorb-result"
      className="flex flex-col gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-4"
    >
      <header className="flex flex-col gap-0.5">
        <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">
          arxiv
        </span>
        <h3 className="font-display text-sm font-semibold text-foreground">
          {result.title}
        </h3>
        <a
          href={result.source_url}
          target="_blank"
          rel="noreferrer"
          className="text-[11px] text-muted-foreground/70 underline-offset-2 hover:text-foreground/80 hover:underline"
        >
          {result.source_url}
        </a>
      </header>

      {result.matches.length > 0 ? <MatchesPanel matches={result.matches} /> : null}
      {result.proposal ? (
        <ProposalPanel proposal={result.proposal} />
      ) : (
        <p className="rounded-md border border-white/8 bg-white/3 px-3 py-2 text-[11px] text-muted-foreground/80">
          Couldn&apos;t draft a proposal — make sure an LLM provider is configured
          in <code className="font-mono">/settings</code>. The matches above still
          show what METIS already does.
        </p>
      )}
    </div>
  );
}

function MatchesPanel({ matches }: { matches: ForgeAbsorbResponse["matches"] }) {
  return (
    <div data-testid="forge-absorb-matches" className="flex flex-col gap-2">
      <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground/70">
        Already in your METIS
      </p>
      <ul className="flex flex-col gap-1.5">
        {matches.map((match) => (
          <li
            key={match.id}
            className="flex items-center justify-between gap-3 rounded-lg border border-white/8 bg-white/3 px-3 py-2"
          >
            <div className="min-w-0">
              <a
                href={`#${match.id}`}
                className="text-sm font-medium text-foreground/90 hover:text-foreground hover:underline"
              >
                {match.name}
              </a>
              <p className="mt-0.5 line-clamp-1 text-[11px] text-muted-foreground/75">
                {match.description}
              </p>
            </div>
            <span
              className={cn(
                "shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em]",
                PILLAR_TONE[match.pillar],
              )}
            >
              {PILLAR_LABEL[match.pillar]}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ProposalPanel({ proposal }: { proposal: NonNullable<ForgeAbsorbResponse["proposal"]> }) {
  const pillar: ForgePillar = proposal.pillar_guess;
  return (
    <div
      data-testid="forge-absorb-proposal"
      className="flex flex-col gap-2 rounded-xl border border-violet-400/20 bg-violet-400/[0.06] p-3"
    >
      <header className="flex items-baseline justify-between gap-3">
        <h4 className="font-display text-sm font-semibold text-foreground">
          {proposal.name}
        </h4>
        <span
          className={cn(
            "shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em]",
            PILLAR_TONE[pillar],
          )}
        >
          {PILLAR_LABEL[pillar]}
        </span>
      </header>
      <p className="text-xs leading-relaxed text-foreground/85">{proposal.claim}</p>
      <p className="text-[11px] leading-relaxed text-muted-foreground/85">
        <span className="text-muted-foreground/60">Sketch — </span>
        {proposal.implementation_sketch}
      </p>
      <p className="rounded-md border border-violet-400/20 bg-violet-400/8 px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-violet-200/80">
        Phase 4a — proposal only · review and pick a setting yourself
      </p>
    </div>
  );
}
