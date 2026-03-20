"""Tests for axiom_app.engine.streaming.stream_rag_answer."""

from __future__ import annotations

import json
import uuid

import axiom_app.engine.indexing as engine_indexing
import axiom_app.engine.streaming as engine_streaming
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


def test_stream_rag_answer_research_mode_emits_subqueries(tmp_path, monkeypatch) -> None:
    """Research mode + use_sub_queries=True emits a subqueries event after retrieval_complete."""
    build_result = _build_test_index(tmp_path, monkeypatch)

    # Patch _generate_sub_queries to return a deterministic list
    monkeypatch.setattr(
        engine_streaming,
        "_generate_sub_queries",
        lambda question, llm: ["sub-query A", "sub-query B"],
    )

    req = RagQueryRequest(
        manifest_path=build_result.manifest_path,
        question="Who wrote the first algorithm?",
        settings={
            "embedding_provider": "mock",
            "llm_provider": "mock",
            "vector_db_type": "json",
            "selected_mode": "Research",
            "use_sub_queries": True,
            "top_k": 2,
            "retrieval_k": 2,
        },
        run_id="research-run-1",
    )

    events = list(stream_rag_answer(req))
    event_types = [e["type"] for e in events]

    assert "error" not in event_types, f"Unexpected error event: {events}"

    # subqueries event must be present and come after retrieval_complete
    assert "subqueries" in event_types
    rc_idx = event_types.index("retrieval_complete")
    sq_idx = event_types.index("subqueries")
    assert sq_idx == rc_idx + 1, "subqueries must immediately follow retrieval_complete"

    sq_event = next(e for e in events if e["type"] == "subqueries")
    assert sq_event["run_id"] == "research-run-1"
    assert sq_event["queries"] == ["sub-query A", "sub-query B"]
    json.dumps(sq_event)  # must be JSON-serialisable


def test_stream_rag_answer_research_mode_emits_retrieval_augmented(tmp_path, monkeypatch) -> None:
    build_result = _build_test_index(tmp_path, monkeypatch)

    monkeypatch.setattr(
        engine_streaming,
        "_generate_sub_queries",
        lambda question, llm: ["sub-query A", "sub-query B"],
    )

    req = RagQueryRequest(
        manifest_path=build_result.manifest_path,
        question="Who wrote the first algorithm?",
        settings={
            "embedding_provider": "mock",
            "llm_provider": "mock",
            "vector_db_type": "json",
            "selected_mode": "Research",
            "use_sub_queries": True,
            "top_k": 2,
            "retrieval_k": 2,
        },
        run_id="research-run-augmented",
    )

    events = list(stream_rag_answer(req))
    augmented = next(e for e in events if e["type"] == "retrieval_augmented")
    assert augmented["run_id"] == "research-run-augmented"
    assert augmented["sources"]
    assert augmented["context_block"]
    assert isinstance(augmented["top_score"], float)


def test_stream_rag_answer_non_research_no_subqueries(tmp_path, monkeypatch) -> None:
    """Non-Research runs must never emit a subqueries event."""
    build_result = _build_test_index(tmp_path, monkeypatch)

    req = RagQueryRequest(
        manifest_path=build_result.manifest_path,
        question="Who popularized compilers?",
        settings={
            "embedding_provider": "mock",
            "llm_provider": "mock",
            "vector_db_type": "json",
            "selected_mode": "Q&A",
            "use_sub_queries": True,  # even if enabled, mode guards it
            "top_k": 2,
            "retrieval_k": 2,
        },
    )

    events = list(stream_rag_answer(req))
    event_types = [e["type"] for e in events]
    assert "subqueries" not in event_types


def test_stream_rag_answer_research_use_sub_queries_false_no_event(tmp_path, monkeypatch) -> None:
    """Research mode with use_sub_queries=False must not emit a subqueries event."""
    build_result = _build_test_index(tmp_path, monkeypatch)

    req = RagQueryRequest(
        manifest_path=build_result.manifest_path,
        question="Who wrote the first algorithm?",
        settings={
            "embedding_provider": "mock",
            "llm_provider": "mock",
            "vector_db_type": "json",
            "selected_mode": "Research",
            "use_sub_queries": False,
            "top_k": 2,
            "retrieval_k": 2,
        },
    )

    events = list(stream_rag_answer(req))
    event_types = [e["type"] for e in events]
    assert "subqueries" not in event_types


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


