---
Milestone: Metis logo rollout (M20)
Status: Ready
Claim: unclaimed
Last updated: 2026-04-28 by claude/cranky-northcutt-42501d
Vision pillar: Cross-cutting + Cosmos
---

## Progress

Plan doc stub created on 2026-04-28 alongside the intake-workflow
promotion of the design-team-supplied M-star logo asset
(`m_star_logo_traced.svg`). Full design captured in
[`docs/plans/2026-04-28-metis-logo-rollout-design.md`](../../docs/plans/2026-04-28-metis-logo-rollout-design.md)
— that document is the source of truth for architecture, motion
spec, surface inventory, edge cases, and phase plan. **No code
written yet.**

User decisions locked in during brainstorming (2026-04-28):

- **Scope 3** — brand surfaces (topbar, nav, hero, splash) +
  system metadata (favicon, OG, Apple touch, Tauri suite) +
  per-surface motion treatment (sonar/topography ripple).
- **Option A wordmark discipline** — mark replaces the
  `METIS<sup>AI</sup>` typographic wordmark in chrome; the
  lowercase `metis` humanist lockup from the README header is
  reserved for *external* surfaces only (OG image, `/setup`
  welcome card, Tauri splash). The existing uppercase Space
  Grotesk identity is **not** migrated by M20.
- **Approach 2** ("Sonar Mark") for the implementation —
  three composable primitives (`<MetisMark>`, `<MetisGlow>`,
  `<MetisLockup>`) backed by a cleaned `currentColor`-themed SVG.
- **Approach 3** ("Living Mark" formed from the existing
  starfield) is **parked** as a follow-up milestone after M20
  lands cleanly.

## Next up

The first agent to claim this milestone should:

1. **Read the design doc end-to-end** —
   [`docs/plans/2026-04-28-metis-logo-rollout-design.md`](../../docs/plans/2026-04-28-metis-logo-rollout-design.md).
   Don't shortcut from this stub; the design captures every
   non-obvious choice (currentColor theming, two-layer glow
   recipe, reduced-motion gating, favicon-at-16px notch
   simplification, etc.).
2. **Coordinate with M01.** The Phase 2 hero swap touches
   `apps/metis-web/components/home/home-visual-system.tsx`,
   which is an M01 audit hotspot. Confirm M01 isn't mid-edit
   there before starting Phase 2.
3. **Start Phase 1 — asset prep + primitives.**
   - SVGO-clean `m_star_logo_traced.svg` to
     `apps/metis-web/public/brand/metis-mark.svg` with
     `fill="currentColor"` and `floatPrecision: 2`.
   - Generate ripple ring path data — preferred path is to
     ask the design team for the layered Figma source
     (the README header clearly already has these as
     separate layers). Fallback: a one-shot
     `paper.js`-based script at
     `scripts/build-metis-ripple-paths.mjs`.
   - Add brand design tokens to `app/globals.css`
     (`--brand-mark`, `--brand-glow-near`,
     `--brand-glow-far`, `--brand-ripple`).
   - Implement the four React components in
     `apps/metis-web/components/brand/` plus their tests.
   - **Do not start surface swaps until Phase 1 lands and
     the components are reviewed.**

## Blockers

- **None.** All upstream decisions are made; the source asset is in
  hand; the design doc is approved.
- **Soft dep on design hand-off:** the layered Figma source for
  the ripple rings is preferred over a generated approximation.
  If the design team can't supply it within the Phase 1 window,
  fall back to the `paper.js` script — non-blocking.

## Notes for the next agent

- **The brand should not disappear with reduced motion.** Static
  glow stays at 0.9 opacity even when ripples and breathing are
  disabled. This is verified in
  `metis-glow.reduced-motion.test.tsx` — don't accidentally
  collapse "no motion" into "no glow".
- **The favicon at 16/32 px renders the mark *without* the M's
  negative-space notches** — i.e., a solid star silhouette. The
  full mark with notches is used at 64 px and above. This is to
  prevent the M's interior from mushing into a black blob in the
  browser tab. Generate the simplified silhouette as part of
  Phase 3.
- **`fill-rule="evenodd"` is load-bearing on the source path.**
  SVGO must not drop it. Configure
  `removeUselessStrokeAndFill: false` for that pass.
- **Don't ship Approach 3 inside M20.** Spinning up the
  starfield-formation animation alongside the primitives
  expands scope by an order of magnitude and risks Phase 1
  bleeding into Phase 4 timelines. File a follow-up idea after
  M20 lands.
- **The `metis` lowercase wordmark in the README header is
  almost certainly Inter Tight or Geist, not Space Grotesk.**
  M20 ships **Inter Tight Medium** as a placeholder (Inter is
  already loaded in `app/layout.tsx:9`; Tight is the same
  family with reduced spacing). If the design team specifies
  a different face, file a separate ticket — don't pull a font
  migration into this milestone.
- **The Google Fonts `@import` in `app/page.tsx:5309` is M17
  territory** (privacy/network audit), not M20. The OG image
  must not introduce *new* Google Fonts imports — use Next.js
  font subsetting (the existing Inter / Space Grotesk imports
  in `layout.tsx`) so OG generation stays self-contained.
- **`metis-mark-dark.svg` (black-on-transparent) ships in
  `public/brand/` for safety but is not wired into any surface
  in M20.** The app is dark-only. If light-mode lands later,
  the asset is already there to swap via `prefers-color-scheme`
  on `--brand-mark`.
- **Visual regression baselines need to be regenerated when
  the ripple animation timing or color tokens change.** Don't
  commit a baseline drift without rerunning the spec — the
  Playwright suite is the single source of truth for "the brand
  looks right".
