---
Milestone: M22 — Comet headline labels
Status: Landed
Claim: Phases 1-3+5 landed via PR #589, #590, #592, #593; Phase 4 (collision suppression) deferred
Last updated: 2026-05-01 by claude/m22-phase-5-polish
Vision pillar: Cosmos
---

## Progress

- 2026-05-01 — Surfaced from the [`plans/IDEAS.md` → "chenglou/pretext"](../IDEAS.md) intake. UI-exploration brainstorm (preview tour + canvas-text census) found that pretext is already in the only place in METIS where it currently applies, and the proper new home for it is comet headline labels.
- 2026-05-01 — Brainstormed and approved design. Full spec at [`docs/plans/2026-05-01-comet-headline-labels-design.md`](../../docs/plans/2026-05-01-comet-headline-labels-design.md).
- 2026-05-01 — Implementation plan written. 5 phases of TDD-throughout work. Plan at [`docs/plans/2026-05-01-comet-headline-labels-implementation.md`](../../docs/plans/2026-05-01-comet-headline-labels-implementation.md).
- 2026-05-01 — Phase 1 claimed on `claude/m22-phase-1-tracer-pathtext`. Tracer-bullet path-text: single comet, full trail, raw per-character spline tangent, no truncation/flip/collision/reduced-motion. The simplest possible signal that the spline math is correct.
- 2026-05-01 — **Phase 1 landed via PR #589.** Includes two reviewer-driven fixes: head-position prepend (label was one frame behind rendered head) and grapheme-cluster iteration via `Intl.Segmenter` (so ZWJ emoji + combining marks render as one unit).
- 2026-05-01 — **Phase 2 landed via PR #590.** Smoothed per-char tangent (secant central-difference, equivalent to Catmull-Rom for tangent-only sampling), orientation flip with hysteresis, 18-grapheme + arc-length truncation, and reduced-motion ±10° clamp on the FINAL post-flip tangent (one reviewer fix: pre-fix code clamped pre-flip, producing upside-down glyphs under reduced-motion + flipped).
- 2026-05-01 — Phase 3 claimed on `claude/m22-phase-3-hover-card`. Hover hit-test, canvas hover card with title/summary/faculty/source/age, `clampToSafeArea`, click-to-open, and `wrapText` shipped in `lib/pretext-labels.ts` — first consumer of pretext's line-breaking surface in METIS.
- 2026-05-01 — **Phase 3 landed via PR #592** (with 9 Copilot review fixes, including a real footer age bug and a real title-overlaps-pill layout bug — both pinned by tests + reproduced before fixing).
- 2026-05-01 — **Phase 4 (collision suppression) deferred** per the design's perf-risk note: "Default `max_active` is small. If a future setting raises it to 20+, the per-frame O(label_count²) collision test starts to bite. Acceptable for now." Re-introducible if a real-world high-comet-count scene surfaces label overlaps.
- 2026-05-01 — **Phase 5 landed via PR #593.** Footer plumbing (`sourceChannel` + `publishedAt` through `CometData`, `formatCompactAge` restored with the `publishedAt=0` guard the Phase 3 review caught), 600ms hover-card persistence, M22 row flipped to `Landed`. M22 is complete.

## Retrospective

**What shipped:** A new visual layer atop M13's news comets — every comet now carries a path-text headline label that bends along its tail, with a canvas-rendered hover card showing the full title, summary, faculty pill, source channel, and age. Click opens the article in a new tab. First production consumer of `@chenglou/pretext`'s *line-breaking* surface in METIS (`wrapText` helper).

**What worked:**
- *Tracer-bullet phase ordering.* Phase 1 shipping rough-but-correct spline math first meant Phase 2's mitigations layered cleanly on a known-good base. Two reviewer-caught bugs in Phase 1 were exactly the kind of subtle math errors that would have been hidden under smoothing/flipping if combined.
- *TDD discipline throughout.* 72 unit tests on the lib (and one integration test on the wrapText cache freezing). Every reviewer-caught bug was repro'd as a failing test before fixing — the fixes pinned the regressions.
- *Pure-function helpers.* `computeArcLengths`, `samplePathAt`, `placeCharactersAlongPath`, `truncateLabelToFit`, `findHoveredComet`, `clampToSafeArea`, `formatCompactAge` are all pure and unit-tested independently of canvas. The canvas-rendering integration is thin.

