"""Monolith-compatible run trace persistence."""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

from axiom_app.models.parity_types import TraceEvent

_AUDIT_LOGGER = logging.getLogger("axiom.trace")

# Key lifecycle event types that warrant an audit log entry.
# High-frequency events (token, retrieval_complete, subqueries) are excluded
# to avoid flooding the log file served by GET /v1/logs/tail.
_AUDIT_EVENT_TYPES: frozenset[str] = frozenset({
    "run_started",
    "stage_start",
    "stage_end",
    "iteration_start",
    "iteration_end",
    "validation_pass",
    "validation_fail",
    "tool_error",
    "error",
    "final",
    "action_required",
})


def _emit_audit_log(event: TraceEvent) -> None:
    """Emit a structured audit log line for key trace lifecycle events."""
    if event.event_type not in _AUDIT_EVENT_TYPES:
        return
    payload = event.payload or {}
    status = str(payload.get("status") or "").strip()
    parts = [f"run={event.run_id}", f"stage={event.stage}", f"type={event.event_type}"]
    if status:
        parts.append(f"status={status}")
    if event.latency_ms is not None:
        parts.append(f"latency_ms={int(event.latency_ms)}")
    dur = payload.get("duration_ms")
    if isinstance(dur, (int, float)):
        parts.append(f"duration_ms={int(dur)}")
    msg = "[trace] " + " ".join(parts)
    if event.event_type in {"error", "validation_fail", "tool_error"}:
        _AUDIT_LOGGER.warning(msg)
    else:
        _AUDIT_LOGGER.info(msg)

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
        _emit_audit_log(event)
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

    def aggregate_metrics(self, *, limit: int = 10_000) -> dict[str, Any]:
        """Return in-memory aggregated metrics derived from the trace event log.

        Scans up to *limit* most-recent events in ``runs.jsonl`` to bound
        memory use.  No external backend is required.

        Returns
        -------
        dict with:

        * ``total_events``      — total events scanned
        * ``event_type_counts`` — ``{event_type: count}``
        * ``status_counts``     — ``{status_value: count}`` (from payload)
        * ``duration_ms``       — ``{count, total_ms, avg_ms, min_ms, max_ms}``
        * ``last_run_id``       — run_id of the most recently appended event
        """
        _empty_dur: dict[str, Any] = {
            "count": 0, "total_ms": 0, "avg_ms": None, "min_ms": None, "max_ms": None
        }
        if not self.runs_jsonl.exists():
            return {
                "total_events": 0,
                "event_type_counts": {},
                "status_counts": {},
                "duration_ms": _empty_dur,
                "last_run_id": None,
            }

        raw = self.runs_jsonl.read_text(encoding="utf-8", errors="replace").splitlines()
        lines = [ln for ln in raw if ln.strip()][-limit:]

        event_type_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        durations: list[int] = []
        last_run_id: str | None = None
        total = 0

        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue

            total += 1

            event_type = str(row.get("event_type") or "").strip()
            if event_type:
                event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1

            # Duration: prefer top-level latency_ms, fall back to payload.duration_ms
            latency = row.get("latency_ms")
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            payload_dur = payload.get("duration_ms")
            dur: int | float | None = (
                latency
                if isinstance(latency, (int, float)) and latency is not None
                else (payload_dur if isinstance(payload_dur, (int, float)) else None)
            )
            if dur is not None and dur >= 0:
                durations.append(int(dur))

            # Status from payload
            status = str(payload.get("status") or "").strip()
            if status:
                status_counts[status] = status_counts.get(status, 0) + 1

            run_id = str(row.get("run_id") or "").strip()
            if run_id:
                last_run_id = run_id

        dur_total = sum(durations)
        return {
            "total_events": total,
            "event_type_counts": event_type_counts,
            "status_counts": status_counts,
            "duration_ms": {
                "count": len(durations),
                "total_ms": dur_total,
                "avg_ms": round(dur_total / len(durations)) if durations else None,
                "min_ms": min(durations) if durations else None,
                "max_ms": max(durations) if durations else None,
            },
            "last_run_id": last_run_id,
        }
