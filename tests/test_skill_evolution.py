from __future__ import annotations

import json
import sqlite3

import pytest

from metis_app.services.skill_repository import SkillRepository


def test_default_candidates_db_path_is_repo_root():
    from metis_app.services.skill_repository import _DEFAULT_CANDIDATES_DB_PATH
    assert _DEFAULT_CANDIDATES_DB_PATH.name == "skill_candidates.db"
    assert (_DEFAULT_CANDIDATES_DB_PATH.parent / "metis_app").is_dir()


@pytest.fixture
def repo(tmp_path):
    return SkillRepository(skills_dir=tmp_path / "skills")


def test_save_candidate_creates_db_and_row(tmp_path, repo):
    db_path = tmp_path / "skill_candidates.db"
    repo.save_candidate(
        db_path=db_path,
        query_text="How does RAG work?",
        trace_json=json.dumps({"iterations": 2, "sources": ["doc1"]}),
        convergence_score=0.97,
    )
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT query_text, convergence_score, promoted FROM skill_candidates").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "How does RAG work?"
    assert abs(rows[0][1] - 0.97) < 1e-6
    assert rows[0][2] == 0  # not promoted yet


def test_iteration_complete_event_has_trace_fields():
    """The iteration_complete event dict must have the expected keys."""
    event = {
        "type": "iteration_complete",
        "run_id": "abc123",
        "iterations_used": 2,
        "convergence_score": 0.97,
        "query_text": "What is RAG?",
    }
    assert event["type"] == "iteration_complete"
    assert "iterations_used" in event
    assert "convergence_score" in event


def test_companion_capture_saves_above_threshold(tmp_path):
    from metis_app.services.assistant_companion import AssistantCompanionService
    companion = AssistantCompanionService.__new__(AssistantCompanionService)  # bypass __init__
    db_path = tmp_path / "skill_candidates.db"
    saved = companion.capture_skill_candidate(
        db_path=db_path,
        query_text="test query",
        trace_json='{"ok": true}',
        convergence_score=0.96,
        trace_iterations=2,
    )
    assert saved is True


def test_companion_capture_skips_below_threshold(tmp_path):
    from metis_app.services.assistant_companion import AssistantCompanionService
    companion = AssistantCompanionService.__new__(AssistantCompanionService)
    db_path = tmp_path / "skill_candidates.db"
    saved = companion.capture_skill_candidate(
        db_path=db_path,
        query_text="test query",
        trace_json='{}',
        convergence_score=0.50,  # below min_convergence=0.90
        trace_iterations=2,
    )
    assert saved is False


