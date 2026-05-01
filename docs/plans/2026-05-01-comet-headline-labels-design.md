# Comet headline labels — design

**Date:** 2026-05-01
**Status:** Approved (brainstorm complete, ready for plan)
**Milestone:** M22 (to be added to [`plans/IMPLEMENTATION.md`](../../plans/IMPLEMENTATION.md))
**Vision pillar:** 🌌 Cosmos
**Depends on:** M13 (Seedling + Feed — Landed)
**Source:** Surfaced from the [`plans/IDEAS.md` → "chenglou/pretext"](../../plans/IDEAS.md) intake on 2026-05-01. The intake's brain-graph-3d migration was the wrong target (dormant code path); UI exploration found that **comets are the proper home** for pretext's line-breaking surface.

---

## Why

**The problem.** M13 ships a real news-comet pipeline — RSS / Hacker News / Reddit items are classified, scored, and streamed across the constellation as moving comets. The data is rich (`title`, `summary`, `url`, `source_channel`, `published_at`, `relevance_score`, `gap_score`, faculty classification) but **none of it is visible to the user**. Comets are pure particles today: a head, a glowing tail, a faculty-coloured fade. You can see something is being ingested, but you can't read what.

**What's missing.** A visual layer that surfaces the headline so the constellation tells you what your AI is consuming, in real time, peripherally.

**Why this is a pretext-shaped problem.** Pretext is already in the codebase (vendored at `@chenglou/pretext@0.0.5` since 2026-03-29) and powers constellation faculty labels via [`apps/metis-web/lib/pretext-labels.ts`](../../apps/metis-web/lib/pretext-labels.ts) — but only its *measurement* surface is exercised. Its line-breaking + grapheme-cluster handling has no consumer in the live UI. Comet labels are the natural fit: headlines are long, headlines wrap, and headlines from RSS feeds contain non-ASCII characters that need correct grapheme handling.

