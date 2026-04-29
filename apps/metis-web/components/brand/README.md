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
on `/setup`, the Tauri window splash. Adding the lockup back into the
topbar / nav is a typography migration in disguise; if it's needed,
file it as a separate milestone.

## Theming

The mark inherits color from CSS via `currentColor` on the path.
Default is `var(--brand-mark)` (near-white) — the `<MetisMark>`
component sets `text-[color:var(--brand-mark)]` so callers don't
have to set color explicitly. To recolor in a specific surface,
set `color` on a parent or pass a className that overrides.

The glow comes from two sources:
1. `.metis-glow` class in `globals.css` — outer halo (CSS drop-shadow stack).
2. The `<MetisGlow>` component itself — ripple rings via SVG `<feMorphology>` filters.

Tokens (in `tokens.css`, dark theme):
- `--brand-mark` — the mark color
- `--brand-glow-near` — RGB triplet for the inner halo (use as `rgb(var(--brand-glow-near) / α)`)
- `--brand-glow-far` — RGB triplet for the outer atmospheric halo
- `--brand-ripple` — RGB triplet for the topographic ripple rings

## Reduced-motion contract

The brand should NOT disappear when `prefers-reduced-motion: reduce`
is set. Static glow stays at 0.9 intensity. Only the ripple animation
and the breathing pulse are dropped. Implementation lives in
`metis-glow.tsx` via `useReducedMotion()` from `motion/react`; the
gate is exercised by the `animated="static"` test path in
`__tests__/metis-glow.test.tsx`.

## Adding a new surface

Pick the right primitive:

- Tiny (<48 px), in-app chrome → `<MetisMark>`
- Medium-large hero / splash, in-app → `<MetisGlow>` wrapping `<MetisMark>`
- Loading indicator → `<MetisLoader>`
- External (OG, Apple touch, `/setup` welcome, Tauri splash) → `<MetisLockup>`

If the surface is a Next.js metadata route (`app/icon.tsx`,
`apple-icon.tsx`, `opengraph-image.tsx`, `twitter-image.tsx`),
**do not import the React components** — Satori (the `ImageResponse`
renderer) only supports a subset of CSS and the components include
client-only motion code. Instead, import the path constants directly:

```tsx
import { METIS_MARK_PATH_D, METIS_MARK_VIEWBOX } from "@/components/brand";
```

…and inline the SVG yourself in the metadata route's JSX. See
`app/apple-icon.tsx` for the canonical example.

Also note: the project has `output: "export"` in `next.config.ts`
(static export for Tauri bundling). Edge runtime is incompatible
with static export — use `export const dynamic = "force-static"`
on every metadata route, never `export const runtime = "edge"`.

## Updating the asset

If the design team supplies an updated SVG:

1. Drop the new file at `apps/metis-web/public/brand/metis-mark-source.svg`.
2. Run `node apps/metis-web/scripts/clean-brand-svg.mjs`.
3. Verify the script output: under 4 KB, contains `currentColor`,
   contains `fill-rule="evenodd"`, viewBox preserved.
4. Open `apps/metis-web/public/brand/metis-mark.svg`, copy the new
   `d=` value into `METIS_MARK_PATH_D` in `metis-mark-path.ts`.
5. Run `node apps/metis-web/scripts/build-tauri-icons.mjs` (from the
   worktree root) to regenerate the desktop icon suite. The script
   lives under `apps/metis-web/` so Node's bare-import resolution
   for `sharp` finds the local `node_modules` (the repo has no root
   `package.json` / hoisted `node_modules`).
6. Run `pnpm test components/brand` and `pnpm build`.
7. Visual spot-check at `/`, `/setup`, and the metadata routes
   (`/icon`, `/apple-icon`, `/opengraph-image`).

## Out of scope (parked for follow-up)

- **"Living Mark"** — formation from the existing starfield. Filed
  in `plans/IDEAS.md` as a follow-up after M20.
- **Light-mode adaptation** — the dark-on-light asset
  (`metis-mark-dark.svg`) is NOT shipped in M20; the app is dark-
  only today.
- **Lottie / animated SVG export** for surfaces we can't render
  React on (Discord embeds, GitHub README's inline image).
- **Wordmark typography lock-in** — `Inter Tight Medium` is a
  placeholder in `<MetisLockup>`. If design specifies Geist or a
  custom face, change the `font-family` rule in `metis-lockup.tsx`
  and add the font load.

## Deviations from the original M20 design

Worth noting for future agents reading the design doc and the
implementation side-by-side:

- **Ripple rings via `<feMorphology>` instead of pre-computed
  offset paths.** Same visual goal, no build script, no extra
  deps. The design doc's "+8/+18/+30/+44/+60 px offset paths" are
  realised as `feMorphology operator="dilate" radius={...}`
  filters inside `<MetisGlow>`.
- **Home hero deviates from `<MetisGlow>` wrapping.** The hero
  already has its own M02 orbital halo system (rotating rings +
  radial gradients). `<MetisGlow>`'s ripple rings would compete
  with those. The hero swaps the rasterised PNG for a bare
  `<MetisMark>` with an inherited drop-shadow; the brand glow
  recipe is preserved but applied via the existing class.
- **Visual regression via Playwright deferred.** The repo has no
  Playwright setup; M20 ships Vitest contract tests + manual
  spot-checks instead.
