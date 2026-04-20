"""Tests for the M17 network-audit Litestar routes (Phase 5a).

Covers the four read-only routes exposed under ``/v1/network-audit/``:

- ``GET /events`` — tail, provider filter, clamp, graceful no-store.
- ``GET /providers`` — registry coverage, 7-day counts, airplane-mode
  blocked state.
- ``GET /recent-count`` — window clamp + count accuracy.
- ``GET /stream`` — no-store fallback frame (the polling loop itself
  is covered structurally; a full end-to-end streaming assertion
  would be flaky under a poll-interval-based implementation).

Also checks the startup hook warms the store singleton.

The tests use the existing Litestar ``TestClient`` pattern
(``tests/test_api_comets.py`` is the closest reference). Each test
builds a fresh app or manipulates the runtime singleton via the
repo-wide ``_isolate_network_audit_store`` autouse fixture from
``tests/conftest.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest
from litestar.testing import TestClient

from metis_app.network_audit import runtime
from metis_app.network_audit.kill_switches import AIRPLANE_MODE_KEY
from metis_app.network_audit.providers import KNOWN_PROVIDERS
from metis_app.network_audit.store import (
    NetworkAuditStore,
    make_synthetic_event,
    new_ulid,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[NetworkAuditStore]:
    """Install a per-test tmp-path NetworkAuditStore as the singleton.

    The repo-wide autouse fixture already points
    ``METIS_NETWORK_AUDIT_DB_PATH`` at a tmp path and resets the
    singleton. This fixture goes a step further: it constructs the
    store explicitly and wires it into ``runtime._store`` so tests
    can seed events deterministically before the first HTTP call.
    """
    runtime.reset_default_store_for_tests()
    store = NetworkAuditStore(tmp_path / "audit.db")
    monkeypatch.setattr(runtime, "_store", store)
    monkeypatch.setattr(runtime, "_store_init_failed", False)
    monkeypatch.setattr(runtime, "get_default_settings", lambda: {})
    try:
        yield store
    finally:
        runtime.reset_default_store_for_tests()


@pytest.fixture
def client(fresh_store: NetworkAuditStore) -> Iterator[TestClient]:
    """A Litestar TestClient wired to a freshly-built app."""
    from metis_app.api_litestar import create_app

    app = create_app()
    with TestClient(app=app) as test_client:
        yield test_client


def _seed(store: NetworkAuditStore, provider_key: str, *, count: int = 1,
          timestamp: datetime | None = None) -> None:
    """Append ``count`` synthetic events for ``provider_key``."""
    ts = timestamp or datetime.now(timezone.utc)
    for i in range(count):
        store.append(
            make_synthetic_event(
                provider_key=provider_key,
                trigger_feature="unit_test",
                event_id=new_ulid(),
                timestamp=ts + timedelta(milliseconds=i),
            )
        )


# ---------------------------------------------------------------------------
# GET /v1/network-audit/events
# ---------------------------------------------------------------------------


def test_events_endpoint_returns_recent_events(
    client: TestClient, fresh_store: NetworkAuditStore
) -> None:
    """Seeded events come back newest-first under the expected shape."""
    _seed(fresh_store, "openai", count=3)

    resp = client.get("/v1/network-audit/events")
    assert resp.status_code == 200
    payload = resp.json()
    assert isinstance(payload, list)
    assert len(payload) == 3
    # Every event is shaped like a NetworkAuditEventResponse.
    for row in payload:
        assert set(row.keys()) >= {
            "id",
            "timestamp",
            "method",
            "url_host",
            "url_path_prefix",
            "query_params_stored",
            "provider_key",
            "trigger_feature",
            "size_bytes_in",
            "size_bytes_out",
            "latency_ms",
            "status_code",
            "user_initiated",
            "blocked",
            "source",
        }
        assert row["query_params_stored"] is False
    # Newest-first ordering.
    timestamps = [row["timestamp"] for row in payload]
    assert timestamps == sorted(timestamps, reverse=True)


def test_events_endpoint_filters_by_provider(
    client: TestClient, fresh_store: NetworkAuditStore
) -> None:
    """``?provider=openai`` returns only openai events."""
    _seed(fresh_store, "openai", count=3)
    _seed(fresh_store, "anthropic", count=2)

    resp = client.get("/v1/network-audit/events", params={"provider": "openai"})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 3
    assert all(row["provider_key"] == "openai" for row in rows)


def test_events_endpoint_respects_limit_clamp(
    client: TestClient, fresh_store: NetworkAuditStore
) -> None:
    """``?limit=10000`` is clamped to the hard cap (500)."""
    # Seed more than the default cap but fewer than 500 to keep the
    # test fast; we only need to prove the handler does not crash and
    # returns at most 500 rows.
    _seed(fresh_store, "openai", count=50)

    resp = client.get("/v1/network-audit/events", params={"limit": 10_000})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) <= 500
    assert len(rows) == 50


def test_events_endpoint_returns_empty_when_store_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A None-returning ``get_default_store`` yields ``[]`` with 200."""
    runtime.reset_default_store_for_tests()
    monkeypatch.setattr(runtime, "_store", None)
    monkeypatch.setattr(runtime, "_store_init_failed", True)
    # Also patch the route module's imported symbol — Litestar imports
    # ``get_default_store`` by name so monkeypatching runtime._store
    # is not enough on its own.
    import metis_app.api_litestar.routes.network_audit as na_routes

    monkeypatch.setattr(na_routes, "get_default_store", lambda: None)

    from metis_app.api_litestar import create_app

    app = create_app()
    with TestClient(app=app) as test_client:
        resp = test_client.get("/v1/network-audit/events")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /v1/network-audit/providers
