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


# ----------------------------------------------------------------------
# Phase 2 review — non-reinforce label filter (PR #599 review item 1).
# The export endpoint at observe.py:177 forwards `_latest_label(run_id)`
# verbatim, so suppress/investigate rows DO reach the JSONL. The plan
# doc says only ``reinforce`` enters the corpus, so the import path
# must filter — otherwise negative or unresolved traces would be scored
# as if they were golden cases.
# ----------------------------------------------------------------------


def test_import_seed_jsonl_skips_suppress_label(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    jsonl = tmp_path / "golden_dataset.jsonl"
    row = dict(SAMPLE_ROW)
    row["eval_id"] = "e-suppress"
    row["label"] = "suppress"
    jsonl.write_text(json.dumps(row) + "\n", encoding="utf-8")
    summary = import_seed_jsonl(store, jsonl)
    assert summary["imported"] == 0
    assert summary["skipped"] == 1
    assert summary["malformed"] == 0
    assert store.list_tasks() == []


def test_import_seed_jsonl_skips_investigate_label(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    jsonl = tmp_path / "golden_dataset.jsonl"
    row = dict(SAMPLE_ROW)
    row["eval_id"] = "e-investigate"
    row["label"] = "investigate"
    jsonl.write_text(json.dumps(row) + "\n", encoding="utf-8")
    summary = import_seed_jsonl(store, jsonl)
    assert summary["imported"] == 0
    assert summary["skipped"] == 1
    assert store.list_tasks() == []


def test_import_seed_jsonl_skips_rows_with_missing_label(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    jsonl = tmp_path / "golden_dataset.jsonl"
    row = dict(SAMPLE_ROW)
    row["eval_id"] = "e-no-label"
    row.pop("label", None)
    jsonl.write_text(json.dumps(row) + "\n", encoding="utf-8")
    summary = import_seed_jsonl(store, jsonl)
    # Missing label means we cannot prove the run was a positive
    # reinforce — skip rather than guess. Counts as ``skipped`` so the
    # operator can see it in the summary.
    assert summary["imported"] == 0
    assert summary["skipped"] == 1
    assert store.list_tasks() == []


def test_import_seed_jsonl_imports_mixed_jsonl_only_reinforce(
    tmp_path: Path,
) -> None:
    store = _make_store(tmp_path)
    jsonl = tmp_path / "golden_dataset.jsonl"
    rows = [
        {**SAMPLE_ROW, "eval_id": "e-good", "label": "reinforce"},
        {**SAMPLE_ROW, "eval_id": "e-bad", "label": "suppress"},
        {**SAMPLE_ROW, "eval_id": "e-meh", "label": "investigate"},
    ]
    jsonl.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    summary = import_seed_jsonl(store, jsonl)
    assert summary["imported"] == 1
    assert summary["skipped"] == 2
    assert {row.task_id for row in store.list_tasks()} == {"e-good"}


# ----------------------------------------------------------------------
# Phase 2 review — items 3 + 4: idempotency must not depend on the
# pre-scan succeeding. The runtime contract is that an existing task
# row is left untouched even if the pre-scan returns an empty set
# (because we use ``INSERT ... ON CONFLICT DO NOTHING`` rather than
# ``ON CONFLICT DO UPDATE``).
# ----------------------------------------------------------------------


def test_import_seed_jsonl_preserves_existing_payload_on_repeat(
    tmp_path: Path,
) -> None:
    store = _make_store(tmp_path)
    jsonl = tmp_path / "golden_dataset.jsonl"
    jsonl.write_text(json.dumps(SAMPLE_ROW) + "\n", encoding="utf-8")
    import_seed_jsonl(store, jsonl)

    # Simulate a downstream edit to the stored task — e.g. a future
    # phase tagging tasks with custom metadata. The idempotent re-run
    # must NOT clobber that edit, even if the pre-scan path were ever
    # broken.
    original = store.get_task("e-1")
    assert original is not None
    edited_payload = json.loads(original.payload_json)
    edited_payload["mode"] = "edited-by-user"
    from metis_app.evals.store import EvalTaskRow

    store.upsert_task(
        EvalTaskRow(
            task_id=original.task_id,
            created_at=original.created_at,
            task_type=original.task_type,
            source_run_id=original.source_run_id,
            payload_json=json.dumps(edited_payload),
            tags_json=original.tags_json,
        )
    )

    # Re-import the unchanged JSONL — the existing edited payload must
    # survive.
    summary = import_seed_jsonl(store, jsonl)
    assert summary["imported"] == 0
    assert summary["skipped"] == 1
    fetched = store.get_task("e-1")
    assert fetched is not None
    assert json.loads(fetched.payload_json)["mode"] == "edited-by-user"
