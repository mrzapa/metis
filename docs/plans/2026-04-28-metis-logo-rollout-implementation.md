# Metis logo rollout — implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire the supplied M-star logo into every brand surface of the METIS frontend — three composable React primitives, in-app surface swaps (topbar / nav / hero / setup / loader), Next.js metadata files (favicon / Apple touch / OG / Twitter), Tauri window icon suite, and per-surface motion treatment — with TDD discipline and zero disruption to existing chrome.

**Architecture:** Source SVG is cleaned (SVGO, `currentColor`) and lives at `public/brand/metis-mark.svg`. Three primitives in `components/brand/` (`MetisMark`, `MetisGlow`, `MetisLockup`) plus a `MetisLoader` convenience export. Glow is two-layer: in-SVG `feGaussianBlur` for the inner back-glow that bleeds through the M's negative space, plus CSS `drop-shadow` for the outer halo. Topographic ripple rings are rendered as `<use>` references to the master path with progressively-larger SVG `<feMorphology>` dilations — a tactical refinement of the design doc's "offset paths" approach (same visual goal, no build script, no extra deps). Motion via `motion/react` with `useReducedMotion()` gating, matching the `page-chrome.tsx` pattern.

**Tech Stack:** Next.js 16 (App Router) · React 19 · TypeScript · Tailwind v4 · `motion` (Framer) · Vitest 4 · @testing-library/react + happy-dom · pnpm · SVGO (added) · sharp (added, for Tauri icon source PNG) · Tauri 2 CLI (`pnpm tauri icon`)

