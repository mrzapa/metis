from __future__ import annotations

import json
import uuid

import axiom_app.engine.indexing as engine_indexing
from axiom_app.engine.querying import (
    DirectQueryRequest,
    KnowledgeSearchRequest,
    RagQueryRequest,
    knowledge_search,
    query_direct,
    query_rag,
)


def test_query_rag_returns_serializable_sources_and_mock_answer(tmp_path, monkeypatch) -> None:
    src = tmp_path / "notes.txt"
    src.write_text(
        "Ada Lovelace wrote the first algorithm.\n"
        "Grace Hopper popularized compilers.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(engine_indexing, "_DEFAULT_INDEX_STORAGE_DIR", tmp_path / "indexes")
    build_result = engine_indexing.build_index(
        engine_indexing.IndexBuildRequest(
            document_paths=[str(src)],
            settings={
                "embedding_provider": "mock",
                "vector_db_type": "json",
                "chunk_size": 60,
                "chunk_overlap": 0,
            },
            index_id="notes-index",
        )
    )

    result = query_rag(
        RagQueryRequest(
            manifest_path=build_result.manifest_path,
            question="Who wrote the first algorithm?",
            settings={
                "embedding_provider": "mock",
                "llm_provider": "mock",
                "vector_db_type": "chroma",
                "selected_mode": "Research",
                "system_instructions": "You are a careful research assistant.",
                "top_k": 2,
                "retrieval_k": 2,
            },
        )
    )

    assert result.answer_text
    assert "Mock/Test Backend" in result.answer_text
    assert result.sources
    assert isinstance(result.sources[0], dict)
    assert json.dumps(result.sources)
    assert result.context_block
    assert isinstance(result.top_score, float)
    assert result.selected_mode == "Research"
    uuid.UUID(result.run_id)


def test_query_direct_returns_mock_answer_and_preserves_run_id() -> None:
    result = query_direct(
        DirectQueryRequest(
            prompt="Say hello.",
            settings={
                "llm_provider": "mock",
                "selected_mode": "Q&A",
                "system_instructions": "Be concise.",
            },
            run_id="run-123",
        )
    )

    assert result.run_id == "run-123"
    assert result.answer_text
    assert result.selected_mode == "Q&A"


def test_query_rag_includes_retrieval_plan_and_fallback(tmp_path, monkeypatch) -> None:
    src = tmp_path / "notes.txt"
    src.write_text(
        "Ada Lovelace wrote the first algorithm.\n"
        "Grace Hopper popularized compilers.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(engine_indexing, "_DEFAULT_INDEX_STORAGE_DIR", tmp_path / "indexes")
    build_result = engine_indexing.build_index(
        engine_indexing.IndexBuildRequest(
            document_paths=[str(src)],
            settings={
                "embedding_provider": "mock",
                "vector_db_type": "json",
                "chunk_size": 32,
                "chunk_overlap": 0,
            },
            index_id="notes-index-hierarchical",
        )
    )

    result = query_rag(
        RagQueryRequest(
            manifest_path=build_result.manifest_path,
            question="Who wrote the first algorithm?",
            settings={
                "embedding_provider": "mock",
                "llm_provider": "mock",
                "vector_db_type": "json",
                "selected_mode": "Research",
                "retrieval_mode": "hierarchical",
                "top_k": 2,
                "retrieval_k": 4,
                "fallback_strategy": "synthesize_anyway",
                "use_sub_queries": False,
            },
        )
    )

    assert result.retrieval_plan["stages"]
    assert result.retrieval_plan["stages"][0]["stage_type"] == "retrieval_complete"
    assert "fallback" in result.retrieval_plan
    assert "triggered" in result.fallback
    assert result.sources[0]["type"] == "parent_chunk"
    assert result.sources[0]["metadata"]["matched_child_count"] >= 1


def test_knowledge_search_returns_summary_text_and_plan(tmp_path, monkeypatch) -> None:
    src = tmp_path / "notes.txt"
    src.write_text(
        "Ada Lovelace wrote the first algorithm.\n"
        "Grace Hopper popularized compilers.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(engine_indexing, "_DEFAULT_INDEX_STORAGE_DIR", tmp_path / "indexes")
    build_result = engine_indexing.build_index(
        engine_indexing.IndexBuildRequest(
            document_paths=[str(src)],
            settings={
                "embedding_provider": "mock",
                "vector_db_type": "json",
                "chunk_size": 32,
                "chunk_overlap": 0,
            },
            index_id="notes-index-search",
        )
    )

    result = knowledge_search(
        KnowledgeSearchRequest(
            manifest_path=build_result.manifest_path,
            question="first algorithm",
            settings={
                "embedding_provider": "mock",
                "llm_provider": "mock",
                "vector_db_type": "json",
                "selected_mode": "Knowledge Search",
                "retrieval_mode": "hierarchical",
                "top_k": 2,
                "use_sub_queries": False,
            },
        )
    )

    assert result.summary_text
    assert result.sources
    assert result.retrieval_plan["selected_mode"] == "Knowledge Search"
    assert result.retrieval_plan["stages"][-1]["stage_type"] == "fallback_decision"


def test_query_rag_no_answer_fallback_returns_message_without_synthesis(
    tmp_path, monkeypatch
) -> None:
    src = tmp_path / "notes.txt"
    src.write_text(
        "Ada Lovelace wrote the first algorithm.\n"
        "Grace Hopper popularized compilers.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(engine_indexing, "_DEFAULT_INDEX_STORAGE_DIR", tmp_path / "indexes")
    build_result = engine_indexing.build_index(
        engine_indexing.IndexBuildRequest(
            document_paths=[str(src)],
            settings={
                "embedding_provider": "mock",
                "vector_db_type": "json",
                "chunk_size": 32,
                "chunk_overlap": 0,
            },
            index_id="notes-index-no-answer",
        )
    )

    class _ExplodingLLM:
        def invoke(self, messages):
            raise AssertionError("query_rag should skip synthesis on no_answer fallback")

    monkeypatch.setattr("axiom_app.engine.querying.create_llm", lambda settings: _ExplodingLLM())

    result = query_rag(
        RagQueryRequest(
            manifest_path=build_result.manifest_path,
            question="Who wrote the first algorithm?",
            settings={
                "embedding_provider": "mock",
                "llm_provider": "mock",
                "vector_db_type": "json",
                "selected_mode": "Q&A",
                "retrieval_min_score": 2.0,
                "fallback_strategy": "no_answer",
                "fallback_message": "Not enough grounded evidence.",
                "use_sub_queries": False,
            },
        )
    )

    assert result.answer_text == "Not enough grounded evidence."
    assert result.sources
    assert result.fallback == {
        "triggered": True,
        "strategy": "no_answer",
        "reason": "score_below_threshold",
        "min_score": 2.0,
        "observed_score": result.top_score,
        "message": "Not enough grounded evidence.",
    }
    assert result.retrieval_plan["fallback"] == result.fallback
    assert result.retrieval_plan["stages"][-1]["stage_type"] == "fallback_decision"
