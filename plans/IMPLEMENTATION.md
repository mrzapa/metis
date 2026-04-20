# METIS — Implementation Index

> **Read first:** [`VISION.md`](../VISION.md) (product), [`plans/README.md`](README.md)
> (how this folder works), [`docs/adr/`](../docs/adr/) (architectural decisions).

This is the **single source of truth for what is being worked on in METIS and
what comes next.** Every row is a milestone from `VISION.md`. Agents claim rows,
do the work, update the row when they stop.

**Last reviewed:** 2026-04-19 (reconciled M07/M08/M09/M11 → Landed; M12 Phase 1 landed; M13/M14/M16/M17 plans drafted; M12 Phase 2 design doc superseded — M02 already shipped the renderer path)

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
| M03 | **IterRAG convergence** — agentic loop with convergence detection | 🧠 | Ready | [`docs/plans/2026-04-01-hermes-sotaku-implementation.md`](../docs/plans/2026-04-01-hermes-sotaku-implementation.md) (Phase 1) | — | 2026-04-04 | — |
| M04 | **Reverse curriculum** — faculty hardness scoring drives research order | 🧠 | Ready | [`docs/plans/2026-04-04-reverse-curriculum-implementation.md`](../docs/plans/2026-04-04-reverse-curriculum-implementation.md) | — | 2026-04-04 | M03 |
| M05 | **Parallel research** — concurrent faculty workers + batch fixes | 🧠 | Ready | [`docs/plans/2026-04-04-parallel-research-implementation.md`](../docs/plans/2026-04-04-parallel-research-implementation.md) | — | 2026-04-04 | — |
| M06 | **Skill self-evolution** — candidate capture from high-convergence traces | 🧠🌱 | Ready | [`docs/plans/2026-04-01-hermes-sotaku-implementation.md`](../docs/plans/2026-04-01-hermes-sotaku-implementation.md) (Phase 3) | — | 2026-04-04 | M03 |
| M07 | **Hermes v0.7.0 patterns** — context compression, skill index, credential pool | 🔧 | Landed | [`docs/plans/2026-04-04-hermes-v070-implementation.md`](../docs/plans/2026-04-04-hermes-v070-implementation.md) | Landed via PR #464 (`551d01b`, 2026-04-04) | 2026-04-04 | — |
| M08 | **Hybrid search** — BM25 + vector alpha-blend retrieval | 🧠 | Landed | [`docs/plans/2026-04-04-hybrid-search-design.md`](../docs/plans/2026-04-04-hybrid-search-design.md) | Landed (`8d6ed98`, 2026-04-04) | 2026-04-04 | — |
| M09 | **Companion realtime visibility** — SSE thought log + constellation auto-refresh | 🌱 | Landed | [`plans/companion-realtime-visibility/plan.md`](companion-realtime-visibility/plan.md) | Landed (`68634ba`, 2026-04-18) | 2026-04-18 | — |
| M10 | **Tribev2 homological scaffold** — persistent homology over BrainGraph | 🌱🌌 | Draft | [`plans/trive-v2-homological-scaffold/plan.md`](trive-v2-homological-scaffold/plan.md) | — | — | — |
| M11 | **Agent-native state + polling** — KV store, structured chat bridge | 🔧 | Landed | [`docs/plan/agent-native-impl-20260402/plan.yaml`](../docs/plan/agent-native-impl-20260402/plan.yaml) | Landed via PR #459 (`5fd0a3f`, 2026-04-03) | 2026-04-03 | — |
| M12 | **Interactive star catalogue** — searchable, filterable star explorer | 🌌 | Draft needed | *(to be created: `plans/interactive-star-catalogue/plan.md`)* — [old design doc superseded](../docs/plans/2026-04-05-interactive-star-catalogue.md) | Phase 1 data layer landed (`StarCatalogue` consumed via `DEFAULT_CATALOGUE_CONFIG` in `page.tsx`); WebGL renderer landed via M02 (`LandingStarfieldWebgl`); interactive explorer layer (search / filter / click-to-inspect) still unshipped | 2026-04-19 | — |
| M13 | **Seedling + Feed** — always-on quantized local model, news-comet ingestion, growth stages | 🌱 | Draft | [`plans/seedling-and-feed/plan.md`](seedling-and-feed/plan.md) | — | 2026-04-19 | M01 |
| M14 | **The Forge** — technique gallery UI, togglable frontier modules | 🌱🧠 | Draft | [`plans/the-forge/plan.md`](the-forge/plan.md) | — | 2026-04-19 | M02, M06, M12 |
| M15 | **Pro tier + public launch** — paywall, skill pack, HN/r/LocalLLaMA launch | 🔧 | Draft needed | [`plans/pro-tier-launch/plan.md`](pro-tier-launch/plan.md) (harvest stub) | — | 2026-04-18 | M13, M14 |
| M16 | **Personal evals** — track companion improvement on user's specific tasks | 🌱 | Draft | [`plans/personal-evals/plan.md`](personal-evals/plan.md) | — | 2026-04-19 | M13 |
| M17 | **Network audit** — outbound call panel, per-provider block, offline proof | 🔧 | In progress | [`plans/network-audit/plan.md`](network-audit/plan.md) | Phases 1-5a landed (`ed99582`); `claude/m17-phase5b-privacy-ui` working Phase 5b — read-only /settings/privacy page (toggles + export + synthetic-pass in 5c) | 2026-04-20 | — |
| M18 | **LoRA fine-tuning (stretch)** — companion weights adapt to user data | 🌱 | Draft needed | *(to be created: `plans/lora-stretch/plan.md`)* | — | — | M13 |
| M19 | **Mobile companion (stretch)** — Tauri Mobile or PWA, read-only | 🌌 | Draft needed | *(to be created: `plans/mobile-stretch/plan.md`)* | — | — | M15 |

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

---

## Rituals

- **Every Friday (or after a milestone lands):** walk this file top-to-bottom.
  Update statuses. Run triage on [`IDEAS.md`](IDEAS.md).
- **When claiming a row:** set `Claim` + `Last updated`. Post nothing else.
- **When a milestone lands:** `Status: Landed`, fill in merge commit SHA and
  date. Move entry to a `## Landed` section if the main table gets long.
- **When a new milestone appears** (promoted from `IDEAS.md`): add a row with
  `Status: Draft needed` and create a plan doc stub.
