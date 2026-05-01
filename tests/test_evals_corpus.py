"""M16 Phase 2 — corpus shape + JSONL seed import tests.

The on-disk seed for the corpus is the existing
``evals/golden_dataset.jsonl`` file written by
``ArtifactConverter.export_as_eval``. ADR 0017 promises an idempotent
first-run import keyed on the JSONL row's ``eval_id``. These tests pin
that contract.
"""

from __future__ import annotations

import json
from pathlib import Path

from metis_app.evals.corpus import (
    EvalTask,
    eval_task_from_jsonl_row,
    import_seed_jsonl,
)
from metis_app.evals.store import EvalStore


SAMPLE_ROW = {
    "eval_id": "e-1",
    "derived_from_run": "run-1",
    "created_at": "2026-05-01T00:00:00+00:00",
    "label": "reinforce",
    "feedback_note": "great answer",
    "query": "what is METIS?",
    "mode": "Q&A",
    "context_chunks": [
        {"snippet": "snippet a", "source": "doc-a", "score": 0.91},
    ],
    "expected_strategy": "direct_synthesis",
    "expected_min_iterations": 1,
    "expected_min_citations": 1,
    "answer_preview": "METIS is a local-first AI workspace...",
    "assertions": [{"type": "no_error"}],
}


def _make_store(tmp_path: Path) -> EvalStore:
    store = EvalStore(tmp_path / "evals.db")
    store.init_db()
    return store


def test_eval_task_from_jsonl_row_uses_eval_id_as_task_id() -> None:
    task = eval_task_from_jsonl_row(SAMPLE_ROW)
    assert isinstance(task, EvalTask)
    assert task.task_id == "e-1"
    assert task.source_run_id == "run-1"
    assert task.task_type == "qa"
    assert task.query == "what is METIS?"
    assert task.expected_strategy == "direct_synthesis"
    assert task.expected_min_citations == 1
    assert task.expected_min_iterations == 1
    assert task.context_chunks[0]["source"] == "doc-a"
    assert task.assertions[0]["type"] == "no_error"
    assert "auto-seed" in task.tags


def test_eval_task_round_trip_through_payload_json() -> None:
    task = eval_task_from_jsonl_row(SAMPLE_ROW)
    payload = task.to_payload_dict()
    rebuilt = EvalTask.from_payload_dict(
        task_id=task.task_id,
        task_type=task.task_type,
        source_run_id=task.source_run_id,
        tags=task.tags,
        payload=payload,
    )
    assert rebuilt.query == task.query
    assert rebuilt.context_chunks == task.context_chunks
    assert rebuilt.assertions == task.assertions


def test_eval_task_task_type_inference_for_summary_mode() -> None:
    row = dict(SAMPLE_ROW)
    row["eval_id"] = "e-2"
    row["mode"] = "Summary"
    task = eval_task_from_jsonl_row(row)
    assert task.task_type == "summary"


def test_eval_task_task_type_inference_for_research_mode() -> None:
    row = dict(SAMPLE_ROW)
    row["eval_id"] = "e-3"
    row["mode"] = "Research"
    task = eval_task_from_jsonl_row(row)
    assert task.task_type == "retrieval"


def test_import_seed_jsonl_into_empty_db(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    jsonl = tmp_path / "golden_dataset.jsonl"
    jsonl.write_text(
        json.dumps(SAMPLE_ROW) + "\n", encoding="utf-8"
    )
    summary = import_seed_jsonl(store, jsonl)
    assert summary["imported"] == 1
    assert summary["skipped"] == 0
    assert summary["malformed"] == 0
    rows = store.list_tasks()
    assert {row.task_id for row in rows} == {"e-1"}


def test_import_seed_jsonl_is_idempotent(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    jsonl = tmp_path / "golden_dataset.jsonl"
    jsonl.write_text(json.dumps(SAMPLE_ROW) + "\n", encoding="utf-8")
    first = import_seed_jsonl(store, jsonl)
    second = import_seed_jsonl(store, jsonl)
    assert first["imported"] == 1
    # Second pass must not double-insert; the row's eval_id is already in
    # the tasks table and ADR 0017 keyed task_id on eval_id for exactly
    # this reason.
    assert second["imported"] == 0
    assert second["skipped"] == 1
    rows = store.list_tasks()
    assert len(rows) == 1


def test_import_seed_jsonl_appends_only_new_rows(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    jsonl = tmp_path / "golden_dataset.jsonl"
    row_a = dict(SAMPLE_ROW)
    row_b = dict(SAMPLE_ROW)
    row_b["eval_id"] = "e-2"
    row_b["query"] = "second question"
    jsonl.write_text(
        json.dumps(row_a) + "\n",
        encoding="utf-8",
    )
    first = import_seed_jsonl(store, jsonl)
    assert first["imported"] == 1
    # Append a second row to the JSONL — simulates the user labeling
    # another run as ``reinforce`` after the initial seed pass.
    with jsonl.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row_b) + "\n")
    second = import_seed_jsonl(store, jsonl)
    assert second["imported"] == 1
    assert second["skipped"] == 1
    rows = store.list_tasks()
    assert {row.task_id for row in rows} == {"e-1", "e-2"}


def test_import_seed_jsonl_with_missing_file_returns_zero(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    summary = import_seed_jsonl(store, tmp_path / "absent.jsonl")
    assert summary == {
        "imported": 0,
        "skipped": 0,
        "malformed": 0,
        "path": str(tmp_path / "absent.jsonl"),
    }


def test_import_seed_jsonl_skips_malformed_lines(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    jsonl = tmp_path / "golden_dataset.jsonl"
    jsonl.write_text(
        json.dumps(SAMPLE_ROW) + "\n" + "{not json\n",
        encoding="utf-8",
    )
    summary = import_seed_jsonl(store, jsonl)
    assert summary["imported"] == 1
    assert summary["malformed"] == 1
