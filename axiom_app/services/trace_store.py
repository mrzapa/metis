"""Monolith-compatible run trace persistence."""

from __future__ import annotations

import json
import pathlib
from typing import Any

from axiom_app.models.parity_types import TraceEvent

_HERE = pathlib.Path(__file__).resolve().parent
_PACKAGE_ROOT = _HERE.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_DEFAULT_TRACE_DIR = _REPO_ROOT / "traces"


class TraceStore:
    """Persist run traces to runs.jsonl and per-run JSONL files."""

    def __init__(self, base_dir: str | pathlib.Path | None = None) -> None:
        self.base_dir = pathlib.Path(base_dir or _DEFAULT_TRACE_DIR)
        self.runs_dir = self.base_dir / "runs"
        self.runs_jsonl = self.base_dir / "runs.jsonl"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def append(self, record: TraceEvent | dict[str, Any]) -> TraceEvent:
        event = record if isinstance(record, TraceEvent) else TraceEvent.from_payload(record)
        line = json.dumps(event.to_payload(), ensure_ascii=False, sort_keys=True)
        for path in (self.runs_jsonl, self.runs_dir / f"{event.run_id}.jsonl"):
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return event

    def append_event(self, **kwargs: Any) -> TraceEvent:
        event = TraceEvent.create(**kwargs)
        return self.append(event)

    @staticmethod
    def _serialize_run_event_row(row: dict[str, Any], fallback_run_id: str) -> dict[str, Any]:
        payload = row.get("payload")
        citations = row.get("citations_chosen")
        if citations is None:
            citations_chosen: list[str] | None = None
        elif isinstance(citations, (list, tuple, set)):
            citations_chosen = [str(item) for item in citations]
        else:
            citations_chosen = [str(citations)]
        return {
            "run_id": str(row.get("run_id") or fallback_run_id or ""),
            "timestamp": str(row.get("timestamp") or ""),
            "stage": str(row.get("stage") or ""),
            "event_type": str(row.get("event_type") or ""),
            "payload": dict(payload) if isinstance(payload, dict) else {},
            "citations_chosen": citations_chosen,
        }

    def read_run(self, run_id: str) -> list[dict[str, Any]]:
        path = self.runs_dir / f"{run_id}.jsonl"
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows

    def read_run_events(self, run_id: str) -> list[dict[str, Any]]:
        normalized_run_id = str(run_id or "").strip()
        return [
            self._serialize_run_event_row(row, normalized_run_id)
            for row in self.read_run(normalized_run_id)
        ]

    def read_runs(self, run_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for run_id in run_ids:
            normalized = str(run_id or "").strip()
            if not normalized:
                continue
            result[normalized] = self.read_run(normalized)
        return result
