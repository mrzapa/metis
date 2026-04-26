"""Tests for Seedling Litestar routes and lifecycle hooks."""

from __future__ import annotations

from litestar.testing import TestClient

from metis_app.api_litestar import create_app
from metis_app.seedling import get_seedling_status
from metis_app.seedling.activity import clear_seedling_activity_events
from metis_app.seedling.lifecycle import reset_seedling_worker
from metis_app.seedling.status import SeedlingStatusCache
from metis_app.seedling.worker import SeedlingWorker


def test_seedling_status_endpoint_reports_startup_and_shutdown(tmp_path) -> None:
    clear_seedling_activity_events()
    worker = SeedlingWorker(
        status_cache=SeedlingStatusCache(tmp_path / "status.json"),
    )
    reset_seedling_worker(worker)

    with TestClient(app=create_app()) as client:
        resp = client.get("/v1/seedling/status")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["running"] is True
        assert payload["current_stage"] == "seedling"
        assert payload["last_tick_at"]
        assert payload["next_action_at"]
        assert payload["queue_depth"] == 0
        assert payload["activity_events"] == []

    stopped = get_seedling_status().to_dict()
    assert stopped["running"] is False
    assert stopped["next_action_at"] is None
    reset_seedling_worker()


def test_seedling_status_endpoint_includes_worker_activity_events(tmp_path) -> None:
    clear_seedling_activity_events()
    reset_seedling_worker()

    with TestClient(app=create_app()) as client:
        resp = client.get("/v1/seedling/status")
        assert resp.status_code == 200
        events = resp.json()["activity_events"]
        assert [event["source"] for event in events] == ["seedling", "seedling"]
        assert events[0]["summary"] == "Seedling heartbeat"
        assert events[1]["summary"] == "Seedling lifecycle started"

    reset_seedling_worker()


def test_seedling_status_endpoint_returns_model_status_field(tmp_path) -> None:
    """Phase 4b: ``model_status`` lands as a top-level field on every
    status read so the dock can render the right copy without a
    second round-trip."""
    clear_seedling_activity_events()
    worker = SeedlingWorker(
        status_cache=SeedlingStatusCache(tmp_path / "status.json"),
    )
    reset_seedling_worker(worker)

    with TestClient(app=create_app()) as client:
        resp = client.get("/v1/seedling/status")
        assert resp.status_code == 200
        payload = resp.json()
        assert "model_status" in payload
        # Default install: no GGUF configured → frontend_only.
        assert payload["model_status"] == "frontend_only"
        assert "last_overnight_reflection_at" in payload

    reset_seedling_worker()