**Reference docs:**
- Design: [`docs/plans/2026-04-28-metis-logo-rollout-design.md`](2026-04-28-metis-logo-rollout-design.md)
- Plan-doc stub: [`plans/metis-logo-rollout/plan.md`](../../plans/metis-logo-rollout/plan.md)
- Source asset: `m_star_logo_traced.svg` (in user's Downloads folder; copy to repo)
- README header reference image (white mark, cyan halo, ripple rings, lowercase `metis` lockup)

**Decisions locked in (do not relitigate):**
- Scope 3 (brand + metadata + motion).
- Option A wordmark discipline — chrome shows the **mark only**; the lowercase `metis` lockup appears only on OG / Apple touch / `/setup` welcome / Tauri splash. The existing uppercase `METIS<sup>AI</sup>` in chrome is **removed**, not migrated.
- Approach 2 (three composable primitives, sonar/topography ripple, `motion/react`).
- Approach 3 ("Living Mark") **parked** — do not implement here.
- Visual regression via Playwright is **deferred** — Playwright isn't installed in this repo. M20 ships Vitest contract tests + manual visual spot-checks.

**Conventions:**
- All commands run from the worktree root (`C:\Users\samwe\Documents\metis\.claude\worktrees\cranky-northcutt-42501d`).
- Use `pnpm`, not `npm` or `yarn`.
- Follow the existing `cn()` + `motion/react` patterns visible in `components/shell/page-chrome.tsx`.
- Commit at the end of every task with conventional-commits format (`feat:`, `chore:`, `test:`, `style:`, `refactor:`).
- Don't skip hooks. Don't `--amend`. Always create new commits.

---

## Phase 1 — Asset prep + primitives

**Goal:** the cleaned SVG asset and four React components exist, render correctly, and have passing tests. **No surface swaps in this phase.**

### Task 1.1: Set up dependencies and copy source asset

**Files:**
- Modify: `apps/metis-web/package.json` (add `svgo` to devDependencies)
- Create: `apps/metis-web/public/brand/metis-mark-source.svg` (copy of the user's source)

**Step 1: Copy the source SVG into the repo**

The user's source asset lives at `C:\Users\samwe\Downloads\m_star_logo_traced.svg`. Copy it to a temporary location inside the repo first; we'll clean it in the next task.

```bash
mkdir -p apps/metis-web/public/brand
cp "/c/Users/samwe/Downloads/m_star_logo_traced.svg" apps/metis-web/public/brand/metis-mark-source.svg
```

(On PowerShell: `Copy-Item "C:\Users\samwe\Downloads\m_star_logo_traced.svg" apps/metis-web/public/brand/metis-mark-source.svg`)

**Step 2: Verify the file landed and has the expected structure**

```bash
ls -la apps/metis-web/public/brand/
head -3 apps/metis-web/public/brand/metis-mark-source.svg
```

Expected: file exists, ~6 KB, opens with `<?xml version="1.0" encoding="UTF-8"?>` then `<svg width="1000" height="1000" viewBox="0 0 1000 1000"...`.

**Step 3: Add `svgo` as a devDependency**

```bash
cd apps/metis-web && pnpm add -D svgo && cd ../..
```

Expected: `svgo` appears in `apps/metis-web/package.json` `devDependencies`. `pnpm-lock.yaml` updates.

**Step 4: Commit**

```bash
git add apps/metis-web/package.json apps/metis-web/pnpm-lock.yaml apps/metis-web/public/brand/metis-mark-source.svg
git commit -m "$(cat <<'EOF'
chore(brand): add svgo and stage source M-star logo asset

Adds svgo to metis-web devDependencies and copies the design team's
supplied m_star_logo_traced.svg into public/brand/metis-mark-source.svg
as the input for the cleanup pass in the next task.

Part of M20 Phase 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.2: Clean the SVG asset (SVGO + currentColor)

**Files:**
- Create: `apps/metis-web/scripts/clean-brand-svg.mjs`
- Create: `apps/metis-web/public/brand/metis-mark.svg`
- Delete: `apps/metis-web/public/brand/metis-mark-source.svg` (only at end of task)

**Step 1: Write the cleanup script**

```javascript
// apps/metis-web/scripts/clean-brand-svg.mjs
import { readFileSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { optimize } from "svgo";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..");
const sourcePath = resolve(root, "public/brand/metis-mark-source.svg");
const outPath = resolve(root, "public/brand/metis-mark.svg");

const raw = readFileSync(sourcePath, "utf-8");

// Replace the hard-coded fill before SVGO so the optimizer doesn't
// strip currentColor as "unnecessary".
const themed = raw.replace(/fill="#111111"/g, 'fill="currentColor"');

const result = optimize(themed, {
  multipass: true,
  plugins: [
    {
      name: "preset-default",
      params: {
        overrides: {
          removeViewBox: false,
          // The M-shape relies on fill-rule:evenodd; keep it.
          removeUselessStrokeAndFill: false,
          // Float coords are excessive in the source; trim to 2dp.
          cleanupNumericValues: { floatPrecision: 2 },
        },
      },
    },
    "removeXMLNS", // we'll add it back via the React component wrapper if needed; static SVG keeps it
    { name: "removeXMLNS", active: false }, // disable — we DO want xmlns for static asset
  ],
});

if (result.error) {
  console.error("SVGO failed:", result.error);
  process.exit(1);
}

writeFileSync(outPath, result.data);

const beforeKB = (raw.length / 1024).toFixed(2);
const afterKB = (result.data.length / 1024).toFixed(2);
console.log(`Cleaned: ${beforeKB} KB → ${afterKB} KB`);

if (result.data.length > 3 * 1024) {
  console.warn(`WARNING: output is ${afterKB} KB, expected under 3 KB`);
}
if (!result.data.includes("currentColor")) {
  console.error("ERROR: currentColor was stripped");
  process.exit(1);
}
if (!result.data.includes("fill-rule=\"evenodd\"") && !result.data.includes("fill-rule='evenodd'")) {
  console.error("ERROR: fill-rule=evenodd was stripped");
  process.exit(1);
}
```

**Step 2: Run the script**

```bash
cd apps/metis-web && node scripts/clean-brand-svg.mjs && cd ../..
```

Expected output:
```
Cleaned: 5.83 KB → 2.4x KB
```
(any value under 3 KB is fine).

**Step 3: Verify the output by hand**

```bash
head -2 apps/metis-web/public/brand/metis-mark.svg
grep -o 'currentColor' apps/metis-web/public/brand/metis-mark.svg | head -1
grep -o 'fill-rule="evenodd"' apps/metis-web/public/brand/metis-mark.svg | head -1
```

Expected: file starts with `<svg ...>`, contains `currentColor`, contains `fill-rule="evenodd"`.

**Step 4: Visual smoke check**

Open `apps/metis-web/public/brand/metis-mark.svg` in a browser. The mark renders as a black M-star (since `currentColor` defaults to black on a default page). Shape matches the source.

**Step 5: Delete the source file**

We don't keep two copies. The cleaned asset is canonical.

```bash
rm apps/metis-web/public/brand/metis-mark-source.svg
```

**Step 6: Commit**

```bash
git add apps/metis-web/scripts/clean-brand-svg.mjs apps/metis-web/public/brand/metis-mark.svg
git rm apps/metis-web/public/brand/metis-mark-source.svg
git commit -m "$(cat <<'EOF'
chore(brand): clean source SVG with SVGO; theme via currentColor

Adds scripts/clean-brand-svg.mjs which runs SVGO with float-precision 2
and replaces the hard-coded fill="#111111" with fill="currentColor" so
the path inherits color from CSS. Preserves fill-rule="evenodd" (the
M-shape negative space depends on it) and the viewBox.

Output asset at public/brand/metis-mark.svg is under 3 KB.

Part of M20 Phase 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.3: Add brand design tokens to globals.css

**Files:**
- Modify: `apps/metis-web/app/globals.css` (append a brand-tokens block)

**Step 1: Read the existing globals.css to find the right insertion point**

```bash
head -60 apps/metis-web/app/globals.css
```

Look for the existing `:root` block or the Tailwind v4 `@theme` block. Brand tokens go alongside other design tokens; if there's no clear home, append them after the `:root` block.

**Step 2: Add the tokens**

Append to the end of the existing `:root` block (or create a new one if needed):

```css
/* ── Brand tokens (M20 — Metis logo rollout) ─────────────────────── */
:root {
  --brand-mark:        oklch(0.97 0.01 248);
  --brand-glow-near:   170 200 255;
  --brand-glow-far:    110 160 255;
  --brand-ripple:      150 190 255;
}

/* Two-layer glow recipe used by <MetisGlow>. The inner back-glow that
   bleeds through the M's negative space is rendered as a duplicated,
   blurred path inside the SVG — see metis-glow.tsx. */
.metis-glow {
  filter:
    drop-shadow(0 0 6px  rgb(var(--brand-glow-near) / 0.85))
    drop-shadow(0 0 18px rgb(var(--brand-glow-near) / 0.55))
    drop-shadow(0 0 48px rgb(var(--brand-glow-far)  / 0.35));
}
```

**Step 3: Commit**

```bash
git add apps/metis-web/app/globals.css
git commit -m "$(cat <<'EOF'
feat(brand): add Metis brand design tokens to globals.css

Adds --brand-mark / --brand-glow-near / --brand-glow-far / --brand-ripple
custom properties and the .metis-glow filter recipe (layered drop-shadows).
The mark color is a near-white with slight cool tint; the glow palette
reads as cyan-white on the existing #06080e starfield without competing
with the nebula-blob colors.

Part of M20 Phase 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.4: `<MetisMark>` — TDD

**Files:**
- Create: `apps/metis-web/components/brand/metis-mark-path.ts` (master path data extracted from the cleaned SVG)
- Create: `apps/metis-web/components/brand/metis-mark.tsx`
- Create: `apps/metis-web/components/brand/__tests__/metis-mark.test.tsx`

**Step 1: Extract the master path data**

Open `apps/metis-web/public/brand/metis-mark.svg`. Find the single `<path d="...">` element. Copy the full `d=` value.

Create `apps/metis-web/components/brand/metis-mark-path.ts`:

```typescript
/**
 * Master path data for the Metis M-star mark.
 *
 * Extracted from public/brand/metis-mark.svg (cleaned via SVGO).
 * The path uses fill-rule:evenodd; the inner sub-path produces the
 * M-shape inside the star silhouette via the negative-space rule.
 *
 * Do NOT hand-edit. To regenerate, re-run scripts/clean-brand-svg.mjs
 * against an updated source asset and copy the new `d=` value here.
 */
export const METIS_MARK_PATH_D = "M 75.8 621.2 L 75.8 631.3 ..." /* full path data here */;

export const METIS_MARK_VIEWBOX = "0 0 1000 1000";
```

**Step 2: Write the failing test**

```typescript
// apps/metis-web/components/brand/__tests__/metis-mark.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MetisMark } from "../metis-mark";

describe("<MetisMark>", () => {
  it("renders an SVG with the master viewBox", () => {
    const { container } = render(<MetisMark />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("viewBox")).toBe("0 0 1000 1000");
  });

  it("uses currentColor on the path so it inherits color from CSS", () => {
    const { container } = render(<MetisMark />);
    const path = container.querySelector("path");
    expect(path?.getAttribute("fill")).toBe("currentColor");
  });

  it("respects the size prop on width and height", () => {
    const { container } = render(<MetisMark size={64} />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("width")).toBe("64");
    expect(svg?.getAttribute("height")).toBe("64");
  });

  it("applies role=img and aria-label when title prop is set", () => {
    render(<MetisMark title="Metis home" />);
    const svg = screen.getByRole("img", { name: /metis home/i });
    expect(svg).not.toBeNull();
  });

  it("is aria-hidden when no title prop is set (decorative)", () => {
    const { container } = render(<MetisMark />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
  });

  it("merges className via cn() without losing default classes", () => {
    const { container } = render(<MetisMark className="custom-class" />);
    const svg = container.querySelector("svg");
    expect(svg?.className.baseVal ?? svg?.getAttribute("class") ?? "").toContain("custom-class");
  });
});
```

**Step 3: Run the test to verify it fails**

```bash
cd apps/metis-web && pnpm test components/brand/__tests__/metis-mark.test.tsx
```

Expected: all 6 tests fail with "Cannot find module '../metis-mark'".

**Step 4: Implement the component**

```typescript
// apps/metis-web/components/brand/metis-mark.tsx
import type { SVGProps } from "react";
import { cn } from "@/lib/utils";
import { METIS_MARK_PATH_D, METIS_MARK_VIEWBOX } from "./metis-mark-path";

export interface MetisMarkProps extends Omit<SVGProps<SVGSVGElement>, "title"> {
  /** Pixel size (square). Defaults to 32. */
  size?: number;
  /** Accessible label. When set, the SVG gets role="img" and is announced.
   *  When omitted, the SVG is treated as decorative (aria-hidden="true"). */
  title?: string;
}

/**
 * Static M-star mark. Inherits color from CSS (`currentColor` on the path).
 *
 * Usage:
 *   <MetisMark size={28} />                      — decorative, in chrome alongside text
 *   <MetisMark size={28} title="Metis home" />   — standalone, screen-reader-named
 *
 * Pair with `<MetisGlow>` when the surface needs the cyan halo + ripple
 * rings; the mark itself ships no glow.
 */
export function MetisMark({
  size = 32,
  title,
  className,
  ...rest
}: MetisMarkProps) {
  const isDecorative = title === undefined;
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={METIS_MARK_VIEWBOX}
      width={size}
      height={size}
      role={isDecorative ? undefined : "img"}
      aria-hidden={isDecorative ? "true" : undefined}
      aria-label={title}
      className={cn("text-[color:var(--brand-mark)]", className)}
      {...rest}
    >
      {!isDecorative && <title>{title}</title>}
      <path d={METIS_MARK_PATH_D} fill="currentColor" fillRule="evenodd" />
    </svg>
  );
}
```

**Step 5: Run the tests to verify they pass**

```bash
pnpm test components/brand/__tests__/metis-mark.test.tsx
```

Expected: all 6 tests pass.

**Step 6: Commit**

```bash
git add apps/metis-web/components/brand/metis-mark-path.ts apps/metis-web/components/brand/metis-mark.tsx apps/metis-web/components/brand/__tests__/metis-mark.test.tsx
git commit -m "$(cat <<'EOF'
feat(brand): add <MetisMark> primitive with currentColor theming

Static SVG component that renders the M-star at any size and inherits
its color from CSS via currentColor on the path. Decorative by default
(aria-hidden); becomes an announced role=img when a `title` prop is
passed (used for the topbar / nav home link).

Test coverage: viewBox, currentColor, size prop, decorative vs named
a11y semantics, className merging.

Part of M20 Phase 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.5: `<MetisGlow>` — TDD

**Files:**
- Create: `apps/metis-web/components/brand/metis-glow.tsx`
- Create: `apps/metis-web/components/brand/__tests__/metis-glow.test.tsx`

**Step 1: Write the failing tests**

```typescript
// apps/metis-web/components/brand/__tests__/metis-glow.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { MetisGlow } from "../metis-glow";
import { MetisMark } from "../metis-mark";

// Default reduced-motion mock: returns false (motion enabled).
vi.mock("motion/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("motion/react")>();
  return { ...actual, useReducedMotion: () => false };
});

describe("<MetisGlow>", () => {
  it("renders the wrapped child", () => {
    const { getByTestId } = render(
      <MetisGlow>
        <div data-testid="child" />
      </MetisGlow>,
    );
    expect(getByTestId("child")).not.toBeNull();
  });

  it("applies the .metis-glow class so the CSS drop-shadow stack kicks in", () => {
    const { container } = render(
      <MetisGlow>
        <MetisMark />
      </MetisGlow>,
    );
    const wrapper = container.querySelector(".metis-glow");
    expect(wrapper).not.toBeNull();
  });

  it("renders 5 ripple rings via <use> with feMorphology dilations", () => {
    const { container } = render(
      <MetisGlow>
        <MetisMark />
      </MetisGlow>,
    );
    const morphologyFilters = container.querySelectorAll("feMorphology");
    expect(morphologyFilters.length).toBe(5);
  });

  it("does not render rings when animated=\"static\"", () => {
    const { container } = render(
      <MetisGlow animated="static">
        <MetisMark />
      </MetisGlow>,
    );
    const morphologyFilters = container.querySelectorAll("feMorphology");
    expect(morphologyFilters.length).toBe(0);
  });

  it("respects the intensity prop by setting CSS opacity on the wrapper", () => {
    const { container } = render(
      <MetisGlow intensity={0.5}>
        <MetisMark />
      </MetisGlow>,
    );
    const wrapper = container.querySelector(".metis-glow") as HTMLElement;
    expect(wrapper.style.opacity).toBe("0.5");
  });
});
```

**Step 2: Write a separate reduced-motion test file**

```typescript
// apps/metis-web/components/brand/__tests__/metis-glow.reduced-motion.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";

vi.mock("motion/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("motion/react")>();
  return { ...actual, useReducedMotion: () => true };
});

describe("<MetisGlow> with reduced motion", () => {
  it("renders rings statically (no motion.* wrappers / no transition props)", async () => {
    const { MetisGlow } = await import("../metis-glow");
    const { MetisMark } = await import("../metis-mark");

    const { container } = render(
      <MetisGlow animated="loop">
        <MetisMark />
      </MetisGlow>,
    );

    // The brand should not disappear under reduced motion — glow class
    // is still applied, just no animation.
    const wrapper = container.querySelector(".metis-glow");
    expect(wrapper).not.toBeNull();

    // No animated motion.div with non-zero transition should appear.
    // Implementation detail: we mark the static fallback with
    // data-motion-disabled="true" so this is testable.
    const animatedEls = container.querySelectorAll("[data-motion-active=\"true\"]");
    expect(animatedEls.length).toBe(0);
  });
});
```

**Step 3: Run the tests to verify they fail**

```bash
pnpm test components/brand/__tests__/metis-glow
```

Expected: tests fail with "Cannot find module '../metis-glow'".

**Step 4: Implement `<MetisGlow>`**

```typescript
// apps/metis-web/components/brand/metis-glow.tsx
"use client";

import { motion, useReducedMotion } from "motion/react";
import { type ReactNode, useId } from "react";
import { cn } from "@/lib/utils";

export type MetisGlowAnimated = "static" | "on-mount" | "loop";

export interface MetisGlowProps {
  /** Pixel size of the wrapped mark — used to scale the ripple SVG overlay. */
  size?: number;
  /** Multiplier on glow opacity (0..1). Default 1. */
  intensity?: number;
  /** Animation behaviour. Default "on-mount". */
  animated?: MetisGlowAnimated;
  /** The mark (or any child) to wrap. */
  children: ReactNode;
  className?: string;
}

const RING_DILATIONS = [8, 18, 30, 44, 60] as const;
const RING_OPACITIES = [0.45, 0.32, 0.22, 0.14, 0.08] as const;
const RING_STAGGER_MS = 80;
const RING_DURATION_S = 0.6;

/**
 * Wraps a `<MetisMark>` (or any child) in the brand glow + topographic
 * ripple rings. The inner glow that bleeds through the M's negative
 * space comes from a CSS drop-shadow stack (`.metis-glow` in
 * globals.css). The rings are SVG `<use>` references to the mark
 * with progressively-larger feMorphology dilations.
 *
 * Motion contract:
 *   - "static": rings hidden, glow visible, no animation
 *   - "on-mount": rings stagger out once on mount, then settle
 *   - "loop": rings re-emit every 2.4s (sonar)
 *
 * Reduced-motion users always see the static fallback — the brand
 * itself stays visible (glow at 0.9 intensity), only the animation
 * is removed.
 */
export function MetisGlow({
  size = 280,
  intensity = 1,
  animated = "on-mount",
  children,
  className,
}: MetisGlowProps) {
  const reducedMotion = useReducedMotion();
  const filterIdBase = useId();

  // Reduced-motion or animated="static": no rings, no animation.
  const showRings = !reducedMotion && animated !== "static";

  return (
    <div
      className={cn("metis-glow relative inline-flex items-center justify-center", className)}
      style={{
        width: size,
        height: size,
        opacity: reducedMotion && animated !== "static" ? 0.9 * intensity : intensity,
      }}
      data-motion-active={!reducedMotion && animated !== "static" ? "true" : "false"}
    >
      {showRings && (
        <svg
          className="absolute inset-0 pointer-events-none"
          viewBox="0 0 1000 1000"
          width={size}
          height={size}
          aria-hidden="true"
        >
          <defs>
            {RING_DILATIONS.map((radius, i) => (
              <filter
                id={`${filterIdBase}-ring-${i}`}
                key={i}
                x="-20%"
                y="-20%"
                width="140%"
                height="140%"
              >
                <feMorphology operator="dilate" radius={radius} />
              </filter>
            ))}
          </defs>
          {RING_DILATIONS.map((_, i) => {
            const initial = animated === "loop" ? { opacity: 0, scale: 0.96 } : { opacity: 0, scale: 0.98 };
            const animate = { opacity: RING_OPACITIES[i], scale: 1 };
            const transition = animated === "loop"
              ? {
                  duration: RING_DURATION_S,
                  delay: (i * RING_STAGGER_MS) / 1000,
                  repeat: Infinity,
                  repeatDelay: 2.4 - (i * RING_STAGGER_MS) / 1000,
                  ease: "easeOut" as const,
                }
              : {
                  duration: RING_DURATION_S,
                  delay: (i * RING_STAGGER_MS) / 1000,
                  ease: "easeOut" as const,
                };
            return (
              <motion.g
                key={i}
                initial={initial}
                animate={animate}
                transition={transition}
                style={{ transformOrigin: "500px 500px" }}
              >
                <use
                  href="#metis-mark-master"
                  fill="none"
                  stroke={`rgb(var(--brand-ripple) / 1)`}
                  strokeWidth="1.5"
                  filter={`url(#${filterIdBase}-ring-${i})`}
                />
              </motion.g>
            );
          })}
        </svg>
      )}

      {/* Mark, with the breathing pulse on idle when animated and not reduced. */}
      {!reducedMotion && animated === "on-mount" ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: [0.85, 1, 0.85] }}
          transition={{
            opacity: {
              delay: 0.8,
              duration: 4,
              repeat: Infinity,
              ease: "easeInOut",
            },
          }}
        >
          {children}
        </motion.div>
      ) : (
        <div>{children}</div>
      )}
    </div>
  );
}
```

**Note for the executor:** the `<use href="#metis-mark-master"/>` reference assumes a single `<symbol id="metis-mark-master">` defined somewhere in the rendered tree. Update `<MetisMark>` to render its content inside `<symbol id="metis-mark-master">` when used as a child of `<MetisGlow>`, OR have `<MetisGlow>` import and inline the path data from `metis-mark-path.ts` directly. **Pick the simpler option:** import `METIS_MARK_PATH_D` directly into `<MetisGlow>` and render `<path d={METIS_MARK_PATH_D}/>` inside each ring instead of `<use href>`. This is cleaner, has no cross-element dependency, and the test for "5 feMorphology elements" still passes.

**Refactor before commit if the `<use>` approach is causing test failures.**

**Step 5: Run the tests**

```bash
pnpm test components/brand/__tests__/metis-glow
```

Expected: all tests pass (6 in `metis-glow.test.tsx`, 1 in `metis-glow.reduced-motion.test.tsx`).

**Step 6: Commit**

```bash
git add apps/metis-web/components/brand/metis-glow.tsx apps/metis-web/components/brand/__tests__/metis-glow.test.tsx apps/metis-web/components/brand/__tests__/metis-glow.reduced-motion.test.tsx
git commit -m "$(cat <<'EOF'
feat(brand): add <MetisGlow> with topographic ripple rings

