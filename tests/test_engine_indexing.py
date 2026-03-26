from __future__ import annotations

import metis_app.engine.indexing as engine_indexing


def test_build_index_persists_manifest_and_returns_summary(tmp_path, monkeypatch) -> None:
    src = tmp_path / "notes.txt"
    src.write_text(
        "Ada Lovelace wrote the first algorithm.\n"
        "Grace Hopper popularized compilers.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(engine_indexing, "_DEFAULT_INDEX_STORAGE_DIR", tmp_path / "indexes")

    events: list[dict[str, object]] = []
    result = engine_indexing.build_index(
        engine_indexing.IndexBuildRequest(
            document_paths=[str(src)],
            settings={
                "embedding_provider": "mock",
                "vector_db_type": "json",
                "chunk_size": 40,
                "chunk_overlap": 0,
            },
            index_id="notes-index",
        ),
        progress_cb=events.append,
    )

    assert result.manifest_path.exists()
    assert str(result.manifest_path).endswith("manifest.json")
    assert result.manifest_path.parent == tmp_path / "indexes" / "notes-index"
    assert result.index_id == "notes-index"
    assert result.document_count == 1
    assert result.chunk_count >= 1
    assert result.embedding_signature == "mock"
    assert result.vector_backend == "json"
    assert any(event.get("type") == "status" for event in events)


def test_build_index_rejects_empty_document_paths() -> None:
    try:
        engine_indexing.build_index(
            engine_indexing.IndexBuildRequest(
                document_paths=[],
                settings={"embedding_provider": "mock"},
            )
        )
    except ValueError as exc:
        assert "document_paths" in str(exc)
    else:
        raise AssertionError("Expected ValueError for empty document_paths")
