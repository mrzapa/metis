"""Eval task corpus — the user-specific set of things the companion can
be tested on.

The on-disk seed for the corpus is the existing
``evals/golden_dataset.jsonl`` written by
``ArtifactConverter.export_as_eval``. ADR 0017 §3 makes the JSONL the
seed-and-audit log and the SQLite ``tasks`` table the queryable index;
this module owns the conversion between those two representations
plus an idempotent first-run import.

The runner (Phase 3) reads from the SQLite index, never from the JSONL
directly — keeps a single source of truth at execution time while
preserving the human-eyeballable JSONL audit log.
"""

from __future__ import annotations

import json
import logging
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .store import EvalStore, EvalTaskRow

log = logging.getLogger(__name__)


# Only ``reinforce``-labeled rows enter the corpus. The export endpoint
# at ``observe.py:177`` forwards ``_latest_label(run_id)`` verbatim,
# so suppress / investigate rows DO appear in
# ``evals/golden_dataset.jsonl`` and must be filtered here. Plan-doc
# semantics (Phase 2): tasks enter the corpus when the user explicitly
# labels a run ``reinforce``.
_IMPORTABLE_LABELS: frozenset[str] = frozenset({"reinforce"})


_TASK_TYPE_BY_MODE: dict[str, str] = {
    "q&a": "qa",
    "qa": "qa",
    "summary": "summary",
    "research": "retrieval",
    "evidence pack": "retrieval",
    "tutor": "qa",
    "reflection": "reflection",
}


def _infer_task_type(mode: str) -> str:
    key = (mode or "").strip().lower()
    return _TASK_TYPE_BY_MODE.get(key, "custom")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EvalTask:
    """Logical eval task model.

    Mirrors the shape produced by ``ArtifactConverter.export_as_eval``
    (see ``metis_app/services/artifact_converter.py``) so the seed
    import is a near-trivial relabel rather than a translation. The
    JSON payload is what gets persisted in the ``tasks.payload_json``
    column; the dataclass is the in-memory ergonomic surface.
    """

    task_id: str
    created_at: str
    task_type: str
    source_run_id: str | None
    query: str
    mode: str = ""
    context_chunks: list[dict[str, Any]] = field(default_factory=list)
    expected_strategy: str = ""
    expected_min_iterations: int = 0
    expected_min_citations: int = 0
    answer_preview: str = ""
    assertions: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_payload_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "mode": self.mode,
            "context_chunks": list(self.context_chunks),
            "expected_strategy": self.expected_strategy,
            "expected_min_iterations": int(self.expected_min_iterations),
            "expected_min_citations": int(self.expected_min_citations),
            "answer_preview": self.answer_preview,
            "assertions": list(self.assertions),
        }

    @classmethod
    def from_payload_dict(
        cls,
        *,
        task_id: str,
        task_type: str,
        source_run_id: str | None,
        tags: list[str],
        payload: dict[str, Any],
        created_at: str | None = None,
    ) -> "EvalTask":
        return cls(
            task_id=task_id,
            created_at=created_at or _now_iso(),
            task_type=task_type,
            source_run_id=source_run_id,
            query=str(payload.get("query") or ""),
            mode=str(payload.get("mode") or ""),
            context_chunks=list(payload.get("context_chunks") or []),
            expected_strategy=str(payload.get("expected_strategy") or ""),
            expected_min_iterations=int(payload.get("expected_min_iterations") or 0),
            expected_min_citations=int(payload.get("expected_min_citations") or 0),
            answer_preview=str(payload.get("answer_preview") or ""),
            assertions=list(payload.get("assertions") or []),
            tags=list(tags),
        )

    def to_storage_row(self) -> EvalTaskRow:
        return EvalTaskRow(
            task_id=self.task_id,
            created_at=self.created_at,
            task_type=self.task_type,
            source_run_id=self.source_run_id,
            payload_json=json.dumps(self.to_payload_dict(), ensure_ascii=False),
            tags_json=json.dumps(list(self.tags), ensure_ascii=False),
        )


