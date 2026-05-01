"""M16 Phase 2 — schema + CRUD tests for ``metis_app.evals.store``.

ADR 0017 locks the three-table schema (``tasks`` / ``runs`` /
``generations``) into a dedicated ``evals.db``. These tests exercise that
contract directly so future schema drift is caught at the unit layer
before it leaks into the runner (Phase 3) or the report surface
(Phase 5).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from metis_app.evals.store import (
    DEFAULT_DB_ENV_VAR,
    EvalGeneration,
    EvalRun,
    EvalStore,
    EvalTaskRow,
    get_default_store,
    reset_default_store_for_tests,
)


def _make_store(tmp_path: Path) -> EvalStore:
    store = EvalStore(tmp_path / "evals.db")
    store.init_db()
    return store


def _task_row(*, task_id: str = "", task_type: str = "qa") -> EvalTaskRow:
    tid = task_id or str(uuid.uuid4())
    return EvalTaskRow(
        task_id=tid,
        created_at="2026-05-01T00:00:00+00:00",
        task_type=task_type,
        source_run_id="run-source",
        payload_json=json.dumps({"query": "what?", "mode": "Q&A"}),
        tags_json=json.dumps(["auto-seed"]),
    )


def test_init_db_creates_three_tables(tmp_path: Path) -> None:
    _make_store(tmp_path)
    with sqlite3.connect(str(tmp_path / "evals.db")) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    names = {row[0] for row in rows}
    assert {"tasks", "runs", "generations"}.issubset(names)


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    # Running init_db twice must not raise — fresh installs and existing
    # installs both pass through the same code path on every startup.
    store.init_db()


def test_upsert_task_round_trip(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    row = _task_row()
    store.upsert_task(row)
    fetched = store.get_task(row.task_id)
    assert fetched is not None
    assert fetched.task_id == row.task_id
    assert fetched.task_type == row.task_type
    assert json.loads(fetched.payload_json)["query"] == "what?"
    assert json.loads(fetched.tags_json) == ["auto-seed"]


def test_upsert_task_is_idempotent_on_same_id(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    row = _task_row(task_id="t1")
    store.upsert_task(row)
    updated = EvalTaskRow(
        task_id="t1",
        created_at=row.created_at,
        task_type="summary",
        source_run_id=row.source_run_id,
        payload_json=json.dumps({"query": "different", "mode": "Summary"}),
        tags_json=row.tags_json,
    )
    store.upsert_task(updated)
    fetched = store.get_task("t1")
    assert fetched is not None
    assert fetched.task_type == "summary"
    assert json.loads(fetched.payload_json)["query"] == "different"


def test_list_tasks_filter_by_type(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.upsert_task(_task_row(task_id="qa1", task_type="qa"))
    store.upsert_task(_task_row(task_id="qa2", task_type="qa"))
    store.upsert_task(_task_row(task_id="s1", task_type="summary"))
    qa = store.list_tasks(task_type="qa")
    summary = store.list_tasks(task_type="summary")
    assert {row.task_id for row in qa} == {"qa1", "qa2"}
    assert {row.task_id for row in summary} == {"s1"}


def test_list_tasks_returns_all_when_no_filter(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.upsert_task(_task_row(task_id="qa1", task_type="qa"))
    store.upsert_task(_task_row(task_id="s1", task_type="summary"))
    rows = store.list_tasks()
    assert {row.task_id for row in rows} == {"qa1", "s1"}


def test_insert_and_list_runs(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.upsert_task(_task_row(task_id="t1"))
    run = EvalRun(
        run_id="r1",
        task_id="t1",
        generation_id="g1",
        created_at="2026-05-01T00:00:00+00:00",
        trace_run_id="trace-r1",
        signals_json=json.dumps({"trace_label": 1.0}),
        aggregate_score=0.85,
        output_text="answer",
        review_required=False,
    )
    store.insert_run(run)
    rows = store.list_runs(task_id="t1")
    assert len(rows) == 1
    assert rows[0].run_id == "r1"
    assert rows[0].review_required is False
    assert rows[0].aggregate_score == pytest.approx(0.85)


def test_list_runs_filters_by_generation(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.upsert_task(_task_row(task_id="t1"))
    store.insert_run(
        EvalRun(
            run_id="r1",
            task_id="t1",
            generation_id="g_old",
            created_at="2026-04-30T00:00:00+00:00",
            trace_run_id="",
            signals_json="{}",
            aggregate_score=None,
            output_text="",
            review_required=False,
        )
    )
    store.insert_run(
        EvalRun(
            run_id="r2",
            task_id="t1",
            generation_id="g_new",
            created_at="2026-05-01T00:00:00+00:00",
            trace_run_id="",
            signals_json="{}",
            aggregate_score=None,
            output_text="",
            review_required=False,
        )
    )
    rows = store.list_runs(task_id="t1", generation_id="g_new")
    assert {row.run_id for row in rows} == {"r2"}


def test_review_required_round_trip(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.upsert_task(_task_row(task_id="t1"))
    store.insert_run(
        EvalRun(
            run_id="r1",
            task_id="t1",
            generation_id="g1",
            created_at="2026-05-01T00:00:00+00:00",
            trace_run_id="",
            signals_json="{}",
            aggregate_score=None,
            output_text="",
            review_required=True,
        )
    )
    rows = store.list_runs(task_id="t1")
    assert rows[0].review_required is True


def test_upsert_generation_round_trip(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    gen = EvalGeneration(
        generation_id="g1",
        first_seen_at="2026-05-01T00:00:00+00:00",
        runtime_spec_json=json.dumps({"llm_provider": "anthropic"}),
        lora_adapter_id=None,
        skill_set_hash="sk1",
        settings_hash="st1",
        notes="initial",
    )
    store.upsert_generation(gen)
    fetched = store.get_generation("g1")
    assert fetched is not None
    assert fetched.skill_set_hash == "sk1"
    assert fetched.notes == "initial"


def test_upsert_generation_is_idempotent(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    gen = EvalGeneration(
        generation_id="g1",
        first_seen_at="2026-05-01T00:00:00+00:00",
        runtime_spec_json="{}",
        lora_adapter_id=None,
        skill_set_hash="sk1",
        settings_hash="st1",
        notes="",
    )
    store.upsert_generation(gen)
    # First-seen-at must remain stable across repeat upserts so
    # generation comparison windows do not silently drift.
    later = EvalGeneration(
        generation_id="g1",
        first_seen_at="2099-01-01T00:00:00+00:00",
        runtime_spec_json="{}",
        lora_adapter_id=None,
        skill_set_hash="sk1",
        settings_hash="st1",
        notes="rewritten",
    )
    store.upsert_generation(later)
    fetched = store.get_generation("g1")
    assert fetched is not None
    assert fetched.first_seen_at == "2026-05-01T00:00:00+00:00"


def test_db_path_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "override.db"
    monkeypatch.setenv(DEFAULT_DB_ENV_VAR, str(db_path))
    reset_default_store_for_tests()
    try:
        store = get_default_store()
        store.init_db()
        assert db_path.exists()
    finally:
        reset_default_store_for_tests()


def test_get_default_store_returns_singleton(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DEFAULT_DB_ENV_VAR, str(tmp_path / "default.db"))
    reset_default_store_for_tests()
    try:
        a = get_default_store()
        b = get_default_store()
        assert a is b
    finally:
        reset_default_store_for_tests()


# ----------------------------------------------------------------------
# Phase 2 review (PR #599 items 3 + 4) — insert_task_if_absent provides
# the "do not overwrite" semantics seed import requires. The pre-existing
# upsert_task uses ON CONFLICT DO UPDATE, which is the right primitive
# for runner-driven mutations but the wrong primitive for idempotent
# imports.
# ----------------------------------------------------------------------


def test_insert_task_if_absent_returns_true_on_first_insert(
    tmp_path: Path,
) -> None:
    store = _make_store(tmp_path)
    row = _task_row(task_id="t1")
    inserted = store.insert_task_if_absent(row)
    assert inserted is True
    fetched = store.get_task("t1")
    assert fetched is not None


def test_insert_task_if_absent_returns_false_when_exists(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    first = _task_row(task_id="t1", task_type="qa")
    store.insert_task_if_absent(first)
    second = _task_row(task_id="t1", task_type="summary")
    inserted = store.insert_task_if_absent(second)
    assert inserted is False
    fetched = store.get_task("t1")
    assert fetched is not None
    # The original row survives — the second call must not overwrite,
    # even on a payload-changing input.
    assert fetched.task_type == "qa"


# ----------------------------------------------------------------------
# Phase 2 review (PR #599 item 5) — singleton construction must be
# guarded by a lock so concurrent first callers cannot race each other
# into building two EvalStore instances under the same env override.
# ----------------------------------------------------------------------


def test_get_default_store_singleton_under_concurrent_first_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    monkeypatch.setenv(DEFAULT_DB_ENV_VAR, str(tmp_path / "concurrent.db"))
    reset_default_store_for_tests()

    barrier = threading.Barrier(8)
    instances: list[EvalStore] = []
    lock = threading.Lock()

    def _race() -> None:
        barrier.wait()
        store = get_default_store()
        with lock:
            instances.append(store)

    try:
        threads = [threading.Thread(target=_race) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(instances) == 8
        first = instances[0]
        for other in instances[1:]:
            assert other is first
    finally:
        reset_default_store_for_tests()


# ----------------------------------------------------------------------
# Phase 2 review (PR #599 item 6) — close() releases the shared
# in-memory connection (and any future shared file connection); reset
# helper must call close before clearing the singleton.
# ----------------------------------------------------------------------


def test_close_releases_shared_in_memory_connection() -> None:
    store = EvalStore(":memory:")
    store.init_db()
    # Sanity-check we can still query before close.
    assert store.list_tasks() == []
    store.close()
    # Subsequent operations must not use the closed connection.
    with pytest.raises(Exception):
        store.list_tasks()


def test_close_is_idempotent() -> None:
    store = EvalStore(":memory:")
    store.init_db()
    store.close()
    # A second close is a no-op rather than an error.
    store.close()


def test_reset_default_store_closes_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DEFAULT_DB_ENV_VAR, ":memory:")
    reset_default_store_for_tests()
    store = get_default_store()
    # In-memory store has a shared connection — reset must close it
    # rather than letting it dangle.
    reset_default_store_for_tests()
    with pytest.raises(Exception):
        store.list_tasks()
    # And after reset, a fresh store can be obtained.
    reset_default_store_for_tests()
    next_store = get_default_store()
    assert next_store is not store
    reset_default_store_for_tests()
