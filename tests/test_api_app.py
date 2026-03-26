from __future__ import annotations

import json
from importlib import import_module
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from metis_app.models.brain_graph import BrainGraph
from metis_app.services.stream_replay import ReplayableRunStreamManager, StreamReplayStore
from metis_app.services.trace_store import TraceStore

api_app_module = import_module("metis_app.api.app")


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
            "question": "What is METIS?",
            "session_id": "s1",
            "settings": {"llm_provider": "mock", "selected_mode": "Q&A"},
        },
    )

    assert response.status_code == 200
    assert captured["question"] == "What is METIS?"
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
            "question": "What is METIS?",
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
            "question": "What is METIS?",
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
    run_started = frames[0][1]
    assert run_started["event_type"] == "run_started"
    assert str(run_started["event_id"]).endswith(":1")
    assert run_started["timestamp"]
    assert run_started["status"] == "started"
    assert run_started["lifecycle"] == "run"
    assert run_started["context"]["run_id"] == run_started["run_id"]
    assert isinstance(run_started["payload"], dict)


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
            "question": "What is METIS?",
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
            "question": "What is METIS?",
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
            "question": "What is METIS?",
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


def test_ui_telemetry_endpoint_accepts_valid_events(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())
    captured: dict[str, object] = {}

    class _FakeOrchestrator:
        def ingest_ui_telemetry_events(self, events):
            captured["events"] = events
            return len(events)

    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: _FakeOrchestrator())

    response = client.post(
        "/v1/telemetry/ui",
        json={
            "events": [
                {
                    "event_name": "artifact_render_success",
                    "source": "chat_artifact_boundary",
                    "occurred_at": "2026-03-23T12:00:00Z",
                    "run_id": "run-telemetry",
                    "session_id": "session-1",
                    "message_id": "message-1",
                    "is_streaming": False,
                    "payload": {
                        "artifact_count": 1,
                        "artifact_types": ["timeline"],
                        "artifact_ids": ["artifact-1"],
                        "renderer": "default",
                    },
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": 1}
    persisted = captured["events"]
    assert isinstance(persisted, list)
    assert persisted[0]["event_name"] == "artifact_render_success"
    assert persisted[0]["payload"]["artifact_types"] == ["timeline"]


def test_ui_telemetry_endpoint_rejects_invalid_payload(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())
    fake_orchestrator = MagicMock()
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

    response = client.post(
        "/v1/telemetry/ui",
        json={
            "events": [
                {
                    "event_name": "artifact_render_success",
                    "source": "chat_artifact_boundary",
                    "occurred_at": "2026-03-23T12:00:00Z",
                    "run_id": "run-telemetry",
                    "payload": {
                        "artifact_count": 1,
                        "artifact_types": ["timeline"],
                        "artifact_ids": ["artifact-1"],
                        "renderer": "default",
                        "unexpected": True,
                    },
                }
            ]
        },
    )

    assert response.status_code == 422
    fake_orchestrator.ingest_ui_telemetry_events.assert_not_called()


def test_ui_telemetry_endpoint_accepts_runtime_lifecycle_events(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())
    captured: dict[str, object] = {}

    class _FakeOrchestrator:
        def ingest_ui_telemetry_events(self, events):
            captured["events"] = events
            return len(events)

    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: _FakeOrchestrator())

    response = client.post(
        "/v1/telemetry/ui",
        json={
            "events": [
                {
                    "event_name": "artifact_runtime_attempt",
                    "source": "chat_artifact_boundary",
                    "occurred_at": "2026-03-23T12:00:00Z",
                    "run_id": "run-telemetry",
                    "payload": {
                        "artifact_index": 0,
                        "artifact_id": "artifact-1",
                        "artifact_type": "timeline",
                    },
                },
                {
                    "event_name": "artifact_runtime_skipped",
                    "source": "chat_artifact_boundary",
                    "occurred_at": "2026-03-23T12:00:01Z",
                    "run_id": "run-telemetry",
                    "payload": {
                        "artifact_index": 1,
                        "artifact_type": "metric_cards",
                        "reason": "runtime_disabled",
                    },
                },
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": 2}
    persisted = captured["events"]
    assert isinstance(persisted, list)
    assert persisted[0]["event_name"] == "artifact_runtime_attempt"
    assert persisted[1]["event_name"] == "artifact_runtime_skipped"


def test_ui_telemetry_endpoint_rejects_malformed_json() -> None:
    client = TestClient(api_app_module.create_app())

    response = client.post(
        "/v1/telemetry/ui",
        content='{"events": [',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400


def test_ui_telemetry_endpoint_requires_auth_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("METIS_API_TOKEN", "secret-token")
    client = TestClient(api_app_module.create_app())

    response = client.post(
        "/v1/telemetry/ui",
        json={
            "events": [
                {
                    "event_name": "artifact_boundary_flag_state",
                    "source": "chat_artifact_boundary",
                    "occurred_at": "2026-03-23T12:00:00Z",
                    "run_id": "run-telemetry",
                    "payload": {"state": "enabled"},
                }
            ]
        },
    )

    assert response.status_code == 401


def test_ui_telemetry_endpoint_accepts_auth_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("METIS_API_TOKEN", "secret-token")
    client = TestClient(api_app_module.create_app())
    captured: dict[str, object] = {}

    class _FakeOrchestrator:
        def ingest_ui_telemetry_events(self, events):
            captured["events"] = events
            return len(events)

    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: _FakeOrchestrator())

    response = client.post(
        "/v1/telemetry/ui",
        headers={"Authorization": "Bearer secret-token"},
        json={
            "events": [
                {
                    "event_name": "artifact_boundary_flag_state",
                    "source": "chat_artifact_boundary",
                    "occurred_at": "2026-03-23T12:00:00Z",
                    "run_id": "run-telemetry",
                    "payload": {"state": "enabled"},
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": 1}
    persisted = captured["events"]
    assert isinstance(persisted, list)
    assert persisted[0]["event_name"] == "artifact_boundary_flag_state"


def test_ui_telemetry_endpoint_rejects_oversized_request() -> None:
    client = TestClient(api_app_module.create_app())
    response = client.post(
        "/v1/telemetry/ui",
        content="x" * 20_000,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413


def test_ui_telemetry_summary_endpoint_returns_structured_summary(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())

    class _FakeOrchestrator:
        def get_ui_telemetry_summary(self, *, window_hours=24, limit=50_000):
            assert window_hours == 24
            assert limit == 999
            return {
                "window_hours": 24,
                "generated_at": "2026-03-23T12:00:00+00:00",
                "sampled_event_count": 12,
                "metrics": {
                    "exposure_count": 10,
                    "render_attempt_count": 10,
                    "render_success_rate": 0.9,
                    "render_failure_rate": 0.1,
                    "fallback_rate_by_reason": {
                        "feature_disabled": 0.0,
                        "no_artifacts": 0.0,
                        "invalid_payload": 0.1,
                        "render_error": 0.0,
                    },
                    "interaction_rate": 0.2,
                    "runtime_attempt_rate": 0.5,
                    "runtime_success_rate": 0.8,
                    "runtime_failure_rate": 0.2,
                    "runtime_skip_mix": {
                        "runtime_disabled": 0.5,
                        "unsupported_type": 0.5,
                        "payload_truncated": 0.0,
                        "invalid_payload": 0.0,
                    },
                    "data_quality": {
                        "events_with_run_id_pct": 99.0,
                        "events_with_source_boundary_pct": 100.0,
                        "events_with_client_timestamp_pct": 98.0,
                    },
                },
                "thresholds": {
                    "per_metric": {
                        "render_success_rate": {
                            "metric": "render_success_rate",
                            "status": "warn",
                            "observed": 0.9,
                            "sample_count": 10,
                            "comparator": "min",
                            "go_threshold": 0.995,
                            "rollback_threshold": 0.985,
                            "reason": "below_go_threshold",
                        }
                    },
                    "overall_recommendation": "hold",
                    "failed_conditions": [],
                    "sample": {
                        "exposure_count": 10,
                        "payload_detected_count": 10,
                        "render_attempt_count": 10,
                        "runtime_attempt_count": 5,
                        "minimum_exposure_count_for_go": 300,
                    },
                },
            }

    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: _FakeOrchestrator())

    response = client.get("/v1/telemetry/ui/summary?window_hours=24&limit=999")

    assert response.status_code == 200
    payload = response.json()
    assert payload["window_hours"] == 24
    assert payload["metrics"]["exposure_count"] == 10
    assert payload["thresholds"]["overall_recommendation"] == "hold"


def test_ui_telemetry_summary_endpoint_validates_query_params() -> None:
    client = TestClient(api_app_module.create_app())

    response = client.get("/v1/telemetry/ui/summary?window_hours=0")

    assert response.status_code == 422


def test_ui_telemetry_summary_endpoint_requires_auth_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("METIS_API_TOKEN", "secret-token")
    client = TestClient(api_app_module.create_app())

    response = client.get("/v1/telemetry/ui/summary")

    assert response.status_code == 401


def test_ui_telemetry_summary_endpoint_accepts_auth_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("METIS_API_TOKEN", "secret-token")
    client = TestClient(api_app_module.create_app())

    class _FakeOrchestrator:
        def get_ui_telemetry_summary(self, *, window_hours=24, limit=50_000):
            return {
                "window_hours": window_hours,
                "generated_at": "2026-03-23T12:00:00+00:00",
                "sampled_event_count": 0,
                "metrics": {
                    "exposure_count": 0,
                    "render_attempt_count": 0,
                    "render_success_rate": None,
                    "render_failure_rate": None,
                    "fallback_rate_by_reason": {},
                    "interaction_rate": None,
                    "runtime_attempt_rate": None,
                    "runtime_success_rate": None,
                    "runtime_failure_rate": None,
                    "runtime_skip_mix": {},
                    "data_quality": {
                        "events_with_run_id_pct": None,
                        "events_with_source_boundary_pct": None,
                        "events_with_client_timestamp_pct": None,
                    },
                },
                "thresholds": {
                    "per_metric": {},
                    "overall_recommendation": "hold",
                    "failed_conditions": [],
                    "sample": {
                        "exposure_count": 0,
                        "payload_detected_count": 0,
                        "render_attempt_count": 0,
                        "runtime_attempt_count": 0,
                        "minimum_exposure_count_for_go": 300,
                    },
                },
            }

    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: _FakeOrchestrator())

    response = client.get(
        "/v1/telemetry/ui/summary",
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 200
    assert response.json()["thresholds"]["overall_recommendation"] == "hold"


def test_brain_graph_preserves_assistant_node_types_and_scope_metadata(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())
    fake_orchestrator = MagicMock()
    fake_orchestrator.get_workspace_graph.return_value = BrainGraph().build_from_indexes_and_sessions(
        [],
        [],
        {
            "identity": {
                "assistant_id": "metis-companion",
                "name": "Guide",
                "companion_enabled": True,
            },
            "status": {
                "runtime_provider": "local_gguf",
                "runtime_model": "metis-q4",
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
                    "target_node_id": "assistant:metis",
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
    assert nodes["assistant:metis"]["node_type"] == "assistant"
    assert nodes["assistant:metis"]["metadata"]["scope"] == "assistant_self"
    assert nodes["memory:memory-1"]["node_type"] == "memory"
    assert nodes["memory:memory-1"]["metadata"]["scope"] == "assistant_learned"
    assert nodes["playbook:playbook-1"]["node_type"] == "playbook"
    assert nodes["playbook:playbook-1"]["metadata"]["scope"] == "assistant_self"
    assert nodes["category:assistant:memory"]["metadata"]["scope"] == "assistant_self"
    assert nodes["category:assistant:playbooks"]["metadata"]["scope"] == "assistant_self"
    assert edges[("category:assistant", "category:brain", "category_member")]["metadata"]["scope"] == "assistant_self"
    assert edges[("memory:memory-1", "assistant:metis", "belongs_to")]["metadata"]["scope"] == "assistant_learned"
    assert edges[("memory:memory-1", "assistant:metis", "belongs_to")]["metadata"]["note"] == "derived"


def test_features_list_returns_known_flags() -> None:
    client = TestClient(api_app_module.create_app())

    response = client.get("/v1/features")

    assert response.status_code == 200
    payload = response.json()
    names = {item["name"] for item in payload["features"]}
    assert "api_compat_openai" in names
    assert "agent_loop_hardening" in names


def test_features_disable_and_enable_roundtrip(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", api_app_module.WorkspaceOrchestrator)
    import metis_app.settings_store as _store

    monkeypatch.setattr(_store, "USER_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(_store, "DEFAULT_PATH", tmp_path / "default_settings.json")
    _store.DEFAULT_PATH.write_text("{}", encoding="utf-8")

    client = TestClient(api_app_module.create_app())

    disable_response = client.post(
        "/v1/features/api_compat_openai/disable",
        json={"reason": "maintenance", "duration_ms": 120000},
    )
    assert disable_response.status_code == 200
    disabled_payload = disable_response.json()
    assert disabled_payload["feature"] == "api_compat_openai"
    assert disabled_payload["enabled"] is False
    assert disabled_payload["disabled_by_kill_switch"] is True
    assert disabled_payload["kill_switch_reason"] == "maintenance"
    assert disabled_payload["disabled_until"]

    enable_response = client.post(
        "/v1/features/api_compat_openai/enable",
        json={"enabled": True},
    )
    assert enable_response.status_code == 200
    enabled_payload = enable_response.json()
    assert enabled_payload["feature"] == "api_compat_openai"
    assert enabled_payload["enabled"] is True
    assert enabled_payload["disabled_by_kill_switch"] is False


def test_features_require_auth_when_token_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("METIS_API_TOKEN", "secret-token")
    client = TestClient(api_app_module.create_app())

    response = client.get("/v1/features")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Phase 1A — OpenAI Chat Completions compatibility endpoint
# ---------------------------------------------------------------------------


def test_openai_chat_completions_disabled_by_default(monkeypatch) -> None:
    """Endpoint returns 404 when api_compat_openai flag is not enabled."""
    monkeypatch.setattr(
        api_app_module._settings_store,
        "load_settings",
        lambda: {},
    )
    client = TestClient(api_app_module.create_app())

    response = client.post(
        "/v1/openai/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 404
    assert "api_compat_openai" in response.json()["detail"]


def test_openai_chat_completions_happy_path(monkeypatch) -> None:
    """Endpoint returns an OpenAI-shaped response when flag is enabled."""
    monkeypatch.setattr(
        api_app_module._settings_store,
        "load_settings",
        lambda: {"feature_flags": {"api_compat_openai": True}},
    )

    class _Result:
        run_id = "run-openai-compat"
        answer_text = "Hello from METIS"
        selected_mode = "Q&A"
        llm_provider = "mock"
        llm_model = "mock-model"

    fake_orchestrator = MagicMock()
    fake_orchestrator.run_direct_query.return_value = _Result()
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

    client = TestClient(api_app_module.create_app())
    response = client.post(
        "/v1/openai/chat/completions",
        json={
            "model": "metis",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is METIS?"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "chat.completion"
    assert payload["id"].startswith("metis-run-openai-compat")
    assert payload["model"] == "metis"
    assert isinstance(payload["created"], int)
    assert len(payload["choices"]) == 1
    choice = payload["choices"][0]
    assert choice["index"] == 0
    assert choice["finish_reason"] == "stop"
    assert choice["message"]["role"] == "assistant"
    assert choice["message"]["content"] == "Hello from METIS"
    assert payload["usage"]["prompt_tokens"] == 0
    assert payload["usage"]["completion_tokens"] == 0
    assert payload["usage"]["total_tokens"] == 0

    # Verify that the last user message was forwarded as the prompt.
    assert fake_orchestrator.run_direct_query.call_count == 1
    called_req = fake_orchestrator.run_direct_query.call_args[0][0]
    assert called_req.prompt == "What is METIS?"


def test_openai_chat_completions_rejects_empty_messages_list(monkeypatch) -> None:
    """Empty messages array fails Pydantic validation (min_length=1) → 422."""
    monkeypatch.setattr(
        api_app_module._settings_store,
        "load_settings",
        lambda: {"feature_flags": {"api_compat_openai": True}},
    )
    client = TestClient(api_app_module.create_app())

    response = client.post(
        "/v1/openai/chat/completions",
        json={"model": "metis", "messages": []},
    )

    assert response.status_code == 422


def test_openai_chat_completions_rejects_no_user_message(monkeypatch) -> None:
    """Messages with only system role and no user turn get 422."""
    monkeypatch.setattr(
        api_app_module._settings_store,
        "load_settings",
        lambda: {"feature_flags": {"api_compat_openai": True}},
    )
    client = TestClient(api_app_module.create_app())

    response = client.post(
        "/v1/openai/chat/completions",
        json={"messages": [{"role": "system", "content": "Be helpful."}]},
    )

    assert response.status_code == 422


def test_openai_chat_completions_requires_auth_when_configured(monkeypatch) -> None:
    """Auth parity: endpoint requires Bearer token when METIS_API_TOKEN is set."""
    monkeypatch.setenv("METIS_API_TOKEN", "secret-token")
    monkeypatch.setattr(
        api_app_module._settings_store,
        "load_settings",
        lambda: {"feature_flags": {"api_compat_openai": True}},
    )
    client = TestClient(api_app_module.create_app())

    response = client.post(
        "/v1/openai/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 401


def test_openai_chat_completions_accepts_auth_when_configured(monkeypatch) -> None:
    """Endpoint works with a valid Bearer token when auth is configured."""
    monkeypatch.setenv("METIS_API_TOKEN", "secret-token")
    monkeypatch.setattr(
        api_app_module._settings_store,
        "load_settings",
        lambda: {"feature_flags": {"api_compat_openai": True}},
    )

    class _Result:
        run_id = "run-auth-compat"
        answer_text = "Authorized response"
        selected_mode = "Q&A"
        llm_provider = "mock"
        llm_model = "mock-model"

    fake_orchestrator = MagicMock()
    fake_orchestrator.run_direct_query.return_value = _Result()
    monkeypatch.setattr(api_app_module, "WorkspaceOrchestrator", lambda: fake_orchestrator)

    client = TestClient(api_app_module.create_app())
    response = client.post(
        "/v1/openai/chat/completions",
        headers={"Authorization": "Bearer secret-token"},
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Authorized response"


def test_openai_chat_completions_rejects_stream_true(monkeypatch) -> None:
    """Streaming is not supported in this slice — stream=true returns 501."""
    monkeypatch.setattr(
        api_app_module._settings_store,
        "load_settings",
        lambda: {"feature_flags": {"api_compat_openai": True}},
    )
    client = TestClient(api_app_module.create_app())

    response = client.post(
        "/v1/openai/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}], "stream": True},
    )

    assert response.status_code == 501
