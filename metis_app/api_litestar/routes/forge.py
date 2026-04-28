"""Forge gallery endpoints (M14 Phase 1).

The Forge is a thin UI surface over already-shipped engine techniques.
Phase 1 returns a static, hard-coded inventory of those techniques so
the frontend can render the gallery shell. Phase 2 will introduce the
typed registry (``metis_app/services/forge_registry.py``) that computes
each technique's ``enabled`` state from the live settings store and
exposes ``setting_keys`` for the toggle wiring.

ADR 0014 (`docs/adr/0014-forge-route-and-toggle-state.md`) is the
architectural baseline this route is built against. Slug stability,
the ``setting_keys`` shape, and the pillar enum are all fixed there.

Shipping the static list before the registry keeps Phase 1 small and
unblocks the frontend shell PR; later phases extend this route in
place rather than replacing it.
"""

from __future__ import annotations

from typing import Any

from litestar import Router, get


# ── Technique inventory ──────────────────────────────────────────────
#
# Each entry mirrors a row from the harvest inventory in
# ``plans/the-forge/plan.md``. The ``default_enabled`` field reflects
# the value in ``metis_app/default_settings.json`` at the time of
# writing; Phase 2 replaces it with a live read against the settings
# store so user overrides surface in the gallery.
#
# Slugs are stable identifiers — the frontend uses them as URL
# anchors (``/forge#<id>``) and the constellation will key Skills-sector
# stars by them in Phase 2. Renames need a redirect or deprecation pass
# the same way ``default_settings.json`` key renames do.

