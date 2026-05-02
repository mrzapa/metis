# M23 — Companion controls Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship Voice/tone presets and a Memory inspector under `/settings → Companion`, closing Shape of AI pattern audit gaps #1 and #2.

**Architecture:** Mostly UI on existing infrastructure. Backend gets one new field on `AssistantIdentity` (`tone_preset`), one preset → seed resolution rule, three new delete repository methods + matching Litestar routes. Front-end gets a restructured Companion settings tab with a `PersonalityCard`, a `MemoryInspector`, and a deep-link from the companion-dock minimised header.

**Tech Stack:** Python 3.11+ / Litestar / SQLite (backend) · Next.js 16 / React 19 / react-hook-form / zod / Tailwind / vitest (frontend) · pytest (backend tests).

**Design doc:** [`docs/plans/2026-05-03-companion-controls-design.md`](2026-05-03-companion-controls-design.md). Read it before starting any task.

**TDD Mode:** pragmatic. RED-step tests for behaviour with regression risk (preset resolution, delete paths, optimistic-UI rollback). Pure DOM restructuring is verified through browser preview, not unit tests.

**Path corrections vs. design doc:**

- The existing assistant config write route is `POST /v1/assistant` (not `PATCH /v1/assistant/config`). The design doc's data-flow diagrams should be read with this substitution.
- `DELETE /v1/assistant/memory?limit=N` already exists for `clear_recent_memory` (oldest-N hard delete). New routes use distinct paths:
  - `DELETE /v1/assistant/memory/{entry_id}` — single entry delete (new)
  - `DELETE /v1/assistant/memory/by-kind?kind=X` — bulk delete by kind (new)
  - `DELETE /v1/assistant/playbooks/{playbook_id}` — single playbook delete (new)

---

## Phase 1 — Backend: tone preset (~half-day)

### Task 1.1: Add `TONE_PRESETS` dict and `tone_preset` field

**Files:**
- Modify: `metis_app/models/assistant_types.py:29-60` (add field + module constant)
- Test: `tests/test_assistant_types.py` (create if absent — check first with `ls tests/test_assistant_types.py`)

**Step 1: Write the failing test**

Append to `tests/test_assistant_types.py`:

```python
from metis_app.models.assistant_types import (
    AssistantIdentity,
    TONE_PRESETS,
)


def test_tone_presets_dict_has_three_canonical_keys():
    assert set(TONE_PRESETS.keys()) == {"warm-curious", "concise-analyst", "playful"}
    for key, seed in TONE_PRESETS.items():
        assert seed.startswith("You are METIS"), key
        assert len(seed) > 60, key


def test_assistant_identity_default_tone_preset():
    identity = AssistantIdentity()
    assert identity.tone_preset == "warm-curious"


def test_assistant_identity_round_trip_preserves_tone_preset():
    original = AssistantIdentity(tone_preset="concise-analyst")
    payload = original.to_payload()
    restored = AssistantIdentity.from_payload(payload)
    assert restored.tone_preset == "concise-analyst"


def test_assistant_identity_from_payload_unknown_preset_falls_back():
    restored = AssistantIdentity.from_payload({"tone_preset": "menace"})
    assert restored.tone_preset == "warm-curious"
```

**Step 2: Run test to verify it fails**

```
pytest tests/test_assistant_types.py -v
```
Expected: 4 FAIL — `ImportError: cannot import name 'TONE_PRESETS'` or `AttributeError: ... has no attribute 'tone_preset'`.

**Step 3: Write minimal implementation**

In `metis_app/models/assistant_types.py`, add module-level constant near the top of the file (after `_coerce_int`):

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

Add field to `AssistantIdentity` (line ~31, after `minimized: bool = True`):

```python
    tone_preset: str = "warm-curious"
```

Update `from_payload` (line ~49) to include:

```python
        tone_preset = str(data.get("tone_preset") or "warm-curious")
        if tone_preset not in TONE_PRESETS and tone_preset != "custom":
            tone_preset = "warm-curious"
```

…and add `tone_preset=tone_preset` to the `cls(...)` call.

**Step 4: Run test to verify it passes**

```
pytest tests/test_assistant_types.py -v
```
Expected: 4 PASS.

**Step 5: Commit**

```
git add metis_app/models/assistant_types.py tests/test_assistant_types.py
git commit -m "feat(m23): add TONE_PRESETS + AssistantIdentity.tone_preset field"
```

---

### Task 1.2: `prompt_seed` resolution rule

**Files:**
- Create: `metis_app/services/companion_voice.py` (small utility module)
- Test: `tests/test_companion_voice.py`

**Step 1: Write the failing test**

`tests/test_companion_voice.py`:

```python
from metis_app.models.assistant_types import AssistantIdentity, TONE_PRESETS
from metis_app.services.companion_voice import resolve_prompt_seed


def test_resolve_returns_preset_seed_when_seed_matches():
    identity = AssistantIdentity(
        tone_preset="concise-analyst",
        prompt_seed=TONE_PRESETS["concise-analyst"],
    )
    assert resolve_prompt_seed(identity) == TONE_PRESETS["concise-analyst"]


def test_resolve_returns_preset_seed_when_seed_empty():
    identity = AssistantIdentity(tone_preset="playful", prompt_seed="")
    assert resolve_prompt_seed(identity) == TONE_PRESETS["playful"]


def test_resolve_returns_custom_seed_when_tone_preset_is_custom():
    identity = AssistantIdentity(
        tone_preset="custom",
        prompt_seed="You are not METIS. You are a pirate.",
    )
    assert resolve_prompt_seed(identity) == "You are not METIS. You are a pirate."


def test_resolve_returns_custom_seed_when_user_overrode_preset_seed():
    identity = AssistantIdentity(
        tone_preset="warm-curious",
        prompt_seed="My custom seed text.",
    )
    # User typed override; treat as custom for resolution
    assert resolve_prompt_seed(identity) == "My custom seed text."


def test_resolve_falls_back_to_warm_curious_for_unknown_preset():
    identity = AssistantIdentity.__new__(AssistantIdentity)
    # Bypass __init__ guard to simulate corrupt persisted state
    object.__setattr__(identity, "tone_preset", "menace")
    object.__setattr__(identity, "prompt_seed", "")
    # Fill remaining slots with defaults
    for f, default in (
        ("assistant_id", "metis-companion"),
        ("name", "METIS"),
        ("archetype", "x"),
        ("companion_enabled", True),
        ("greeting", "g"),
        ("docked", True),
        ("minimized", True),
    ):
        object.__setattr__(identity, f, default)
    assert resolve_prompt_seed(identity) == TONE_PRESETS["warm-curious"]
```

