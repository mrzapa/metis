"""Tests for GET /v1/settings and POST /v1/settings endpoints."""

from __future__ import annotations

from importlib import import_module

from litestar.testing import TestClient

litestar_app = import_module("metis_app.api_litestar")
settings_module = import_module("metis_app.api_litestar.routes.settings")


def _client() -> TestClient:
    return TestClient(app=litestar_app.create_app())


def _fake_load(extra: dict | None = None) -> dict:
    base = {
        "llm_provider": "anthropic",
        "llm_model": "claude-opus-4-6",
        "llm_temperature": 0.0,
        "api_key_openai": "sk-secret",
        "api_key_anthropic": "ant-secret",
        "api_key_voyage": "voy-secret",
    }
    if extra:
        base.update(extra)
    return base


# ---------------------------------------------------------------------------
# GET /v1/settings
# ---------------------------------------------------------------------------


def test_get_settings_returns_200(monkeypatch) -> None:
    monkeypatch.setattr(settings_module._store, "load_settings", lambda: _fake_load())
    with _client() as c:
        response = c.get("/v1/settings")
        assert response.status_code == 200


def test_get_settings_returns_safe_subset(monkeypatch) -> None:
    monkeypatch.setattr(settings_module._store, "load_settings", lambda: _fake_load())
    with _client() as c:
        data = c.get("/v1/settings").json()
    assert "api_key_openai" not in data
    assert "api_key_anthropic" not in data
    assert "api_key_voyage" not in data


def test_get_settings_redacts_multiple_api_keys(monkeypatch) -> None:
    settings_with_keys = {
        "llm_provider": "openai",
        "api_key_openai": "sk-1",
        "api_key_anthropic": "ant-1",
        "api_key_cohere": "co-1",
        "api_key_xai": "xai-1",
        "api_key_voyage": "voy-1",
    }
    monkeypatch.setattr(settings_module._store, "load_settings", lambda: settings_with_keys)
    with _client() as c:
        data = c.get("/v1/settings").json()
    api_key_fields = [k for k in data if k.startswith("api_key_")]
    assert api_key_fields == [], f"Leaked api_key_* fields: {api_key_fields}"


def test_get_settings_includes_safe_keys(monkeypatch) -> None:
    monkeypatch.setattr(settings_module._store, "load_settings", lambda: _fake_load())
    with _client() as c:
        data = c.get("/v1/settings").json()
    assert data["llm_provider"] == "anthropic"
    assert data["llm_model"] == "claude-opus-4-6"
    assert data["llm_temperature"] == 0.0


# ---------------------------------------------------------------------------
# POST /v1/settings
# ---------------------------------------------------------------------------


def test_post_settings_rejects_api_key_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings_module._store, "load_settings", lambda: _fake_load())
    monkeypatch.delenv("METIS_ALLOW_API_KEY_WRITE", raising=False)

    with _client() as c:
        response = c.post(
            "/v1/settings",
            json={"updates": {"api_key_openai": "sk-new"}},
        )

    assert response.status_code == 403
    assert "api_key_openai" in response.json()["detail"]


def test_post_settings_rejects_any_api_key_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings_module._store, "load_settings", lambda: _fake_load())
    monkeypatch.delenv("METIS_ALLOW_API_KEY_WRITE", raising=False)

    with _client() as c:
        response = c.post(
            "/v1/settings",
            json={"updates": {"llm_provider": "openai", "api_key_openai": "sk-new"}},
        )

    assert response.status_code == 403


def test_post_settings_allows_api_key_when_env_set(monkeypatch) -> None:
    saved: dict = {}

    def _fake_save(updates: dict) -> dict:
        merged = _fake_load()
        merged.update(updates)
        saved.update(merged)
        return merged

    monkeypatch.setattr(settings_module._store, "load_settings", lambda: _fake_load())
    monkeypatch.setattr(settings_module._store, "save_settings", _fake_save)
    monkeypatch.setenv("METIS_ALLOW_API_KEY_WRITE", "1")

    with _client() as c:
        response = c.post(
            "/v1/settings",
            json={"updates": {"api_key_openai": "sk-new"}},
        )

    assert response.status_code == 200
    assert saved.get("api_key_openai") == "sk-new"


def test_post_settings_persists_safe_keys(monkeypatch) -> None:
    saved: dict = {}

    def _fake_save(updates: dict) -> dict:
        merged = _fake_load()
        merged.update(updates)
        saved.update(merged)
        return merged

    monkeypatch.setattr(settings_module._store, "load_settings", lambda: _fake_load())
    monkeypatch.setattr(settings_module._store, "save_settings", _fake_save)
    monkeypatch.delenv("METIS_ALLOW_API_KEY_WRITE", raising=False)

    with _client() as c:
        response = c.post(
            "/v1/settings",
            json={"updates": {"llm_provider": "openai", "llm_temperature": 0.7}},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["llm_provider"] == "openai"
    assert data["llm_temperature"] == 0.7


def test_post_settings_response_never_returns_api_keys(monkeypatch) -> None:
    def _fake_save(updates: dict) -> dict:
        merged = _fake_load()
        merged.update(updates)
        return merged

    monkeypatch.setattr(settings_module._store, "load_settings", lambda: _fake_load())
    monkeypatch.setattr(settings_module._store, "save_settings", _fake_save)
    monkeypatch.setenv("METIS_ALLOW_API_KEY_WRITE", "1")

    with _client() as c:
        response = c.post(
            "/v1/settings",
            json={"updates": {"api_key_openai": "sk-new", "llm_provider": "openai"}},
        )

    assert response.status_code == 200
    data = response.json()
    api_key_fields = [k for k in data if k.startswith("api_key_")]
    assert api_key_fields == [], f"Response leaked api_key_* fields: {api_key_fields}"


def test_post_settings_503_on_write_error(monkeypatch) -> None:
    monkeypatch.setattr(settings_module._store, "load_settings", lambda: _fake_load())
    monkeypatch.setattr(
        settings_module._store,
        "save_settings",
        lambda _: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.delenv("METIS_ALLOW_API_KEY_WRITE", raising=False)

    with _client() as c:
        response = c.post(
            "/v1/settings",
            json={"updates": {"llm_provider": "openai"}},
        )

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# resolve_secret_refs tests (settings_store)
# ---------------------------------------------------------------------------


def test_resolve_secret_refs_replaces_env_prefix(monkeypatch) -> None:
    from metis_app.settings_store import resolve_secret_refs

    monkeypatch.setenv("TEST_METIS_KEY", "secret123")
    result = resolve_secret_refs({"api_key_openai": "env:TEST_METIS_KEY", "llm_provider": "openai"})

    assert result["api_key_openai"] == "secret123"
    assert result["llm_provider"] == "openai"


def test_resolve_secret_refs_retains_value_when_env_var_missing(monkeypatch) -> None:
    from metis_app.settings_store import resolve_secret_refs

    monkeypatch.delenv("TEST_METIS_MISSING", raising=False)
    result = resolve_secret_refs({"api_key_openai": "env:TEST_METIS_MISSING"})

    assert result["api_key_openai"] == "env:TEST_METIS_MISSING"


def test_resolve_secret_refs_leaves_non_env_values_untouched() -> None:
    from metis_app.settings_store import resolve_secret_refs

    data = {"llm_provider": "openai", "max_results": 5, "flag": True}
    result = resolve_secret_refs(data)

    assert result == data
