# Quiet Loaders Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship a six-loader inline-semantic dot-matrix vocabulary (`<DotMatrixLoader>`) next to M20's `<MetisLoader>`, and migrate six existing `Loader2` / cyan-ring sites to use it.

**Architecture:** Dispatcher React component at `apps/metis-web/components/brand/dot-matrix-loader.tsx` switches on a `name` prop and renders one of six 5×5-SVG sub-components (`thinking`, `stream`, `compile`, `verify`, `halt`, `breath`). Animation comes from a single shared `keyframes.css` file (six `@keyframes` blocks, imported once in `app/layout.tsx`). Theming via `currentColor`. No reduced-motion gate (deliberate). Pure CSS — no `motion/react`, no JS hook.

**Tech Stack:** React 18 / Next.js 15 (static export), TypeScript, Tailwind utility classes, vitest + `@testing-library/react`. SVG inline. CSS keyframes. lucide-react stays imported (not all `Loader2` usage migrates).

**Design source:** [`docs/plans/2026-05-02-quiet-loaders-design.md`](2026-05-02-quiet-loaders-design.md) — full architectural rationale, choreography specs, attribution, and out-of-scope list. **Read it before starting.**

**Milestone:** M01 — *preserve and productise* (rolling). Add a *Quiet loader pass* note to `docs/preserve-and-productize-plan.md` under *Notes for the next agent* in Phase 3 of this plan.

---

## Conventions

- **Path roots.** All app paths are relative to `apps/metis-web/` unless stated otherwise (e.g. `components/brand/dot-matrix/thinking.tsx` means `apps/metis-web/components/brand/dot-matrix/thinking.tsx`).
- **Cell indexing.** 5×5 grid. `(col, row)` where `(0, 0)` is top-left and `(4, 4)` is bottom-right. Convention matches the shipped `cells.ts` (stores `[col, row]` tuples) and `INNER_DELAYS` (keys are `"col,row"` strings). Earlier drafts of this plan said `(row, col)`; corrected after Copilot review.
- **Re-locating call sites.** Line numbers in this plan are **as of plan-write time (2026-05-02)**. They will drift. Each migration task gives a `grep` recipe to re-find the exact line before editing.
- **Test command.** `pnpm test components/brand` (run from `apps/metis-web/`). Build: `pnpm build`. Type-check only: `pnpm typecheck`.
- **Dev visual check.** `pnpm dev` and visit the surface at `http://localhost:3000/<route>`. Use the chat thinking-bubble surface as the canonical sanity check that the keyframes CSS imported.
- **Commit style.** Match recent METIS commit messages (e.g. `feat(quiet-loaders): add <thing>`, `fix(m01): migrate <surface>`). Examples in `git log -10 --oneline`.

---

## Phase 1 — Primitive scaffold

Six loaders + dispatcher + keyframes CSS + tests. TDD on each loader: failing test → keyframe + component → passing test → commit. Phase 1 is ~14 tasks.

### Task 1: Wire keyframes CSS scaffold + author `breath` (simplest loader)

**Files:**
- Create: `components/brand/dot-matrix/keyframes.css`
- Modify: `app/layout.tsx` (add one CSS import next to the existing `globals.css` import)

**Step 1.1: Create the keyframes file with the `breath` rule.**

Write `components/brand/dot-matrix/keyframes.css`:

```css
/* dot-matrix loader keyframes
 *
 * One @keyframes block per loader. Each block is named `dm-<slug>` to
 * match the class applied by the matching sub-component.
 *
 * Theming via currentColor; no opacity overrides here — the keyframe
 * controls opacity entirely.
 *
 * See ./README.md for vocabulary and authorship notes.
 */

@keyframes dm-breath {
  0%, 100% { opacity: 0.30; }
  50%      { opacity: 1.00; }
}

.dm-breath circle {
  animation: dm-breath 3000ms ease-in-out infinite;
}
```

**Step 1.2: Wire the import.**

Open `app/layout.tsx`. Find the existing import of `./globals.css` (one of the first imports near the top of the file). Add directly below it:

```tsx
import "@/components/brand/dot-matrix/keyframes.css";
```

**Step 1.3: Smoke-check the build.**

Run: `pnpm build`
Expected: build succeeds, no CSS errors.

**Step 1.4: Commit.**

```bash
git add apps/metis-web/components/brand/dot-matrix/keyframes.css apps/metis-web/app/layout.tsx
git commit -m "feat(quiet-loaders): scaffold dot-matrix keyframes CSS + breath rule"
```

---

### Task 2: Failing test for `<DotMatrixLoader name="breath">`

**Files:**
- Create: `components/brand/__tests__/dot-matrix-loader.test.tsx`

**Step 2.1: Write the test.**

```tsx
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { DotMatrixLoader } from "../dot-matrix-loader";

describe("<DotMatrixLoader>", () => {
  it("renders breath as a 5×5 grid of circles with the dm-breath class", () => {
    const { container } = render(<DotMatrixLoader name="breath" />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg!.classList.contains("dm-breath")).toBe(true);
    const circles = container.querySelectorAll("circle");
    expect(circles.length).toBe(25);
  });
});
```

**Step 2.2: Run the test, expect FAIL.**

Run: `pnpm test components/brand/__tests__/dot-matrix-loader`
Expected: FAIL — `Cannot find module "../dot-matrix-loader"` or similar.

**Step 2.3: Do not commit yet.** The test stays failing until Task 3 lands.

---

### Task 3: Implement minimal `<DotMatrixLoader>` + `breath.tsx`

**Files:**
- Create: `components/brand/dot-matrix/breath.tsx`
- Create: `components/brand/dot-matrix-loader.tsx`

**Step 3.1: Create `breath.tsx`.**

