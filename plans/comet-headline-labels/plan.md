---
Milestone: M22 — Comet headline labels
Status: In progress
Claim: claude/m22-phase-1-tracer-pathtext
Last updated: 2026-05-01 by claude/m22-phase-1-tracer-pathtext
Vision pillar: Cosmos
---

## Progress

- 2026-05-01 — Surfaced from the [`plans/IDEAS.md` → "chenglou/pretext"](../IDEAS.md) intake. UI-exploration brainstorm (preview tour + canvas-text census) found that pretext is already in the only place in METIS where it currently applies, and the proper new home for it is comet headline labels.
- 2026-05-01 — Brainstormed and approved design. Full spec at [`docs/plans/2026-05-01-comet-headline-labels-design.md`](../../docs/plans/2026-05-01-comet-headline-labels-design.md).
- 2026-05-01 — Implementation plan written. 5 phases of TDD-throughout work. Plan at [`docs/plans/2026-05-01-comet-headline-labels-implementation.md`](../../docs/plans/2026-05-01-comet-headline-labels-implementation.md).
- 2026-05-01 — Phase 1 claimed on `claude/m22-phase-1-tracer-pathtext`. Tracer-bullet path-text: single comet, full trail, raw per-character spline tangent, no truncation/flip/collision/reduced-motion. The simplest possible signal that the spline math is correct.

## Next up

1. Execute Phase 1 tasks 1.1–1.6 from the [implementation plan](../../docs/plans/2026-05-01-comet-headline-labels-implementation.md) using `superpowers:executing-plans`.
2. After Phase 1 PR lands on `main`, branch off main as `claude/m22-phase-2-mitigations` and start Phase 2.

## Blockers

None known. Phase 1 depends on a running comet feed for live verification — confirm `/v1/comets/active` returns data before claiming Phase 1 visually verified.

## Notes for the next agent

### Phase ordering is load-bearing

Phase 1 ships visibly-rough path-text on purpose — to prove the spline math is right *before* layering Catmull-Rom smoothing, orientation flip, truncation, and reduced-motion clamps on top of it. Resist combining phases 1 and 2 into a single PR. The rough Phase 1 is the simplest signal of "spline math correct."

### Pretext-side work goes through `lib/pretext-labels.ts`

The wrapper is the only sanctioned import surface for `@chenglou/pretext`. M22 adds one helper (`wrapText`) — keep it small. Don't add per-feature one-off pretext calls outside the wrapper; that's the failure mode the M01 convention rule is meant to prevent.

### Pretext is pinned at 0.0.5

Pre-1.0; breaking changes are normal. Risk flagged in M01's *Notes for the next agent*. If a 0.1.x or 1.0.0 release lands during M22's lifetime, evaluate the upgrade in a *separate* PR — don't fold it into a phase.

### BiDi is deferred

Phases 1–5 ship LTR-only path-text. If real-world RSS feeds surface backwards-rendered or mojibake headlines, file as a Phase 6 follow-up rather than retrofitting mid-milestone.

### Visual verification is eyeballed in the preview

Canvas snapshot testing is not in METIS today; M22 follows existing M02/M12 conventions and verifies look-and-feel via the live preview. The Vitest suite covers the spline math, layout helpers, and pure-function logic.

### Watch for collision with the live UI

Phase 3's `clampToSafeArea` must avoid the zoom-pill, hero overlay, "+ New Chat" FAB, and top-bar. These are existing fixed-position elements on `/`; the helper looks them up by stable className once per frame. If M01's UI work changes any of those classnames during M22's lifetime, this is the integration point to update.
