from __future__ import annotations

import io
import sys

import pytest

from axiom_app.cli import main as cli_main
import axiom_app.models.app_model as app_model_module
from axiom_app.services.index_service import (
    build_index_bundle,
    load_index_manifest,
    load_index_bundle,
    list_index_manifests,
    query_index_bundle,
    save_index_bundle,
)
from axiom_app.services.vector_store import resolve_vector_store


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


def test_index_service_persists_manifest_and_lists_indexes(tmp_path) -> None:
    src = tmp_path / "notes.txt"
    src.write_text(
        "Structured evidence should survive restore.\n"
        "Index manifests should enumerate native stores.\n",
        encoding="utf-8",
    )

    settings = {"embedding_provider": "mock", "vector_db_type": "json"}
    bundle = build_index_bundle([str(src)], settings)
    manifest_path = save_index_bundle(bundle, index_dir=tmp_path / "indexes")
    manifest = load_index_manifest(manifest_path)
    loaded = load_index_bundle(manifest_path)
    listed = list_index_manifests(tmp_path / "indexes")

    assert manifest_path.name == "manifest.json"
    assert manifest.backend == "json"
    assert manifest.bundle_path == "bundle.json"
    assert manifest.document_count == 1
    assert loaded.index_path.endswith("manifest.json")
    assert listed and listed[0].index_id == bundle.index_id


def test_chroma_adapter_round_trips_queries_natively(tmp_path) -> None:
    pytest.importorskip("chromadb")

    src = tmp_path / "chroma.txt"
    src.write_text(
        "Axiom stores vectors in Chroma.\n"
        "Native backend queries should still return [S1].\n",
        encoding="utf-8",
    )
    settings = {
        "embedding_provider": "mock",
        "vector_db_type": "chroma",
        "top_k": 1,
    }
    adapter = resolve_vector_store(settings)
    bundle = adapter.build([str(src)], settings)
    manifest_path = adapter.save(bundle, index_dir=tmp_path / "indexes")
    restored = adapter.load(manifest_path)
    manifest = load_index_manifest(manifest_path)
    result = adapter.query(restored, "Where are vectors stored?", settings)

    assert manifest.backend == "chroma"
    assert (manifest_path.parent / "chroma").exists()
    assert manifest.collection_name
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


def test_cli_default_index_output_is_manifest_directory(tmp_path) -> None:
    src = tmp_path / "paper.txt"
    src.write_text("Manifest-first CLI indexing.\n", encoding="utf-8")

    assert cli_main(["index", "--file", str(src)]) == 0

    manifest_path = src.with_name(src.name + ".axiom-index") / "manifest.json"
    assert manifest_path.exists()


def test_cli_index_handles_cp1252_stdout(tmp_path, monkeypatch) -> None:
    src = tmp_path / "paper.txt"
    src.write_text("ASCII only runtime smoke.\n", encoding="utf-8")

    raw = io.BytesIO()
    stdout = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", stdout)

    assert cli_main(["index", "--file", str(src)]) == 0

    stdout.flush()
    output = raw.getvalue().decode("cp1252")
    assert "Index written ->" in output


def test_cli_skills_commands_and_query_show_skills(tmp_path, monkeypatch, capsys) -> None:
    defaults = tmp_path / "default_settings.json"
    user_settings = tmp_path / "settings.json"
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    research_dir = skills_dir / "research-claims"
    research_dir.mkdir()
    (research_dir / "SKILL.md").write_text(
        "---\n"
        "id: research-claims\n"
        "name: Research Claims\n"
        "description: Map evidence-backed claims.\n"
        "enabled_by_default: false\n"
        "priority: 8\n"
        "triggers:\n"
        '  keywords: ["claim", "counterclaim"]\n'
        '  modes: ["Research"]\n'
        '  file_types: [".txt"]\n'
        '  output_styles: ["Structured report"]\n'
        "runtime_overrides:\n"
        '  selected_mode: "Research"\n'
        "  retrieval_k: 9\n"
        "  top_k: 4\n"
        "---\n"
        "Focus on claims and counterclaims.\n",
        encoding="utf-8",
    )
    defaults.write_text(
        io.StringIO(
            '{"embedding_provider":"mock","embedding_model":"mock-embed","llm_provider":"mock","llm_model":"mock-v1","vector_db_type":"json","chunk_size":120,"chunk_overlap":0,"retrieval_k":3,"top_k":2,"selected_mode":"Q&A","output_style":"Structured report","skills":{"enabled":{}}}'
        ).getvalue(),
        encoding="utf-8",
    )
    user_settings.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(app_model_module, "_DEFAULT_SETTINGS_PATH", defaults)
    monkeypatch.setattr(app_model_module, "_USER_SETTINGS_PATH", user_settings)
    monkeypatch.setattr(app_model_module, "_SKILLS_DIR", skills_dir)

    assert cli_main(["skills", "list"]) == 0
    stdout = capsys.readouterr().out
    assert "research-claims" in stdout

    assert cli_main(["skills", "enable", "research-claims"]) == 0
    persisted = user_settings.read_text(encoding="utf-8")
    assert '"research-claims": true' in persisted

    src = tmp_path / "claims.txt"
    src.write_text("The document contains a claim and a counterclaim.\n", encoding="utf-8")
    assert cli_main(
        [
            "query",
            "--file",
            str(src),
            "--question",
            "map the claim and counterclaim",
            "--show-skills",
            "--pin-skill",
            "research-claims",
        ]
    ) == 0
    stdout = capsys.readouterr().out
    assert "Primary  : research-claims" in stdout
    assert "research-claims: pinned for session" in stdout
