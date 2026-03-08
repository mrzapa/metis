from __future__ import annotations

import json
import sqlite3

from axiom_app.models.session_types import EvidenceSource
from axiom_app.services.session_repository import SessionRepository


def test_create_append_load_and_export_session(tmp_path) -> None:
    db_path = tmp_path / "rag_sessions.db"
    repo = SessionRepository(db_path)
    repo.init_db()

    session = repo.create_session(
        title="Quarterly Review",
        mode="Research",
        llm_provider="mock",
        llm_model="mock-v1",
        embed_model="mock-embed-v1",
        extra_json=json.dumps({"selected_index_path": "/tmp/index.json"}),
    )
    repo.append_message(
        session.session_id,
        role="user",
        content="What changed?",
        run_id="run-1",
    )
    repo.append_message(
        session.session_id,
        role="assistant",
        content="Revenue improved [S1].",
        run_id="run-1",
        sources=[
            EvidenceSource(
                sid="S1",
                source="report.txt",
                snippet="Revenue improved in Q4.",
                chunk_id="report::chunk0",
                chunk_idx=0,
                score=0.91,
            )
        ],
    )

    detail = repo.get_session(session.session_id)
    assert detail is not None
    assert detail.summary.title == "Quarterly Review"
    assert len(detail.messages) == 2
    assert detail.messages[1].sources[0].sid == "S1"

    md_path, json_path = repo.export_session(session.session_id, tmp_path / "exports")
    assert md_path.exists()
    assert json_path.exists()
    exported = json.loads(json_path.read_text(encoding="utf-8"))
    assert exported["messages"][1]["sources"][0]["sid"] == "S1"
    assert "Quarterly Review" in md_path.read_text(encoding="utf-8")
    assert "Primary Skill" in md_path.read_text(encoding="utf-8")


def test_loads_monolith_compatible_schema_without_migration(tmp_path) -> None:
    db_path = tmp_path / "rag_sessions.db"
    repo = SessionRepository(db_path)
    repo.init_db()

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sessions(
                session_id, created_at, updated_at, title, summary,
                active_profile, mode, index_id, vector_backend, llm_provider,
                llm_model, embed_model, retrieve_k, final_k, mmr_lambda,
                agentic_iterations, extra_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-session",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
                "Legacy session",
                "Imported from legacy",
                "qa-core",
                "Q&A",
                "axiom-legacy",
                "json",
                "mock",
                "mock-v1",
                "mock-embed-v1",
                10,
                3,
                0.5,
                2,
                json.dumps({"selected_index_path": "C:/tmp/legacy-index.json"}),
            ),
        )
        conn.execute(
            """
            INSERT INTO messages(message_id, session_id, ts, role, content, run_id, sources_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "message-1",
                "legacy-session",
                "2026-01-01T00:00:01+00:00",
                "assistant",
                "Legacy answer [S1]",
                "run-1",
                json.dumps(
                    [
                        {
                            "sid": "S1",
                            "source": "legacy.txt",
                            "snippet": "Legacy snippet.",
                            "chunk_id": "legacy::chunk0",
                            "chunk_idx": 0,
                            "score": 0.8,
                        }
                    ]
                ),
            ),
        )

    detail = repo.get_session("legacy-session")
    assert detail is not None
    assert detail.summary.title == "Legacy session"
    assert detail.summary.extra["selected_index_path"].endswith("legacy-index.json")
    assert detail.messages[0].sources[0].source == "legacy.txt"


def test_list_sessions_filters_by_selected_skill(tmp_path) -> None:
    repo = SessionRepository(tmp_path / "rag_sessions.db")
    repo.init_db()
    repo.create_session(
        title="Research run",
        active_profile="research-claims",
        mode="Research",
        extra_json=json.dumps(
            {
                "skills": {
                    "selected": ["research-claims", "qa-core"],
                    "primary": "research-claims",
                    "reasons": {"research-claims": "keywords"},
                }
            }
        ),
    )
    repo.create_session(
        title="Summary run",
        active_profile="summary-blinkist",
        mode="Summary",
        extra_json=json.dumps(
            {
                "skills": {
                    "selected": ["summary-blinkist"],
                    "primary": "summary-blinkist",
                    "reasons": {"summary-blinkist": "mode"},
                }
            }
        ),
    )

    filtered = repo.list_sessions(skill="research-claims")

    assert len(filtered) == 1
    assert filtered[0].primary_skill_id == "research-claims"
