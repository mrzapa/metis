"""Unit tests for WorkspaceOrchestrator.

The orchestrator must delegate to the existing subsystems rather than
re-implement their logic.  Each test verifies that the correct underlying
method is called with the correct arguments, using lightweight stubs /
mock objects so that no real disk I/O or LLM calls are made.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from axiom_app.models.brain_graph import BrainGraph
from axiom_app.models.parity_types import SkillDefinition
from axiom_app.models.session_types import (
    SessionDetail,
    SessionSummary,
)
from axiom_app.services.workspace_orchestrator import WorkspaceOrchestrator


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
) -> WorkspaceOrchestrator:
    """Return a WorkspaceOrchestrator with stub dependencies injected."""
    if session_repo is None:
        session_repo = MagicMock()
        session_repo.list_sessions.return_value = []
    if skill_repo is None:
        skill_repo = MagicMock()
        skill_repo.list_valid_skills.return_value = []
        skill_repo.enabled_skills.return_value = []
    return WorkspaceOrchestrator(
        session_repo=session_repo,
        skill_repo=skill_repo,
        index_dir="/tmp/fake_indexes",
    )


# ---------------------------------------------------------------------------
# Ingestion / organisation
# ---------------------------------------------------------------------------


class TestIngestDocuments:
    def test_delegates_to_build_index(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[Any] = []

        def _fake_build_index(req: Any, progress_cb: Any = None) -> Any:
            captured.append((req, progress_cb))
            result = MagicMock()
            result.index_id = "idx-new"
            return result

        monkeypatch.setattr(
            "axiom_app.services.workspace_orchestrator.build_index",
            _fake_build_index,
        )

        orch = _make_orchestrator()
        result = orch.ingest_documents(
            document_paths=["/tmp/a.txt"],
            settings={"llm_provider": "mock"},
            index_id="idx-new",
        )

        assert len(captured) == 1
        req, cb = captured[0]
        assert req.document_paths == ["/tmp/a.txt"]
        assert req.settings == {"llm_provider": "mock"}
        assert req.index_id == "idx-new"
        assert cb is None
        assert result.index_id == "idx-new"

    def test_passes_progress_callback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[Any] = []

        def _fake_build_index(req: Any, progress_cb: Any = None) -> Any:
            captured.append(progress_cb)
            return MagicMock()

        monkeypatch.setattr(
            "axiom_app.services.workspace_orchestrator.build_index",
            _fake_build_index,
        )

        def cb(ev: Any) -> None:
            pass

        _make_orchestrator().ingest_documents(
            ["/tmp/b.txt"], {}, progress_cb=cb
        )
        assert captured[0] is cb


class TestListIndexes:
    def test_delegates_to_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_indexes = [{"index_id": "idx-1"}, {"index_id": "idx-2"}]

        def _fake_list(index_dir: Any = None) -> list[dict[str, Any]]:
            return fake_indexes

        monkeypatch.setattr(
            "axiom_app.services.workspace_orchestrator.list_indexes",
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
            "axiom_app.services.workspace_orchestrator.get_index",
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
        fake_result = MagicMock()

        def _fake_query_rag(req: Any) -> Any:
            return fake_result

        monkeypatch.setattr(
            "axiom_app.services.workspace_orchestrator.query_rag",
            _fake_query_rag,
        )

        from axiom_app.engine.querying import RagQueryRequest

        req = RagQueryRequest(
            manifest_path="/tmp/manifest.json",
            question="What is Axiom?",
            settings={},
        )
        result = _make_orchestrator().run_rag_query(req)
        assert result is fake_result


class TestRunDirectQuery:
    def test_delegates_to_query_direct(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_result = MagicMock()

        def _fake_query_direct(req: Any) -> Any:
            return fake_result

        monkeypatch.setattr(
            "axiom_app.services.workspace_orchestrator.query_direct",
            _fake_query_direct,
        )

        from axiom_app.engine.querying import DirectQueryRequest

        req = DirectQueryRequest(prompt="Hello", settings={})
        result = _make_orchestrator().run_direct_query(req)
        assert result is fake_result


class TestStreamRagQuery:
    def test_delegates_to_stream_rag_answer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        events = [{"type": "token", "text": "hello"}]

        def _fake_stream(req: Any, cancel_token: Any = None) -> Any:
            return iter(events)

        monkeypatch.setattr(
            "axiom_app.services.workspace_orchestrator.stream_rag_answer",
            _fake_stream,
        )

        from axiom_app.engine.querying import RagQueryRequest

        req = RagQueryRequest(manifest_path="/tmp/m.json", question="?", settings={})
        result = list(_make_orchestrator().stream_rag_query(req))
        assert result == events


# ---------------------------------------------------------------------------
# Graph / Brain canvas
# ---------------------------------------------------------------------------


class TestGetWorkspaceGraph:
    def test_returns_brain_graph(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_indexes = [{"index_id": "idx-1", "backend": "json"}]

        monkeypatch.setattr(
            "axiom_app.services.workspace_orchestrator.list_indexes",
            lambda index_dir=None: fake_indexes,
        )

        session_repo = MagicMock()
        session_repo.list_sessions.return_value = []

        orch = WorkspaceOrchestrator(session_repo=session_repo)
        graph = orch.get_workspace_graph()

        assert isinstance(graph, BrainGraph)
        # The brain graph should contain at least an "indexes" category node
        assert any(n.node_type in ("category", "index") for n in graph.nodes.values())

    def test_uses_session_repo(self) -> None:
        session_repo = MagicMock()
        session_repo.list_sessions.return_value = [_make_summary()]

        with patch("axiom_app.services.workspace_orchestrator.list_indexes", return_value=[]):
            orch = WorkspaceOrchestrator(session_repo=session_repo)
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
            "axiom_app.services.workspace_orchestrator._settings_store.load_settings",
            lambda: fake,
        )
        assert _make_orchestrator().load_settings() == fake

    def test_save_settings_delegates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        merged: dict[str, Any] = {}

        def _fake_save(updates: dict[str, Any]) -> dict[str, Any]:
            merged.update(updates)
            return merged

        monkeypatch.setattr(
            "axiom_app.services.workspace_orchestrator._settings_store.save_settings",
            _fake_save,
        )
        result = _make_orchestrator().save_settings({"llm_provider": "openai"})
        assert result == {"llm_provider": "openai"}

    def test_safe_settings_strips_api_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fake_safe(settings: dict[str, Any]) -> dict[str, Any]:
            return {k: v for k, v in settings.items() if not k.startswith("api_key_")}

        monkeypatch.setattr(
            "axiom_app.services.workspace_orchestrator._settings_store.safe_settings",
            _fake_safe,
        )
        payload = {"llm_provider": "openai", "api_key_openai": "sk-secret"}
        result = _make_orchestrator().safe_settings(payload)
        assert "api_key_openai" not in result
        assert result["llm_provider"] == "openai"


# ---------------------------------------------------------------------------
# API integration — brain graph uses orchestrator
# ---------------------------------------------------------------------------


class TestApiBrainGraphUsesOrchestrator:
    """Smoke-test that GET /v1/brain/graph goes through WorkspaceOrchestrator."""

    def test_endpoint_returns_graph_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from importlib import import_module

        from fastapi.testclient import TestClient

        api_module = import_module("axiom_app.api.app")

        # Patch out the orchestrator's graph builder
        fake_graph = BrainGraph()

        def _fake_graph(self_: Any) -> BrainGraph:
            return fake_graph

        monkeypatch.setattr(
            "axiom_app.services.workspace_orchestrator.WorkspaceOrchestrator.get_workspace_graph",
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