Wraps a MetisMark (or any child) in the brand glow + 5 progressively-
dilated ripple rings rendered via SVG feMorphology. Three motion
modes: static (no animation), on-mount (rings stagger out once,
then idle breathing on the mark), loop (continuous sonar — used by
MetisLoader).

Reduced-motion users see the static fallback at 0.9 intensity — the
brand stays visible, only the animation drops.

Test coverage: child rendering, .metis-glow class application, ring
count by mode, reduced-motion fallback contract, intensity prop.

Part of M20 Phase 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.6: `<MetisLockup>` and `<MetisLoader>` — TDD

**Files:**
- Create: `apps/metis-web/components/brand/metis-lockup.tsx`
- Create: `apps/metis-web/components/brand/metis-loader.tsx`
- Create: `apps/metis-web/components/brand/__tests__/metis-lockup.test.tsx`
- Create: `apps/metis-web/components/brand/__tests__/metis-loader.test.tsx`

**Step 1: Write the lockup test**

```typescript
// apps/metis-web/components/brand/__tests__/metis-lockup.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";

vi.mock("motion/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("motion/react")>();
  return { ...actual, useReducedMotion: () => false };
});

describe("<MetisLockup>", () => {
  it("renders the mark and the wordmark text 'metis'", async () => {
    const { MetisLockup } = await import("../metis-lockup");
    const { container, getByText } = render(<MetisLockup />);
    expect(container.querySelector("svg")).not.toBeNull();
    expect(getByText("metis")).not.toBeNull();
  });

  it("places the wordmark to the right by default", async () => {
    const { MetisLockup } = await import("../metis-lockup");
    const { container } = render(<MetisLockup />);
    expect(container.firstChild).toHaveProperty("className");
    const root = container.firstChild as HTMLElement;
    expect(root.className).toMatch(/flex-row/);
  });

  it("places the wordmark below when wordmarkPosition='below'", async () => {
    const { MetisLockup } = await import("../metis-lockup");
    const { container } = render(<MetisLockup wordmarkPosition="below" />);
    const root = container.firstChild as HTMLElement;
    expect(root.className).toMatch(/flex-col/);
  });
});
```