def test_stream_rag_answer_no_answer_fallback_short_circuits_generation(
    tmp_path, monkeypatch
) -> None:
    build_result = _build_test_index(tmp_path, monkeypatch)

    req = RagQueryRequest(
        manifest_path=build_result.manifest_path,
        question="Who wrote the first algorithm?",
        settings={
            "embedding_provider": "mock",
            "llm_provider": "mock",
            "vector_db_type": "json",
            "retrieval_min_score": 0.99,
            "fallback_strategy": "no_answer",
            "fallback_message": "Need better evidence.",
            "selected_mode": "Q&A",
            "top_k": 2,
            "retrieval_k": 2,
        },
        run_id="fallback-run-1",
    )

    events = list(stream_rag_answer(req))
    event_types = [e["type"] for e in events]
    assert event_types == ["run_started", "retrieval_complete", "fallback_decision", "final"]
    assert "token" not in event_types
    fallback_event = next(e for e in events if e["type"] == "fallback_decision")
    assert fallback_event["fallback"]["triggered"] is True
    assert fallback_event["fallback"]["strategy"] == "no_answer"
    assert fallback_event["fallback"]["message"] == "Need better evidence."
    final = events[-1]
    assert final["fallback"]["triggered"] is True
    assert final["fallback"]["strategy"] == "no_answer"
    assert final["answer_text"] == "Need better evidence."


def test_stream_rag_answer_research_emits_retrieval_augmented_event(
    tmp_path, monkeypatch
) -> None:
    build_result = _build_test_index(tmp_path, monkeypatch)

    monkeypatch.setattr(
        engine_streaming,
        "_generate_sub_queries",
        lambda question, llm: ["Ada Lovelace algorithm", "compiler history"],
    )

    req = RagQueryRequest(
        manifest_path=build_result.manifest_path,
        question="Who wrote the first algorithm?",
        settings={
            "embedding_provider": "mock",
            "llm_provider": "mock",
            "vector_db_type": "json",
            "selected_mode": "Research",
            "use_sub_queries": True,
            "top_k": 2,
            "retrieval_k": 2,
        },
        run_id="augmented-run-1",
    )

    events = list(stream_rag_answer(req))
    event_types = [e["type"] for e in events]

    assert "error" not in event_types, f"Unexpected error event: {events}"
    assert "retrieval_augmented" in event_types
    assert event_types.index("subqueries") < event_types.index("retrieval_augmented")
    assert event_types.index("retrieval_augmented") < event_types.index("fallback_decision")

    augmented = next(e for e in events if e["type"] == "retrieval_augmented")
    assert augmented["run_id"] == "augmented-run-1"
    assert augmented["sources"]
    assert augmented["context_block"]
    assert isinstance(augmented["top_score"], float)

    final = events[-1]
    assert final["type"] == "final"
    assert final["fallback"]["strategy"] == "synthesize_anyway"


# ---------------------------------------------------------------------------
# Agentic iterative refinement loop (AIlice-inspired self-critique)
# ---------------------------------------------------------------------------


def test_stream_agentic_mode_emits_iteration_and_refinement_events(
    tmp_path, monkeypatch
) -> None:
    """agentic_mode=True emits iteration_start, gaps_identified, and
    refinement_retrieval events before the final answer."""
    build_result = _build_test_index(tmp_path, monkeypatch)

    # Patch _identify_gaps to return a deterministic non-empty list.
    monkeypatch.setattr(
        engine_streaming,
        "_identify_gaps",
        lambda question, draft, ctx, llm: ["gap query A"],
    )

    req = RagQueryRequest(
        manifest_path=build_result.manifest_path,
        question="Who wrote the first algorithm?",
        settings={
            "embedding_provider": "mock",
            "llm_provider": "mock",
            "vector_db_type": "json",
            "selected_mode": "Research",
            "agentic_mode": True,
            "agentic_max_iterations": 1,
            "top_k": 2,
            "retrieval_k": 2,
        },
        run_id="agentic-run-1",
    )

    events = list(stream_rag_answer(req))
    event_types = [e["type"] for e in events]

    assert "error" not in event_types, f"Unexpected error: {events}"

    # All events are JSON-serialisable.
    for event in events:
        json.dumps(event)

    # Required agentic events are present.
    assert "iteration_start" in event_types
    assert "gaps_identified" in event_types
    assert "refinement_retrieval" in event_types

    # run_id is consistent across all events.
    assert all(e["run_id"] == "agentic-run-1" for e in events)

    # iteration_start payload is correct.
    it_start = next(e for e in events if e["type"] == "iteration_start")
    assert it_start["iteration"] == 1
    assert it_start["total_iterations"] == 1

    # gaps_identified payload contains the patched gaps.
    gaps_evt = next(e for e in events if e["type"] == "gaps_identified")
    assert gaps_evt["gaps"] == ["gap query A"]
    assert gaps_evt["iteration"] == 1

    # refinement_retrieval contains sources and context_block.
    refine_evt = next(e for e in events if e["type"] == "refinement_retrieval")
    assert "sources" in refine_evt
    assert "context_block" in refine_evt
    assert "top_score" in refine_evt
    assert isinstance(refine_evt["top_score"], float)
    assert refine_evt["iteration"] == 1

    # Sequence: run_started first, final last, token events present.
    assert event_types[0] == "run_started"
    assert event_types[-1] == "final"
    assert "token" in event_types

    # final.answer_text equals joined token texts.
    token_texts = "".join(e["text"] for e in events if e["type"] == "token")
    final = events[-1]
    assert final["answer_text"] == token_texts


