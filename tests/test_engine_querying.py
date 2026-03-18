from __future__ import annotations

import json
import uuid

import axiom_app.engine.indexing as engine_indexing
from axiom_app.engine.querying import (
    DirectQueryRequest,
    RagQueryRequest,
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