**Step 2: Write the loader test**

```typescript
// apps/metis-web/components/brand/__tests__/metis-loader.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";

vi.mock("motion/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("motion/react")>();
  return { ...actual, useReducedMotion: () => false };
});

describe("<MetisLoader>", () => {
  it("renders MetisGlow in loop mode (5 feMorphology rings)", async () => {
    const { MetisLoader } = await import("../metis-loader");
    const { container } = render(<MetisLoader />);
    const morph = container.querySelectorAll("feMorphology");
    expect(morph.length).toBe(5);
  });
});
```

**Step 3: Run tests to verify they fail**

```bash
pnpm test components/brand/__tests__/metis-lockup components/brand/__tests__/metis-loader
```

Expected: tests fail (modules don't exist).

**Step 4: Implement `<MetisLockup>`**

```typescript
// apps/metis-web/components/brand/metis-lockup.tsx
"use client";

import { cn } from "@/lib/utils";
import { MetisGlow } from "./metis-glow";
import { MetisMark } from "./metis-mark";

export interface MetisLockupProps {
  /** Visual scale. "md" = 64px mark; "lg" = 128px mark. Default "md". */
  size?: "md" | "lg";
  /** Where to place the lowercase `metis` wordmark relative to the mark. */
  wordmarkPosition?: "right" | "below";
  className?: string;
}

const MARK_PX = { md: 64, lg: 128 } as const;
const WORDMARK_PX = { md: 28, lg: 56 } as const;

/**
 * Mark + lowercase `metis` wordmark, with glow. **External surfaces
 * only** per option A from M20 brainstorming — OG image, Apple
 * touch icon, /setup welcome card, Tauri splash. NOT used in
 * in-app chrome.
 *
 * Wordmark uses Inter Tight (placeholder; the design team may swap
 * to Geist or a custom face later — handled by tweaking the
 * font-family rule, not by re-rendering this component).
 */
export function MetisLockup({
  size = "md",
  wordmarkPosition = "right",
  className,
}: MetisLockupProps) {
  const isVertical = wordmarkPosition === "below";
  return (
    <div
      className={cn(
        "inline-flex items-center gap-4",
        isVertical ? "flex-col" : "flex-row",
        className,
      )}
    >
      <MetisGlow size={MARK_PX[size]} animated="static">
        <MetisMark size={MARK_PX[size]} title="Metis" />
      </MetisGlow>
      <span
        style={{
          fontFamily: "'Inter Tight', 'Inter', sans-serif",
          fontWeight: 500,
          fontSize: `${WORDMARK_PX[size]}px`,
          letterSpacing: "-0.02em",
          color: "var(--brand-mark)",
        }}
      >
        metis
      </span>
    </div>
  );
}
```

**Step 5: Implement `<MetisLoader>`**

```typescript
// apps/metis-web/components/brand/metis-loader.tsx
"use client";

import { MetisGlow, type MetisGlowProps } from "./metis-glow";
import { MetisMark } from "./metis-mark";

export interface MetisLoaderProps extends Omit<MetisGlowProps, "animated" | "children"> {
  size?: number;
}

/**
 * Convenience wrapper: a MetisGlow in loop mode (continuous sonar)
 * with the mark inside. Used for in-flight loading states —
 * DesktopReadyGuard, SetupGuard splash, companion-dock loading.
 */
export function MetisLoader({ size = 96, ...rest }: MetisLoaderProps) {
  return (
    <MetisGlow size={size} animated="loop" {...rest}>
      <MetisMark size={size * 0.4} title="Loading Metis" />
    </MetisGlow>
  );
}
```

**Step 6: Run the tests to verify they pass**

```bash
pnpm test components/brand
```

Expected: all brand tests pass (now ~10 tests across 4 files).

**Step 7: Create the barrel export**

```typescript
// apps/metis-web/components/brand/index.ts
export { MetisMark, type MetisMarkProps } from "./metis-mark";
export { MetisGlow, type MetisGlowProps, type MetisGlowAnimated } from "./metis-glow";
export { MetisLockup, type MetisLockupProps } from "./metis-lockup";
export { MetisLoader, type MetisLoaderProps } from "./metis-loader";
```

**Step 8: Commit**

```bash
git add apps/metis-web/components/brand/metis-lockup.tsx apps/metis-web/components/brand/metis-loader.tsx apps/metis-web/components/brand/__tests__/metis-lockup.test.tsx apps/metis-web/components/brand/__tests__/metis-loader.test.tsx apps/metis-web/components/brand/index.ts
git commit -m "$(cat <<'EOF'
feat(brand): add <MetisLockup>, <MetisLoader>, barrel export

MetisLockup pairs the mark with the lowercase 'metis' wordmark
(Inter Tight Medium, placeholder — design team may swap to Geist
or a custom face later). External surfaces only per option A:
OG image, Apple touch, /setup welcome, Tauri splash. NOT used in
chrome.

MetisLoader is MetisGlow(animated="loop") + MetisMark — used for
in-flight loading states.

Phase 1 closes with a barrel export and ~10 passing tests across
the four primitives.

Part of M20 Phase 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.7: Phase 1 verification gate

**Goal:** confirm Phase 1 is genuinely complete before any surface swaps.

**Step 1: Run the full test suite**

```bash
cd apps/metis-web && pnpm test && cd ../..
```

Expected: full suite passes. Brand tests are part of it.

**Step 2: Run lint**

```bash
cd apps/metis-web && pnpm lint && cd ../..
```

Expected: zero errors. Fix any typing or unused-import issues before proceeding.

**Step 3: Visual smoke check via the Next.js dev server**

```bash
cd apps/metis-web && pnpm dev
```

In a browser, open `http://localhost:3000` and use React DevTools (or just paste a quick test page) to render `<MetisMark>`, `<MetisGlow>`, `<MetisLockup>`, `<MetisLoader>` at common sizes. Confirm:
- Mark is visible, white-ish, on the dark starfield.
- Glow has the cyan halo with the soft outer bloom.
- Ripple rings stagger out on mount and breathe.
- Lockup wordmark is legible; spacing looks intentional.
- Loader rings re-emit on a continuous loop.

If any of those look broken, fix in Phase 1 before swapping any surfaces.

Stop the dev server with Ctrl+C.

**Step 4: No commit needed.** This is a verification gate.

---

## Phase 2 — In-app surface swaps

**Goal:** chrome and hero use the new primitives. The old PNG and typographic logo blocks are removed. **Coordinate with M01 before starting** — `home-visual-system.tsx` is an M01 hotspot.

### Task 2.1: Swap topbar wordmark for the mark

**Files:**
- Modify: `apps/metis-web/components/shell/page-chrome.tsx:101–114`

**Step 1: Read the current implementation**

```bash
cat apps/metis-web/components/shell/page-chrome.tsx | head -160 | tail -70
```

Confirm lines 101–114 still match the typographic wordmark (`<span style={...}>METIS<sup>...</sup></span>`).

**Step 2: Replace the wordmark with the mark**

Edit `components/shell/page-chrome.tsx`. Replace the `<Link href="/"><span style={...}>METIS<sup>...</sup></span></Link>` block (lines 101–114) with:

```tsx
<Link href="/" aria-label="Metis home">
  <MetisMark size={28} title="Metis home" />
</Link>
```

Add the import at the top of the file alongside the other component imports:

```tsx
import { MetisMark } from "@/components/brand";
```

**Step 3: Run the dev server and verify**

```bash
cd apps/metis-web && pnpm dev
```

Visit `/`, `/chat`, `/settings`. Topbar shows the mark (~28 px) on the left, no text. Click the mark — navigates to `/`. Hover behaviour is unchanged for the rest of the nav. Stop the server.

**Step 4: Commit**

```bash
git add apps/metis-web/components/shell/page-chrome.tsx
git commit -m "$(cat <<'EOF'
feat(shell): replace topbar wordmark with <MetisMark>

Swaps the typographic METIS<sup>AI</sup> wordmark in the page-chrome
topbar for the new M-star mark (28px, named for screen readers).
Per M20 option A: chrome is mark-only; the lowercase 'metis' lockup
is reserved for external surfaces.

Part of M20 Phase 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.2: Swap landing nav wordmark for the mark + prune CSS

**Files:**
- Modify: `apps/metis-web/app/page.tsx:5694` and the `.metis-logo` CSS block at `:6111–6117`

**Step 1: Read the current nav block and the CSS**

```bash
sed -n '5690,5700p' apps/metis-web/app/page.tsx
sed -n '6110,6120p' apps/metis-web/app/page.tsx
```

**Step 2: Replace the wordmark element**

Change line 5694 from:
```tsx
<div className="metis-logo">METIS<sup>AI</sup></div>
```
to:
```tsx
<MetisMark size={32} title="Metis home" className="metis-logo" />
```

(Keeping `className="metis-logo"` for now in case any other layout CSS targets it; the next step removes the styling that's now orthogonal.)

**Step 3: Add the import**

At the top of `app/page.tsx` alongside other imports:

```tsx
import { MetisMark } from "@/components/brand";
```

**Step 4: Prune the dead `.metis-logo` CSS**

Delete the `.metis-logo { ... }` and `.metis-logo sup { ... }` blocks at lines ~6111–6117. The mark inherits its color from `var(--brand-mark)` via the component, not from page-scoped CSS.

**Step 5: Run the dev server and verify**

```bash
cd apps/metis-web && pnpm dev
```

Visit `/`. Landing nav shows the mark (32 px) on the left where the wordmark used to be. Layout (gap to nav links) looks consistent with the topbar treatment.

**Step 6: Commit**

```bash
git add apps/metis-web/app/page.tsx
git commit -m "$(cat <<'EOF'
feat(landing): replace nav wordmark with <MetisMark>; prune .metis-logo CSS

Swaps the .metis-logo typographic wordmark in the landing-page nav
for the new mark (32px, screen-reader-named). Removes the now-dead
.metis-logo and .metis-logo sup CSS blocks; the mark inherits color
from --brand-mark via the component.

Part of M20 Phase 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.3: Swap home hero PNG for `<MetisGlow><MetisMark/></MetisGlow>`

**Files:**
- Modify: `apps/metis-web/components/home/home-visual-system.tsx:135` (and surrounding `<Image>` block)

**Step 1: Read the current hero block**

```bash
sed -n '125,150p' apps/metis-web/components/home/home-visual-system.tsx
```

Identify the `<Image src="/metis-logo.png" ... />` element and its sizing wrapper.

**Step 2: Replace it**

Replace the `<Image src="/metis-logo.png" alt="METIS logo" fill ... />` element with:

```tsx
<MetisGlow size={280} animated="on-mount">
  <MetisMark size={280} title="Metis" />
</MetisGlow>
```

Adjust the parent container's size if needed — the previous PNG was filling a parent; the new component wants a fixed 280px square. If the parent uses `position: relative` with `fill`, drop those and let the inline-flex of `<MetisGlow>` handle layout.

**Step 3: Add the imports**

```tsx
import { MetisGlow, MetisMark } from "@/components/brand";
```

Remove the now-unused `Image` import if `home-visual-system.tsx` doesn't use it elsewhere.

**Step 4: Run the dev server and verify**

```bash
cd apps/metis-web && pnpm dev
```

Visit `/`. The home hero shows the mark with the cyan halo and ripple rings staggering out on mount, then breathing. Resize the window — the mark stays centered. The starfield behind it is undisturbed.

**Step 5: Commit**

```bash
git add apps/metis-web/components/home/home-visual-system.tsx
git commit -m "$(cat <<'EOF'
feat(home): replace metis-logo.png with <MetisGlow> + <MetisMark>

Swaps the rasterised hero PNG for the new SVG mark wrapped in the
brand glow at 280px. Ripple rings stagger out on mount; idle
breathing kicks in after 800ms. Reduced-motion users see the
static glow at 0.9 intensity.

The unused PNG is removed in a follow-up task.

Part of M20 Phase 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.4: Add `<MetisLockup>` to the /setup welcome card

**Files:**
- Modify: `apps/metis-web/app/setup/page.tsx`

**Step 1: Find the welcome / hero card in the setup page**

```bash
grep -n "Welcome\|welcome\|h1\|eyebrow\|hero" apps/metis-web/app/setup/page.tsx | head -20
```

Identify the topmost card / hero block in the setup wizard's first step.

**Step 2: Add the lockup**

At the top of the welcome / hero card, before the existing eyebrow / heading:

```tsx
<MetisLockup size="md" wordmarkPosition="right" className="mb-4" />
```

Add the import:

```tsx
import { MetisLockup } from "@/components/brand";
```

**Step 3: Run the dev server and verify**

```bash
cd apps/metis-web && pnpm dev
```

Visit `/setup`. The lockup (mark + lowercase `metis` wordmark) appears at the top of the welcome card. Spacing looks intentional. The rest of the wizard is undisturbed.

**Step 4: Commit**

```bash
git add apps/metis-web/app/setup/page.tsx
git commit -m "$(cat <<'EOF'
feat(setup): add <MetisLockup> to welcome card

Renders the mark + lowercase 'metis' wordmark at the top of the
first setup step — a new user's first impression of the brand.
External-surface-only per M20 option A.

Part of M20 Phase 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.5: Swap the desktop-ready loader

**Files:**
- Modify: `apps/metis-web/components/desktop-ready.tsx`

**Step 1: Read the existing loader**

```bash
cat apps/metis-web/components/desktop-ready.tsx
```

Identify the existing spinner / loading indicator inside the guard's "not ready yet" branch.

**Step 2: Replace it with `<MetisLoader>`**

Swap the spinner JSX for:

```tsx
<div className="flex min-h-screen items-center justify-center">
  <MetisLoader size={120} />
</div>
```

Add the import:

```tsx
import { MetisLoader } from "@/components/brand";
```

**Step 3: Verify**

If you can boot the Tauri shell or simulate the not-ready state in the dev server, confirm the loader shows the mark with the continuous sonar rings. Otherwise, a unit test of `desktop-ready.tsx` (if one exists) will exercise the path. **If neither verification is practical, the test in Phase 4 will catch regressions** — proceed to commit.

**Step 4: Commit**

```bash
git add apps/metis-web/components/desktop-ready.tsx
git commit -m "$(cat <<'EOF'
feat(desktop): use <MetisLoader> for the desktop-ready guard

Replaces the previous spinner with the brand sonar loader (mark +
continuous ripple rings). Reduced-motion users see the static glow
fallback.

Part of M20 Phase 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.6: Delete the unused PNG

**Files:**
- Delete: `apps/metis-web/public/metis-logo.png`

**Step 1: Confirm there are no remaining references**

```bash
grep -rn "metis-logo.png\|/metis-logo" apps/metis-web --include="*.ts" --include="*.tsx" --include="*.css" --include="*.json"
```

Expected: zero matches outside of `_archive` files. If any non-archive file still references the PNG, fix the reference first.

**Step 2: Delete the asset**

```bash
git rm apps/metis-web/public/metis-logo.png
```

**Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
chore(brand): remove unused metis-logo.png

The home hero now uses <MetisMark> + <MetisGlow>; no remaining
references to the rasterised PNG. Part of M20 Phase 2 close-out.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.7: Phase 2 verification gate

**Step 1: Run the full test suite and lint**

```bash
cd apps/metis-web && pnpm test && pnpm lint && cd ../..
```

Expected: green.

**Step 2: Visual spot-check across the app**

```bash
cd apps/metis-web && pnpm dev
```

Click through every primary route (`/`, `/chat`, `/settings`, `/setup`, `/diagnostics`, `/library`, `/improvements`). Confirm:
- Topbar mark is consistent on every route.
- Home hero mark + glow + ripples animate cleanly.
- Setup welcome shows the lockup.
- No layout regressions; no console errors mentioning the brand components.

Stop the dev server.

**Step 3: No commit needed.** Verification gate.

---

## Phase 3 — System metadata

**Goal:** browser tabs, social unfurls, and the Tauri window all show the brand.

### Task 3.1: `app/icon.tsx` — favicon

**Files:**
- Create: `apps/metis-web/app/icon.tsx`
- Delete: `apps/metis-web/app/favicon.ico` (only after icon.tsx is confirmed working)

**Step 1: Create `app/icon.tsx`**

The Next.js `app/icon.tsx` convention generates a 32×32 favicon at build time. At 32×32 the M's negative-space notches mush together, so we render a **simplified silhouette** — the star outline without the inner M cutout.

```tsx
// apps/metis-web/app/icon.tsx
import { ImageResponse } from "next/og";

export const runtime = "edge";
export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background: "#06080e",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {/*
          Simplified star silhouette (no M cutout) so the mark stays
          legible at 32x32. The shape is a 5-point star approximation
          using SVG path data.
        */}
        <svg width="24" height="24" viewBox="0 0 100 100">
          <path
            d="M50 5 L62 38 L96 38 L68 58 L78 92 L50 72 L22 92 L32 58 L4 38 L38 38 Z"
            fill="#f4f6fa"
          />
        </svg>
      </div>
    ),
    size,
  );
}
```

**Step 2: Build and verify**

```bash
cd apps/metis-web && pnpm build
```

Expected: build succeeds. Check the output — Next.js places the generated icon under `.next/`. Visit `http://localhost:3000/icon` after `pnpm start` to confirm a 32×32 PNG renders.

