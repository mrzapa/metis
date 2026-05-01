# Comet Headline Labels — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Surface M13 news-comet headlines in the constellation via canvas-rendered ambient path-text labels (along comet tails) and a pinned canvas hover card (title/summary/faculty/source/age, click-to-open).

**Architecture:** Two new visual layers on top of the existing `drawCometSprites(ctx, cometSprites, ts)` call in `apps/metis-web/app/page.tsx`. Both consume `@chenglou/pretext` via the existing wrapper at `lib/pretext-labels.ts`. The wrapper gets one new export — `wrapText(text, font, maxWidth)` — which is the first consumer of pretext's line-breaking surface in METIS. No backend changes; `CometData` already carries `title`, `summary`, `url`, `tailHistory`, `color`, `phase`, `opacity`, `relevanceScore`.

**Tech Stack:** TypeScript, Next.js (`apps/metis-web`), Canvas 2D, `@chenglou/pretext@0.0.5`, Vitest, pnpm, Tauri webview as runtime target.

**Reference:**
- Design doc: [`docs/plans/2026-05-01-comet-headline-labels-design.md`](./2026-05-01-comet-headline-labels-design.md)
- Plan stub: [`plans/comet-headline-labels/plan.md`](../../plans/comet-headline-labels/plan.md)
- Milestone row: M22 in [`plans/IMPLEMENTATION.md`](../../plans/IMPLEMENTATION.md)
- Existing pretext wrapper: [`apps/metis-web/lib/pretext-labels.ts`](../../apps/metis-web/lib/pretext-labels.ts)
- Existing comet rendering: [`apps/metis-web/lib/constellation-comets.ts`](../../apps/metis-web/lib/constellation-comets.ts) → `drawComets`
- Existing comet types: [`apps/metis-web/lib/comet-types.ts`](../../apps/metis-web/lib/comet-types.ts) → `CometData`

**Conventions:**
- Branch: `claude/m22-phase-N-<short>` (e.g. `claude/m22-phase-1-tracer-pathtext`).
- Commits: `feat(m22): Phase N — <summary>` for code, `test(m22): ...` for test-only, `docs(m22): ...` for plan/doc updates. Each commit gets the standard `Co-Authored-By` trailer used in `git log`.
- One phase per PR. Land phase N before starting phase N+1. PR title `feat(m22): Phase N — <summary>`.
- Test runner: `pnpm exec vitest run <file>` (run from `apps/metis-web/`).
- Type check: `pnpm exec tsc --noEmit` (run from `apps/metis-web/`).
- Lint: `pnpm exec eslint <touched files>`.

**Pre-flight (before claiming):**
1. Verify the M22 row in [`plans/IMPLEMENTATION.md`](../../plans/IMPLEMENTATION.md) is `Status: Ready` or `Status: Draft needed`, `Claim` blank.
2. Re-read the design doc top-to-bottom. Particularly the *Risks* and *Phase boundaries* sections.
3. Spin up `pnpm install` and confirm `@chenglou/pretext@0.0.5` is in `apps/metis-web/node_modules`.

---

## Phase 1 — Tracer-bullet path-text (one comet, no mitigations)

**Goal:** A single comet renders its raw `title` (no truncation) along its full visible tail, with per-character position from arc-length walk and per-character rotation from raw spline tangent. No smoothing, no orientation flip, no collision suppression, no truncation, no faculty tint, no reduced-motion handling. Just *does the spline math work*.

**Why first:** The path-text math is the highest-risk piece. Getting it visibly correct on `main` early de-risks every other phase.

**Branch:** `claude/m22-phase-1-tracer-pathtext` (off `main`).

### Task 1.0: Claim the milestone

**Files:**
- Modify: `plans/IMPLEMENTATION.md` (M22 row — set `Claim` to your branch name, `Last updated` to today)
- Modify: `plans/comet-headline-labels/plan.md` (set `Status: In progress`, fill `Claim`, append to `Progress`)

**Step 1: Edit the M22 row**

Set `Claim` to `claude/m22-phase-1-tracer-pathtext` and `Last updated` to today's date.

**Step 2: Edit the plan stub frontmatter**

```yaml
Status: In progress
Claim: claude/m22-phase-1-tracer-pathtext
Last updated: YYYY-MM-DD by <agent>
```

**Step 3: Commit (standalone)**

```bash
git checkout -b claude/m22-phase-1-tracer-pathtext
git add plans/IMPLEMENTATION.md plans/comet-headline-labels/plan.md
git commit -m "docs(m22): claim Phase 1 — tracer-bullet path-text"
git push -u origin claude/m22-phase-1-tracer-pathtext
```

---

### Task 1.1: Stub `lib/constellation-comet-labels.ts` + first test for `computeArcLengths`

**Files:**
- Create: `apps/metis-web/lib/constellation-comet-labels.ts`
- Create: `apps/metis-web/lib/__tests__/constellation-comet-labels.test.ts`

**Step 1: Write the failing test**

```ts
// apps/metis-web/lib/__tests__/constellation-comet-labels.test.ts
import { describe, expect, it } from "vitest";
import { computeArcLengths } from "../constellation-comet-labels";

describe("computeArcLengths", () => {
  it("returns cumulative arc length from head back along tail history", () => {
    // Tail goes head=(0,0) → (3,0) → (3,4) — straight 3px then perpendicular 4px.
    const tail = [
      { x: 0, y: 0 },
      { x: 3, y: 0 },
      { x: 3, y: 4 },
    ];
    expect(computeArcLengths(tail)).toEqual([0, 3, 7]);
  });

  it("returns [0] for a single-point tail", () => {
    expect(computeArcLengths([{ x: 1, y: 2 }])).toEqual([0]);
  });

  it("returns [] for empty tail", () => {
    expect(computeArcLengths([])).toEqual([]);
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd apps/metis-web && pnpm exec vitest run lib/__tests__/constellation-comet-labels.test.ts
```

