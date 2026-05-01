"""Companion-generation versioning (ADR 0017 §4 + §5).

A ``generation_id`` is the SHA-256 of a canonical JSON object built from
the material runtime fingerprint (model spec, LoRA adapter id, enabled
skill set hash, and a curated allowlist of behavior-shaping settings).
Material settings change behavior in a way that makes score comparisons
unfair; cosmetic settings do not. The allowlist lives here so future
edits to ``GENERATION_SETTINGS`` are reviewable as code rather than
hidden in scattered call sites.

The runner (Phase 3) calls ``bump_if_needed`` once per eval run so a
fresh generation row exists before any ``runs.generation_id`` value is
inserted. Reverting to a prior config naturally reuses the same
generation, because the hash is content-addressed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable

from .store import EvalGeneration, EvalStore


# The canonical material-settings allowlist. Anything outside this tuple
# is excluded from the fingerprint, so theme / log-level / verbosity /
# UI toggles do not bump generations on their own. Edits here are
# behaviour-affecting and must be reviewed alongside ADR 0017.
GENERATION_SETTINGS: tuple[str, ...] = (
    # LLM choice + invocation parameters that change inference output.
    "llm_provider",
    "llm_model",
    "llm_model_custom",
    "llm_temperature",
    "llm_max_tokens",
    # Embedding choice — changes retrieval geometry.
    "embedding_provider",
    "embedding_model",
    "embedding_model_custom",
    # Retrieval pipeline.
    "retrieval_mode",
    "retrieval_k",
    "retrieval_min_score",
    "search_type",
    "hybrid_alpha",
    "mmr_lambda",
    "use_reranker",
    "use_sub_queries",
    "knowledge_search_top_k",
    "top_k",
    # Agentic behaviour.
    "agentic_mode",
    "agentic_max_iterations",
    "agentic_iteration_budget",
    "agentic_convergence_threshold",
    "agentic_context_compress_enabled",
    # Mode + chat shape that change prompt construction.
    "selected_mode",
    "chat_path",
    "system_instructions",
    # Local GGUF runtime details.
    "local_gguf_model_path",
    "local_gguf_context_length",
    # Companion runtime block (provider/model overrides, fallback policy).
    "assistant_runtime",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_skill_set(enabled_skill_ids: Iterable[str]) -> str:
    normalized = sorted({str(sid) for sid in enabled_skill_ids if str(sid)})
    return _sha256_hex(_canonical_json(normalized))


def _hash_settings(settings: dict[str, Any]) -> str:
    material: dict[str, Any] = {}
    for key in GENERATION_SETTINGS:
        if key in settings:
            material[key] = settings[key]
    return _sha256_hex(_canonical_json(material))


def _runtime_spec(
    settings: dict[str, Any],
    enabled_skill_ids: Iterable[str],
    lora_adapter_id: str | None,
) -> dict[str, Any]:
    skill_ids = sorted({str(sid) for sid in enabled_skill_ids if str(sid)})
    spec: dict[str, Any] = {
        "settings": {
            key: settings[key] for key in GENERATION_SETTINGS if key in settings
        },
        "enabled_skill_ids": skill_ids,
        "lora_adapter_id": lora_adapter_id,
    }
    return spec


def current_generation_id(
    *,
    settings: dict[str, Any],
    enabled_skill_ids: Iterable[str],
    lora_adapter_id: str | None,
) -> str:
    """Return the SHA-256 hex digest identifying this companion config.

    Restart-stable: identical inputs hash to the same id, so the
    generations table does not churn on every server start. Reverting to
    an older config reuses the same id.
    """

    spec = _runtime_spec(settings, enabled_skill_ids, lora_adapter_id)
    return _sha256_hex(_canonical_json(spec))


def bump_if_needed(
    store: EvalStore,
    *,
    settings: dict[str, Any],
    enabled_skill_ids: Iterable[str],
    lora_adapter_id: str | None,
    notes: str = "",
    now: datetime | None = None,
) -> EvalGeneration:
    """Insert the current generation row if it is new; return it either way.

    Existing rows are left untouched (``upsert_generation`` uses
    ``ON CONFLICT DO NOTHING`` for exactly this reason) so the original
    ``first_seen_at`` and ``notes`` survive repeat calls. Comparison
    surfaces can rely on those values being stable.
    """

    skill_ids = list(enabled_skill_ids)
    gen_id = current_generation_id(
        settings=settings,
        enabled_skill_ids=skill_ids,
        lora_adapter_id=lora_adapter_id,
    )
    existing = store.get_generation(gen_id)
    if existing is not None:
        return existing

    spec = _runtime_spec(settings, skill_ids, lora_adapter_id)
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    gen = EvalGeneration(
        generation_id=gen_id,
        first_seen_at=timestamp,
        runtime_spec_json=_canonical_json(spec),
        lora_adapter_id=lora_adapter_id,
        skill_set_hash=_hash_skill_set(skill_ids),
        settings_hash=_hash_settings(settings),
        notes=str(notes or ""),
    )
    store.upsert_generation(gen)
    return store.get_generation(gen_id) or gen
