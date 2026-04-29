# Metis logo rollout — design

**Date:** 2026-04-28
**Milestone:** M20 (Metis logo rollout)
**Plan-doc reference:** [`plans/metis-logo-rollout/plan.md`](../../plans/metis-logo-rollout/plan.md)
**Source asset:** `m_star_logo_traced.svg` (provided 2026-04-28; 1000×1000 viewBox, single fill-rule:evenodd path, `fill="#111111"`)
**Reference:** GitHub README header from the design team — white M-star mark with cyan halo + topographic ripple rings, lowercase `metis` wordmark on dark navy field.
**Status:** Approved 2026-04-28.

## Problem

The METIS web app has no logo glyph. Today the brand surface is purely
typographic — `METIS<sup>AI</sup>` in Space Grotesk, repeated in the topbar
([`components/shell/page-chrome.tsx:101–114`](../../apps/metis-web/components/shell/page-chrome.tsx)) and the
landing nav ([`apps/metis-web/app/page.tsx:5694`](../../apps/metis-web/app/page.tsx)). A raster
`metis-logo.png` is shown only in the home hero
([`components/home/home-visual-system.tsx:135`](../../apps/metis-web/components/home/home-visual-system.tsx)).
The default Next.js favicon ships in `app/favicon.ico`; there are no
metadata icon files (`app/icon.tsx`, `apple-icon`, `opengraph-image`)
and no Tauri window icon suite derived from a brand source. A
production-grade Pro-tier launch (M15) and a credible privacy-audit
panel (M17, landed) both rely on the app *looking* like itself, which
right now it doesn't.

The design team supplied a finished mark. The question is how to wire
it into the frontend without disrupting the rest of the visual
system, and how to extend it across the system metadata
surfaces (favicon, OG, Tauri) so external impressions of METIS match
the in-app identity.

## Solution

**Three composable React primitives backed by a cleaned, themeable
SVG asset, plus four Next.js metadata files and a Tauri icon-build
script. Motion is applied per-surface — chrome stays still, hero +
splash get a sonar/topography ripple. The lowercase `metis` lockup is
reserved for external surfaces only (option A from brainstorming).**

Architecture:

1. **Cleaned source asset.** SVGO-pass on `m_star_logo_traced.svg` →
   `apps/metis-web/public/brand/metis-mark.svg`. Hard-coded
   `fill="#111111"` becomes `fill="currentColor"` so the path
   inherits color from CSS, enabling white-on-dark in chrome and
   black-on-light wherever needed without two assets. A second
   asset `metis-mark-dark.svg` ships as a static black-on-transparent
   safety net for any light surface (print, third-party embeds).

2. **Ripple ring path data.** Five offset copies of the master
   silhouette — at +8 / +18 / +30 / +44 / +60 px — exported as path
   strings in `apps/metis-web/components/brand/metis-mark-paths.ts`.
   Generated at build time via a one-shot `paper.js` script
   (`scripts/build-metis-ripple-paths.mjs`), or accepted from the
   design team's layered Figma file if they provide it (preferred,
   since the README header clearly already has these layered).
   Either way the ring data is committed, not regenerated at
   runtime.

3. **Three React primitives** in `apps/metis-web/components/brand/`:

   | Component | Responsibility | Key props |
   |---|---|---|
   | `<MetisMark>` | Renders the path only. Inherits color from CSS. | `size`, `className`, `title` (for SR-named instances), `aria-hidden` (for decorative) |
   | `<MetisGlow>` | Wraps a child mark in two-layer halo + ripple rings. | `size`, `animated` ("on-mount" / "loop" / "static"), `intensity` (0..1) |
   | `<MetisLockup>` | `<MetisGlow><MetisMark/></MetisGlow>` + lowercase `metis` wordmark. | `size` ("md"/"lg"), `wordmarkPosition` ("right"/"below") |

   Plus one convenience export `<MetisLoader>` = `<MetisGlow animated="loop">` for in-flight loading states.