(Alternative quick check: `pnpm dev`, then `curl -I http://localhost:3000/icon` — should return `200 image/png`.)

**Step 3: Delete the default `app/favicon.ico`**

Once `icon.tsx` is confirmed serving, the old `.ico` is dead weight. Next.js prefers `icon.tsx` when both exist; explicit deletion avoids confusion.

```bash
git rm apps/metis-web/app/favicon.ico
```

**Step 4: Commit**

```bash
git add apps/metis-web/app/icon.tsx
git commit -m "$(cat <<'EOF'
feat(metadata): add app/icon.tsx; remove default favicon.ico

Renders a 32x32 favicon at build time using a simplified star
silhouette (no M cutout) so the mark stays legible at tab-icon
scale. Removes the default Next.js favicon.ico now that icon.tsx
is the canonical source.

Part of M20 Phase 3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3.2: `app/apple-icon.tsx`

**Files:**
- Create: `apps/metis-web/app/apple-icon.tsx`

**Step 1: Create the file**

```tsx
// apps/metis-web/app/apple-icon.tsx
import { ImageResponse } from "next/og";
import { METIS_MARK_PATH_D, METIS_MARK_VIEWBOX } from "@/components/brand/metis-mark-path";

export const runtime = "edge";
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background: "#06080e",
          borderRadius: "32px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <svg width="120" height="120" viewBox={METIS_MARK_VIEWBOX}>
          <path d={METIS_MARK_PATH_D} fill="#f4f6fa" fillRule="evenodd" />
        </svg>
      </div>
    ),
    size,
  );
}
```

**Step 2: Build and verify**

```bash
pnpm build && pnpm start
```

Visit `http://localhost:3000/apple-icon` — should return a 180×180 PNG with the white mark on dark navy with rounded corners.