**Step 2: Run test to verify it fails**

```
pytest tests/test_companion_voice.py -v
```
Expected: 5 FAIL — `ModuleNotFoundError: No module named 'metis_app.services.companion_voice'`.

**Step 3: Write minimal implementation**

`metis_app/services/companion_voice.py`:

```python
"""Resolve effective prompt seed from AssistantIdentity tone preset."""

from __future__ import annotations

from metis_app.models.assistant_types import AssistantIdentity, TONE_PRESETS


def resolve_prompt_seed(identity: AssistantIdentity) -> str:
    """Return the seed METIS should use given the identity's preset and override.

    Rules:
      - tone_preset == "custom" → use prompt_seed verbatim
      - tone_preset is a known key AND prompt_seed is empty → preset's seed
      - tone_preset is a known key AND prompt_seed equals the preset → preset's seed
      - tone_preset is a known key AND prompt_seed differs → user override (custom)
      - tone_preset is unknown → fall back to "warm-curious"
    """
    preset = identity.tone_preset or "warm-curious"
    seed = identity.prompt_seed or ""

    if preset == "custom":
        return seed

    if preset not in TONE_PRESETS:
        return TONE_PRESETS["warm-curious"]

    canonical = TONE_PRESETS[preset]
    if seed == "" or seed == canonical:
        return canonical

    # User typed an override — honour it
    return seed
```

**Step 4: Run test to verify it passes**

```
pytest tests/test_companion_voice.py -v
```
Expected: 5 PASS.

**Step 5: Commit**

```
git add metis_app/services/companion_voice.py tests/test_companion_voice.py
git commit -m "feat(m23): tone preset → prompt seed resolution rule"
```

---

### Task 1.3: Wire `tone_preset` through `update_config` round-trip

**Files:**
- Test: `tests/test_assistant_companion.py` (existing — append to it)

`update_config` already accepts `identity: dict[str, Any] | None`, and `AssistantIdentity.from_payload` (extended in Task 1.1) reads `tone_preset` from the dict. This task only adds the integration test. If the test passes without further code, that's the desired result.

**Step 1: Write the failing test**

Append to `tests/test_assistant_companion.py`:

```python
def test_update_config_persists_tone_preset(tmp_path):
    # Use whatever fixture the file already uses to construct the service.
    # Look up an existing test in this file; copy its setup pattern.
    from metis_app.services.assistant_companion import AssistantCompanionService
    # ... construct service with tmp_path-backed repos as other tests do ...
    service = _make_service(tmp_path)  # pseudocode — match local fixture style
    settings = {}
    service.update_config(identity={"tone_preset": "concise-analyst"})
    snapshot = service.get_snapshot(settings)
    assert snapshot["identity"]["tone_preset"] == "concise-analyst"
```

**Note for the implementer:** the existing tests in `tests/test_assistant_companion.py` already wire up `AssistantRepository` against a temp DB. Match that fixture pattern exactly — do not invent a new one. Look at the first 100 lines of that file to copy the setup helpers.

**Step 2: Run test to verify it fails**

```
pytest tests/test_assistant_companion.py::test_update_config_persists_tone_preset -v
```
Expected: PASS if Task 1.1's `from_payload` extension works; FAIL with `KeyError: 'tone_preset'` if it doesn't.

**Step 3: If it FAILED — fix `from_payload`**

If the test fails, the cause is `from_payload` not threading `tone_preset` into the `cls(...)` construction. Re-check Task 1.1's edit. Add `tone_preset=tone_preset` to the constructor call if missing.

**Step 4: Run test to verify it passes**

```
pytest tests/test_assistant_companion.py::test_update_config_persists_tone_preset -v
```
Expected: PASS.

**Step 5: Commit**

```
git add tests/test_assistant_companion.py metis_app/models/assistant_types.py
git commit -m "test(m23): tone preset round-trips through update_config"
```

---

## Phase 2 — Backend: delete endpoints (~half-day)

### Task 2.1: `AssistantRepository.delete_memory_entry`

**Files:**
- Modify: `metis_app/services/assistant_repository.py`
- Test: `tests/test_assistant_repository.py` (existing — append)

**Step 1: Write the failing test**

Append to `tests/test_assistant_repository.py`:

```python
def test_delete_memory_entry_round_trip(tmp_path):
    repo = _make_repo(tmp_path)  # match existing fixture pattern in this file
    entry = AssistantMemoryEntry(
        entry_id="abc-123",
        created_at="2026-05-03T00:00:00+00:00",
        kind="reflection",
        title="Test entry",
        summary="A test reflection",
    )
    repo.upsert_memory_entry(entry)
    assert repo.delete_memory_entry("abc-123") is True
    assert all(e.entry_id != "abc-123" for e in repo.list_memory_entries())


def test_delete_memory_entry_missing_id_returns_false(tmp_path):
    repo = _make_repo(tmp_path)
    assert repo.delete_memory_entry("does-not-exist") is False
```

**Step 2: Run test to verify it fails**

```
pytest tests/test_assistant_repository.py::test_delete_memory_entry_round_trip tests/test_assistant_repository.py::test_delete_memory_entry_missing_id_returns_false -v
```
Expected: FAIL — `AttributeError: 'AssistantRepository' object has no attribute 'delete_memory_entry'`.

**Step 3: Write minimal implementation**

In `metis_app/services/assistant_repository.py`, after `upsert_memory_entry` (or wherever memory mutators live):

```python
    def delete_memory_entry(self, entry_id: str) -> bool:
        """Hard-delete one memory entry. Returns True if a row was deleted."""
        with self._transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM assistant_memory WHERE entry_id = ?",
                (entry_id,),
            )
            return cursor.rowcount > 0
```

**Step 4: Run test to verify it passes**

```
pytest tests/test_assistant_repository.py::test_delete_memory_entry_round_trip tests/test_assistant_repository.py::test_delete_memory_entry_missing_id_returns_false -v
```
Expected: 2 PASS.

**Step 5: Commit**

