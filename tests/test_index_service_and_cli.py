from __future__ import annotations

from axiom_app.cli import main as cli_main
from axiom_app.services.index_service import (
    build_index_bundle,
    load_index_bundle,
    query_index_bundle,
    save_index_bundle,
)


def test_index_service_round_trips_bundle_and_queries(tmp_path) -> None:
    src = tmp_path / "notes.txt"
    src.write_text(
        "Ada Lovelace wrote the first algorithm.\n"
        "Grace Hopper popularized compilers.\n",
        encoding="utf-8",
    )

    settings = {"embedding_provider": "mock", "chunk_size": 60, "chunk_overlap": 10, "top_k": 2}
    bundle = build_index_bundle([str(src)], settings)
    out_path = save_index_bundle(bundle, target_path=tmp_path / "notes.axiom-index.json")
    loaded = load_index_bundle(out_path)
    result = query_index_bundle(loaded, "Who wrote the first algorithm?", settings)

    assert loaded.index_id == bundle.index_id
    assert len(loaded.chunks) >= 1
    assert result.sources
    assert result.sources[0].sid == "S1"


def test_cli_index_and_query_use_shared_backend(tmp_path, capsys) -> None:
    src = tmp_path / "paper.txt"
    out = tmp_path / "paper.axiom-index.json"
    src.write_text(
        "The installation guide explains how dependencies are installed.\n"
        "The query path reuses the same retrieval backend.\n",
        encoding="utf-8",
    )

    assert cli_main(["index", "--file", str(src), "--out", str(out)]) == 0
    assert out.exists()

    assert cli_main(
        ["query", "--file", str(src), "--index", str(out), "--question", "dependencies"]
    ) == 0
    stdout = capsys.readouterr().out
    assert "shared retrieval" in stdout
    assert "[S1]" in stdout or "[S2]" in stdout
