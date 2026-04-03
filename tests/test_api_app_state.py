"""Tests for AppStateService + FastAPI + Litestar app-state routes."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from litestar.testing import TestClient as LitestarTestClient

from metis_app.api.app import create_app as create_fastapi_app
from metis_app.api.app_state import get_app_state_service
from metis_app.services.app_state_service import AppStateService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app_state_service(tmp_path):
    return AppStateService(db_path=str(tmp_path / "app_state.db"))


@pytest.fixture
def fastapi_client(app_state_service):
    app = create_fastapi_app()
    app.dependency_overrides[get_app_state_service] = lambda: app_state_service
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def litestar_client(app_state_service, tmp_path):
    from metis_app.api_litestar import create_app as create_litestar_app
    import metis_app.api_litestar.routes.app_state as litestar_app_state

    def _get_override() -> AppStateService:
        return app_state_service

    with patch.object(litestar_app_state, "_get_service", _get_override):
        litestar_app_state._service = None  # reset singleton so patch takes effect
        app = create_litestar_app()
        with LitestarTestClient(app=app) as client:
            yield client


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------


def test_write_returns_incrementing_version(app_state_service):
    v1 = app_state_service.write("sess1", "k1", "val1")
    v2 = app_state_service.write("sess1", "k2", "val2")
    assert v2 > v1


def test_read_returns_none_for_missing_key(app_state_service):
    result = app_state_service.read("no-session", "no-key")
    assert result is None


def test_list_returns_all_keys_for_session(app_state_service):
    app_state_service.write("sess-list", "a", "1")
    app_state_service.write("sess-list", "b", "2")
    entries = app_state_service.list("sess-list")
    keys = [e["key"] for e in entries]
    assert sorted(keys) == ["a", "b"]


def test_delete_removes_key(app_state_service):
    app_state_service.write("sess-del", "x", "hello")
    app_state_service.delete("sess-del", "x")
    assert app_state_service.read("sess-del", "x") is None


def test_get_version_returns_current_counter(app_state_service):
    before = app_state_service.get_version()
    app_state_service.write("sess-ver", "k", "v")
    after = app_state_service.get_version()
    assert after > before


def test_write_increments_version_atomically(app_state_service):
    v0 = app_state_service.get_version()
    app_state_service.write("sess-atomic", "key", "value")
    v1 = app_state_service.get_version()
    assert v1 == v0 + 1


# ---------------------------------------------------------------------------
# FastAPI integration tests
# ---------------------------------------------------------------------------


def test_post_app_state_returns_200(fastapi_client):
    r = fastapi_client.post(
        "/v1/app-state/s1/key1", json={"value": "hello"}
    )
    assert r.status_code == 200
    assert "version" in r.json()


def test_get_app_state_key_returns_value(fastapi_client):
    fastapi_client.post("/v1/app-state/s2/mykey", json={"value": "myval"})
    r = fastapi_client.get("/v1/app-state/s2/mykey")
    assert r.status_code == 200
    data = r.json()
    assert data["value"] == "myval"
    assert data["key"] == "mykey"


def test_get_app_state_missing_key_returns_404(fastapi_client):
    r = fastapi_client.get("/v1/app-state/no-session/no-key")
    assert r.status_code == 404


def test_delete_app_state_returns_ok(fastapi_client):
    fastapi_client.post("/v1/app-state/s3/dk", json={"value": "to-delete"})
    r = fastapi_client.delete("/v1/app-state/s3/dk")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_poll_returns_changed_true_after_write(fastapi_client):
    # Get baseline version
    r0 = fastapi_client.post("/v1/app-state/s4/k", json={"value": "v"})
    version_after = r0.json()["version"]
    # Poll with since = version_after - 1 → changed must be True
    r = fastapi_client.get(f"/v1/poll?since={version_after - 1}")
    assert r.status_code == 200
    data = r.json()
    assert data["changed"] is True


def test_poll_returns_changed_false_when_no_write(fastapi_client):
    # Get current version without writing
    from metis_app.api.app_state import get_app_state_service as _dep  # noqa: F401

    # We need the service's current version; use the fastapi_client to get it
    # by polling with since=0 first to learn current version
    r0 = fastapi_client.get("/v1/poll?since=0")
    current_version = r0.json()["version"]
    # Now poll with since=current_version → no new writes → changed=False
    r = fastapi_client.get(f"/v1/poll?since={current_version}")
    assert r.status_code == 200
    assert r.json()["changed"] is False


# ---------------------------------------------------------------------------
# Litestar smoke test
# ---------------------------------------------------------------------------


def test_litestar_poll_returns_200(litestar_client):
    r = litestar_client.get("/v1/poll?since=0")
    assert r.status_code == 200
    data = r.json()
    assert "version" in data
    assert "changed" in data


def test_litestar_post_app_state_returns_value(litestar_client):
    r = litestar_client.post(
        "/v1/app-state/ls1/mykey", json={"value": "myval"}
    )
    assert r.status_code == 200
    assert "version" in r.json()


def test_litestar_get_app_state_key_returns_value(litestar_client):
    litestar_client.post("/v1/app-state/ls2/k", json={"value": "v"})
    r = litestar_client.get("/v1/app-state/ls2/k")
    assert r.status_code == 200
    data = r.json()
    assert data["value"] == "v"
    assert data["key"] == "k"


def test_litestar_get_app_state_missing_key_returns_404(litestar_client):
    r = litestar_client.get("/v1/app-state/no-session-ls/no-key")
    assert r.status_code == 404


def test_litestar_delete_app_state_returns_ok(litestar_client):
    litestar_client.post("/v1/app-state/ls3/dk", json={"value": "to-delete"})
    r = litestar_client.delete("/v1/app-state/ls3/dk")
    assert r.status_code == 200
    assert r.json().get("ok") is True
