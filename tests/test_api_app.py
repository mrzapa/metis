from __future__ import annotations

import json
from importlib import import_module

from fastapi.testclient import TestClient

api_app_module = import_module("axiom_app.api.app")


def test_healthz_returns_ok() -> None:
    client = TestClient(api_app_module.create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_query_direct_happy_path(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())

    def _fake_query_direct(req):
        class _Result:
            run_id = req.run_id or "run-xyz"
            answer_text = "Mock/Test Backend: hello"
            selected_mode = "Q&A"

        return _Result()

    monkeypatch.setattr(api_app_module, "query_direct", _fake_query_direct)

    response = client.post(
        "/v1/query/direct",
        json={
            "prompt": "Say hello",
            "settings": {"llm_provider": "mock", "selected_mode": "Q&A"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer_text"] == "Mock/Test Backend: hello"
    assert payload["selected_mode"] == "Q&A"
    assert payload["run_id"] == "run-xyz"


def test_stream_rag_happy_path(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())

    def _fake_stream(req, cancel_token=None):
        yield {"type": "run_started", "run_id": "r1"}
        yield {"type": "token", "run_id": "r1", "text": "hello"}
        yield {"type": "final", "run_id": "r1", "answer_text": "hello", "sources": []}

    monkeypatch.setattr(api_app_module, "stream_rag_answer", _fake_stream)

    response = client.post(
        "/v1/query/rag/stream",
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "What is Axiom?",
            "settings": {
                "llm_provider": "mock",
                "embedding_provider": "mock",
                "vector_db_type": "json",
            },
        },
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    event_types = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            event = json.loads(line[len("data: "):])
            event_types.append(event["type"])

    assert "run_started" in event_types
    assert "final" in event_types


def test_stream_rag_error_event(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())

    def _fake_stream(req, cancel_token=None):
        yield {"type": "error", "run_id": "r0", "message": "question must not be empty."}

    monkeypatch.setattr(api_app_module, "stream_rag_answer", _fake_stream)

    response = client.post(
        "/v1/query/rag/stream",
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "",
            "settings": {},
        },
    )

    assert response.status_code == 200
    data_lines = [l for l in response.text.splitlines() if l.startswith("data: ")]
    assert any(json.loads(l[6:])["type"] == "error" for l in data_lines)
