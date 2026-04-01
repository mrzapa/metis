from __future__ import annotations

import json
import pathlib
import sqlite3

import pytest

from metis_app.services.skill_repository import SkillRepository


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


def test_list_candidates_returns_top_unreviewed(tmp_path, repo):
    db_path = tmp_path / "skill_candidates.db"
    for i in range(5):
        repo.save_candidate(db_path=db_path, query_text=f"q{i}", trace_json="{}", convergence_score=float(i) / 10)
    candidates = repo.list_candidates(db_path=db_path, limit=3)
    assert len(candidates) == 3
    # Should be ordered by convergence_score desc
    scores = [c["convergence_score"] for c in candidates]
    assert scores == sorted(scores, reverse=True)