4. **Color and glow as design tokens** in `app/globals.css` so the
   palette stays themeable and consistent with the existing
   nebula-blob colors:

   ```css
   --brand-mark:        oklch(0.97 0.01 248);   /* near-white, slight cool tint */
   --brand-glow-near:   170 200 255;            /* cyan-white inner halo (RGB triplet for rgb(var(--…) / α)) */
   --brand-glow-far:    110 160 255;            /* deeper blue outer halo */
   --brand-ripple:      150 190 255;            /* topography rings */
   ```

   The two-layer glow recipe (matches the README, which has both a
   tight inner halo and a softer atmospheric bloom):

   ```css
   .metis-glow {
     filter:
       drop-shadow(0 0 6px  rgb(var(--brand-glow-near) / 0.85))
       drop-shadow(0 0 18px rgb(var(--brand-glow-near) / 0.55))
       drop-shadow(0 0 48px rgb(var(--brand-glow-far)  / 0.35));
   }
   ```

   The internal back-glow visible through the M's negative-space
   notches in the reference is rendered as a duplicated path inside
   the SVG with a heavy `feGaussianBlur` filter, behind the main
   path.

5. **Per-surface motion specification.** All animation goes through
   `motion/react` with `useReducedMotion()` gating, matching the
   pattern already used in `page-chrome.tsx`.

   | Surface | On mount | Idle | Hover/active | Reduced-motion |
   |---|---|---|---|---|
   | Topbar / nav (`<MetisMark>`) | fade 200ms | static | glow brightens 200ms | identical |
   | Home hero (`<MetisGlow>` size 280) | rings 1–5 stagger out 80 ms each over 600ms; glow opacity 0→1 over 800ms ease-out | breathing: glow opacity 0.85↔1.0 over 4.0s sine | n/a | static glow at 0.9, no rings |
   | Splash / `<MetisLoader>` | fade 300ms | sonar: rings re-emit every 2.4s while `loading=true` | n/a | static glow only |
   | Companion dock loading | fade 200ms | breathing only (no rings) | n/a | static |

6. **Surface inventory and edits.** Where each primitive lands:

   | Where | Change | File |
   |---|---|---|
   | Topbar wordmark → mark | replace `<span>METIS<sup>AI</sup></span>` block with `<MetisMark size={28}/>` link to `/` | `apps/metis-web/components/shell/page-chrome.tsx:101–114` |
   | Landing nav wordmark → mark | replace `.metis-logo` text with `<MetisMark size={32}/>` | `apps/metis-web/app/page.tsx:5694` (and prune `.metis-logo` CSS at `:6111–6117`) |
   | Home hero PNG → SVG + glow | replace `<Image src="/metis-logo.png">` with `<MetisGlow><MetisMark size={280}/></MetisGlow>` | `apps/metis-web/components/home/home-visual-system.tsx:135` |
   | `/setup` welcome | add `<MetisLockup size="lg"/>` at top of welcome card | `apps/metis-web/app/setup/page.tsx` |
   | Desktop-ready guard | swap spinner for `<MetisLoader/>` | `apps/metis-web/components/desktop-ready.tsx` |
   | Favicon | new file: `app/icon.tsx` (Next.js generates 32×32 from React) | `apps/metis-web/app/icon.tsx` |
   | Apple touch | new file: `app/apple-icon.tsx` (180×180, white mark on `#06080e` rounded square) | `apps/metis-web/app/apple-icon.tsx` |
   | Open Graph | new file: `app/opengraph-image.tsx` (1200×630, full lockup + static ripple rings) | `apps/metis-web/app/opengraph-image.tsx` |
   | Twitter card | re-export of OG | `apps/metis-web/app/twitter-image.tsx` |
   | Tauri window icon | generate PNG suite (16, 32, 48, 128, 256, 512) at build via `sharp` | `apps/metis-desktop/src-tauri/icons/` + `scripts/build-tauri-icons.mjs` |

7. **External-only lockup discipline (option A).** The lowercase
   `metis` wordmark from the README appears **only** on:
   - `app/opengraph-image.tsx` (OG / Twitter unfurl)
   - `app/setup/page.tsx` welcome card (first impression for a new user)
   - Tauri window splash (handled by the desktop app's startup screen)

   It does **not** replace the existing uppercase `METIS<sup>AI</sup>`
   typographic identity inside the running app. Chrome shows the
   mark only. This was the explicit decision in brainstorming —
   keeps the mark doing the work, avoids dragging an unrelated
   typography migration into a logo rollout.

## Design choices considered and rejected

- **Approach 1 — single monolithic `<MetisLogo>` component.** Rejected:
  one component with `variant` and `glow` and `animated` props ends
  up as a prop-soup that's harder to read at the call site than three
  primitives with clear names. The README's signature ripple
  treatment also doesn't fit cleanly inside a single component
  without conditional rendering branches per surface.
- **Approach 3 — "Living Mark" formed from the existing starfield.** Parked.
  The mark "forming" out of the starfield in `app/layout.tsx` on
  first load is on-brand for the Cosmos pillar and visually
  spectacular, but it's *additive* to approach 2 (the OG image,
  favicon, and Tauri icon are all static surfaces that still need
  the primitives). Best treated as a follow-up milestone after M20
  primitives ship.
