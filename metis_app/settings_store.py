"""Non-UI helper for loading and saving METIS settings JSON files.

This module intentionally avoids importing Qt or any UI toolkit so that
it can be used safely from the API layer and other non-GUI contexts.

The merge priority is:
  defaults (metis_app/default_settings.json)
  → user    (settings.json in repo root)

Schema versioning:
  - Settings have an integer schema_version field
  - On load, migrations are applied if schema_version differs from current
  - Migrations are run sequentially from old version to new
  - See _run_migrations() for available migration functions

Concurrency notes:
  - Atomic writes are used to prevent corruption from interrupted saves.
  - Multiple processes reading/writing settings.json simultaneously is supported
    at the file level (WAL would help but is not used here - settings are
    simple enough that the atomic write pattern is sufficient).
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import tempfile
from typing import Annotated, Any, Callable

from pydantic import BaseModel, BeforeValidator, ConfigDict, ValidationError

HERE = pathlib.Path(__file__).resolve().parent  # metis_app/
REPO_ROOT = HERE.parent  # <repo root>

DEFAULT_PATH = HERE / "default_settings.json"
USER_PATH = REPO_ROOT / "settings.json"

API_KEY_PREFIX = "api_key_"

SCHEMA_VERSION = 1

log = logging.getLogger(__name__)


def _migrate_v1_to_current(settings: dict[str, Any]) -> dict[str, Any]:
    """Migration from schema_version 1 to current. Currently a no-op."""
    return settings


_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    1: _migrate_v1_to_current,
}


def _run_migrations(settings: dict[str, Any]) -> dict[str, Any]:
    """Run any pending migrations from settings schema_version to current."""
    current_schema = settings.get("schema_version", 0)

    if current_schema == SCHEMA_VERSION:
        return settings

    if current_schema > SCHEMA_VERSION:
        log.warning(
            "Settings schema version (%s) is newer than app supports (%s). "
            "Some settings may be ignored.",
            current_schema,
            SCHEMA_VERSION,
        )
        return settings

    for version in range(current_schema + 1, SCHEMA_VERSION + 1):
        migration_fn = _MIGRATIONS.get(version)
        if migration_fn:
            log.info("Running settings migration from v%d to v%d", version - 1, version)
            settings = migration_fn(settings)
            settings["schema_version"] = version

    return settings


def resolve_secret_refs(settings: dict[str, Any]) -> dict[str, Any]:
    """Replace ``'env:VAR_NAME'`` string values with the corresponding
    environment variable, leaving all other values untouched.

    This lets users store sensitive keys (API tokens, etc.) as
    ``"env:OPENAI_API_KEY"`` in *settings.json* rather than as plain text.
    If the referenced variable is not set the original ``'env:...'`` string
    is retained so that the caller can detect an unresolved reference.
    """
    resolved: dict[str, Any] = {}
    for key, value in settings.items():
        if isinstance(value, str) and value.startswith("env:"):
            var_name = value[4:].strip()
            env_value = os.environ.get(var_name)
            resolved[key] = env_value if env_value is not None else value
        else:
            resolved[key] = value
    return resolved


# ---------------------------------------------------------------------------
# Settings schema — Pydantic v2 validation layer
# ---------------------------------------------------------------------------

def _unresolved_env_to_none(v: Any) -> Any:
    """Return None for unresolved 'env:VAR' strings; pass everything else through."""
    if isinstance(v, str) and v.startswith("env:"):
        return None
    return v


_EnvPassthrough = Annotated[Any, BeforeValidator(_unresolved_env_to_none)]


class AssistantIdentitySettings(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = "METIS"
    persona: str = ""
    response_style: str = ""
    assistant_id: str = "metis-companion"
    archetype: str = ""
    companion_enabled: bool = True
    greeting: str = ""
    prompt_seed: str = ""
    docked: bool = True
    minimized: bool = False


class AssistantRuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="allow")
    max_context_chars: _EnvPassthrough = 0
    context_window: _EnvPassthrough = 0
    context_window_override: _EnvPassthrough = 0
    provider: str = ""
    model: str = ""
    local_gguf_model_path: str = ""
    local_gguf_context_length: _EnvPassthrough = 2048
    local_gguf_gpu_layers: _EnvPassthrough = 0
    local_gguf_threads: _EnvPassthrough = 0
    fallback_to_primary: bool = True
    auto_bootstrap: bool = True
    auto_install: bool = False
    bootstrap_state: str = "pending"
    recommended_model_name: str = ""
    recommended_quant: str = ""
    recommended_use_case: str = "chat"


class AssistantPolicySettings(BaseModel):
    model_config = ConfigDict(extra="allow")
    safety_filter: bool = False
    allow_web_search: bool = False
    reflection_enabled: bool = True
    reflection_backend: str = "hybrid"
    reflection_cooldown_seconds: _EnvPassthrough = 180
    max_memory_entries: _EnvPassthrough = 200
    max_playbooks: _EnvPassthrough = 64
    max_brain_links: _EnvPassthrough = 400
    trigger_on_onboarding: bool = True
    trigger_on_index_build: bool = True
    trigger_on_completed_run: bool = True
    allow_automatic_writes: bool = True
    autonomous_research_enabled: bool = False
    autonomous_research_provider: str = "tavily"
    autonomous_research_concurrency: _EnvPassthrough = 1
    autonomous_research_request_delay_ms: _EnvPassthrough = 500


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # ── Schema ────────────────────────────────────────────────────────────────
    schema_version: _EnvPassthrough = 1

    # ── UI / App ──────────────────────────────────────────────────────────────
    ui_backend: str = "tauri"
    theme: str = "space_dust"
    startup_mode_setting: str = "basic"
    last_used_mode: str = "basic"
    basic_wizard_completed: bool = False
    verbose_mode: bool = False
    show_retrieved_context: bool = False
    deepread_mode: bool = False
    secure_mode: bool = False
    experimental_override: bool = False
    output_style: str = "Default answer"
    selected_mode: str = "Q&A"
    chat_path: str = "RAG"

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_provider: str = "anthropic"
    llm_model: str = "claude-opus-4-6"
    llm_model_id: str = ""
    llm_model_custom: str = ""
    llm_temperature: _EnvPassthrough = 0.0
    llm_max_tokens: _EnvPassthrough = 1024
    llm_timeout: _EnvPassthrough = 120
    local_llm_url: str = "http://localhost:1234/v1"
    local_gguf_model_path: str = ""
    local_gguf_models_dir: str = ""
    local_gguf_context_length: _EnvPassthrough = 2048
    local_gguf_gpu_layers: _EnvPassthrough = 0
    local_gguf_threads: _EnvPassthrough = 0
    smart_llm_provider: str = ""
    smart_llm_model: str = ""
    smart_llm_temperature: _EnvPassthrough = 0.0
    smart_llm_max_tokens: _EnvPassthrough = 2048
    api_key: str = ""
    credential_pool: dict[str, Any] = {}

    # ── Hardware ──────────────────────────────────────────────────────────────
    hardware_override_enabled: bool = False
    hardware_override_total_ram_gb: _EnvPassthrough = 0
    hardware_override_available_ram_gb: _EnvPassthrough = 0
    hardware_override_gpu_name: str = ""
    hardware_override_gpu_vram_gb: _EnvPassthrough = 0
    hardware_override_gpu_count: _EnvPassthrough = 0
    hardware_override_backend: str = ""
    hardware_override_unified_memory: bool = False

    # ── Embedding ─────────────────────────────────────────────────────────────
    embedding_provider: str = "voyage"
    embedding_model: str = "voyage-4-large"
    embedding_model_id: str = ""
    embedding_model_custom: str = ""
    embedding_dimension: _EnvPassthrough = 0
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embeddings_backend: str = "mock"
    sentence_transformers_model: str = "all-MiniLM-L6-v2"
    local_st_model_name: str = ""
    local_st_cache_dir: str = "~/.cache/sentence_transformers"
    local_st_batch_size: _EnvPassthrough = 32
    force_embedding_compat: bool = False
    index_embedding_signature: str = ""

    # ── Vector DB / Index paths ───────────────────────────────────────────────
    selected_index_path: str = ""
    selected_collection_name: str = ""
    cache_dir: str = ".metis_cache"
    vector_db_type: str = "json"
    weaviate_url: str = ""
    weaviate_api_key: str = ""
    index_dir: str = ""

    # ── API keys ──────────────────────────────────────────────────────────────
    api_key_openai: str = ""
    api_key_anthropic: str = ""
    api_key_google: str = ""
    api_key_xai: str = ""
    api_key_cohere: str = ""
    api_key_mistral: str = ""
    api_key_groq: str = ""
    api_key_azure_openai: str = ""
    api_key_together: str = ""
    api_key_voyage: str = ""
    api_key_huggingface: str = ""
    api_key_fireworks: str = ""
    api_key_perplexity: str = ""
    web_search_api_key: str = ""

    # ── Ports / URLs ──────────────────────────────────────────────────────────
    api_port: _EnvPassthrough = 0
    api_base_url: str = ""
    api_token: str = ""

    # ── Web search ────────────────────────────────────────────────────────────
    web_graph_mode: bool = False
    web_scrape_full_content: bool = False

    # ── Index / Ingestion ─────────────────────────────────────────────────────
    chunk_size: _EnvPassthrough = 1000
    chunk_overlap: _EnvPassthrough = 100
    parent_chunk_size: _EnvPassthrough = 2800
    parent_chunk_overlap: _EnvPassthrough = 320
    chunk_strategy: str = "fixed"
    document_loader: str = "auto"
    structure_aware_ingestion: bool = False
    semantic_layout_ingestion: bool = False
    build_digest_index: bool = True
    build_comprehension_index: bool = False
    build_llm_knowledge_graph: bool = False
    comprehension_extraction_depth: str = "Standard"

    # ── Retrieval ─────────────────────────────────────────────────────────────
    top_k: _EnvPassthrough = 5
    retrieval_token_budget: _EnvPassthrough = 0
    knowledge_search_top_k: _EnvPassthrough = 8
    retrieval_k: _EnvPassthrough = 25
    retrieval_mode: str = "flat"
    retrieval_min_score: _EnvPassthrough = 0.15
    search_type: str = "similarity"
    hybrid_alpha: _EnvPassthrough = 1.0
    mmr_lambda: _EnvPassthrough = 0.5
    use_reranker: bool = True
    use_sub_queries: bool = True
    fallback_strategy: str = "synthesize_anyway"
    fallback_message: str = "I couldn't find enough grounded evidence in the selected index to answer confidently."
    subquery_max_docs: _EnvPassthrough = 200
    chat_history_max_turns: _EnvPassthrough = 6

    # ── Forecast ──────────────────────────────────────────────────────────────
    forecast_model_id: str = "google/timesfm-2.5-200m-pytorch"
    forecast_max_context: _EnvPassthrough = 15360
    forecast_max_horizon: _EnvPassthrough = 1000
    forecast_use_quantiles: bool = True
    forecast_xreg_mode: str = "xreg + timesfm"
    forecast_force_xreg_cpu: bool = True

    # ── Agentic ───────────────────────────────────────────────────────────────
    agentic_mode: bool = False
    agentic_max_iterations: _EnvPassthrough = 2
    swarm_n_personas: _EnvPassthrough = 8
    swarm_n_rounds: _EnvPassthrough = 4
    agentic_iteration_budget: _EnvPassthrough = 4
    agentic_convergence_threshold: _EnvPassthrough = 0.95
    agentic_context_compress_enabled: bool = True
    agentic_context_compress_threshold_chars: _EnvPassthrough = 12000
    system_instructions: str = ""

    # ── Feature flags ─────────────────────────────────────────────────────────
    enable_summarizer: bool = True
    enable_langextract: bool = False
    enable_structured_extraction: bool = False
    enable_brain_pass: bool = True
    brain_pass_native_enabled: bool = True
    brain_pass_native_text_enabled: bool = True
    brain_pass_allow_fallback: bool = True
    brain_pass_model_id: str = "facebook/tribev2"
    brain_pass_cache_dir: str = ".metis_cache/tribev2"
    brain_pass_device: str = "auto"
    enable_arrow_artifacts: bool = False
    enable_arrow_artifact_runtime: bool = True
    enable_recursive_memory: bool = False
    enable_recursive_retrieval: bool = False
    enable_citation_v2: bool = True
    enable_claim_level_grounding_citefix_lite: bool = False
    agent_lightning_enabled: bool = False
    prefer_comprehension_index: bool = True
    enable_mces: bool = False
    mces_roi_window: _EnvPassthrough = 1800
    enable_knowledge_cache: bool = False
    knowledge_cache_ttl_hours: _EnvPassthrough = 24

    # ── Misc ──────────────────────────────────────────────────────────────────
    landing_constellation_user_stars: list[Any] = []
    log_dir: str = "logs"
    log_level: str = "DEBUG"
    kg_query_mode: str = "hybrid"
    heretic_output_dir: str = ""

    # ── News comets ───────────────────────────────────────────────────────────
    news_comets_enabled: bool = False
    news_comet_sources: list[str] = []
    news_comet_poll_interval_seconds: _EnvPassthrough = 300
    news_comet_max_active: _EnvPassthrough = 5
    news_comet_auto_absorb_threshold: _EnvPassthrough = 0.75
    news_comet_rss_feeds: list[str] = []
    news_comet_reddit_subs: list[str] = []

    # ── Nested groups ─────────────────────────────────────────────────────────
    assistant_identity: AssistantIdentitySettings = AssistantIdentitySettings()
    assistant_runtime: AssistantRuntimeSettings = AssistantRuntimeSettings()
    assistant_policy: AssistantPolicySettings = AssistantPolicySettings()
    skills: dict[str, Any] = {}
    local_model_registry: dict[str, Any] = {}


def _validate_and_coerce(settings: dict[str, Any]) -> dict[str, Any]:
    """Validate and coerce *settings* against AppSettings.

    - Unknown keys are silently ignored (extra='ignore').
    - Unresolved "env:VAR" strings in non-str fields are coerced to None
      so the field falls back to its model default.
    - On type errors raises ValueError with a human-readable summary.
    """
    try:
        validated = AppSettings.model_validate(settings)
    except ValidationError as exc:
        lines = [
            f"  \u2022 {'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        ]
        raise ValueError(
            "METIS settings validation failed. Fix the following fields in "
            "settings.json:\n" + "\n".join(lines)
        ) from exc

    # model_dump() only returns AppSettings fields; re-merge extra keys so
    # callers that access unknown keys (e.g. plugin configs) still work.
    coerced = validated.model_dump()
    extra_keys = {k: v for k, v in settings.items() if k not in coerced}
    coerced.update(extra_keys)
    return coerced


def load_settings() -> dict[str, Any]:
    """Return fully-merged settings (defaults → user overrides).

    Keys whose name is ``_comment`` are stripped.  Missing files are silently
    skipped so callers always receive a usable dict.
    """
    defaults: dict[str, Any] = {}
    if DEFAULT_PATH.exists():
        try:
            defaults = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
            defaults.pop("_comment", None)
        except Exception as exc:
            log.warning("Could not read default settings (%s): %s", DEFAULT_PATH, exc)

    user: dict[str, Any] = {}
    if USER_PATH.exists():
        try:
            user = json.loads(USER_PATH.read_text(encoding="utf-8"))
            user.pop("_comment", None)
        except Exception as exc:
            log.warning("Could not read user settings (%s): %s", USER_PATH, exc)

    merged = dict(defaults)
    merged.update(user)
    merged = _run_migrations(merged)
    merged = resolve_secret_refs(merged)
    merged = _validate_and_coerce(merged)
    return merged


def _atomic_write(target: pathlib.Path, content: str) -> None:
    """Write content to target atomically using temp file + rename.

    On POSIX, os.replace() is atomic. On Windows, it's not guaranteed atomic
    but provides better semantics than a direct write. The temp file is written
    in the same directory as the target to ensure same filesystem.
    """
    dir_path = target.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=dir_path,
        prefix=".settings_",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = pathlib.Path(tmp.name)

    try:
        os.replace(tmp_path, target)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def save_settings(updates: dict[str, Any]) -> dict[str, Any]:
    """Merge *updates* into the current settings and persist to settings.json.

    Uses atomic write (temp file + rename) to prevent corruption from
    interrupted saves. Ensures schema_version is set to current.

    Returns the full merged settings dict after saving.

    Raises
    ------
    OSError
        If the file cannot be written (propagated to the caller).
    """
    merged = load_settings()
    merged.update(updates)
    merged.pop("_comment", None)
    merged["schema_version"] = SCHEMA_VERSION
    content = json.dumps(merged, indent=2, ensure_ascii=False)
    _atomic_write(USER_PATH, content)
    log.info("Settings saved to %s (%d key(s))", USER_PATH, len(merged))
    return merged


def safe_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *settings* with all ``api_key_*`` keys removed."""
    return {k: v for k, v in settings.items() if not k.startswith(API_KEY_PREFIX)}
