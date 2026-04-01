from __future__ import annotations

import metis_app.engine.indexing as engine_indexing
from metis_app.engine import get_index, list_indexes


def test_registry_lists_built_indexes_and_reads_metadata(tmp_path, monkeypatch) -> None:
    src = tmp_path / "notes.txt"
    src.write_text(
        "Ada Lovelace wrote the first algorithm.\n"
        "Grace Hopper popularized compilers.\n",
        encoding="utf-8",
    )
    index_dir = tmp_path / "indexes"
    monkeypatch.setattr(engine_indexing, "_DEFAULT_INDEX_STORAGE_DIR", index_dir)
    monkeypatch.setattr("metis_app.services.brain_pass._native_tribev2_available", lambda: False)

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
        )
    )

    listed = list_indexes(index_dir=index_dir)
    listed_index = next(
        item for item in listed if item.get("index_id") == "notes-index"
    )
    fetched = get_index("notes-index", index_dir=index_dir)

    assert set(listed_index) == {
        "index_id",
        "backend",
        "created_at",
        "document_count",
        "chunk_count",
        "manifest_path",
        "embedding_signature",
        "collection_name",
        "legacy_compat",
        "brain_pass",
        "metadata",
    }
    assert listed_index["index_id"] == "notes-index"
    assert listed_index["backend"] == "json"
    assert listed_index["document_count"] == 1
    assert listed_index["chunk_count"] >= 1
    assert listed_index["manifest_path"] == str(result.manifest_path)
    assert listed_index["embedding_signature"] == "mock"
    assert listed_index["collection_name"] == "notes-index"
    assert listed_index["legacy_compat"] is False
    assert listed_index["brain_pass"]["provider"] == "fallback"
    assert isinstance(listed_index["metadata"], dict)
    assert listed_index["metadata"]["document_title"] == "notes.txt"

    assert fetched == listed_index
    assert get_index("missing-index", index_dir=index_dir) is None

    listed_index["metadata"]["document_title"] = "changed"
    fresh = get_index("notes-index", index_dir=index_dir)

    assert fresh is not None
    assert fresh["metadata"]["document_title"] == "notes.txt"
