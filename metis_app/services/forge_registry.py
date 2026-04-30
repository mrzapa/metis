"""Typed registry for the M14 Forge gallery (ADR 0014, Phase 2a).

Each Forge technique is a :class:`TechniqueDescriptor` — a frozen
dataclass that names the technique, the settings keys that gate it,
and an ``enabled_predicate`` that reads the live settings dict and
returns whether the capability is currently active.

The registry is a **module-level static tuple**. Adding a technique
means appending one descriptor to ``_REGISTRY``. ADR 0014 explicitly
rejects dynamic plugin loading and synthesising entries from
``default_settings.json`` keys — every descriptor earns its slot
through hand-curated copy (one honest sentence, the right pillar,
the right pre-flight check) and a hand-written predicate.

The route layer (``metis_app/api_litestar/routes/forge.py``) calls
``settings_store.load_settings()`` once per request and passes the
result to each descriptor's ``is_enabled`` to compute the gallery
state. There is no caching here — settings reads are cheap and the
endpoint is not hot.

Slug stability is part of the URL surface
(``/forge#<technique-id>``). Renames need a redirect or deprecation
pass the same way ``default_settings.json`` key renames do; reviewers
should treat changes to ``id`` fields the same way.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

Settings = dict[str, Any]
ForgePillar = Literal["cosmos", "companion", "cortex", "cross-cutting"]

# Mirror of ``HereticService``'s default output root. The service
# itself falls back to this when ``heretic_output_dir`` is empty
# (`metis_app/services/heretic_service.py:309`). Resolving via
# ``Path.home()`` at import time gives an absolute, user-home-based
# path that survives packaged/desktop runs where the process CWD is
# not necessarily writable. ``HERETIC_DEFAULT_OUTPUT_DIR_ALIGNS_WITH_SERVICE``
# (the test in ``tests/test_api_forge.py``) trips if this drifts.
HERETIC_DEFAULT_OUTPUT_DIR = str(pathlib.Path.home() / ".metis_heretic")


RuntimeStatus = Literal["ready", "blocked"]


@dataclass(frozen=True)
class RuntimeReadiness:
    """Phase 3b — per-technique pre-flight readiness report.

    ``status`` summarises whether the technique can be flipped right
    now; ``blockers`` lists the human-readable reasons it cannot. A
    descriptor without prerequisites returns ``status="ready"`` and
    an empty blocker list (the default produced by
    :func:`_always_ready`). ``cta`` carries an optional UI hint for
    the gallery's "Get ready" affordance — the frontend uses
    ``cta_kind`` to pick a render branch (e.g. open an install
    dialog vs. deep-link into another route) and ``cta_target`` to
    parameterise it.
    """

    status: RuntimeStatus = "ready"
    blockers: tuple[str, ...] = ()
    cta_kind: Literal["install_heretic", "switch_chat_path", None] = None
    cta_target: str | None = None


def _always_ready(_settings: Settings) -> RuntimeReadiness:
    return RuntimeReadiness()


@dataclass(frozen=True)
class TechniqueDescriptor:
    """One row of the Forge gallery. ADR 0014 is the spec."""

    id: str
    name: str
    description: str
    pillar: ForgePillar
    setting_keys: tuple[str, ...]
    enabled_predicate: Callable[[Settings], bool]
    engine_symbols: tuple[str, ...] = ()
    docs_url: str | None = None
    # Phase 3 — when both ``enable_overrides`` and
    # ``disable_overrides`` are set, the gallery card renders an
    # interactive toggle. Flipping it ``POST``s the relevant payload
    # to ``/v1/settings`` (the existing settings endpoint), and the
    # next ``GET /v1/forge/techniques`` reflects the new state via
    # the descriptor's own ``enabled_predicate``.
    #
    # ``None`` marks a technique as informational-only — typically
    # because flipping it would either need a global state change
    # (TimesFM rewires ``chat_path``) or a runtime pre-flight check
    # whose CTA isn't a simple toggle. Phase 3b adds a parallel
    # ``runtime_probe`` for the case where the prereq is just
    # missing-but-installable (Heretic CLI on PATH).
    enable_overrides: dict[str, Any] | None = None
    disable_overrides: dict[str, Any] | None = None
    # Phase 3b — runtime readiness probe. Returns a
    # :class:`RuntimeReadiness` describing whether the technique can
    # be flipped right now. The default (``_always_ready``) reports
    # ``status="ready"`` with no blockers, which is correct for the
    # eleven Phase 3a-toggleable techniques. Heretic and TimesFM
    # ship dedicated probes that surface the missing CLI / chat-mode
    # context to the frontend's "Get ready" CTA.
    runtime_probe: Callable[[Settings], RuntimeReadiness] = field(default=_always_ready)
    # Phase 6 — trace markers. The set of TraceEvent ``event_type``
    # strings the engine emits when this technique fires. The Forge
    # gallery uses this in two places:
    #
    # * the card-face "Used X times this week" counter (single pass
    #   over ``runs.jsonl`` filtered by membership in this set), and
    # * the per-card detail endpoint
    #   (``/v1/forge/techniques/<id>/recent-uses``) which projects the
    #   matching events into a mini-timeline.
    #
    # An empty tuple is allowed and means "no trace integration wired
    # yet" — the card renders an empty state instead of a counter.
    trace_event_types: tuple[str, ...] = ()

    def is_enabled(self, settings: Settings) -> bool:
        """Resolve the live enabled state for this technique.

        Predicates are expected to be cheap and side-effect-free.
        Exceptions are swallowed and reported as ``False`` so a single
        misbehaving predicate cannot take down the whole gallery
        endpoint.
        """
        try:
            return bool(self.enabled_predicate(settings))
        except Exception:
            return False

    def readiness(self, settings: Settings) -> RuntimeReadiness:
        """Resolve the live readiness state for this technique.

        Same defensive posture as ``is_enabled``: any exception in
        the probe collapses to ``status="blocked"`` with an
        ``"unknown error"`` blocker, so a flaky probe (e.g. a future
        ``subprocess`` call) can't take down the gallery endpoint.
        """
        try:
            return self.runtime_probe(settings)
        except Exception as exc:
            return RuntimeReadiness(
                status="blocked",
                blockers=(f"runtime probe failed: {exc!s}",),
            )

    @property
    def toggleable(self) -> bool:
        """True iff the gallery should render an interactive toggle.

        Requires both override payloads. Independent from runtime
        readiness — a toggleable+blocked technique still surfaces
        the switch, just disabled, so the user sees what's available
        once the blocker clears.
        """
        return self.enable_overrides is not None and self.disable_overrides is not None


# ── Predicate helpers ──────────────────────────────────────────────
#
# Most techniques key off a single boolean setting. Higher-arity
# checks (string equality, scalar comparison, environment lookups)
# get their own named function so the registry stays readable.


def _bool_key(key: str, default: bool = False) -> Callable[[Settings], bool]:
    """Return a predicate that reads ``key`` and coerces to bool."""
    return lambda settings: bool(settings.get(key, default))


def _hybrid_search_enabled(settings: Settings) -> bool:
    """``hybrid_alpha`` is 1.0 for pure vector, 0.0 for pure BM25.

    Anything strictly less than 1.0 is a real blend, so the technique
    counts as "on" — that mirrors how the engine treats the value in
    ``hybrid_scorer.py``.
    """
    try:
        return float(settings.get("hybrid_alpha", 1.0)) < 1.0
    except (TypeError, ValueError):
        return False


def _mmr_enabled(settings: Settings) -> bool:
    return settings.get("retrieval_mode") == "mmr"


def _swarm_enabled(settings: Settings) -> bool:
    """Swarm runs whenever there is at least one persona configured.

    The 0-personas case is the natural off-switch even though there is
    no dedicated boolean key for it.
    """
    try:
        return int(settings.get("swarm_n_personas") or 0) > 0
    except (TypeError, ValueError):
        return False


def _forecast_enabled(settings: Settings) -> bool:
    """Forecast mode is reachable only via the Forecast chat path."""
    return settings.get("chat_path") == "Forecast"


def _heretic_enabled(settings: Settings) -> bool:
    """Heretic needs both the output dir configured *and* the CLI on
    ``$PATH``. The CLI check is lazy-imported so the registry stays
    free of ``heretic_service`` import-time cost.
    """
    if not settings.get("heretic_output_dir"):
        return False
    try:
        from metis_app.services.heretic_service import is_heretic_available

        return bool(is_heretic_available())
    except Exception:
        return False


# ── Runtime readiness probes (Phase 3b) ───────────────────────────


def _heretic_readiness(settings: Settings) -> RuntimeReadiness:
    """Block Heretic when the CLI is missing on ``$PATH``.

    Lazy-import the service module so the registry doesn't pay the
    ``heretic_service`` import cost on every gallery fetch when
    Heretic isn't even configured.
    """
    try:
        from metis_app.services.heretic_service import is_heretic_available
    except Exception as exc:
        return RuntimeReadiness(
            status="blocked",
            blockers=(f"could not import heretic_service: {exc!s}",),
            cta_kind="install_heretic",
        )
    if not is_heretic_available():
        return RuntimeReadiness(
            status="blocked",
            blockers=("Heretic CLI is not on $PATH",),
            cta_kind="install_heretic",
        )
    if not settings.get("heretic_output_dir"):
        # CLI is there but no output dir is configured — toggling on
        # will set a default, so this is "ready" rather than blocked.
        # Reported as an empty-blockers ready state.
        return RuntimeReadiness(status="ready")
    return RuntimeReadiness(status="ready")


def _timesfm_readiness(_settings: Settings) -> RuntimeReadiness:
    """TimesFM is informational-only in the Forge.

    Activating Forecast mode rewires the global ``chat_path`` setting,
    which would silently change every chat session — too invasive for
    a gallery-side toggle. The blocker reports the actual activation
    path (the chat-mode picker) and surfaces a deep-link CTA.
    """
    return RuntimeReadiness(
        status="blocked",
        blockers=(
            "Forecast mode is activated by switching the chat to "
            "Forecast (it rewires the chat path globally).",
        ),
        cta_kind="switch_chat_path",
        cta_target="/chat",
    )


def _semantic_chunking_enabled(settings: Settings) -> bool:
    return (
        settings.get("chunk_strategy") == "semantic"
        or bool(settings.get("structure_aware_ingestion"))
        or bool(settings.get("semantic_layout_ingestion"))
    )


# ── Registry ───────────────────────────────────────────────────────
#
# The order here is the order the gallery renders today. It mirrors
# the harvest inventory in ``plans/the-forge/plan.md`` — Cortex
# techniques first (the retrieval/synthesis stack a typical query
# walks through), then Companion techniques (the brain-pass /
# news-comet / hebbian growth surface).

_REGISTRY: tuple[TechniqueDescriptor, ...] = (
    TechniqueDescriptor(
        id="iterrag-convergence",
        name="IterRAG convergence",
        description=(
            "Agentic retrieval loop that re-queries until the "
            "answer stabilises against a convergence threshold."
        ),
        pillar="cortex",
        setting_keys=(
            "agentic_mode",
            "agentic_max_iterations",
            "agentic_convergence_threshold",
            "agentic_iteration_budget",
            "agentic_context_compress_enabled",
        ),
        enabled_predicate=_bool_key("agentic_mode"),
        engine_symbols=(
            "metis_app.engine.querying",
            "metis_app.engine.streaming",
        ),
        enable_overrides={"agentic_mode": True},
        disable_overrides={"agentic_mode": False},
        # The agentic loop emits these on each iteration (see
        # ``stream_events._STATUS_BY_EVENT_TYPE`` for the canonical
        # list). ``iteration_complete`` and ``iteration_converged``
        # are the most informative for the card-face counter — one per
        # actual converged answer rather than one per micro-step.
        trace_event_types=(
            "iteration_start",
            "iteration_complete",
            "iteration_converged",
            "gaps_identified",
            "refinement_retrieval",
        ),
    ),
    TechniqueDescriptor(
        id="sub-query-expansion",
        name="Sub-query expansion",
        description=(
            "Decomposes a question into smaller sub-queries before "
            "retrieval, then merges the evidence."
        ),
        pillar="cortex",
        setting_keys=("use_sub_queries", "subquery_max_docs"),
        enabled_predicate=_bool_key("use_sub_queries", default=True),
        engine_symbols=("metis_app.services.retrieval_pipeline",),
        enable_overrides={"use_sub_queries": True},
        disable_overrides={"use_sub_queries": False},
        trace_event_types=("subqueries",),
    ),
    TechniqueDescriptor(
        id="hybrid-search",
        name="Hybrid search (BM25 + vector)",
        description=(
            "Blends lexical BM25 with vector similarity on every "
            "retrieval; ``hybrid_alpha`` controls the mix."
        ),
        pillar="cortex",
        setting_keys=("hybrid_alpha",),
        enabled_predicate=_hybrid_search_enabled,
        engine_symbols=(
            "metis_app.services.hybrid_scorer",
            "metis_app.services.vector_store",
        ),
        # Enable lands on a 50/50 BM25 + vector blend; disable goes
        # back to pure vector (1.0). Power users still tweak the alpha
        # via /settings; the toggle just picks a sensible default.
        enable_overrides={"hybrid_alpha": 0.5},
        disable_overrides={"hybrid_alpha": 1.0},
    ),
    TechniqueDescriptor(
        id="mmr-diversification",
        name="MMR diversification",
        description=(
            "Re-ranks retrieved passages to balance relevance against "
            "redundancy; lifts answer breadth on multi-document questions."
        ),
        pillar="cortex",
        setting_keys=("mmr_lambda", "retrieval_mode"),
        enabled_predicate=_mmr_enabled,
        engine_symbols=("metis_app.services.retrieval_pipeline",),
        enable_overrides={"retrieval_mode": "mmr"},
        disable_overrides={"retrieval_mode": "flat"},
    ),
    TechniqueDescriptor(
        id="reranker",
        name="Reranker",
        description=(
            "Applies a cross-encoder pass over retrieved passages "
            "before they hit the LLM."
        ),
        pillar="cortex",
        setting_keys=("use_reranker",),
        enabled_predicate=_bool_key("use_reranker", default=True),
        engine_symbols=("metis_app.services.reranker",),
        enable_overrides={"use_reranker": True},
        disable_overrides={"use_reranker": False},
    ),
    TechniqueDescriptor(
        id="swarm-personas",
        name="Swarm persona simulation",
        description=(
            "Runs the question past multiple synthetic personas in "
            "parallel rounds, then synthesises a majority view."
        ),
        pillar="cortex",
        setting_keys=("swarm_n_personas", "swarm_n_rounds"),
        enabled_predicate=_swarm_enabled,
        engine_symbols=("metis_app.services.swarm_service",),
        # Enable restores the default-settings persona count (8); the
        # 0-personas state is the natural disable knob.
        enable_overrides={"swarm_n_personas": 8},
        disable_overrides={"swarm_n_personas": 0},
        # Both the simulation_*  and swarm_* event families are
        # included — the codebase uses them somewhat interchangeably
        # (``stream_events`` maps both to the simulation lifecycle).
        # ``swarm_complete`` is the natural "one per finished
        # simulation" counter event.
        trace_event_types=(
            "swarm_start",
            "swarm_round_start",
            "swarm_persona_vote",
            "swarm_round_end",
            "swarm_synthesis",
            "swarm_complete",
            "persona_created",
            "simulation_round_start",
            "simulation_round",
            "simulation_complete",
            "topics_extracted",
            "belief_shift",
        ),
    ),
    TechniqueDescriptor(
        id="timesfm-forecasting",
        name="TimesFM forecasting",
        description=(
            "Time-series forecasting with Google's TimesFM, optionally "
            "blended with classical xreg baselines."
        ),
        pillar="cortex",
        setting_keys=(
            "forecast_model_id",
            "forecast_max_context",
            "forecast_max_horizon",
            "forecast_use_quantiles",
            "forecast_xreg_mode",
        ),
        enabled_predicate=_forecast_enabled,
        engine_symbols=(
            "metis_app.services.forecast_service",
            "metis_app.engine.forecasting",
        ),
        # No overrides — Forecast is activated by switching the chat
        # mode, not by flipping a setting. The runtime probe surfaces
        # this contextually so the card shows a "Open chat to switch
        # to Forecast" CTA instead of a dead lock badge.
        runtime_probe=_timesfm_readiness,
    ),
    TechniqueDescriptor(
        id="tribev2-multimodal",
        name="Tribev2 multimodal extraction",
        description=(
            "Faculty-aware classifier that routes audio, video, and "
            "image content into the brain graph during indexing."
        ),
        pillar="companion",
        setting_keys=(
            "enable_brain_pass",
            "brain_pass_native_enabled",
            "brain_pass_native_text_enabled",
            "brain_pass_model_id",
        ),
        enabled_predicate=_bool_key("enable_brain_pass", default=True),
        engine_symbols=("metis_app.services.brain_pass",),
        enable_overrides={"enable_brain_pass": True},
        disable_overrides={"enable_brain_pass": False},
    ),
    TechniqueDescriptor(
        id="heretic-abliteration",
        name="Heretic abliteration",
        description=(
            "CLI-driven abliteration pass that removes refusal "
            "behaviour from open-weight models. External CLI required."
        ),
        pillar="cortex",
        setting_keys=("heretic_output_dir",),
        enabled_predicate=_heretic_enabled,
        engine_symbols=(
            "metis_app.services.heretic_service",
            "metis_app.api_litestar.routes.heretic",
        ),
        # Phase 3b — toggleable when the CLI is on $PATH. Enable
        # writes the user-home-based default output dir
        # (``HERETIC_DEFAULT_OUTPUT_DIR``) so packaged/desktop runs
        # don't fail mid-flight when the process CWD isn't writable;
        # disable clears the setting so ``_heretic_enabled`` reads
        # False again. The card disables the switch when
        # ``runtime_probe`` reports blocked.
        enable_overrides={"heretic_output_dir": HERETIC_DEFAULT_OUTPUT_DIR},
        disable_overrides={"heretic_output_dir": ""},
        runtime_probe=_heretic_readiness,
    ),
    TechniqueDescriptor(
        id="news-comets",
        name="News-comet ingestion",
        description=(
            "Continuous RSS and subreddit polling that turns fresh "
            "items into comets the companion can absorb on its own."
        ),
        pillar="companion",
        setting_keys=(
            "news_comets_enabled",
            "news_comet_sources",
            "news_comet_poll_interval_seconds",
            "news_comet_max_active",
            "news_comet_auto_absorb_threshold",
            "news_comet_rss_feeds",
            "news_comet_reddit_subs",
        ),
        enabled_predicate=_bool_key("news_comets_enabled"),
        engine_symbols=(
            "metis_app.services.news_ingest_service",
            "metis_app.services.comet_decision_engine",
        ),
        enable_overrides={"news_comets_enabled": True},
        disable_overrides={"news_comets_enabled": False},
    ),
    TechniqueDescriptor(
        id="hebbian-edges",
        name="Hebbian edge updates",
        description=(
            "Strengthens brain-graph edges when concepts co-occur in "
            "queries; decays unused links over time."
        ),
        pillar="companion",
        setting_keys=("enable_hebbian", "hebbian_boost", "hebbian_decay"),
        enabled_predicate=_bool_key("enable_hebbian", default=True),
        engine_symbols=("metis_app.utils.hebbian_decoder",),
        enable_overrides={"enable_hebbian": True},
        disable_overrides={"enable_hebbian": False},
    ),
    TechniqueDescriptor(
        id="citation-v2",
        name="Citation v2 / claim-level grounding",
        description=(
            "Per-claim citation pass that anchors every assertion in "
            "the answer to a specific source span."
        ),
        pillar="cortex",
        setting_keys=(
            "enable_citation_v2",
            "enable_claim_level_grounding_citefix_lite",
        ),
        enabled_predicate=_bool_key("enable_citation_v2", default=True),
        engine_symbols=("metis_app.services.response_pipeline",),
        enable_overrides={"enable_citation_v2": True},
        disable_overrides={"enable_citation_v2": False},
        # ``claim_grounding`` fires once per validated answer when the
        # citation v2 pass is on (``app_controller.py:2003``). It's
        # the cleanest signal that the technique earned its keep on
        # this run.
        trace_event_types=("claim_grounding",),
    ),
    TechniqueDescriptor(
        id="semantic-chunking",
        name="Semantic chunking",
        description=(
            "Layout- and structure-aware ingestion that respects "
            "section boundaries instead of fixed character windows."
        ),
        pillar="cortex",
        setting_keys=(
            "structure_aware_ingestion",
            "semantic_layout_ingestion",
            "chunk_strategy",
        ),
        enabled_predicate=_semantic_chunking_enabled,
        engine_symbols=("metis_app.services.semantic_chunker",),
        enable_overrides={"chunk_strategy": "semantic"},
        # ``_semantic_chunking_enabled`` ORs three keys, so the disable
        # path must clear every one of them. If a previous user state
        # (or another surface — `/settings`) had flipped
        # ``structure_aware_ingestion`` or ``semantic_layout_ingestion``
        # on, leaving them untouched here would leave the technique
        # reading as ENABLED despite the toggle showing OFF.
        disable_overrides={
            "chunk_strategy": "fixed",
            "structure_aware_ingestion": False,
            "semantic_layout_ingestion": False,
        },
    ),
)


def get_registry() -> tuple[TechniqueDescriptor, ...]:
    """Return the curated list of Forge technique descriptors."""
    return _REGISTRY


def get_descriptor(slug: str) -> TechniqueDescriptor | None:
    """Resolve a descriptor by its stable slug, or ``None``."""
    for descriptor in _REGISTRY:
        if descriptor.id == slug:
            return descriptor
    return None


def find_missing_setting_keys(settings: Settings) -> dict[str, tuple[str, ...]]:
    """Return any descriptor IDs whose ``setting_keys`` are absent
    from *settings*. Used by the test suite to mechanically guard
    the hand-curated registry against ``default_settings.json``
    drift; an empty mapping means every key resolves.
    """
    missing: dict[str, tuple[str, ...]] = {}
    for descriptor in _REGISTRY:
        gaps = tuple(key for key in descriptor.setting_keys if key not in settings)
        if gaps:
            missing[descriptor.id] = gaps
    return missing
