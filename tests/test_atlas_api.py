from __future__ import annotations

from importlib import import_module

from litestar.testing import TestClient


def _candidate_payload(status: str = "candidate") -> dict[str, object]:
    return {
        "entry_id": "atlas-1",
        "created_at": "2026-04-06T20:00:00Z",
        "updated_at": "2026-04-06T20:05:00Z",
        "session_id": "session-1",
        "run_id": "run-1",
        "title": "How does METIS stay grounded?",
        "summary": "METIS stays grounded by keeping cited evidence in view.",
        "body_md": "METIS keeps cited evidence in view.",
        "sources": [{"sid": "S1", "source": "doc.txt", "snippet": "evidence"}],
        "mode": "Research",
        "index_id": "idx-1",
        "top_score": 0.88,
        "source_count": 1,
        "confidence": 0.77,
        "rationale": "Strong grounded answer.",
        "slug": "how-does-metis-stay-grounded",
        "status": status,
        "saved_at": "2026-04-06T20:05:00Z" if status == "saved" else "",
        "markdown_path": "C:/tmp/atlas/entries/how-does-metis-stay-grounded.md" if status == "saved" else "",
    }


def test_atlas_routes_round_trip(monkeypatch) -> None:
    litestar_atlas = import_module("metis_app.api_litestar.routes.atlas")
    litestar_app = import_module("metis_app.api_litestar")

    captured: dict[str, object] = {}

    class _FakeOrchestrator:
        def get_atlas_candidate(self, *, session_id: str, run_id: str):
            captured["candidate"] = (session_id, run_id)
            return _candidate_payload()

        def save_atlas_entry(self, *, session_id: str, run_id: str, title=None, summary=None):
            captured["save"] = (session_id, run_id, title, summary)
            payload = _candidate_payload("saved")
            payload["title"] = title or payload["title"]
            payload["summary"] = summary or payload["summary"]
            return payload

        def decide_atlas_candidate(self, *, session_id: str, run_id: str, decision: str):
            captured["decision"] = (session_id, run_id, decision)
            return _candidate_payload(decision)

        def list_atlas_entries(self, *, limit: int = 20):
            captured["list"] = limit
            return [_candidate_payload("saved")]

    monkeypatch.setattr(litestar_atlas, "WorkspaceOrchestrator", lambda: _FakeOrchestrator())

    with TestClient(app=litestar_app.create_app()) as client:
        candidate = client.get(
            "/v1/atlas/candidate", params={"session_id": "session-1", "run_id": "run-1"}
        )
        assert candidate.status_code == 200
        assert candidate.json()["entry_id"] == "atlas-1"

        save = client.post(
            "/v1/atlas/save",
            json={
                "session_id": "session-1",
                "run_id": "run-1",
                "title": "Save this",
                "summary": "Atlas summary",
            },
        )
        assert save.status_code == 200
        assert save.json()["status"] == "saved"

        decision = client.post(
            "/v1/atlas/decision",
            json={"session_id": "session-1", "run_id": "run-1", "decision": "declined"},
        )
        assert decision.status_code == 200
        assert decision.json()["status"] == "declined"

        entries = client.get("/v1/atlas/entries", params={"limit": 5})
        assert entries.status_code == 200
        assert len(entries.json()) == 1

    assert captured["candidate"] == ("session-1", "run-1")
    assert captured["save"] == ("session-1", "run-1", "Save this", "Atlas summary")
    assert captured["decision"] == ("session-1", "run-1", "declined")
    assert captured["list"] == 5
