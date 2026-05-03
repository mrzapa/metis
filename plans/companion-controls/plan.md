---
Milestone: M23 — Companion controls
Status: Ready for review
Claim: claude/sharp-payne-90957a (all 6 phases shipped; 25 commits on branch; PR pending)
Last updated: 2026-05-03 by claude/sharp-payne-90957a
Vision pillar: Companion
TDD Mode: pragmatic
---

> **Coordinates with M01.** Closes Shape of AI pattern audit gaps #1 (Voice and tone + Personality) and #2 (Memory inspector) — flip both from ❌ to ✅ in [`docs/preserve-and-productize-plan.md` → *Shape of AI pattern audit (2026-05-02)*](../../docs/preserve-and-productize-plan.md#shape-of-ai-pattern-audit-2026-05-02) at Phase 6.

## Why this exists

Two VISION promises are not delivered by the current UI:

1. **"Feels like *yours*"** — but the user has no surface to tune *how the companion speaks*. `AssistantIdentity.prompt_seed` exists in the data model and renders as a free-text Textarea on `/settings → Companion`, but it is invisible, intimidating, and undiscoverable.
2. **"Control what details the AI knows about you"** — but there is no read-write surface over `assistant_memory` and `assistant_playbooks`. The user cannot inspect what the companion remembers, cannot delete individual memories, and cannot bulk-clear by category.

Both surfaces share the same backend (`AssistantCompanionService.update_config` / `get_snapshot`), the same persistence (`AssistantRepository`), and the same UI page (`/settings → Companion` tab). Bundling them is correct.

## Design doc

Full design at [`docs/plans/2026-05-03-companion-controls-design.md`](../../docs/plans/2026-05-03-companion-controls-design.md). Read it before starting any phase.

## Implementation plan

Task-by-task at [`docs/plans/2026-05-03-companion-controls-implementation.md`](../../docs/plans/2026-05-03-companion-controls-implementation.md). 17 tasks across 6 phases, each task a 2–5 minute RED-GREEN-COMMIT cycle. Use `superpowers:executing-plans` to drive it.

## Progress

All six phases shipped on `claude/sharp-payne-90957a` between 2026-05-03 (start) and 2026-05-03 (PR). 25 commits, bisect-friendly. Final state:

- **Phase 1** — Backend tone preset. Three commits (`d69f58d`, `91b93bd`, `59bc9af`) + two fix commits from review (`72e8aba`, `68adb04`).
- **Phase 2** — Backend delete endpoints. Five commits (`136b150`, `5f8ddf1`, `c7e4b10`, `ea13762`, `69878ce`) + three fix commits maintaining `AssistantStatus.latest_summary` coherence (`949be37`, `c4cc474`, `13bcdc3`).
- **Phase 3** — Frontend Companion-tab restructure + PersonalityCard. Two commits (`8d6a83f`, `ee22fc8`) + two fix commits (`0ed459e`, `f51ad28`).
- **Phase 4** — Frontend MemoryInspector. Three commits (`a2a3c56`, `c365624`, `2b132a5`) + two fix commits (`42d9dea`, `42c2e5d`).
- **Phase 5** — Companion-dock settings deep-link. One commit (`6d7bb43`).
- **Final review fixes** — Two commits (`9ae8925` dock-link `?tab=` query fix, `3d93991` `resolve_prompt_seed` wiring).
- **Phase 6** — Audit reconciliation: M01 plan-doc gaps #1, #2 flipped ❌→✅; this plan-stub frontmatter promoted to *Ready for review*; IDEAS.md decision line updated; IMPLEMENTATION.md M23 row to be flipped to *Landed* post-PR-merge with merge SHA.

Cumulative test status at HEAD:
- Backend pytest (excluding pre-existing-broken `tests/test_api_app.py`): **1598 passed, 12 skipped**.
- Frontend vitest: **735 passed, 10 skipped, 80 files**.
- `tsc --noEmit` (in `apps/metis-web`): clean.

## Next up

Open the PR. After merge, flip IMPLEMENTATION.md M23 row to *Landed* with merge SHA.

## Phases

Six phases, ~4 days total. Each phase is a separable PR; final PR may bundle 5+6.

- **Phase 1** — Backend: tone preset (~half-day)
- **Phase 2** — Backend: delete endpoints (~half-day)
- **Phase 3** — Front-end: PersonalityCard (~1 day)
- **Phase 4** — Front-end: MemoryInspector (~1.5 days)
- **Phase 5** — Dock link (~1 hour)
- **Phase 6** — Verify + audit cross-reference (~half-day)

Backend phases (1–2) ship without UI behind feature-untouched defaults — no risk to running users. Front-end phases (3–4) gate on backend landing. Phase 5 is trivial chrome. Phase 6 closes out audit reconciliation.

## Blockers

None at filing time. Two minor judgement calls left to the impl agent (see design doc *Open questions for impl*):

1. Tone preset count — three is the design intent; drop to two if "playful" reads as off-brand during impl.
2. Confirm-on-overwrite frequency — once per session per the spec; promote to every-time if usability testing flags accidental clobber.

## Notes for the next agent

- **Existing infrastructure is ~80% of the lift.** `AssistantIdentity` schema, `update_config`, `get_snapshot`, the Companion tab in settings, the `assistant_memory` + `assistant_playbooks` SQLite tables, and the `assistantForm` react-hook-form binding all already exist. M23 is a structured-affordances + delete-paths overlay, not a new subsystem.
- **The tone presets are seed *templates*, not personalities.** Role/scope clauses are identical across presets — only voice clauses change. This avoids the "different personality means different competence" trap.
- **Memory grouping uses the existing `kind` discriminator on `AssistantMemoryEntry`.** Don't invent a new ontology.
- **The dock gets a link, not controls.** `Settings ↗` deep-link to `/settings#companion`. No modal, no inline editing, no duplicated UI.
- **Phase 6 is the audit-reconciliation gate.** Don't claim Landed without flipping gaps #1 + #2 in the M01 plan doc and updating IDEAS.md.
- **Out of scope (do not add):** Avatar customisation, memory edit/add, soft tombstones, per-tone retraining, memory in the dock, localised preset names. All recorded in the design doc.