```tsx
import type { CSSProperties } from "react";

interface DotMatrixSubProps {
  size: number;
  className?: string;
  ariaLabel: string;
}

/**
 * 5×5 grid coordinates (col, row) for the 25 circles.
 * Generated once at module load.
 */
const CELLS: ReadonlyArray<readonly [number, number]> = (() => {
  const out: Array<[number, number]> = [];
  for (let row = 0; row < 5; row++) {
    for (let col = 0; col < 5; col++) {
      out.push([col, row]);
    }
  }
  return out;
})();

/** Cell-centre coordinates in the 50×50 viewBox (10 px per cell). */
const cx = (col: number) => col * 10 + 5;
const cy = (row: number) => row * 10 + 5;
const DOT_RADIUS = 2;

export function BreathLoader({ size, className, ariaLabel }: DotMatrixSubProps) {
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox="0 0 50 50"
      width={size}
      height={size}
      className={["dm-breath", className].filter(Boolean).join(" ")}
      data-dot-matrix-loader="breath"
    >
      {CELLS.map(([col, row], i) => (
        <circle
          key={i}
          cx={cx(col)}
          cy={cy(row)}
          r={DOT_RADIUS}
          fill="currentColor"
        />
      ))}
    </svg>
  );
}
```

(`CELLS` and the helpers will be moved to a shared module in Task 5; for now they live inline.)

**Step 3.2: Create the dispatcher.**

```tsx
/**
 * Dot-matrix inline semantic loaders.
 *
 * 5×5 grid · single CSS @keyframes · per-dot animation-delay map.
 * Technique inspired by https://icons.icantcode.fyi/ (used with permission).
 * See `./dot-matrix/README.md` for the full vocabulary and authorship notes.
 */
"use client";

import { BreathLoader } from "./dot-matrix/breath";

export type DotMatrixLoaderName =
  | "thinking"
  | "stream"
  | "compile"
  | "verify"
  | "halt"
  | "breath";

export interface DotMatrixLoaderProps {
  name: DotMatrixLoaderName;
  size?: number;
  "aria-label"?: string;
  className?: string;
}

const DEFAULT_ARIA: Record<DotMatrixLoaderName, string> = {
  thinking: "Thinking",
  stream: "Streaming",
  compile: "Working",
  verify: "Verified",
  halt: "Halted",
  breath: "Loading",
};

export function DotMatrixLoader({
  name,
  size = 20,
  className,
  "aria-label": ariaLabel,
}: DotMatrixLoaderProps) {
  const label = ariaLabel ?? DEFAULT_ARIA[name];
  switch (name) {
    case "breath":
      return <BreathLoader size={size} className={className} ariaLabel={label} />;
    // Other arms added in Tasks 4–13.
    default:
      // Fallback while authoring; replaced with exhaustive switch in Task 14.
      return <BreathLoader size={size} className={className} ariaLabel={label} />;
  }
}
```

**Step 3.3: Run the test, expect PASS.**

Run: `pnpm test components/brand/__tests__/dot-matrix-loader`
Expected: PASS — 1/1.

**Step 3.4: Commit.**

```bash
git add apps/metis-web/components/brand/dot-matrix-loader.tsx apps/metis-web/components/brand/dot-matrix/breath.tsx apps/metis-web/components/brand/__tests__/dot-matrix-loader.test.tsx
git commit -m "feat(quiet-loaders): DotMatrixLoader dispatcher + breath sub-component"
```

---

### Task 4: Failing test for `thinking`

**Files:**
- Modify: `components/brand/__tests__/dot-matrix-loader.test.tsx`

**Step 4.1: Append a test.**

```tsx
it("renders thinking with the dm-thinking class and 25 circles", () => {
  const { container } = render(<DotMatrixLoader name="thinking" />);
  const svg = container.querySelector("svg");
  expect(svg!.classList.contains("dm-thinking")).toBe(true);
  expect(container.querySelectorAll("circle").length).toBe(25);
});

it("inner-cluster cells of thinking carry an animation-delay style", () => {
  // Inner 3×3 spans cols 1..3, rows 1..3. Per the design doc, those
  // 9 cells are the only ones with non-zero animation-delay.
  const { container } = render(<DotMatrixLoader name="thinking" />);
  const circles = Array.from(container.querySelectorAll("circle"));
  // Inner cluster cells are indices where col in [1..3] and row in [1..3]
  // — for our row-major emit order, those are 9 specific indices.
  const innerIndices = [6, 7, 8, 11, 12, 13, 16, 17, 18];
  const inner = innerIndices.map((i) => circles[i] as SVGCircleElement);
  for (const c of inner) {
    expect(c.style.animationDelay).not.toBe("");
  }
});
```

**Step 4.2: Run, expect FAIL.**

Run: `pnpm test components/brand/__tests__/dot-matrix-loader`
Expected: 2 new tests FAIL.

---

### Task 5: Author `thinking` keyframe + sub-component

**Files:**
- Modify: `components/brand/dot-matrix/keyframes.css`
- Create: `components/brand/dot-matrix/cells.ts` (extract `CELLS`, `cx`, `cy`, `DOT_RADIUS` from `breath.tsx`)
- Modify: `components/brand/dot-matrix/breath.tsx` (import from `./cells`)
- Create: `components/brand/dot-matrix/thinking.tsx`
- Modify: `components/brand/dot-matrix-loader.tsx` (add `thinking` arm)

**Step 5.1: Extract shared cell module.**

Create `components/brand/dot-matrix/cells.ts`:

