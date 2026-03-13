"""Tests for axiom_app.engine.streaming.stream_rag_answer."""

from __future__ import annotations

import json
import uuid

import axiom_app.engine.indexing as engine_indexing
from axiom_app.engine.querying import RagQueryRequest
from axiom_app.engine.streaming import stream_rag_answer


def _build_test_index(tmp_path, monkeypatch):
    """Helper: build a minimal JSON index with mock embeddings."""
    src = tmp_path / "notes.txt"
    src.write_text(
        "Ada Lovelace wrote the first algorithm.\n"
        "Grace Hopper popularized compilers.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(engine_indexing, "_DEFAULT_INDEX_STORAGE_DIR", tmp_path / "indexes")
    return engine_indexing.build_index(
        engine_indexing.IndexBuildRequest(
            document_paths=[str(src)],
            settings={
                "embedding_provider": "mock",
                "vector_db_type": "json",
                "chunk_size": 60,
                "chunk_overlap": 0,
            },
            index_id="stream-test-index",
        )
    )


def test_stream_rag_answer_happy_path(tmp_path, monkeypatch) -> None:
    """Generator yields events in order; all are JSON-serialisable; ends with final."""
    build_result = _build_test_index(tmp_path, monkeypatch)

    req = RagQueryRequest(
        manifest_path=build_result.manifest_path,
        question="Who wrote the first algorithm?",
        settings={
            "embedding_provider": "mock",
            "llm_provider": "mock",
            "vector_db_type": "json",
            "selected_mode": "Q&A",
            "top_k": 2,
            "retrieval_k": 2,
        },
        run_id="stream-run-1",
    )

    events = list(stream_rag_answer(req))

    # No error events
    event_types = [e["type"] for e in events]
    assert "error" not in event_types, f"Unexpected error event: {events}"

    # All events are JSON-serialisable
    for event in events:
        json.dumps(event)  # raises if not serialisable

    # Correct ordering: run_started first, retrieval_complete second, final last
    assert event_types[0] == "run_started"
    assert event_types[1] == "retrieval_complete"
    assert event_types[-1] == "final"

    # At least one token event between retrieval_complete and final
    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) >= 1

    # run_id is consistent across all events
    run_ids = {e["run_id"] for e in events}
    assert run_ids == {"stream-run-1"}

    # retrieval_complete payload
    rc = next(e for e in events if e["type"] == "retrieval_complete")
    assert rc["sources"]
    assert rc["context_block"]
    assert isinstance(rc["top_score"], float)

    # final payload
    final = events[-1]
    assert final["answer_text"]
    assert final["sources"] == rc["sources"]
    # answer_text should equal the concatenation of all token texts
    assert final["answer_text"] == "".join(e["text"] for e in token_events)


def test_stream_rag_answer_auto_run_id(tmp_path, monkeypatch) -> None:
    """When run_id is not provided, a valid UUID is generated."""
    build_result = _build_test_index(tmp_path, monkeypatch)

    req = RagQueryRequest(
        manifest_path=build_result.manifest_path,
        question="Who popularized compilers?",
        settings={
            "embedding_provider": "mock",
            "llm_provider": "mock",
            "vector_db_type": "json",
            "top_k": 1,
            "retrieval_k": 1,
        },
    )

    events = list(stream_rag_answer(req))
    assert "error" not in [e["type"] for e in events]
    run_id = events[0]["run_id"]
    uuid.UUID(run_id)  # raises if not a valid UUID


def test_stream_rag_answer_empty_question_yields_error() -> None:
    """Empty question produces a single error event without raising."""
    req = RagQueryRequest(
        manifest_path="/nonexistent/manifest.json",
        question="   ",
        settings={"llm_provider": "mock"},
        run_id="err-run",
    )

    events = list(stream_rag_answer(req))
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert events[0]["run_id"] == "err-run"
    assert events[0]["message"]
    # Must be JSON-serialisable
    json.dumps(events[0])