```
git add metis_app/services/assistant_repository.py tests/test_assistant_repository.py
git commit -m "feat(m23): AssistantRepository.delete_memory_entry"
```

---

### Task 2.2: `AssistantRepository.delete_memory_by_kind`

**Files:**
- Modify: `metis_app/services/assistant_repository.py`
- Test: `tests/test_assistant_repository.py`

**Step 1: Write the failing test**

```python
def test_delete_memory_by_kind_filters_correctly(tmp_path):
    repo = _make_repo(tmp_path)
    for i, kind in enumerate(["reflection", "reflection", "reflection", "skill", "skill"]):
        repo.upsert_memory_entry(AssistantMemoryEntry(
            entry_id=f"id-{i}",
            created_at="2026-05-03T00:00:00+00:00",
            kind=kind,
            title=f"t{i}",
            summary="s",
        ))
    deleted = repo.delete_memory_by_kind("reflection")
    assert deleted == 3
    remaining = repo.list_memory_entries()
    assert len(remaining) == 2
    assert all(e.kind == "skill" for e in remaining)


def test_delete_memory_by_kind_unknown_kind_returns_zero(tmp_path):
    repo = _make_repo(tmp_path)
    assert repo.delete_memory_by_kind("nonexistent") == 0
```

**Step 2: Run test to verify it fails**

```
pytest tests/test_assistant_repository.py::test_delete_memory_by_kind_filters_correctly tests/test_assistant_repository.py::test_delete_memory_by_kind_unknown_kind_returns_zero -v
```
Expected: FAIL — method doesn't exist.

**Step 3: Write minimal implementation**

```python
    def delete_memory_by_kind(self, kind: str) -> int:
        """Hard-delete all memory entries of a given kind. Returns count deleted."""
        with self._transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM assistant_memory WHERE kind = ?",
                (kind,),
            )
            return cursor.rowcount
```

**Step 4: Run test to verify it passes**

```
pytest tests/test_assistant_repository.py::test_delete_memory_by_kind_filters_correctly tests/test_assistant_repository.py::test_delete_memory_by_kind_unknown_kind_returns_zero -v
```
Expected: 2 PASS.

**Step 5: Commit**

```
git add metis_app/services/assistant_repository.py tests/test_assistant_repository.py
git commit -m "feat(m23): AssistantRepository.delete_memory_by_kind"
```

---

### Task 2.3: `AssistantRepository.delete_playbook`

**Files:**
- Modify: `metis_app/services/assistant_repository.py`
- Test: `tests/test_assistant_repository.py`

**Step 1: Write the failing test**

```python
def test_delete_playbook_round_trip(tmp_path):
    repo = _make_repo(tmp_path)
    pb = AssistantPlaybook.create(title="t", bullets=["a", "b"])
    repo.upsert_playbook(pb)
    assert repo.delete_playbook(pb.playbook_id) is True
    assert all(p.playbook_id != pb.playbook_id for p in repo.list_playbooks())


def test_delete_playbook_missing_id_returns_false(tmp_path):
    repo = _make_repo(tmp_path)
    assert repo.delete_playbook("not-real") is False
```

**Step 2 / 3 / 4 / 5:** Same pattern as Task 2.1.

```python
    def delete_playbook(self, playbook_id: str) -> bool:
        """Hard-delete one playbook. Returns True if a row was deleted."""
        with self._transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM assistant_playbooks WHERE playbook_id = ?",
                (playbook_id,),
            )
            return cursor.rowcount > 0
```

Commit:
```
git commit -m "feat(m23): AssistantRepository.delete_playbook"
```

---

### Task 2.4: `WorkspaceOrchestrator` wrapper methods

**Files:**
- Modify: `metis_app/services/workspace_orchestrator.py` (find the existing `clear_assistant_memory` method, add the new wrappers near it)
- Test: skip — these are 1-line passthroughs; tested transitively through Task 2.5

**Step 1: Add three wrapper methods**

Locate the existing `clear_assistant_memory` method in `workspace_orchestrator.py` and add nearby:

```python
    def delete_assistant_memory_entry(self, entry_id: str) -> dict[str, Any]:
        ok = self._assistant_repo.delete_memory_entry(entry_id)
        return {"ok": ok}

    def delete_assistant_memory_by_kind(self, kind: str) -> dict[str, Any]:
        deleted = self._assistant_repo.delete_memory_by_kind(kind)
        return {"ok": True, "deleted_count": deleted}

    def delete_assistant_playbook(self, playbook_id: str) -> dict[str, Any]:
        ok = self._assistant_repo.delete_playbook(playbook_id)
        return {"ok": ok}
```

(If the existing repo attribute name is not `self._assistant_repo`, match what `clear_assistant_memory` uses.)

**Step 2: Commit**

```
git add metis_app/services/workspace_orchestrator.py
git commit -m "feat(m23): orchestrator wrappers for memory/playbook delete"
```

---

### Task 2.5: Three new Litestar routes

**Files:**
- Modify: `metis_app/api_litestar/routes/assistant.py`
- Test: `tests/test_assistant_routes.py` (find the existing test file for assistant routes — likely `tests/test_api_litestar.py` or `tests/test_assistant_routes.py`. Match its fixture pattern.)

**Step 1: Write the failing tests**

Three integration tests, one per route. Use `litestar.testing.TestClient` per the existing pattern (find an example in the file — assistant route tests already exist for `POST /v1/assistant`).

```python
def test_delete_memory_entry_route_round_trip(client_with_seeded_memory):
    # Fixture seeds one entry with id "seed-1"
    response = client_with_seeded_memory.delete("/v1/assistant/memory/seed-1")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_delete_memory_entry_route_missing_id(client):
    response = client.delete("/v1/assistant/memory/does-not-exist")
    assert response.status_code == 200
    assert response.json() == {"ok": False}


def test_delete_memory_by_kind_route(client_with_seeded_memory):
    # Fixture seeds 3 entries of kind "reflection"
    response = client_with_seeded_memory.delete("/v1/assistant/memory/by-kind?kind=reflection")
    assert response.status_code == 200
    assert response.json()["deleted_count"] == 3


def test_delete_playbook_route_round_trip(client_with_seeded_playbook):
    response = client_with_seeded_playbook.delete("/v1/assistant/playbooks/pb-1")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
```

**Step 2: Run tests to verify they fail**

```
pytest tests/test_assistant_routes.py -k "delete" -v
```
Expected: 4 FAIL — 404 from Litestar (route not registered).

