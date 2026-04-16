"""Tests for GET /v1/logs/tail and GET /v1/logs/metrics endpoints."""

from __future__ import annotations

from importlib import import_module

from litestar.testing import TestClient

litestar_app = import_module("metis_app.api_litestar")
logs_module = import_module("metis_app.api_litestar.routes.logs")


def _client() -> TestClient:
    return TestClient(app=litestar_app.create_app())


# ---------------------------------------------------------------------------
# GET /v1/version
# ---------------------------------------------------------------------------


def test_version_returns_200() -> None:
    with _client() as c:
        response = c.get("/v1/version")
        assert response.status_code == 200


def test_version_returns_string() -> None:
    with _client() as c:
        data = c.get("/v1/version").json()
        assert isinstance(data.get("version"), str)
        assert data["version"]  # non-empty


# ---------------------------------------------------------------------------
# GET /v1/logs/tail — missing log file
# ---------------------------------------------------------------------------


def test_log_tail_missing_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        logs_module._store,
        "load_settings",
        lambda: {"log_dir": str(tmp_path)},
    )
    with _client() as c:
        data = c.get("/v1/logs/tail").json()
        assert data["missing"] is True
        assert data["lines"] == []


# ---------------------------------------------------------------------------
# GET /v1/logs/tail — log exists
# ---------------------------------------------------------------------------


def test_log_tail_returns_lines(monkeypatch, tmp_path) -> None:
    log_file = tmp_path / "metis.log"
    log_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
    monkeypatch.setattr(
        logs_module._store,
        "load_settings",
        lambda: {"log_dir": str(tmp_path)},
    )
    with _client() as c:
        data = c.get("/v1/logs/tail").json()
        assert data["missing"] is False
        assert data["lines"] == ["line1", "line2", "line3"]


def test_log_tail_limits_to_200_lines(monkeypatch, tmp_path) -> None:
    log_file = tmp_path / "metis.log"
    log_file.write_text("\n".join(f"line{i}" for i in range(300)), encoding="utf-8")
    monkeypatch.setattr(
        logs_module._store,
        "load_settings",
        lambda: {"log_dir": str(tmp_path)},
    )
    with _client() as c:
        data = c.get("/v1/logs/tail").json()
        assert len(data["lines"]) == 200
        assert data["total_lines"] == 300
        assert data["lines"][0] == "line100"
        assert data["lines"][-1] == "line299"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def test_log_tail_redacts_api_key_assignment(monkeypatch, tmp_path) -> None:
    log_file = tmp_path / "metis.log"
    log_file.write_text("api_key_anthropic = sk-ant-secret123\n", encoding="utf-8")
    monkeypatch.setattr(
        logs_module._store,
        "load_settings",
        lambda: {"log_dir": str(tmp_path)},
    )
    with _client() as c:
        data = c.get("/v1/logs/tail").json()
        assert "sk-ant-secret123" not in data["lines"][0]
        assert "[REDACTED]" in data["lines"][0]
        assert "api_key_anthropic" in data["lines"][0]


def test_log_tail_redacts_bearer_token(monkeypatch, tmp_path) -> None:
    log_file = tmp_path / "metis.log"
    log_file.write_text("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\n", encoding="utf-8")
    monkeypatch.setattr(
        logs_module._store,
        "load_settings",
        lambda: {"log_dir": str(tmp_path)},
    )
    with _client() as c:
        data = c.get("/v1/logs/tail").json()
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in data["lines"][0]
        assert "[REDACTED]" in data["lines"][0]


def test_log_tail_redacts_long_token(monkeypatch, tmp_path) -> None:
    secret = "a" * 32
    log_file = tmp_path / "metis.log"
    log_file.write_text(f"some log message token={secret}\n", encoding="utf-8")
    monkeypatch.setattr(
        logs_module._store,
        "load_settings",
        lambda: {"log_dir": str(tmp_path)},
    )
    with _client() as c:
        data = c.get("/v1/logs/tail").json()
        assert secret not in data["lines"][0]
        assert "[REDACTED]" in data["lines"][0]


# ---------------------------------------------------------------------------
# Path safety — no query params accepted
# ---------------------------------------------------------------------------


