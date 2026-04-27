# Heartbeat noise suppression — design

**Date:** 2026-04-26
**Milestone:** M13 (Seedling + Feed) — close-out polish
**Plan-doc reference:** `plans/seedling-and-feed/plan.md` *Next up* item 5
("Web UI new-user audit follow-up — heartbeat label").
**Branch:** `claude/m13-heartbeat-noise-suppress`
**Status:** Approved 2026-04-26.

## Problem

A new user opening METIS for the first time sees the companion dock's
thought log filled with `"Seedling heartbeat"` repeated up to 8 times.
The string is developer-jargon and the repetition is noise — the
audit finding flagged it as directly contradicting the milestone's
*"intelligence grown, not bought"* promise.

Root cause: the Seedling worker tick emits a `CompanionActivityEvent`
on every cycle (Phase 2's deliberately-no-op heartbeat). When a tick
has nothing meaningful to report, the event flows through with no
`summary`. The frontend bridge in `apps/metis-web/lib/api.ts:2791-2797`
backfills the missing field with the fallback string `"Seedling
heartbeat"`. The dock's thought log then renders all 8 of them.

The dock already considers these events noise — its sigil-pulse
animation at `metis-companion-dock.tsx:319` explicitly skips
`source === "seedling"`. The thought log just didn't get the memo.

## Solution

**Filter summary-less seedling events at the activity-bridge
boundary.** A `CompanionActivityEvent` with `source === "seedling"`
AND a missing-or-empty `summary` is dropped at
`apps/metis-web/lib/api.ts` before reaching `emitCompanionActivity`.
The filter site is the single emit point for seedling events, so all
downstream subscribers (dock thought log, unseen-count badge, future
listeners) inherit the rule for free.

The fallback string `"Seedling heartbeat"` at line 2796 becomes dead
code and is removed; the type contract becomes "events that flow
through MUST have a non-empty summary."

## Design choices considered and rejected

- **Rename the fallback label** (e.g. `"Companion checked the feed"`).
  Cosmetic only — the dock would still show 6 friendlier-but-still-
  noisy lines. The audit complaint had two axes (developer-y string
  AND visible × 6); renaming addresses one.
- **Filter at the dock subscriber.** Multiple components subscribe to
  `companionActivity`; pushing the filter into one subscriber means
  every other subscriber re-implements (or forgets) the rule.
  Filtering at the emit point is the one-place fix.
- **Default thought log to 1 line + "show recent" expansion.**
  Adds a UX surface a non-developer audience hasn't asked for.
  YAGNI — revisit if real users still find the log noisy after the
  noise filter lands.

## Edge cases checked

- **Empty-string summary (not undefined).** Treated identically to
  missing — empty strings are no more useful to a non-developer than
  the missing-field case.
- **Non-seedling summary-less events.** Pass through. Only
  `source === "seedling"` is filtered. M09 autonomous-research and
  M02 constellation events are unaffected.
- **Phase 5 stage-transition events.** Always carry a summary
  (`"Companion advanced to Sapling"` etc.), so the filter never
  drops them. Verified by reading the orchestrator's
  `record_seedling_activity` call in
  `metis_app/services/workspace_orchestrator.py`.
- **Unseen-count badge.** Dropping at the bridge means the badge only
  counts events that reached subscribers. That's the desired
  behaviour — no badge bumps from background ticks.

## Test changes

- `apps/metis-web/lib/__tests__/api.test.ts`:
  - Two existing cases assert the `"Seedling heartbeat"` fallback
    fires (lines 111, 133). Reframe them to assert summary-less
    seedling events are *dropped* at the bridge (no listener call).
  - Add a positive case: a seedling event with a real summary
    (e.g. `"Absorbed news comet: ..."`) still reaches subscribers.
  - Add a non-seedling summary-less case (e.g.
    `source: "autonomous_research"`) to confirm the filter is
    seedling-scoped.

No backend test changes — Python emitters are unchanged.

## Scope

One frontend bridge file change + one test file change. ~30 min.
Branch off `main` (Phase 5 already landed via PR #555). PR is
independent of the in-flight Phase 6 / Phase 7 PRs (#558 / #561) and
can land in any order.

## Closes

This is item 5 of *Next up* in `plans/seedling-and-feed/plan.md`. With
this fix landed and the in-flight #558 / #561 PRs merged, M13's
*Next up* list contains only data-gated retro work — the milestone
can flip to `Landed` in `plans/IMPLEMENTATION.md`.
