# Dot-matrix loaders

`<DotMatrixLoader>` is the inline-semantic loader vocabulary. It lives
next to `<MetisLoader>` (brand-forward) but solves a different problem:
in-text states where the brand mark would be too heavy — the chat
thinking-bubble, the technique-card pending state, a button busy
state. Each loader is a 5×5 dot grid driven by a single CSS keyframe
and a per-dot `animation-delay` map (~4 KB inline SVG per loader, no
JS runtime). The dot aesthetic threads back to the M-mark, so the
vocabulary is brand-coherent without re-using brand-forward primitives.

## Vocabulary

| Slug | Semantic role | Choreography | Current consumer |
|---|---|---|---|
| `thinking` | Agent composing / reflecting | Outer ring at 15%; inner 3×3 cluster fires on a 1200 ms loop with per-cell delays. Reads as "neurons firing." | Chat thinking-bubble (`chat-panel.tsx`); companion-dock reflect-now busy (`metis-companion-dock.tsx`). |
| `stream` | Tokens emitting | Dots light in row-major order (top-left → bottom-right) with a 60 ms per-dot stagger. Reads as "tokens marching out in reading order." | Chat send-button pending (`chat-panel.tsx`). |
| `compile` | Multi-step process running | Five columns fill bottom-up (120 ms per dot, 480 ms per column), 800 ms inter-column stagger; full grid holds, then releases per cell at the end of its own 4600 ms cycle. (See [implementation note](#a-note-on-compile) below.) | Forge technique-card pending (`technique-card.tsx`); companion-dock atlas-save busy (`metis-companion-dock.tsx`). |
| `verify` | Success (one-shot) | Five cells trace a checkmark in time order, ignite-and-hold; final frame stays via `fill-mode: forwards`. | *Available — no current consumer; reserved for future skill-promote success / eval-pass surfaces.* |
| `halt` | Error / cancel (one-shot) | Inner 3×3 collapses to centre over 800 ms; final frame is the centre dot alone. | *Available — no current consumer; reserved for future error / cancel surfaces.* |
| `breath` | Idle "alive" | All 25 dots breathe together 30% → 100% → 30% over 3000 ms. Reads as "the surface is alive but quiet." | Root `app/loading.tsx` (route-level fallback). |

## API

```tsx
<DotMatrixLoader name="thinking" size={20} />
```

The `name` union:

```tsx
type DotMatrixLoaderName =
  | "thinking" | "stream" | "compile"
  | "verify" | "halt" | "breath";
```

Defaults: `size={20}` (sized for inline use), and `aria-label` derives
from `name` via a semantic-English map (`thinking → "Thinking"`,
`stream → "Streaming"`, `compile → "Working"`, `verify → "Verified"`,
`halt → "Halted"`, `breath → "Loading"`). Override per call site
with the `aria-label` prop. `verify` and `halt` are one-shot
(`animation-iteration-count: 1` + `fill-mode: forwards`); re-run them
by changing `key=` at the call site (the standard React idiom for
restarting CSS animations).

## Theming

Dots use `fill="currentColor"`. Tinting cascades from any parent that
sets `color` (e.g. `text-muted-foreground`). Same convention as
`<MetisMark>`. No new tokens; loaders inherit text colour from their
surrounding context.

## Adding a new loader

1. Design the choreography on paper or in a tool like
   [DAB](https://obaidnadeem.github.io/dab/) (browser-based dot-grid
   editor that exports per-frame arrays).
2. Author the keyframe in `keyframes.css` named `dm-<slug>`. Use the
   per-cell `animation-delay` map idiom (see `thinking.tsx` or
   `stream.tsx` for canonical examples).
3. Create `<slug>.tsx` mirroring the existing sub-components — import
   from `./cells`, take the `DotMatrixSubProps` shape, render 25
   circles with `fill="currentColor"`.
4. Add `"<slug>"` to the `DotMatrixLoaderName` union in
   `dot-matrix-loader.tsx`, add a `case "<slug>":` arm to the
   dispatcher, and add a `<slug>` entry to `DEFAULT_ARIA`.
5. Append a row to the vocabulary table in this README.
6. Add a contract test in `__tests__/dot-matrix-loader.test.tsx`
   (class assertion + 25-circle assertion at minimum;
   per-cell-delay assertions if the choreography is delay-driven).

## A note on `compile`

The current `compile` keyframe (`0/10/87/100`) plus the per-cell
`animation-delay` map produces *rolling* fill-and-release rather than
the design doc's intended "snap-release" (where all cells would fade
together at the global cycle boundary). Achieving snap-release in
pure CSS requires either two animations per cell or a separate
synchronised release layer; the current single-keyframe form is a
deliberate first-pass simplification. If the rolling release reads
poorly in practice, the upgrade path is documented in the design doc
under *Phase 4 — Tuning*.

## Attribution

> The dot-matrix loader vocabulary is inspired by [dot/matrix](https://icons.icantcode.fyi/) by [@icantcodefyi](https://github.com/icantcodefyi). The 5×5-grid + single-keyframe + per-dot-delay-map technique originated there. The six choreographies in this folder are original work designed to fit METIS's specific semantic roles (`thinking`, `stream`, `compile`, `verify`, `halt`, `breath`); they are not vendored from the dot/matrix repo. Permission to use the technique was granted by the author.