def test_log_tail_no_path_param(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        logs_module._store,
        "load_settings",
        lambda: {"log_dir": str(tmp_path)},
    )
    with _client() as c:
        response = c.get("/v1/logs/tail?path=/etc/passwd")
        assert response.status_code in (200, 400, 422)
        if response.status_code == 200:
            for line in response.json().get("lines", []):
                assert "root:" not in line


# ---------------------------------------------------------------------------
# GET /v1/logs/metrics
# ---------------------------------------------------------------------------


def _make_stub_trace_store(tmp_path):
    from metis_app.services.trace_store import TraceStore as _RealStore

    stub = _RealStore(tmp_path)
    stub.append_event(run_id="r1", stage="synthesis", event_type="final", payload={"status": "success"})
    stub.append_event(run_id="r1", stage="retrieval", event_type="run_started", payload={})
    return stub


class TestLogsMetrics:
    def test_metrics_returns_200(self, monkeypatch, tmp_path) -> None:
        stub = _make_stub_trace_store(tmp_path)
        monkeypatch.setattr(logs_module, "TraceStore", lambda: stub)

        with _client() as c:
            response = c.get("/v1/logs/metrics")
            assert response.status_code == 200

    def test_metrics_response_has_required_keys(self, monkeypatch, tmp_path) -> None:
        stub = _make_stub_trace_store(tmp_path)
        monkeypatch.setattr(logs_module, "TraceStore", lambda: stub)

        with _client() as c:
            data = c.get("/v1/logs/metrics").json()
        for key in ("total_events", "event_type_counts", "status_counts", "duration_ms", "last_run_id"):
            assert key in data, f"missing key: {key}"

    def test_metrics_event_type_counts_are_correct(self, monkeypatch, tmp_path) -> None:
        stub = _make_stub_trace_store(tmp_path)
        monkeypatch.setattr(logs_module, "TraceStore", lambda: stub)

        with _client() as c:
            data = c.get("/v1/logs/metrics").json()
        assert data["total_events"] == 2
        assert data["event_type_counts"].get("final") == 1
        assert data["event_type_counts"].get("run_started") == 1

    def test_metrics_status_counts_are_correct(self, monkeypatch, tmp_path) -> None:
        stub = _make_stub_trace_store(tmp_path)
        monkeypatch.setattr(logs_module, "TraceStore", lambda: stub)

        with _client() as c:
            data = c.get("/v1/logs/metrics").json()
        assert data["status_counts"].get("success") == 1

    def test_metrics_duration_ms_structure(self, monkeypatch, tmp_path) -> None:
        stub = _make_stub_trace_store(tmp_path)
        monkeypatch.setattr(logs_module, "TraceStore", lambda: stub)

        with _client() as c:
            data = c.get("/v1/logs/metrics").json()
        dur = data["duration_ms"]
        for key in ("count", "total_ms", "avg_ms", "min_ms", "max_ms"):
            assert key in dur, f"duration_ms missing key: {key}"

    def test_metrics_empty_store(self, monkeypatch, tmp_path) -> None:
        from metis_app.services.trace_store import TraceStore as _RealStore

        empty_store = _RealStore(tmp_path)
        monkeypatch.setattr(logs_module, "TraceStore", lambda: empty_store)

        with _client() as c:
            data = c.get("/v1/logs/metrics").json()
        assert data["total_events"] == 0
        assert data["event_type_counts"] == {}
        assert data["last_run_id"] is None

    def test_metrics_does_not_break_log_tail(self, monkeypatch, tmp_path) -> None:
        log_file = tmp_path / "metis.log"
        log_file.write_text("line1\nline2\n", encoding="utf-8")
        monkeypatch.setattr(logs_module._store, "load_settings", lambda: {"log_dir": str(tmp_path)})

        with _client() as c:
            tail_data = c.get("/v1/logs/tail").json()
        assert tail_data["missing"] is False
        assert "line1" in tail_data["lines"]
        assert "line2" in tail_data["lines"]

    def test_metrics_response_is_json_serializable(self, monkeypatch, tmp_path) -> None:
        import json as _json

        stub = _make_stub_trace_store(tmp_path)
        monkeypatch.setattr(logs_module, "TraceStore", lambda: stub)

        with _client() as c:
            data = c.get("/v1/logs/metrics").json()
        _json.dumps(data)