**Step 3: Write minimal implementation**

In `metis_app/api_litestar/routes/assistant.py`, after the existing `clear_assistant_memory` handler (line ~85), add three new handlers and register them in the `Router` at the bottom of the file:

```python
@delete("/v1/assistant/memory/{entry_id:str}", status_code=200)
def delete_memory_entry(entry_id: str) -> dict:
    return WorkspaceOrchestrator().delete_assistant_memory_entry(entry_id)


@delete("/v1/assistant/memory/by-kind", status_code=200)
def delete_memory_by_kind(kind: str) -> dict:
    return WorkspaceOrchestrator().delete_assistant_memory_by_kind(kind)


@delete("/v1/assistant/playbooks/{playbook_id:str}", status_code=200)
def delete_playbook(playbook_id: str) -> dict:
    return WorkspaceOrchestrator().delete_assistant_playbook(playbook_id)
```

Add the three handler names to the `Router(path="", route_handlers=[...])` list at the bottom.

**Note on route ordering:** Litestar matches `/v1/assistant/memory/by-kind` before `/v1/assistant/memory/{entry_id:str}` only if the static path is registered first. Verify by reading the route list — register `delete_memory_by_kind` *above* `delete_memory_entry` in the handler list to be safe. The test for `delete_memory_entry_route_round_trip` will catch a misorder.

**Step 4: Run tests to verify they pass**

```
pytest tests/test_assistant_routes.py -k "delete" -v
```
Expected: 4 PASS.

**Step 5: Commit**

```
git add metis_app/api_litestar/routes/assistant.py tests/test_assistant_routes.py
git commit -m "feat(m23): DELETE routes for memory entry / by-kind / playbook"
```

---

## Phase 3 — Front-end: PersonalityCard (~1 day)

### Task 3.1: Restructure Companion tab into sub-components (DOM-only)

**Files:**
- Create: `apps/metis-web/components/settings/companion/identity-card.tsx`
- Create: `apps/metis-web/components/settings/companion/reflection-policy-card.tsx`
- Create: `apps/metis-web/components/settings/companion/runtime-card.tsx`
- Modify: `apps/metis-web/app/settings/page.tsx:1631–~end-of-companion-tab`

**Spec:**

Move the existing JSX inside `<TabsContent value="companion">` (starting ~line 1631) into three sub-components, keeping the form binding at the page level. Each component takes `{ form }` (the react-hook-form `assistantForm` instance) as a prop.

```tsx
// apps/metis-web/components/settings/companion/identity-card.tsx
"use client";

import type { UseFormReturn } from "react-hook-form";
import type { AssistantFormValues } from "@/app/settings/page";
// ... import existing UI primitives (FieldLabel, Input, Textarea, ToggleRow, etc.)

interface Props {
  form: UseFormReturn<AssistantFormValues>;
}

export function IdentityCard({ form }: Props) {
  // Move lines 1655-1740-ish here. Use form.register, form.watch, form.setValue.
  return (/* ... existing JSX ... */);
}
```

Same shape for `<ReflectionPolicyCard>` and `<RuntimeCard>`. The `prompt_seed` Textarea moves out of `IdentityCard` into the new `PersonalityCard` (Task 3.2).

**Verification (no test):**

```
cd apps/metis-web && pnpm run typecheck
```
Expected: no new errors. Then start dev server and visit `/settings#companion` — page renders identically to before.

**Commit:**

```
git add apps/metis-web/components/settings/companion/ apps/metis-web/app/settings/page.tsx
git commit -m "refactor(m23): split Companion settings tab into sub-cards"
```

---

### Task 3.2: PersonalityCard with preset radio + auto-fill on change

**Files:**
- Create: `apps/metis-web/components/settings/companion/personality-card.tsx`
- Create: `apps/metis-web/components/settings/companion/__tests__/personality-card.test.tsx`
- Create: `apps/metis-web/lib/companion-voice.ts` (mirror of backend `TONE_PRESETS` for client-side preview + auto-fill)
- Modify: `apps/metis-web/app/settings/page.tsx` (mount the new card and update zod schema to include `tone_preset`)

**Step 1: Write the failing test**

`personality-card.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useForm } from "react-hook-form";
import { PersonalityCard } from "../personality-card";
import { TONE_PRESETS } from "@/lib/companion-voice";

function Harness({ initial }: { initial: { tone_preset: string; prompt_seed: string } }) {
  const form = useForm({
    defaultValues: {
      assistant_identity: { ...initial },
    },
  });
  return <PersonalityCard form={form as any} />;
}

describe("PersonalityCard", () => {
  it("auto-fills prompt seed when switching from a preset that matches", () => {
    render(<Harness initial={{ tone_preset: "warm-curious", prompt_seed: TONE_PRESETS["warm-curious"] }} />);
    fireEvent.click(screen.getByRole("radio", { name: /concise analyst/i }));
    // Resolved-seed preview shows the new preset's seed
    expect(screen.getByTestId("resolved-seed-preview")).toHaveTextContent(/clinical/i);
  });

  it("flips tone_preset to 'custom' when the user types in the override textarea", () => {
    render(<Harness initial={{ tone_preset: "warm-curious", prompt_seed: TONE_PRESETS["warm-curious"] }} />);
    fireEvent.click(screen.getByRole("button", { name: /edit prompt seed directly/i }));
    fireEvent.change(screen.getByLabelText(/prompt seed/i), { target: { value: "I am a pirate." } });
    // The "Custom" radio is now checked
    expect(screen.getByRole("radio", { name: /custom/i })).toBeChecked();
  });

  it("shows confirm dialog when switching presets while in custom mode", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<Harness initial={{ tone_preset: "custom", prompt_seed: "Pirate persona" }} />);
    fireEvent.click(screen.getByRole("radio", { name: /warm & curious/i }));
    expect(confirmSpy).toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
```

**Step 2: Run tests to verify they fail**

```
cd apps/metis-web && pnpm vitest run components/settings/companion/__tests__/personality-card
```
Expected: FAIL — `Cannot find module 'personality-card'`.

**Step 3: Write minimal implementation**

`apps/metis-web/lib/companion-voice.ts`:

