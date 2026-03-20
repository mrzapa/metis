from __future__ import annotations

import json
from importlib import import_module
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from axiom_app.models.brain_graph import BrainGraph
from axiom_app.services.stream_replay import ReplayableRunStreamManager, StreamReplayStore
from axiom_app.services.trace_store import TraceStore

api_app_module = import_module("axiom_app.api.app")


def test_healthz_returns_ok() -> None:
    client = TestClient(api_app_module.create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_build_index_uses_orchestrator(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())
    captured: dict[str, object] = {}

    class _Result:
        manifest_path = "/tmp/index/manifest.json"
        index_id = "idx-new"
        document_count = 3
        chunk_count = 9
        embedding_signature = "sig-1"
        vector_backend = "json"

    fake_orchestrator = MagicMock()

    def _fake_build_index(document_paths, settings, *, index_id=None, progress_cb=None):
        captured["document_paths"] = document_paths
        captured["settings"] = settings
        captured["index_id"] = index_id
        captured["progress_cb"] = progress_cb
        return _Result()

    fake_orchestrator.build_index.side_effect = _fake_build_index
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

    response = client.post(
        "/v1/index/build",
        json={
            "document_paths": ["/tmp/doc-1.txt", "/tmp/doc-2.txt"],
            "settings": {"llm_provider": "mock"},
            "index_id": "idx-new",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["index_id"] == "idx-new"
    assert payload["manifest_path"] == "/tmp/index/manifest.json"
    assert captured == {
        "document_paths": ["/tmp/doc-1.txt", "/tmp/doc-2.txt"],
        "settings": {"llm_provider": "mock"},
        "index_id": "idx-new",
        "progress_cb": None,
    }
    assert fake_orchestrator.build_index.call_count == 1


def test_stream_build_index_uses_orchestrator_and_progress_callback(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())
    captured: dict[str, object] = {}

    class _Result:
        manifest_path = "/tmp/index/manifest.json"
        index_id = "idx-stream"
        document_count = 4
        chunk_count = 12
        embedding_signature = "sig-stream"
        vector_backend = "json"

    fake_orchestrator = MagicMock()

    def _fake_build_index(document_paths, settings, *, index_id=None, progress_cb=None):
        captured["document_paths"] = document_paths
        captured["settings"] = settings
        captured["index_id"] = index_id
        captured["progress_cb"] = progress_cb
        if progress_cb is not None:
            progress_cb({"type": "progress", "run_id": "idx-stream", "percent": 50})
        return _Result()

    fake_orchestrator.build_index.side_effect = _fake_build_index
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

    response = client.post(
        "/v1/index/build/stream",
        json={
            "document_paths": ["/tmp/doc-1.txt"],
            "settings": {"llm_provider": "mock"},
            "index_id": "idx-stream",
        },
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    frames = _parse_sse_frames(response.text)
    assert [payload["type"] for _, payload in frames] == [
        "build_started",
        "progress",
        "build_complete",
    ]
    assert captured["document_paths"] == ["/tmp/doc-1.txt"]
    assert captured["settings"] == {"llm_provider": "mock"}
    assert captured["index_id"] == "idx-stream"
    assert callable(captured["progress_cb"])
    assert fake_orchestrator.build_index.call_count == 1


def test_query_direct_happy_path(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())
    captured: dict[str, object] = {}

    class _Result:
        run_id = "run-xyz"
        answer_text = "Mock/Test Backend: hello"
        selected_mode = "Q&A"
        llm_provider = "mock"
        llm_model = "mock-model"

    fake_orchestrator = MagicMock()

    def _fake_run_direct_query(req, *, session_id=""):
        captured["prompt"] = req.prompt
        captured["session_id"] = session_id
        return _Result()

    fake_orchestrator.run_direct_query.side_effect = _fake_run_direct_query
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

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
    assert captured == {"prompt": "Say hello", "session_id": ""}


def test_query_rag_forwards_session_id_to_orchestrator(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())
    captured: dict[str, object] = {}

    class _Result:
        run_id = "run-rag"
        answer_text = "rag answer"
        sources: list[dict[str, object]] = []
        context_block = "context"
        top_score = 0.42
        selected_mode = "Q&A"
        retrieval_plan = {}
        fallback = {}

    fake_orchestrator = MagicMock()

    def _fake_run_rag_query(req, *, session_id=""):
        captured["question"] = req.question
        captured["session_id"] = session_id
        return _Result()

    fake_orchestrator.run_rag_query.side_effect = _fake_run_rag_query
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

    response = client.post(
        "/v1/query/rag",
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "What is Axiom?",
            "session_id": "s1",
            "settings": {"llm_provider": "mock", "selected_mode": "Q&A"},
        },
    )

    assert response.status_code == 200
    assert captured["question"] == "What is Axiom?"
    assert captured["session_id"] == "s1"
    assert fake_orchestrator.run_rag_query.call_count == 1


def test_query_rag_serializes_retrieval_plan_and_fallback(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())

    class _Result:
        run_id = "run-rag-plan"
        answer_text = "rag answer"
        sources: list[dict[str, object]] = []
        context_block = "context"
        top_score = 0.42
        selected_mode = "Q&A"
        retrieval_plan = {"stages": [{"stage_type": "retrieval_complete", "payload": {}}]}
        fallback = {"triggered": False, "strategy": "synthesize_anyway"}

    fake_orchestrator = MagicMock()
    fake_orchestrator.run_rag_query.return_value = _Result()
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

    response = client.post(
        "/v1/query/rag",
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "What is Axiom?",
            "settings": {"llm_provider": "mock", "selected_mode": "Q&A"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["retrieval_plan"]["stages"][0]["stage_type"] == "retrieval_complete"
    assert payload["fallback"]["strategy"] == "synthesize_anyway"


def test_search_knowledge_forwards_session_id_to_orchestrator(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())
    captured: dict[str, object] = {}

    class _Result:
        run_id = "run-search"
        summary_text = "Found 2 passages."
        sources = [{"sid": "S1", "source": "doc", "snippet": "evidence"}]
        context_block = "context"
        top_score = 0.81
        selected_mode = "Knowledge Search"
        retrieval_plan = {"stages": [{"stage_type": "retrieval_complete", "payload": {}}]}
        fallback = {"triggered": False, "strategy": "synthesize_anyway"}

    fake_orchestrator = MagicMock()

    def _fake_run_knowledge_search(req, *, session_id=""):
        captured["question"] = req.question
        captured["session_id"] = session_id
        return _Result()

    fake_orchestrator.run_knowledge_search.side_effect = _fake_run_knowledge_search
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

    response = client.post(
        "/v1/search/knowledge",
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "Find evidence",
            "session_id": "s-search",
            "settings": {"llm_provider": "mock", "selected_mode": "Knowledge Search"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary_text"] == "Found 2 passages."
    assert payload["retrieval_plan"]["stages"][0]["stage_type"] == "retrieval_complete"
    assert payload["fallback"]["strategy"] == "synthesize_anyway"
    assert captured == {"question": "Find evidence", "session_id": "s-search"}


def test_query_direct_forwards_session_id_to_orchestrator(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())
    captured: dict[str, object] = {}

    class _Result:
        run_id = "run-direct"
        answer_text = "direct answer"
        selected_mode = "Tutor"
        llm_provider = "mock"
        llm_model = "mock-model"

    fake_orchestrator = MagicMock()

    def _fake_run_direct_query(req, *, session_id=""):
        captured["prompt"] = req.prompt
        captured["session_id"] = session_id
        return _Result()

    fake_orchestrator.run_direct_query.side_effect = _fake_run_direct_query
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

    response = client.post(
        "/v1/query/direct",
        json={
            "prompt": "Say hello",
            "session_id": "s2",
            "settings": {"llm_provider": "mock", "selected_mode": "Tutor"},
        },
    )

    assert response.status_code == 200
    assert captured["prompt"] == "Say hello"
    assert captured["session_id"] == "s2"
    assert fake_orchestrator.run_direct_query.call_count == 1


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
    fake_orchestrator = MagicMock()

    def _fake_stream_rag_query(req, *, session_id=""):
        yield {"type": "run_started", "run_id": "r1"}
        yield {"type": "token", "run_id": "r1", "text": "hello"}
        yield {"type": "final", "run_id": "r1", "answer_text": "hello", "sources": []}

    fake_orchestrator.stream_rag_query.side_effect = _fake_stream_rag_query
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

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
    fake_orchestrator = MagicMock()

    def _fake_stream_rag_query(req, *, session_id=""):
        yield {"type": "run_started", "run_id": "r1"}
        yield {"type": "token", "run_id": "r1", "text": "hello"}
        yield {"type": "final", "run_id": "r1", "answer_text": "hello", "sources": []}

    fake_orchestrator.stream_rag_query.side_effect = _fake_stream_rag_query
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

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
    fake_orchestrator = MagicMock()
    fake_orchestrator.stream_rag_query.return_value = iter(())
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

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
    fake_orchestrator = MagicMock()

    def _fake_stream_rag_query(req, *, session_id=""):
        yield {"type": "error", "run_id": "r0", "message": "question must not be empty."}

    fake_orchestrator.stream_rag_query.side_effect = _fake_stream_rag_query
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

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
    fake_orchestrator = MagicMock()
    fake_orchestrator.get_workspace_graph.return_value = BrainGraph().build_from_indexes_and_sessions([], [])
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

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


def test_brain_graph_preserves_assistant_node_types_and_scope_metadata(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())
    fake_orchestrator = MagicMock()
    fake_orchestrator.get_workspace_graph.return_value = BrainGraph().build_from_indexes_and_sessions(
        [],
        [],
        {
            "identity": {
                "assistant_id": "axiom-companion",
                "name": "Guide",
                "companion_enabled": True,
            },
            "status": {
                "runtime_provider": "local_gguf",
                "runtime_model": "axiom-q4",
                "paused": False,
            },
            "memory": [
                {
                    "entry_id": "memory-1",
                    "title": "Learned from a completed run",
                    "summary": "Captured a short next step.",
                    "confidence": 0.9,
                }
            ],
            "playbooks": [
                {
                    "playbook_id": "playbook-1",
                    "title": "Follow-up pattern",
                    "bullets": ["Lead with the next step."],
                    "confidence": 0.8,
                }
            ],
            "brain_links": [
                {
                    "source_node_id": "memory:memory-1",
                    "target_node_id": "assistant:axiom",
                    "relation": "belongs_to",
                    "summary": "Captured a short next step.",
                    "confidence": 0.9,
                    "metadata": {"scope": "assistant_learned", "note": "derived"},
                }
            ],
        },
    )
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

    response = client.get("/v1/brain/graph")

    assert response.status_code == 200
    payload = response.json()
    nodes = {node["node_id"]: node for node in payload["nodes"]}
    edges = {
        (edge["source_id"], edge["target_id"], edge["edge_type"]): edge for edge in payload["edges"]
    }

    assert nodes["category:brain"]["metadata"]["scope"] == "workspace"
    assert nodes["category:assistant"]["node_type"] == "category"
    assert nodes["category:assistant"]["metadata"]["scope"] == "assistant_self"
    assert nodes["assistant:axiom"]["node_type"] == "assistant"
    assert nodes["assistant:axiom"]["metadata"]["scope"] == "assistant_self"
    assert nodes["memory:memory-1"]["node_type"] == "memory"
    assert nodes["memory:memory-1"]["metadata"]["scope"] == "assistant_learned"
    assert nodes["playbook:playbook-1"]["node_type"] == "playbook"
    assert nodes["playbook:playbook-1"]["metadata"]["scope"] == "assistant_self"
    assert nodes["category:assistant:memory"]["metadata"]["scope"] == "assistant_self"
    assert nodes["category:assistant:playbooks"]["metadata"]["scope"] == "assistant_self"
    assert edges[("category:assistant", "category:brain", "category_member")]["metadata"]["scope"] == "assistant_self"
    assert edges[("memory:memory-1", "assistant:axiom", "belongs_to")]["metadata"]["scope"] == "assistant_learned"
    assert edges[("memory:memory-1", "assistant:axiom", "belongs_to")]["metadata"]["note"] == "derived"
