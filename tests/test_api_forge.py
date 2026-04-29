"""Tests for the M14 Forge gallery routes (Phases 1 + 2a)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from litestar.testing import TestClient

from metis_app.api_litestar import create_app
from metis_app.services.forge_registry import (
    find_missing_setting_keys,
    get_descriptor,
    get_registry,
)


def _client() -> TestClient:
    return TestClient(app=create_app())


def test_list_techniques_returns_registry_inventory() -> None:
    with _client() as client:
        resp = client.get("/v1/forge/techniques")
        assert resp.status_code == 200
        payload = resp.json()

    assert payload["phase"] == 2
    techniques = payload["techniques"]
    assert len(techniques) == len(get_registry())

    ids = {item["id"] for item in techniques}
    # Spot-check the marquee techniques the UI promises in the
    # harvest inventory (plans/the-forge/plan.md).
    for required in (
        "iterrag-convergence",
        "swarm-personas",
        "heretic-abliteration",
        "tribev2-multimodal",
        "timesfm-forecasting",
        "news-comets",
        "reranker",
        "hybrid-search",
        "sub-query-expansion",
    ):
        assert required in ids, f"missing technique: {required}"


def test_list_techniques_response_shape() -> None:
    with _client() as client:
        resp = client.get("/v1/forge/techniques")
        techniques = resp.json()["techniques"]

    required_fields = {
        "id",
        "name",
        "description",
        "pillar",
        "enabled",
        "setting_keys",
        "engine_symbols",
        "recent_uses",
        # Phase 3 additions — every entry exposes its toggle posture
        # and (when toggleable) the settings overrides the frontend
        # writes through ``POST /v1/settings``.
        "toggleable",
        "enable_overrides",
        "disable_overrides",
        # Phase 3b additions — runtime readiness probe output. Every
        # entry reports a ``runtime_status`` (default "ready") plus a
        # blockers list and an optional CTA descriptor for the
        # gallery's "Get ready" affordance.
        "runtime_status",
        "runtime_blockers",
        "runtime_cta_kind",
        "runtime_cta_target",
    }
    for entry in techniques:
        assert required_fields <= entry.keys()
        assert isinstance(entry["id"], str) and entry["id"]
        assert isinstance(entry["name"], str) and entry["name"]
        assert isinstance(entry["description"], str) and entry["description"]
        assert entry["pillar"] in {"cosmos", "companion", "cortex", "cross-cutting"}
        assert isinstance(entry["enabled"], bool)
        assert isinstance(entry["setting_keys"], list)
        assert all(isinstance(key, str) for key in entry["setting_keys"])
        assert isinstance(entry["engine_symbols"], list)
        # Phase 2a still has no live trace integration (that's Phase 6).
        assert entry["recent_uses"] == []
        assert isinstance(entry["toggleable"], bool)
        if entry["toggleable"]:
            assert isinstance(entry["enable_overrides"], dict)
            assert isinstance(entry["disable_overrides"], dict)
            assert entry["enable_overrides"], "toggleable technique must declare enable_overrides"
            assert entry["disable_overrides"], "toggleable technique must declare disable_overrides"
        else:
            assert entry["enable_overrides"] is None
            assert entry["disable_overrides"] is None
        assert entry["runtime_status"] in {"ready", "blocked"}
        assert isinstance(entry["runtime_blockers"], list)
        assert all(isinstance(b, str) for b in entry["runtime_blockers"])
        if entry["runtime_status"] == "ready":
            assert entry["runtime_blockers"] == []
        else:
            assert entry["runtime_blockers"], "blocked status must list at least one blocker"
        if entry["runtime_cta_kind"] is not None:
            assert entry["runtime_cta_kind"] in {"install_heretic", "switch_chat_path"}


def test_toggleable_overrides_reference_real_setting_keys() -> None:
    """Every override key must exist in default_settings.json — same
    invariant as the descriptor's ``setting_keys``, applied to the
    overrides too. Drift here would land the frontend writing a key
    the engine ignores.
    """
    import metis_app.settings_store as settings_store

    settings = settings_store.load_settings()

    with _client() as client:
        techniques = client.get("/v1/forge/techniques").json()["techniques"]

    for entry in techniques:
        if not entry["toggleable"]:
            continue
        for payload_label, payload in (
            ("enable_overrides", entry["enable_overrides"]),
            ("disable_overrides", entry["disable_overrides"]),
        ):
            for key in payload.keys():
                assert key in settings, (
                    f"{entry['id']!r} {payload_label} references missing "
                    f"setting key {key!r}"
                )


def test_overrides_flip_the_descriptor_predicate() -> None:
    """Self-check: applying ``enable_overrides`` to the default
    settings makes ``is_enabled`` return ``True``; applying
    ``disable_overrides`` makes it return ``False``. Without this,
    the frontend toggle could silently land settings the predicate
    interprets the wrong way.
    """
    import metis_app.settings_store as settings_store

    base = dict(settings_store.load_settings())
    # Stub the Heretic CLI check globally for this test so the
    # predicate behaves like CLI-on-PATH. The dedicated probe tests
    # (``test_heretic_probe_*``) cover the missing-CLI branch.
    with patch(
        "metis_app.services.heretic_service.is_heretic_available",
        return_value=True,
    ):
        for descriptor in get_registry():
            if not descriptor.toggleable:
                continue
            on = dict(base)
            on.update(descriptor.enable_overrides or {})
            assert descriptor.is_enabled(on) is True, (
                f"{descriptor.id!r} enable_overrides did not flip the predicate ON"
            )
            off = dict(base)
            off.update(descriptor.disable_overrides or {})
            assert descriptor.is_enabled(off) is False, (
                f"{descriptor.id!r} disable_overrides did not flip the predicate OFF"
            )


def test_disable_overrides_clear_every_predicate_input_for_or_predicates() -> None:
    """Regression test for the semantic-chunking OR-predicate bug
    (Codex P1 review on PR #579): when a predicate ORs multiple
    settings keys, ``disable_overrides`` must zero every one of them.

    The earlier ``test_overrides_flip_the_descriptor_predicate``
    starts from default settings, where the predicate's "companion
    keys" happen to be off, so it would let a partial disable through
    silently. This test seeds a *maximally-on* base — every key the
    descriptor declares in ``setting_keys`` is set to a value that
    would individually satisfy the predicate — and then asserts the
    disable payload still drives ``is_enabled`` to ``False``. Any
    future OR-predicate descriptor that ships a one-knob disable
    will trip here.
    """
    import metis_app.settings_store as settings_store

    truthy_seed = settings_store.load_settings()
    # Same Heretic-CLI stub as the simpler predicate test above —
    # the maximally-on seed includes a heretic_output_dir, but the
    # predicate also requires the CLI on PATH. The dedicated
    # ``test_heretic_probe_*`` cases cover the runtime-only branch.
    with patch(
        "metis_app.services.heretic_service.is_heretic_available",
        return_value=True,
    ):
        for descriptor in get_registry():
            if not descriptor.toggleable:
                continue
            # Build a settings dict where every key the predicate could
            # read has been explicitly set to a value that, on its own,
            # makes the predicate read True.
            seed = dict(truthy_seed)
            for key in descriptor.setting_keys:
                seed[key] = _maximally_on_value_for(key)
            # Sanity: the seed should make the predicate ON.
            assert descriptor.is_enabled(seed) is True, (
                f"test seed did not make {descriptor.id!r} read ON; "
                "_maximally_on_value_for likely needs a new branch for "
                f"{descriptor.setting_keys!r}"
            )
            off = dict(seed)
            off.update(descriptor.disable_overrides or {})
            assert descriptor.is_enabled(off) is False, (
                f"{descriptor.id!r} disable_overrides leaves the "
                "predicate reading ON when other companion keys had been "
                "previously enabled — the disable payload must clear every "
                "input the predicate ORs over"
            )


def test_heretic_enable_override_uses_service_default_output_dir() -> None:
    """The Forge's enable payload must write the same output root the
    Heretic service falls back to on its own. CWD-relative paths
    break in packaged/desktop runs where the process working
    directory is read-only or unstable.

    The service's default lives inline at
    ``HereticService.__init__`` (``output_root or
    pathlib.Path.home() / ".metis_heretic"``); we mirror it as
    ``HERETIC_DEFAULT_OUTPUT_DIR`` in ``forge_registry``. If either
    drifts, this test trips.
    """
    import pathlib

    from metis_app.services.forge_registry import HERETIC_DEFAULT_OUTPUT_DIR

    descriptor = get_descriptor("heretic-abliteration")
    assert descriptor is not None
    assert descriptor.enable_overrides is not None
    assert descriptor.enable_overrides == {
        "heretic_output_dir": HERETIC_DEFAULT_OUTPUT_DIR,
    }

    expected_default = str(pathlib.Path.home() / ".metis_heretic")
    assert HERETIC_DEFAULT_OUTPUT_DIR == expected_default
    # Hard guard: path must be absolute. A CWD-relative path here is
    # exactly the bug Codex P1 caught on PR #580.
    assert pathlib.Path(HERETIC_DEFAULT_OUTPUT_DIR).is_absolute()


def test_heretic_probe_blocks_when_cli_missing() -> None:
    """When the ``heretic`` CLI is not on ``$PATH``, the descriptor's
    readiness probe returns ``status="blocked"`` with a single
    blocker referring to the missing CLI and an ``install_heretic``
    CTA for the frontend.
    """
    from metis_app.services.forge_registry import RuntimeReadiness

    descriptor = get_descriptor("heretic-abliteration")
    assert descriptor is not None

    with patch(
        "metis_app.services.heretic_service.is_heretic_available",
        return_value=False,
    ):
        readiness = descriptor.readiness({})

    assert isinstance(readiness, RuntimeReadiness)
    assert readiness.status == "blocked"
    assert any("PATH" in b for b in readiness.blockers)
    assert readiness.cta_kind == "install_heretic"


def test_heretic_probe_ready_when_cli_available() -> None:
    descriptor = get_descriptor("heretic-abliteration")
    assert descriptor is not None
    with patch(
        "metis_app.services.heretic_service.is_heretic_available",
        return_value=True,
    ):
        readiness = descriptor.readiness({})
    assert readiness.status == "ready"
    assert readiness.blockers == ()


def test_timesfm_probe_is_informational_blocked() -> None:
    """TimesFM is not toggleable from the gallery; the probe reports
    a permanent blocker pointing to the chat-mode picker so the
    frontend can render a deep-link CTA."""
    descriptor = get_descriptor("timesfm-forecasting")
    assert descriptor is not None
    readiness = descriptor.readiness({})
    assert readiness.status == "blocked"
    assert any("Forecast" in b for b in readiness.blockers)
    assert readiness.cta_kind == "switch_chat_path"
    assert readiness.cta_target == "/chat"


def test_route_serialises_runtime_blocker_for_blocked_techniques() -> None:
    """End-to-end: with the Heretic CLI absent, the route output's
    ``heretic-abliteration`` row reports ``runtime_status="blocked"``
    and includes the blocker text in ``runtime_blockers``."""
    with patch(
        "metis_app.services.heretic_service.is_heretic_available",
        return_value=False,
    ):
        with _client() as client:
            techniques = client.get("/v1/forge/techniques").json()["techniques"]
    heretic = next(t for t in techniques if t["id"] == "heretic-abliteration")
    assert heretic["runtime_status"] == "blocked"
    assert any("PATH" in b for b in heretic["runtime_blockers"])
    assert heretic["runtime_cta_kind"] == "install_heretic"
    # TimesFM is independent of Heretic but always informational-blocked.
    timesfm = next(t for t in techniques if t["id"] == "timesfm-forecasting")
    assert timesfm["runtime_status"] == "blocked"
    assert timesfm["runtime_cta_kind"] == "switch_chat_path"


def test_readiness_swallows_probe_errors() -> None:
    """A probe that raises must collapse to ``status="blocked"``
    rather than propagate up to the route handler. The collapsed
    state's blocker text mentions the failure so debugging stays
    cheap."""
    from metis_app.services.forge_registry import (
        RuntimeReadiness,
        TechniqueDescriptor,
    )

    def boom(_settings: object) -> RuntimeReadiness:
        raise RuntimeError("network down")

    descriptor = TechniqueDescriptor(
        id="boom",
        name="Boom",
        description="boom",
        pillar="cortex",
        setting_keys=(),
        enabled_predicate=lambda _: False,
        runtime_probe=boom,
    )
    readiness = descriptor.readiness({})
    assert readiness.status == "blocked"
    assert any("network down" in b for b in readiness.blockers)


def _maximally_on_value_for(key: str) -> object:
    """Pick a value for ``key`` that would make any predicate that
    reads it interpret it as 'on'. Boolean keys → True; the handful
    of value-keys read by current predicates have known on values.
    """
    # Value keys that current predicates read explicitly. Add new
    # entries here when a future predicate gates on a string or
    # numeric value.
    explicit_on = {
        "hybrid_alpha": 0.5,
        "retrieval_mode": "mmr",
        "swarm_n_personas": 8,
        "chat_path": "Forecast",
        "chunk_strategy": "semantic",
        "heretic_output_dir": "/tmp/heretic",
        "agentic_max_iterations": 4,
        "agentic_convergence_threshold": 0.95,
        "agentic_iteration_budget": 4,
        "swarm_n_rounds": 4,
        "subquery_max_docs": 100,
        "mmr_lambda": 0.5,
        "hebbian_boost": 1.0,
        "hebbian_decay": 0.999,
        "forecast_model_id": "google/timesfm-2.5-200m-pytorch",
        "forecast_max_context": 2048,
        "forecast_max_horizon": 256,
        "forecast_use_quantiles": True,
        "forecast_xreg_mode": "xreg + timesfm",
        "brain_pass_native_enabled": True,
        "brain_pass_native_text_enabled": True,
        "brain_pass_model_id": "facebook/tribev2",
        "news_comet_sources": ["arxiv"],
        "news_comet_poll_interval_seconds": 300,
        "news_comet_max_active": 5,
        "news_comet_auto_absorb_threshold": 0.5,
        "news_comet_rss_feeds": [],
        "news_comet_reddit_subs": [],
        "enable_claim_level_grounding_citefix_lite": True,
    }
    if key in explicit_on:
        return explicit_on[key]
    # Default: treat unknown keys as booleans flipped on.
    return True


def test_list_techniques_ids_are_unique_and_url_safe() -> None:
    """Slugs are stable URL anchors per ADR 0014; renames need a
    redirect or deprecation pass. Guard them mechanically."""
    with _client() as client:
        techniques = client.get("/v1/forge/techniques").json()["techniques"]

    ids = [item["id"] for item in techniques]
    assert len(ids) == len(set(ids)), "duplicate technique slug detected"
    for slug in ids:
        assert slug == slug.lower(), f"slug must be lowercase: {slug}"
        # Anchor-safe: lowercase letters, digits, hyphens. Underscores
        # and other separators force escaping in URLs and break the
        # `/forge#<id>` deep-link contract.
        assert all(ch.isalnum() or ch == "-" for ch in slug), (
            f"slug must be alphanumeric or hyphen: {slug}"
        )


def test_registry_setting_keys_reference_real_settings() -> None:
    """Every ``setting_keys`` entry must exist in the live settings
    store. Drift between the hand-curated registry and
    ``default_settings.json`` is caught here.
    """
    import metis_app.settings_store as settings_store

    settings = settings_store.load_settings()
    missing = find_missing_setting_keys(settings)
    assert missing == {}, (
        "Forge registry references settings keys that do not exist in "
        f"default_settings.json: {missing}"
    )


def test_enabled_field_reflects_live_settings_overrides() -> None:
    """Phase 2a promise: user toggles surface in the gallery.

    Patch ``load_settings`` at the route layer so the response reflects
    a synthetic settings dict in which a few defaults are flipped, and
    confirm the ``enabled`` flag tracks the override per descriptor.
    """
    base = {
        # Defaults that should make the corresponding techniques on:
        "use_sub_queries": True,
        "use_reranker": True,
        "enable_brain_pass": True,
        "enable_hebbian": True,
        "enable_citation_v2": True,
        # Defaults off:
        "agentic_mode": False,
        "hybrid_alpha": 1.0,
        "retrieval_mode": "flat",
        "swarm_n_personas": 0,
        "chat_path": "RAG",
        "heretic_output_dir": "",
        "news_comets_enabled": False,
        "chunk_strategy": "fixed",
        "structure_aware_ingestion": False,
        "semantic_layout_ingestion": False,
    }

    overrides: dict[str, Any] = dict(base)
    overrides.update(
        {
            "agentic_mode": True,  # iterrag-convergence on
            "hybrid_alpha": 0.6,  # hybrid-search on
            "retrieval_mode": "mmr",  # mmr-diversification on
            "swarm_n_personas": 3,  # swarm-personas on
            "news_comets_enabled": True,  # news-comets on
            "chunk_strategy": "semantic",  # semantic-chunking on
            "use_reranker": False,  # reranker off
        }
    )

    with patch(
        "metis_app.api_litestar.routes.forge.load_settings",
        return_value=overrides,
    ):
        with _client() as client:
            resp = client.get("/v1/forge/techniques")
            techniques = {item["id"]: item for item in resp.json()["techniques"]}

    assert techniques["iterrag-convergence"]["enabled"] is True
    assert techniques["hybrid-search"]["enabled"] is True
    assert techniques["mmr-diversification"]["enabled"] is True
    assert techniques["swarm-personas"]["enabled"] is True
    assert techniques["news-comets"]["enabled"] is True
    assert techniques["semantic-chunking"]["enabled"] is True
    assert techniques["reranker"]["enabled"] is False
    # Spot-check a few that should match the base defaults:
    assert techniques["sub-query-expansion"]["enabled"] is True
    assert techniques["tribev2-multimodal"]["enabled"] is True
    assert techniques["citation-v2"]["enabled"] is True
    assert techniques["timesfm-forecasting"]["enabled"] is False


def test_descriptor_predicate_swallows_predicate_errors() -> None:
    """Defensive guard: a misbehaving predicate returns ``False``
    rather than crashing the gallery endpoint.
    """
    descriptor = get_descriptor("reranker")
    assert descriptor is not None

    # ``int.real`` access on a None will raise — confirm ``is_enabled``
    # converts the exception to a clean ``False``.
    class _BoomDict(dict):
        def get(self, *args, **kwargs):  # type: ignore[override]
            raise RuntimeError("boom")

    assert descriptor.is_enabled(_BoomDict()) is False


@pytest.mark.parametrize(
    "slug",
    [
        "iterrag-convergence",
        "reranker",
        "tribev2-multimodal",
        "news-comets",
    ],
)
def test_get_descriptor_resolves_known_slugs(slug: str) -> None:
    descriptor = get_descriptor(slug)
    assert descriptor is not None
    assert descriptor.id == slug


def test_get_descriptor_returns_none_for_unknown_slug() -> None:
    assert get_descriptor("not-a-real-technique") is None
