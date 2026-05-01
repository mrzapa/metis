# Edge-pulse visual — design

**Date:** 2026-04-26
**Milestone:** M13 (Seedling + Feed) — close-out polish
**Plan-doc reference:** `plans/seedling-and-feed/plan.md` *Phase 6
follow-up — edge-pulse visual* (deferred from PR #558).
**Branch:** `claude/m13-edge-pulse-visual`
**Status:** Approved 2026-04-26. **Frontend portion superseded
2026-05-01** — the `brain-graph-3d.tsx` surface this design
targeted was never mounted on a route in v1, and was reaped
under M01 §4.9. The backend portion (steps 1-3 below: the
`brain_link_created` event flowing through `CompanionActivityEvent`
to the live companion dock) shipped and is live; only the
3D-canvas pulse visualisation in step 4 never reached users.

## Problem

When the Seedling produces a new `AssistantBrainLink` record (during
either while-you-work or overnight reflection), the brain-graph view
silently absorbs the new edge on the next graph refresh. There is no
*moment* — no visible cue that the companion just learned something.
Phase 6 shipped the structural densification (Elder gate on
`compute_assistant_density`), but the felt sensation of "the
companion is growing" requires a brief animation.

## Solution

**Backend emits a CompanionActivityEvent per reflection that wrote
new brain links; frontend brain-graph-3d.tsx subscribes and pulses
the matching edges with a brief GSAP tween.**

Architecture:

1. `metis_app/seedling/activity.py` extends `_VALID_KINDS` with
   `"brain_link_created"` so the bridge propagates the new event
   type through the existing `/v1/seedling/status` polling surface.
2. `metis_app/services/assistant_companion.py` — both `reflect()`
   and `record_external_reflection` call `add_brain_links()` and
   then emit ONE `record_seedling_activity` event with
   `kind: "brain_link_created"` and a payload listing the new links
   (`source_node_id`, `target_node_id`, `relation`). One event per
   reflection (not per link) keeps the bridge buffer healthy when a
   reflection emits 2-4 links.
3. `apps/metis-web/lib/api.ts` extends the `CompanionActivityEvent`
   `kind` union with `"brain_link_created"` (additive type
   extension, mirrors Phase 4a/5).
4. `apps/metis-web/components/brain/brain-graph-3d.tsx` subscribes
   to events with `kind === "brain_link_created"`. For each link in
   the payload:
   - Find the THREE.js edge object by `(source_node_id, target_node_id, relation)`.
   - Run a GSAP tween on the edge's material — brightness +
     line-width pulse, ~600ms ease-out — matching the existing
     `bloomPassRef` tween vocabulary at line 538.
   - Stagger across multiple links in the same event with 80ms
     spacing so a 4-link reflection looks like a wave, not a flash.
   - Honor `prefers-reduced-motion`: skip the tween entirely (no
     fallback flash — the brain graph is too noisy a primary
     surface to insist on a visual cue against the user's setting).

## Design choices considered and rejected

- **One activity event per link** (instead of per reflection).
  Rejected: a reflection that emits 4 brain links would burst
  4 events through the bridge buffer (cap = 20), pushing earlier
  events out. One-per-reflection-with-list is cleaner.
- **Frontend infers brain-link creation by polling
  `/v1/assistant/snapshot` and diffing.** Rejected: fragile
  (race conditions on poll interval), ties the visual to a fixed
  cadence, can't represent "the link was created at time T".
- **Particle-along-edge animation** (more elaborate than a colour
  pulse). Rejected for now — the existing graph already uses
  directional particles for RAG activity (`activityProfile`), so
  re-using that vocabulary would conflate two semantically distinct
  activity types. A material-brightness + width pulse is visually
  distinct from particle flow.
- **Pulse on `add_brain_links()` regardless of source.**
  Rejected: the bridge surface is for *companion-driven* events.
  Manual edits or test fixtures shouldn't fire UI animations.

## Edge cases checked

- **Edge not in current graph render** (e.g. graph refresh in
  flight). Drop silently — the next graph refresh will include the
  edge but without the pulse. Acceptable; the event is best-effort
  visual feedback, not a correctness signal.
- **Burst from a reflection emitting 4 links.** Stagger 80ms.
- **Reduced motion.** Skip tween entirely. Test for this.
- **Brain link payload references nodes the graph hasn't loaded
  yet.** Drop silently (existence guard at edge-lookup time).
- **`record_seedling_activity` raises.** Already wrapped in
  try/except in the orchestrator (Phase 5 pattern). Reflection
  itself never demotes on activity-emit failure.

## Tests

- `tests/test_seedling_activity.py` — new test verifying
  `_VALID_KINDS` includes `"brain_link_created"` and that an event
  with that kind survives the bridge filter.
- `tests/test_assistant_companion.py` — extend the existing
  reflect-emits-event tests with an assertion that one
  `kind: "brain_link_created"` event is recorded per `reflect()`
  call that wrote brain links.
- `apps/metis-web/components/brain/__tests__/brain-graph-3d.test.tsx`
  (or a sibling test file) — verify the subscriber wires up the
  GSAP tween for `kind: "brain_link_created"` events. Reduced-motion
  branch tested via mock `matchMedia`.

## Scope

Backend ~30 min (activity allow-list + emitter in two reflect
paths + 1 backend test). Frontend type extension + subscriber +
GSAP tween ~60-90 min (the brain-graph component is large but the
new code is local to one effect block). Plan-doc update + PR
~10 min. Total ~2 hr.

## Closes

This is the deferred Phase 6 follow-up. With this landed, the
plan-doc *Next up* contains only data-gated retro work and the
admin close-out (flip M13 row to `Landed` + write retro). After
this PR merges, M13 is fully done.