```ts
export const TONE_PRESETS: Record<string, string> = {
  "warm-curious":
    "You are METIS, a local-first companion who helps the user get oriented, " +
    "suggests next steps, and records concise reflections without taking over " +
    "the main chat. Keep replies warm and exploratory.",
  "concise-analyst":
    "You are METIS, a local-first companion who helps the user get oriented, " +
    "suggests next steps, and records concise reflections without taking over " +
    "the main chat. Keep replies brief and clinical. Lead with the answer; " +
    "cite sources before commentary.",
  "playful":
    "You are METIS, a local-first companion who helps the user get oriented, " +
    "suggests next steps, and records concise reflections without taking over " +
    "the main chat. Keep replies relaxed and a touch wry.",
};

export type TonePreset = keyof typeof TONE_PRESETS | "custom";

export const TONE_PRESET_LABELS: Record<TonePreset, string> = {
  "warm-curious": "Warm & curious",
  "concise-analyst": "Concise analyst",
  "playful": "Playful collaborator",
  "custom": "Custom (advanced)",
};

export function isCustomSeed(tonePreset: string, promptSeed: string): boolean {
  if (tonePreset === "custom") return true;
  if (!(tonePreset in TONE_PRESETS)) return false;
  return promptSeed !== "" && promptSeed !== TONE_PRESETS[tonePreset];
}
```

`apps/metis-web/components/settings/companion/personality-card.tsx`:

```tsx
"use client";

import { useState } from "react";
import type { UseFormReturn } from "react-hook-form";
import type { AssistantFormValues } from "@/app/settings/page";
import { TONE_PRESETS, TONE_PRESET_LABELS, isCustomSeed, type TonePreset } from "@/lib/companion-voice";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { FieldLabel } from "@/app/settings/page"; // or wherever FieldLabel is defined

interface Props {
  form: UseFormReturn<AssistantFormValues>;
}

export function PersonalityCard({ form }: Props) {
  const tonePreset = form.watch("assistant_identity.tone_preset") as TonePreset;
  const promptSeed = form.watch("assistant_identity.prompt_seed");
  const [showOverride, setShowOverride] = useState(false);

  function handlePresetChange(next: TonePreset) {
    const currentlyCustom = isCustomSeed(tonePreset, promptSeed);
    if (currentlyCustom && next !== "custom") {
      const ok = window.confirm(
        "Switching presets will overwrite your custom prompt seed. Continue?"
      );
      if (!ok) return;
    }
    form.setValue("assistant_identity.tone_preset", next, { shouldDirty: true });
    if (next !== "custom") {
      form.setValue("assistant_identity.prompt_seed", TONE_PRESETS[next], { shouldDirty: true });
    }
  }

  function handleOverrideChange(value: string) {
    form.setValue("assistant_identity.prompt_seed", value, { shouldDirty: true });
    if (tonePreset !== "custom") {
      form.setValue("assistant_identity.tone_preset", "custom", { shouldDirty: true });
    }
  }

  const resolvedSeed =
    tonePreset === "custom"
      ? promptSeed
      : (TONE_PRESETS as Record<string, string>)[tonePreset] ?? TONE_PRESETS["warm-curious"];

  return (
    <section className="space-y-4 rounded-2xl border border-white/8 bg-black/10 p-4">
      <div>
        <h3 className="text-sm font-semibold">Personality</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">How should METIS speak?</p>
      </div>

      <fieldset className="space-y-2">
        {(Object.keys(TONE_PRESET_LABELS) as TonePreset[]).map((preset) => (
          <label key={preset} className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="tone_preset"
              checked={tonePreset === preset}
              onChange={() => handlePresetChange(preset)}
              aria-label={TONE_PRESET_LABELS[preset]}
            />
            {TONE_PRESET_LABELS[preset]}
          </label>
        ))}
      </fieldset>

      <div className="space-y-2 rounded-xl border border-white/8 bg-black/20 p-3">
        <div className="text-xs font-medium text-muted-foreground">Resolved prompt seed</div>
        <p data-testid="resolved-seed-preview" className="whitespace-pre-wrap text-xs">
          {resolvedSeed}
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setShowOverride((v) => !v)}
        >
          {showOverride ? "Hide" : "Edit prompt seed directly"}
        </Button>
        {showOverride && (
          <div className="space-y-1.5">
            <FieldLabel htmlFor="assistant_identity.prompt_seed_override">Prompt seed</FieldLabel>
            <Textarea
              id="assistant_identity.prompt_seed_override"
              rows={5}
              value={promptSeed}
              onChange={(e) => handleOverrideChange(e.target.value)}
            />
          </div>
        )}
      </div>
    </section>
  );
}
```

In `apps/metis-web/app/settings/page.tsx`:

1. Update the zod schema for `assistant_identity` to include `tone_preset: z.string().default("warm-curious")` and remove the `prompt_seed` field from the Identity card (move it into Personality).
2. Mount `<PersonalityCard form={assistantForm} />` between `<IdentityCard>` and `<ReflectionPolicyCard>`.
3. Update `ASSISTANT_DEFAULT_VALUES.assistant_identity` to include `tone_preset: "warm-curious"`.

**Step 4: Run tests to verify they pass**

```
cd apps/metis-web && pnpm vitest run components/settings/companion/__tests__/personality-card
```
Expected: 3 PASS.

Also run `pnpm run typecheck` — no new errors.

**Step 5: Commit**

```
git add apps/metis-web/components/settings/companion/personality-card.tsx \
        apps/metis-web/components/settings/companion/__tests__/personality-card.test.tsx \
        apps/metis-web/lib/companion-voice.ts \
        apps/metis-web/app/settings/page.tsx
git commit -m "feat(m23): PersonalityCard with tone presets + override disclosure"
```

---

## Phase 4 — Front-end: MemoryInspector (~1.5 days)

### Task 4.1: api.ts client methods for the three delete endpoints

**Files:**
- Modify: `apps/metis-web/lib/api.ts` (find the existing `clearAssistantMemory` helper; add the three new ones nearby)
- Test: `apps/metis-web/lib/__tests__/api.test.ts` (existing — append)

**Step 1: Write the failing test**

