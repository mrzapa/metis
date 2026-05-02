# Quiet loaders — design

**Date:** 2026-05-02
**Status:** Approved (brainstorm complete, ready for plan)
**Milestone:** M01 (rolling — *preserve and productise*); will appear under *Notes for the next agent → Quiet loader pass* in [`docs/preserve-and-productize-plan.md`](../preserve-and-productize-plan.md).
**Vision pillar:** 🔧 Cross-cutting (with 🌱 Companion adjacency at the agent-themed loaders)
**Depends on:** M20 (Metis logo rollout — Ready/landed). The new primitive sits next to `<MetisLoader>` in `components/brand/`; it depends on the M20 brand-primitive convention existing.
**Source:** Surfaced from the [`plans/IDEAS.md` → "dot/matrix loaders + DAB pixel/braille editor"](../../plans/IDEAS.md) intake on 2026-05-02. Brainstormed same day under `superpowers:brainstorming`.

---

## Why

**The problem.** Loader/spinner usage in `apps/metis-web` is split across three vocabularies today, with no semantic discipline:

1. **Brand-forward `<MetisLoader>`** (M20, shipped) — mark + sonar ripple. Used at whole-surface moments: `DesktopReadyGuard`, `SetupGuard` splash, companion-dock cold start. Brand decision; not in scope to displace.
2. **Generic `Loader2 + animate-spin`** (lucide-react) — the default everywhere else. ~28 files. Semantically empty: every state collapses to "something is happening," whether the agent is thinking, the chat is streaming, the Forge is promoting a skill, or the page is mounting.
3. **One outlier** at [`apps/metis-web/app/loading.tsx`](../../apps/metis-web/app/loading.tsx) — a hand-rolled cyan ring spinner. Neither brand nor lucide; an accident.

**The gap.** Inline contexts where the brand mark is too heavy and lucide's spin is too generic. Specifically: chat thinking-state, chat token streaming, Forge technique-card pending, companion-dock action busy states. These are the surfaces where the user perceives "the agent is doing X" — and today they all read identically as "spin spin spin."