_TECHNIQUE_INVENTORY: tuple[dict[str, Any], ...] = (
    {
        "id": "iterrag-convergence",
        "name": "IterRAG convergence",
        "description": (
            "Agentic retrieval loop that re-queries until the "
            "answer stabilises against a convergence threshold."
        ),
        "pillar": "cortex",
        "default_enabled": False,
        "setting_keys": (
            "agentic_mode",
            "agentic_max_iterations",
            "agentic_convergence_threshold",
            "agentic_iteration_budget",
            "agentic_context_compress_enabled",
        ),
        "engine_symbols": (
            "metis_app.engine.querying",
            "metis_app.engine.streaming",
        ),
    },
    {
        "id": "sub-query-expansion",
        "name": "Sub-query expansion",
        "description": (
            "Decomposes a question into smaller sub-queries before "
            "retrieval, then merges the evidence."
        ),
        "pillar": "cortex",
        "default_enabled": True,
        "setting_keys": ("use_sub_queries", "subquery_max_docs"),
        "engine_symbols": ("metis_app.services.retrieval_pipeline",),
    },
    {
        "id": "hybrid-search",
        "name": "Hybrid search (BM25 + vector)",
        "description": (
            "Blends lexical BM25 with vector similarity on every "
            "retrieval; ``hybrid_alpha`` controls the mix."
        ),
        "pillar": "cortex",
        "default_enabled": True,
        "setting_keys": ("hybrid_alpha",),
        "engine_symbols": (
            "metis_app.services.hybrid_scorer",
            "metis_app.services.vector_store",
        ),
    },
    {
        "id": "mmr-diversification",
        "name": "MMR diversification",
        "description": (
            "Re-ranks retrieved passages to balance relevance against "
            "redundancy; lifts answer breadth on multi-document questions."
        ),
        "pillar": "cortex",
        "default_enabled": False,
        "setting_keys": ("mmr_lambda", "retrieval_mode"),
        "engine_symbols": ("metis_app.services.retrieval_pipeline",),
    },
    {
        "id": "reranker",
        "name": "Reranker",
        "description": (
            "Applies a cross-encoder pass over retrieved passages "
            "before they hit the LLM."
        ),
        "pillar": "cortex",
        "default_enabled": True,
        "setting_keys": ("use_reranker",),
        "engine_symbols": ("metis_app.services.reranker",),
    },
    {
        "id": "swarm-personas",
        "name": "Swarm persona simulation",
        "description": (
            "Runs the question past multiple synthetic personas in "
            "parallel rounds, then synthesises a majority view."
        ),
        "pillar": "cortex",
        "default_enabled": False,
        "setting_keys": ("swarm_n_personas", "swarm_n_rounds"),
        "engine_symbols": ("metis_app.services.swarm_service",),
    },
    {
        "id": "timesfm-forecasting",
        "name": "TimesFM forecasting",
        "description": (
            "Time-series forecasting with Google's TimesFM, optionally "
            "blended with classical xreg baselines."
        ),
        "pillar": "cortex",
        "default_enabled": False,
        "setting_keys": (
            "forecast_model_id",
            "forecast_max_context",
            "forecast_max_horizon",
            "forecast_use_quantiles",
            "forecast_xreg_mode",
        ),
        "engine_symbols": (
            "metis_app.services.forecast_service",
            "metis_app.engine.forecasting",
        ),
    },
    {
        "id": "tribev2-multimodal",
        "name": "Tribev2 multimodal extraction",
        "description": (
            "Faculty-aware classifier that routes audio, video, and "
            "image content into the brain graph during indexing."
        ),
        "pillar": "companion",
        "default_enabled": True,
        "setting_keys": (
            "enable_brain_pass",
            "brain_pass_native_enabled",
            "brain_pass_native_text_enabled",
            "brain_pass_model_id",
        ),
        "engine_symbols": ("metis_app.services.brain_pass",),
    },
    {
        "id": "heretic-abliteration",
        "name": "Heretic abliteration",
        "description": (
            "CLI-driven abliteration pass that removes refusal "
            "behaviour from open-weight models. External CLI required."
        ),
        "pillar": "cortex",
        "default_enabled": False,
        "setting_keys": ("heretic_output_dir",),
        "engine_symbols": (
            "metis_app.services.heretic_service",
            "metis_app.api_litestar.routes.heretic",
        ),
    },
    {
        "id": "news-comets",
        "name": "News-comet ingestion",
        "description": (
            "Continuous RSS and subreddit polling that turns fresh "
            "items into comets the companion can absorb on its own."
        ),
        "pillar": "companion",
        "default_enabled": False,
        "setting_keys": (
            "news_comets_enabled",
            "news_comet_sources",
            "news_comet_poll_interval_seconds",
            "news_comet_max_active",
            "news_comet_auto_absorb_threshold",
            "news_comet_rss_feeds",
            "news_comet_reddit_subs",
        ),
        "engine_symbols": (
            "metis_app.services.news_ingest_service",
            "metis_app.services.comet_decision_engine",
        ),
    },
    {
        "id": "hebbian-edges",
        "name": "Hebbian edge updates",
        "description": (
            "Strengthens brain-graph edges when concepts co-occur in "
            "queries; decays unused links over time."
        ),
        "pillar": "companion",
        "default_enabled": True,
        "setting_keys": ("enable_hebbian", "hebbian_boost", "hebbian_decay"),
        "engine_symbols": ("metis_app.utils.hebbian_decoder",),
    },
    {
        "id": "citation-v2",
        "name": "Citation v2 / claim-level grounding",
        "description": (
            "Per-claim citation pass that anchors every assertion in "
            "the answer to a specific source span."
        ),
        "pillar": "cortex",
        "default_enabled": True,
        "setting_keys": (
            "enable_citation_v2",
            "enable_claim_level_grounding_citefix_lite",
        ),
        "engine_symbols": ("metis_app.services.response_pipeline",),
    },
    {
        "id": "semantic-chunking",
        "name": "Semantic chunking",
        "description": (
            "Layout- and structure-aware ingestion that respects "
            "section boundaries instead of fixed character windows."
        ),
        "pillar": "cortex",
        "default_enabled": False,
        "setting_keys": (
            "structure_aware_ingestion",
            "semantic_layout_ingestion",
            "chunk_strategy",
        ),
        "engine_symbols": ("metis_app.services.semantic_chunker",),
    },
)


def _serialise(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry["id"],
        "name": entry["name"],
        "description": entry["description"],
        "pillar": entry["pillar"],
        "enabled": entry["default_enabled"],
        "setting_keys": list(entry["setting_keys"]),
        "engine_symbols": list(entry["engine_symbols"]),
        "recent_uses": [],
    }


@get("/v1/forge/techniques", sync_to_thread=False)
def list_techniques() -> dict[str, Any]:
    """Return the static technique inventory (Phase 1)."""
    return {
        "techniques": [_serialise(entry) for entry in _TECHNIQUE_INVENTORY],
        "phase": 1,
    }


router = Router(
    path="",
    route_handlers=[list_techniques],
    tags=["forge"],
)
