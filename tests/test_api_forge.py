"""Tests for the M14 Forge gallery routes (Phase 1)."""

from __future__ import annotations

from litestar.testing import TestClient

from metis_app.api_litestar import create_app
from metis_app.api_litestar.routes.forge import _TECHNIQUE_INVENTORY


def _client() -> TestClient:
    return TestClient(app=create_app())


def test_list_techniques_returns_static_inventory() -> None:
    with _client() as client:
        resp = client.get("/v1/forge/techniques")
        assert resp.status_code == 200
        payload = resp.json()

    assert payload["phase"] == 1
    techniques = payload["techniques"]
    assert len(techniques) == len(_TECHNIQUE_INVENTORY)

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
        # Phase 1 has no live trace integration yet (that's Phase 6).
        assert entry["recent_uses"] == []


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


def test_list_techniques_setting_keys_reference_real_settings() -> None:
    """Every ``setting_keys`` entry must exist in ``default_settings.json``.

    This guards against typos in the hand-curated inventory. When
    Phase 2 swaps the static list for the live registry, the same
    invariant holds and is enforced by the registry's
    ``TechniqueDescriptor`` constructor.
    """
    import metis_app.settings_store as settings_store

    defaults = settings_store.load_settings()

    with _client() as client:
        techniques = client.get("/v1/forge/techniques").json()["techniques"]

    for entry in techniques:
        for key in entry["setting_keys"]:
            assert key in defaults, (
                f"technique {entry['id']!r} references missing setting "
                f"key {key!r}"
            )
