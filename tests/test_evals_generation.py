"""M16 Phase 2 — companion-generation hashing tests.

ADR 0017 picks a content-addressed ``generation_id`` so that:

- restart does not invent a new generation,
- reverting to a prior config reuses the same generation,
- M18 can compare candidate vs current LoRA adapters across the same
  surface used by interactive runs.

These tests pin the hashing contract (deterministic, change-sensitive
where it matters, change-insensitive where it does not) and the
``bump_if_needed`` insert-or-reuse behaviour.
"""

from __future__ import annotations

from pathlib import Path

from metis_app.evals.generation import (
    GENERATION_SETTINGS,
    bump_if_needed,
    current_generation_id,
)
from metis_app.evals.store import EvalStore


_BASE_SETTINGS = {
    "llm_provider": "anthropic",
    "llm_model": "claude-opus-4-6",
    "llm_model_custom": "",
    "embedding_provider": "voyage",
    "embedding_model": "voyage-4-large",
    "retrieval_mode": "flat",
    "retrieval_k": 25,
    "agentic_mode": False,
    "agentic_max_iterations": 2,
    "agentic_convergence_threshold": 0.95,
    "use_reranker": True,
    "use_sub_queries": True,
    "selected_mode": "Q&A",
    "local_gguf_model_path": "",
    "local_gguf_context_length": 2048,
    # Cosmetic / non-material settings — must NOT affect the hash.
    "theme": "space_dust",
    "verbose_mode": False,
    "log_level": "DEBUG",
}


def _make_store(tmp_path: Path) -> EvalStore:
    store = EvalStore(tmp_path / "evals.db")
    store.init_db()
    return store


def test_current_generation_id_is_deterministic() -> None:
    a = current_generation_id(
        settings=_BASE_SETTINGS,
        enabled_skill_ids=["skill-a", "skill-b"],
        lora_adapter_id=None,
    )
    b = current_generation_id(
        settings=_BASE_SETTINGS,
        enabled_skill_ids=["skill-a", "skill-b"],
        lora_adapter_id=None,
    )
    assert a == b
    # Sanity check on the hash shape (sha256 hex digest).
    assert len(a) == 64
    assert all(c in "0123456789abcdef" for c in a)


def test_current_generation_id_skill_set_is_order_independent() -> None:
    a = current_generation_id(
        settings=_BASE_SETTINGS,
        enabled_skill_ids=["b", "a", "c"],
        lora_adapter_id=None,
    )
    b = current_generation_id(
        settings=_BASE_SETTINGS,
        enabled_skill_ids=["c", "a", "b"],
        lora_adapter_id=None,
    )
    assert a == b


def test_current_generation_id_changes_when_model_changes() -> None:
    a = current_generation_id(
        settings=_BASE_SETTINGS,
        enabled_skill_ids=[],
        lora_adapter_id=None,
    )
    swapped = dict(_BASE_SETTINGS)
    swapped["llm_model"] = "claude-haiku-4-5"
    b = current_generation_id(
        settings=swapped,
        enabled_skill_ids=[],
        lora_adapter_id=None,
    )
    assert a != b


def test_current_generation_id_changes_when_skill_set_changes() -> None:
    a = current_generation_id(
        settings=_BASE_SETTINGS,
        enabled_skill_ids=["skill-a"],
        lora_adapter_id=None,
    )
    b = current_generation_id(
        settings=_BASE_SETTINGS,
        enabled_skill_ids=["skill-a", "skill-b"],
        lora_adapter_id=None,
    )
    assert a != b


def test_current_generation_id_changes_when_lora_changes() -> None:
    a = current_generation_id(
        settings=_BASE_SETTINGS,
        enabled_skill_ids=[],
        lora_adapter_id=None,
    )
    b = current_generation_id(
        settings=_BASE_SETTINGS,
        enabled_skill_ids=[],
        lora_adapter_id="lora-1",
    )
    assert a != b


def test_current_generation_id_unaffected_by_cosmetic_setting() -> None:
    a = current_generation_id(
        settings=_BASE_SETTINGS,
        enabled_skill_ids=[],
        lora_adapter_id=None,
    )
    cosmetic = dict(_BASE_SETTINGS)
    cosmetic["theme"] = "midnight"
    cosmetic["verbose_mode"] = True
    cosmetic["log_level"] = "INFO"
    b = current_generation_id(
        settings=cosmetic,
        enabled_skill_ids=[],
        lora_adapter_id=None,
    )
    assert a == b


def test_current_generation_id_changes_when_material_setting_changes() -> None:
    a = current_generation_id(
        settings=_BASE_SETTINGS,
        enabled_skill_ids=[],
        lora_adapter_id=None,
    )
    swapped = dict(_BASE_SETTINGS)
    swapped["retrieval_mode"] = "iterative"
    b = current_generation_id(
        settings=swapped,
        enabled_skill_ids=[],
        lora_adapter_id=None,
    )
    assert a != b


def test_generation_settings_allowlist_is_a_tuple() -> None:
    # GENERATION_SETTINGS is the canonical material-settings allowlist.
    # Tuple type prevents accidental mutation from outside the module.
    assert isinstance(GENERATION_SETTINGS, tuple)
    assert "llm_model" in GENERATION_SETTINGS
    assert "retrieval_mode" in GENERATION_SETTINGS
    # Cosmetic settings must NOT appear in the allowlist.
    assert "theme" not in GENERATION_SETTINGS
    assert "log_level" not in GENERATION_SETTINGS