- **Adopt the lowercase `metis` lockup app-wide (option B).** Rejected.
  Replacing the uppercase Space Grotesk wordmark in the topbar and
  nav with the lowercase humanist lockup is a typography migration
  pretending to be a logo rollout. The app's existing identity is
  consistent with the rest of the chrome (Space Grotesk display +
  letterspacing); ripping it out should be a separate decision.
- **Keep both wordmarks (option C — mark + uppercase wordmark in chrome,
  lowercase lockup external).** Rejected. Two visual identities to
  maintain, and the chrome ends up redundantly branded (mark *and*
  wordmark side-by-side) where one would do. Option A is more
  disciplined and matches how Vercel / Linear / Anthropic chrome
  themselves.
- **Pure CSS drop-shadow glow only, no internal back-glow.** Rejected.
  CSS `drop-shadow` produces a soft outer halo but cannot reproduce
  the inner glow that bleeds *through* the M's negative-space
  notches in the reference. That requires a duplicated, blurred
  copy of the path *inside* the SVG, layered behind the main path.
  We do both — CSS for the outer halo (cheap, themeable), in-SVG
  filter for the inner back-glow (faithful to the reference).
- **Animate the ripple rings with CSS keyframes.** Rejected. The
  existing pattern in this codebase for orchestrated motion is
  `motion/react` (`page-chrome.tsx`, `brain-graph-3d.tsx` GSAP
  pulses, dock animations). CSS keyframes can't easily stagger
  five elements with `useReducedMotion()` gating from the same
  component, and we'd be inventing a new motion vocabulary for
  one feature.
- **Stroke-based draw-on entrance ("trace the star").** Rejected.
  The source path is filled, not stroked, and the M-shape is
  produced by `fill-rule:evenodd` over a single compound path —
  there isn't a clean stroke order to trace. Converting to strokes
  would be a separate design exercise. Ripple rings are the
  approved entrance treatment.
- **Use `@vercel/og` for the OG image instead of `app/opengraph-image.tsx`.**
  Defer. Next.js's built-in metadata-route OG generation handles
  the static case fine. If the OG ever needs dynamic content (per-
  page titles, A/B variants), revisit.
- **Build-time SVGO inside the Next.js bundler (e.g., `next-svgr`).**
  Defer. The asset gets cleaned once at check-in time via a script
  in `scripts/`. Adding a build-time loader pulls in a dep and
  obscures the output. If we end up shipping more brand SVGs the
  calculus changes.

## Edge cases checked

- **Hard-coded `#111111` fill on the source path.** Replaced with
  `currentColor` in the cleaned asset. Verified that all React
  call sites set color via CSS (`color: var(--brand-mark)`) so the
  inheritance chain works.
- **`fill-rule="evenodd"` on the compound path.** Preserved — the
  M-shape's negative-space notches depend on it. SVGO must not
  drop this attribute (configure `removeUselessStrokeAndFill: false`
  for that path).
- **Reduced-motion users.** All ripples and breathing animations
  gated on `useReducedMotion()` from `motion/react`. Static glow
  remains visible at 0.9 opacity — the *brand* should not
  disappear with reduced motion, only the animation does. Verified
  with a dedicated component test (`metis-glow.reduced-motion.test.tsx`).
- **High-contrast / forced-colors mode.** The mark uses
  `currentColor`, so it inherits the system foreground color in
  forced-colors mode. The glow (CSS `drop-shadow`) is suppressed
  by browsers in forced-colors mode, which is correct. Test
  manually with Windows high-contrast.