Expected: FAIL with `Cannot find module '../constellation-comet-labels'`.

**Step 3: Write minimal implementation**

```ts
// apps/metis-web/lib/constellation-comet-labels.ts
"use client";

export interface TailPoint {
  x: number;
  y: number;
}

/**
 * Cumulative arc length along the tail-history polyline, indexed
 * from the head outward (index 0 = at head, index N-1 = at tail end).
 */
export function computeArcLengths(tail: ReadonlyArray<TailPoint>): number[] {
  if (tail.length === 0) return [];
  const out = [0];
  for (let i = 1; i < tail.length; i += 1) {
    const dx = tail[i].x - tail[i - 1].x;
    const dy = tail[i].y - tail[i - 1].y;
    out.push(out[i - 1] + Math.hypot(dx, dy));
  }
  return out;
}
```

**Step 4: Run test to verify it passes**

```bash
pnpm exec vitest run lib/__tests__/constellation-comet-labels.test.ts
```

Expected: PASS, 3/3.

**Step 5: Commit**

```bash
git add apps/metis-web/lib/constellation-comet-labels.ts apps/metis-web/lib/__tests__/constellation-comet-labels.test.ts
git commit -m "test(m22): Phase 1 — computeArcLengths over tail history"
```

---

### Task 1.2: `samplePathAt(arcLengths, tail, s)` — interpolate a position at arc-length `s`

**Files:**
- Modify: `apps/metis-web/lib/constellation-comet-labels.ts`
- Modify: `apps/metis-web/lib/__tests__/constellation-comet-labels.test.ts`

**Step 1: Write the failing test**

```ts
import { computeArcLengths, samplePathAt } from "../constellation-comet-labels";

describe("samplePathAt", () => {
  const tail = [
    { x: 0, y: 0 },
    { x: 10, y: 0 },
    { x: 10, y: 10 },
  ];
  const arc = computeArcLengths(tail); // [0, 10, 20]

  it("returns head position at s=0", () => {
    expect(samplePathAt(arc, tail, 0)).toEqual({ x: 0, y: 0, tangent: 0 });
  });

  it("interpolates linearly between samples", () => {
    // s=5 is halfway between (0,0) and (10,0); tangent points along +x (0 rad).
    expect(samplePathAt(arc, tail, 5)).toEqual({ x: 5, y: 0, tangent: 0 });
  });

  it("handles segment boundary — picks the segment containing s", () => {
    // s=15 is halfway along the second segment, going +y (π/2 rad).
    const r = samplePathAt(arc, tail, 15);
    expect(r.x).toBeCloseTo(10);
    expect(r.y).toBeCloseTo(5);
    expect(r.tangent).toBeCloseTo(Math.PI / 2);
  });

  it("clamps to tail end if s exceeds total arc length", () => {
    const r = samplePathAt(arc, tail, 999);
    expect(r.x).toBe(10);
    expect(r.y).toBe(10);
    expect(r.tangent).toBeCloseTo(Math.PI / 2);
  });
});
```

**Step 2: Run — expect FAIL** (`samplePathAt is not a function`).

**Step 3: Implement**

```ts
export interface PathSample {
  x: number;
  y: number;
  /** Tangent angle in radians, measured from +x axis. */
  tangent: number;
}

export function samplePathAt(
  arcLengths: ReadonlyArray<number>,
  tail: ReadonlyArray<TailPoint>,
  s: number,
): PathSample {
  if (tail.length === 0) return { x: 0, y: 0, tangent: 0 };
  if (tail.length === 1) return { x: tail[0].x, y: tail[0].y, tangent: 0 };

  // Find the segment [i, i+1] such that arcLengths[i] ≤ s ≤ arcLengths[i+1].
  let i = 0;
  for (let k = 0; k < arcLengths.length - 1; k += 1) {
    if (s >= arcLengths[k] && s <= arcLengths[k + 1]) {
      i = k;
      break;
    }
    if (k === arcLengths.length - 2) i = k; // clamp to last segment
  }

  const segLen = arcLengths[i + 1] - arcLengths[i];
  const t = segLen === 0 ? 0 : Math.min(1, Math.max(0, (s - arcLengths[i]) / segLen));
  const dx = tail[i + 1].x - tail[i].x;
  const dy = tail[i + 1].y - tail[i].y;
  return {
    x: tail[i].x + dx * t,
    y: tail[i].y + dy * t,
    tangent: Math.atan2(dy, dx),
  };
}
```

**Step 4: Run — expect PASS, 4/4.**

**Step 5: Commit**

```bash
git add apps/metis-web/lib/constellation-comet-labels.ts apps/metis-web/lib/__tests__/constellation-comet-labels.test.ts
git commit -m "test(m22): Phase 1 — samplePathAt interpolation"
```

---

### Task 1.3: `placeCharactersAlongPath(label, font, tail, opts)` — list of `{char, x, y, tangent}`

**Files:** same two as above.

**Step 1: Write the failing test**