```ts
import { describe, it, expect, vi } from "vitest";
import {
  deleteAssistantMemoryEntry,
  deleteAssistantMemoryByKind,
  deleteAssistantPlaybook,
} from "../api";

describe("assistant memory delete clients", () => {
  it("calls DELETE /v1/assistant/memory/:id", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    );
    const result = await deleteAssistantMemoryEntry("abc-123");
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/v1/assistant/memory/abc-123"),
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(result.ok).toBe(true);
    fetchSpy.mockRestore();
  });

  it("calls DELETE /v1/assistant/memory/by-kind?kind=X", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true, deleted_count: 4 }), { status: 200 })
    );
    const result = await deleteAssistantMemoryByKind("skill");
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/v1/assistant/memory/by-kind?kind=skill"),
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(result.deleted_count).toBe(4);
    fetchSpy.mockRestore();
  });

  it("calls DELETE /v1/assistant/playbooks/:id", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    );
    await deleteAssistantPlaybook("pb-1");
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/v1/assistant/playbooks/pb-1"),
      expect.objectContaining({ method: "DELETE" }),
    );
    fetchSpy.mockRestore();
  });
});
```

**Step 2: Run tests to verify they fail**

```
cd apps/metis-web && pnpm vitest run lib/__tests__/api -t "assistant memory delete"
```
Expected: 3 FAIL — exports don't exist.

**Step 3: Write minimal implementation**

In `apps/metis-web/lib/api.ts`, near `clearAssistantMemory`:

```ts
export async function deleteAssistantMemoryEntry(entryId: string): Promise<{ ok: boolean }> {
  const res = await fetch(apiUrl(`/v1/assistant/memory/${encodeURIComponent(entryId)}`), {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`delete memory entry failed: ${res.status}`);
  return res.json();
}

export async function deleteAssistantMemoryByKind(kind: string): Promise<{ ok: boolean; deleted_count: number }> {
  const res = await fetch(apiUrl(`/v1/assistant/memory/by-kind?kind=${encodeURIComponent(kind)}`), {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`delete memory by kind failed: ${res.status}`);
  return res.json();
}

export async function deleteAssistantPlaybook(playbookId: string): Promise<{ ok: boolean }> {
  const res = await fetch(apiUrl(`/v1/assistant/playbooks/${encodeURIComponent(playbookId)}`), {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`delete playbook failed: ${res.status}`);
  return res.json();
}
```

