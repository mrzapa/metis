# M23 — Companion controls: design

**Date:** 2026-05-03
**Author:** claude/sharp-payne-90957a
**Vision pillar:** Companion (🌱)
**Source intake:** [`plans/IDEAS.md` → *Shape of AI — pattern-coverage audit*](../../plans/IDEAS.md). Promoted from gaps #1 (Voice and tone + Personality) + #2 (Memory inspector) of the [Shape of AI pattern audit](../preserve-and-productize-plan.md#shape-of-ai-pattern-audit-2026-05-02).

## Why this milestone exists

VISION makes two specific Companion-pillar promises that the UI does not currently deliver on:

1. **"Intelligence grown, not bought"** + **"feels like *yours*"** — but the user has no surface to tune *how the companion speaks*. The personality knob (`AssistantIdentity.prompt_seed`) exists in the data model and is rendered as a free-text Textarea in `/settings → Companion`, but it's invisible, intimidating, and undiscoverable.
2. **"Control what details the AI knows about you"** — but there is no read-write surface over `assistant_memory` and `assistant_playbooks`. Memory entries are written by the reflection loop and capped at 200, with hard auto-evict after that. The user cannot inspect what the companion remembers, cannot delete individual memories, and cannot bulk-clear by category.

The Shape of AI catalogue surfaces these as two distinct patterns (**Tuners → Voice and tone / Identifiers → Personality**, and **Governors → Memory**) — but in the Metis codebase they share the same backend service (`AssistantCompanionService.update_config` / `get_snapshot`), the same persistence layer (`AssistantRepository`), and the same UI page (the `Companion` tab in `/settings`). Bundling them into one milestone is correct.

## What this milestone is not

- Not a new route. The existing `/settings → Companion` tab is the canonical home.
- Not avatar customisation. The M-star is the Metis brand; companion-as-avatar is vision-tense and stays out of scope until a separate ADR.
- Not memory edit / add. Edit corrupts the AI's understanding in ways that are hard to reason about; add isn't needed because memory is *earned* through interaction. Delete + bulk-clear are the only memory write affordances.
- Not soft tombstones. The existing `clear_recent_memory(limit)` is hard-delete; staying consistent.
- Not per-tone retraining or per-tone model swaps. A single `prompt_seed` derived from the chosen `tone_preset` is the only knob.

## Decisions and rationale

| # | Decision | Rationale |
|---|---|---|
| 1 | Bundle Voice/tone + Memory inspector as one milestone | Both surfaces live in the same `Companion` settings tab and share `update_config` / `get_snapshot`; splitting forces two design passes that overlap ~70% |
| 2 | Tone **presets** that translate to `prompt_seed`, with an "edit prompt seed directly" advanced disclosure | Free-text `prompt_seed` already exists but is invisible. Presets make personality discoverable without removing the power-user knob |
| 3 | Memory inspector: **read + delete only** (per-entry + bulk-clear-by-kind). No edit, no add | Edit corrupts AI state. Add bypasses earned memory. Delete satisfies VISION's "control" promise |
| 4 | Lives in `/settings → Companion`. Add a small "Settings ↗" link in the dock-minimised header | One canonical home; no duplicated UI in the dock |
| 5 | Extend `AssistantIdentity` with `tone_preset: str = "warm-curious"`. Resolve `prompt_seed` from preset at runtime when the user has not customised it | Smallest possible schema delta; existing migration story; existing `update_config` path covers persistence |
| 6 | Default `tone_preset = "warm-curious"` | Matches the current implicit default `prompt_seed`; brand-coherent |
| 7 | Memory grouped by existing `AssistantMemoryEntry.kind` discriminator. Playbooks as a separate panel | Use existing ontology; no new taxonomy to maintain |
| 8 | Hard delete for both individual entry and bulk-clear-by-kind | Existing `clear_recent_memory` is hard-delete; stay consistent |