```ts
/** 25-cell flat array, row-major: index = row * 5 + col. */
export const CELLS: ReadonlyArray<readonly [number, number]> = (() => {
  const out: Array<[number, number]> = [];
  for (let row = 0; row < 5; row++) {
    for (let col = 0; col < 5; col++) {
      out.push([col, row]);
    }
  }
  return out;
})();

export const cx = (col: number) => col * 10 + 5;
export const cy = (row: number) => row * 10 + 5;
export const DOT_RADIUS = 2;
export const VIEWBOX = "0 0 50 50";

export const isInnerCluster = (col: number, row: number) =>
  col >= 1 && col <= 3 && row >= 1 && row <= 3;
```

**Step 5.2: Update `breath.tsx` to import from `./cells`.**

Replace the inline `CELLS`/`cx`/`cy`/`DOT_RADIUS` definitions in `breath.tsx` with:

```tsx
import { CELLS, cx, cy, DOT_RADIUS, VIEWBOX } from "./cells";
```

…and use `viewBox={VIEWBOX}` on the `<svg>`.

**Step 5.3: Add the `thinking` keyframe.**

Append to `components/brand/dot-matrix/keyframes.css`:

```css
@keyframes dm-thinking {
  0%, 100% { opacity: 0; }
  20%      { opacity: 1; }
  60%      { opacity: 0; }
}

/* Outer ring stays dim; inner 3×3 fires per per-dot delays set inline. */
.dm-thinking circle {
  opacity: 0.15;
}
.dm-thinking circle[data-inner="1"] {
  opacity: 0;
  animation: dm-thinking 1200ms ease-in-out infinite;
}
```

**Step 5.4: Create `thinking.tsx`.**

```tsx
import type { CSSProperties } from "react";
import { CELLS, cx, cy, DOT_RADIUS, VIEWBOX, isInnerCluster } from "./cells";

interface DotMatrixSubProps {
  size: number;
  className?: string;
  ariaLabel: string;
}

/** Per-cell delays (ms) for the inner 3×3 cluster, indexed by (col, row).
 *  Manually authored to read as random-but-deterministic firing.
 *  Cells: (col,row) → delay ms.
 */
const INNER_DELAYS: Record<string, number> = {
  "1,1": 0,
  "2,1": 200,
  "3,1": 400,
  "1,2": 600,
  "2,2": 100,
  "3,2": 300,
  "1,3": 500,
  "2,3": 700,
  "3,3": 50,
};

export function ThinkingLoader({ size, className, ariaLabel }: DotMatrixSubProps) {
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={VIEWBOX}
      width={size}
      height={size}
      className={["dm-thinking", className].filter(Boolean).join(" ")}
      data-dot-matrix-loader="thinking"
    >
      {CELLS.map(([col, row], i) => {
        const inner = isInnerCluster(col, row);
        const delay = inner ? INNER_DELAYS[`${col},${row}`] : undefined;
        const style: CSSProperties | undefined =
          delay !== undefined ? { animationDelay: `${delay}ms` } : undefined;
        return (
          <circle
            key={i}
            cx={cx(col)}
            cy={cy(row)}
            r={DOT_RADIUS}
            fill="currentColor"
            data-inner={inner ? "1" : "0"}
            style={style}
          />
        );
      })}
    </svg>
  );
}
```

**Step 5.5: Add the `thinking` arm to the dispatcher.**

In `dot-matrix-loader.tsx`, add the import and the case:

```tsx
import { ThinkingLoader } from "./dot-matrix/thinking";
```

Inside the switch:

```tsx
case "thinking":
  return <ThinkingLoader size={size} className={className} ariaLabel={label} />;
```

**Step 5.6: Run all tests.**

Run: `pnpm test components/brand/__tests__/dot-matrix-loader`
Expected: 3/3 PASS (1 breath + 2 thinking).

**Step 5.7: Commit.**

```bash
git add apps/metis-web/components/brand/dot-matrix/cells.ts apps/metis-web/components/brand/dot-matrix/thinking.tsx apps/metis-web/components/brand/dot-matrix/breath.tsx apps/metis-web/components/brand/dot-matrix/keyframes.css apps/metis-web/components/brand/dot-matrix-loader.tsx apps/metis-web/components/brand/__tests__/dot-matrix-loader.test.tsx
git commit -m "feat(quiet-loaders): add thinking loader + extract shared cells module"
```

---

### Task 6: Failing test for `stream`

**Files:**
- Modify: `components/brand/__tests__/dot-matrix-loader.test.tsx`

**Step 6.1: Append.**

```tsx
it("renders stream with dm-stream class and per-cell row-major delays", () => {
  const { container } = render(<DotMatrixLoader name="stream" />);
  const svg = container.querySelector("svg");
  expect(svg!.classList.contains("dm-stream")).toBe(true);
  const circles = Array.from(container.querySelectorAll("circle"));
  expect(circles.length).toBe(25);
  // Every circle should carry a non-empty animation-delay (every cell animates).
  for (const c of circles) {
    expect((c as SVGCircleElement).style.animationDelay).not.toBe("");
  }
});
```

**Step 6.2: Run, expect FAIL.**

---

### Task 7: Author `stream` keyframe + sub-component

**Files:**
- Modify: `components/brand/dot-matrix/keyframes.css`
- Create: `components/brand/dot-matrix/stream.tsx`
- Modify: `components/brand/dot-matrix-loader.tsx`

**Step 7.1: Append the `stream` keyframe.**

```css
@keyframes dm-stream {
  0%             { opacity: 0; }
  4%             { opacity: 1; }    /* 60ms fade-in over 1500ms cycle ≈ 4% */
  10.7%          { opacity: 1; }    /* +100ms hold */
  24%            { opacity: 0; }    /* +200ms fade-out */
  100%           { opacity: 0; }
}

.dm-stream circle {
  opacity: 0;
  animation: dm-stream 1500ms linear infinite;
}
```

**Step 7.2: Create `stream.tsx`.**