**Why dot-matrix is the right vocabulary.** A 5×5 dot grid driven by a single `@keyframes` rule + per-dot `animation-delay` map — the technique pioneered by [dot/matrix](https://icons.icantcode.fyi/) — produces semantically distinct loaders at ~20 px size for ~4 KB of code per loader. The dot aesthetic also threads back to METIS's M-mark (M20), so the vocabulary is brand-coherent without re-using brand-forward primitives.

**Vision pillar.** 🔧 Cross-cutting under principle #2 ("beauty is a feature"). The agent-flavoured subset (`thinking`, `stream`) reinforces 🌱 Companion by making the persistent local AI's mental states visibly distinct rather than collapsed into a generic spinner.

---

## What ships

A new sibling family next to the M20 brand primitives:

1. **`<DotMatrixLoader name="…" />`** — a dispatcher React component at `apps/metis-web/components/brand/dot-matrix-loader.tsx`.
2. **Six sub-components** at `apps/metis-web/components/brand/dot-matrix/{thinking,stream,compile,verify,halt,breath}.tsx` — each a 5×5 SVG grid with a keyframe class.
3. **One stylesheet** at `apps/metis-web/components/brand/dot-matrix/keyframes.css` — six `@keyframes` rules, imported once in `app/layout.tsx`.
4. **Six surface migrations** (chat thinking-bubble, chat send-button, Forge technique-card pending, companion-dock reflect-now, companion-dock atlas-save, `app/loading.tsx`).
5. **Documentation:** new `dot-matrix/README.md` with vocabulary table + attribution; existing `components/brand/README.md` extended with the divide-paragraph and decision-tree row.
6. **Tests:** vitest contract tests, one per sub-component plus a dispatcher test (mirrors the M20 brand-test pattern).

**Out of scope (parked):** light-mode loaders, animated PNG/Lottie export, visual regression testing (no Playwright in repo), reduced-motion media-query gate (deliberately dropped per project owner), DAB integration as a runtime tool, migrating the rest of the `Loader2` spinners (most stay).

---

## Architecture

### File layout

| File | Action | Purpose |
|---|---|---|
| `apps/metis-web/components/brand/dot-matrix-loader.tsx` | **New** | Dispatcher. Switches on `name`, renders the chosen sub-component, derives default `aria-label` from `name`. ~40 lines. |
| `apps/metis-web/components/brand/dot-matrix/thinking.tsx` | **New** | Inner-cluster firing pattern. ~25 lines. |
| `apps/metis-web/components/brand/dot-matrix/stream.tsx` | **New** | Row-major emission. ~25 lines. |
| `apps/metis-web/components/brand/dot-matrix/compile.tsx` | **New** | Bottom-up column fill. ~25 lines. |
| `apps/metis-web/components/brand/dot-matrix/verify.tsx` | **New** | One-shot checkmark trace. ~25 lines. |
| `apps/metis-web/components/brand/dot-matrix/halt.tsx` | **New** | One-shot 3×3 collapse to centre. ~25 lines. |
| `apps/metis-web/components/brand/dot-matrix/breath.tsx` | **New** | Whole-grid breathing pulse. ~25 lines. |
| `apps/metis-web/components/brand/dot-matrix/keyframes.css` | **New** | Six `@keyframes` blocks, scoped by class names like `.dm-thinking`, `.dm-stream`, etc. ~80 lines total. |
| `apps/metis-web/components/brand/dot-matrix/README.md` | **New** | Vocabulary table, API snippet, "adding a new loader" workflow, attribution block. |
| `apps/metis-web/components/brand/index.ts` | **Edit** | Re-export `DotMatrixLoader` and `DotMatrixLoaderName`. |
| `apps/metis-web/components/brand/README.md` | **Edit** | Add divide-paragraph + decision-tree row pointing at `dot-matrix/README.md`. |
| `apps/metis-web/app/layout.tsx` | **Edit** | Import `dot-matrix/keyframes.css` once (next to `globals.css` import). |
| **Six surface files** (chat-panel, technique-card, metis-companion-dock, app/loading.tsx) | **Edit** | Replace specific `Loader2` / cyan-ring usages — see [Consumer migration plan](#consumer-migration-plan). |
| `apps/metis-web/components/brand/__tests__/dot-matrix-loader.test.tsx` | **New** | Vitest contract tests: dispatcher routing + per-loader render assertions. |

### API

```tsx
// In dot-matrix-loader.tsx (re-exported from components/brand/index.ts)
export type DotMatrixLoaderName =
  | "thinking"   // agent composing
  | "stream"     // tokens emitting
  | "compile"    // multi-step process
  | "verify"     // success, one-shot
  | "halt"       // error/cancel, one-shot
  | "breath";    // idle "alive"

export interface DotMatrixLoaderProps {
  /** Required — every consumer picks semantically. */
  name: DotMatrixLoaderName;
  /** Square size in px. Default 20 (sized for inline use). */
  size?: number;
  /** Override aria-label. Default derives from `name`. */
  "aria-label"?: string;
  className?: string;
}
```

### Theming

All dots use `fill="currentColor"`. Tinting cascades from any parent that sets `color`. No new design tokens. Same convention as `<MetisMark>` from M20.

### Why this folder layout

The loader family lives inside `components/brand/` rather than a sibling `components/loaders/` for two reasons. First, it preserves a single-folder mental model — readers find every dot-aesthetic primitive in one place. Second, the existing `components/brand/README.md` already contains the "Pick the right primitive" decision tree; extending that table is one paragraph of doc edit, whereas a sibling folder forks the discoverability surface. The trade-off: `<MetisLoader>` (brand-forward) and `<DotMatrixLoader>` (inline-semantic) coexist in the same folder, and the README must teach the divide. One paragraph is enough; the README change is part of this design.

---

## Loader vocabulary

Each entry: choreography description (used to author the keyframe + delay map), and final-frame for one-shots. All loaders use a 5×5 grid with cells indexed `(row, col)` where `(0, 0)` is top-left and `(4, 4)` is bottom-right.

### 1. `thinking` — agent composing / reflecting

**Inspired by** [icon-19 *Thinking*](https://icons.icantcode.fyi/icon/icon-19) (used with permission).

**Choreography.** Outer ring (16 cells) stays at 15% opacity throughout. Inner 3×3 cluster (9 cells: `(1,1)` … `(3,3)`) fires independently:

- Each inner cell fades 0% → 100% → 0% over 400 ms.
- Per-cell delays (ms): `(1,1):0`, `(1,2):200`, `(1,3):400`, `(2,1):600`, `(2,2):100`, `(2,3):300`, `(3,1):500`, `(3,2):700`, `(3,3):50`.
- Cycle: 1200 ms, infinite.

Reads as "neurons firing, agent has presence."

### 2. `stream` — tokens emitting

**Inspired by** [icon-20 *Stream*](https://icons.icantcode.fyi/icon/icon-20).

**Choreography.** Dots light in row-major order (top-left → bottom-right):

- Each dot fades-in 0% → 100% over 60 ms, holds at 100% for 100 ms, fades-out 100% → 0% over 200 ms.
- Stagger: 60 ms per dot.
- Cycle: 25 × 60 ms = 1500 ms; last dot's fade overlaps the next cycle's start.

Reads as "tokens marching out in reading order."

### 3. `compile` — multi-step process running

**Inspired by** [icon-28 *Compile*](https://icons.icantcode.fyi/icon/icon-28).

**Choreography.** Five columns fill bottom-up, then release as one:

- Each column fills its 5 dots over 600 ms (120 ms per dot, bottom row first).
- Inter-column stagger: 800 ms (col-1 starts at 0 ms, col-5 starts at 3200 ms).
- After col-5 completes (3800 ms), all 25 dots hold at 100% for 200 ms, then all fade together over 600 ms.
- Cycle: 4600 ms, infinite.

Reads as "filling, filling, then snap-released."

### 4. `verify` — success (one-shot)

**Inspired by** [icon-38 *Verify*](https://icons.icantcode.fyi/icon/icon-38).

**Choreography.** Six cells trace a checkmark in time order:

- Cell sequence: `(3,0)` → `(4,1)` → `(3,2)` → `(2,3)` → `(1,4)`. Short stroke down-right `(3,0)→(4,1)`, then long stroke up-right `(4,1)→(1,4)`.
- Each cell ignites over 100 ms, then holds at 100% for the rest of the animation.
- Stagger: 180 ms per cell.
- Total: ~1080 ms ignite + 800 ms hold = 1880 ms one-shot.
- `animation-iteration-count: 1; animation-fill-mode: forwards` — final frame stays.

**Final frame.** Six checkmark cells at 100%, all others at 0%.

Re-running requires a `key=` change at the call site (standard React idiom for restarting CSS animations).

### 5. `halt` — error / cancel (one-shot)

**Inspired by** [icon-39 *Halt*](https://icons.icantcode.fyi/icon/icon-39).

**Choreography.** Inner 3×3 collapses to centre:

- t=0 ms: inner 3×3 (cells `(1,1)` … `(3,3)`) all at 100%.
- t=400 ms → t=700 ms: eight outer cells of the 3×3 (the ring around the centre) fade to 0%.
- t=800 ms+: only `(2,2)` (centre dot) remains at 100%, holds.
- Total: 800 ms one-shot, fill-mode forwards.

**Final frame.** Centre dot at 100%, all others at 0%.

### 6. `breath` — idle "alive"

**Inspired by** [icon-15 *Breath*](https://icons.icantcode.fyi/icon/icon-15).

**Choreography.** All 25 dots animate together: opacity 30% → 100% → 30% over 3000 ms with `ease-in-out`. Continuous loop.

Reads as "the surface is alive but quiet."

---

## Consumer migration plan

Six surface migrations in the M01 patch. Every swap maps to one of the six loaders, picked from real audit hits.

| # | File | Line (today) | Today | After |
|---|---|---|---|---|
| 1 | `apps/metis-web/components/chat/chat-panel.tsx` | 909 | `Loader2 spin size-3.5` inside glass micro-surface (chat thinking bubble) | `<DotMatrixLoader name="thinking" size={14} />` |
| 2 | `apps/metis-web/components/chat/chat-panel.tsx` | 1084 | `Loader2 spin size-4` on send button while pending | `<DotMatrixLoader name="stream" size={16} />` |
| 3 | `apps/metis-web/components/forge/technique-card.tsx` | 380 | `Loader2 spin size-3` on technique-card pending chip | `<DotMatrixLoader name="compile" size={12} />` |
| 4 | `apps/metis-web/components/shell/metis-companion-dock.tsx` | 1063 | `Loader2 spin size-4` on reflect-now busy state | `<DotMatrixLoader name="thinking" size={16} />` |
| 5 | `apps/metis-web/components/shell/metis-companion-dock.tsx` | 779 | `Loader2 spin size-3.5` on atlas save busy state | `<DotMatrixLoader name="compile" size={14} />` |
| 6 | `apps/metis-web/app/loading.tsx` | 9–12 | Hand-rolled cyan ring spinner (M01 outlier) | `<DotMatrixLoader name="breath" size={48} />` wrapped in the existing `flex flex-col` container |

### Deliberately not migrated (kept as `Loader2`)

- Chat session-loading spinner (`chat-panel.tsx:743`) — generic "loading session" doesn't have a clean semantic role. Future pass.
- "Loading older messages" pagination spinner (`chat-panel.tsx:736`) — pagination is the canonical "indeterminate" use case.
- Forge `installed-skills-pane`, `candidate-skills-pane`, `proposal-review-pane` `Loader2`s — list-load indeterminate.
- Companion dock pause/play toggle (`companion-dock.tsx:1046`) — micro-action.
- Other route-level `loading.tsx` files (`forge`, `chat`, `settings`, `gguf`, `diagnostics`) — keep `Loader2`.

### `verify` and `halt` are unconsumed in this patch

Both ship in this patch but have no consumer. Their natural homes are future surfaces that surface success/error transitions visibly:

- `verify` → "Skill promoted ✓" toast, eval-pass card.
- `halt` → "Promote failed" toast, eval-fail card.

The Forge today does not have transient success/error toasts — promote success refreshes the card; error logs to a status pill. We ship the loaders and document them as "available for adoption" rather than wait for consumers.

---

## Documentation surfaces

### `apps/metis-web/components/brand/dot-matrix/README.md` (new)

Sections:

1. **Purpose.** "Inline semantic loaders, sibling to `<MetisLoader>`. Use these for in-text agent / progress / status states the brand mark would be too heavy for."
2. **Vocabulary table.** Six rows: slug · semantic role · choreography one-liner · current consumer or "available."
3. **API snippet.** `<DotMatrixLoader name="thinking" size={20} />` plus the type union.
4. **Theming.** `currentColor` cascades from parent; matches `<MetisMark>`.
5. **Adding a new loader.** Workflow: design frames (DAB optional), author keyframe + delay map by hand, add sub-component file, extend `DotMatrixLoaderName` union, add row to vocabulary table.
6. **Attribution block** (see below).

### `apps/metis-web/components/brand/README.md` (extend)

Two changes to the existing file:

1. **Decision-tree row.** Add to the "Pick the right primitive" subsection:
   > Inline semantic state (chat thinking, technique-card compile, etc.) → `<DotMatrixLoader name="…">`. See `dot-matrix/README.md`.

2. **Divide paragraph.** Add to the section that introduces `<MetisLoader>`:
   > `<MetisLoader>` is brand-forward — mark + sonar — for whole-surface loading. `<DotMatrixLoader>` is inline-semantic — dot grid + keyframe — for in-text states the brand mark would be too heavy for. Both are `currentColor`-themed; pick by surface size and whether the user should perceive *"the brand is here"* or *"this specific operation is in flight."*

### `plans/IDEAS.md` (update)

The dot/matrix entry's *Decision* line moves from "*awaiting go/no-go*" to:

> **Brainstormed 2026-05-02; merged into M01.** Design at [`docs/plans/2026-05-02-quiet-loaders-design.md`](../docs/plans/2026-05-02-quiet-loaders-design.md); implementation plan at [`docs/plans/2026-05-02-quiet-loaders-implementation.md`](../docs/plans/2026-05-02-quiet-loaders-implementation.md). Six-loader vocabulary (`thinking`, `stream`, `compile`, `verify`, `halt`, `breath`) ships as `<DotMatrixLoader>` next to M20's `<MetisLoader>`. DAB rejected as a runtime integration target; reference-only. Upstream permission obtained for the dot-matrix technique.

### `docs/preserve-and-productize-plan.md` (update)

Append under *Notes for the next agent*:

> **Quiet loader pass (2026-05-02).** Six-loader vocabulary at `components/brand/dot-matrix/*`, dispatcher at `components/brand/dot-matrix-loader.tsx`. Six surfaces migrated (chat thinking-bubble, chat send-button, Forge technique-card pending, companion-dock reflect-now, companion-dock atlas-save, `app/loading.tsx` cyan-ring outlier). Other inline `Loader2` usage left as-is by design — only semantic surfaces migrate. Design: `docs/plans/2026-05-02-quiet-loaders-design.md`. Plan: `plans/quiet-loaders/plan.md`.

---

## Attribution

The user has explicit permission from `icantcodefyi/dot-matrix-animations` (the upstream dot/matrix repo) to use the technique in METIS. Recorded in two places:

### `dot-matrix/README.md` Attribution block

> The dot-matrix loader vocabulary is inspired by [dot/matrix](https://icons.icantcode.fyi/) by [@icantcodefyi](https://github.com/icantcodefyi). The 5×5-grid + single-keyframe + per-dot-delay-map technique originated there. The six choreographies in this folder are original work designed to fit METIS's specific semantic roles (`thinking`, `stream`, `compile`, `verify`, `halt`, `breath`); they are not vendored from the dot/matrix repo. Permission to use the technique was granted by the author.

### Header comment in `dot-matrix-loader.tsx`

```tsx
/**
 * Dot-matrix inline semantic loaders.
 *
 * 5×5 grid · single CSS @keyframes · per-dot animation-delay map.
 * Technique inspired by https://icons.icantcode.fyi/ (used with permission).
 * See `./dot-matrix/README.md` for the full vocabulary and authorship notes.
 */
```

---

## Implementation phases (high level)

The detailed plan is at [`docs/plans/2026-05-02-quiet-loaders-implementation.md`](2026-05-02-quiet-loaders-implementation.md) (generated from this design via `superpowers:writing-plans`). Phase summary:

1. **Phase 1 — Primitive scaffold.** Create the dispatcher, the six sub-components (with hand-authored keyframes + delay maps), the keyframes CSS, and the vitest contract tests. Wire the keyframes import into `app/layout.tsx`. Update `components/brand/index.ts` to re-export. Test: `pnpm test components/brand`.

2. **Phase 2 — Surface migrations.** Six edits to four files, one PR-sized batch. Test: visual spot-check at each surface (manual; screenshots in PR description).

3. **Phase 3 — Documentation.** Author `dot-matrix/README.md`. Edit `components/brand/README.md` (decision-tree row + divide paragraph). Update `plans/IDEAS.md` Decision line. Update `docs/preserve-and-productize-plan.md` Notes for the next agent.

4. **Phase 4 — Tuning.** Real-app spot-check across the six surfaces. If any choreography reads as wrong (`compile` too slow, `thinking` too twitchy, etc.), tune the keyframe timings in a follow-up commit. Single-author choreography risk is real; first PR may need an iteration.

Aggregate scope: **~2 days** across phases 1–3, with phase 4 deferred to feedback.

---

## Risks and honest tradeoffs

- **Single-author choreography risk.** Six animations are authored on instinct. If any reads off in real use (`compile` static-feeling, `thinking` twitchy, `stream` too fast / too slow), tuning is the keyframe timings — a follow-up commit. The design is hard to evaluate as a still-image spec; first PR should expect a tuning round.
- **`<DotMatrixLoader>` vs. `<MetisLoader>` confusion.** Mitigated by the brand README divide-paragraph. If consumer confusion appears in PR review, escalate by adding a one-paragraph header comment to each file restating the divide.
- **Bundle weight.** Six SVG components + one CSS file with six keyframes ≈ 4 KB raw / ~2 KB gzipped. Smaller than a single lucide icon's tree-shake hit. Not a concern.
- **Reduced-motion deliberately not gated.** Loaders are tiny inline animations — much less aggressive than the constellation-scale motion that M21 Phase 5 just removed. If accessibility regressions are reported, revisit; not pre-emptive.
- **Two unconsumed loaders (`verify`, `halt`).** Both ship without a live consumer. The marginal cost is two ~25-line files plus two keyframes. The marginal benefit is that a future consumer (skill-promote toast, eval-pass card) can adopt them in a single-line change rather than a re-design. Net: cheap insurance.
- **Pre-1.0 upstream divergence.** dot/matrix's gallery is at v0.2 and growing (28 → 60 loaders in a week). Our six are authored, not vendored — we own them. No upgrade churn. If a future loader is needed and dot/matrix has a great example, we can author our own version of it under the same permission grant.

---

## Out of scope (parked for follow-up)

- **Light-mode loaders.** METIS is dark-only today; `currentColor` cascade will Just Work in light mode the day light mode arrives. No extra work needed.
- **Lottie / animated PNG export.** Surfaces we can't render React on (Discord embeds, GitHub README inline images) don't need a loader anyway.
- **Visual regression testing.** Repo has no Playwright; manual spot-check + screenshots in PR. Same posture as M20.
- **Reduced-motion media query.** Explicitly dropped per project owner. If accessibility regresses noisily, revisit.
- **Migrating remaining `Loader2` spinners.** Most stay. A future pass can revisit if a consistent inline vocabulary becomes desirable; today's posture is "indeterminate-to-text contexts keep `Loader2`; semantic contexts use `<DotMatrixLoader>`."
- **`verify` / `halt` consumer surfacing.** Both ship in this patch but unconsumed. Future Forge UX work (skill-promote toast, eval-pass card) is the natural home.
- **DAB integration as a runtime tool.** Rejected at triage. DAB stays as a designer-side tool; if we add a 7th loader later, designer fires up DAB locally, exports the JSON delay map, developer translates it. No runtime dependency.
- **Bigger-than-six palette.** `listening`, `handshake`, `cipher`, `radar`, `roulette` and others from dot/matrix's gallery are tonally fine but have no current METIS consumer. Add only when a consumer earns a slot — same discipline as M14's "one star per active technique."

---

## References

- **Source intake:** [`plans/IDEAS.md` → "dot/matrix loaders + DAB pixel/braille editor"](../../plans/IDEAS.md)
- **Upstream gallery:** https://icons.icantcode.fyi/ (dot/matrix v0.2, 2026)
- **Upstream repo:** https://github.com/icantcodefyi/dot-matrix-animations
- **DAB designer tool:** https://obaidnadeem.github.io/dab/
- **M20 brand primitives:** [`apps/metis-web/components/brand/README.md`](../../apps/metis-web/components/brand/README.md), [`docs/plans/2026-04-28-metis-logo-rollout-design.md`](2026-04-28-metis-logo-rollout-design.md)
- **M01 plan doc:** [`docs/preserve-and-productize-plan.md`](../preserve-and-productize-plan.md)
- **M21 Phase 5 ADR addendum (constellation aesthetic pivot):** [`docs/adr/0006-constellation-design-2d-primary.md`](../adr/0006-constellation-design-2d-primary.md)