```ts
import { placeCharactersAlongPath } from "../constellation-comet-labels";

describe("placeCharactersAlongPath", () => {
  const tail = [
    { x: 0, y: 0 },
    { x: 200, y: 0 }, // 200px straight line, plenty of arc length
  ];
  const font = '400 11px "Space Grotesk", sans-serif';

  it("places one entry per character", () => {
    const placed = placeCharactersAlongPath("ABC", font, tail);
    expect(placed).toHaveLength(3);
  });

  it("first character is roughly at the head", () => {
    const placed = placeCharactersAlongPath("ABC", font, tail);
    expect(placed[0].x).toBeLessThan(15); // first char near head
    expect(placed[0].y).toBe(0);
    expect(placed[0].tangent).toBeCloseTo(0, 2);
  });

  it("characters advance along +x along a straight horizontal tail", () => {
    const placed = placeCharactersAlongPath("ABC", font, tail);
    expect(placed[1].x).toBeGreaterThan(placed[0].x);
    expect(placed[2].x).toBeGreaterThan(placed[1].x);
    expect(placed[0].y).toBe(0);
    expect(placed[1].y).toBe(0);
    expect(placed[2].y).toBe(0);
  });

  it("returns empty array if tail too short to fit any character", () => {
    const tinyTail = [{ x: 0, y: 0 }, { x: 1, y: 0 }];
    const placed = placeCharactersAlongPath("Hello", font, tinyTail);
    expect(placed.length).toBeLessThanOrEqual(1);
  });
});
```

**Step 2: Run — expect FAIL** (`placeCharactersAlongPath is not a function`).

**Step 3: Implement**

```ts
import { measureSingleLineTextWidth } from "./pretext-labels";

export interface PlacedChar {
  char: string;
  x: number;
  y: number;
  /** Tangent angle in radians at this character's center. */
  tangent: number;
}

/**
 * Place each character of `label` along the tail polyline, starting from
 * the head and walking outward. Skips characters that don't fit in the
 * available arc length (Phase 1: just stops; Phase 2 adds an ellipsis).
 *
 * NOTE: Phase 1 uses raw per-character tangent. Phase 2 will replace this
 * with a Catmull-Rom-smoothed spline.
 */
export function placeCharactersAlongPath(
  label: string,
  font: string,
  tail: ReadonlyArray<TailPoint>,
): PlacedChar[] {
  if (tail.length < 2 || label.length === 0) return [];
  const arcLengths = computeArcLengths(tail);
  const total = arcLengths[arcLengths.length - 1];

  const out: PlacedChar[] = [];
  let s = 0; // arc-length cursor from head outward
  for (const ch of label) {
    const w = measureSingleLineTextWidth(ch, font);
    const center = s + w / 2;
    if (center > total) break;
    const sample = samplePathAt(arcLengths, tail, center);
    out.push({ char: ch, x: sample.x, y: sample.y, tangent: sample.tangent });
    s += w;
  }
  return out;
}
```

**Step 4: Run — expect PASS, 4/4.**

**Step 5: Commit**

```bash
git add apps/metis-web/lib/constellation-comet-labels.ts apps/metis-web/lib/__tests__/constellation-comet-labels.test.ts
git commit -m "test(m22): Phase 1 — placeCharactersAlongPath layout"
```

---

### Task 1.4: `drawCometLabel(ctx, comet, ts, opts)` — minimum render

**Files:**
- Modify: `apps/metis-web/lib/constellation-comet-labels.ts`

**Step 1: Add export and implement**

```ts
import type { CometData } from "./comet-types";
import { buildCanvasFont } from "./pretext-labels";

const LABEL_FONT_FAMILY = '"Space Grotesk", -apple-system, "Segoe UI", sans-serif';
const LABEL_FONT_SIZE = 11;
const LABEL_FONT_WEIGHT = 400;

export interface DrawCometLabelOpts {
  /** ts ignored in Phase 1 (no fade animations yet). */
  ts?: number;
}

export function drawCometLabel(
  ctx: CanvasRenderingContext2D,
  comet: CometData,
  _opts: DrawCometLabelOpts = {},
): void {
  const tail = comet.tailHistory;
  if (tail.length < 2) return;

  // Phase 1: full title, no truncation. Tail history starts at the head.
  // Order matches placeCharactersAlongPath's expectation (head first).
  const font = buildCanvasFont(LABEL_FONT_SIZE, LABEL_FONT_FAMILY, LABEL_FONT_WEIGHT);
  const placed = placeCharactersAlongPath(comet.title, font, tail);
  if (placed.length === 0) return;

  const [r, g, b] = comet.color;
  ctx.save();
  ctx.font = font;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${0.65 * comet.opacity})`;
  for (const p of placed) {
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(p.tangent);
    ctx.fillText(p.char, 0, 0);
    ctx.restore();
  }
  ctx.restore();
}
```

**Step 2: Smoke-test the function does not throw under jsdom**

Append to test file:

```ts
import { drawCometLabel } from "../constellation-comet-labels";
import type { CometData } from "../comet-types";