```tsx
import type { CSSProperties } from "react";
import { CELLS, cx, cy, DOT_RADIUS, VIEWBOX } from "./cells";

interface DotMatrixSubProps {
  size: number;
  className?: string;
  ariaLabel: string;
}

const STAGGER_MS = 60;

export function StreamLoader({ size, className, ariaLabel }: DotMatrixSubProps) {
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={VIEWBOX}
      width={size}
      height={size}
      className={["dm-stream", className].filter(Boolean).join(" ")}
      data-dot-matrix-loader="stream"
    >
      {CELLS.map(([col, row], i) => {
        const style: CSSProperties = {
          animationDelay: `${i * STAGGER_MS}ms`,
        };
        return (
          <circle
            key={i}
            cx={cx(col)}
            cy={cy(row)}
            r={DOT_RADIUS}
            fill="currentColor"
            style={style}
          />
        );
      })}
    </svg>
  );
}
```

**Step 7.3: Add dispatcher arm.**

```tsx
import { StreamLoader } from "./dot-matrix/stream";
// ...
case "stream":
  return <StreamLoader size={size} className={className} ariaLabel={label} />;
```

**Step 7.4: Run tests, expect PASS.**

Run: `pnpm test components/brand/__tests__/dot-matrix-loader`
Expected: 4/4 PASS.

**Step 7.5: Commit.**

```bash
git add apps/metis-web/components/brand/dot-matrix/stream.tsx apps/metis-web/components/brand/dot-matrix/keyframes.css apps/metis-web/components/brand/dot-matrix-loader.tsx apps/metis-web/components/brand/__tests__/dot-matrix-loader.test.tsx
git commit -m "feat(quiet-loaders): add stream loader (row-major token emission)"
```

---

### Task 8: Failing test for `compile`

**Step 8.1: Append.**

```tsx
it("renders compile with dm-compile class and 25 circles", () => {
  const { container } = render(<DotMatrixLoader name="compile" />);
  const svg = container.querySelector("svg");
  expect(svg!.classList.contains("dm-compile")).toBe(true);
  expect(container.querySelectorAll("circle").length).toBe(25);
});
```

**Step 8.2: Run, expect FAIL.**

---

### Task 9: Author `compile` keyframe + sub-component

**Step 9.1: Append the `compile` keyframe.**

The cycle is 4600 ms. Bottom-up column fill, then snap-release:

```css
@keyframes dm-compile {
  0%      { opacity: 0; }
  /* Per-dot ignite happens via animation-delay on the cell.
   * From its delay onward, the cell holds at 100%.
   * The shared release happens at 4000/4600 ≈ 87% (start of fade)
   * to 4600/4600 = 100% (end of fade). */
  87%     { opacity: 1; }
  100%    { opacity: 0; }
}

.dm-compile circle {
  opacity: 0;
  animation: dm-compile 4600ms ease-out infinite;
}
```

