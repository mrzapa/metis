# plans/ — How work moves through METIS

This folder is the **operational layer** of the METIS vision. If `VISION.md` is
*what* we're building and `docs/adr/` is *why* we're building it a certain way,
`plans/` is *what's happening right now* and *what any agent should pick up next*.

## The three files that matter

| File | Purpose | Who writes it |
|---|---|---|
| [`IMPLEMENTATION.md`](IMPLEMENTATION.md) | Master index. One row per milestone from `VISION.md`. Status, current plan doc, next action, claim. | Any agent updating progress. |
| [`IDEAS.md`](IDEAS.md) | Inbox. Drop raw ideas here. Never touched by implementation agents unless promoted. | User, primarily. Agents only append under *Agent observations*. |
| Individual `plans/<milestone>/plan.md` or `docs/plans/<date>-<topic>.md` | The actual work doc for a milestone. | Whoever claims the milestone. |

## How an agent picks up work (60-second orient)

1. **Read `VISION.md`.** Understand the product.
2. **Open `plans/IMPLEMENTATION.md`.** Find a row where `Status` is `Next up`
   or `In progress` and `Claim` is empty or stale.
3. **Claim it.** Edit the row: set `Claim` to your session ID / branch name
   and `Last updated` to today's date.
4. **Open the linked plan doc.** Read its *Progress* and *Next up* sections.
5. **Do the work.** Small commits, clear messages.
6. **Before you stop** (even mid-session): update the plan doc's *Progress*
   and *Next up* sections so the next agent can continue without guessing.
7. **When the milestone is done:** flip `Status` to `Landed` in
   `IMPLEMENTATION.md` and add a one-line summary with the merge commit SHA.

## Plan-doc frontmatter (standard)

Every milestone plan doc starts with this block. Agents **must** keep it current.

```markdown
---
Milestone: <name from IMPLEMENTATION.md>
Status: Draft | Ready | In progress | Rolling | Blocked | Landed | Superseded
Claim: <session id / branch / agent name, or "unclaimed">
Last updated: YYYY-MM-DD by <who>
Vision pillar: Cosmos | Companion | Cortex | Cross-cutting
---

## Progress
<Bullet list of what's already been done. Append-only; don't rewrite history.>

## Next up
<The next 1–3 concrete actions. Whoever claims this does these first.>

## Blockers
<Anything stopping progress. Empty if unblocked.>

## Notes for the next agent
<Free-form. Surprises, gotchas, half-finished threads, "I tried X and it didn't work".>
```

## Parallel work rules

Multiple agents can work simultaneously on METIS **if** they pick different
rows in `IMPLEMENTATION.md` and each claims its row. Rules:

- **One claim per milestone.** If `Claim` is non-empty and `Last updated` is
  within 7 days, leave it alone and pick a different row.
- **Touch different files.** Use the *Scope* column to spot overlap. Two
  agents editing `apps/metis-web/app/page.tsx` at the same time is asking
  for pain — coordinate or pick different milestones.
- **Update `Last updated` every time you make a commit for that milestone.**
  A stale claim (>7 days untouched) is assumed abandoned and may be
  reclaimed.
- **Don't cross the streams.** If milestone A depends on milestone B,
  `IMPLEMENTATION.md`'s *Depends on* column says so — wait for B to reach
  `Landed` or coordinate explicitly.

## Adding ideas (the user inbox)

When the user sees something they want in METIS — a paper, a technique, a
UI idea, a wishlist item — it goes in [`IDEAS.md`](IDEAS.md), not into any
active plan doc. That keeps work-in-flight from being disturbed.

Periodically (after a milestone lands is a good trigger) run a **triage
pass**: walk `IDEAS.md` top-to-bottom and either:

- **Promote** — an idea becomes a new row in `IMPLEMENTATION.md` with a plan
  doc stub.
- **Reject** — doesn't fit the vision; strike through with a one-line
  reason.
- **Park** — move to an *Iced* section at the bottom of `IDEAS.md`.
- **Merge** — fold into an existing plan's *Notes for the next agent*.

Leave the rest in the inbox for next time.

## Why this structure

- **Agents can join cold.** Every plan has a fixed frontmatter that tells
  them what's done and what's next. No archaeology required.
- **User never has to gate-keep.** Drop ideas in `IDEAS.md` at any time
  without interrupting active work.
- **Multiple agents can parallelise.** Claim column + scope column prevent
  collisions.
- **Nothing is lost.** Superseded plans stay on disk with `Status:
  Superseded` and a pointer to what replaced them.