it("drawCometLabel does not throw with a real-shaped comet", () => {
  const c: CometData = {
    comet_id: "test",
    x: 100, y: 100, vx: 1, vy: 0,
    tailHistory: [{ x: 100, y: 100 }, { x: 80, y: 100 }, { x: 60, y: 100 }, { x: 40, y: 100 }],
    color: [120, 200, 255],
    facultyId: "perception",
    targetX: 0, targetY: 0,
    phase: "drifting",
    phaseStartedAt: 0,
    size: 4, opacity: 1,
    title: "Hello world", summary: "", url: "",
    decision: "drift", relevanceScore: 0.5,
  };
  // jsdom has a noop canvas context; just verify no throw.
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    // jsdom env without canvas package — skip this assertion
    return;
  }
  expect(() => drawCometLabel(ctx, c)).not.toThrow();
});
```

**Step 3: Run — expect PASS.**

**Step 4: Commit**

```bash
git add apps/metis-web/lib/constellation-comet-labels.ts apps/metis-web/lib/__tests__/constellation-comet-labels.test.ts
git commit -m "feat(m22): Phase 1 — drawCometLabel with raw per-char path-text"
```

---

### Task 1.5: Wire into `app/page.tsx` after `drawCometSprites`

**Files:**
- Modify: `apps/metis-web/app/page.tsx` (around line 4734, after the existing `drawCometSprites(ctx, cometSprites, ts)` call)

**Step 1: Add the import**

Find the existing pretext-labels import block (around line 134-138) and add an adjacent line for the new module:

```tsx
import { drawCometLabel } from "@/lib/constellation-comet-labels";
```

**Step 2: Add the per-frame call**

Locate the existing line `drawCometSprites(ctx, cometSprites, ts);`. Immediately after it:

```tsx
        drawCometSprites(ctx, cometSprites, ts);
        for (const comet of cometSprites) {
          drawCometLabel(ctx, comet);
        }
```

**Step 3: Type check**

```bash
cd apps/metis-web && pnpm exec tsc --noEmit
```

Expected: no new errors. (Pre-existing M20 sigil-test error remains; ignore.)

**Step 4: Live preview verification**

Start the preview server and stream comets. Eyeball the home page for ~30 seconds and confirm:

- Each visible comet has letters along its tail (raw, no smoothing — they may shimmer; this is expected for Phase 1).
- The text is dim, faculty-coloured, no backdrop.
- Comets without yet-formed tails show partial labels (only the prefix that fits).

If the preview returns no comets within ~30s, the news-comet API may not be running locally. Diagnose by hitting `/v1/comets/active` directly. **Don't fake comet data**; if the API is offline, document and stop here.

**Step 5: Commit**

```bash
git add apps/metis-web/app/page.tsx
git commit -m "feat(m22): Phase 1 — wire drawCometLabel into render loop"
```

---

### Task 1.6: Open Phase 1 PR

**Step 1: Push and open PR**

```bash
git push
gh pr create --title "feat(m22): Phase 1 — tracer-bullet path-text labels on comets" --body "$(cat <<'EOF'
## Summary
First slice of M22 — comets carry raw per-character path-text labels along their tails.

## What's in this PR
- New `lib/constellation-comet-labels.ts` with `computeArcLengths`, `samplePathAt`, `placeCharactersAlongPath`, `drawCometLabel`.
- Wired into `app/page.tsx` after the existing `drawCometSprites` call.
- Vitest suite covering arc-length walk, path sampling, character placement, and a smoke test of the integrated draw.

## What's NOT in this PR (deferred to later phases)
- **Phase 2:** Catmull-Rom tangent smoothing, orientation flip, truncation budget, reduced-motion clamp, faculty-tinted opacity polish.
- **Phase 3:** `wrapText` helper in `pretext-labels.ts`, hover detection, canvas hover card, click-to-open.
- **Phase 4:** Collision suppression by relevance score.
- **Phase 5:** Final QA + polish.

## Verification
- `pnpm exec vitest run lib/__tests__/constellation-comet-labels.test.ts` — passes.
- `pnpm exec tsc --noEmit` — no new errors.
- Live preview at `/` — labels render along comet tails. Shimmer at high tail curvature is expected and is fixed in Phase 2.

## Refs
- Design: [`docs/plans/2026-05-01-comet-headline-labels-design.md`](docs/plans/2026-05-01-comet-headline-labels-design.md)
- Plan: [`docs/plans/2026-05-01-comet-headline-labels-implementation.md`](docs/plans/2026-05-01-comet-headline-labels-implementation.md)
- Milestone: M22 in [`plans/IMPLEMENTATION.md`](plans/IMPLEMENTATION.md)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 2: Stop. Wait for review.** Do not start Phase 2 until Phase 1 lands on `main`.

---

## Phase 2 — Mitigations

**Goal:** Smoothed tangents + orientation flip with hysteresis + 18-char truncation budget honouring arc length + reduced-motion ±10° clamp + faculty-color opacity polish.

**Why second:** Phase 1 ships visibly-correct-but-rough; Phase 2 makes it look right.

**Branch:** `claude/m22-phase-2-mitigations` (off `main`, after Phase 1 lands).

**Pre-flight:** Update the M22 row's `Claim` to the new branch.

### Task 2.1: Catmull-Rom smoothed tangent

**Files:** `apps/metis-web/lib/constellation-comet-labels.ts` + its test file.

**Step 1: Write the failing test**

```ts
describe("smoothedTangentAt", () => {
  it("returns the same tangent as raw on a straight line", () => {
    const tail = [
      { x: 0, y: 0 }, { x: 10, y: 0 }, { x: 20, y: 0 }, { x: 30, y: 0 },
    ];
    const arc = computeArcLengths(tail);
    expect(smoothedTangentAt(arc, tail, 15)).toBeCloseTo(0, 3);
  });

  it("smooths a sharp corner — tangent at the elbow is between the two segment angles", () => {
    // Right-angle elbow: x then y. Raw tangent at the elbow jumps from 0 to π/2.
    // Smoothed should land between, around π/4.
    const tail = [
      { x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 10, y: 20 },
    ];
    const arc = computeArcLengths(tail);
    const smoothed = smoothedTangentAt(arc, tail, 10); // at the elbow
    expect(smoothed).toBeGreaterThan(0);
    expect(smoothed).toBeLessThan(Math.PI / 2);
  });
});
```