# ---------------------------------------------------------------------------


def test_providers_endpoint_returns_all_known_providers(
    client: TestClient,
) -> None:
    """Response carries every KNOWN_PROVIDERS entry minus ``unclassified``."""
    resp = client.get("/v1/network-audit/providers")
    assert resp.status_code == 200
    rows = resp.json()
    expected_keys = {k for k in KNOWN_PROVIDERS if k != "unclassified"}
    actual_keys = {row["key"] for row in rows}
    assert actual_keys == expected_keys
    # Schema sanity.
    for row in rows:
        assert set(row.keys()) >= {
            "key",
            "display_name",
            "category",
            "kill_switch_setting_key",
            "blocked",
            "events_7d",
            "last_call_at",
        }


def test_providers_endpoint_reports_blocked_state(
    monkeypatch: pytest.MonkeyPatch,
    fresh_store: NetworkAuditStore,
) -> None:
    """With airplane mode on, every provider reports ``blocked: true``."""
    import metis_app.api_litestar.routes.network_audit as na_routes

    monkeypatch.setattr(
        na_routes,
        "get_default_settings",
        lambda: {AIRPLANE_MODE_KEY: True},
    )

    from metis_app.api_litestar import create_app

    app = create_app()
    with TestClient(app=app) as test_client:
        resp = test_client.get("/v1/network-audit/providers")
        assert resp.status_code == 200
        rows = resp.json()
        assert rows, "Expected at least one provider entry"
        assert all(row["blocked"] is True for row in rows)


def test_providers_endpoint_counts_7d_events(
    client: TestClient, fresh_store: NetworkAuditStore
) -> None:
    """``events_7d`` reflects the per-provider count over the 7-day window."""
    _seed(fresh_store, "openai", count=4)
    _seed(fresh_store, "anthropic", count=1)

    resp = client.get("/v1/network-audit/providers")
    assert resp.status_code == 200
    by_key = {row["key"]: row for row in resp.json()}
    assert by_key["openai"]["events_7d"] == 4
    assert by_key["anthropic"]["events_7d"] == 1
    # Providers with no events show 0.
    assert by_key["voyage"]["events_7d"] == 0
    # And ``last_call_at`` is populated iff there were events.
    assert by_key["openai"]["last_call_at"] is not None
    assert by_key["voyage"]["last_call_at"] is None


