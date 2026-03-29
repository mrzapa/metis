"""Unit tests for WorkspaceOrchestrator.

The orchestrator must delegate to the existing subsystems rather than
re-implement their logic.  Each test verifies that the correct underlying
method is called with the correct arguments, using lightweight stubs /
mock objects so that no real disk I/O or LLM calls are made.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import ANY, MagicMock, patch

import pytest

from metis_app.engine.querying import DirectQueryRequest, RagQueryRequest
from metis_app.models.brain_graph import BrainGraph
from metis_app.models.parity_types import SkillDefinition
from metis_app.models.session_types import SessionDetail, SessionSummary
from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_summary(session_id: str = "s1") -> SessionSummary:
    return SessionSummary(
        session_id=session_id,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        title="Test",
        summary="",
        active_profile="",
        mode="Q&A",
        index_id="idx-1",
        vector_backend="json",
        llm_provider="mock",
        llm_model="mock-model",
        embed_model="",
        retrieve_k=5,
        final_k=3,
        mmr_lambda=0.5,
        agentic_iterations=0,
        extra_json="{}",
    )


def _make_skill(skill_id: str = "research") -> SkillDefinition:
    return SkillDefinition(
        skill_id=skill_id,
        name="Research",
        description="Deep-dive research skill",
        enabled_by_default=True,
        priority=10,
    )


def _make_orchestrator(
    session_repo: Any | None = None,
    skill_repo: Any | None = None,
    assistant_service: Any | None = None,
) -> WorkspaceOrchestrator:
    """Return a WorkspaceOrchestrator with stub dependencies injected."""
    if session_repo is None:
        session_repo = MagicMock()
        session_repo.list_sessions.return_value = []
        session_repo.get_session.return_value = None
    if skill_repo is None:
        skill_repo = MagicMock()
        skill_repo.list_valid_skills.return_value = []
        skill_repo.enabled_skills.return_value = []
    if assistant_service is None:
        assistant_service = MagicMock()
        assistant_service.get_snapshot.return_value = {
            "identity": {},
            "runtime": {},
            "policy": {},
            "status": {},
        }
        assistant_service.reflect.return_value = {"ok": True}
    return WorkspaceOrchestrator(
        session_repo=session_repo,
        skill_repo=skill_repo,
        assistant_service=assistant_service,
        index_dir="/tmp/fake_indexes",
    )


# ---------------------------------------------------------------------------
# Ingestion / organisation
# ---------------------------------------------------------------------------


class TestIngestDocuments:
    def test_delegates_to_build_index(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[Any] = []

        def _fake_build_index(self: Any, document_paths: list[str], settings: dict[str, Any], *, index_id: str | None = None, progress_cb: Any = None) -> Any:
            captured.append((document_paths, settings, index_id, progress_cb))
            result = MagicMock()
            result.index_id = "idx-new"
            return result

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.WorkspaceOrchestrator.build_index",
            _fake_build_index,
        )

        orch = _make_orchestrator()
        result = orch.ingest_documents(
            document_paths=["/tmp/a.txt"],
            settings={"llm_provider": "mock"},
            index_id="idx-new",
        )

        assert len(captured) == 1
        document_paths, settings, index_id, progress_cb = captured[0]
        assert document_paths == ["/tmp/a.txt"]
        assert settings == {"llm_provider": "mock"}
        assert index_id == "idx-new"
        assert progress_cb is None
        assert result.index_id == "idx-new"

    def test_passes_progress_callback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[Any] = []

        def _fake_build_index(req: Any, progress_cb: Any = None) -> Any:
            captured.append(progress_cb)
            return MagicMock()

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.build_index",
            _fake_build_index,
        )

        def cb(ev: Any) -> None:
            pass

        _make_orchestrator().ingest_documents(
            ["/tmp/b.txt"], {}, progress_cb=cb
        )
        assert captured[0] is cb


class TestBuildIndex:
    def test_resolves_settings_and_reflects(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[Any] = []
        assistant_service = MagicMock()
        assistant_service.reflect.return_value = {"ok": True}

        def _fake_build_index(req: Any, progress_cb: Any = None) -> Any:
            captured.append((req, progress_cb))
            result = MagicMock()
            result.index_id = "idx-new"
            return result

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.build_index",
            _fake_build_index,
        )
        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator._settings_store.load_settings",
            lambda: {},
        )

        orch = _make_orchestrator(assistant_service=assistant_service)
        result = orch.build_index(
            document_paths=["/tmp/a.txt"],
            settings={"llm_provider": "mock"},
            index_id="idx-new",
        )

        assert len(captured) == 1
        req, cb = captured[0]
        assert req.document_paths == ["/tmp/a.txt"]
        assert req.settings == {
            "llm_provider": "mock",
            "assistant_identity": {},
            "assistant_runtime": {},
            "assistant_policy": {},
        }
        assert req.index_id == "idx-new"
        assert cb is None
        assert result.index_id == "idx-new"
        assistant_service.reflect.assert_called_once_with(
            trigger="index_build",
            settings=req.settings,
            context_id="index:idx-new",
            _orchestrator=ANY,
        )

    def test_passes_progress_callback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[Any] = []

        def _fake_build_index(req: Any, progress_cb: Any = None) -> Any:
            captured.append(progress_cb)
            return MagicMock()

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.build_index",
            _fake_build_index,
        )

        def cb(ev: Any) -> None:
            pass

        _make_orchestrator().build_index(["/tmp/b.txt"], {}, progress_cb=cb)
        assert captured[0] is cb


class TestUiTelemetry:
    def test_persists_ui_telemetry_via_trace_store(self) -> None:
        trace_store = MagicMock()
        orch = _make_orchestrator()
        orch._trace_store = trace_store

        accepted = orch.ingest_ui_telemetry_events(
            [
                {
                    "event_name": "artifact_interaction",
                    "source": "chat_artifact_boundary",
                    "occurred_at": "2026-03-23T12:00:00Z",
                    "run_id": "run-telemetry",
                    "session_id": "session-1",
                    "message_id": "message-1",
                    "is_streaming": False,
                    "payload": {
                        "interaction_type": "card_click",
                        "artifact_index": 0,
                        "artifact_id": "artifact-1",
                        "artifact_type": "timeline",
                    },
                }
            ]
        )

        assert accepted == 1
        trace_store.append_event.assert_called_once_with(
            run_id="run-telemetry",
            stage="ui_artifact",
            event_type="artifact_interaction",
            payload={
                "source": "chat_artifact_boundary",
                "session_id": "session-1",
                "message_id": "message-1",
                "client_timestamp": "2026-03-23T12:00:00Z",
                "is_streaming": False,
                "telemetry": {
                    "interaction_type": "card_click",
                    "artifact_index": 0,
                    "artifact_id": "artifact-1",
                    "artifact_type": "timeline",
                },
            },
        )


class TestUiTelemetrySummary:
    def test_delegates_to_trace_store(self) -> None:
        orch = _make_orchestrator()
        orch._trace_store = MagicMock()
        orch._trace_store.aggregate_ui_artifact_summary.return_value = {
            "window_hours": 24,
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

        result = orch.get_ui_telemetry_summary(window_hours=24, limit=1000)

        assert result["window_hours"] == 24
        orch._trace_store.aggregate_ui_artifact_summary.assert_called_once_with(
            window_hours=24,
            limit=1000,
        )

    def test_normalizes_invalid_window_and_limit(self) -> None:
        orch = _make_orchestrator()
        orch._trace_store = MagicMock()
        orch._trace_store.aggregate_ui_artifact_summary.return_value = {
            "window_hours": 24,
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

        _ = orch.get_ui_telemetry_summary(window_hours=0, limit=-5)

        orch._trace_store.aggregate_ui_artifact_summary.assert_called_once_with(
            window_hours=24,
            limit=50_000,
        )


class TestListIndexes:
    def test_delegates_to_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_indexes = [{"index_id": "idx-1"}, {"index_id": "idx-2"}]

        def _fake_list(index_dir: Any = None) -> list[dict[str, Any]]:
            return fake_indexes

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.list_indexes",
            _fake_list,
        )

        result = _make_orchestrator().list_indexes()
        assert result == fake_indexes


class TestGetIndex:
    def test_delegates_to_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_meta = {"index_id": "idx-42"}

        def _fake_get(index_id: str, index_dir: Any = None) -> dict[str, Any] | None:
            if index_id == "idx-42":
                return fake_meta
            return None

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.get_index",
            _fake_get,
        )

        orch = _make_orchestrator()
        assert orch.get_index("idx-42") == fake_meta
        assert orch.get_index("idx-unknown") is None


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


class TestRunRagQuery:
    def test_delegates_to_query_rag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_result = MagicMock(
            run_id="run-rag",
            answer_text="answer",
            sources=[],
            context_block="context",
            top_score=0.5,
            selected_mode="Q&A",
        )

        def _fake_query_rag(req: Any) -> Any:
            return fake_result

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.query_rag",
            _fake_query_rag,
        )

        from metis_app.engine.querying import RagQueryRequest

        req = RagQueryRequest(
            manifest_path="/tmp/manifest.json",
            question="What is METIS?",
            settings={},
        )
        orch = _make_orchestrator()
        orch._trace_store.append_event = MagicMock()  # type: ignore[method-assign]
        result = orch.run_rag_query(req)
        assert result is fake_result

    def test_session_id_persists_session_messages_and_reflects(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_result = MagicMock(
            run_id="run-1",
            answer_text="answer",
            sources=[{"sid": "S1", "source": "doc.txt", "snippet": "evidence"}],
            context_block="context",
            top_score=0.91,
            selected_mode="Q&A",
            retrieval_plan={
                "stages": [
                    {
                        "stage_type": "retrieval_complete",
                        "payload": {
                            "sources": [{"sid": "S1", "source": "doc.txt", "snippet": "evidence"}],
                            "context_block": "context",
                            "top_score": 0.91,
                        },
                    },
                    {
                        "stage_type": "fallback_decision",
                        "payload": {
                            "triggered": False,
                            "strategy": "synthesize_anyway",
                            "reason": "",
                            "min_score": 0.15,
                            "observed_score": 0.91,
                            "message": "ok",
                        },
                    },
                ]
            },
            fallback={
                "triggered": False,
                "strategy": "synthesize_anyway",
                "reason": "",
                "min_score": 0.15,
                "observed_score": 0.91,
                "message": "ok",
            },
        )
        session_repo = MagicMock()
        session_repo.get_session.return_value = None
        session_repo.upsert_session.return_value = _make_summary("s1")
        session_repo.append_message.return_value = None
        assistant_service = MagicMock()
        assistant_service.get_snapshot.return_value = {"identity": {"name": "Companion"}}
        assistant_service.reflect.return_value = {"ok": True}
        orch = _make_orchestrator(session_repo=session_repo, assistant_service=assistant_service)
        trace_append = MagicMock()
        orch._trace_store.append_event = trace_append  # type: ignore[method-assign]

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator._settings_store.load_settings",
            lambda: {
                "selected_mode": "Q&A",
                "llm_provider": "mock",
                "llm_model_custom": "model-x",
                "embedding_model_custom": "embed-x",
                "vector_db_type": "json",
                "retrieval_k": 9,
                "top_k": 4,
                "mmr_lambda": 0.25,
                "agentic_max_iterations": 2,
            },
        )
        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.list_indexes",
            lambda index_dir=None: [
                {"manifest_path": "/tmp/manifest.json", "index_id": "idx-1"}
            ],
        )
        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.query_rag",
            lambda req: fake_result,
        )

        expected_settings = {
            "selected_mode": "Q&A",
            "llm_provider": "mock",
            "llm_model_custom": "model-x",
            "embedding_model_custom": "embed-x",
            "vector_db_type": "json",
            "retrieval_k": 9,
            "top_k": 4,
            "mmr_lambda": 0.25,
            "agentic_max_iterations": 2,
            "assistant_identity": {},
            "assistant_runtime": {},
            "assistant_policy": {},
        }
        req = RagQueryRequest(
            manifest_path="/tmp/manifest.json",
            question="What is METIS?",
            settings={"selected_mode": "Q&A"},
        )
        result = orch.run_rag_query(req, session_id="s1")

        assert result is fake_result
        session_repo.upsert_session.assert_called_once()
        upsert_kwargs = session_repo.upsert_session.call_args.kwargs
        assert upsert_kwargs["title"] == "What is METIS?"
        assert upsert_kwargs["index_id"] == "idx-1"
        assert upsert_kwargs["llm_provider"] == "mock"
        assert upsert_kwargs["llm_model"] == "model-x"
        assert upsert_kwargs["embed_model"] == "embed-x"
        assert "Companion" in upsert_kwargs["extra_json"]
        assert session_repo.append_message.call_args_list[0].args == ("s1",)
        assert session_repo.append_message.call_args_list[0].kwargs == {
            "role": "user",
            "content": "What is METIS?",
            "run_id": "",
            "sources": [],
        }
        assert session_repo.append_message.call_args_list[1].args == ("s1",)
        assert session_repo.append_message.call_args_list[1].kwargs["role"] == "assistant"
        assert session_repo.append_message.call_args_list[1].kwargs["run_id"] == "run-1"
        assert assistant_service.reflect.call_args.kwargs == {
            "trigger": "completed_run",
            "settings": expected_settings,
            "session_id": "s1",
            "run_id": "run-1",
            "_orchestrator": ANY,
        }
        assert [call.kwargs["event_type"] for call in trace_append.call_args_list] == [
            "retrieval_complete",
            "fallback_decision",
            "final",
        ]


class TestRunDirectQuery:
    def test_delegates_to_query_direct(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_result = MagicMock(
            run_id="run-direct",
            answer_text="hello",
            selected_mode="Q&A",
            llm_provider="mock",
            llm_model="mock-model",
        )

        def _fake_query_direct(req: Any) -> Any:
            return fake_result

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.query_direct",
            _fake_query_direct,
        )

        from metis_app.engine.querying import DirectQueryRequest

        req = DirectQueryRequest(prompt="Hello", settings={})
        orch = _make_orchestrator()
        orch._trace_store.append_event = MagicMock()  # type: ignore[method-assign]
        result = orch.run_direct_query(req)
        assert result is fake_result

    def test_session_id_persists_session_messages_and_reflects(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_result = MagicMock(
            run_id="run-2",
            answer_text="answer",
            selected_mode="Tutor",
            llm_provider="mock",
            llm_model="model-y",
        )
        session_repo = MagicMock()
        session_repo.get_session.return_value = None
        session_repo.upsert_session.return_value = _make_summary("s2")
        session_repo.append_message.return_value = None
        assistant_service = MagicMock()
        assistant_service.get_snapshot.return_value = {"identity": {"name": "Companion"}}
        assistant_service.reflect.return_value = {"ok": True}
        orch = _make_orchestrator(session_repo=session_repo, assistant_service=assistant_service)
        trace_append = MagicMock()
        orch._trace_store.append_event = trace_append  # type: ignore[method-assign]

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator._settings_store.load_settings",
            lambda: {
                "selected_mode": "Tutor",
                "llm_provider": "mock",
                "llm_model_custom": "model-y",
                "embedding_model_custom": "embed-y",
                "vector_db_type": "json",
                "retrieval_k": 3,
                "top_k": 2,
                "mmr_lambda": 0.5,
                "agentic_max_iterations": 1,
            },
        )
        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.query_direct",
            lambda req: fake_result,
        )

        req = DirectQueryRequest(prompt="Hello", settings={"selected_mode": "Tutor"})
        result = orch.run_direct_query(req, session_id="s2")

        assert result is fake_result
        session_repo.upsert_session.assert_called_once()
        assert session_repo.upsert_session.call_args.kwargs["title"] == "Hello"
        assert session_repo.append_message.call_args_list[0].kwargs == {
            "role": "user",
            "content": "Hello",
            "run_id": "",
            "sources": [],
        }
        assert session_repo.append_message.call_args_list[1].kwargs["run_id"] == "run-2"
        assert assistant_service.reflect.call_args.kwargs == {
            "trigger": "completed_run",
            "settings": {
                "selected_mode": "Tutor",
                "llm_provider": "mock",
                "llm_model_custom": "model-y",
                "embedding_model_custom": "embed-y",
                "vector_db_type": "json",
                "retrieval_k": 3,
                "top_k": 2,
                "mmr_lambda": 0.5,
                "agentic_max_iterations": 1,
                "assistant_identity": {},
                "assistant_runtime": {},
                "assistant_policy": {},
            },
            "session_id": "s2",
            "run_id": "run-2",
            "_orchestrator": ANY,
        }
        assert trace_append.call_count == 1


class TestRunKnowledgeSearch:
    def test_session_id_persists_search_summary_and_sources(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from metis_app.engine.querying import KnowledgeSearchRequest

        fake_result = MagicMock(
            run_id="run-search-1",
            summary_text="Found 2 relevant passages.",
            sources=[{"sid": "S1", "source": "doc.txt", "snippet": "evidence"}],
            context_block="context",
            top_score=0.77,
            selected_mode="Knowledge Search",
            fallback={"triggered": False, "strategy": "synthesize_anyway"},
        )
        session_repo = MagicMock()
        session_repo.get_session.return_value = None
        session_repo.upsert_session.return_value = _make_summary("s-search")
        assistant_service = MagicMock()
        assistant_service.get_snapshot.return_value = {"identity": {"name": "Companion"}}
        orch = _make_orchestrator(session_repo=session_repo, assistant_service=assistant_service)
        trace_append = MagicMock()
        orch._trace_store.append_event = trace_append  # type: ignore[method-assign]

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator._settings_store.load_settings",
            lambda: {
                "selected_mode": "Knowledge Search",
                "llm_provider": "mock",
                "top_k": 4,
            },
        )
        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.knowledge_search",
            lambda req: fake_result,
        )

        req = KnowledgeSearchRequest(
            manifest_path="/tmp/manifest.json",
            question="Find evidence",
            settings={"selected_mode": "Knowledge Search"},
        )
        result = orch.run_knowledge_search(req, session_id="s-search")

        assert result is fake_result
        assert session_repo.append_message.call_args_list[0].kwargs["role"] == "user"
        assert session_repo.append_message.call_args_list[1].kwargs["role"] == "assistant"
        assert session_repo.append_message.call_args_list[1].kwargs["run_id"] == "run-search-1"
        assert trace_append.call_args.kwargs["event_type"] == "knowledge_search_complete"

    def test_records_retrieval_plan_stages_before_completion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from metis_app.engine.querying import KnowledgeSearchRequest

        fake_result = MagicMock(
            run_id="run-search-2",
            summary_text="Found 2 relevant passages.",
            sources=[{"sid": "S2", "source": "doc.txt", "snippet": "augmented evidence"}],
            context_block="context",
            top_score=0.88,
            selected_mode="Knowledge Search",
            retrieval_plan={
                "stages": [
                    {
                        "stage_type": "retrieval_complete",
                        "payload": {
                            "sources": [{"sid": "S1"}],
                            "context_block": "ctx",
                            "top_score": 0.5,
                        },
                    },
                    {
                        "stage_type": "query_expansion",
                        "payload": {"queries": ["ada algorithm"]},
                    },
                    {
                        "stage_type": "fallback_decision",
                        "payload": {
                            "triggered": False,
                            "strategy": "synthesize_anyway",
                            "reason": "",
                            "min_score": 0.15,
                            "observed_score": 0.88,
                            "message": "ok",
                        },
                    },
                ]
            },
            fallback={
                "triggered": False,
                "strategy": "synthesize_anyway",
                "reason": "",
                "min_score": 0.15,
                "observed_score": 0.88,
                "message": "ok",
            },
        )
        orch = _make_orchestrator()
        trace_append = MagicMock()
        orch._trace_store.append_event = trace_append  # type: ignore[method-assign]

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator._settings_store.load_settings",
            lambda: {"selected_mode": "Knowledge Search", "llm_provider": "mock"},
        )
        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.knowledge_search",
            lambda req: fake_result,
        )

        req = KnowledgeSearchRequest(
            manifest_path="/tmp/manifest.json",
            question="Find evidence",
            settings={"selected_mode": "Knowledge Search"},
        )
        orch.run_knowledge_search(req)

        event_types = [call.kwargs["event_type"] for call in trace_append.call_args_list]
        stages = [call.kwargs["stage"] for call in trace_append.call_args_list]

        assert event_types == [
            "retrieval_complete",
            "subqueries",
            "fallback_decision",
            "knowledge_search_complete",
        ]
        assert stages == ["retrieval", "retrieval", "fallback", "retrieval"]
        assert trace_append.call_args_list[-1].kwargs["payload"]["fallback"] == fake_result.fallback


class TestStreamRagQuery:
    def test_delegates_to_stream_rag_answer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        events = [{"type": "token", "text": "hello"}]

        def _fake_stream(req: Any, cancel_token: Any = None) -> Any:
            return iter(events)

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.stream_rag_answer",
            _fake_stream,
        )

        from metis_app.engine.querying import RagQueryRequest

        req = RagQueryRequest(manifest_path="/tmp/m.json", question="?", settings={})
        result = list(_make_orchestrator().stream_rag_query(req))
        assert result == events

    def test_session_id_writes_user_and_assistant_messages(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session_repo = MagicMock()
        session_repo.get_session.return_value = None
        session_repo.upsert_session.return_value = _make_summary("s3")
        assistant_service = MagicMock()
        assistant_service.get_snapshot.return_value = {"identity": {"name": "Companion"}}
        assistant_service.reflect.return_value = {"ok": True}
        orch = _make_orchestrator(session_repo=session_repo, assistant_service=assistant_service)
        trace_append = MagicMock()
        orch._trace_store.append_event = trace_append  # type: ignore[method-assign]

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator._settings_store.load_settings",
            lambda: {"selected_mode": "Q&A", "llm_provider": "mock"},
        )
        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.stream_rag_answer",
            lambda req, cancel_token=None: iter(
                [
                    {"type": "retrieval_complete", "run_id": "run-3", "sources": [{"sid": "S1", "source": "doc", "snippet": "evidence"}]},
                    {"type": "final", "run_id": "run-3", "answer_text": "done", "sources": [{"sid": "S1", "source": "doc", "snippet": "evidence"}]},
                ]
            ),
        )

        req = RagQueryRequest(
            manifest_path="/tmp/m.json",
            question="?",
            settings={"selected_mode": "Q&A"},
            run_id="run-3",
        )
        result = list(orch.stream_rag_query(req, session_id="s3"))

        assert [item["type"] for item in result] == ["retrieval_complete", "final"]
        assert session_repo.append_message.call_args_list[0].kwargs["role"] == "user"
        assert session_repo.append_message.call_args_list[1].kwargs["role"] == "assistant"
        assert assistant_service.reflect.call_args.kwargs["session_id"] == "s3"
        assert assistant_service.reflect.call_args.kwargs["run_id"] == "run-3"
        assert assistant_service.reflect.call_args.kwargs["settings"] == {
            "selected_mode": "Q&A",
            "llm_provider": "mock",
            "assistant_identity": {},
            "assistant_runtime": {},
            "assistant_policy": {},
        }
        assert trace_append.call_count == 2

    def test_retrieval_augmented_updates_pending_sources_for_final_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from metis_app.engine.querying import RagQueryRequest

        session_repo = MagicMock()
        session_repo.get_session.return_value = None
        session_repo.upsert_session.return_value = _make_summary("s4")
        assistant_service = MagicMock()
        assistant_service.get_snapshot.return_value = {"identity": {"name": "Companion"}}
        assistant_service.reflect.return_value = {"ok": True}
        orch = _make_orchestrator(session_repo=session_repo, assistant_service=assistant_service)
        trace_append = MagicMock()
        orch._trace_store.append_event = trace_append  # type: ignore[method-assign]

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator._settings_store.load_settings",
            lambda: {"selected_mode": "Research", "llm_provider": "mock"},
        )
        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.stream_rag_answer",
            lambda req, cancel_token=None: iter(
                [
                    {
                        "type": "retrieval_complete",
                        "run_id": "run-aug-1",
                        "sources": [{"sid": "S1", "source": "doc", "snippet": "initial evidence"}],
                    },
                    {
                        "type": "retrieval_augmented",
                        "run_id": "run-aug-1",
                        "sources": [{"sid": "S2", "source": "doc", "snippet": "augmented evidence"}],
                    },
                    {
                        "type": "final",
                        "run_id": "run-aug-1",
                        "answer_text": "done",
                        "fallback": {"triggered": False, "strategy": "synthesize_anyway"},
                    },
                ]
            ),
        )

        req = RagQueryRequest(
            manifest_path="/tmp/m.json",
            question="?",
            settings={"selected_mode": "Research"},
            run_id="run-aug-1",
        )
        result = list(orch.stream_rag_query(req, session_id="s4"))

        assert [item["type"] for item in result] == [
            "retrieval_complete",
            "retrieval_augmented",
            "final",
        ]
        assistant_message = session_repo.append_message.call_args_list[1].kwargs
        assert assistant_message["role"] == "assistant"
        assert assistant_message["run_id"] == "run-aug-1"
        assert [source.sid for source in assistant_message["sources"]] == ["S2"]
        assert [call.kwargs["event_type"] for call in trace_append.call_args_list] == [
            "retrieval_complete",
            "retrieval_augmented",
            "final",
        ]


class TestTraceHooks:
    def test_records_non_token_events_and_maps_stages(self) -> None:
        orch = _make_orchestrator()
        append_event = MagicMock()
        orch._trace_store.append_event = append_event  # type: ignore[method-assign]

        orch._record_trace_event("run-4", {"type": "token", "run_id": "run-4", "text": "skip"})
        orch._record_trace_event(
            "run-4",
            {"type": "retrieval_complete", "run_id": "run-4", "sources": [{"sid": "S1"}]},
        )
        orch._record_trace_event(
            "run-4",
            {"type": "final", "run_id": "run-4", "answer_text": "done"},
        )
        orch._record_trace_event(
            "run-4",
            {"type": "fallback_decision", "run_id": "run-4", "fallback": {"triggered": True}},
        )
        orch._record_trace_event(
            "run-4",
            {"type": "knowledge_search_complete", "run_id": "run-4", "sources": [{"sid": "S1"}]},
        )

        assert append_event.call_count == 4
        first_call = append_event.call_args_list[0].kwargs
        second_call = append_event.call_args_list[1].kwargs
        third_call = append_event.call_args_list[2].kwargs
        fourth_call = append_event.call_args_list[3].kwargs
        assert first_call["stage"] == "retrieval"
        assert first_call["event_type"] == "retrieval_complete"
        assert first_call["payload"] == {"sources": [{"sid": "S1"}]}
        assert second_call["stage"] == "synthesis"
        assert second_call["event_type"] == "final"
        assert third_call["stage"] == "fallback"
        assert third_call["event_type"] == "fallback_decision"
        assert fourth_call["stage"] == "retrieval"
        assert fourth_call["event_type"] == "knowledge_search_complete"

    def test_trace_payload_sanitizes_artifacts_to_metadata_only(self) -> None:
        orch = _make_orchestrator()
        append_event = MagicMock()
        orch._trace_store.append_event = append_event  # type: ignore[method-assign]

        orch._record_trace_event(
            "run-5",
            {
                "type": "final",
                "run_id": "run-5",
                "answer_text": "done",
                "artifacts": [
                    {
                        "id": "a1",
                        "type": "table",
                        "summary": "artifact",
                        "payload": "x" * 20_000,
                    }
                ],
            },
        )

        assert append_event.call_count == 1
        payload = append_event.call_args.kwargs["payload"]
        artifacts = list(payload.get("artifacts") or [])
        assert len(artifacts) == 1
        assert artifacts[0]["id"] == "a1"
        assert "payload" not in artifacts[0]
        assert artifacts[0]["payload_bytes"] > 16_384


class TestReflectionHooks:
    def test_reflect_assistant_forwards_session_and_run_arguments(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assistant_service = MagicMock()
        assistant_service.reflect.return_value = {"ok": True}
        orch = _make_orchestrator(assistant_service=assistant_service)

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator._settings_store.load_settings",
            lambda: {"selected_mode": "Tutor", "llm_provider": "mock"},
        )

        result = orch.reflect_assistant(
            trigger="manual",
            session_id="s9",
            run_id="r9",
            force=True,
            settings={"llm_provider": "openai"},
        )

        assert result == {"ok": True}
        assistant_service.reflect.assert_called_once_with(
            trigger="manual",
            settings={
                "selected_mode": "Tutor",
                "llm_provider": "openai",
                "assistant_identity": {},
                "assistant_runtime": {},
                "assistant_policy": {},
            },
            session_id="s9",
            run_id="r9",
            force=True,
            _orchestrator=orch,
        )


# ---------------------------------------------------------------------------
# Graph / Brain canvas
# ---------------------------------------------------------------------------


class TestGetWorkspaceGraph:
    def test_returns_brain_graph(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_indexes = [{"index_id": "idx-1", "backend": "json"}]

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.list_indexes",
            lambda index_dir=None: fake_indexes,
        )

        session_repo = MagicMock()
        session_repo.list_sessions.return_value = []
        assistant_service = MagicMock()
        assistant_service.get_snapshot.return_value = {"identity": {"companion_enabled": False}}

        orch = _make_orchestrator(
            session_repo=session_repo,
            assistant_service=assistant_service,
        )
        graph = orch.get_workspace_graph()

        assert isinstance(graph, BrainGraph)
        # The brain graph should contain at least an "indexes" category node
        assert any(n.node_type in ("category", "index") for n in graph.nodes.values())

    def test_uses_session_repo(self) -> None:
        session_repo = MagicMock()
        session_repo.list_sessions.return_value = [_make_summary()]
        assistant_service = MagicMock()
        assistant_service.get_snapshot.return_value = {"identity": {"companion_enabled": False}}

        with patch("metis_app.services.workspace_orchestrator.list_indexes", return_value=[]):
            orch = _make_orchestrator(
                session_repo=session_repo,
                assistant_service=assistant_service,
            )
            orch.get_workspace_graph()

        session_repo.list_sessions.assert_called_once()


# ---------------------------------------------------------------------------
# Sessions / Memory
# ---------------------------------------------------------------------------


class TestListSessions:
    def test_delegates_with_filters(self) -> None:
        summaries = [_make_summary("s1"), _make_summary("s2")]
        session_repo = MagicMock()
        session_repo.list_sessions.return_value = summaries

        orch = _make_orchestrator(session_repo=session_repo)
        result = orch.list_sessions(search="foo", skill="bar")

        session_repo.list_sessions.assert_called_once_with(search="foo", skill="bar")
        assert result == summaries


class TestGetSession:
    def test_found(self) -> None:
        detail = SessionDetail(summary=_make_summary())
        session_repo = MagicMock()
        session_repo.get_session.return_value = detail

        orch = _make_orchestrator(session_repo=session_repo)
        assert orch.get_session("s1") is detail
        session_repo.get_session.assert_called_once_with("s1")

    def test_not_found(self) -> None:
        session_repo = MagicMock()
        session_repo.get_session.return_value = None

        orch = _make_orchestrator(session_repo=session_repo)
        assert orch.get_session("missing") is None


class TestCreateSession:
    def test_delegates_all_kwargs(self) -> None:
        expected = _make_summary("new-1")
        session_repo = MagicMock()
        session_repo.create_session.return_value = expected

        orch = _make_orchestrator(session_repo=session_repo)
        result = orch.create_session(title="My Chat", mode="Q&A", index_id="idx-1")

        session_repo.create_session.assert_called_once_with(
            title="My Chat",
            summary="",
            active_profile="",
            mode="Q&A",
            index_id="idx-1",
            vector_backend="json",
            llm_provider="",
            llm_model="",
            embed_model="",
            retrieve_k=0,
            final_k=0,
            mmr_lambda=0.0,
            agentic_iterations=0,
            extra_json="{}",
            session_id=None,
        )
        assert result is expected


class TestAppendMessage:
    def test_delegates_to_repo(self) -> None:
        session_repo = MagicMock()
        orch = _make_orchestrator(session_repo=session_repo)
        orch.append_message("s1", role="user", content="Hello", run_id="r1")
        session_repo.append_message.assert_called_once_with(
            "s1", role="user", content="Hello", run_id="r1", sources=[]
        )


class TestSaveFeedback:
    def test_delegates_to_repo(self) -> None:
        session_repo = MagicMock()
        orch = _make_orchestrator(session_repo=session_repo)
        orch.save_feedback("s1", run_id="r1", vote=1, note="Great!")
        session_repo.save_feedback.assert_called_once_with(
            "s1", run_id="r1", vote=1, note="Great!"
        )


class TestDeleteSession:
    def test_delegates_to_repo(self) -> None:
        session_repo = MagicMock()
        orch = _make_orchestrator(session_repo=session_repo)
        orch.delete_session("s1")
        session_repo.delete_session.assert_called_once_with("s1")


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


class TestListSkills:
    def test_delegates_to_skill_repo(self) -> None:
        skill = _make_skill()
        skill_repo = MagicMock()
        skill_repo.list_valid_skills.return_value = [skill]

        orch = _make_orchestrator(skill_repo=skill_repo)
        result = orch.list_skills()

        skill_repo.list_valid_skills.assert_called_once()
        assert result == [skill]


class TestGetSkill:
    def test_found(self) -> None:
        skill = _make_skill("research")
        skill_repo = MagicMock()
        skill_repo.get_skill.return_value = skill

        orch = _make_orchestrator(skill_repo=skill_repo)
        assert orch.get_skill("research") is skill
        skill_repo.get_skill.assert_called_once_with("research")

    def test_not_found(self) -> None:
        skill_repo = MagicMock()
        skill_repo.get_skill.return_value = None

        orch = _make_orchestrator(skill_repo=skill_repo)
        assert orch.get_skill("nope") is None


class TestEnabledSkills:
    def test_delegates_with_settings(self) -> None:
        skill = _make_skill()
        skill_repo = MagicMock()
        skill_repo.enabled_skills.return_value = [skill]

        settings = {"llm_provider": "mock"}
        orch = _make_orchestrator(skill_repo=skill_repo)
        result = orch.enabled_skills(settings)

        skill_repo.enabled_skills.assert_called_once_with(settings)
        assert result == [skill]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class TestSettings:
    def test_load_settings_delegates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = {"llm_provider": "mock"}
        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator._settings_store.load_settings",
            lambda: fake,
        )
        assert _make_orchestrator().load_settings() == fake

    def test_save_settings_delegates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        merged: dict[str, Any] = {}

        def _fake_save(updates: dict[str, Any]) -> dict[str, Any]:
            merged.update(updates)
            return merged

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator._settings_store.save_settings",
            _fake_save,
        )
        result = _make_orchestrator().save_settings({"llm_provider": "openai"})
        assert result == {"llm_provider": "openai"}

    def test_safe_settings_strips_api_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fake_safe(settings: dict[str, Any]) -> dict[str, Any]:
            return {k: v for k, v in settings.items() if not k.startswith("api_key_")}

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator._settings_store.safe_settings",
            _fake_safe,
        )
        payload = {"llm_provider": "openai", "api_key_openai": "sk-secret"}
        result = _make_orchestrator().safe_settings(payload)
        assert "api_key_openai" not in result
        assert result["llm_provider"] == "openai"


# ---------------------------------------------------------------------------
# API integration — brain graph uses orchestrator
# ---------------------------------------------------------------------------


def test_run_autonomous_research_returns_none_when_disabled(tmp_path):
    """run_autonomous_research returns None when autonomous_research_enabled is False."""
    from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator
    orc = WorkspaceOrchestrator()
    settings = {
        "assistant_policy": {"autonomous_research_enabled": False},
        "llm_provider": "mock",
    }
    result = orc.run_autonomous_research(settings)
    assert result is None


def test_run_autonomous_research_returns_result_when_enabled():
    """run_autonomous_research propagates AutonomousResearchService.run result."""
    import unittest.mock as um
    from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator

    expected = {
        "faculty_id": "emergence",
        "index_id": "auto_emergence_abc12345",
        "title": "Emergence in Complex Systems",
        "sources": ["http://example.com"],
    }

    settings = {
        "assistant_policy": {"autonomous_research_enabled": True},
        "llm_provider": "mock",
    }

    orc = WorkspaceOrchestrator()

    mock_svc_instance = um.MagicMock()
    mock_svc_instance.run.return_value = expected
    MockSvcClass = um.MagicMock(return_value=mock_svc_instance)

    with um.patch(
        "metis_app.services.autonomous_research_service.AutonomousResearchService",
        MockSvcClass,
    ), um.patch(
        "metis_app.utils.web_search.create_web_search",
        return_value=um.MagicMock(),
    ), um.patch.object(orc, "list_indexes", return_value=[]):
        result = orc.run_autonomous_research(settings)

    assert result == expected


# ---------------------------------------------------------------------------
# API integration — brain graph uses orchestrator
# ---------------------------------------------------------------------------


class TestApiBrainGraphUsesOrchestrator:
    """Smoke-test that GET /v1/brain/graph goes through WorkspaceOrchestrator."""

    def test_endpoint_returns_graph_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from importlib import import_module

        from fastapi.testclient import TestClient

        api_module = import_module("metis_app.api.app")

        # Patch out the orchestrator's graph builder
        fake_graph = BrainGraph()

        def _fake_graph(self_: Any) -> BrainGraph:
            return fake_graph

        monkeypatch.setattr(
            "metis_app.services.workspace_orchestrator.WorkspaceOrchestrator.get_workspace_graph",
            _fake_graph,
        )

        client = TestClient(api_module.create_app())
        response = client.get("/v1/brain/graph")

        assert response.status_code == 200
        body = response.json()
        assert "nodes" in body
        assert "edges" in body
        assert isinstance(body["nodes"], list)
        assert isinstance(body["edges"], list)