**Step 2: Run — FAIL.**

**Step 3: Implement**

Use a Catmull-Rom spline through the tail points; sample tangent at arc-length `s` by finite-differencing the spline at `s ± epsilon`. Reuse `samplePathAt` to find the segment, then look up the spline-tangent for that local parameterization.

(Implementation sketch — keep it short. ~30 LOC. Reference: `https://en.wikipedia.org/wiki/Centripetal_Catmull%E2%80%93Rom_spline` if needed; no external dep.)

**Step 4: Run — PASS, 2/2.**

**Step 5: Commit** `test(m22): Phase 2 — smoothedTangentAt via Catmull-Rom`.

### Task 2.2: Replace raw tangent in `placeCharactersAlongPath`

Replace the call to `samplePathAt(...).tangent` with `smoothedTangentAt(...)`. Add temporal smoothing (rolling 3-frame average per `comet_id`) — keep a `Map<string, number[]>` module-level state, push current tangent, average. Add a test for the temporal smoothing call shape (mock the rolling buffer).

Commit: `feat(m22): Phase 2 — smoothed per-char tangent + temporal lowpass`.

### Task 2.3: Orientation flip with hysteresis

**Step 1: Test**

```ts
describe("shouldFlipOrientation", () => {
  // Hysteresis: flip when crossing 95°, unflip when crossing 90°.
  it("does not flip below threshold", () => {
    expect(shouldFlipOrientation(Math.PI / 2 - 0.1, false)).toBe(false);
  });
  it("flips above 95°", () => {
    expect(shouldFlipOrientation((95 * Math.PI) / 180 + 0.01, false)).toBe(true);
  });
  it("once flipped, stays flipped above 90°", () => {
    expect(shouldFlipOrientation((92 * Math.PI) / 180, true)).toBe(true);
  });
  it("once flipped, unflips below 90°", () => {
    expect(shouldFlipOrientation((89 * Math.PI) / 180, true)).toBe(false);
  });
});
```

**Step 2-4:** Implement, run, expect PASS.

**Step 5:** Wire flipped tangent into `placeCharactersAlongPath` (rotate label baseline by π when `flipped === true`). Track flip state per `comet_id` in a module-level `Map<string, boolean>`.

Commit: `feat(m22): Phase 2 — orientation flip with hysteresis`.

### Task 2.4: 18-char truncation + ellipsis honouring arc length

**Step 1: Test**

```ts
describe("truncateLabelToFit", () => {
  it("returns the full string if it fits", () => {
    expect(truncateLabelToFit("Hi", 11, 200)).toBe("Hi");
  });
  it("hard-caps at 18 chars + ellipsis", () => {
    const out = truncateLabelToFit("This is a much longer headline than 18 chars", 11, 200);
    expect(out.length).toBeLessThanOrEqual(19); // 18 + ellipsis char
    expect(out.endsWith("…")).toBe(true);
  });
  it("further truncates if available arc length is short", () => {
    expect(truncateLabelToFit("Hello world", 11, 20)).toMatch(/^H[…]?$/); // tiny budget
  });
  it("returns empty string when no character fits", () => {
    expect(truncateLabelToFit("Hello", 11, 1)).toBe("");
  });
});
```

**Step 2-4:** Implement using `measureSingleLineTextWidth` to walk character widths until budget exhausts.

**Step 5:** Wire into `drawCometLabel` so it calls `truncateLabelToFit(comet.title, fontSize, totalArcLength)` before placing characters.

Commit: `feat(m22): Phase 2 — truncation budget honouring arc length`.

### Task 2.5: Reduced-motion ±10° tangent clamp

**Step 1: Test**

```ts
describe("clampTangentForReducedMotion", () => {
  it("does not clamp when reducedMotion=false", () => {
    expect(clampTangentForReducedMotion(Math.PI / 3, false)).toBeCloseTo(Math.PI / 3);
  });
  it("clamps to ±10° (≈0.1745 rad) when reducedMotion=true", () => {
    expect(clampTangentForReducedMotion(Math.PI / 2, true)).toBeCloseTo(0.1745, 3);
    expect(clampTangentForReducedMotion(-Math.PI / 2, true)).toBeCloseTo(-0.1745, 3);
  });
  it("preserves small tangents under reducedMotion", () => {
    expect(clampTangentForReducedMotion(0.1, true)).toBeCloseTo(0.1);
  });
});
```

**Step 2-4:** Implement (one-liner: `Math.max(-MAX, Math.min(MAX, t))` where `MAX = (10 * Math.PI) / 180`).

**Step 5:** Plumb a `reducedMotion: boolean` opt through `DrawCometLabelOpts` and respect in the per-char tangent step. Read from `useReducedMotion` (motion/react) in `app/page.tsx` and pass through.

Commit: `feat(m22): Phase 2 — reduced-motion ±10° tangent clamp`.

### Task 2.6: Phase 2 verification + PR

**Step 1: Live preview verification**

- Watch comets for ~60s. Confirm labels do NOT shimmer at corners (smoothed).
- Spot a comet diving down-and-left. Confirm orientation flips cleanly (no flicker).
- Long headlines visibly truncate to ~18 chars + ellipsis.
- DevTools `prefers-reduced-motion: reduce` → labels still draw, but rotation is gentle (≤10°).