def test_bump_if_needed_inserts_first_time(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    gen = bump_if_needed(
        store,
        settings=_BASE_SETTINGS,
        enabled_skill_ids=["a"],
        lora_adapter_id=None,
        notes="initial",
    )
    assert gen.generation_id == current_generation_id(
        settings=_BASE_SETTINGS,
        enabled_skill_ids=["a"],
        lora_adapter_id=None,
    )
    fetched = store.get_generation(gen.generation_id)
    assert fetched is not None
    assert fetched.notes == "initial"


def test_bump_if_needed_reuses_existing_on_repeat(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    a = bump_if_needed(
        store,
        settings=_BASE_SETTINGS,
        enabled_skill_ids=["a"],
        lora_adapter_id=None,
        notes="initial",
    )
    b = bump_if_needed(
        store,
        settings=_BASE_SETTINGS,
        enabled_skill_ids=["a"],
        lora_adapter_id=None,
        notes="should-not-overwrite",
    )
    assert a.generation_id == b.generation_id
    fetched = store.get_generation(a.generation_id)
    assert fetched is not None
    # The original notes survive — first-seen-at and the original notes
    # must remain stable so the comparison surface stays honest.
    assert fetched.notes == "initial"


# ----------------------------------------------------------------------
# Phase 2 review (PR #599 item 2) — assistant_runtime is a mixed dict
# of behavior-affecting fields (provider, model, GGUF tuning) and
# volatile non-behavioral fields (bootstrap_state, recommended_*,
# auto_install). Hashing the whole block bumps generations on
# bootstrap-state transitions and hardware-detection refreshes, which
# fragments week-over-week comparisons. The hash must project
# assistant_runtime to a stable material-only subset.
# ----------------------------------------------------------------------


_RUNTIME_BASE = dict(_BASE_SETTINGS, assistant_runtime={
    "provider": "anthropic",
    "model": "claude-opus-4-6",
    "local_gguf_model_path": "",
    "local_gguf_context_length": 2048,
    "local_gguf_gpu_layers": 0,
    "local_gguf_threads": 0,
    "fallback_to_primary": True,
    "auto_bootstrap": True,
    "auto_install": False,
    "bootstrap_state": "pending",
    "recommended_model_name": "",
    "recommended_quant": "",
    "recommended_use_case": "chat",
})


def test_generation_id_unaffected_by_assistant_runtime_bootstrap_state() -> None:
    base = current_generation_id(
        settings=_RUNTIME_BASE,
        enabled_skill_ids=[],
        lora_adapter_id=None,
    )
    flipped = dict(_RUNTIME_BASE)
    flipped["assistant_runtime"] = dict(
        _RUNTIME_BASE["assistant_runtime"], bootstrap_state="complete"
    )
    later = current_generation_id(
        settings=flipped,
        enabled_skill_ids=[],
        lora_adapter_id=None,
    )
    assert base == later


def test_generation_id_unaffected_by_recommended_metadata() -> None:
    base = current_generation_id(
        settings=_RUNTIME_BASE,
        enabled_skill_ids=[],
        lora_adapter_id=None,
    )
    flipped = dict(_RUNTIME_BASE)
    flipped["assistant_runtime"] = dict(
        _RUNTIME_BASE["assistant_runtime"],
        recommended_model_name="phi-3.5-mini",
        recommended_quant="Q4_K_M",
        recommended_use_case="chat",
        auto_install=True,
    )
    later = current_generation_id(
        settings=flipped,
        enabled_skill_ids=[],
        lora_adapter_id=None,
    )
    assert base == later


def test_generation_id_changes_when_assistant_runtime_provider_changes() -> None:
    base = current_generation_id(
        settings=_RUNTIME_BASE,
        enabled_skill_ids=[],
        lora_adapter_id=None,
    )
    flipped = dict(_RUNTIME_BASE)
    flipped["assistant_runtime"] = dict(
        _RUNTIME_BASE["assistant_runtime"], provider="local"
    )
    later = current_generation_id(
        settings=flipped,
        enabled_skill_ids=[],
        lora_adapter_id=None,
    )
    assert base != later


def test_generation_id_changes_when_assistant_runtime_model_changes() -> None:
    base = current_generation_id(
        settings=_RUNTIME_BASE,
        enabled_skill_ids=[],
        lora_adapter_id=None,
    )
    flipped = dict(_RUNTIME_BASE)
    flipped["assistant_runtime"] = dict(
        _RUNTIME_BASE["assistant_runtime"], model="claude-haiku-4-5"
    )
    later = current_generation_id(
        settings=flipped,
        enabled_skill_ids=[],
        lora_adapter_id=None,
    )
    assert base != later


def test_bump_if_needed_inserts_again_after_change(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    a = bump_if_needed(
        store,
        settings=_BASE_SETTINGS,
        enabled_skill_ids=[],
        lora_adapter_id=None,
        notes="initial",
    )
    swapped = dict(_BASE_SETTINGS)
    swapped["llm_model"] = "claude-haiku-4-5"
    b = bump_if_needed(
        store,
        settings=swapped,
        enabled_skill_ids=[],
        lora_adapter_id=None,
        notes="user-swapped-to-haiku",
    )
    assert a.generation_id != b.generation_id
    fetched = store.get_generation(b.generation_id)
    assert fetched is not None
    assert fetched.notes == "user-swapped-to-haiku"
