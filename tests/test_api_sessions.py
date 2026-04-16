"""Tests for the v1/sessions API routes."""

from __future__ import annotations

import json

import pytest
from litestar.testing import TestClient

from metis_app.api_litestar import create_app
from metis_app.api_litestar.routes import sessions as sessions_module
from metis_app.services.session_repository import SessionRepository
from metis_app.services.trace_store import TraceStore


@pytest.fixture
def repo(tmp_path):
    r = SessionRepository(db_path=tmp_path / "test_sessions.db")
    r.init_db()
    return r


@pytest.fixture
def client(repo, monkeypatch):
    monkeypatch.setattr(sessions_module, "get_session_repo", lambda: repo)
    app = create_app()
    with TestClient(app=app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /v1/sessions
# ---------------------------------------------------------------------------


def test_list_sessions_empty(client):
    r = client.get("/v1/sessions")
    assert r.status_code == 200
    assert r.json() == []


def test_list_sessions_returns_inserted_session(client, repo):
    repo.create_session(session_id="s1", title="Hello world")

    r = client.get("/v1/sessions")

    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["session_id"] == "s1"
    assert items[0]["title"] == "Hello world"
    assert isinstance(items[0]["extra"], dict)


def test_list_sessions_search_filter(client, repo):
    repo.create_session(session_id="s1", title="Alpha session")
    repo.create_session(session_id="s2", title="Beta session")

    r = client.get("/v1/sessions", params={"search": "alpha"})

    assert r.status_code == 200
    ids = [item["session_id"] for item in r.json()]
    assert ids == ["s1"]


def test_list_sessions_skill_filter(client, repo):
    skills_json = json.dumps(
        {"skills": {"selected": ["skill-a"], "primary": "skill-a", "reasons": {}}}
    )
    repo.create_session(session_id="s1", title="With skill", extra_json=skills_json)
    repo.create_session(session_id="s2", title="No skill")

    r = client.get("/v1/sessions", params={"skill": "skill-a"})

    assert r.status_code == 200
    ids = [item["session_id"] for item in r.json()]
    assert ids == ["s1"]


# ---------------------------------------------------------------------------
# GET /v1/sessions/{session_id}
# ---------------------------------------------------------------------------


def test_get_session_returns_detail(client, repo):
    repo.create_session(session_id="s1", title="My session")
    repo.append_message("s1", role="user", content="Hello?", run_id="run-1")

    r = client.get("/v1/sessions/s1")

    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["session_id"] == "s1"
    assert body["summary"]["title"] == "My session"
    assert len(body["messages"]) == 1
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][0]["content"] == "Hello?"
    assert body["messages"][0]["run_id"] == "run-1"


def test_get_session_not_found(client):
    r = client.get("/v1/sessions/nonexistent-id")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_get_session_includes_feedback(client, repo):
    repo.create_session(session_id="s1")
    repo.save_feedback("s1", run_id="run-1", vote=1, note="nice")

    r = client.get("/v1/sessions/s1")

    assert r.status_code == 200
    feedback = r.json()["feedback"]
    assert len(feedback) == 1
    assert feedback[0]["run_id"] == "run-1"
    assert feedback[0]["vote"] == 1
    assert feedback[0]["note"] == "nice"


def test_get_session_no_absolute_file_paths_in_sources(client, repo):
    from metis_app.models.session_types import EvidenceSource

    repo.create_session(session_id="s1")
    src = EvidenceSource(
        sid="ev1",
        source="doc.pdf",
        snippet="some text",
        file_path="/home/user/secret/doc.pdf",
    )
    repo.append_message("s1", role="assistant", content="Answer", sources=[src])

    r = client.get("/v1/sessions/s1")

    assert r.status_code == 200
    msg = r.json()["messages"][0]
    assert len(msg["sources"]) == 1
    assert "file_path" not in msg["sources"][0]