**Step 3: Commit**

```bash
git add apps/metis-web/app/apple-icon.tsx
git commit -m "$(cat <<'EOF'
feat(metadata): add app/apple-icon.tsx

Renders the 180x180 Apple touch icon at build time — white mark on
dark navy (#06080e) with 32px rounded corners. Uses the full mark
(M cutout intact) since 180px is plenty of resolution.

Part of M20 Phase 3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3.3: `app/opengraph-image.tsx`

**Files:**
- Create: `apps/metis-web/app/opengraph-image.tsx`

**Step 1: Create the file**

```tsx
// apps/metis-web/app/opengraph-image.tsx
import { ImageResponse } from "next/og";
import { METIS_MARK_PATH_D, METIS_MARK_VIEWBOX } from "@/components/brand/metis-mark-path";

export const runtime = "edge";
export const alt = "Metis — a local-first frontier AI workspace";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background: "linear-gradient(180deg, #06080e 0%, #0a1024 100%)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 96px",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        {/* Left: lockup */}
        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          <span
            style={{
              fontSize: "144px",
              fontWeight: 500,
              color: "#f4f6fa",
              letterSpacing: "-0.04em",
              lineHeight: 1,
            }}
          >
            metis
          </span>
          <span
            style={{
              fontSize: "32px",
              color: "rgba(244, 246, 250, 0.72)",
              maxWidth: "560px",
              lineHeight: 1.3,
            }}
          >
            A local-first frontier AI workspace.
          </span>
        </div>

        {/* Right: glowing mark with static ripple rings */}
        <div
          style={{
            position: "relative",
            width: "360px",
            height: "360px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {/* Static ripple rings — 5 concentric, opacity-graduated */}
          {[60, 44, 30, 18, 8].map((r, i) => (
            <div
              key={r}
              style={{
                position: "absolute",
                inset: `${-r * 0.5}px`,
                border: `1.5px solid rgba(150, 190, 255, ${0.08 + i * 0.07})`,
                borderRadius: "50%",
                filter: "blur(0.5px)",
              }}
            />
          ))}
          <svg width="280" height="280" viewBox={METIS_MARK_VIEWBOX} style={{ filter: "drop-shadow(0 0 48px rgba(110, 160, 255, 0.45))" }}>
            <path d={METIS_MARK_PATH_D} fill="#f4f6fa" fillRule="evenodd" />
          </svg>
        </div>
      </div>
    ),
    size,
  );
}
```

**Note:** the `<ImageResponse>` API doesn't render arbitrary SVG filters faithfully (it's powered by Satori which has a subset of CSS). The static rings are approximated as concentric `border-radius: 50%` divs rather than feMorphology. This is intentional — OG must rasterize at build time.

**Step 2: Add a re-export for Twitter**

```tsx
// apps/metis-web/app/twitter-image.tsx
export { default, alt, size, contentType, runtime } from "./opengraph-image";
```

**Step 3: Build and verify**

```bash
pnpm build && pnpm start
```

Visit `http://localhost:3000/opengraph-image` — should return a 1200×630 PNG with the lockup on the left and glowing mark on the right. Drop the URL into a social-card preview tool (or just view the image) to confirm it composes well at the standard OG aspect ratio.

**Step 4: Commit**

