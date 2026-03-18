from __future__ import annotations

import json
from importlib import import_module

from fastapi.testclient import TestClient

from axiom_app.services.stream_replay import ReplayableRunStreamManager, StreamReplayStore
from axiom_app.services.trace_store import TraceStore

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
            llm_provider = "mock"
            llm_model = "mock-model"

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


def _set_stream_manager(monkeypatch, tmp_path) -> None:
    manager = ReplayableRunStreamManager(StreamReplayStore(tmp_path / "traces"))
    monkeypatch.setattr(api_app_module, "_RAG_STREAM_MANAGER", manager)


def _parse_sse_frames(body: str) -> list[tuple[int | None, dict[str, object]]]:
    frames: list[tuple[int | None, dict[str, object]]] = []
    current_id: int | None = None
    current_payload: dict[str, object] | None = None
    for line in body.splitlines():
        if line.startswith("id: "):
            current_id = int(line[len("id: "):])
        elif line.startswith("data: "):
            current_payload = json.loads(line[len("data: "):])
        elif not line.strip() and current_payload is not None:
            frames.append((current_id, current_payload))
            current_id = None
            current_payload = None
    if current_payload is not None:
        frames.append((current_id, current_payload))
    return frames


def test_stream_rag_happy_path_includes_sse_ids(monkeypatch, tmp_path) -> None:
    _set_stream_manager(monkeypatch, tmp_path)
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
    frames = _parse_sse_frames(response.text)
    data_line_types = [
        json.loads(line[len("data: "):])["type"]
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]

    assert [frame_id for frame_id, _ in frames] == [1, 2, 3]
    assert [payload["type"] for _, payload in frames] == ["run_started", "token", "final"]
    assert data_line_types == ["run_started", "token", "final"]


def test_stream_rag_replays_only_events_after_last_event_id(monkeypatch, tmp_path) -> None:
    _set_stream_manager(monkeypatch, tmp_path)
    client = TestClient(api_app_module.create_app())

    def _fake_stream(req, cancel_token=None):
        yield {"type": "run_started", "run_id": "r1"}
        yield {"type": "token", "run_id": "r1", "text": "hello"}
        yield {"type": "final", "run_id": "r1", "answer_text": "hello", "sources": []}

    monkeypatch.setattr(api_app_module, "stream_rag_answer", _fake_stream)

    first = client.post(
        "/v1/query/rag/stream",
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "What is Axiom?",
            "run_id": "r1",
            "settings": {
                "llm_provider": "mock",
                "embedding_provider": "mock",
                "vector_db_type": "json",
            },
        },
    )
    assert first.status_code == 200

    replay = client.post(
        "/v1/query/rag/stream",
        headers={"Last-Event-ID": "1"},
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "What is Axiom?",
            "run_id": "r1",
            "settings": {
                "llm_provider": "mock",
                "embedding_provider": "mock",
                "vector_db_type": "json",
            },
        },
    )

    assert replay.status_code == 200
    replay_frames = _parse_sse_frames(replay.text)

    assert [frame_id for frame_id, _ in replay_frames] == [2, 3]
    assert [payload["type"] for _, payload in replay_frames] == ["token", "final"]


def test_stream_rag_reconnect_ignores_unrelated_trace_rows(monkeypatch, tmp_path) -> None:
    _set_stream_manager(monkeypatch, tmp_path)
    client = TestClient(api_app_module.create_app())

    TraceStore(tmp_path / "traces").append_event(
        run_id="run-with-trace-only",
        stage="synthesis",
        event_type="llm_response",
        payload={"response_preview": "trace-only"},
    )

    response = client.post(
        "/v1/query/rag/stream",
        headers={"Last-Event-ID": "1"},
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "What is Axiom?",
            "run_id": "run-with-trace-only",
            "settings": {
                "llm_provider": "mock",
                "embedding_provider": "mock",
                "vector_db_type": "json",
            },
        },
    )

    assert response.status_code == 200
    assert response.text == ""


def test_stream_rag_error_event(monkeypatch, tmp_path) -> None:
    _set_stream_manager(monkeypatch, tmp_path)
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
    frames = _parse_sse_frames(response.text)

    assert [frame_id for frame_id, _ in frames] == [1]
    assert [payload["type"] for _, payload in frames] == ["error"]


def test_brain_graph_returns_nodes_and_edges(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())

    monkeypatch.setattr(api_app_module, "list_indexes", lambda: [])

    class _FakeRepo:
        def init_db(self) -> None:
            pass

        def list_sessions(self, **_kwargs):  # type: ignore[override]
            return []

    import axiom_app.services.session_repository as _sr

    monkeypatch.setattr(_sr, "SessionRepository", lambda **_kw: _FakeRepo())

    response = client.get("/v1/brain/graph")

    assert response.status_code == 200
    payload = response.json()
    assert "nodes" in payload
    assert "edges" in payload
    # Root categories are always present
    node_ids = {n["node_id"] for n in payload["nodes"]}
    assert "category:brain" in node_ids
    assert "category:indexes" in node_ids
    assert "category:sessions" in node_ids
