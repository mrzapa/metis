"""Tests for comet-news API routes (Litestar)."""

from __future__ import annotations


import pytest
from litestar.testing import TestClient

from metis_app.api_litestar import create_app
from metis_app.models.comet_event import CometEvent, NewsItem
from metis_app.services.news_feed_repository import (
    NewsFeedRepository,
    reset_default_repository,
)


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
def repo() -> NewsFeedRepository:
    """Install a `:memory:` repository so each test starts clean."""
    fresh = NewsFeedRepository(":memory:")
    reset_default_repository(fresh)
    yield fresh
    reset_default_repository(None)


@pytest.fixture
def client(repo):
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
    resp = client.get("/v1/comets/active")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_active_with_comets(client, repo):
    evt = _make_comet_event()
    repo.record_comet(evt)
    resp = client.get("/v1/comets/active")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["comet_id"] == "c-1"


def test_absorb_existing_comet(client, repo):
    evt = _make_comet_event(comet_id="absorb-1", decision="approach")
    repo.record_comet(evt)
    resp = client.post("/v1/comets/absorb-1/absorb", json={"notes": "loved it"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert repo.get_comet("absorb-1").phase == "absorbing"


def test_absorb_missing_comet(client):
    resp = client.post("/v1/comets/nonexistent/absorb")
    assert resp.status_code == 404


def test_dismiss_existing_comet(client, repo):
    evt = _make_comet_event(comet_id="dismiss-1")
    repo.record_comet(evt)
    resp = client.post("/v1/comets/dismiss-1/dismiss", json={"reason": "spam"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    refetched = repo.get_comet("dismiss-1")
    assert refetched is not None
    assert refetched.phase == "dismissed"


def test_dismiss_missing_comet(client):
    resp = client.post("/v1/comets/nonexistent/dismiss")
    assert resp.status_code == 404
