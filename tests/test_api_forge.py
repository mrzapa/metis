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
        # Heretic and similar runtime-prereq techniques rely on more
        # than just settings — only assert the simpler predicates.
        if descriptor.id in {"heretic-abliteration", "timesfm-forecasting"}:
            continue
        assert descriptor.is_enabled(off) is False, (
            f"{descriptor.id!r} disable_overrides did not flip the predicate OFF"
        )


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