def test_get_session_hydrates_latest_nyx_action_result(client, repo, monkeypatch, tmp_path):
    trace_store = TraceStore(tmp_path / "traces")
    monkeypatch.setattr(sessions_module, "TraceStore", lambda: trace_store, raising=False)

    # The Litestar route uses hydrate_session_actions from metis_app.services.session_actions
    # which instantiates TraceStore() — patch at the source module.
    import metis_app.services.session_actions as sessions_src
    monkeypatch.setattr(sessions_src, "TraceStore", lambda: trace_store)

    repo.create_session(session_id="s1", title="Nyx session")
    repo.append_message(
        "s1",
        role="assistant",
        content="Use Glow Card.",
        run_id="run-nyx-action",
        artifacts=[
            {
                "id": "nyx_component_selection",
                "type": "nyx_component_selection",
                "summary": "Nyx matched 1 component candidate.",
                "payload": {
                    "selected_components": [
                        {"component_name": "glow-card", "title": "Glow Card"}
                    ]
                },
            }
        ],
        actions=[
            {
                "action_id": "nyx-install:abc123",
                "action_type": "nyx_install",
                "label": "Approve Nyx install proposal",
                "summary": "Approve installing Glow Card.",
                "requires_approval": True,
                "run_action_endpoint": "/v1/runs/run-nyx-action/actions",
                "payload": {
                    "action_id": "nyx-install:abc123",
                    "action_type": "nyx_install",
                    "proposal_token": "nyx-proposal:abc123",
                    "component_count": 1,
                    "component_names": ["glow-card"],
                },
                "proposal": {
                    "schema_version": "1.0",
                    "proposal_token": "nyx-proposal:abc123",
                    "source": "nyx_runtime",
                    "run_id": "run-nyx-action",
                    "query": "Design a glowing card.",
                    "intent_type": "interface_pattern_selection",
                    "matched_signals": ["pattern:card"],
                    "component_names": ["glow-card"],
                    "component_count": 1,
                    "components": [{"component_name": "glow-card", "title": "Glow Card"}],
                },
            }
        ],
    )
    trace_store.append_event(
        run_id="run-nyx-action",
        stage="action_required",
        event_type="nyx_install_action_submitted",
        payload={
            "approved": False,
            "action_id": "nyx-install:abc123",
            "action_type": "nyx_install",
            "proposal_token": "nyx-proposal:abc123",
            "component_names": ["glow-card"],
            "component_count": 1,
            "execution_status": "failed",
            "status": "error",
            "command": ["node", "scripts/add-nyx-component.mjs", "--", "glow-card"],
            "cwd": str(tmp_path),
            "package_script": "ui:add:nyx",
            "returncode": 9,
            "stdout_excerpt": "stale install output",
            "failure_code": "installer_error",
        },
    )
    trace_store.append_event(
        run_id="run-nyx-action",
        stage="action_required",
        event_type="nyx_install_action_submitted",
        payload={
            "approved": True,
            "action_id": "nyx-install:abc123",
            "action_type": "nyx_install",
            "proposal_token": "nyx-proposal:abc123",
            "component_names": ["glow-card"],
            "component_count": 1,
            "execution_status": "completed",
            "status": "success",
            "command": ["node", "scripts/add-nyx-component.mjs", "--", "glow-card"],
            "cwd": str(tmp_path),
            "package_script": "ui:add:nyx",
            "returncode": 0,
            "stdout_excerpt": "newest install output",
        },
    )

    r = client.get("/v1/sessions/s1")

    assert r.status_code == 200
    body = r.json()
    message = body["messages"][0]
    assert message["artifacts"][0]["type"] == "nyx_component_selection"
    assert message["actions"][0]["action_type"] == "nyx_install"
    assert message["action_result"]["execution_status"] == "completed"
    assert message["action_result"]["status"] == "success"
    assert message["action_result"]["proposal_token"] == "nyx-proposal:abc123"
    assert message["action_result"]["installer"]["returncode"] == 0
    assert message["action_result"]["installer"]["stdout_excerpt"] == "newest install output"
    assert not message["action_result"]["failure_code"]
    assert len(body["traces"]["run-nyx-action"]) == 2
    assert body["traces"]["run-nyx-action"][0]["event_type"] == "nyx_install_action_submitted"


# ---------------------------------------------------------------------------
# POST /v1/sessions
# ---------------------------------------------------------------------------


def test_create_session_returns_summary(client):
    r = client.post("/v1/sessions", json={"title": "My first chat"})

    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "My first chat"
    assert body["session_id"]


def test_create_session_appears_in_list(client):
    client.post("/v1/sessions", json={"title": "Auto session"})

    r = client.get("/v1/sessions")

    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["title"] == "Auto session"


def test_create_session_default_title(client):
    r = client.post("/v1/sessions", json={})

    assert r.status_code == 201
    assert r.json()["title"] == "New Chat"


# ---------------------------------------------------------------------------
# POST /v1/sessions/{session_id}/feedback
# ---------------------------------------------------------------------------


def test_submit_feedback_returns_ok(client, repo):
    repo.create_session(session_id="s1", title="Feedback test")

    r = client.post(
        "/v1/sessions/s1/feedback",
        json={"run_id": "run-1", "vote": 1, "note": "great answer"},
    )

    assert r.status_code in (200, 201)
    assert r.json() == {"ok": True}


def test_submit_feedback_persisted_in_db(client, repo):
    repo.create_session(session_id="s1")

    client.post(
        "/v1/sessions/s1/feedback",
        json={"run_id": "run-2", "vote": -1, "note": "wrong"},
    )

    detail = repo.get_session("s1")
    assert len(detail.feedback) == 1
    fb = detail.feedback[0]
    assert fb.run_id == "run-2"
    assert fb.vote == -1
    assert fb.note == "wrong"


def test_submit_feedback_no_note(client, repo):
    repo.create_session(session_id="s1")

    r = client.post(
        "/v1/sessions/s1/feedback",
        json={"run_id": "run-3", "vote": 1},
    )

    assert r.status_code in (200, 201)
    assert r.json()["ok"] is True
