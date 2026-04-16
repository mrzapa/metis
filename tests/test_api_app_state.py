"""Tests for AppStateService + Litestar app-state routes."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from litestar.testing import TestClient

from metis_app.services.app_state_service import AppStateService


@pytest.fixture
def app_state_service(tmp_path):
    return AppStateService(db_path=str(tmp_path / "app_state.db"))


@pytest.fixture
def client(app_state_service):
    from metis_app.api_litestar import create_app
    import metis_app.api_litestar.routes.app_state as litestar_app_state

    def _get_override() -> AppStateService:
        return app_state_service

    with patch.object(litestar_app_state, "_get_service", _get_override):
        litestar_app_state._service = None  # reset singleton so patch takes effect
        app = create_app()
        with TestClient(app=app) as c:
            yield c


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
# Litestar integration tests
# ---------------------------------------------------------------------------


def test_poll_returns_200(client):
    r = client.get("/v1/poll?since=0")
    assert r.status_code == 200
    data = r.json()
    assert "version" in data
    assert "changed" in data


def test_post_app_state_returns_version(client):
    r = client.post("/v1/app-state/s1/mykey", json={"value": "myval"})
    assert r.status_code == 200
    assert "version" in r.json()


def test_get_app_state_key_returns_value(client):
    client.post("/v1/app-state/s2/k", json={"value": "v"})
    r = client.get("/v1/app-state/s2/k")
    assert r.status_code == 200
    data = r.json()
    assert data["value"] == "v"
    assert data["key"] == "k"


def test_get_app_state_missing_key_returns_404(client):
    r = client.get("/v1/app-state/no-session-ls/no-key")
    assert r.status_code == 404


def test_delete_app_state_returns_ok(client):
    client.post("/v1/app-state/s3/dk", json={"value": "to-delete"})
    r = client.delete("/v1/app-state/s3/dk")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_poll_returns_changed_true_after_write(client):
    r0 = client.post("/v1/app-state/s4/k", json={"value": "v"})
    version_after = r0.json()["version"]
    r = client.get(f"/v1/poll?since={version_after - 1}")
    assert r.status_code == 200
    data = r.json()
    assert data["changed"] is True


def test_poll_returns_changed_false_when_no_write(client):
    r0 = client.get("/v1/poll?since=0")
    current_version = r0.json()["version"]
    r = client.get(f"/v1/poll?since={current_version}")
    assert r.status_code == 200
    assert r.json()["changed"] is False