**Step 2: Run full test + typecheck**

```bash
cd apps/metis-web && pnpm exec vitest run && pnpm exec tsc --noEmit
```

**Step 3: PR**

`feat(m22): Phase 2 — path-text mitigations (smoothing, flip, truncation, reduced-motion)`. Stop. Wait for merge.

---

## Phase 3 — Hover card + click

**Goal:** `wrapText` shipped in `pretext-labels.ts` + hover hit-test + canvas hover card + `clampToSafeArea` + click handler.

**Branch:** `claude/m22-phase-3-hover-card`.

### Task 3.1: `wrapText` in `lib/pretext-labels.ts`

**Files:**
- Modify: `apps/metis-web/lib/pretext-labels.ts`
- Create: `apps/metis-web/lib/__tests__/pretext-labels.test.ts`

**Step 1: Write the failing test**

```ts
import { describe, expect, it } from "vitest";
import { wrapText, buildCanvasFont } from "../pretext-labels";

describe("wrapText", () => {
  const font = buildCanvasFont(13, '"Space Grotesk"', 600);

  it("returns the original string as one line if it fits", () => {
    const lines = wrapText("Short", font, 1000);
    expect(lines.length).toBe(1);
    expect(lines[0].text).toBe("Short");
  });

  it("wraps a long string at the max width", () => {
    const lines = wrapText("AnthropicAI: Sonnet 4.7 release with extended context window", font, 196);
    expect(lines.length).toBeGreaterThan(1);
    for (const l of lines) {
      expect(l.width).toBeLessThanOrEqual(196);
    }
  });

  it("returns empty array on empty input", () => {
    expect(wrapText("", font, 100)).toEqual([]);
  });

  it("caches identical calls (second call does not re-invoke pretext)", () => {
    // (Implementation note: spy on prepareWithSegments via vi.mock if needed; otherwise
    // prove cache via direct identity check on returned array.)
    const a = wrapText("Headline text here", font, 100);
    const b = wrapText("Headline text here", font, 100);
    expect(a).toBe(b); // referential equality from cache
  });
});
```

**Step 2: Run — FAIL.**

**Step 3: Implement**

```ts
// in lib/pretext-labels.ts, alongside existing exports:
import { walkLineRanges } from "@chenglou/pretext";
// `prepareWithSegments` is already imported

export interface WrappedLine {
  text: string;
  width: number;
}

const wrapTextCache = new Map<string, WrappedLine[]>();

export function wrapText(text: string, font: string, maxWidth: number): WrappedLine[] {
  if (text.length === 0) return [];
  const key = `${font}::${maxWidth}::${text}`;
  const cached = wrapTextCache.get(key);
  if (cached) return cached;

  let lines: WrappedLine[];
  try {
    const prepared = prepareWithSegments(text, font);
    const out: WrappedLine[] = [];
    walkLineRanges(prepared, maxWidth, (line) => {
      out.push({ text: text.slice(line.start, line.end), width: line.width });
    });
    lines = out;
  } catch {
    lines = wrapTextWordBoundaryFallback(text, font, maxWidth);
  }
  wrapTextCache.set(key, lines);
  return lines;
}

function wrapTextWordBoundaryFallback(text: string, font: string, maxWidth: number): WrappedLine[] {
  const words = text.split(/\s+/);
  const out: WrappedLine[] = [];
  let curr = "";
  for (const w of words) {
    const trial = curr ? `${curr} ${w}` : w;
    const trialW = measureSingleLineTextWidth(trial, font);
    if (trialW <= maxWidth) {
      curr = trial;
    } else {
      if (curr) out.push({ text: curr, width: measureSingleLineTextWidth(curr, font) });
      curr = w;
    }
  }
  if (curr) out.push({ text: curr, width: measureSingleLineTextWidth(curr, font) });
  return out;
}
```

**Step 4: PASS.**

**Step 5:** Commit `test(m22): Phase 3 — wrapText with cache + word-boundary fallback`.

### Task 3.2: Hover hit-test (`findHoveredComet`)

**Step 1: Test**

```ts
describe("findHoveredComet", () => {
  it("returns nearest comet within 24px", () => {
    const comets = [
      { ...mkComet("a"), x: 100, y: 100 },
      { ...mkComet("b"), x: 200, y: 200 },
    ];
    expect(findHoveredComet(comets, { x: 110, y: 105 })?.comet_id).toBe("a");
    expect(findHoveredComet(comets, { x: 200, y: 220 })?.comet_id).toBe("b");
  });
  it("returns null beyond 24px", () => {
    const comets = [{ ...mkComet("a"), x: 0, y: 0 }];
    expect(findHoveredComet(comets, { x: 50, y: 50 })).toBeNull();
  });
});
```

(`mkComet` is a tiny test helper that returns a default-shaped CometData with the listed fields overridable.)

**Step 2-4:** Implement linear scan with `Math.hypot(dx, dy) < 24`.

**Step 5:** Commit `test(m22): Phase 3 — findHoveredComet hit-test`.

### Task 3.3: `drawCometHoverCard(ctx, comet, anchor, opts)`

**Step 1: Test (rendering smoke + layout invariants)**