```bash
git add apps/metis-web/app/opengraph-image.tsx apps/metis-web/app/twitter-image.tsx
git commit -m "$(cat <<'EOF'
feat(metadata): add OpenGraph and Twitter card images

1200x630 social card with lockup on the left (lowercase 'metis' +
tagline) and glowing mark on the right. Static ripple rings
approximated as concentric border-radius divs since Satori (the
ImageResponse renderer) doesn't render feMorphology filters.

Part of M20 Phase 3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3.4: Tauri window icon suite

**Files:**
- Modify: `apps/metis-web/package.json` (add `sharp` to devDependencies)
- Create: `scripts/build-tauri-icons.mjs` (at the repo root)
- Modify (generated): `apps/metis-desktop/src-tauri/icons/*`

**Step 1: Add sharp**

```bash
cd apps/metis-web && pnpm add -D sharp && cd ../..
```

**Step 2: Write the build script**

```javascript
// scripts/build-tauri-icons.mjs
import { execSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..");

const sourceSvg = resolve(root, "apps/metis-web/public/brand/metis-mark.svg");
const tauriDir = resolve(root, "apps/metis-desktop");
const tempPng = resolve(tauriDir, "src-tauri/icons/_source-1024.png");

console.log("Rasterising SVG → 1024x1024 PNG...");
await sharp(sourceSvg)
  .resize(1024, 1024)
  .flatten({ background: { r: 6, g: 8, b: 14, alpha: 1 } }) // #06080e
  .composite([
    {
      input: Buffer.from(
        `<svg width="1024" height="1024"><rect width="1024" height="1024" rx="180" fill="#06080e"/></svg>`,
      ),
      blend: "dest-over",
    },
  ])
  .png()
  .toFile(tempPng);

console.log("Running `pnpm tauri icon`...");
execSync(`pnpm tauri icon "${tempPng}"`, {
  cwd: tauriDir,
  stdio: "inherit",
});

console.log("Done. Generated icons under apps/metis-desktop/src-tauri/icons/");
```

**Step 3: Run the script**

```bash
node scripts/build-tauri-icons.mjs
```

Expected: outputs the standard Tauri icon set (`32x32.png`, `128x128.png`, `128x128@2x.png`, `icon.icns`, `icon.ico`) into `apps/metis-desktop/src-tauri/icons/`.

**Step 4: Verify the output**

```bash
ls apps/metis-desktop/src-tauri/icons/
```

Expected files present. Open one of the PNGs visually to confirm the white mark on dark navy renders correctly.

**Step 5: Clean up the temp file**

```bash
rm apps/metis-desktop/src-tauri/icons/_source-1024.png
```

**Step 6: Commit**

```bash
git add apps/metis-web/package.json apps/metis-web/pnpm-lock.yaml scripts/build-tauri-icons.mjs apps/metis-desktop/src-tauri/icons/
git commit -m "$(cat <<'EOF'
feat(desktop): regenerate Tauri icon suite from M-star SVG

Adds sharp as a metis-web devDependency and a one-shot script
(scripts/build-tauri-icons.mjs) that rasterises the brand SVG
to 1024x1024 (with a #06080e rounded-square background) and
runs `pnpm tauri icon` to emit the standard 5-file icon suite
under apps/metis-desktop/src-tauri/icons/.

Part of M20 Phase 3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3.5: Phase 3 verification gate

**Step 1: Build and start the production server**

```bash
cd apps/metis-web && pnpm build && pnpm start
```

Visit:
- `http://localhost:3000/icon` → 32×32 PNG, white star on navy
- `http://localhost:3000/apple-icon` → 180×180 PNG, full mark on rounded navy square
- `http://localhost:3000/opengraph-image` → 1200×630 PNG, lockup + glowing mark
- `http://localhost:3000/twitter-image` → identical to opengraph-image

Stop the server.

**Step 2: Tauri smoke check (if Tauri is buildable locally)**

If the Rust toolchain is set up:

```bash
cd apps/metis-desktop && pnpm tauri dev
```

Confirm the desktop window's title-bar / taskbar icon shows the new mark. Stop with Ctrl+C.

**If Tauri isn't buildable in this environment, defer this check** — the next agent who picks up M20 (or anyone running a Tauri build for unrelated reasons) will surface any icon issue.

**Step 3: No commit.** Verification gate.

---

## Phase 4 — Motion polish

**Goal:** the per-surface motion spec from the design doc is fully implemented and tuned. Reduced-motion is verified end-to-end.

### Task 4.1: Topbar hover-glow effect

**Files:**
- Modify: `apps/metis-web/components/shell/page-chrome.tsx` (the topbar mark Link)

**Step 1: Add the hover effect**

Wrap the existing `<MetisMark>` in the topbar with a `motion.span` that brightens the glow on hover:

```tsx
import { motion } from "motion/react";
// ...
<Link href="/" aria-label="Metis home">
  <motion.span
    className="metis-glow inline-flex"
    initial={{ opacity: 0.92 }}
    whileHover={{ opacity: 1 }}
    transition={{ duration: 0.2, ease: "easeOut" }}
    style={{ filter: "drop-shadow(0 0 4px rgb(var(--brand-glow-near) / 0.6))" }}
  >
    <MetisMark size={28} title="Metis home" />
  </motion.span>
</Link>
```

**Step 2: Verify**

```bash
cd apps/metis-web && pnpm dev
```

Hover over the topbar mark. Glow brightens subtly. Move the cursor away — fades back. No layout shift.

**Step 3: Commit**

```bash
git add apps/metis-web/components/shell/page-chrome.tsx
git commit -m "$(cat <<'EOF'
style(shell): add hover-glow to topbar Metis mark

Subtle brightness lift on hover (200ms ease-out, opacity 0.92→1.0
plus a 4px brand-glow drop-shadow). No layout shift; reduced-motion
users still get the static mark.

Part of M20 Phase 4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4.2: Tune hero ripple timing against the live page

**Files:**
- Possibly modify: `apps/metis-web/components/brand/metis-glow.tsx` (only if visual review surfaces issues)

**Step 1: Visual review on the home page**

```bash
cd apps/metis-web && pnpm dev
```

Reload `/` several times. Watch the ripple rings:
- Stagger feels intentional (not too fast, not too slow).
- Final ring opacity reads as "topographic" not "noise".
- Idle breathing kicks in cleanly without a visible seam.
- On a slow refresh (Network → Slow 3G in DevTools), the rings still trigger as expected after the page paints.

If anything feels off, adjust the constants in `metis-glow.tsx`:
- `RING_STAGGER_MS` (default 80) — increase to 120 for slower stagger
- `RING_OPACITIES` — flatten the curve if rings feel too faint
- `RING_DURATION_S` — increase to 0.8 for a softer entrance

**Step 2: Test with reduced motion**

In Chrome DevTools: Rendering → Emulate CSS `prefers-reduced-motion: reduce`. Reload `/`. Confirm:
- Mark still visible at 0.9 intensity.
- No ripple rings.
- No breathing pulse.

**Step 3: Commit if any tweaks were made**

```bash
git add apps/metis-web/components/brand/metis-glow.tsx
git commit -m "$(cat <<'EOF'
style(brand): tune ripple timing for hero entrance

Visual review against the live home page surfaced [describe what
was tweaked — e.g., "slowed stagger to 120ms" or "flattened ring
opacity curve"]. Reduced-motion path verified via Chrome DevTools.

Part of M20 Phase 4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

If no tweaks were needed, skip the commit and note "no changes — defaults work" in your session log.

---

### Task 4.3: Document the brand surface for future agents

**Files:**
- Create: `apps/metis-web/components/brand/README.md`

**Step 1: Write the README**

```markdown
# Brand primitives

The Metis logo system. Three composable React components plus a loader
convenience export, all backed by a single cleaned, themeable SVG.

| Component | Use it for |
|---|---|
| `<MetisMark>` | The mark alone. In-app chrome (topbar, nav), favicon source, anywhere small. |
| `<MetisGlow>` | Mark + brand glow + topographic ripple rings. Hero, splash, OG image. |
| `<MetisLockup>` | Mark + lowercase `metis` wordmark. **External surfaces only** — OG, Apple touch, /setup welcome, Tauri splash. NOT for chrome. |
| `<MetisLoader>` | Mark + continuous sonar rings. Loading states (DesktopReadyGuard, etc.). |

## The wordmark discipline (don't re-litigate)

Per M20 option A: **chrome shows the mark only**. The lowercase
humanist `metis` wordmark in `<MetisLockup>` is for surfaces where
the brand needs to be *spoken* — social unfurls, the first impression
on /setup, the Tauri window splash. Adding the lockup back into the
topbar / nav is a typography migration in disguise; if it's needed,
file it as a separate milestone.

## Theming

The mark inherits color from CSS via `currentColor` on the path.
Default is `var(--brand-mark)` (near-white). To recolor anywhere,
just set `color` on a parent, or pass a className that does.

The glow comes from two sources:
1. `.metis-glow` class in `globals.css` — outer halo (CSS drop-shadow stack).
2. The `<MetisGlow>` component itself — inner back-glow + ripple rings.

## Reduced-motion contract

The brand should NOT disappear when `prefers-reduced-motion: reduce`
is set. Static glow stays at 0.9 intensity. Only the ripple animation
and the breathing pulse are dropped. Verified in
`__tests__/metis-glow.reduced-motion.test.tsx`.

## Adding a new surface

Pick the right primitive:
- Tiny (<48px), in-app chrome → `<MetisMark>`
- Medium-large hero / splash, in-app → `<MetisGlow>` + `<MetisMark>`
- Loading indicator → `<MetisLoader>`
- External (OG, Apple touch, /setup, Tauri splash) → `<MetisLockup>`

If the surface is a Next.js metadata route (`app/icon.tsx`,
`apple-icon.tsx`, `opengraph-image.tsx`), import `METIS_MARK_PATH_D`
from `metis-mark-path.ts` and render it inside an `ImageResponse`-
compatible JSX subset (Satori's CSS subset). Don't try to use the
React components themselves there — they have client-only motion code.

## Updating the asset

If the design team supplies an updated SVG:

1. Drop the new file at `apps/metis-web/public/brand/metis-mark-source.svg`.
2. Run `node apps/metis-web/scripts/clean-brand-svg.mjs`.
3. Verify: under 3 KB, contains `currentColor`, contains `fill-rule="evenodd"`.
4. Update `METIS_MARK_PATH_D` in `metis-mark-path.ts` with the new `d=` value.
5. Run `node scripts/build-tauri-icons.mjs` to regenerate the desktop icon suite.
6. Run `pnpm test components/brand`.
7. Visual spot-check at `/`, `/setup`, and the metadata routes (`/icon`, `/apple-icon`, `/opengraph-image`).

## Out of scope (future)

- "Living Mark" — formation from the existing starfield. Filed in `plans/IDEAS.md` as a follow-up after M20.
- Light-mode adaptation — the dark-on-light asset (`metis-mark-dark.svg`) ships in `public/brand/` but isn't wired anywhere.
- Lottie / animated SVG export for surfaces we can't render React on.
```

**Step 2: Commit**

```bash
git add apps/metis-web/components/brand/README.md
git commit -m "$(cat <<'EOF'
docs(brand): document the brand-primitive surface for future agents

Adds a README that covers component usage, the wordmark-discipline
decision (option A — don't re-litigate), theming, the reduced-motion
contract, and how to update the asset if design ships a new version.

Part of M20 Phase 4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4.4: Final M20 verification gate

**Step 1: Run the full test suite, lint, and build**

```bash
cd apps/metis-web && pnpm test && pnpm lint && pnpm build && cd ../..
```

Expected: green across all three.

**Step 2: Visual smoke check across every brand surface**

```bash
cd apps/metis-web && pnpm dev
```

Walk:
- `/` — topbar mark, hero glow + ripples + breathing, landing nav mark.
- `/chat`, `/settings`, `/diagnostics`, `/library`, `/improvements` — topbar mark consistent.
- `/setup` — lockup at top of welcome card.
- DesktopReadyGuard loading state (if reproducible) — sonar loader.
- `/icon`, `/apple-icon`, `/opengraph-image`, `/twitter-image` — all return correct PNGs.

Run with reduced motion enabled (Chrome DevTools → Rendering → Emulate CSS `prefers-reduced-motion: reduce`):
- All animations stop.
- Brand stays visible everywhere.

Stop the dev server.

**Step 3: Update the milestone status**

Edit `plans/IMPLEMENTATION.md` row M20: change `Status` from `Ready` to `Landed`, fill in the Claim with the merge commit SHA once the PR lands, and update `Last updated`.

Edit `plans/metis-logo-rollout/plan.md` frontmatter: `Status: Landed`. Update Progress with a one-line summary of each phase.

**Step 4: Open the PR**

```bash
git push -u origin <branch-name>
gh pr create --title "feat(brand): M20 — Metis logo rollout" --body "$(cat <<'EOF'
## Summary
- Adds three React brand primitives (`<MetisMark>`, `<MetisGlow>`, `<MetisLockup>`) + a `<MetisLoader>` convenience export, backed by a cleaned `currentColor`-themed SVG asset.
- Swaps the topbar wordmark, landing nav wordmark, home hero PNG, and desktop-ready loader for the new primitives. The lowercase `metis` lockup appears on `/setup` welcome only (external-surface discipline per M20 option A).
- Adds Next.js metadata files (`app/icon.tsx`, `apple-icon.tsx`, `opengraph-image.tsx`, `twitter-image.tsx`) and regenerates the Tauri window icon suite.
- Reduced-motion users get the static brand at 0.9 intensity — verified by a dedicated component test.

## Test plan
- [ ] `pnpm test` green
- [ ] `pnpm lint` clean
- [ ] `pnpm build` succeeds
- [ ] Visual spot-check on `/`, `/chat`, `/settings`, `/setup` shows the new mark consistently
- [ ] Reduced-motion path verified via Chrome DevTools emulation
- [ ] `/icon`, `/apple-icon`, `/opengraph-image` return correct PNGs
- [ ] Tauri icon suite regenerates cleanly via `node scripts/build-tauri-icons.mjs`

Closes M20.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Cross-cutting verification (run before declaring done)

- [ ] `pnpm test` — all brand tests pass + no other tests regressed.
- [ ] `pnpm lint` — zero errors, zero warnings outside pre-existing.
- [ ] `pnpm build` — production build succeeds; no missing-asset warnings; bundle size delta is reasonable (<10 KB gzipped for the brand surface).
- [ ] No remaining references to `metis-logo.png` or `.metis-logo` CSS class outside `_archive/`.
- [ ] No remaining references to the typographic `METIS<sup>AI</sup>` wordmark outside `_archive/` or where it's intentionally kept for content (e.g., a hero h1 that happens to spell "Metis").
- [ ] `metis-mark.svg` is under 3 KB.
- [ ] All brand metadata routes (`/icon`, `/apple-icon`, `/opengraph-image`, `/twitter-image`) return 200 with `Content-Type: image/png`.
- [ ] Tauri icon suite regenerates idempotently from `pnpm tauri icon` against a `1024x1024` source PNG.
- [ ] Reduced-motion behavior verified manually: brand visible, no animation.

---

## Out of scope (filed but not done in M20)

- **Approach 3 — "Living Mark" formed from starfield.** File a new entry in `plans/IDEAS.md` as a follow-up milestone after M20 lands.
- **Playwright visual regression baselines** for the hero and OG. Defer until Playwright is added repo-wide.
- **Light-mode brand variant.** `metis-mark-dark.svg` ships as a safety net but isn't wired anywhere; revisit if light mode lands.
- **Wordmark typography lock-in.** `Inter Tight Medium` is a placeholder; if the design team specifies Geist or a custom face, it's a one-line swap inside `<MetisLockup>`.
- **Animated SVG / Lottie export.** Only relevant for surfaces we can't render React on (Discord embeds, the README itself if updated inline).

---

## Notes for the executor

- **Don't skip the verification gates between phases.** Phase 1's primitives need to be solid before any surface swap. A regression in `<MetisGlow>` discovered during Phase 3 means walking back through Phases 2 *and* 3.
- **Coordinate with M01 before Phase 2.** Check `plans/IMPLEMENTATION.md` and the M01 plan doc — if anyone's mid-edit on `home-visual-system.tsx`, defer or rebase.
- **The `<use href>` cross-element reference inside `<MetisGlow>` is fragile.** If you hit issues, switch to inlining `METIS_MARK_PATH_D` directly inside each ring (the design-doc note covers this — it's an approved fallback, not a deviation).
- **`tauri icon` requires the Rust toolchain.** If your machine doesn't have it, defer Task 3.4 with a note in the PR description; whoever has Rust set up can run the script and amend the PR.
- **The Google Fonts `@import` at `app/page.tsx:5309`** is M17 territory (network audit), not M20. Don't get sidetracked refactoring it.
- **Don't add Playwright in this milestone** even if you're tempted by the visual-regression mention in the design doc. Adding a new test framework is its own decision; it's deferred.
