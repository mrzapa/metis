# Prompt agents

> One-page briefing on how to launch a fresh agent against METIS work. The goal
> is: minimum prompt that makes the agent self-sufficient, and the minimum
> context it has to read before committing code.

## How to use this file

- **Starting a new agent session** (either interactively, or via a headless
  harness like Symphony/Codex): paste the *Onboarding prompt* below into the
  agent's first message, swapping in any specific task.
- **For bulk / parallel dispatches**: each sub-agent gets the prompt scoped to
  its task. They each read `VISION.md` + `plans/IMPLEMENTATION.md` +
  `plans/README.md` + their milestone's plan doc and nothing else.
- **Update this file** when the process changes — new rituals, new intake
  rules, new "read this first" files. Keep it under 300 lines; a fresh agent
  should finish reading it in under 2 minutes.

---

## Onboarding prompt (paste-ready)

Copy everything inside the fence, fill in the `<…>` placeholders, and hand it
to a new agent.

```
You are picking up work on METIS, a local-first AI workspace described in
`VISION.md`. Read these four files in order before touching any code:

1. `VISION.md` — product, pillars, "what we are NOT doing", roadmap order.
2. `plans/README.md` — how the plans/ folder works: claim rules, plan-doc
   frontmatter, intake workflow for external asks, parallel-work rules.
3. `plans/IMPLEMENTATION.md` — the live milestone table. Find a row with
   `Status: Ready` or `Status: In progress` where the `Claim` column is
   blank. That's the task.
4. The plan doc linked from the chosen row (usually `plans/<slug>/plan.md`).
   Read its `Progress`, `Next up`, `Blockers`, and `Notes for the next agent`
   sections in full. `Next up` is where your concrete first actions live.

Never start coding before those four reads complete.

**Your task:** <one sentence — e.g. "claim M17 Phase 6 and implement the
enforcement + prove-offline affordance per the plan's Phase 6 section." If
the task is open-ended, say so: "scan the table for the highest-priority
`Ready` row and propose what to pick before claiming.">

**Ground rules:**

- **Verify the row is genuinely open before you claim.** The table lags
  reality. Before committing a claim, grep the codebase for the key
  artefacts the milestone's plan doc promises. Look at the plan's
  *Progress* / *Next up* / *Notes for the next agent* sections, pull out
  the named files, functions, settings keys, or endpoints that are
  supposed to be delivered, and check they aren't **already** present on
  `main`. If they are — run the milestone's tests to confirm — the row
  is stale. **Turn your branch into a docs-only reconciliation PR** that
  flips the row to `Landed` with the real merge SHA + date (use
  `git log --grep="<milestone keyword>"` and `git log --oneline --all
  <file>` to find it), and mention any sibling rows from the same era
  that smell similarly stale (often a whole batch shipped without the
  table being updated). Then start fresh work on a different branch
  against a genuinely open row. This happened with M12 Phase 1 (PR #513)
  and M03 Phase 1 (caught 2026-04-20 on `codex/m03-phase1-iterrag-convergence`) —
  both were marked `Ready` with shipped code. The claim-commit rule
  below still applies to the reconciliation PR: small, standalone,
  docs-only.
- **Claim before you code.** Set the `Claim` column in `plans/IMPLEMENTATION.md`
  to your branch name and `Last updated` to today's date. Commit that row
  update as a standalone `docs(m##): claim …` commit on a fresh branch off
  `main`. This is how other agents know the row is taken.
- **Respect the plan's phase boundaries.** The plan doc's phases are usually
  shippable slices. Don't try to land the entire milestone in one PR — land
  one phase, open the PR, let it merge, then start the next phase on a new
  branch. Each PR title should read `feat(m##): Phase N — <summary>` or the
  equivalent convention you see in recent merges (`git log --oneline`).
- **Harvest first, greenfield second.** Every M## plan doc has a harvest
  inventory describing what already exists in the codebase that the work
  can wrap or extend. Read it. Most milestones are "thin new surface over
  existing thick infrastructure" — if you find yourself designing something
  from scratch that the plan says already exists, re-read the plan.
- **Branch naming:** `claude/m##-<short-descriptor>` (e.g.
  `claude/m17-phase6-enforcement`). If you're running under a different
  identity, substitute your agent name.
- **CI guard:** `tests/test_network_audit_no_raw_urlopen.py` will fail any
  new stdlib `urllib.request.urlopen` outside the audit module. Use
  `audited_urlopen` from `metis_app.network_audit`.
- **Commit hygiene:** conventional-commit style
  (`feat(m##): …`, `fix(m##): …`, `docs(m##): …`, `test(m##): …`).
  Every commit gets the `Co-Authored-By` trailer that appears in `git log`.
- **Verification before completion:**
  - Backend: `python -m pytest tests/ --ignore=tests/_litestar_helpers
    --ignore=tests/test_api_app.py` must be green (those two exclusions
    are pre-existing unrelated issues).
  - Frontend: `cd apps/metis-web && npx tsc --noEmit && npx vitest run`
    must be clean.
  - Lint: `ruff check <touched files>` must pass.
- **When you finish the phase:** push the branch, open a PR with a
  summary that mirrors the commit messages, and stop. Do not immediately
  start the next phase — let the human review the PR first.

**Tool skills available in this harness** (invoke via the Skill tool if the
environment supports it):

- `superpowers:subagent-driven-development` — the review loop we use:
  implementer → spec review → code-quality review → polish → final
  integration review → PR. Dispatch sub-agents for discrete sub-tasks.
- `superpowers:dispatching-parallel-agents` — when two independent slices
  can run concurrently (different file trees, different plan docs).
- `superpowers:test-driven-development` — when writing new logic, tests
  first.
- `superpowers:verification-before-completion` — reminder checklist: run
  the three verification commands above before claiming "done".

**When you hit a genuine blocker** (spec mismatch, external decision
needed, test infrastructure broken), stop and ask. Do not guess your way
through — the previous M17 agent wasted a full pass building code
against a spec that predated a prior refactor because they didn't stop
to read the current codebase first.

You can now begin. Start with the four required reads.
```

---

## Variant: intake workflow (external ask)

When the user asks you to implement something from outside the repo — a
GitHub repo, a paper, a tweet, a technique, a screenshot, a concept — **do
not start coding**. Use this shorter prompt instead:

```
The user has asked me to look at <source>. I will file it in
`plans/IDEAS.md` under *Open ideas* with:

- **Source:** <link / paper title / description>
- **Ask:** <one-line user summary>
- **Context:** <what the user said>
- **Filed:** <today's date> by <session id>

Then produce a triage review in the same message:

- **What it is** — a paragraph from a genuine read of the source, not a
  copy-paste.
- **Pillar fit** — Cosmos / Companion / Cortex / Cross-cutting / doesn't
  fit the vision, with reasoning.
- **Overlap** — which `IMPLEMENTATION.md` rows it touches.
- **Recommendation** — Promote | Merge into M## | Park | Reject.
- **Rough scope** — patch / day / multi-day / multi-week.

Stop. Do not start implementation until the user confirms the
recommendation.
```

The full intake rules live in [`plans/README.md`](README.md) under *Intake
workflow for implementation requests from external sources*.

---

## Where to find current state

**Do not cache state in this file.** The source of truth is
[`plans/IMPLEMENTATION.md`](IMPLEMENTATION.md) — scan the table, find a
row with `Status: Ready` or `Status: Next up` and a blank `Claim`, then
run the trust-but-verify pass above before committing.

An earlier version of this file duplicated the table inline. That copy
went stale within 24 hours and contributed to a wasted session
(M03 looked unclaimed here but had already shipped). The table is
reviewed periodically — the `Last reviewed:` banner at the top of
`IMPLEMENTATION.md` tells you how fresh it is — but the authoritative
"is the work done" answer always lives in the code, not the table.

### Heuristic: which unfinished row to pick if none is assigned

These heuristics are process, not state. They should age better than
the table did:

- **Prefer "finishing" to "starting".** If there's an `In progress`
  milestone with one phase left, it's almost always higher-leverage
  than opening a new multi-week milestone. Check the milestone's plan
  doc — phases tagged `🔜 Next` are what's actually shippable.
- **After that, follow the VISION.md roadmap order.** The roadmap
  section in `IMPLEMENTATION.md` (starting "The vision's ordered
  roadmap is…") numbers the strategic order 1–8. Items earlier in
  the list are the ones that unblock later launches.
- **`Draft needed` rows need a plan first.** If you pick one, your
  first PR is the plan doc draft — not code. See how `plans/seedling-and-feed/plan.md`
  and `plans/the-forge/plan.md` were structured by earlier
  plan-drafting passes for the template.
- **`Rolling` rows are anyone-anytime.** M01 preserve-and-productise
  is the canonical example — chip at it whenever you have a spare
  slot and see dead code or stale docs.

---

## Why this file exists

Historical context: METIS has had ~20 agent sessions over the last month
working across the plan table. The highest-leverage unit of agent time is
the first 5 minutes — the gap between "agent starts" and "agent has found
the right row and read the plan." Without a paste-ready prompt, every
session rediscovers the conventions (branch naming, CI guards, intake
workflow) from scratch. This file collapses that discovery into a single
copy-paste.

Update it when the process changes, not when individual tasks change.
Task-level state lives in the milestone plan docs.