```ts
describe("drawCometHoverCard", () => {
  it("does not throw with a real-shaped comet", () => {
    const c = mkComet("x", { title: "Test", summary: "A summary." });
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    expect(() => drawCometHoverCard(ctx, c, { x: 100, y: 100 }, { viewport: { w: 1000, h: 800 } })).not.toThrow();
  });

  it("returns a card bbox for the caller to use for click hit-test", () => {
    const c = mkComet("x", { title: "Test" });
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const bbox = drawCometHoverCard(ctx, c, { x: 100, y: 100 }, { viewport: { w: 1000, h: 800 } });
    expect(bbox).toMatchObject({ x: expect.any(Number), y: expect.any(Number), w: 220, h: expect.any(Number) });
  });
});
```

**Step 2-4:** Implement card layout per the design doc § Hover card. Use `wrapText` for title (max 2 lines, max 196px wide) and summary (max 4 lines, max 196px wide). Faculty short codes — pull from a small inline lookup keyed on `comet.facultyId`.

**Step 5:** Commit `feat(m22): Phase 3 — drawCometHoverCard layout via wrapText`.

### Task 3.4: `clampToSafeArea(rect, viewport, fixedRects)`

**Step 1: Test**

```ts
describe("clampToSafeArea", () => {
  const vp = { w: 1000, h: 800 };
  it("nudges card left if it overflows the right edge", () => {
    const r = clampToSafeArea({ x: 950, y: 100, w: 220, h: 120 }, vp, []);
    expect(r.x + r.w).toBeLessThanOrEqual(vp.w - 16);
  });
  it("nudges card up if it overflows the bottom edge", () => {
    const r = clampToSafeArea({ x: 100, y: 750, w: 220, h: 120 }, vp, []);
    expect(r.y + r.h).toBeLessThanOrEqual(vp.h - 16);
  });
  it("nudges card to avoid a fixed UI rect (zoom pill at bottom)", () => {
    const fixedRects = [{ x: 290, y: 700, w: 420, h: 60 }];
    const r = clampToSafeArea({ x: 300, y: 680, w: 220, h: 120 }, vp, fixedRects);
    // The card must not overlap the zoom pill rect.
    expect(rectsOverlap(r, fixedRects[0])).toBe(false);
  });
});
```

**Step 2-4:** Implement clamp-then-iterative-nudge. `rectsOverlap` is a small AABB helper exported alongside.

**Step 5:** Commit `test(m22): Phase 3 — clampToSafeArea against viewport + fixed UI`.

### Task 3.5: Wire hover state + card + click into `app/page.tsx`

**Files:**
- Modify: `apps/metis-web/app/page.tsx`

**Step 1:** Add a `cometHoverStateRef` (useRef) tracking `{ cometId: string | null, anchor: {x,y} | null, lastSeenAt: number, cardBbox: Rect | null }`.

**Step 2:** In the existing mousemove handler on the canvas, compute `findHoveredComet(cometSprites, cursor)` and update the ref. Note `cursor` is screen-relative; comets are also screen-space so no transform needed.

**Step 3:** In the per-frame draw loop, after the per-comet `drawCometLabel` calls, if `cometHoverStateRef.current.cometId` matches a live comet, call `drawCometHoverCard(ctx, hovered, anchor, { viewport, fixedRects: METIS_FIXED_UI_RECTS, reducedMotion })`. Save the returned `cardBbox` back to the ref.

**Step 4:** Add a click handler on the canvas: if `(e.x, e.y)` is within 16px of any comet head OR inside the saved `cardBbox`, `window.open(comet.url, "_blank", "noopener,noreferrer")`.

**Step 5:** `METIS_FIXED_UI_RECTS` — define near the top of `page.tsx` as a function `getFixedUiRects(viewport)` returning the bounding rects of the zoom-pill, hero overlay, and FAB. Use `getBoundingClientRect()` on those existing DOM elements (lookup by stable className) once per frame.

**Step 6:** Type check + visual preview: hover a comet, see card; click card, article opens; comet absorbs, card disappears. Commit.

`feat(m22): Phase 3 — wire hover card, hit-test, and click-to-open`.

### Task 3.6: Phase 3 PR

Open PR `feat(m22): Phase 3 — canvas hover card + click-to-open + wrapText helper`. Stop. Wait for merge.

---

## Phase 4 — Collision suppression

**Goal:** Multi-comet scenes don't overlap labels.

**Branch:** `claude/m22-phase-4-collision`.

### Task 4.1: Compute rotated AABB for a placed label

**Files:** `lib/constellation-comet-labels.ts` + tests.

**Step 1: Test**

```ts
describe("rotatedLabelBbox", () => {
  it("returns the AABB of a horizontal label", () => {
    const placed = [
      { char: "A", x: 0, y: 0, tangent: 0 },
      { char: "B", x: 10, y: 0, tangent: 0 },
    ];
    const bbox = rotatedLabelBbox(placed, 11);
    expect(bbox.x).toBeLessThanOrEqual(0);
    expect(bbox.y).toBeLessThanOrEqual(-5.5);
    expect(bbox.w).toBeGreaterThanOrEqual(10);
    expect(bbox.h).toBeGreaterThanOrEqual(11);
  });
  it("expands the AABB to cover a rotated diagonal label", () => {
    const placed = [
      { char: "A", x: 0, y: 0, tangent: Math.PI / 4 },
      { char: "B", x: 10, y: 10, tangent: Math.PI / 4 },
    ];
    const bbox = rotatedLabelBbox(placed, 11);
    expect(bbox.w).toBeGreaterThan(10); // diagonal extent
    expect(bbox.h).toBeGreaterThan(10);
  });
});
```

**Step 2-4:** Implement: for each placed char, compute its 4 rotated corners, then min/max over all corners.

