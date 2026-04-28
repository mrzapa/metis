# Components directory inversion inventory

**Last updated:** 2026-04-27 by `claude/review-codebase-standards-HSWD9`

A LANGUAGE.md-style audit of `apps/metis-web/components/`. Records
the "inverted depth" pattern flagged in the codebase audit: top-level
silos that each ship one or two mega-components and a long tail of
single-use leaf components extracted as private names rather than
real reusable modules.

The audit is intentionally separate from the [interface-confusion
inventory](./interface-confusion-inventory.md), which tracks the
reverse problem (interfaces lying about what's behind them).

## Vocabulary recap (from `docs/LANGUAGE.md`)

- **Deep module**: large behaviour behind a small interface.
  Leverage and locality both pay off.
- **Shallow module**: interface nearly as wide as the implementation.
  Caller pays an interface cost without getting leverage back.
- **Deletion test**: imagine deleting the module. If complexity
  vanishes (no caller has to take it on), the module wasn't earning
  its keep.
- **One adapter is hypothetical, two adapters is real.** A
  single-use leaf component is a hypothetical seam.

## Mega-components (decompose along an orchestration axis)

Each of these ships >1k LOC behind a single React component name. The
deletion test passes — they hold real complexity — but the *interface
shape is wrong*: callers cannot opt into a sub-flow without taking
the whole component. Decomposition target: split along
**orchestration** axes (upload flow vs. archetype flow vs. learning
route flow), not along **render** axes (header vs. body vs. footer).

| File | LOC | Status | Suggested split |
|---|---:|---|---|
| `components/constellation/star-observatory-dialog.tsx` | 1860 | **Partial extraction landed (this PR):** `useIndexBuildProgress` hook now owns the read→embed→save state machine. | Next: extract upload-flow state (selectedFiles, uploadedPaths, uploading, uploadError, pickError, rawPaths, desktopPaths) into `useStarUploadFlow`; archetype-flow state (`selectedArchetype` + suggestion fetch) into `useStarArchetype`; commit-and-link logic into `commitStarUpdate` as a free function. |
| `components/brain/brain-graph-3d.tsx` | 1658 | Untouched | Three.js scene management is a real deep module — keep the canvas adapter monolithic. Extract: brain-graph-rag-activity subscription, hover/select state, and camera transitions into separate hooks called from the canvas component. |
| `components/shell/metis-companion-dock.tsx` | 1511 | Untouched | Dock is a stable shell; the depth here is in the dock-tab orchestration. Extract: per-tab content components (research dock, autonomous dock, network audit dock) into `components/shell/dock-tabs/` so each tab is a real adapter. |
| `components/chat/chat-panel.tsx` | 1145 | Untouched | Some of the dedup pain is now centralised via `lib/services/rag-stream-dedup.ts` (this PR). Next: lift the `ActiveRagStream` state machine into a dedicated hook, since `app/chat/page.tsx` carries 16 fields of stream state today. |
| `components/gguf/gguf-models-panel.tsx` | 961 | Untouched | Verify it's not duplicating logic with `components/library/nyx-catalog-page.tsx`; both are catalog browsers. |
| `components/home/landing-starfield-webgl.tsx` | 900 | Untouched | WebGL renderer is a real deep module — keep monolithic. Make sure the `useLandingStars()`-style hooks (already real adapters) cover all entry points. |

## Single-use leaf components inside the megas

These are extracted *inside* the mega-component file as named
`function`s — the audit's "inverted depth" pattern. Each has exactly
one caller. They cost interface complexity without paying leverage.

| File | Component | Callers | Recommended action |
|---|---|---:|---|
| `star-observatory-dialog.tsx` | `StarMiniPreview` | 1 (within file) | Inline into the dialog body. |
| `star-observatory-dialog.tsx` | `StarIdentityPanel` | 1 | Inline. |
| `star-observatory-dialog.tsx` | `FacultyConceptPanel` | 1 | Inline or, if it has independent state, promote to its own file in `components/constellation/`. |

Not exhaustive — sweep with `grep -E '^function [A-Z]'
components/**/*.tsx` to find more.

## Real adapters — preserve

These are deep modules done right. They have a small external
interface and real behaviour behind it. Avoid accidental erosion
during decomposition.

- `lib/landing-stars/` — 1.6k LOC behind ~12 named exports;
  10+ call sites. Spatial index, LOD, profile generation, halo
  composition.
- `lib/star-catalogue/` — 810 LOC behind ~11 named exports;
  filter / promotion / naming.
- `hooks/use-constellation-camera.ts` — 280 LOC behind a single
  `useConstellationCamera()` returning a 14-method handle. Easing,
  galaxy pullback, idle drift, dive ease, scroll velocity.
  *Audit incorrectly flagged this for inlining; deletion test
  fails — page.tsx would grow by 200+ lines of math.*
- `hooks/use-constellation-stars.ts` — 270 LOC of state +
  localStorage + settings sync + nourishment events. *Same:
  do not inline.*
- `hooks/use-star-focus-phase.ts` — small, but earns its keep
  by guaranteeing the state/ref mirror never drifts (cause of
  past "stuck in focusing" bugs). Added in this PR.
- `hooks/use-index-build-progress.ts` — small, names the
  read→embed→save transitions explicitly. Added in this PR.
- `lib/services/rag-stream-dedup.ts` — small, but the policy
  is subtle (resume floor + signature dedup + watermark
  advancement) and the dialog used to inline all three. Added
  in this PR; tested in `lib/__tests__/rag-stream-dedup.test.ts`.

## Process note

Future audits should run alongside this file rather than rebuilding
the inventory from scratch. The deletion test and "two adapters is
real" rule are the two primitives to apply.