**Important:** the per-cell `animationDelay` controls when the dot ignites. After the delay, the dot is at 100% (the keyframe rises from 0% → 100% across the first ~13% of its remaining duration via `ease-out`). To get the bottom-up fill behaviour cleanly, we author the keyframe so:
- Each cell's effective animation starts at its delay and runs for `4600 - delay` ms.
- The keyframe at 87% (4000 ms absolute, but normalised to the cell's local timeline) holds the dot lit.
- Then the final 13% (600 ms) is the shared snap-release fade.

This requires `animation-fill-mode: backwards` so the dot is invisible *before* its delay, and the shared 87% mark to happen at the *same wall-clock time* across all cells. The simpler approach: don't try to share the release in the keyframe — instead, each cell's keyframe rises to 100% and stays. The "snap-release" is just the next cycle's start at 0%.

**Author the simpler keyframe:**

```css
@keyframes dm-compile {
  0%      { opacity: 0; }
  10%     { opacity: 1; }
  87%     { opacity: 1; }
  100%    { opacity: 0; }
}

.dm-compile circle {
  opacity: 0;
  animation: dm-compile 4600ms ease-out infinite;
  animation-fill-mode: both;
}
```

With per-cell delays (Step 9.2 below), this gives: dot is dark before its delay, fades-in over the first 10% of its post-delay duration, holds, then fades together with all cells at the cycle boundary. Visual reads as bottom-up fill + snap-release. **This is good enough for the first pass — Phase 4 tunes if it doesn't read.**

**Step 9.2: Create `compile.tsx`.**

```tsx
import type { CSSProperties } from "react";
import { CELLS, cx, cy, DOT_RADIUS, VIEWBOX } from "./cells";

interface DotMatrixSubProps {
  size: number;
  className?: string;
  ariaLabel: string;
}

const COL_STAGGER_MS = 800;
const ROW_STAGGER_MS = 120; // within a column, bottom-up

/** Delay (ms) for cell at (col, row).
 *  col 0 starts at 0; each next col +800ms.
 *  Within a col, row 4 (bottom) is first, then 3, 2, 1, 0.
 */
function compileDelay(col: number, row: number): number {
  const colStart = col * COL_STAGGER_MS;
  const inCol = (4 - row) * ROW_STAGGER_MS; // bottom-up
  return colStart + inCol;
}

export function CompileLoader({ size, className, ariaLabel }: DotMatrixSubProps) {
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={VIEWBOX}
      width={size}
      height={size}
      className={["dm-compile", className].filter(Boolean).join(" ")}
      data-dot-matrix-loader="compile"
    >
      {CELLS.map(([col, row], i) => {
        const style: CSSProperties = {
          animationDelay: `${compileDelay(col, row)}ms`,
        };
        return (
          <circle
            key={i}
            cx={cx(col)}
            cy={cy(row)}
            r={DOT_RADIUS}
            fill="currentColor"
            style={style}
          />
        );
      })}
    </svg>
  );
}
```

**Step 9.3: Add dispatcher arm and run tests, expect PASS.**

**Step 9.4: Commit.**

```bash
git commit -m "feat(quiet-loaders): add compile loader (bottom-up column fill + snap-release)"
```

---

### Task 10: Failing test for `verify` (one-shot)

**Step 10.1: Append.**

```tsx
it("renders verify as a one-shot with fill-forwards", () => {
  const { container } = render(<DotMatrixLoader name="verify" />);
  const svg = container.querySelector("svg");
  expect(svg!.classList.contains("dm-verify")).toBe(true);
  // Six checkmark cells should carry a non-empty animation-delay style.
  // Other cells should not animate at all.
  const circles = Array.from(container.querySelectorAll("circle")) as SVGCircleElement[];
  const animated = circles.filter((c) => c.style.animationDelay !== "");
  expect(animated.length).toBe(5); // (3,0) (4,1) (3,2) (2,3) (1,4)
});
```

**Step 10.2: Run, expect FAIL.**

---

### Task 11: Author `verify` keyframe + sub-component

**Step 11.1: Append the `verify` keyframe.**

```css
@keyframes dm-verify {
  0%   { opacity: 0; }
  100% { opacity: 1; }
}

/* Default: invisible. The 5 checkmark cells carry a per-cell animation
 * that ignites them in sequence and holds (fill-mode: forwards). */
.dm-verify circle {
  opacity: 0;
}
.dm-verify circle[data-check="1"] {
  animation: dm-verify 100ms ease-out 1 forwards;
}
```

**Step 11.2: Create `verify.tsx`.**

```tsx
import type { CSSProperties } from "react";
import { CELLS, cx, cy, DOT_RADIUS, VIEWBOX } from "./cells";

interface DotMatrixSubProps {
  size: number;
  className?: string;
  ariaLabel: string;
}

/** Checkmark trace cells in time order: (col, row).
 *  Short stroke (3,0) → (4,1), then long stroke (4,1) → (1,4).
 */
const CHECK_PATH: ReadonlyArray<readonly [number, number]> = [
  [3, 0], [4, 1], [3, 2], [2, 3], [1, 4],
];
const CHECK_STAGGER_MS = 180;

export function VerifyLoader({ size, className, ariaLabel }: DotMatrixSubProps) {
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={VIEWBOX}
      width={size}
      height={size}
      className={["dm-verify", className].filter(Boolean).join(" ")}
      data-dot-matrix-loader="verify"
    >
      {CELLS.map(([col, row], i) => {
        const checkIndex = CHECK_PATH.findIndex(([c, r]) => c === col && r === row);
        const onCheck = checkIndex !== -1;
        const style: CSSProperties | undefined = onCheck
          ? { animationDelay: `${checkIndex * CHECK_STAGGER_MS}ms` }
          : undefined;
        return (
          <circle
            key={i}
            cx={cx(col)}
            cy={cy(row)}
            r={DOT_RADIUS}
            fill="currentColor"
            data-check={onCheck ? "1" : "0"}
            style={style}
          />
        );
      })}
    </svg>
  );
}
```

**Step 11.3: Add dispatcher arm, run tests (expect PASS), commit.**

```bash
git commit -m "feat(quiet-loaders): add verify loader (one-shot checkmark trace)"
```

---

### Task 12: Failing test for `halt` (one-shot)

**Step 12.1: Append.**

```tsx
it("renders halt with dm-halt class and 25 circles", () => {
  const { container } = render(<DotMatrixLoader name="halt" />);
  const svg = container.querySelector("svg");
  expect(svg!.classList.contains("dm-halt")).toBe(true);
  expect(container.querySelectorAll("circle").length).toBe(25);
});
```

**Step 12.2: Run, expect FAIL.**

---

### Task 13: Author `halt` keyframe + sub-component

**Step 13.1: Append the `halt` keyframe.**

The choreography: t=0 inner 3×3 lit → t=400 ring fades → t=800 only centre stays.

```css
/* Inner 3×3 ring (8 cells around centre) lit until 400ms, then fades to 0
 * by 700ms, hold transparent. */
@keyframes dm-halt-ring {
  0%, 50%       { opacity: 1; }   /* 0–400ms of 800ms cycle */
  87.5%, 100%   { opacity: 0; }   /* 700–800ms */
}

/* Centre (2,2) lights at 0% and stays. */
@keyframes dm-halt-centre {
  0%, 100% { opacity: 1; }
}

.dm-halt circle {
  opacity: 0;
}
.dm-halt circle[data-halt="ring"] {
  animation: dm-halt-ring 800ms ease-out 1 forwards;
}
.dm-halt circle[data-halt="centre"] {
  animation: dm-halt-centre 800ms linear 1 forwards;
}
```

**Step 13.2: Create `halt.tsx`.**

```tsx
import { CELLS, cx, cy, DOT_RADIUS, VIEWBOX } from "./cells";

interface DotMatrixSubProps {
  size: number;
  className?: string;
  ariaLabel: string;
}

/** Inner 3×3 cells around centre (2,2) — the ring that fades. */
const RING_CELLS = new Set([
  "1,1", "2,1", "3,1",
  "1,2",        "3,2",
  "1,3", "2,3", "3,3",
]);

export function HaltLoader({ size, className, ariaLabel }: DotMatrixSubProps) {
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={VIEWBOX}
      width={size}
      height={size}
      className={["dm-halt", className].filter(Boolean).join(" ")}
      data-dot-matrix-loader="halt"
    >
      {CELLS.map(([col, row], i) => {
        const isCentre = col === 2 && row === 2;
        const isRing = RING_CELLS.has(`${col},${row}`);
        const haltAttr = isCentre ? "centre" : isRing ? "ring" : undefined;
        return (
          <circle
            key={i}
            cx={cx(col)}
            cy={cy(row)}
            r={DOT_RADIUS}
            fill="currentColor"
            data-halt={haltAttr}
          />
        );
      })}
    </svg>
  );
}
```

**Step 13.3: Add dispatcher arm, run tests (expect PASS), commit.**

```bash
git commit -m "feat(quiet-loaders): add halt loader (one-shot collapse to centre)"
```

---

### Task 14: Make the dispatcher exhaustive + size + aria-label tests

**Files:**
- Modify: `components/brand/dot-matrix-loader.tsx`
- Modify: `components/brand/__tests__/dot-matrix-loader.test.tsx`

**Step 14.1: Replace the `default:` arm with an exhaustive switch.**

```tsx
import { BreathLoader } from "./dot-matrix/breath";
import { CompileLoader } from "./dot-matrix/compile";
import { HaltLoader } from "./dot-matrix/halt";
import { StreamLoader } from "./dot-matrix/stream";
import { ThinkingLoader } from "./dot-matrix/thinking";
import { VerifyLoader } from "./dot-matrix/verify";

// ...inside the function body
switch (name) {
  case "thinking":
    return <ThinkingLoader size={size} className={className} ariaLabel={label} />;
  case "stream":
    return <StreamLoader size={size} className={className} ariaLabel={label} />;
  case "compile":
    return <CompileLoader size={size} className={className} ariaLabel={label} />;
  case "verify":
    return <VerifyLoader size={size} className={className} ariaLabel={label} />;
  case "halt":
    return <HaltLoader size={size} className={className} ariaLabel={label} />;
  case "breath":
    return <BreathLoader size={size} className={className} ariaLabel={label} />;
  default: {
    // Exhaustiveness check — TypeScript should ensure this is unreachable.
    const _never: never = name;
    void _never;
    return null;
  }
}
```

**Step 14.2: Append size + aria-label tests.**

```tsx
it("respects a custom size prop on the rendered svg", () => {
  const { container } = render(<DotMatrixLoader name="breath" size={48} />);
  const svg = container.querySelector("svg") as SVGSVGElement;
  expect(svg.getAttribute("width")).toBe("48");
  expect(svg.getAttribute("height")).toBe("48");
});

it("default aria-label is derived from name when not overridden", () => {
  const { container } = render(<DotMatrixLoader name="thinking" />);
  const svg = container.querySelector("svg") as SVGSVGElement;
  expect(svg.getAttribute("aria-label")).toBe("Thinking");
});

it("custom aria-label overrides the default", () => {
  const { container } = render(
    <DotMatrixLoader name="thinking" aria-label="Reasoning…" />
  );
  const svg = container.querySelector("svg") as SVGSVGElement;
  expect(svg.getAttribute("aria-label")).toBe("Reasoning…");
});
```

**Step 14.3: Run, expect ALL PASS.**

Run: `pnpm test components/brand`
Expected: all dot-matrix tests pass + existing brand tests still pass.

**Step 14.4: Commit.**

```bash
git commit -m "test(quiet-loaders): exhaustive dispatcher + size/aria-label coverage"
```

---

### Task 15: Re-export from `components/brand/index.ts`

**Files:**
- Modify: `components/brand/index.ts`

**Step 15.1: Append exports.**

After the existing `export { MetisLoader, ... }` line, add:

```ts
export {
  DotMatrixLoader,
  type DotMatrixLoaderName,
  type DotMatrixLoaderProps,
} from "./dot-matrix-loader";
```

**Step 15.2: Smoke-check.**

Run: `pnpm typecheck` (or `pnpm build`).
Expected: no errors.

**Step 15.3: Commit.**

```bash
git commit -m "feat(quiet-loaders): re-export DotMatrixLoader from brand barrel"
```

**End of Phase 1.**

---

## Phase 2 — Surface migrations

Six file edits, six commits. Each task: re-locate the line with grep, swap the import + JSX, typecheck, visual spot-check at `pnpm dev`, commit.

### Task 16: Migrate chat thinking-bubble

**Files:**
- Modify: `apps/metis-web/components/chat/chat-panel.tsx`

**Step 16.1: Re-locate the call site.**

Run from repo root:

```bash
grep -nE 'glass-micro-surface.*rounded' apps/metis-web/components/chat/chat-panel.tsx | head
```

Or look for the chat-thinking bubble — it's the `Loader2 size-3.5 animate-spin` inside a `glass-micro-surface rounded-[1.1rem]` div, immediately after the `flex justify-start` wrapper. **At plan-write time, line 909.**

**Step 16.2: Edit the JSX.**

Replace:

```tsx
<AnimatedLucideIcon icon={Loader2} mode="spin" className="size-3.5" />
```

…with:

```tsx
<DotMatrixLoader name="thinking" size={14} className="text-muted-foreground" />
```

**Step 16.3: Add the import.**

Near the existing imports from `lucide-react` and `@/components/ui/animated-lucide-icon`, add:

```tsx
import { DotMatrixLoader } from "@/components/brand";
```

**Step 16.4: Typecheck.**

Run: `pnpm typecheck`
Expected: no errors.

**Step 16.5: Visual spot-check.**

Run: `pnpm dev`. Open `http://localhost:3000/chat`, send a message, observe the thinking bubble while the response is in flight. Confirm the inner 3×3 cluster fires; outer ring is dim.

**Step 16.6: Commit.**

```bash
git commit -m "feat(m01): migrate chat thinking-bubble to DotMatrixLoader.thinking"
```

---

### Task 17: Migrate chat send-button pending state

**Files:**
- Modify: `apps/metis-web/components/chat/chat-panel.tsx`

**Step 17.1: Re-locate.**

Look for the `isSending ? ... : ...` ternary on the send button. **At plan-write time, line 1084.** The current code:

```tsx
{isSending ? (
  <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" />
) : (
  <AnimatedLucideIcon icon={SendHorizontal} mode="hoverLift" className="size-4" />
)}
```

**Step 17.2: Replace the `isSending` arm.**

```tsx
{isSending ? (
  <DotMatrixLoader name="stream" size={16} className="text-foreground" />
) : (
  <AnimatedLucideIcon icon={SendHorizontal} mode="hoverLift" className="size-4" />
)}
```

(Import already added in Task 16.)

**Step 17.3: Typecheck + dev visual spot-check + commit.**

```bash
git commit -m "feat(m01): migrate chat send-button pending to DotMatrixLoader.stream"
```

---

### Task 18: Migrate Forge technique-card pending chip

**Files:**
- Modify: `apps/metis-web/components/forge/technique-card.tsx`

**Step 18.1: Re-locate.**

```bash
grep -nE 'pending.*Loader2|Loader2.*size-3' apps/metis-web/components/forge/technique-card.tsx | head
```

Look for the `pending ? <Loader2 ... /> : null` ternary. **At plan-write time, line 380.**

**Step 18.2: Replace.**

```tsx
{pending ? (
  <DotMatrixLoader name="compile" size={12} className="text-foreground/70" />
) : null}
```

Add import: `import { DotMatrixLoader } from "@/components/brand";`

**Step 18.3: Typecheck + spot-check at `/forge` (toggle a technique to trigger pending) + commit.**

```bash
git commit -m "feat(m01): migrate Forge technique-card pending to DotMatrixLoader.compile"
```

---

### Task 19: Migrate companion-dock reflect-now busy state

**Files:**
- Modify: `apps/metis-web/components/shell/metis-companion-dock.tsx`

**Step 19.1: Re-locate.**

```bash
grep -nE 'busyAction.*reflect|reflect.*Loader2' apps/metis-web/components/shell/metis-companion-dock.tsx | head
```

Look for `busyAction === "reflect" ? <Loader2 ... /> : <RefreshCw ... />`. **At plan-write time, line 1063.**

**Step 19.2: Replace the `Loader2` arm.**

```tsx
{busyAction === "reflect" ? (
  <DotMatrixLoader name="thinking" size={16} className="text-foreground" />
) : (
  <RefreshCw className="size-4" />
)}
```

Add import.

**Step 19.3: Typecheck + spot-check (open companion dock, click "Reflect now") + commit.**

```bash
git commit -m "feat(m01): migrate companion-dock reflect-now to DotMatrixLoader.thinking"
```

---

### Task 20: Migrate companion-dock atlas-save busy state

**Files:**
- Modify: `apps/metis-web/components/shell/metis-companion-dock.tsx`

**Step 20.1: Re-locate.**

```bash
grep -nE 'atlasBusyAction.*save' apps/metis-web/components/shell/metis-companion-dock.tsx | head
```

**At plan-write time, line 779.** Code:

```tsx
{atlasBusyAction === "save" ? (
  <Loader2 className="size-3.5 animate-spin" />
) : null}
Save to Atlas
```

**Step 20.2: Replace.**

```tsx
{atlasBusyAction === "save" ? (
  <DotMatrixLoader name="compile" size={14} className="text-foreground/70" />
) : null}
Save to Atlas
```

(Import already added in Task 19.)

**Step 20.3: Typecheck + spot-check + commit.**

```bash
git commit -m "feat(m01): migrate companion-dock atlas-save to DotMatrixLoader.compile"
```

---

### Task 21: Replace `app/loading.tsx` cyan-ring outlier

**Files:**
- Modify: `apps/metis-web/app/loading.tsx`

**Step 21.1: Replace the entire body.**

```tsx
import { DotMatrixLoader } from "@/components/brand";

export default function RootLoading() {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="status"
      aria-label="Loading"
    >
      <div className="flex flex-col items-center gap-4 text-cyan-400/80">
        <DotMatrixLoader name="breath" size={48} />
        <p className="text-xs text-muted-foreground tracking-widest uppercase">
          Loading
        </p>
      </div>
    </div>
  );
}
```

(The `text-cyan-400/80` on the wrapper preserves the cyan tint of the original via `currentColor` cascade — keeps the brand-cyan note that was the only good thing about the cyan ring.)

**Step 21.2: Typecheck + spot-check.**

To trigger this loader, throttle network in dev tools and visit `/` cold. Confirm the breathing dot grid replaces the spinning ring.

**Step 21.3: Commit.**

```bash
git commit -m "fix(m01): replace cyan-ring loader at app/loading.tsx with DotMatrixLoader.breath"
```

**End of Phase 2.**

---

## Phase 3 — Documentation

### Task 22: Author `dot-matrix/README.md`

**Files:**
- Create: `apps/metis-web/components/brand/dot-matrix/README.md`

**Step 22.1: Author the README.**

Use this template — see [`docs/plans/2026-05-02-quiet-loaders-design.md` § Documentation surfaces](2026-05-02-quiet-loaders-design.md) for the canonical attribution wording. Suggested structure:

1. Purpose paragraph (one paragraph: "inline semantic loaders, sibling to `<MetisLoader>`").
2. Vocabulary table — six rows: slug · semantic role · choreography one-liner · current consumer or "available."
3. API snippet showing `<DotMatrixLoader name="thinking" size={20} />` plus the union type.
4. Theming note (`currentColor` cascades from parent — same convention as `<MetisMark>`).
5. "Adding a new loader" subsection — workflow: design frames in DAB if needed, hand-author keyframe + delay map, write sub-component file, add to `DotMatrixLoaderName` union, add row to vocabulary table.
6. Attribution block (see design doc for exact wording).

**Step 22.2: Commit.**

```bash
git add apps/metis-web/components/brand/dot-matrix/README.md
git commit -m "docs(quiet-loaders): authoring guide + vocabulary table + attribution"
```

---

### Task 23: Extend `components/brand/README.md`

**Files:**
- Modify: `apps/metis-web/components/brand/README.md`

**Step 23.1: Two edits.**

(a) **Decision-tree row.** In the "Adding a new surface → Pick the right primitive" subsection, after the "Loading indicator → `<MetisLoader>`" bullet, add:

> - Inline semantic state (chat thinking, technique-card compile, etc.) → `<DotMatrixLoader name="…">`. See [`dot-matrix/README.md`](./dot-matrix/README.md).

(b) **Divide paragraph.** In the introductory section (top of file, near the table that lists `<MetisMark>`/`<MetisGlow>`/`<MetisLockup>`/`<MetisLoader>`), add a new row for `<DotMatrixLoader>`:

| `<DotMatrixLoader>` | Inline semantic states (thinking / streaming / compiling / etc.). Sibling to `<MetisLoader>` — see `dot-matrix/README.md`. |

And add a paragraph below the table:

> `<MetisLoader>` is brand-forward — mark + sonar — for whole-surface loading. `<DotMatrixLoader>` is inline-semantic — dot grid + keyframe — for in-text states the brand mark would be too heavy for. Both are `currentColor`-themed; pick by surface size and whether the user should perceive *"the brand is here"* or *"this specific operation is in flight."*

**Step 23.2: Commit.**

```bash
git commit -m "docs(brand): document DotMatrixLoader vs MetisLoader divide"
```

---

### Task 24: Note in `docs/preserve-and-productize-plan.md`

**Files:**
- Modify: `docs/preserve-and-productize-plan.md`

**Step 24.1: Append under *Notes for the next agent*.**

Find the most recent dated entry under *Notes for the next agent* (likely "2026-05-01 — UI/UX skill-pass refinements" or similar). Add a new dated entry above or after it (per local convention):

> ### 2026-05-02 — Quiet loader pass
>
> Six-loader dot-matrix vocabulary at `components/brand/dot-matrix/*`, dispatcher at `components/brand/dot-matrix-loader.tsx`. Six surfaces migrated (chat thinking-bubble, chat send-button, Forge technique-card pending, companion-dock reflect-now + atlas-save, `app/loading.tsx` cyan-ring outlier). Other inline `Loader2` usage left as-is by design — only semantic surfaces migrate.
>
> Design: [`docs/plans/2026-05-02-quiet-loaders-design.md`](plans/2026-05-02-quiet-loaders-design.md). Plan: [`docs/plans/2026-05-02-quiet-loaders-implementation.md`](plans/2026-05-02-quiet-loaders-implementation.md).

**Step 24.2: Commit.**

```bash
git commit -m "docs(m01): note 2026-05-02 quiet-loader pass under preserve-and-productize"
```

**End of Phase 3.**

---

## Phase 4 — Tuning (deferred until feedback)

No actionable tasks until the PR opens and the project owner spot-checks. Likely follow-up areas:

- **`thinking`** — if the firing pattern reads as "twitchy," increase the per-cell fade duration from 400 ms → 500–600 ms or stretch the overall cycle.
- **`compile`** — if the column fill reads as "static," shorten `COL_STAGGER_MS` from 800 ms → 500 ms or shrink the overall cycle.
- **`stream`** — if the row-major march is too fast, increase `STAGGER_MS` from 60 ms → 80–100 ms.
- **`breath`** — easy to tune: just the cycle duration. 3000 ms is conservative; 2000 ms or 4000 ms are equally plausible.

Tuning is keyframe-only — no sub-component edits. Single-file commits per loader.

---

## Final sanity sweep (before opening PR)

### Task 25: Full test + build + visual sweep

**Step 25.1: Run all brand tests.**

```bash
pnpm test components/brand
```

Expected: all dot-matrix tests pass + existing brand tests pass. If any existing brand test fails, investigate (likely a snapshot or import-graph regression).

**Step 25.2: Run full build.**

```bash
pnpm build
```

Expected: build succeeds. Bundle delta should be small (~2 KB gzipped).

**Step 25.3: Walk all six migrated surfaces in `pnpm dev`.**

Surfaces to visit:

1. `/chat` — send a message, observe thinking-bubble (Task 16) + send-button (Task 17).
2. `/forge` — toggle a technique, observe technique-card pending chip (Task 18).
3. Open companion dock anywhere — click "Reflect now," observe (Task 19).
4. Companion dock → atlas, click "Save to Atlas," observe (Task 20).
5. Throttle network to slow-3G, hard-reload `/`, observe `app/loading.tsx` (Task 21).

If any surface looks off, **do not tune in this PR** — file a follow-up note in the PR description and let the project owner decide if it's a blocker.

**Step 25.4: PR description checklist.**

- Link to design doc.
- Screenshot per migrated surface (5 GIFs is overkill; static screenshots OK).
- Note: "Reduced-motion gate intentionally not implemented per design doc § Risks. `verify` and `halt` ship without consumers per design doc § Consumer migration plan."

---

## Skill references

- `@superpowers:executing-plans` — the umbrella skill for executing this plan task-by-task.
- `@superpowers:test-driven-development` — Phase 1 follows red-green-refactor on each loader.
- `@superpowers:verification-before-completion` — Phase 2 each task includes a typecheck + visual check before commit.

---

## Definition of done

- All six loaders ship with passing vitest contract tests.
- Six surfaces migrated.
- `dot-matrix/README.md` authored; `components/brand/README.md` extended; `docs/preserve-and-productize-plan.md` notes the pass.
- `pnpm build` succeeds.
- PR opened against `main` with screenshots of all six migrated surfaces.
- Tuning round (Phase 4) deferred until feedback.
