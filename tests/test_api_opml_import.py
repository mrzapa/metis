"""End-to-end test for ``POST /v1/comets/opml/import`` (ADR 0008 §5)."""

from __future__ import annotations

from io import BytesIO

import pytest
from litestar.testing import TestClient

from metis_app.api_litestar import create_app
from metis_app.services.news_feed_repository import (
    NewsFeedRepository,
    reset_default_repository,
)


_SAMPLE_OPML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <body>
    <outline type="rss" xmlUrl="https://news.ycombinator.com/rss" />
    <outline type="rss" xmlUrl="https://lwn.net/headlines/rss" />
  </body>
</opml>
""".encode("utf-8")


@pytest.fixture
def repo() -> NewsFeedRepository:
    fresh = NewsFeedRepository(":memory:")
    reset_default_repository(fresh)
    yield fresh
    reset_default_repository(None)


@pytest.fixture
def client(repo, monkeypatch):
    """Patch settings load/save so the OPML endpoint does not write disk."""
    state: dict[str, object] = {
        "settings": {
            "news_comet_rss_feeds": [],
            "seedling_opml_import_max_bytes": 1_048_576,
        },
    }

    def _load() -> dict[str, object]:
        # Return a shallow copy so the route's mutation does not leak.
        return dict(state["settings"])  # type: ignore[arg-type]

    def _save(settings: dict[str, object]) -> None:
        state["settings"] = dict(settings)

    monkeypatch.setattr("metis_app.settings_store.load_settings", _load)
    monkeypatch.setattr("metis_app.settings_store.save_settings", _save)

    app = create_app()
    with TestClient(app=app) as c:
        yield c, state


def test_opml_import_adds_new_feeds(client, repo):
    c, state = client
    resp = c.post(
        "/v1/comets/opml/import",
        files={"file": ("subs.opml", BytesIO(_SAMPLE_OPML), "application/xml")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == 2
    assert "https://news.ycombinator.com/rss" in body["added_urls"]
    # Settings persisted.
    assert state["settings"]["news_comet_rss_feeds"] == [  # type: ignore[index]
        "https://news.ycombinator.com/rss",
        "https://lwn.net/headlines/rss",
    ]
    # Cursors seeded with last_polled_at = 0.
    cursor = repo.get_cursor("rss", "https://news.ycombinator.com/rss")
    assert cursor is not None and cursor.last_polled_at == 0.0


def test_opml_import_dedups_against_existing(client, repo):
    c, state = client
    state["settings"]["news_comet_rss_feeds"] = [  # type: ignore[index]
        "https://news.ycombinator.com/rss",
    ]
    resp = c.post(
        "/v1/comets/opml/import",
        files={"file": ("subs.opml", BytesIO(_SAMPLE_OPML), "application/xml")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == 1
    assert body["skipped_duplicate"] == 1


def test_opml_import_rejects_oversized_payload(client):
    c, state = client
    state["settings"]["seedling_opml_import_max_bytes"] = 10  # type: ignore[index]
    resp = c.post(
        "/v1/comets/opml/import",
        files={"file": ("big.opml", BytesIO(_SAMPLE_OPML), "application/xml")},
    )
    assert resp.status_code == 413


def test_opml_import_rejects_malformed_xml(client):
    c, _ = client
    resp = c.post(
        "/v1/comets/opml/import",
        files={"file": ("bad.opml", BytesIO(b"<opml><body><<<"), "application/xml")},
    )
    assert resp.status_code == 400


def test_opml_import_returns_422_when_no_feeds(client):
    c, _ = client
    payload = b"""<?xml version="1.0"?>
    <opml><body><outline title='no feeds here'/></body></opml>"""
    resp = c.post(
        "/v1/comets/opml/import",
        files={"file": ("empty.opml", BytesIO(payload), "application/xml")},
    )
    assert resp.status_code == 422


def test_opml_import_accepts_raw_body(client, repo):
    c, _ = client
    resp = c.post(
        "/v1/comets/opml/import",
        content=_SAMPLE_OPML,
        headers={"content-type": "application/xml"},
    )
    assert resp.status_code == 200
    assert resp.json()["added"] == 2
