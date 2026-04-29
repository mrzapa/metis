---
Milestone: Metis logo rollout (M20)
Status: In progress (PR pending)
Claim: claude/cranky-northcutt-42501d
Last updated: 2026-04-28 by claude/cranky-northcutt-42501d
Vision pillar: Cross-cutting + Cosmos
---

## Progress

Plan doc stub created on 2026-04-28 alongside the intake-workflow
promotion of the design-team-supplied M-star logo asset
(`m_star_logo_traced.svg`). Full design captured in
[`docs/plans/2026-04-28-metis-logo-rollout-design.md`](../../docs/plans/2026-04-28-metis-logo-rollout-design.md)
and the step-by-step implementation in
[`docs/plans/2026-04-28-metis-logo-rollout-implementation.md`](../../docs/plans/2026-04-28-metis-logo-rollout-implementation.md).

**All four phases shipped on `claude/cranky-northcutt-42501d` (2026-04-28).**

- **Phase 1 — primitives.** Cleaned SVG asset (`public/brand/metis-mark.svg`,
  3.52 KB, currentColor-themed via `apps/metis-web/scripts/clean-brand-svg.mjs`).
  Brand design tokens in `tokens.css` + `.metis-glow` utility in `globals.css`.
  Four React primitives in `apps/metis-web/components/brand/`: `<MetisMark>`,
  `<MetisGlow>` (with feMorphology ripple rings — tactical refinement of
  the design doc's "offset paths" approach), `<MetisLockup>`, `<MetisLoader>`.
  22 brand tests passing. Barrel export.
- **Phase 2 — surface swaps.** Topbar wordmark → mark (`page-chrome.tsx`).
  Landing nav wordmark → mark + dead `.metis-logo` CSS pruned (`app/page.tsx`).
  Home hero `metis-logo.png` → `<MetisMark>` preserving the existing M02
  orbital halo (deviation from design doc — see design doc Phase 2 commit
  message for rationale; `<MetisGlow>` ripples would have competed with the
  existing rotating orbital rings). `<MetisLockup>` on `/setup` welcome.
  `<MetisLoader>` on the desktop-ready guard. Unused PNG deleted.
- **Phase 3 — system metadata.** `app/icon.tsx` (32×32 simplified silhouette
  for browser tabs), `app/apple-icon.tsx` (180×180 full mark), `app/opengraph-image.tsx`
  (1200×630 lockup + glowing mark), `app/twitter-image.tsx` (alias). Default
  `favicon.ico` removed. **Static-export fix:** `runtime = "edge"` is incompatible
  with the project's `output: "export"` config; switched all four routes to
  `dynamic = "force-static"`. Tauri icon suite regenerated from the SVG via
  `apps/metis-web/scripts/build-tauri-icons.mjs` (sharp + `pnpm tauri icon`) — full desktop
  + mobile + Windows Store suite (~56 files, 392 KB).
- **Phase 4 — motion polish.** Topbar hover-glow effect via `motion/react`
  `whileHover` (200ms ease-out, reduced-motion gated). Hero ripple timing
  defaults accepted (no tweaks needed). Brand `README.md` documenting the
  primitive surface, theming, reduced-motion contract, how to update the
  asset, and the deviations from the original design doc.

**Final gate:** 527 tests passing, 0 lint errors, `pnpm build` succeeds with
all 4 metadata routes prerendered as static content.

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

1. **PR review.** Branch `claude/cranky-northcutt-42501d` is pushed
   and [PR #574](https://github.com/mrzapa/metis/pull/574) opened.
   Block on user/team review.
2. **On merge:** flip Status to `Landed` in IMPLEMENTATION.md M20 row
   and add the merge SHA. Move row to a `## Landed` section if needed.

## Follow-ups filed (post-PR-open, 2026-04-29)

- **"Living Mark" formation from starfield** — filed in
  [`plans/IDEAS.md`](../IDEAS.md) under *Open ideas*. **Promote
  decision locked, gated on M20 PR #574 landing.** When M20 merges
  to `main`, the next agent runs `superpowers:brainstorming` on
  the IDEAS entry, produces an M21 design doc, and adds a row to
  `IMPLEMENTATION.md`. Stacking it on the open M20 PR risks
  merge-conflict pain in `home-visual-system.tsx` (the same hero
  M20 modifies).
- **Wordmark typography lock-in** (Inter Tight Medium placeholder
  in `<MetisLockup>`) — filed in [`plans/IDEAS.md`](../IDEAS.md)
  *Iced* section as **Parked** 2026-04-29. The placeholder
  degrades gracefully (Inter is already loaded); revisit when
  design specifies a typeface or marketing surfaces ship
  publicly. One-hour patch when triggered.
- **Tauri `bundle.icon` whitelist** — investigated and **resolved
  as a non-issue** on 2026-04-29. The existing 5-file list is
  Tauri 2's standard desktop set; the additional 50+ files
  generated by `tauri icon` (Microsoft Store tiles, iOS AppIcon,
  Android mipmap) are platforms we don't ship to today. Documented
  in
  [`apps/metis-desktop/src-tauri/icons/README.md`](../../apps/metis-desktop/src-tauri/icons/README.md)
  so future agents know what's bundled vs available.

## Blockers

- **None.** Implementation complete on branch; PR pending review.

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