def test_list_candidates_returns_top_unreviewed(tmp_path, repo):
    db_path = tmp_path / "skill_candidates.db"
    for i in range(5):
        repo.save_candidate(db_path=db_path, query_text=f"q{i}", trace_json="{}", convergence_score=float(i) / 10)
    candidates = repo.list_candidates(db_path=db_path, limit=3)
    assert len(candidates) == 3
    # Should be ordered by convergence_score desc
    scores = [c["convergence_score"] for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_stream_rag_answer_docstring_documents_iteration_complete():
    from metis_app.engine.streaming import stream_rag_answer
    assert "iteration_complete" in (stream_rag_answer.__doc__ or "")


def test_reflect_spawns_promote_thread_on_completed_run(monkeypatch):
    """reflect() must spawn _promote_skill_candidates in a daemon thread for completed_run
    when allow_automatic_writes is True."""
    import time
    from unittest.mock import MagicMock, patch
    from metis_app.services.assistant_companion import AssistantCompanionService

    promote_calls = []

    companion = AssistantCompanionService.__new__(AssistantCompanionService)
    companion.repository = MagicMock()
    companion.repository.get_status.return_value = MagicMock(
        paused=False, last_reflection_at=None, to_payload=lambda: {},
        state="", last_reflection_trigger="", latest_summary="", latest_why="",
    )
    companion.session_repo = None
    companion.trace_store = MagicMock(read_run_events=MagicMock(return_value=[]))

    companion._promote_skill_candidates = lambda settings, **kw: promote_calls.append(settings) or 0

    fake_mem = MagicMock()
    fake_mem.to_payload = lambda: {}
    fake_mem.entry_id = "e1"
    fake_mem.created_at = ""
    fake_mem.summary = fake_mem.title = fake_mem.why = ""
    fake_mem.tags = fake_mem.related_node_ids = []

    with patch("metis_app.services.assistant_companion.resolve_assistant_identity",
               return_value=MagicMock(companion_enabled=True, to_payload=lambda: {})), \
         patch("metis_app.services.assistant_companion.resolve_assistant_policy",
               return_value=MagicMock(
                   reflection_enabled=True, allow_automatic_writes=True,
                   reflection_cooldown_seconds=0, max_memory_entries=100,
                   max_playbooks=50, max_brain_links=100,
                   autonomous_research_enabled=False, trigger_on_completed_run=True,
               )), \
         patch("metis_app.services.assistant_companion.resolve_assistant_runtime",
               return_value=MagicMock(to_payload=lambda: {})), \
         patch.object(companion, "_ensure_status", return_value=MagicMock(
             paused=False, last_reflection_at=None, to_payload=lambda: {},
             state="", last_reflection_trigger="", latest_summary="", latest_why="",
         )), \
         patch.object(companion, "_generate_reflection", return_value={
             "title": "t", "summary": "s", "details": "d", "why": "w",
             "playbook_title": "pt", "playbook_bullets": [], "confidence": 0.7,
             "tags": [], "related_node_ids": [], "context_lines": [],
         }), \
         patch.object(companion, "_is_duplicate_reflection", return_value=False), \
         patch("metis_app.services.assistant_companion.AssistantMemoryEntry") as mock_mem_cls, \
         patch("metis_app.services.assistant_companion.AssistantBrainLink"), \
         patch("metis_app.services.assistant_companion.settings_store"):
        mock_mem_cls.create.return_value = fake_mem
        companion.reflect(trigger="completed_run", settings={}, force=True)

    time.sleep(0.1)
    assert len(promote_calls) >= 1


def test_promote_skill_candidates_writes_md_and_marks_promoted(tmp_path):
    """_promote_skill_candidates writes a .md file and marks the candidate promoted."""
    import json
    from unittest.mock import MagicMock, patch
    from metis_app.services.assistant_companion import AssistantCompanionService
    from metis_app.services.skill_repository import SkillRepository

    db_path = tmp_path / "skill_candidates.db"
    auto_gen_dir = tmp_path / "skills" / "auto-generated"
    repo = SkillRepository(skills_dir=tmp_path / "skills")
    repo.save_candidate(
        db_path=db_path, query_text="How does vector search work?",
        trace_json=json.dumps({"iterations": 3}), convergence_score=0.97,
    )

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content=json.dumps({
        "is_generalizable": True, "skill_name": "Vector Search Skill",
        "skill_description": "Explains vector search.", "confidence": 0.9,
    }))

    companion = AssistantCompanionService.__new__(AssistantCompanionService)
    with patch("metis_app.services.assistant_companion.create_llm", return_value=mock_llm), \
         patch.object(companion, "_resolve_runtime_llm_settings", return_value={"llm_provider": "openai"}):
        count = companion._promote_skill_candidates(
            settings={}, _db_path=db_path, _auto_gen_dir=auto_gen_dir,
        )

    assert count == 1
    md_files = list(auto_gen_dir.glob("*.md"))
    assert len(md_files) == 1
    assert "Vector Search Skill" in md_files[0].read_text()
    # Promoted candidate filtered out
    assert len(repo.list_candidates(db_path=db_path, limit=10)) == 0


def test_iteration_complete_wired_in_wrapped(monkeypatch):
    """_wrapped() must call capture_skill_candidate when iteration_complete fires with iterations_used >= 2."""
    from unittest.mock import MagicMock, patch
    from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator
    from metis_app.services.skill_repository import _DEFAULT_CANDIDATES_DB_PATH

    captured_calls = []

    fake_events = [
        {"type": "run_started", "run_id": "r1"},
        {"type": "iteration_complete", "run_id": "r1",
         "iterations_used": 3, "convergence_score": 0.97, "query_text": "What is RAG?"},
        {"type": "final", "run_id": "r1", "answer_text": "An answer.", "sources": []},
    ]

    orchestrator = WorkspaceOrchestrator.__new__(WorkspaceOrchestrator)
    orchestrator._assistant_service = MagicMock()
    orchestrator._assistant_service.capture_skill_candidate = lambda **kw: captured_calls.append(kw)
    orchestrator._assistant_service.reflect = MagicMock(return_value={"ok": True})

    with patch("metis_app.services.workspace_orchestrator.stream_rag_answer", return_value=iter(fake_events)), \
         patch.object(orchestrator, "_record_trace_event"), \
         patch.object(orchestrator, "_resolve_nyx_install_actions", return_value=None), \
         patch.object(orchestrator, "append_message"), \
         patch.object(orchestrator, "_resolve_query_settings", return_value={}), \
         patch.object(orchestrator, "_prepare_session_for_query"):
        from metis_app.engine.querying import RagQueryRequest
        req = RagQueryRequest(question="What is RAG?", manifest_path="", settings={})
        list(orchestrator.stream_rag_query(req, session_id="s1"))

    assert len(captured_calls) == 1
    assert captured_calls[0]["query_text"] == "What is RAG?"
    assert captured_calls[0]["convergence_score"] == 0.97
    assert captured_calls[0]["trace_iterations"] == 3
    assert captured_calls[0]["db_path"] == _DEFAULT_CANDIDATES_DB_PATH