- **Mark in a context where the page already announces "Metis"
  (e.g., the home hero, where there's an `<h1>Metis`).** SVG gets
  `aria-hidden="true"` to avoid double-announcement. Mark in
  chrome (topbar link) gets `role="img" aria-label="Metis home"`.
- **Tauri window icon platform variants.** macOS wants `.icns`,
  Windows wants `.ico`, Linux wants a PNG suite. The `sharp`-based
  build script generates all three from the master SVG; commit the
  outputs so non-developer builds don't need to run the script.
- **Favicon at 16×16 and 32×32.** The mark's negative-space M
  notches start to mush together below ~24 px. The favicon
  (`app/icon.tsx`) renders the mark *without* the M notches —
  i.e., a solid star silhouette — so it stays legible at tab-icon
  scale. The full mark is used at 64 px and above (Apple touch,
  OG, Tauri).
- **OG image rasterization.** Ripple rings + glow are *static* in
  the OG image (it's a PNG output). Configure the rings as a
  pre-rendered SVG layer rather than relying on the React motion
  pipeline.
- **Path size after SVGO.** Source is ~5.8 KB of float
  coordinates. Target after SVGO with `floatPrecision: 2` is under
  3 KB. Verified by running SVGO locally during design phase.
- **Dark-only app.** The app sets `<html className="dark">`
  unconditionally in `app/layout.tsx`. We ship the white-on-dark
  asset path as the default; `metis-mark-dark.svg` is committed
  for completeness but not wired into any surface in M20. If
  light-mode lands later, swap via CSS `prefers-color-scheme` on
  `--brand-mark`.

## Tests

- **Component tests** (Vitest + React Testing Library), under
  `apps/metis-web/components/brand/__tests__/`:
  - `metis-mark.test.tsx` — renders SVG with correct `viewBox`,
    inherits `currentColor` (set color via parent, assert computed
    fill on path), accessible name set when `title` prop passed,
    `aria-hidden="true"` when no title.
  - `metis-glow.test.tsx` — renders ripple ring paths in correct
    order, applies `drop-shadow` filter classes, mount-mode
    triggers stagger animation, loop-mode re-emits.
  - `metis-glow.reduced-motion.test.tsx` — mocks
    `useReducedMotion()` to return true; asserts no animation
    classes / no `motion.div` children with non-zero transitions.
  - `metis-lockup.test.tsx` — renders mark + wordmark in correct
    order based on `wordmarkPosition` prop.
- **Visual regression** (Playwright), under
  `apps/metis-web/tests/visual/`:
  - `topbar-mark.spec.ts` — screenshot the topbar of `/` and
    `/chat`; baseline the mark position and size.
  - `hero-glow.spec.ts` — load `/`, wait for ripple animation to
    settle (animation event listener), screenshot the home hero.
  - `og-image.spec.ts` — fetch `/opengraph-image` and screenshot;
    baseline the lockup composition.
- **Build-output checks** in `scripts/check-brand-assets.mjs`:
  - `metis-mark.svg` is under 3 KB.
  - `metis-mark.svg` contains `currentColor`, not `#111111`.
  - `app/icon.tsx`, `app/apple-icon.tsx`, `app/opengraph-image.tsx`
    all exist (presence check; the actual rasterization is
    Next.js's job).
  - `apps/metis-desktop/src-tauri/icons/` contains the expected
    PNG suite (12 files for the standard Tauri set).
- **No backend tests.** The rollout is frontend-only. Existing
  pytest suite (`tests/test_api_app.py`, etc.) untouched.

## Phase plan (proposed)

A first cut. The claimant is free to restructure, but every phase
has an explicit *what NOT to do* boundary.

### Phase 1 — Asset prep + primitives

**Goal:** the three React components exist, render correctly, and
have tests. No surface swaps yet.

- SVGO-clean `m_star_logo_traced.svg` →
  `apps/metis-web/public/brand/metis-mark.svg`.
- Generate ripple ring path data (script or design hand-off) →
  `apps/metis-web/components/brand/metis-mark-paths.ts`.
- Add design tokens to `app/globals.css`.
- Implement `<MetisMark>`, `<MetisGlow>`, `<MetisLockup>`,
  `<MetisLoader>` in `components/brand/`.
- Component tests pass.

**Not this phase:** any surface swaps; metadata files; Tauri.

### Phase 2 — In-app surface swaps

**Goal:** chrome and hero use the new primitives. The old PNG and
typographic logo blocks are removed.

- Edit `components/shell/page-chrome.tsx` (topbar).
- Edit `app/page.tsx` (landing nav + delete `.metis-logo` CSS).
- Edit `components/home/home-visual-system.tsx` (hero).
- Edit `components/desktop-ready.tsx` (loader).
- Edit `app/setup/page.tsx` (lockup on welcome).
- Delete unused `public/metis-logo.png` if no other reference.
- Visual regression baselines updated.

**Not this phase:** favicon / OG / Tauri.

### Phase 3 — System metadata

**Goal:** browser tabs, social unfurls, and the Tauri window all
show the brand.

- Add `app/icon.tsx`, `app/apple-icon.tsx`, `app/opengraph-image.tsx`,
  `app/twitter-image.tsx`.
- Delete the default `app/favicon.ico` (Next.js prefers
  `icon.tsx` when both exist; explicit deletion avoids confusion).
- Write `scripts/build-tauri-icons.mjs`; run it; commit the
  generated PNG suite under `apps/metis-desktop/src-tauri/icons/`.
- Update `apps/metis-desktop/src-tauri/tauri.conf.json` if the
  icon path needs adjusting.
- OG visual regression baseline.

**Not this phase:** motion polish (Phase 4).

### Phase 4 — Motion polish

**Goal:** the per-surface motion spec is fully implemented and
tuned.

- Hero ripple-on-mount + breathing.
- `<MetisLoader>` sonar loop.
- Topbar hover glow.
- All gated on `useReducedMotion()`.
- Visual regression baselines for animated surfaces.

**Not this phase:** Approach 3 ("Living Mark" — formation from
starfield). Parked.

## What NOT to do in M20

- **Don't migrate the in-app wordmark typography.** This is option B
  from brainstorming, explicitly rejected. The lowercase `metis`
  lockup is external-only.
- **Don't introduce a new motion library.** `motion/react` is
  already a dep and matches the existing patterns; adding GSAP /
  Anime.js / Lottie for this would be churn.
- **Don't hand-author multiple SVG variants.** One source asset,
  themed via `currentColor`. The dark-on-light `metis-mark-dark.svg`
  is a one-liner exception, committed for safety, not actively
  wired anywhere.
- **Don't delete `metis-logo.png` until the hero swap lands.**
  Hero is the only current consumer; staged removal at the end of
  Phase 2.
- **Don't put the audit-panel-style SSE / live-update treatment
  on the loader.** The loader is a brand surface, not a data
  surface; the breathing should be steady, not data-driven.
- **Don't ship Approach 3 inside M20.** Park as a follow-up
  milestone after M20 lands cleanly.
- **Don't touch the dark/light theme system.** The app is
  dark-only today (M01 / M02 territory). Light-mode adaptation is
  a separate decision.

## Coordination

- **M01 (Preserve & productise, Rolling)** — has been triaging
  every visible UX defect on the home page. The hero swap (Phase 2)
  changes a hotspot file (`apps/metis-web/components/home/home-visual-system.tsx`)
  that M01 may also touch. Coordinate before Phase 2 lands; if M01
  is mid-edit there, defer or rebase.
- **M02 (Constellation 2D refactor, Landed)** — owns the home
  visual system. M20 is purely additive at the hero (replace one
  PNG with a primitive); no architectural conflict.
- **M14 (The Forge, Draft)** — the Forge will eventually need a
  technique-card aesthetic. The brand primitives in `components/brand/`
  give them a glow recipe to reuse if relevant. Soft coordination.
- **M15 (Pro tier + public launch, Draft needed)** — the OG image
  and the Tauri window icon are load-bearing for launch
  credibility. M20 unblocks M15's external-impressions work. The
  `metis` lockup on the OG is the marketing-facing surface.
- **M17 (Network audit, Landed)** — `app/icon.tsx`, `apple-icon.tsx`,
  and `opengraph-image.tsx` are statically rendered at build-time
  by Next.js — no outbound calls. The Google Fonts `@import` in
  `app/page.tsx:5309` (already flagged in M17's notes) is a separate
  posture issue and **out of scope for M20**.

## Key files the next agent will touch

Frontend (new):
- `apps/metis-web/components/brand/metis-mark.tsx`
- `apps/metis-web/components/brand/metis-glow.tsx`
- `apps/metis-web/components/brand/metis-lockup.tsx`
- `apps/metis-web/components/brand/metis-loader.tsx`
- `apps/metis-web/components/brand/metis-mark-paths.ts`
- `apps/metis-web/components/brand/index.ts`
- `apps/metis-web/components/brand/__tests__/*.test.tsx`
- `apps/metis-web/public/brand/metis-mark.svg`
- `apps/metis-web/public/brand/metis-mark-dark.svg`
- `apps/metis-web/public/brand/metis-lockup.svg`
- `apps/metis-web/app/icon.tsx`
- `apps/metis-web/app/apple-icon.tsx`
- `apps/metis-web/app/opengraph-image.tsx`
- `apps/metis-web/app/twitter-image.tsx`
- `apps/metis-web/tests/visual/topbar-mark.spec.ts`
- `apps/metis-web/tests/visual/hero-glow.spec.ts`
- `apps/metis-web/tests/visual/og-image.spec.ts`
- `scripts/build-metis-ripple-paths.mjs` *(if rings come from script, not design)*
- `scripts/build-tauri-icons.mjs`
- `scripts/check-brand-assets.mjs`

Frontend (modified):
- `apps/metis-web/components/shell/page-chrome.tsx` *(topbar)*
- `apps/metis-web/app/page.tsx` *(landing nav + CSS prune)*
- `apps/metis-web/components/home/home-visual-system.tsx` *(hero)*
- `apps/metis-web/components/desktop-ready.tsx` *(loader)*
- `apps/metis-web/app/setup/page.tsx` *(lockup on welcome)*
- `apps/metis-web/app/globals.css` *(design tokens)*
- `apps/metis-web/app/layout.tsx` *(if metadata adjustments needed for OG)*

Frontend (deleted):
- `apps/metis-web/public/metis-logo.png` *(after Phase 2 hero swap lands)*
- `apps/metis-web/app/favicon.ico` *(after Phase 3 `app/icon.tsx` lands)*

Tauri:
- `apps/metis-desktop/src-tauri/icons/*` *(generated PNG suite)*
- `apps/metis-desktop/src-tauri/tauri.conf.json` *(icon path, if needed)*

ADRs: none required. M20 is a visual implementation, not an
architectural decision. The wordmark-discipline call (option A) is
captured here in the design doc and in `plans/IDEAS.md`'s triage
record; if it warrants an ADR later, file separately.

## Prior art to read before starting

- `m_star_logo_traced.svg` (the source asset, attached 2026-04-28).
- README header reference image showing white mark + cyan halo +
  topographic ripple rings + lowercase `metis` lockup.
- `apps/metis-web/components/shell/page-chrome.tsx` —
  `useReducedMotion()` usage pattern for the topbar header
  (lines 66–80, 93–155). Mirror the gating shape.
- `apps/metis-web/app/layout.tsx` — the existing starfield + nebula
  blob colors (`rgba(0,180,200,0.07)` and similar). The brand glow
  tokens should harmonize with these; specifically, `--brand-glow-far`
  in the `110 160 255` range is intentionally bluer-than-the-nebula
  so the mark *reads* as a feature against, not part of, the
  starfield.
- `apps/metis-web/components/icons/` — the existing animated-icon
  pattern (`BrainIcon`, etc.) using ref-driven start/stop
  animation. Brand primitives don't need this — they're not
  hover-interactive lucide-style icons — but the file structure
  convention (one component per file, barrel export) is the same.
- VISION.md — pillar #3 *Cosmos* and the role of the constellation
  metaphor. The mark is the visual anchor for that metaphor; the
  glow ties it to the starfield. A logo rollout is also a
  *"preserve and productise"* (M01) act in spirit — finishing the
  identity an existing UI was missing.
- Reference projects (style precedent only, not for copying):
  Vercel, Linear, Anthropic chrome — mark-only in topbar, full
  lockup on external surfaces. This is the discipline option A
  encodes.

## Out of scope (intentional, parked for follow-up)

- **Approach 3 — "Living Mark" formed from the existing starfield.**
  Filed in `plans/IDEAS.md` as a follow-up after M20.
- **Wordmark typography choice for the lockup.** The README
  reference looks like Inter Tight or Geist, not Space Grotesk.
  M20 ships **Inter Tight Medium** as a placeholder (uses an
  already-loaded font weight; see `app/layout.tsx:9` Inter import
  — Inter Tight is the same Google-Fonts family with tighter
  spacing). If the design team wants Geist or a custom face, that's
  a separate ticket and a separate font load.
- **Light-mode brand variant.** The app is dark-only today.
  `metis-mark-dark.svg` ships as an asset-only safety net; not
  wired anywhere in M20.
- **Animated SVG / Lottie export.** Only relevant for surfaces we
  can't render React on (Discord embeds, README itself if updated
  inline). Add later if needed.
- **Brand-extension components** (badges, pills, gradient
  surfaces beyond the glow recipe). M20 ships the mark and lockup
  only. Anything else is its own milestone.