**Vision pillar.** 🌌 Cosmos. *"Stars are knowledge, not astronomy"* (principle #10) — comets are knowledge in motion. Currently they're decoration; this milestone makes them legible.

---

## What ships

Two new visual layers on top of the existing comet rendering loop:

1. **Ambient path-text label.** Truncated headline rendered along the comet's tail trail. Per-character placement and rotation follow the smoothed tangent of the trail. Always visible (in every phase except `absorbed`/`dismissed`).
2. **Pinned canvas hover card.** When the user hovers within 24px of a comet head, a canvas-rendered card draws beside it — full title (wrapped to ≤2 lines), summary (wrapped to ≤4 lines), faculty pill, source channel, age. Clicking the card or the comet head opens the article in a new tab.

Both consume `@chenglou/pretext` via the existing wrapper; the wrapper gets one new export — `wrapText(text, font, maxWidth)` — built on `prepareWithSegments` + `walkLineRanges`.

---

## Architecture

### File layout

| File | Action | Purpose |
|---|---|---|
| `apps/metis-web/lib/constellation-comet-labels.ts` | **New** | Pure rendering functions: `drawCometLabel(ctx, comet, ts, opts)` for the ambient path-text label, `drawCometHoverCard(ctx, comet, anchor, opts)` for the pinned card, plus a collision-suppression helper. Pretext-driven layout, opacity, truncation, orientation-flip, tangent damping for reduced-motion. |
| `apps/metis-web/lib/pretext-labels.ts` | **Edit** | Add `wrapText(text, font, maxWidth): Array<{text: string, width: number}>` — wraps a string to a max pixel width via `prepareWithSegments` + `walkLineRanges`, returns per-line text + width. Cached by `font::maxWidth::text` key. Falls back to a word-boundary heuristic when pretext throws. |
| `apps/metis-web/app/page.tsx` | **Edit** | After the existing `drawCometSprites(ctx, cometSprites, ts)` call (currently around line 4734), iterate the same comet list and call `drawCometLabel(ctx, c, ts, opts)`. Add a `cometHoverState` ref tracking nearest-hovered comet + cursor position. Augment existing mousemove handler to hit-test comet heads. Click handler on the canvas: if click is within 16px of a comet head OR within the hover card's bbox, `window.open(comet.url, "_blank", "noopener,noreferrer")`. |
| `apps/metis-web/lib/constellation-comets.ts` | **No edit** | `drawComets()` keeps its single responsibility (heads + tails). |
| `apps/metis-web/lib/constellation-comet-labels.test.ts` | **New** | Unit tests over the path-text math and collision logic. |
| `apps/metis-web/lib/pretext-labels.test.ts` | **New (or edit if exists)** | Unit tests for `wrapText`. |

### Data flow

```
M13 backend (news-comet engine)
    ↓ /v1/comets/active + /v1/comets/events SSE
app/page.tsx — cometSprites: CometData[]
    ↓ existing render loop
drawCometSprites(ctx, cometSprites, ts)        ← already shipped
drawCometLabel(ctx, comet, ts, opts) for each   ← NEW (ambient path-text)
collision-suppress + draw                       ← NEW
if hovered: drawCometHoverCard(ctx, hovered, anchor, opts)  ← NEW
```

`CometData` already carries everything we need (`title`, `summary`, `url`, `tailHistory`, `color`, `phase`, `opacity`, `relevanceScore`). No backend changes.

---

## Visual spec

### Ambient label

- **Font:** 11px Space Grotesk weight 400. Built via existing `buildCanvasFont(11, NODE_LABEL_FONT_FAMILY, 400)`.
- **Color:** faculty-tinted from `comet.color` RGB tuple. Opacity 0.65 baseline, multiplied by `comet.opacity`.
- **Layout:** characters placed along the **full visible tail** (not a middle-band). Position by arc length: walk `tailHistory` as a Catmull-Rom-smoothed spline; the i-th character's center is at arc length `Σ(advance widths)[0..i] + (start offset)` from the head.
- **Rotation:** per-character tangent from the smoothed spline, in radians. Pretext supplies per-character advance via segment cursors; the wrapper exposes them as a flat list. Smoothed via temporal low-pass (rolling 3-frame average of tangents) to suppress shimmer.
- **Orientation flip:** if dominant tangent (mean over the rendered span) is in [95°, 265°] off horizontal (with hysteresis bands of 90°/270° to avoid flicker), flip baseline by 180° so text always reads left-to-right from the user's POV. The flip is per-comet, smoothed across phase changes.
- **Truncation budget:** 18 chars + ellipsis hard maximum. If 18 chars don't fit the available arc length, truncate further to the prefix that fits. Pretext's cumulative segment widths drive this — *as the trail grows, more characters become renderable*. Headlines materialise.
- **No backdrop.** Text floats on the trail; the trail's own glow provides contrast. Adding a pill backdrop would clutter and hide the trail.
- **Reduced-motion.** Under `prefers-reduced-motion: reduce`, clamp per-character tangent deviation from horizontal to ±10°. Curve is felt; aggressive rotation is suppressed. The label still renders. (Comet motion itself can't be killed by reduced-motion without removing the comet.)

### Hover card

- **Trigger.** Hover within 24px of a comet head (Euclidean). Persists 600ms after mouseleave to allow cursor transit toward the card.
- **Position.** 16px to the right of the head, vertically centered on the head. If the resulting card bbox extends past `viewport.right - 16`, flip horizontally to 16px-left of the head. Same logic for top/bottom edges. Card never overlaps the existing fixed UI (zoom-pill, hero overlay, FAB) — those bbox-rect tests live in a small `clampToSafeArea(rect, viewport)` helper.
- **Backdrop.** Frosted-glass pill: `rgba(8, 10, 16, 0.78)` fill, `1px solid rgba(255, 255, 255, 0.12)` border, 12px corner radius. Matches the visual language of `makeTextSprite` in `brain-graph-3d.tsx`.
- **Width:** 220px fixed. Height: dynamic from wrapped content.
- **Padding:** 12px horizontal, 10px vertical.
- **Layout (top to bottom):**
  - Faculty pill, top-right corner inset 8px: 9px uppercase 3-letter code (`PER`, `KNW`, `MEM`, `RSN`, `SKL`, `STR`, `PRS`, `VAL`, `EMR`, `ATM`, `SYN`), faculty-coloured outline, transparent fill.
  - Title: 13px weight 600, faculty color, wrapped via pretext `wrapText(comet.title, font, 196)` to max 2 lines, ellipsis on overflow.
  - 4px gap.
  - Summary: 11px weight 400, `rgba(255,255,255,0.7)`, wrapped via pretext to max 4 lines, ellipsis on overflow. (`comet.summary`.)
  - 6px gap.
  - Footer: 10px `rgba(255,255,255,0.5)`, single line: `${comet.source_channel} · ${humanize_age(comet.published_at)}` like `"hackernews · 12m ago"`.
- **Click.** Click anywhere on the card or on the comet head → `window.open(comet.url, "_blank", "noopener,noreferrer")`.
- **Animation.** Fade in 180ms ease-out from `opacity: 0 + translateY(4px)`. Fade out 220ms ease-in.

### Collision suppression (ambient labels)

Multiple comets can be on screen simultaneously (`max_active` from the API). Strategy:

1. Sort `cometSprites` by `relevanceScore` descending.
2. For each comet in order, compute the rotated bounding box of its ambient label after path-layout.
3. AABB-test against each previously-drawn label's bounding box.
4. If overlap ratio > 40%, skip drawing the current label (the higher-scoring one wins).
5. Pretext's font-keyed cache makes per-frame measurement cheap; bbox computation is `O(label_count^2)` worst case, but `max_active` is small (typically 4–8).

Hover card is always drawn (one at most); never suppressed by collision.

---

## Interaction summary

| Surface | Trigger | Action |
|---|---|---|
| Ambient label | always (in active phases) | informational only — no interaction |
| Hover card | hover within 24px of comet head | render, persist 600ms after mouseleave |
| Click on comet head | click within 16px of head | `window.open(comet.url, _blank, noopener noreferrer)` |
| Click on hover card | click anywhere within card bbox | same as click on head |
| Settings: comets toggle | `cometsEnabled` (existing) | when off, both labels and hover card off |

No new settings. No new toggle. (Vision principle #4: skills over settings.)

---

## Network / privacy posture

- The hover card and labels render purely from data already arriving via `GET /v1/comets/active` and `GET /v1/comets/events` (M13 endpoints, already in M17's audit scope).
- Click → `window.open(url, "_blank")` is a browser-level outbound navigation initiated by the user. M17's `audited_urlopen` gates Python-side stdlib calls; this is browser nav, by definition explicit and not in M17's posture scope.
- No new outbound calls. No new endpoints. No new fonts loaded (Space Grotesk already in `app/layout.tsx`).

---

## Testing

### Unit (Vitest)

**`lib/constellation-comet-labels.test.ts`** (new):
- Path-text positioning: synthetic 5-point tail history forming a gentle arc, verify per-character positions and tangents.
- Truncation: short tail (arc length < label width), verify only fitting prefix is returned and ellipsis is appended.
- Orientation flip: tail going from top-right to bottom-left (dominant tangent ≈ 225°), verify flip is applied (baseline flipped, character order preserved in visual reading direction).
- Hysteresis: tangent oscillating around 90°, verify no flicker (flip threshold uses 95°/265°, not 90°/270°).
- Collision suppression: two labels with bboxes overlapping 50%, verify the lower-`relevanceScore` one is suppressed.
- Reduced-motion clamp: when `opts.reducedMotion === true`, verify max per-char tangent deviation from horizontal is ≤10°.

**`lib/pretext-labels.test.ts`** (new):
- `wrapText` honours max width: 200px max, long string, verify each returned line's width ≤200.
- Returns per-line widths (sanity).
- Caches by `font::maxWidth::text` key (call twice, verify pretext is called once via spy).
- Falls back to word-boundary heuristic when `prepareWithSegments` throws (mock the throw, assert the fallback shape).

### Live preview verification

- Open `/`, watch comets stream in over ~60s, observe ambient labels appearing along trails.
- Hover a comet, see card appear with title + summary + faculty + source.
- Click the card → article opens in a new tab.
- Click a comet head directly → same.
- Toggle `cometsEnabled` off → labels disappear.
- DevTools `prefers-reduced-motion: reduce` emulation → ambient label still renders, but rotation is gentle (≤10°).
- Confirm a comet crossing the lower-left → upper-right diagonal: orientation flip kicks in around 95°, no flicker.

---

## Risks

1. **Path-text math is subtle.** Catmull-Rom smoothing + per-char tangent + orientation flip + temporal smoothing is where bugs hide. **Tracer bullet first** — phase 1 ships a single comet with full path-text, no truncation/collision/flip, just verifies the spline math is right. Phase 2 adds the mitigations.
2. **Hover card collision with existing fixed UI.** The home page has a zoom-pill bottom-center, an "+ New Chat" FAB bottom-right, a "Discover everything" hero bottom-left, and a top-bar with logo + chat/settings. The card MUST clamp inside the safe area between these, not just the viewport. Phase 3 adds `clampToSafeArea` with the explicit list of fixed-UI rects.
3. **BiDi.** Pretext's `prepareWithSegments` returns BiDi-aware segment cursors. For mixed-script headlines (Arabic news in an RSS feed), per-character tangent assignment must follow visual order, not source order. **Phase 1 ships LTR-only.** Phase 4 adds BiDi if real-world feeds surface it. Filed as deferred risk in the plan's *Notes for the next agent*.
4. **`@chenglou/pretext` is at 0.0.5.** Already flagged in M01's pretext note. The new `wrapText` helper goes through the wrapper, so a future bump is one-file.
5. **Performance under high comet count.** Default `max_active` is small. If a future setting raises it to 20+, the per-frame `O(label_count²)` collision test starts to bite. Acceptable for now; revisit if `max_active` grows.

---

## Phase boundaries

This is a real multi-day milestone. Phases:

| Phase | Scope | Deliverable |
|---|---|---|
| **1 — Tracer bullet path-text** | One comet, full trail, no truncation/flip/collision. Pretext per-character measurement only. `wrapText` not yet exercised. | A comet's title rendered along its tail in `/`. Visual sanity check passes. |
| **2 — Mitigations** | Smoothed tangent (Catmull-Rom + temporal), orientation flip with hysteresis, truncation budget, reduced-motion clamp, faculty color tint. | Ambient labels look right under all comet trajectories and at all phases. |
| **3 — Hover card + click** | `wrapText` shipped in `pretext-labels.ts`, hover detection, card layout, `clampToSafeArea`, click handler, fade animations. | Full feature live in `/`. |
| **4 — Collision suppression + tests** | AABB collision suppression, Vitest tests for both files. | Tests green, multi-comet scenes don't overlap labels. |
| **5 — Polish + QA pass** | Live preview verification under all the verification scenarios above. PR. | M22 ready to merge. |

Each phase ends with a small PR (`feat(m22): Phase N — <summary>`) that's reviewable on its own. Phase 1 should land first as a separate PR before phase 2 starts (the spline math is the highest-risk piece — get it on `main` early so other work isn't blocked).

---

## Open questions deferred to implementation

- Faculty 3-letter codes (`PER`, `KNW`, etc.) — confirm the canonical short codes from M02 / M12 faculty taxonomy. Falls out of `NODE_COLOR_HEX` lookup.
- Exact `humanize_age` format — `12m ago` / `2h ago` / `3d ago`? Match whatever existing UI does for timestamps. Find the helper and reuse.
- Per-character spline sampling resolution — start at 4 samples per pixel of arc length and tune in phase 2.

---

## Notes for the next agent

- Wrapper-only convention: any new pretext-side work goes through `lib/pretext-labels.ts`. The `wrapText` addition is the second feature on the wrapper; keep the surface small.
- Pretext is at `0.0.5` — pre-1.0. If a 0.1.x or 1.0.0 lands during this milestone's lifetime, evaluate the upgrade in a *separate* PR to keep blame clean.
- BiDi is a known deferred risk. If you start finding mojibake or backwards-rendered headlines, that's why.