def eval_task_from_jsonl_row(row: dict[str, Any]) -> EvalTask:
    """Convert one ``golden_dataset.jsonl`` row into an ``EvalTask``.

    The JSONL row's ``eval_id`` becomes the task's ``task_id`` (ADR 0017
    §3 — keeps the seed import idempotent across reruns).
    """

    eval_id = str(row.get("eval_id") or "").strip()
    if not eval_id:
        raise ValueError("JSONL row missing 'eval_id'")
    mode = str(row.get("mode") or "")
    return EvalTask(
        task_id=eval_id,
        created_at=str(row.get("created_at") or _now_iso()),
        task_type=_infer_task_type(mode),
        source_run_id=str(row.get("derived_from_run") or "") or None,
        query=str(row.get("query") or ""),
        mode=mode,
        context_chunks=list(row.get("context_chunks") or []),
        expected_strategy=str(row.get("expected_strategy") or ""),
        expected_min_iterations=int(row.get("expected_min_iterations") or 0),
        expected_min_citations=int(row.get("expected_min_citations") or 0),
        answer_preview=str(row.get("answer_preview") or ""),
        assertions=list(row.get("assertions") or []),
        tags=["auto-seed"],
    )


def import_seed_jsonl(
    store: EvalStore, jsonl_path: pathlib.Path
) -> dict[str, Any]:
    """Idempotently import seed rows from ``golden_dataset.jsonl``.

    Returns a summary dict with counts of ``imported`` / ``skipped`` /
    ``malformed`` rows plus the resolved ``path``. Existing rows are
    left untouched via :meth:`EvalStore.insert_task_if_absent`, which
    uses ``ON CONFLICT DO NOTHING`` rather than ``ON CONFLICT DO
    UPDATE`` — matching ADR 0017 §3's idempotency contract regardless
    of whether a pre-scan succeeds, and avoiding the previous
    O(corpus) round-trip needed to enumerate ``task_id``s up front.

    Skip semantics:

    - Rows whose ``label`` is not in :data:`_IMPORTABLE_LABELS` (today
      that means anything except ``reinforce``) are counted as
      ``skipped``, never as ``malformed``. The plan-doc rule is that
      only reinforce-labeled traces become tasks — suppress and
      investigate are grading signals on runs, not corpus members.
    - Rows whose ``task_id`` is already present are counted as
      ``skipped``.
    - JSON-decode failures, non-dict rows, missing ``eval_id``, and
      shape errors raised from :func:`eval_task_from_jsonl_row` are
      counted as ``malformed``.
    """

    summary: dict[str, Any] = {
        "imported": 0,
        "skipped": 0,
        "malformed": 0,
        "path": str(jsonl_path),
    }
    if not jsonl_path.exists():
        return summary

    try:
        with jsonl_path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    row = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    log.warning("Skipping malformed seed row: %s", exc)
                    summary["malformed"] += 1
                    continue
                if not isinstance(row, dict):
                    summary["malformed"] += 1
                    continue
                eval_id = str(row.get("eval_id") or "").strip()
                if not eval_id:
                    summary["malformed"] += 1
                    continue
                label = str(row.get("label") or "").strip().lower()
                if label not in _IMPORTABLE_LABELS:
                    summary["skipped"] += 1
                    continue
                try:
                    task = eval_task_from_jsonl_row(row)
                except (TypeError, ValueError) as exc:
                    log.warning("Skipping seed row %s: %s", eval_id, exc)
                    summary["malformed"] += 1
                    continue
                inserted = store.insert_task_if_absent(task.to_storage_row())
                if inserted:
                    summary["imported"] += 1
                else:
                    summary["skipped"] += 1
    except OSError as exc:
        log.warning("Could not read seed JSONL %s: %s", jsonl_path, exc)
        return summary

    return summary