def test_stream_agentic_mode_no_gaps_stops_early(tmp_path, monkeypatch) -> None:
    """When _identify_gaps returns [] the loop breaks after the first
    iteration_start event without emitting gaps_identified."""
    build_result = _build_test_index(tmp_path, monkeypatch)

    monkeypatch.setattr(
        engine_streaming,
        "_identify_gaps",
        lambda question, draft, ctx, llm: [],  # no gaps found
    )

    req = RagQueryRequest(
        manifest_path=build_result.manifest_path,
        question="Who wrote the first algorithm?",
        settings={
            "embedding_provider": "mock",
            "llm_provider": "mock",
            "vector_db_type": "json",
            "agentic_mode": True,
            "agentic_max_iterations": 3,
            "top_k": 2,
            "retrieval_k": 2,
        },
        run_id="agentic-no-gaps",
    )

    events = list(stream_rag_answer(req))
    event_types = [e["type"] for e in events]

    assert "error" not in event_types
    # iteration_start is emitted once, then the loop breaks.
    assert event_types.count("iteration_start") == 1
    # No gaps means no gaps_identified or refinement_retrieval events.
    assert "gaps_identified" not in event_types
    assert "refinement_retrieval" not in event_types
    assert event_types[-1] == "final"


def test_stream_agentic_mode_respects_max_iterations(tmp_path, monkeypatch) -> None:
    """The loop never exceeds agentic_max_iterations iteration cycles."""
    build_result = _build_test_index(tmp_path, monkeypatch)

    monkeypatch.setattr(
        engine_streaming,
        "_identify_gaps",
        lambda question, draft, ctx, llm: ["gap Q"],
    )

    max_iter = 2
    req = RagQueryRequest(
        manifest_path=build_result.manifest_path,
        question="Who wrote the first algorithm?",
        settings={
            "embedding_provider": "mock",
            "llm_provider": "mock",
            "vector_db_type": "json",
            "agentic_mode": True,
            "agentic_max_iterations": max_iter,
            "top_k": 2,
            "retrieval_k": 2,
        },
        run_id="agentic-max-iter",
    )

    events = list(stream_rag_answer(req))
    event_types = [e["type"] for e in events]

    assert "error" not in event_types

    iteration_starts = [e for e in events if e["type"] == "iteration_start"]
    assert len(iteration_starts) == max_iter
    assert [e["iteration"] for e in iteration_starts] == list(range(1, max_iter + 1))
    assert all(e["total_iterations"] == max_iter for e in iteration_starts)
    assert event_types[-1] == "final"


def test_stream_non_agentic_no_agentic_events(tmp_path, monkeypatch) -> None:
    """When agentic_mode is False, no agentic events are emitted."""
    build_result = _build_test_index(tmp_path, monkeypatch)

    req = RagQueryRequest(
        manifest_path=build_result.manifest_path,
        question="Who wrote the first algorithm?",
        settings={
            "embedding_provider": "mock",
            "llm_provider": "mock",
            "vector_db_type": "json",
            "agentic_mode": False,
            "top_k": 2,
            "retrieval_k": 2,
        },
    )

    events = list(stream_rag_answer(req))
    event_types = [e["type"] for e in events]

    assert "iteration_start" not in event_types
    assert "gaps_identified" not in event_types
    assert "refinement_retrieval" not in event_types
    assert event_types[-1] == "final"


def test_dedup_sources_removes_duplicates() -> None:
    """_dedup_sources removes entries with the same chunk_id."""
    from axiom_app.engine.streaming import _dedup_sources

    sources = [
        {"chunk_id": "c1", "snippet": "foo"},
        {"chunk_id": "c2", "snippet": "bar"},
        {"chunk_id": "c1", "snippet": "foo"},  # duplicate
        {"chunk_id": "c3", "snippet": "baz"},
    ]
    result = _dedup_sources(sources)
    chunk_ids = [s["chunk_id"] for s in result]
    assert chunk_ids == ["c1", "c2", "c3"]


def test_identify_gaps_returns_list(tmp_path, monkeypatch) -> None:
    """_identify_gaps returns a list and handles LLM failures gracefully."""
    from axiom_app.engine.streaming import _identify_gaps

    class _MockLLM:
        def invoke(self, messages: list) -> object:
            # Return well-formed JSON list
            return type("R", (), {"content": '["query about X", "query about Y"]'})()

    gaps = _identify_gaps("test question", "test answer", "test context", _MockLLM())
    assert isinstance(gaps, list)
    assert len(gaps) == 2

    class _BadLLM:
        def invoke(self, messages: list) -> object:
            raise RuntimeError("LLM error")

    gaps_on_error = _identify_gaps("q", "a", "ctx", _BadLLM())
    assert gaps_on_error == []
