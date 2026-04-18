# METIS — Implementation Index

> **Read first:** [`VISION.md`](../VISION.md) (product), [`plans/README.md`](README.md)
> (how this folder works), [`docs/adr/`](../docs/adr/) (architectural decisions).

This is the **single source of truth for what is being worked on in METIS and
what comes next.** Every row is a milestone from `VISION.md`. Agents claim rows,
do the work, update the row when they stop.

**Last reviewed:** 2026-04-18

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
| M02 | **Constellation 2D refactor** — retire 3D sphere, 2D archetype dive (ADR 0006) | 🌌 | In progress | [`plans/constellation-2d-refactor/plan.md`](constellation-2d-refactor/plan.md) | `claude/m02-archetypes-nebula-bh-rg` (Phase 3: all 12 archetypes) — Phases 0/0.3/1/2/3 landed | 2026-04-18 | — |
| M03 | **IterRAG convergence** — agentic loop with convergence detection | 🧠 | Ready | [`docs/plans/2026-04-01-hermes-sotaku-implementation.md`](../docs/plans/2026-04-01-hermes-sotaku-implementation.md) (Phase 1) | — | 2026-04-04 | — |
| M04 | **Reverse curriculum** — faculty hardness scoring drives research order | 🧠 | Ready | [`docs/plans/2026-04-04-reverse-curriculum-implementation.md`](../docs/plans/2026-04-04-reverse-curriculum-implementation.md) | — | 2026-04-04 | M03 |
| M05 | **Parallel research** — concurrent faculty workers + batch fixes | 🧠 | Ready | [`docs/plans/2026-04-04-parallel-research-implementation.md`](../docs/plans/2026-04-04-parallel-research-implementation.md) | — | 2026-04-04 | — |
| M06 | **Skill self-evolution** — candidate capture from high-convergence traces | 🧠🌱 | Ready | [`docs/plans/2026-04-01-hermes-sotaku-implementation.md`](../docs/plans/2026-04-01-hermes-sotaku-implementation.md) (Phase 3) | — | 2026-04-04 | M03 |
| M07 | **Hermes v0.7.0 patterns** — context compression, skill index, credential pool | 🔧 | Ready | [`docs/plans/2026-04-04-hermes-v070-implementation.md`](../docs/plans/2026-04-04-hermes-v070-implementation.md) | — | 2026-04-04 | — |
| M08 | **Hybrid search** — BM25 + vector alpha-blend retrieval | 🧠 | Ready | [`docs/plans/2026-04-04-hybrid-search-design.md`](../docs/plans/2026-04-04-hybrid-search-design.md) | — | 2026-04-04 | — |
| M09 | **Companion realtime visibility** — SSE thought log + constellation auto-refresh | 🌱 | Ready | [`plans/companion-realtime-visibility/plan.md`](companion-realtime-visibility/plan.md) | — | — | — |
| M10 | **Tribev2 homological scaffold** — persistent homology over BrainGraph | 🌱🌌 | Draft | [`plans/trive-v2-homological-scaffold/plan.md`](trive-v2-homological-scaffold/plan.md) | — | — | — |
| M11 | **Agent-native state + polling** — KV store, structured chat bridge | 🔧 | Ready | [`docs/plan/agent-native-impl-20260402/plan.yaml`](../docs/plan/agent-native-impl-20260402/plan.yaml) | — | 2026-04-02 | — |
| M12 | **Interactive star catalogue** — searchable, filterable star explorer | 🌌 | Ready | [`docs/plans/2026-04-05-interactive-star-catalogue.md`](../docs/plans/2026-04-05-interactive-star-catalogue.md) | — | 2026-04-05 | M02 (share renderer) |
| M13 | **Seedling + Feed** — always-on quantized local model, news-comet ingestion, growth stages | 🌱 | Draft needed | *(to be created: `plans/seedling-and-feed/plan.md`)* | — | — | M01 |
| M14 | **The Forge** — technique gallery UI, togglable frontier modules | 🌱🧠 | Draft needed | *(to be created: `plans/the-forge/plan.md`)* | — | — | M02, M06 |
| M15 | **Pro tier + public launch** — paywall, skill pack, HN/r/LocalLLaMA launch | 🔧 | Draft needed | *(to be created: `plans/pro-tier-launch/plan.md`)* | — | — | M13, M14 |
| M16 | **Personal evals** — track companion improvement on user's specific tasks | 🌱 | Draft needed | *(to be created: `plans/personal-evals/plan.md`)* | — | — | M13 |
| M17 | **Network audit** — outbound call panel, per-provider block, offline proof | 🔧 | Draft needed | *(to be created: `plans/network-audit/plan.md`)* | — | — | — |
| M18 | **LoRA fine-tuning (stretch)** — companion weights adapt to user data | 🌱 | Draft needed | *(to be created: `plans/lora-stretch/plan.md`)* | — | — | M13 |
| M19 | **Mobile companion (stretch)** — Tauri Mobile or PWA, read-only | 🌌 | Draft needed | *(to be created: `plans/mobile-stretch/plan.md`)* | — | — | M15 |

### Superseded

| # | Milestone | Superseded by |
|---|---|---|
| — | `2026-04-04-star-dive-sphere-design.md` (3D sphere dive) | ADR 0006 + M02 |
| — | `2026-04-04-star-dive-sphere-overhaul.md` (3D sphere impl) | ADR 0006 + M02 |
| — | `2026-04-04-star-closeup-aspect-ratio-fix.md` (fullscreen shader fix) | ADR 0006 + M02 (partially) |
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
- **M12** — Star catalogue UI. Coordinates with M02 (shares 2D renderer).
- **M13** — New process (`metis_app/seedling/`?), continuous ingestion, companion
  stages. Coordinate with M09 (shared dock surface).
- **M14** — New UI surface (`apps/metis-web/app/forge/`?), skill marketplace hooks.
- **M15** — Tauri installer signing, paywall gate, marketing site.
- **M16** — Evals harness, per-user benchmark store.
- **M17** — Network panel in settings, per-provider kill switch.
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
