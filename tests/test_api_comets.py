"""Tests for comet-news API routes (FastAPI + Litestar)."""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient
from litestar.testing import TestClient as LitestarTestClient

from metis_app.api.app import create_app as create_fastapi_app
from metis_app.models.comet_event import CometEvent, NewsItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_comet_event(comet_id: str = "c-1", decision: str = "approach") -> CometEvent:
    return CometEvent(
        comet_id=comet_id,
        news_item=NewsItem(
            item_id="n-1",
            title="Test News",
            summary="Summary text",
            url="https://example.com/news",
            source_channel="rss",
        ),
        faculty_id="knowledge",
        classification_score=0.8,
        decision=decision,
        relevance_score=0.7,
        gap_score=0.6,
    )


# ---------------------------------------------------------------------------
# FastAPI fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fastapi_client():
    app = create_fastapi_app()
    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# FastAPI route tests
# ---------------------------------------------------------------------------


def test_fastapi_get_sources(fastapi_client):
    resp = fastapi_client.get("/v1/comets/sources")
    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data
    assert "available_sources" in data
    assert "hackernews" in data["available_sources"]
    assert "reddit" in data["available_sources"]


def test_fastapi_get_active_empty(fastapi_client):
    import metis_app.api.comets as comets_mod
    comets_mod._active_comets.clear()
    resp = fastapi_client.get("/v1/comets/active")
    assert resp.status_code == 200
    assert resp.json() == []


def test_fastapi_get_active_with_comets(fastapi_client):
    import metis_app.api.comets as comets_mod
    evt = _make_comet_event()
    comets_mod._active_comets.clear()
    comets_mod._active_comets.append(evt)
    try:
        resp = fastapi_client.get("/v1/comets/active")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["comet_id"] == "c-1"
    finally:
        comets_mod._active_comets.clear()


def test_fastapi_absorb_existing_comet(fastapi_client):
    import metis_app.api.comets as comets_mod
    evt = _make_comet_event(comet_id="absorb-1", decision="approach")
    comets_mod._active_comets.clear()
    comets_mod._active_comets.append(evt)
    try:
        resp = fastapi_client.post("/v1/comets/absorb-1/absorb")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
    finally:
        comets_mod._active_comets.clear()


def test_fastapi_absorb_missing_comet(fastapi_client):
    import metis_app.api.comets as comets_mod
    comets_mod._active_comets.clear()
    resp = fastapi_client.post("/v1/comets/nonexistent/absorb")
    assert resp.status_code == 404


def test_fastapi_dismiss_existing_comet(fastapi_client):
    import metis_app.api.comets as comets_mod
    evt = _make_comet_event(comet_id="dismiss-1")
    comets_mod._active_comets.clear()
    comets_mod._active_comets.append(evt)
    try:
        resp = fastapi_client.post("/v1/comets/dismiss-1/dismiss")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        # Dismiss marks phase="dismissed" but keeps it in list (filtered from active view)
        assert comets_mod._active_comets[0].phase == "dismissed"
    finally:
        comets_mod._active_comets.clear()


def test_fastapi_dismiss_missing_comet(fastapi_client):
    import metis_app.api.comets as comets_mod
    comets_mod._active_comets.clear()
    resp = fastapi_client.post("/v1/comets/nonexistent/dismiss")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Litestar fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def litestar_client():
    from metis_app.api_litestar import create_app as create_litestar_app
    app = create_litestar_app()
    with LitestarTestClient(app=app) as client:
        yield client


# ---------------------------------------------------------------------------
# Litestar route tests
# ---------------------------------------------------------------------------


def test_litestar_get_sources(litestar_client):
    resp = litestar_client.get("/v1/comets/sources")
    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data
    assert "available_sources" in data
    assert "hackernews" in data["available_sources"]
    assert "reddit" in data["available_sources"]


def test_litestar_get_active_empty(litestar_client):
    import metis_app.api_litestar.routes.comets as ls_comets
    ls_comets._active_comets.clear()
    resp = litestar_client.get("/v1/comets/active")
    assert resp.status_code == 200
    assert resp.json() == []


def test_litestar_absorb_missing_comet(litestar_client):
    import metis_app.api_litestar.routes.comets as ls_comets
    ls_comets._active_comets.clear()
    resp = litestar_client.post("/v1/comets/nonexistent/absorb")
    assert resp.status_code == 404


def test_litestar_dismiss_missing_comet(litestar_client):
    import metis_app.api_litestar.routes.comets as ls_comets
    ls_comets._active_comets.clear()
    resp = litestar_client.post("/v1/comets/nonexistent/dismiss")
    assert resp.status_code == 404