## Architecture

Three surfaces.

### 1. `/settings → Companion` tab — restructured

Existing tab content has *Assistant identity / Runtime / Policy*. After M23 it has, in order:

- **Identity** — id, name, archetype, greeting, dock toggles. Existing fields, unchanged.
- **Personality** *(new)* — tone-preset radio group + prompt-seed override disclosure.
- **Memory** *(new)* — stats row, grouped reflection accordion, playbooks panel, delete affordances.
- **Reflection policy** — moved below Memory. Existing fields, unchanged.
- **Runtime** — moved to bottom. Existing fields, unchanged.

### 2. Companion dock — minimised header gets a settings link

A `Settings ↗` text link in the dock's minimised chrome that deep-links to `/settings#companion`. No modal, no inline editing, no controls duplicated. The link exists so users can find the new surface without hunting.

### 3. Backend — minimal extensions

#### Schema

`AssistantIdentity` (in `metis_app/models/assistant_types.py`) gets one new field:

```python
@dataclass
class AssistantIdentity:
    # ... existing fields ...
    tone_preset: str = "warm-curious"  # NEW: warm-curious | concise-analyst | playful | custom
```

#### Tone preset table

In the same module, a new module-level constant:

```python
TONE_PRESETS: dict[str, str] = {
    "warm-curious": (
        "You are METIS, a local-first companion who helps the user get oriented, "
        "suggests next steps, and records concise reflections without taking over "
        "the main chat. Keep replies warm and exploratory."
    ),
    "concise-analyst": (
        "You are METIS, a local-first companion who helps the user get oriented, "
        "suggests next steps, and records concise reflections without taking over "
        "the main chat. Keep replies brief and clinical. Lead with the answer; "
        "cite sources before commentary."
    ),
    "playful": (
        "You are METIS, a local-first companion who helps the user get oriented, "
        "suggests next steps, and records concise reflections without taking over "
        "the main chat. Keep replies relaxed and a touch wry."
    ),
}
```

Final wording is finalised during impl. The role/scope clauses are identical across presets — only the voice clause changes. This avoids the "different personality means different competence" trap.

#### `prompt_seed` resolution rule

`AssistantCompanionService` resolves the effective seed at use-time:

- If `tone_preset == "custom"` → use `prompt_seed` verbatim.
- If `tone_preset` is a known key AND `prompt_seed` matches `TONE_PRESETS[tone_preset]` exactly → use the preset (the user hasn't customised it).
- If `tone_preset` is a known key AND `prompt_seed` differs → user has typed an override; treat as `custom` for resolution purposes but keep `tone_preset` as the user set it.
- If `tone_preset` is unknown → fall back to `"warm-curious"`.

This handles legacy data (records with no `tone_preset` or empty `prompt_seed`) without a migration step. New writes always set both.

#### Repository methods (new)

In `metis_app/services/assistant_repository.py`:

```python
def delete_memory_entry(self, entry_id: str) -> bool: ...
def delete_memory_by_kind(self, kind: str) -> int: ...   # returns count deleted
def delete_playbook(self, playbook_id: str) -> bool: ...
```

All three are simple `DELETE FROM` queries inside `_transaction()`. No cascade — `assistant_brain_links` references are not affected (links can outlive the memory entry that produced them; this is intentional).

#### HTTP routes (new)

In `metis_app/api_litestar/routes/assistant.py` (or wherever the existing assistant config route lives):

- `DELETE /v1/assistant/memory/{entry_id}` → `delete_memory_entry`
- `DELETE /v1/assistant/memory?kind={kind}` → `delete_memory_by_kind`
- `DELETE /v1/assistant/playbooks/{playbook_id}` → `delete_playbook`

Each returns `{ok: bool, deleted_count?: int}`. 404 if id not found.

## Front-end components (new)

Under `apps/metis-web/components/settings/companion/`:

### `personality-card.tsx`

```
┌─ Personality ──────────────────────────────────┐
│ How should METIS speak?                        │
│                                                │
│   ◉ Warm & curious        (default)            │
│   ○ Concise analyst                            │
│   ○ Playful collaborator                       │
│   ○ Custom (advanced)                          │
│                                                │
│ ┌─ Resolved prompt seed ───────────────────┐   │
│ │ You are METIS, a local-first companion … │   │
│ │                                          │   │
│ │ [Edit prompt seed directly] (disclosure) │   │
│ └──────────────────────────────────────────┘   │
└────────────────────────────────────────────────┘
```

Radio group controls `tone_preset`. The resolved-seed block previews `TONE_PRESETS[tone_preset]` (read-only when preset ≠ custom). Clicking the disclosure expands the existing `Textarea` for direct `prompt_seed` editing and switches `tone_preset` to `"custom"` on first edit.

Coupling rule: changing the preset auto-fills `prompt_seed` from `TONE_PRESETS[next_preset]` *unless* the current `prompt_seed` is custom (i.e. doesn't match any preset). In that case, surface a confirm — "Switching presets will overwrite your custom prompt seed. Continue?"

### `memory-inspector.tsx`

```
┌─ Memory ───────────────────────────────────────┐
│  ⊙ 47 / 200 entries   ⊙ 3 playbooks            │
│  ⊙ Last reflection: 2 hours ago                │
│                                                │
│ ▾ Reflections by kind                          │
│   ▸ reflection (32)            [clear all]     │
│   ▸ skill (8)                  [clear all]     │
│   ▸ onboarding (4)             [clear all]     │
│   ▸ index_build (3)            [clear all]     │
│                                                │
│ ▾ Playbooks                                    │
│   • [✓ active] Researching X    [delete]       │
│   • [  ]       Summarising Y    [delete]       │
│   • [✓ active] Catching up on Z [delete]       │
└────────────────────────────────────────────────┘
```

Stats row uses `assistant_status` data already in `get_snapshot`. Reflection accordion: each `kind` group expands to show its entries with title / summary / created_at / confidence + a delete icon per entry; "clear all" button is the bulk-delete-by-kind. Playbooks list shows `active` toggle and delete.

### `memory-stats-row.tsx`

Three stat tiles. Quiet-loaders compatible (`<DotMatrixLoader name="thinking">` while fetching). One small file, kept separate so the row can be reused if a future "Companion overview" surface wants the same data.

### Refactor of `app/settings/page.tsx`

The existing inline Companion-tab JSX (~200 lines) splits into four sub-components:

- `<IdentityCard form={assistantForm} />`
- `<PersonalityCard form={assistantForm} />` *(new)*
- `<MemoryInspector />`  *(new — reads `get_snapshot`, no form binding)*
- `<ReflectionPolicyCard form={assistantForm} />`
- `<RuntimeCard form={assistantForm} />`

The form is still owned at the page level; sub-components receive `register` / `setValue` / `watch` via props. This is a pure DOM reshuffle for Identity/Reflection/Runtime; net-new components for Personality and Memory.

## Data flow

### Tone preset → seed resolution

```
User toggles "Concise analyst" in PersonalityCard
  ↓
PersonalityCard onChange:
  setValue("assistant_identity.tone_preset", "concise-analyst")
  IF current prompt_seed === TONE_PRESETS[old_preset] OR empty:
    setValue("assistant_identity.prompt_seed", TONE_PRESETS["concise-analyst"])
  ELSE: confirm("Switching presets will overwrite custom seed?")
  ↓
User hits "Save companion settings"
  ↓
onAssistantSubmit → PATCH /v1/assistant/config (existing route)
  ↓
AssistantCompanionService.update_config persists tone_preset + prompt_seed
  ↓
Next chat / reflect call uses the new prompt_seed
```

### Memory delete (single entry)

```
User clicks delete icon on a reflection entry
  ↓
MemoryInspector optimistic remove from local state
  ↓
DELETE /v1/assistant/memory/{entry_id}
  ↓
AssistantRepository.delete_memory_entry → DELETE FROM assistant_memory WHERE entry_id=?
  ↓
On 200: nothing more (UI already optimistic)
On non-200: rollback local state, toast error with the entry's title
  ↓
SWR mutate of get_snapshot key refreshes cap-counter row
```

### Memory bulk-clear by kind

```
User clicks "clear all" on the "skill" group
  ↓
MemoryInspector confirm dialog: "Clear all 8 skill entries? This cannot be undone."
  ↓
On confirm: DELETE /v1/assistant/memory?kind=skill
  ↓
AssistantRepository.delete_memory_by_kind returns deleted_count
  ↓
Toast "Cleared 8 skill memory entries"
  ↓
SWR mutate refreshes the inspector
```

## Error handling

- **Tone preset PATCH failure** — existing `assistantForm` toast pattern (already wired). Revert the preset radio to last-known-good using react-hook-form's `reset({ ...currentValues, tone_preset: oldPreset })`.
- **Memory delete failure (single)** — optimistic UI with rollback; toast quotes the entry title for context: `Couldn't delete "{entry.title}". {error.message}`.
- **Memory bulk-clear failure** — no optimistic UI for bulk; show pending state, then either toast success or toast error with retry button.
- **Empty memory state** — copy: `No reflections yet. Open a chat or run autonomous research to seed memory.` Link to `/chat`. Do not surface the kind-accordion when zero entries.
- **200-entry cap reached** — in-card hint: `Older entries auto-evict at the cap. [Clear oldest 50]` with a button that calls `clear_recent_memory(limit=50)` (existing endpoint).
- **`get_snapshot` fetch failure** — re-use existing assistant-load error UI from the settings page (`assistantLoadError` state).
- **Custom prompt-seed override prevention** — when `tone_preset === "custom"` and the user hits a preset radio, show a confirm dialog (one-shot per session, not on every toggle) before clobbering the custom seed.

## Testing

**TDD mode: pragmatic** (matches M21 / M01 conventions). Unit tests for behaviour with regression risk; visual / structural changes are verified through browser preview.

### Backend (pytest)

`tests/test_assistant_repository.py` — new cases:
- `test_delete_memory_entry_round_trip` — insert one, delete by id, list returns empty.
- `test_delete_memory_entry_missing_id_returns_false`.
- `test_delete_memory_by_kind_filters_correctly` — insert 3 of kind A and 2 of kind B, delete kind A, B remains.
- `test_delete_memory_by_kind_unknown_kind_returns_zero`.
- `test_delete_playbook_round_trip` + missing-id case.

`tests/test_assistant_companion.py` — new cases:
- `test_update_config_persists_tone_preset` — PATCH `tone_preset`, snapshot reflects it.
- `test_tone_preset_resolves_to_seed` — when `tone_preset="concise-analyst"` and `prompt_seed=""`, runtime resolves seed from `TONE_PRESETS`.
- `test_custom_seed_takes_precedence_over_preset` — when `tone_preset="custom"`, `prompt_seed` is verbatim.
- `test_unknown_tone_preset_falls_back_to_warm_curious`.

### Front-end (vitest)

`personality-card.test.tsx`:
- Switching preset auto-fills `prompt_seed` when current matches old preset.
- Switching preset shows confirm when current is custom.
- "Edit prompt seed directly" disclosure expands and switches `tone_preset` to `"custom"` on first keystroke.

`memory-inspector.test.tsx`:
- Optimistic delete removes entry from UI immediately.
- Failed delete rolls back UI and shows error toast.
- Bulk-clear-by-kind shows confirm dialog and calls correct endpoint.
- Empty state renders the chat-link CTA when zero entries.

### Browser preview verification (after impl, before merge)

1. Load `/settings#companion`. New layout renders without console errors.
2. Toggle each tone preset. Resolved-seed preview updates. Save. Toast appears. Reload. Selection persists.
3. Toggle to "Custom" and edit the textarea. Save. Reload. Custom text persists.
4. Switch from "Custom" back to a preset. Confirm appears. Accept. Custom text gone.
5. Open Memory tab. Stats row populates from `get_snapshot`.
6. Delete one entry. Disappears immediately. Cap-counter decrements. Reload. Still gone.
7. Bulk-clear one `kind` group. Confirm dialog. Accept. All entries in that group disappear.
8. Click "Settings ↗" in the minimised companion dock from `/`. Lands on `/settings#companion`.
9. With reduced-motion enabled, no animation regressions.

## Phasing

Six phases, ~4 days total. Each phase is a separable PR; final PR could bundle 5+6.

| # | Phase | Scope | Est. |
|---|---|---|---|
| 1 | Backend: tone preset | `tone_preset` field + `TONE_PRESETS` dict + resolution rule + `update_config` round-trip + 4 pytest cases | ~half-day |
| 2 | Backend: delete endpoints | 3 repo methods + 3 Litestar routes + 5 pytest cases | ~half-day |
| 3 | Front-end: PersonalityCard | Restructure Companion tab into sub-components; ship PersonalityCard with preset radio + override disclosure + confirm dialog + 3 vitest cases | ~1 day |
| 4 | Front-end: MemoryInspector | Stats row + grouped accordion + delete actions + bulk-clear + empty state + 4 vitest cases | ~1.5 days |
| 5 | Dock link | `Settings ↗` deep-link in `metis-companion-dock.tsx` minimised header | ~1 hour |
| 6 | Verify + audit cross-reference | Browser-preview QA (the 9 steps above), flip Shape-of-AI gaps #1/#2 from ❌ to ✅ in the M01 audit, update IDEAS.md decision line | ~half-day |

Phasing rationale: phases 1–2 (backend) ship without UI behind a feature-untouched data model — no risk to running users. Phases 3–4 are the visible work and gate on phases 1–2 landing. Phase 5 is trivial chrome. Phase 6 is the close-out audit reconciliation.

## Coordination hooks

- **M01** — gap #1 + #2 in the [Shape of AI pattern audit](../preserve-and-productize-plan.md#shape-of-ai-pattern-audit-2026-05-02) flip from ❌ to ✅ at Phase 6.
- **M21** — no overlap; M21 is bug-bash, M23 is feature-add.
- **M13 (Landed)** — M23 builds on M13's seedling+feed memory primitives. No code conflict; just a downstream consumer.
- **M16 (In progress)** — M16's eval store will eventually want to render alongside Memory. Out of scope for M23 but worth noting in Phase 6 for the next agent.
- **ADR opportunity (not blocking M23)** — if a future agent wants to revisit the "no avatar / no edit" decisions, an ADR is the right venue. M23 ships without one.

## Open questions for impl

None blocking. Two minor judgement calls left to the impl agent:

1. **Tone preset count.** Three presets (Warm & curious / Concise analyst / Playful) is the design intent. If during impl the playful seed reads as off-brand, drop to two — the system tolerates any preset count ≥1.
2. **Confirm dialog frequency.** Confirm-on-overwrite-custom-seed once per session vs every time. Spec says once; impl can promote to every-time if usability testing surfaces accidental clobber.

## Out-of-scope, recorded

- Avatar customisation. Vision-tense; defer to ADR.
- Memory edit / add. Corruption-prone; not promised by VISION.
- Soft tombstones. Inconsistent with `clear_recent_memory`.
- Per-tone retraining or model swap. Single `prompt_seed` is the only knob.
- Surfacing memory in the companion dock. Single canonical home is `/settings`.
- Localised tone preset names. Existing settings UI is English-only; defer.
