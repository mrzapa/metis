from __future__ import annotations

from importlib import import_module

from litestar.testing import TestClient


def _entry_payload() -> dict[str, object]:
    return {
        "entry_id": "improvement-1",
        "artifact_key": "idea:reflection:completed_run:session-1:run-1:mem-1",
        "artifact_type": "idea",
        "created_at": "2026-04-06T20:00:00Z",
        "updated_at": "2026-04-06T20:05:00Z",
        "title": "Research follow-up idea",
        "summary": "Turn the last reflection into a durable idea.",
        "body_md": "Inspect the run and propose a better next experiment.",
        "session_id": "session-1",
        "run_id": "run-1",
        "status": "draft",
        "tags": ["assistant_reflection", "completed_run"],
        "upstream_ids": ["source-1"],
        "metadata": {"origin": "assistant_reflection"},
        "slug": "research-follow-up-idea",
        "saved_at": "2026-04-06T20:05:00Z",
        "markdown_path": "C:/tmp/improvements/ideas/research-follow-up-idea.md",
    }


def test_improvement_routes_round_trip(monkeypatch) -> None:
    litestar_improvements = import_module("metis_app.api_litestar.routes.improvements")
    litestar_app = import_module("metis_app.api_litestar")

    captured: dict[str, object] = {}

    class _FakeOrchestrator:
        def list_improvement_entries(self, *, artifact_type: str = "", status: str = "", limit: int = 20):
            captured["list"] = (artifact_type, status, limit)
            return [_entry_payload()]

        def get_improvement_entry(self, entry_id: str):
            captured["get"] = entry_id
            if entry_id == "missing":
                return None
            return _entry_payload()

    monkeypatch.setattr(litestar_improvements, "WorkspaceOrchestrator", lambda: _FakeOrchestrator())

    with TestClient(app=litestar_app.create_app()) as client:
        lst = client.get(
            "/v1/improvements",
            params={"artifact_type": "idea", "status": "draft", "limit": 5},
        )
        assert lst.status_code == 200
        assert lst.json()[0]["entry_id"] == "improvement-1"

        got = client.get("/v1/improvements/improvement-1")
        assert got.status_code == 200

        missing = client.get("/v1/improvements/missing")
        assert missing.status_code == 404

    assert captured["list"] == ("idea", "draft", 5)
    assert captured["get"] == "missing"


def test_create_improvement_entry(monkeypatch) -> None:
    litestar_improvements = import_module("metis_app.api_litestar.routes.improvements")
    litestar_app = import_module("metis_app.api_litestar")

    created_payloads: list[dict] = []

    def _fake_upsert(payload: dict) -> dict:
        created_payloads.append(payload)
        return {
            **_entry_payload(),
            "artifact_type": payload["artifact_type"],
            "title": payload["title"],
            "artifact_key": payload.get("artifact_key", "idea:manual:test-hypothesis:abc12345"),
        }

    class _FakeOrchestrator:
        def upsert_improvement_entry(self, payload: dict) -> dict:
            return _fake_upsert(payload)

    monkeypatch.setattr(litestar_improvements, "WorkspaceOrchestrator", lambda: _FakeOrchestrator())

    body = {"artifact_type": "idea", "title": "Test Hypothesis"}

    with TestClient(app=litestar_app.create_app()) as client:
        resp = client.post("/v1/improvements", json=body)
        assert resp.status_code == 201
        data = resp.json()
        assert data["artifact_type"] == "idea"
        assert data["title"] == "Test Hypothesis"
        # auto-generated key must contain artifact_type and "manual"
        assert "idea" in data.get("artifact_key", "")
        assert "manual" in data.get("artifact_key", "")

    assert len(created_payloads) == 1