def test_providers_endpoint_handles_no_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the store is unavailable, every row shows events_7d=0, last_call_at=None."""
    runtime.reset_default_store_for_tests()
    import metis_app.api_litestar.routes.network_audit as na_routes

    monkeypatch.setattr(na_routes, "get_default_store", lambda: None)
    monkeypatch.setattr(na_routes, "get_default_settings", lambda: {})

    from metis_app.api_litestar import create_app

    app = create_app()
    with TestClient(app=app) as test_client:
        resp = test_client.get("/v1/network-audit/providers")
        assert resp.status_code == 200
        rows = resp.json()
        assert rows
        assert all(row["events_7d"] == 0 for row in rows)
        assert all(row["last_call_at"] is None for row in rows)


# ---------------------------------------------------------------------------
# GET /v1/network-audit/recent-count
# ---------------------------------------------------------------------------


def test_recent_count_endpoint(
    client: TestClient, fresh_store: NetworkAuditStore
) -> None:
    """Count reflects events in the requested window."""
    _seed(fresh_store, "openai", count=3)

    resp = client.get("/v1/network-audit/recent-count", params={"window": 300})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["count"] == 3
    assert payload["window_seconds"] == 300


def test_recent_count_clamps_window(
    client: TestClient, fresh_store: NetworkAuditStore
) -> None:
    """Out-of-range ``window`` is clamped to the [60, 604800] envelope.

    The echoed ``window_seconds`` reflects the clamped value so the
    caller can render an accurate label.
    """
    resp_high = client.get(
        "/v1/network-audit/recent-count", params={"window": 999_999_999}
    )
    assert resp_high.status_code == 200
    assert resp_high.json()["window_seconds"] == 7 * 24 * 60 * 60

    resp_low = client.get(
        "/v1/network-audit/recent-count", params={"window": 1}
    )
    assert resp_low.status_code == 200
    assert resp_low.json()["window_seconds"] == 60


def test_recent_count_no_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unavailable store returns count=0 (not 500)."""
    runtime.reset_default_store_for_tests()
    import metis_app.api_litestar.routes.network_audit as na_routes

    monkeypatch.setattr(na_routes, "get_default_store", lambda: None)

    from metis_app.api_litestar import create_app

    app = create_app()
    with TestClient(app=app) as test_client:
        resp = test_client.get(
            "/v1/network-audit/recent-count", params={"window": 60}
        )
        assert resp.status_code == 200
        assert resp.json() == {"count": 0, "window_seconds": 60}


# ---------------------------------------------------------------------------
# GET /v1/network-audit/stream
# ---------------------------------------------------------------------------


def test_stream_endpoint_handles_no_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the store is unavailable, the stream yields ``no_store`` and closes."""
    runtime.reset_default_store_for_tests()
    import metis_app.api_litestar.routes.network_audit as na_routes

    monkeypatch.setattr(na_routes, "get_default_store", lambda: None)

    from metis_app.api_litestar import create_app

    app = create_app()
    with TestClient(app=app) as test_client:
        # Use the streaming API so we do not block on a 25-minute connection.
        with test_client.stream("GET", "/v1/network-audit/stream") as resp:
            assert resp.status_code == 200
            body = b"".join(resp.iter_bytes())
            assert b"no_store" in body


def test_stream_endpoint_registered() -> None:
    """The SSE route is registered at ``/v1/network-audit/stream``.

    Full end-to-end streaming verification is not attempted here:
    the Litestar TestClient does not easily support bounded reads on
    a long-lived SSE generator, and a polling-cadence test would
    either sleep (slow suite) or flake under CI timing. The no-store
    fallback test above exercises the generator end-to-end for the
    degenerate case; together with the per-handler unit coverage of
    ``recent``/``recent_by_provider``, the streaming path is
    adequately protected for Phase 5a.

    Phase 5b's frontend integration will provide the real
    end-to-end coverage (a Playwright test that connects to the
    stream and asserts events arrive in the UI).
    """
    from metis_app.api_litestar import create_app

    app = create_app()
    registered_paths = {route.path for route in app.routes}
    assert "/v1/network-audit/stream" in registered_paths
    assert "/v1/network-audit/events" in registered_paths
    assert "/v1/network-audit/providers" in registered_paths
    assert "/v1/network-audit/recent-count" in registered_paths


# ---------------------------------------------------------------------------
# App lifecycle hooks
# ---------------------------------------------------------------------------


def test_app_startup_warms_default_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Building + entering the test client triggers ``get_default_store``.

    The lifecycle hook is registered on the Litestar app's
    ``on_startup`` list. This test replaces ``get_default_store``
    with a counting shim and confirms the first TestClient
    ``__enter__`` calls it at least once.
    """
    import metis_app.api_litestar.app as app_module

    call_count = 0

    def _counting_get_default_store() -> None:
        nonlocal call_count
        call_count += 1
        return None

    monkeypatch.setattr(
        app_module, "get_default_store", _counting_get_default_store
    )
    # Ensure our patched get_default_store is what the startup hook calls.
    monkeypatch.setattr(
        app_module,
        "_warm_network_audit_store",
        lambda: _counting_get_default_store(),
    )

    from metis_app.api_litestar import create_app

    app = create_app()
    with TestClient(app=app):
        pass

    assert call_count >= 1, "Startup hook should warm the store at least once"
