---
Milestone: M23 — Companion controls
Status: Ready
Claim: unclaimed
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

## Progress

*(milestone not yet started)*

## Next up

Phase 1 — Backend: tone preset. See *Phasing* in the design doc.

1. Add `tone_preset: str = "warm-curious"` to `AssistantIdentity` in `metis_app/models/assistant_types.py`.
2. Add `TONE_PRESETS: dict[str, str]` constant in the same module with three presets (warm-curious / concise-analyst / playful).
3. Implement seed resolution rule in `AssistantCompanionService` (or wherever `prompt_seed` is read at use-time — most likely `runtime_resolution.py`).
4. Wire `tone_preset` through `update_config` and `get_snapshot`.
5. Add four pytest cases per the design doc *Testing* section.
6. Run full backend suite (`pytest`); confirm no regressions in `test_assistant_companion.py` and `test_assistant_repository.py`.

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
