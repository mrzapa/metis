# METIS — Implementation Index

> **Read first:** [`VISION.md`](../VISION.md) (product), [`plans/README.md`](README.md)
> (how this folder works), [`docs/adr/`](../docs/adr/) (architectural decisions).

This is the **single source of truth for what is being worked on in METIS and
what comes next.** Every row is a milestone from `VISION.md`. Agents claim rows,
do the work, update the row when they stop.

**Last reviewed:** 2026-05-01 (M14 Phase 4c + Phase 6 reconciled from `in PR` to `Landed` — PR #583 (`e841e38`, 2026-05-01) merged the news-comet auto-absorb bridge and PR #585 (`15da54e`, 2026-05-01) merged the trace-integration cards, leaving Phase 7 (stretch — `.metis-skill` export/import) as the only remaining declared phase. claude/jovial-volhard-3fa662 holds the reconciliation claim while assessing Phase 7. Earlier 2026-04-29 (M14 Phase 1 reconciled to Landed — PR #575 (`0bd11b4`, 2026-04-29) merged the Forge route, ADR 0014, the static technique inventory backend, the read-only Forge shell page, and the `Hammer → /forge` nav entry. Phase 2a — registry promotion (`forge_registry.py` + `TechniqueDescriptor` + live-settings predicates) and read-only technique-card rendering — claimed by `claude/m14-phase2-cards`; constellation Skills-sector star generation split into a Phase 2b follow-up. Earlier 2026-04-28 pass: M20 implemented end-to-end on `claude/cranky-northcutt-42501d` and flipped to `Ready for review` — 4 phases / ~17 commits delivering brand primitives, surface swaps, Next.js metadata routes, Tauri icon suite, and motion polish. PR pending. Earlier same-day pass: M20 added as `Ready` after intake-workflow promotion of the design-team-supplied M-star logo asset; full design captured in `docs/plans/2026-04-28-metis-logo-rollout-design.md`, plan doc stub at `plans/metis-logo-rollout/plan.md`. Earlier 2026-04-27 pass: M12 row reconciled to `Landed` to match `plans/interactive-star-catalogue/plan.md` frontmatter — Phases 0–4 shipped via `70eeb40` + `771634f` on 2026-04-24, Phase 4c storage migration deferred per ADR 0012; M18/M19 stretch stubs created at `plans/lora-stretch/plan.md` and `plans/mobile-stretch/plan.md`. Earlier 2026-04-26 pass flipped M13 from `In progress` to `Landed`: the Seedling + Feed milestone shipped its full structural surface via Phases 1-7 plus the heartbeat-widget polish (PR #549) and the edge-pulse follow-up (PR #567). Retrospective + deferred-items audit captured in `plans/seedling-and-feed/plan.md` *Retrospective* section. 2026-04-24 (M12 row flipped from `Draft needed` to `Ready` and claimed by `claude/m12-plan-and-claim`; new plan doc `plans/interactive-star-catalogue/plan.md` supersedes `docs/plans/2026-04-05-interactive-star-catalogue.md` — verified genuinely open: no catalogue-search overlay, catalogue-star inspector, spectral/magnitude filter, or promote-non-addable flow on `main`. Earlier same-day pass flipped M10 from `Draft` to `Landed` to close the reconciliation noted on 2026-04-22 — the underlying homological-scaffold work shipped in `cc3923f` (2026-03-28) + `6fa1ff2` (2026-04-05) and the plan.md was marked Landed via PR #529 (`95480be`, 2026-04-22). Prior 2026-04-22 pass reconciled M17 Phase 7 to `Landed` via PR #527 (`3cde870`, 2026-04-21); Phase 8 (Tauri-layer enforcement) remains a declared v2 stretch. 2026-04-20 pass reconciled stale-ready M03/M04/M05/M06 rows to Landed after a code-vs-plan audit, and reconciled M17 Phase 6 via PR #525). See [`Prompt agents.md`](Prompt%20agents.md) for the onboarding prompt to give a fresh agent.

## Quick start for a fresh agent

1. Scan the table below. Find a row with `Status: Next up` and no `Claim`.
2. Write your session ID into `Claim` and today's date into `Last updated`.
3. Open the linked `Plan doc`. Read its *Progress* and *Next up* sections.
4. Do the work. Update the plan doc's *Progress* as you go.
5. When you stop — finished or not — update *Next up* and *Notes for the next
   agent* in the plan doc so whoever comes next can continue.

## Legend

- **Status**: `Draft` (plan being shaped) · `Ready` (plan complete, can be
  picked up) · `Next up` (currently at the front of the queue) · `In progress`
  (someone is actively working — `Claim` must be non-empty) ·
  `Rolling` (ongoing reference plan that anyone can chip at; no single claim
  expected — used for M01 preserve & productise) ·
  `Blocked` · `Landed` · `Superseded`.
- **Claim**: session ID, agent name, or branch name. Blank = available.
  Required whenever `Status` is `In progress`; optional for `Rolling`.
- **Pillar**: 🌌 Cosmos · 🌱 Companion · 🧠 Cortex · 🔧 Cross-cutting.

---

## Roadmap order (from VISION.md)

The vision's ordered roadmap is:

1. **Preserve and productise** — finish what exists, kill dead paths.
2. **The Seedling and the Feed** — always-on local LLM + continuous ingestion.
3. **The Forge** — technique gallery.
4. **Pro tier and public launch.**
5. **Dreams and self-evolution** — skills from traces, marketplace.
6. **Personal Evals and Network Audit.**
7. **Stretch:** LoRA fine-tuning.
8. **Stretch:** mobile read-only companion.

Cross-cutting milestones (Cosmos UI, infra) run alongside.

---

## Master milestone table

| # | Milestone | Pillar | Status | Plan doc | Claim | Last updated | Depends on |
|---|---|---|---|---|---|---|---|
| M01 | **Preserve & productise** — audit, surface, cut dead paths | 🔧 | Rolling | [`docs/preserve-and-productize-plan.md`](../docs/preserve-and-productize-plan.md) | — | 2026-04-18 | — |
| M02 | **Constellation 2D refactor** — retire 3D sphere, 2D archetype dive (ADR 0006) | 🌌 | Landed | [`plans/constellation-2d-refactor/plan.md`](constellation-2d-refactor/plan.md) | Phases 0-8 landed (merge `0449c2e`, 2026-04-19) | 2026-04-19 | — |
| M03 | **IterRAG convergence** — agentic loop with convergence detection | 🧠 | Landed | [`docs/plans/2026-04-01-hermes-sotaku-implementation.md`](../docs/plans/2026-04-01-hermes-sotaku-implementation.md) (Phase 1) | Landed via PR #501 (`ea75561`, 2026-04-18) | 2026-04-20 | — |
| M04 | **Reverse curriculum** — faculty hardness scoring drives research order | 🧠 | Landed | [`docs/plans/2026-04-04-reverse-curriculum-implementation.md`](../docs/plans/2026-04-04-reverse-curriculum-implementation.md) | Landed via PR #465 (`46cd2e4`, 2026-04-04) | 2026-04-20 | M03 |
| M05 | **Parallel research** — concurrent faculty workers + batch fixes | 🧠 | Landed | [`docs/plans/2026-04-04-parallel-research-implementation.md`](../docs/plans/2026-04-04-parallel-research-implementation.md) | Landed via PR #466 (`5327e84`, 2026-04-04) | 2026-04-20 | — |
| M06 | **Skill self-evolution** — candidate capture from high-convergence traces | 🧠🌱 | Landed | [`docs/plans/2026-04-01-hermes-sotaku-implementation.md`](../docs/plans/2026-04-01-hermes-sotaku-implementation.md) (Phase 3) | Landed via PR #461 (`4517b77`, 2026-04-03); quality-gate follow-up `2cb29be` | 2026-04-20 | M03 |
| M07 | **Hermes v0.7.0 patterns** — context compression, skill index, credential pool | 🔧 | Landed | [`docs/plans/2026-04-04-hermes-v070-implementation.md`](../docs/plans/2026-04-04-hermes-v070-implementation.md) | Landed via PR #464 (`551d01b`, 2026-04-04) | 2026-04-04 | — |
| M08 | **Hybrid search** — BM25 + vector alpha-blend retrieval | 🧠 | Landed | [`docs/plans/2026-04-04-hybrid-search-design.md`](../docs/plans/2026-04-04-hybrid-search-design.md) | Landed (`8d6ed98`, 2026-04-04) | 2026-04-04 | — |
| M09 | **Companion realtime visibility** — SSE thought log + constellation auto-refresh | 🌱 | Landed | [`plans/companion-realtime-visibility/plan.md`](companion-realtime-visibility/plan.md) | Landed (`68634ba`, 2026-04-18) | 2026-04-18 | — |
| M10 | **Tribev2 homological scaffold** — persistent homology over BrainGraph | 🌱🌌 | Landed | [`plans/trive-v2-homological-scaffold/plan.md`](trive-v2-homological-scaffold/plan.md) | Landed (`cc3923f`, 2026-03-28 + `6fa1ff2`, 2026-04-05); plan.md reconciled via PR #529 (`95480be`, 2026-04-22); row reconciled 2026-04-24 | 2026-04-24 | — |
| M11 | **Agent-native state + polling** — KV store, structured chat bridge | 🔧 | Landed | [`docs/plan/agent-native-impl-20260402/plan.yaml`](../docs/plan/agent-native-impl-20260402/plan.yaml) | Landed via PR #459 (`5fd0a3f`, 2026-04-03) | 2026-04-03 | — |
| M12 | **Interactive star catalogue** — searchable, filterable star explorer | 🌌 | Landed | [`plans/interactive-star-catalogue/plan.md`](interactive-star-catalogue/plan.md) (supersedes `docs/plans/2026-04-05-interactive-star-catalogue.md`) | Phases 0–4 landed (`70eeb40` + `771634f`, 2026-04-24); Phase 4c storage migration deferred per ADR 0012 | 2026-04-27 | — |
| M13 | **Seedling + Feed** — always-on quantized local model, news-comet ingestion, growth stages | 🌱 | Landed | [`plans/seedling-and-feed/plan.md`](seedling-and-feed/plan.md) | Landed via PRs #537 (Phase 1), #541 (Phase 2), #542 + #545 (Phase 3), #548 (Phase 4a), #550 (Phase 4b), #555 (Phase 5), #558 (Phase 6), #561 (Phase 7), #549 (heartbeat widget), #567 (edge-pulse follow-up) — 2026-04-24 → 2026-04-26 | 2026-04-26 | M01 |
| M14 | **The Forge** — technique gallery UI, togglable frontier modules | 🌱🧠 | Landed | [`plans/the-forge/plan.md`](the-forge/plan.md) | Phases 1–6 landed (PRs #575–#585; Phase 4c `e841e38`, Phase 6 `15da54e`). Phase 7 (stretch — `.metis-skill` export) remains as an unclaimed follow-up. Prior `claude/jovial-volhard-3fa662` reconciliation claim cleared 2026-05-01 — no open PR | 2026-05-01 | M02, M06, M12 |
| M15 | **Pro tier + public launch** — paywall, skill pack, HN/r/LocalLLaMA launch | 🔧 | Draft needed | [`plans/pro-tier-launch/plan.md`](pro-tier-launch/plan.md) (harvest stub) | — | 2026-04-18 | M13, M14 |
| M16 | **Personal evals** — track companion improvement on user's specific tasks | 🌱 | In progress | [`plans/personal-evals/plan.md`](personal-evals/plan.md) | Phase 1 (ADR 0010 + 0011 grading-signal & storage) in PR #594 (`claude/m16-phase1-adrs`) | 2026-05-01 | M13 |
| M17 | **Network audit** — outbound call panel, per-provider block, offline proof | 🔧 | Landed | [`plans/network-audit/plan.md`](network-audit/plan.md) | Phases 1-7 landed (PRs #516-#521, #525, #527; Phase 7 merge `3cde870`, 2026-04-21); Phase 8 (Tauri-layer enforcement) deferred as v2 stretch | 2026-04-22 | — |
| M18 | **LoRA fine-tuning (stretch)** — companion weights adapt to user data | 🌱 | Draft needed | [`plans/lora-stretch/plan.md`](lora-stretch/plan.md) (stub) | — | 2026-04-27 | M13, M16 |
| M19 | **Mobile companion (stretch)** — Tauri Mobile or PWA, read-only | 🌌 | Draft needed | [`plans/mobile-stretch/plan.md`](mobile-stretch/plan.md) (stub) | — | 2026-04-27 | M15 |
| M20 | **Metis logo rollout** — M-star mark + glow primitives, brand-system metadata (favicon / OG / Tauri), per-surface motion | 🔧🌌 | Ready | [`plans/metis-logo-rollout/plan.md`](metis-logo-rollout/plan.md) (design: [`docs/plans/2026-04-28-metis-logo-rollout-design.md`](../docs/plans/2026-04-28-metis-logo-rollout-design.md), impl: [`docs/plans/2026-04-28-metis-logo-rollout-implementation.md`](../docs/plans/2026-04-28-metis-logo-rollout-implementation.md)) | Prior `claude/cranky-northcutt-42501d` claim cleared 2026-05-01 — 4 phases were locally shipped on that branch but no PR was ever opened; next agent should diff `claude/cranky-northcutt-42501d` (if still present on origin) against `main` to harvest, or rebuild from the impl plan | 2026-04-28 | — |
| M21 | **UI critical-eye triage** — bug bash from full-app QA walk: hydration mismatch, dead routes, request-storm, nav inconsistency, overlay/safe-area issues | 🔧 | In progress | [`plans/ui-critical-triage/plan.md`](ui-critical-triage/plan.md) | P0 batch (#1, #2, #4, #5) landed 2026-05-01 via PR #588 (`7604156` + Codex fix `3f732cf`). Prior `claude/objective-napier-432f1e` claim cleared. claude/m21-p0-fixes picking up P1 (#6 request-storm dedup) | 2026-05-01 | — |
| M22 | **Comet headline labels** — path-text label along comet tail + canvas hover card with title/summary/faculty/source/age, click-to-open | 🌌 | Landed | [`plans/comet-headline-labels/plan.md`](comet-headline-labels/plan.md) (design: [`docs/plans/2026-05-01-comet-headline-labels-design.md`](../docs/plans/2026-05-01-comet-headline-labels-design.md), impl: [`docs/plans/2026-05-01-comet-headline-labels-implementation.md`](../docs/plans/2026-05-01-comet-headline-labels-implementation.md)) | All 5 phases landed via PR #589, #590, #592, #593, #595; live preview QA + BiDi remain deferred with documented triggers in plan stub | 2026-05-01 | M13 |

### Superseded

| # | Milestone | Superseded by |
|---|---|---|
| — | `2026-04-04-star-dive-sphere-design.md` (3D sphere dive) | ADR 0006 + M02 |
| — | `2026-04-04-star-dive-sphere-overhaul.md` (3D sphere impl) | ADR 0006 + M02 |
| — | `2026-04-04-star-closeup-aspect-ratio-fix.md` (fullscreen shader fix) | ADR 0006 + M02 (partially) |
| — | `2026-04-05-interactive-star-catalogue.md` (Phase 2 WebGL renderer) | M02 landed renderer + data wiring; interactive explorer layer needs a fresh plan (see M12 row above) |
| — | ADR 0001, 0002, 0003 | ADR 0004 |

---

## Milestone scope — one-line summaries

Use these to spot overlap before claiming. If two milestones touch the same
files, coordinate.

- **M01** — Repo-wide cleanup. Touches: Qt refs, `metis-reflex`, `metis-web-lite`,
  onboarding, README, docs.
- **M02** — 2D constellation refactor. Touches: `apps/metis-web/components/home/*`,
  `apps/metis-web/lib/landing-stars/*`, `star-observatory-dialog.tsx`,
  `star-name-generator.ts`. **Heavy overlap with M12.**
- **M03–M07** — Backend/RAG. Touches: `metis_app/engine/*`, `metis_app/services/*`,
  `metis_app/api_litestar/*`. Can run mostly parallel to M02.
- **M08** — `metis_app/services/vector_store.py`, retrieval pipeline. Parallel-safe.
- **M09** — Autonomous research service + dock UI. Parallel-safe.
- **M10** — BrainGraph topology. Parallel-safe unless M02 touches brain view.
- **M11** — App state KV + SSE. Foundational; unblocks several UX flows.
- **M12** — Interactive explorer UI on top of the already-landed M02 renderer + Phase 1 data layer. Touches `apps/metis-web/app/page.tsx` (hotspot), `components/home/*`, and whatever click/inspect/search surfaces get added. Old design doc (`2026-04-05-interactive-star-catalogue.md`) is Superseded; needs a fresh plan.
- **M13** — New process (`metis_app/seedling/`?), continuous ingestion, companion
  stages. Coordinate with M09 (shared dock surface).
- **M14** — Thin UI surface over already-thick technique infrastructure at `apps/metis-web/app/forge/`. Gallery (not a settings page) per principle #4; one star per active technique per principle #9. arXiv-paste produces proposals + skill drafts, not executable code. Harvest: every named technique already exists in the engine with a settings toggle.
- **M15** — Tauri installer signing, paywall gate, marketing site.
- **M16** — Evals harness, per-user benchmark store. Load-bearing for M18 (LoRA gate: only promote weights that pass eval). Harvest: ~40-50% of capture infrastructure already in place (`trace_feedback`, `message_feedback`, `BehaviorProfile`, `ArtifactConverter.export_as_eval`).
- **M17** — Network panel in settings, per-provider kill switch. Operational note: should land *before* M13 (M13 massively increases outbound traffic). Backend uses stdlib `urllib` only — one wrapper covers 100% of in-process outbound. `metis_app/audit.py` is a pytest parity runner, unrelated; new package at `metis_app/network_audit/`.
- **M18** — LoRA training loop, eval gate, weight swap.
- **M19** — Read-only mobile client, sync protocol.
- **M22** — New visual layer on top of M13's comet pipeline. Touches `apps/metis-web/lib/constellation-comet-labels.ts` (new), `apps/metis-web/lib/pretext-labels.ts` (adds `wrapText`), `apps/metis-web/app/page.tsx` (renderer + hover hit-test + click). No backend. First consumer of pretext's line-breaking surface in METIS. Design at [`docs/plans/2026-05-01-comet-headline-labels-design.md`](../docs/plans/2026-05-01-comet-headline-labels-design.md). 5 phases, multi-day. Promoted from the 2026-05-01 pretext intake's UI-exploration brainstorm.
- **M20** — Frontend-only brand rollout. Adds three primitives at
  `apps/metis-web/components/brand/*` (`<MetisMark>`, `<MetisGlow>`,
  `<MetisLockup>`), one cleaned `currentColor`-themed SVG at
  `public/brand/metis-mark.svg`, four Next.js metadata files
  (`app/icon.tsx`, `apple-icon.tsx`, `opengraph-image.tsx`,
  `twitter-image.tsx`), and a Tauri PNG icon suite under
  `apps/metis-desktop/src-tauri/icons/`. Touches the topbar
  (`components/shell/page-chrome.tsx`), landing nav (`app/page.tsx`),
  home hero (`components/home/home-visual-system.tsx`), setup welcome
  (`app/setup/page.tsx`), and desktop loader
  (`components/desktop-ready.tsx`). Motion via `motion/react`,
  reduced-motion gated. **Coordinate with M01** before Phase 2 (hero
  swap touches an M01 hotspot).

---

## Rituals

- **Every Friday (or after a milestone lands):** walk this file top-to-bottom.
  Update statuses. Run triage on [`IDEAS.md`](IDEAS.md).
- **When claiming a row:** set `Claim` + `Last updated`. Post nothing else.
- **When a milestone lands:** `Status: Landed`, fill in merge commit SHA and
  date. Move entry to a `## Landed` section if the main table gets long.
- **When a new milestone appears** (promoted from `IDEAS.md`): add a row with
  `Status: Draft needed` and create a plan doc stub.
