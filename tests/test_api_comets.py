"""Tests for comet-news API routes (Litestar)."""

from __future__ import annotations


import pytest
from litestar.testing import TestClient

from metis_app.api_litestar import create_app
from metis_app.models.comet_event import CometEvent, NewsItem


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


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app=app) as c:
        yield c


def test_get_sources(client):
    resp = client.get("/v1/comets/sources")
    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data
    assert "available_sources" in data
    assert "hackernews" in data["available_sources"]
    assert "reddit" in data["available_sources"]


def test_get_active_empty(client):
    import metis_app.api_litestar.routes.comets as comets_mod
    comets_mod._active_comets.clear()
    resp = client.get("/v1/comets/active")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_active_with_comets(client):
    import metis_app.api_litestar.routes.comets as comets_mod
    evt = _make_comet_event()
    comets_mod._active_comets.clear()
    comets_mod._active_comets.append(evt)
    try:
        resp = client.get("/v1/comets/active")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["comet_id"] == "c-1"
    finally:
        comets_mod._active_comets.clear()


def test_absorb_existing_comet(client):
    import metis_app.api_litestar.routes.comets as comets_mod
    evt = _make_comet_event(comet_id="absorb-1", decision="approach")
    comets_mod._active_comets.clear()
    comets_mod._active_comets.append(evt)
    try:
        resp = client.post("/v1/comets/absorb-1/absorb")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
    finally:
        comets_mod._active_comets.clear()


def test_absorb_missing_comet(client):
    import metis_app.api_litestar.routes.comets as comets_mod
    comets_mod._active_comets.clear()
    resp = client.post("/v1/comets/nonexistent/absorb")
    assert resp.status_code == 404


def test_dismiss_existing_comet(client):
    import metis_app.api_litestar.routes.comets as comets_mod
    evt = _make_comet_event(comet_id="dismiss-1")
    comets_mod._active_comets.clear()
    comets_mod._active_comets.append(evt)
    try:
        resp = client.post("/v1/comets/dismiss-1/dismiss")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert comets_mod._active_comets[0].phase == "dismissed"
    finally:
        comets_mod._active_comets.clear()


def test_dismiss_missing_comet(client):
    import metis_app.api_litestar.routes.comets as comets_mod
    comets_mod._active_comets.clear()
    resp = client.post("/v1/comets/nonexistent/dismiss")
    assert resp.status_code == 404