(Use the `apiUrl()` helper that other functions in the file use. If it's named differently, match the local convention.)

**Step 4: Run tests to verify they pass**

```
cd apps/metis-web && pnpm vitest run lib/__tests__/api -t "assistant memory delete"
```
Expected: 3 PASS.

**Step 5: Commit**

```
git add apps/metis-web/lib/api.ts apps/metis-web/lib/__tests__/api.test.ts
git commit -m "feat(m23): api.ts delete clients for memory + playbook"
```

---

### Task 4.2: MemoryStatsRow component

**Files:**
- Create: `apps/metis-web/components/settings/companion/memory-stats-row.tsx`

This is a presentation-only component; no test (rendered values come straight from the snapshot prop).

**Implementation:**

```tsx
"use client";

import { formatDistanceToNow } from "date-fns";

interface Props {
  entryCount: number;
  maxEntries: number;
  playbookCount: number;
  lastReflectionAt?: string | null;
}

export function MemoryStatsRow({ entryCount, maxEntries, playbookCount, lastReflectionAt }: Props) {
  const reflectionLabel = lastReflectionAt
    ? `${formatDistanceToNow(new Date(lastReflectionAt))} ago`
    : "never";
  return (
    <div className="grid grid-cols-3 gap-3 text-xs">
      <Tile label="Memory entries" value={`${entryCount} / ${maxEntries}`} />
      <Tile label="Playbooks" value={`${playbookCount}`} />
      <Tile label="Last reflection" value={reflectionLabel} />
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/8 bg-black/10 p-3">
      <div className="text-muted-foreground">{label}</div>
      <div className="mt-1 font-medium text-foreground">{value}</div>
    </div>
  );
}
```

**Commit:**

```
git add apps/metis-web/components/settings/companion/memory-stats-row.tsx
git commit -m "feat(m23): MemoryStatsRow tile component"
```

---

### Task 4.3: MemoryInspector — grouped accordion + per-entry delete

**Files:**
- Create: `apps/metis-web/components/settings/companion/memory-inspector.tsx`
- Create: `apps/metis-web/components/settings/companion/__tests__/memory-inspector.test.tsx`
- Modify: `apps/metis-web/app/settings/page.tsx` (mount `<MemoryInspector />` between `<PersonalityCard>` and `<ReflectionPolicyCard>`)

**Step 1: Write the failing test**

`memory-inspector.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryInspector } from "../memory-inspector";

const SNAPSHOT = {
  identity: { name: "METIS" },
  status: { last_reflection_at: "2026-05-03T10:00:00+00:00" },
  policy: { max_memory_entries: 200 },
  memory: [
    { entry_id: "m1", kind: "reflection", title: "Note A", summary: "...", created_at: "2026-05-03T09:00:00+00:00", confidence: 0.7 },
    { entry_id: "m2", kind: "reflection", title: "Note B", summary: "...", created_at: "2026-05-03T08:00:00+00:00", confidence: 0.5 },
    { entry_id: "m3", kind: "skill", title: "Skill X", summary: "...", created_at: "2026-05-03T07:00:00+00:00", confidence: 0.9 },
  ],
  playbooks: [],
};

vi.mock("@/lib/api", () => ({
  fetchAssistantSnapshot: vi.fn(async () => SNAPSHOT),
  deleteAssistantMemoryEntry: vi.fn(async () => ({ ok: true })),
  deleteAssistantMemoryByKind: vi.fn(async () => ({ ok: true, deleted_count: 2 })),
  deleteAssistantPlaybook: vi.fn(async () => ({ ok: true })),
}));

describe("MemoryInspector", () => {
  it("optimistically removes an entry on delete", async () => {
    render(<MemoryInspector />);
    await waitFor(() => screen.getByText("Note A"));
    fireEvent.click(screen.getByLabelText(/delete Note A/i));
    expect(screen.queryByText("Note A")).not.toBeInTheDocument();
  });

  it("shows confirm and bulk-clears a kind group on accept", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MemoryInspector />);
    await waitFor(() => screen.getByText("Note A"));
    fireEvent.click(screen.getByRole("button", { name: /clear all reflection/i }));
    expect(confirmSpy).toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.queryByText("Note A")).not.toBeInTheDocument();
      expect(screen.queryByText("Note B")).not.toBeInTheDocument();
    });
    confirmSpy.mockRestore();
  });

  it("renders empty-state CTA when no entries", async () => {
    const { fetchAssistantSnapshot } = await import("@/lib/api");
    (fetchAssistantSnapshot as any).mockResolvedValueOnce({
      ...SNAPSHOT,
      memory: [],
      playbooks: [],
    });
    render(<MemoryInspector />);
    await waitFor(() => screen.getByText(/no reflections yet/i));
    expect(screen.getByRole("link", { name: /open a chat/i })).toHaveAttribute("href", "/chat");
  });
});
```

**Step 2: Run tests to verify they fail**

```
cd apps/metis-web && pnpm vitest run components/settings/companion/__tests__/memory-inspector
```
Expected: 3 FAIL.

**Step 3: Write minimal implementation**

`memory-inspector.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import {
  fetchAssistantSnapshot,
  deleteAssistantMemoryEntry,
  deleteAssistantMemoryByKind,
} from "@/lib/api";
import { MemoryStatsRow } from "./memory-stats-row";
import { Button } from "@/components/ui/button";

interface MemoryEntry {
  entry_id: string;
  kind: string;
  title: string;
  summary: string;
  created_at: string;
  confidence: number;
}

export function MemoryInspector() {
  const [snapshot, setSnapshot] = useState<any | null>(null);

  useEffect(() => {
    fetchAssistantSnapshot().then(setSnapshot).catch(() => setSnapshot(null));
  }, []);

  if (!snapshot) {
    return <div className="text-sm text-muted-foreground">Loading memory…</div>;
  }

  const entries: MemoryEntry[] = snapshot.memory ?? [];
  const playbooks = snapshot.playbooks ?? [];

  if (entries.length === 0 && playbooks.length === 0) {
    return (
      <section className="space-y-3 rounded-2xl border border-white/8 bg-black/10 p-4">
        <h3 className="text-sm font-semibold">Memory</h3>
        <p className="text-xs text-muted-foreground">
          No reflections yet. <a href="/chat" className="underline">Open a chat</a> or run autonomous research to seed memory.
        </p>
      </section>
    );
  }

  const grouped = entries.reduce<Record<string, MemoryEntry[]>>((acc, e) => {
    (acc[e.kind] ||= []).push(e);
    return acc;
  }, {});

  async function handleDeleteEntry(entry: MemoryEntry) {
    setSnapshot((prev: any) => ({
      ...prev,
      memory: prev.memory.filter((e: MemoryEntry) => e.entry_id !== entry.entry_id),
    }));
    try {
      await deleteAssistantMemoryEntry(entry.entry_id);
    } catch (err) {
      // rollback
      setSnapshot((prev: any) => ({ ...prev, memory: [...prev.memory, entry] }));
    }
  }

  async function handleClearKind(kind: string) {
    const ok = window.confirm(
      `Clear all ${grouped[kind].length} ${kind} entries? This cannot be undone.`
    );
    if (!ok) return;
    setSnapshot((prev: any) => ({
      ...prev,
      memory: prev.memory.filter((e: MemoryEntry) => e.kind !== kind),
    }));
    await deleteAssistantMemoryByKind(kind);
  }

  return (
    <section className="space-y-4 rounded-2xl border border-white/8 bg-black/10 p-4">
      <h3 className="text-sm font-semibold">Memory</h3>
      <MemoryStatsRow
        entryCount={entries.length}
        maxEntries={snapshot.policy?.max_memory_entries ?? 200}
        playbookCount={playbooks.length}
        lastReflectionAt={snapshot.status?.last_reflection_at}
      />
      <div className="space-y-3">
        {Object.entries(grouped).map(([kind, list]) => (
          <details key={kind} className="rounded-xl border border-white/8 bg-black/20 p-3">
            <summary className="flex cursor-pointer items-center justify-between text-xs font-medium">
              <span>{kind} ({list.length})</span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`clear all ${kind}`}
                onClick={(e) => { e.preventDefault(); handleClearKind(kind); }}
              >
                clear all
              </Button>
            </summary>
            <ul className="mt-2 space-y-2">
              {list.map((entry) => (
                <li key={entry.entry_id} className="flex items-start justify-between gap-2 text-xs">
                  <div>
                    <div className="font-medium">{entry.title}</div>
                    <div className="text-muted-foreground">{entry.summary}</div>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={`delete ${entry.title}`}
                    onClick={() => handleDeleteEntry(entry)}
                  >
                    ✕
                  </Button>
                </li>
              ))}
            </ul>
          </details>
        ))}
      </div>
    </section>
  );
}
```

If `fetchAssistantSnapshot` does not yet exist in `api.ts`, find the existing fetch helper that calls `GET /v1/assistant` and either alias it or add a thin wrapper. (`getAssistantConfig` may already do this.)

**Step 4: Run tests to verify they pass**

```
cd apps/metis-web && pnpm vitest run components/settings/companion/__tests__/memory-inspector
```
Expected: 3 PASS.

**Step 5: Commit**

```
git add apps/metis-web/components/settings/companion/memory-inspector.tsx \
        apps/metis-web/components/settings/companion/__tests__/memory-inspector.test.tsx \
        apps/metis-web/app/settings/page.tsx \
        apps/metis-web/lib/api.ts
git commit -m "feat(m23): MemoryInspector grouped accordion + delete actions"
```

---

### Task 4.4: At-cap hint with "Clear oldest 50"

**Files:**
- Modify: `apps/metis-web/components/settings/companion/memory-inspector.tsx`

**Spec:** When `entries.length >= maxEntries`, render a hint above the accordion: `Older entries auto-evict at the cap.` with a button `Clear oldest 50` that calls the existing `clearAssistantMemory(50)` helper. Optimistic UI: drop the oldest 50 from `snapshot.memory` immediately; rollback on error.

**Manual verification (no new test — covered by Task 4.3's optimistic-delete pattern):**

1. Seed 200 memory entries via the API (`POST /v1/assistant/record-reflection` x200).
2. Visit `/settings#companion`.
3. See the hint + button.
4. Click the button. 50 oldest disappear. Counter goes to 150 / 200.

**Commit:**

```
git add apps/metis-web/components/settings/companion/memory-inspector.tsx
git commit -m "feat(m23): at-cap hint + clear-oldest-50 fallback"
```

---

## Phase 5 — Dock link (~1 hour)

### Task 5.1: Settings ↗ link in companion-dock minimised header

**Files:**
- Modify: `apps/metis-web/components/shell/metis-companion-dock.tsx` (find the minimised-header JSX; likely near where `handleMinimizeToggle` is rendered)

**Spec:** Add a small text-link near the minimised header (or in the dock's overflow menu if more appropriate visually). Href: `/settings#companion`. Label: `Settings ↗`. Visible only when `isMinimized === true` (the link is redundant when the dock is expanded — the user can navigate via the existing settings nav).

**Verification:**

```tsx
// In an existing or new test in metis-companion-dock.test.tsx
it("renders settings deep-link in minimised mode", () => {
  // ... mount component in minimised state ...
  const link = screen.getByRole("link", { name: /settings ↗/i });
  expect(link).toHaveAttribute("href", "/settings#companion");
});
```

**Commit:**

```
git add apps/metis-web/components/shell/metis-companion-dock.tsx \
        apps/metis-web/components/shell/__tests__/metis-companion-dock.test.tsx
git commit -m "feat(m23): companion-dock minimised header gets Settings deep-link"
```

---

## Phase 6 — Verify + audit cross-reference (~half-day)

### Task 6.1: Browser-preview verification (the 9-step QA from the design doc)

**Spec:** Start the dev server. Walk these 9 steps and screenshot any failure for follow-up.

1. Load `/settings#companion`. New layout renders without console errors.
2. Toggle each tone preset. Resolved-seed preview updates. Save. Toast appears. Reload. Selection persists.
3. Toggle to "Custom" and edit the textarea. Save. Reload. Custom text persists.
4. Switch from "Custom" back to a preset. Confirm appears. Accept. Custom text gone.
5. Open Memory tab. Stats row populates from `get_snapshot`.
6. Delete one entry. Disappears immediately. Cap-counter decrements. Reload. Still gone.
7. Bulk-clear one `kind` group. Confirm dialog. Accept. All entries in that group disappear.
8. From `/`, click `Settings ↗` in the minimised companion dock. Lands on `/settings#companion`.
9. Toggle prefers-reduced-motion in DevTools. No animation regressions.

If any step fails, write a regression test, fix, re-walk. Commit each fix as `fix(m23): <symptom>`.

---

### Task 6.2: Flip Shape of AI gaps #1 + #2 from ❌ to ✅

**Files:**
- Modify: `docs/preserve-and-productize-plan.md` — *Per-pattern scorecard* table:
  - Tuners → Voice and tone: ❌ → ✅
  - Identifiers → Personality: ❌ → ✅
  - Governors → Memory: ⚠️ → ✅

Append a `*Closed by M23 (PR #XXX, YYYY-MM-DD)*` annotation to each row's Notes column.

Also update the *Top 10 highest-leverage gaps* list — gaps #1 and #2 already say "Promoted as M23 (2026-05-03)"; add `→ Landed (PR #XXX)`.

**Commit:**

```
git add docs/preserve-and-productize-plan.md
git commit -m "docs(m23): flip Shape of AI gaps #1 + #2 to landed in audit"
```

---

### Task 6.3: Update IDEAS.md and IMPLEMENTATION.md

**Files:**
- Modify: `plans/IDEAS.md` (the Shape of AI entry's Decision line)
- Modify: `plans/IMPLEMENTATION.md` (M23 row: Status → Landed; Last updated → today; merge SHA + PR link)

**Decision-line update for IDEAS.md:**

Append: `M23 landed YYYY-MM-DD (PR #XXX). Gaps #1 + #2 closed.`

**M23 row update in IMPLEMENTATION.md:**

`Status: Landed`. `Claim: Landed via PR #XXX (<merge sha>, YYYY-MM-DD)`. `Last updated: YYYY-MM-DD`.

**Commit:**

```
git add plans/IDEAS.md plans/IMPLEMENTATION.md
git commit -m "docs(m23): mark milestone landed in IDEAS + IMPLEMENTATION"
```

---

### Task 6.4: Open the PR

```
git push -u origin <branch>
gh pr create --title "M23: Companion controls — tone presets + memory inspector" --body "$(cat <<'EOF'
## Summary

- Closes Shape of AI pattern audit gaps #1 (Voice and tone + Personality) and #2 (Memory inspector).
- Adds `tone_preset` field on `AssistantIdentity` + `TONE_PRESETS` dict + seed-resolution rule.
- Adds `DELETE /v1/assistant/memory/{entry_id}`, `DELETE /v1/assistant/memory/by-kind?kind=X`, `DELETE /v1/assistant/playbooks/{playbook_id}` routes + matching repository methods.
- Restructures the `/settings → Companion` tab into sub-cards: Identity, **Personality** (new), **Memory** (new), Reflection policy, Runtime.
- Adds `Settings ↗` deep-link in the companion-dock minimised header.

## Plan + design

- Design: `docs/plans/2026-05-03-companion-controls-design.md`
- Implementation plan: `docs/plans/2026-05-03-companion-controls-implementation.md`
- Plan stub: `plans/companion-controls/plan.md`

## Test plan

- [ ] Backend: `pytest tests/test_assistant_types.py tests/test_companion_voice.py tests/test_assistant_repository.py tests/test_assistant_companion.py tests/test_assistant_routes.py` all green
- [ ] Frontend: `cd apps/metis-web && pnpm vitest run components/settings/companion lib/__tests__/api` all green
- [ ] Frontend typecheck: `pnpm run typecheck` clean
- [ ] Browser preview: 9-step QA walk per design doc Phase 6 completed

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Done definition

- All 17 tasks landed.
- Backend pytest suite green; frontend vitest + typecheck green.
- 9-step browser-preview QA complete.
- Shape of AI audit reflects ✅ on gaps #1 + #2.
- IMPLEMENTATION.md M23 row at `Status: Landed` with merge SHA.
- IDEAS.md decision line updated.
- PR open, ready for review.

## What's explicitly out of scope (do not add)

- Avatar customisation (vision-tense; defer to ADR).
- Memory edit / add (corruption-prone; not promised by VISION).
- Soft tombstones (existing `clear_recent_memory` is hard-delete; staying consistent).
- Per-tone retraining or model swap (single `prompt_seed` is the only knob).
- Surfacing memory in the companion dock (one canonical home is `/settings`).
- Localised tone-preset names (defer until i18n is a real requirement).