**What didn't:**
- *Live preview verification was deferred every phase.* The local Metis API was offline for the entire M22 lifetime, so none of the design's *Live preview verification* scenarios could be ticked off in-browser. The unit suite covers the math; the visual look-and-feel of bending labels and hover cards remains unverified against a real comet feed. **First action when API is next running:** spend ~5 minutes on `/` watching comets stream and walking the design's verification checklist.
- *Plan vs reality drift.* The implementation plan I wrote called for Catmull-Rom-smoothed tangents (Phase 2.1); the secant central-difference I shipped is mathematically equivalent for tangent-only sampling on a polyline but saves ~30 LOC. The plan also called for temporal smoothing (Phase 2.2) which I dropped as YAGNI. Both divergences were called out in commit messages, but the plan doc itself wasn't updated. A plan that drifts from reality during execution is fine if the divergence is captured somewhere; the plan-of-record was never reconciled.

**Reviewer-caught bugs worth flagging:**
1. `tickComet` records pre-update `comet.x/y` to `tailHistory` before advancing, so the head was one frame behind the rendered position. Fixed in PR #589 follow-up.
2. `for (const ch of label)` iterates code points, not graphemes — split ZWJ emoji and base+combining sequences. Fixed via `Intl.Segmenter`. PR #589.
3. Reduced-motion ±10° clamp was applied to the *raw* tangent before the flip offset, so flipped labels under reduced-motion rendered upside-down. Fixed in PR #590 follow-up: clamp moved to act on the final post-flip orientation.
4. `formatCompactAge(0, Date.now())` returned ~20000d ago (1970 epoch delta), not "now". Footer placeholder rewritten in PR #592 follow-up; full `${source} · ${age}` footer with `publishedAt=0` guard shipped in Phase 5.
5. Title overlapped the faculty pill in the top-right at long-headline cases. Fixed via `CARD_TITLE_TOP_OFFSET` in PR #592 follow-up.

## Deferred items

- ~~**Phase 4 — Collision suppression.**~~ Shipped via [PR #(Phase 4 follow-up)](#) on 2026-05-01. `rotatedLabelBbox` + `suppressCollidingLabels` + prepare/suppress/draw pipeline; +12 unit tests. Highest-relevance comet wins when AABBs overlap >40%.
- ~~**Fixed-UI rect coverage.**~~ Shipped via the same PR. Hover-card safe-area now also avoids `.metis-home-fab-root`, `.metis-hero-overlay`, and a synthetic 64px top-viewport band (the page-chrome topbar doesn't have a single stable className — a fixed-band fallback is more robust than chasing chrome's class composition).
- **BiDi.** Phases 1-5 shipped LTR-only. **Still deferred.** Pretext's `prepareWithSegments` already returns BiDi-aware segment cursors, so `wrapText` (the one Phase 3 surface that uses pretext's full layout pipeline) handles mixed-script content correctly out of the box. The real risk lives in `placeCharactersAlongPath`'s per-character tangent assignment: it walks `Intl.Segmenter` graphemes in **source order**, not pretext's **visual order**. For a mixed-LTR/RTL headline, the character-to-tangent mapping would skew. Implementing this blind is risky — BiDi is one of the trickiest text-layout problems, has no observable acceptance criterion without a concrete failing case, and pretext's segment-cursor API would need wrapping (currently exposed only via private types in our wrapper). The design doc's *Risks* section explicitly framed this as "Phase 1 ships LTR-only. Phase 4 [now Phase 6] adds BiDi if real-world feeds surface it." Keep deferred. **First triggers to revisit:**
  1. Real RSS feed surfaces an Arabic / Hebrew / mixed-script headline and the path-text comes out garbled.
  2. The user explicitly waives the "if surfaced" gate.
  3. We land a BiDi-aware test fixture (e.g. an Arabic headline string + an expected per-char tangent assignment) that pins the failure mode.
- **Live preview QA.** API was offline for the entire M22 lifetime. Unit tests cover the math; visual look-and-feel of bending labels and hover cards remains unconfirmed against a real comet feed. **First action when API is next running:** spend ~5 min on `/` walking the design's *Live preview verification* checklist.

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