**Step 5:** Commit.

### Task 4.2: `suppressCollidingLabels(labels, threshold=0.4)`

**Step 1: Test**

```ts
describe("suppressCollidingLabels", () => {
  it("keeps both when no overlap", () => {
    const a = { id: "a", relevance: 0.8, bbox: { x: 0, y: 0, w: 50, h: 11 } };
    const b = { id: "b", relevance: 0.5, bbox: { x: 100, y: 100, w: 50, h: 11 } };
    expect(suppressCollidingLabels([a, b]).map(l => l.id)).toEqual(["a", "b"]);
  });
  it("suppresses lower-relevance when overlap > 40%", () => {
    const a = { id: "high", relevance: 0.9, bbox: { x: 0, y: 0, w: 50, h: 11 } };
    const b = { id: "low", relevance: 0.3, bbox: { x: 25, y: 0, w: 50, h: 11 } };
    expect(suppressCollidingLabels([a, b]).map(l => l.id)).toEqual(["high"]);
  });
  it("does NOT suppress when overlap ≤ 40%", () => {
    const a = { id: "high", relevance: 0.9, bbox: { x: 0, y: 0, w: 50, h: 11 } };
    const b = { id: "low", relevance: 0.3, bbox: { x: 45, y: 0, w: 50, h: 11 } };
    expect(suppressCollidingLabels([a, b]).map(l => l.id).sort()).toEqual(["high", "low"]);
  });
});
```

**Step 2-4:** Implement: sort by relevance desc; iterate; for each, AABB-overlap check against already-kept; keep if overlap ratio ≤ threshold.

**Step 5:** Commit.

### Task 4.3: Wire suppression into the per-frame loop

**Files:** `app/page.tsx` and `lib/constellation-comet-labels.ts`.

**Step 1:** Refactor `drawCometLabel` to return its placed-chars + bbox without drawing, then split into `prepareCometLabel` (returns layout) and `drawPreparedLabel` (renders). Existing `drawCometLabel` becomes a convenience wrapper that calls both.

**Step 2:** In `page.tsx`'s frame loop, replace the simple `for (comet) drawCometLabel(...)` with: prepare all labels → suppress → draw the survivors.

**Step 3:** Live preview: spawn many comets (lower the relevance threshold or wait), confirm labels don't overlap visibly.

**Step 4:** Commit.

### Task 4.4: Phase 4 PR

`feat(m22): Phase 4 — collision suppression by relevance score`. Stop.

---

## Phase 5 — Polish + final QA + PR landing

**Goal:** Everything works end-to-end. Run all the design doc's verification scenarios. Tighten any rough edges.

**Branch:** `claude/m22-phase-5-polish`.

### Task 5.1: Full preview QA pass

Run every scenario from the design doc § Live preview verification:

- [ ] Comets stream over ~60s; ambient labels appear along trails.
- [ ] Hover a comet → card appears 16px to the right, faculty pill, title, summary, footer.
- [ ] Click card → article opens in new tab.
- [ ] Click comet head directly → same.
- [ ] `cometsEnabled = false` → labels disappear.
- [ ] DevTools `prefers-reduced-motion: reduce` → labels still draw, gentle rotation.
- [ ] Comet diving down-and-left → orientation flip kicks in around 95°, no flicker.
- [ ] Multi-comet scene → no label overlaps.
- [ ] Card never overlaps the zoom-pill, hero overlay, FAB, or top-bar.

For each failing scenario, file an issue and fix. Document any fix as `fix(m22): Phase 5 — <issue>`.

### Task 5.2: Test + lint + typecheck cleanliness

```bash
cd apps/metis-web && pnpm exec vitest run && pnpm exec tsc --noEmit && pnpm exec eslint lib/constellation-comet-labels.ts lib/pretext-labels.ts app/page.tsx
```

All three must be clean (modulo the known pre-existing M20 sigil-test error).

### Task 5.3: Mark M22 Landed

**Files:**
- Modify: `plans/IMPLEMENTATION.md` (M22 row → `Status: Landed`, fill final merge SHA + date)
- Modify: `plans/comet-headline-labels/plan.md` (frontmatter → `Status: Landed`; append final retrospective)

Commit `docs(m22): mark M22 Landed`.

### Task 5.4: Open Phase 5 PR

`feat(m22): Phase 5 — final polish, QA pass, mark Landed`. Merge.

---

## Notes for the next agent

- **Tracer-bullet discipline.** Phase 1 ships rough on purpose. Resist the temptation to land Phase 2 mitigations alongside it. Smoothing on top of broken spline math hides the broken spline math.
- **Pretext is at 0.0.5.** If a 0.1.x or 1.0.0 lands during this milestone, evaluate the upgrade in a *separate* PR.
- **BiDi is deferred.** Phase 1-5 ship LTR-only. If real-world feeds surface mojibake, file as a Phase 6 follow-up.
- **Visual regression is eyeballed in the live preview, not snapshot-tested.** Three reasons: (1) `canvas.getContext("2d")` is partly mocked in jsdom; (2) M22 is fundamentally about look-and-feel that snapshot tests can't catch; (3) the existing M02/M12 constellation surfaces also rely on visual QA. If we ever add canvas snapshot testing in M01, retrofit M22 into it.
- **No new outbound calls.** No new endpoints. No new fonts. Network audit (M17) is unaffected — verify by checking `/v1/network-audit/` after the milestone lands and confirming it shows no new outbound to comet-related URLs initiated by the page itself.
