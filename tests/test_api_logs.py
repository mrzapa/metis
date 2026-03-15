"""Tests for GET /v1/logs/tail and GET /v1/version endpoints."""

from __future__ import annotations

import pathlib
from importlib import import_module

from fastapi.testclient import TestClient

api_app_module = import_module("axiom_app.api.app")
logs_module = import_module("axiom_app.api.logs")


def _client() -> TestClient:
    return TestClient(api_app_module.create_app())


# ---------------------------------------------------------------------------
# GET /v1/version
# ---------------------------------------------------------------------------


def test_version_returns_200() -> None:
    response = _client().get("/v1/version")
    assert response.status_code == 200


def test_version_returns_string() -> None:
    data = _client().get("/v1/version").json()
    assert isinstance(data.get("version"), str)
    assert data["version"]  # non-empty


# ---------------------------------------------------------------------------
# GET /v1/logs/tail — missing log file
# ---------------------------------------------------------------------------


def test_log_tail_missing_file(monkeypatch, tmp_path) -> None:
    """When axiom.log does not exist, endpoint returns missing=True, empty lines."""
    monkeypatch.setattr(
        logs_module._store,
        "load_settings",
        lambda: {"log_dir": str(tmp_path)},
    )
    data = _client().get("/v1/logs/tail").json()
    assert data["missing"] is True
    assert data["lines"] == []


# ---------------------------------------------------------------------------
# GET /v1/logs/tail — log exists
# ---------------------------------------------------------------------------


def test_log_tail_returns_lines(monkeypatch, tmp_path) -> None:
    log_file = tmp_path / "axiom.log"
    log_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
    monkeypatch.setattr(
        logs_module._store,
        "load_settings",
        lambda: {"log_dir": str(tmp_path)},
    )
    data = _client().get("/v1/logs/tail").json()
    assert data["missing"] is False
    assert data["lines"] == ["line1", "line2", "line3"]


def test_log_tail_limits_to_200_lines(monkeypatch, tmp_path) -> None:
    log_file = tmp_path / "axiom.log"
    log_file.write_text("\n".join(f"line{i}" for i in range(300)), encoding="utf-8")
    monkeypatch.setattr(
        logs_module._store,
        "load_settings",
        lambda: {"log_dir": str(tmp_path)},
    )
    data = _client().get("/v1/logs/tail").json()
    assert len(data["lines"]) == 200
    assert data["total_lines"] == 300
    # Should be the last 200 lines
    assert data["lines"][0] == "line100"
    assert data["lines"][-1] == "line299"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def test_log_tail_redacts_api_key_assignment(monkeypatch, tmp_path) -> None:
    log_file = tmp_path / "axiom.log"
    log_file.write_text("api_key_anthropic = sk-ant-secret123\n", encoding="utf-8")
    monkeypatch.setattr(
        logs_module._store,
        "load_settings",
        lambda: {"log_dir": str(tmp_path)},
    )
    data = _client().get("/v1/logs/tail").json()
    assert "sk-ant-secret123" not in data["lines"][0]
    assert "[REDACTED]" in data["lines"][0]
    # Key name should be preserved
    assert "api_key_anthropic" in data["lines"][0]


def test_log_tail_redacts_bearer_token(monkeypatch, tmp_path) -> None:
    log_file = tmp_path / "axiom.log"
    log_file.write_text("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\n", encoding="utf-8")
    monkeypatch.setattr(
        logs_module._store,
        "load_settings",
        lambda: {"log_dir": str(tmp_path)},
    )
    data = _client().get("/v1/logs/tail").json()
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in data["lines"][0]
    assert "[REDACTED]" in data["lines"][0]


def test_log_tail_redacts_long_token(monkeypatch, tmp_path) -> None:
    secret = "a" * 32
    log_file = tmp_path / "axiom.log"
    log_file.write_text(f"some log message token={secret}\n", encoding="utf-8")
    monkeypatch.setattr(
        logs_module._store,
        "load_settings",
        lambda: {"log_dir": str(tmp_path)},
    )
    data = _client().get("/v1/logs/tail").json()
    assert secret not in data["lines"][0]
    assert "[REDACTED]" in data["lines"][0]


# ---------------------------------------------------------------------------
# Path safety — no query params accepted
# ---------------------------------------------------------------------------


def test_log_tail_no_path_param(monkeypatch, tmp_path) -> None:
    """Endpoint must not accept a path query parameter."""
    monkeypatch.setattr(
        logs_module._store,
        "load_settings",
        lambda: {"log_dir": str(tmp_path)},
    )
    # Passing an arbitrary path query param should be silently ignored (422 or 200 with safe path)
    response = _client().get("/v1/logs/tail?path=/etc/passwd")
    # FastAPI returns 422 for unexpected query params with strict models, or 200 ignoring it.
    # Either way the response must not contain /etc/passwd content.
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        for line in response.json().get("lines", []):
            assert "root:" not in line
