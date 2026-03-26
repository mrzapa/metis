"""Monolith-compatible run trace persistence."""

from __future__ import annotations

import json
import logging
import pathlib
from datetime import datetime, timedelta, timezone
from typing import Any

from metis_app.models.parity_types import TraceEvent

_AUDIT_LOGGER = logging.getLogger("metis.trace")

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

_UI_ARTIFACT_EVENT_TYPES: frozenset[str] = frozenset({
    "artifact_boundary_flag_state",
    "artifact_payload_detected",
    "artifact_render_attempt",
    "artifact_render_success",
    "artifact_render_failure",
    "artifact_render_fallback_markdown",
    "artifact_interaction",
    "artifact_runtime_attempt",
    "artifact_runtime_success",
    "artifact_runtime_failure",
    "artifact_runtime_skipped",
})
_FALLBACK_REASONS: tuple[str, ...] = (
    "feature_disabled",
    "no_artifacts",
    "invalid_payload",
    "render_error",
)
_RUNTIME_SKIP_REASONS: tuple[str, ...] = (
    "runtime_disabled",
    "unsupported_type",
    "payload_truncated",
    "invalid_payload",
)


def _parse_iso_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 6)


def _percent(numerator: int, denominator: int) -> float | None:
    value = _ratio(numerator, denominator)
    if value is None:
        return None
    return round(value * 100.0, 2)


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _eval_min(
    *,
    metric: str,
    observed: float | None,
    sample_count: int,
    go_min: float,
    rollback_min: float | None = None,
) -> dict[str, Any]:
    if observed is None or sample_count <= 0:
        return {
            "metric": metric,
            "status": "warn",
            "observed": observed,
            "sample_count": sample_count,
            "comparator": "min",
            "go_threshold": go_min,
            "rollback_threshold": rollback_min,
            "reason": "insufficient_samples",
        }
    if rollback_min is not None and observed < rollback_min:
        return {
            "metric": metric,
            "status": "fail",
            "observed": observed,
            "sample_count": sample_count,
            "comparator": "min",
            "go_threshold": go_min,
            "rollback_threshold": rollback_min,
            "reason": "below_rollback_threshold",
        }
    if observed >= go_min:
        status = "pass"
        reason = "meets_go_threshold"
    else:
        status = "warn"
        reason = "below_go_threshold"
    return {
        "metric": metric,
        "status": status,
        "observed": observed,
        "sample_count": sample_count,
        "comparator": "min",
        "go_threshold": go_min,
        "rollback_threshold": rollback_min,
        "reason": reason,
    }


def _eval_max(
    *,
    metric: str,
    observed: float | None,
    sample_count: int,
    go_max: float,
    rollback_max: float | None = None,
) -> dict[str, Any]:
    if observed is None or sample_count <= 0:
        return {
            "metric": metric,
            "status": "warn",
            "observed": observed,
            "sample_count": sample_count,
            "comparator": "max",
            "go_threshold": go_max,
            "rollback_threshold": rollback_max,
            "reason": "insufficient_samples",
        }
    if rollback_max is not None and observed > rollback_max:
        return {
            "metric": metric,
            "status": "fail",
            "observed": observed,
            "sample_count": sample_count,
            "comparator": "max",
            "go_threshold": go_max,
            "rollback_threshold": rollback_max,
            "reason": "above_rollback_threshold",
        }
    if observed <= go_max:
        status = "pass"
        reason = "meets_go_threshold"
    else:
        status = "warn"
        reason = "above_go_threshold"
    return {
        "metric": metric,
        "status": status,
        "observed": observed,
        "sample_count": sample_count,
        "comparator": "max",
        "go_threshold": go_max,
        "rollback_threshold": rollback_max,
        "reason": reason,
    }


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

    def aggregate_ui_artifact_summary(
        self,
        *,
        window_hours: int = 24,
        limit: int = 50_000,
    ) -> dict[str, Any]:
        """Aggregate persisted UI artifact telemetry and evaluate rollout thresholds."""
        normalized_window_hours = _positive_int(window_hours, 24)
        normalized_limit = _positive_int(limit, 50_000)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=normalized_window_hours)
        sampled_minimum_exposures = 300

        event_counts: dict[str, int] = {event_type: 0 for event_type in _UI_ARTIFACT_EVENT_TYPES}
        fallback_counts: dict[str, int] = {reason: 0 for reason in _FALLBACK_REASONS}
        runtime_skip_counts: dict[str, int] = {reason: 0 for reason in _RUNTIME_SKIP_REASONS}
        total_ui_events = 0
        events_with_run_id = 0
        events_with_source_boundary = 0
        events_with_client_timestamp = 0
        payload_detected_count = 0
        exposure_count = 0

        if self.runs_jsonl.exists():
            raw = self.runs_jsonl.read_text(encoding="utf-8", errors="replace").splitlines()
            lines = [line for line in raw if line.strip()][-normalized_limit:]

            for line in lines:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue

                event_type = str(row.get("event_type") or "").strip()
                if event_type not in _UI_ARTIFACT_EVENT_TYPES:
                    continue

                payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
                event_timestamp = _parse_iso_timestamp(row.get("timestamp"))
                if event_timestamp is None:
                    event_timestamp = _parse_iso_timestamp(payload.get("client_timestamp"))
                if event_timestamp is not None and event_timestamp < cutoff:
                    continue

                total_ui_events += 1

                run_id = str(row.get("run_id") or "").strip()
                if run_id:
                    events_with_run_id += 1

                source = str(payload.get("source") or "").strip()
                if source == "chat_artifact_boundary":
                    events_with_source_boundary += 1

                if str(payload.get("client_timestamp") or "").strip():
                    events_with_client_timestamp += 1

                include_in_rollout_metrics = bool(run_id)
                if not include_in_rollout_metrics:
                    continue

                event_counts[event_type] = event_counts.get(event_type, 0) + 1

                telemetry = payload.get("telemetry") if isinstance(payload.get("telemetry"), dict) else {}

                if event_type == "artifact_payload_detected":
                    payload_detected_count += 1
                    if bool(telemetry.get("has_valid_artifacts")):
                        exposure_count += 1
                elif event_type == "artifact_render_fallback_markdown":
                    reason = str(telemetry.get("reason") or "").strip()
                    if reason in fallback_counts:
                        fallback_counts[reason] = fallback_counts.get(reason, 0) + 1
                elif event_type == "artifact_runtime_skipped":
                    reason = str(telemetry.get("reason") or "").strip()
                    if reason in runtime_skip_counts:
                        runtime_skip_counts[reason] = runtime_skip_counts.get(reason, 0) + 1

        render_attempt_count = event_counts.get("artifact_render_attempt", 0)
        render_success_count = event_counts.get("artifact_render_success", 0)
        render_failure_count = event_counts.get("artifact_render_failure", 0)
        interaction_count = event_counts.get("artifact_interaction", 0)
        runtime_attempt_count = event_counts.get("artifact_runtime_attempt", 0)
        runtime_success_count = event_counts.get("artifact_runtime_success", 0)
        runtime_failure_count = event_counts.get("artifact_runtime_failure", 0)
        total_runtime_skipped = event_counts.get("artifact_runtime_skipped", 0)

        render_success_rate = _ratio(render_success_count, render_attempt_count)
        render_failure_rate = _ratio(render_failure_count, render_attempt_count)
        interaction_rate = _ratio(interaction_count, render_success_count)
        runtime_attempt_rate = _ratio(runtime_attempt_count, exposure_count)
        runtime_success_rate = _ratio(runtime_success_count, runtime_attempt_count)
        runtime_failure_rate = _ratio(runtime_failure_count, runtime_attempt_count)
        fallback_rate_by_reason = {
            reason: _ratio(count, payload_detected_count)
            for reason, count in fallback_counts.items()
        }
        runtime_skip_mix = {
            reason: _ratio(count, total_runtime_skipped)
            for reason, count in runtime_skip_counts.items()
        }

        data_quality = {
            "events_with_run_id_pct": _percent(events_with_run_id, total_ui_events),
            "events_with_source_boundary_pct": _percent(events_with_source_boundary, total_ui_events),
            "events_with_client_timestamp_pct": _percent(events_with_client_timestamp, total_ui_events),
        }

        render_error_fallback_rate = _ratio(fallback_counts.get("render_error", 0), exposure_count)
        invalid_payload_fallback_rate = _ratio(
            fallback_counts.get("invalid_payload", 0),
            payload_detected_count,
        )
        runtime_skip_invalid_payload_rate = _ratio(
            runtime_skip_counts.get("invalid_payload", 0),
            payload_detected_count,
        )
        runtime_skip_payload_truncated_rate = _ratio(
            runtime_skip_counts.get("payload_truncated", 0),
            payload_detected_count,
        )

        per_metric = {
            "render_success_rate": _eval_min(
                metric="render_success_rate",
                observed=render_success_rate,
                sample_count=render_attempt_count,
                go_min=0.995,
                rollback_min=0.985,
            ),
            "render_failure_rate": _eval_max(
                metric="render_failure_rate",
                observed=render_failure_rate,
                sample_count=render_attempt_count,
                go_max=0.003,
                rollback_max=0.01,
            ),
            "render_error_fallback_rate": _eval_max(
                metric="render_error_fallback_rate",
                observed=render_error_fallback_rate,
                sample_count=exposure_count,
                go_max=0.002,
                rollback_max=0.005,
            ),
            "invalid_payload_fallback_rate": _eval_max(
                metric="invalid_payload_fallback_rate",
                observed=invalid_payload_fallback_rate,
                sample_count=payload_detected_count,
                go_max=0.01,
                rollback_max=0.03,
            ),
            "interaction_rate": _eval_min(
                metric="interaction_rate",
                observed=interaction_rate,
                sample_count=render_success_count,
                go_min=0.08,
            ),
            "runtime_success_rate": _eval_min(
                metric="runtime_success_rate",
                observed=runtime_success_rate,
                sample_count=runtime_attempt_count,
                go_min=0.99,
                rollback_min=0.98,
            ),
            "runtime_failure_rate": _eval_max(
                metric="runtime_failure_rate",
                observed=runtime_failure_rate,
                sample_count=runtime_attempt_count,
                go_max=0.005,
                rollback_max=0.01,
            ),
            "runtime_skip_invalid_payload_rate": _eval_max(
                metric="runtime_skip_invalid_payload_rate",
                observed=runtime_skip_invalid_payload_rate,
                sample_count=payload_detected_count,
                go_max=0.02,
            ),
            "runtime_skip_payload_truncated_rate": _eval_max(
                metric="runtime_skip_payload_truncated_rate",
                observed=runtime_skip_payload_truncated_rate,
                sample_count=payload_detected_count,
                go_max=0.05,
            ),
            "events_with_run_id_pct": _eval_min(
                metric="events_with_run_id_pct",
                observed=(data_quality.get("events_with_run_id_pct") or 0.0) / 100.0
                if data_quality.get("events_with_run_id_pct") is not None
                else None,
                sample_count=total_ui_events,
                go_min=0.95,
            ),
        }

        failed_conditions = [
            f"{name}:{evaluation['reason']}"
            for name, evaluation in per_metric.items()
            if evaluation.get("status") == "fail"
        ]
        artifact_rollback_metrics = {
            "render_success_rate",
            "render_failure_rate",
            "render_error_fallback_rate",
            "invalid_payload_fallback_rate",
        }
        runtime_rollback_metrics = {
            "runtime_success_rate",
            "runtime_failure_rate",
        }
        artifact_rollback_failures = [
            metric
            for metric in artifact_rollback_metrics
            if per_metric.get(metric, {}).get("status") == "fail"
        ]
        runtime_rollback_failures = [
            metric
            for metric in runtime_rollback_metrics
            if per_metric.get(metric, {}).get("status") == "fail"
        ]

        go_required_metrics = {
            "render_success_rate",
            "render_failure_rate",
            "render_error_fallback_rate",
            "invalid_payload_fallback_rate",
            "interaction_rate",
            "runtime_success_rate",
            "runtime_failure_rate",
            "runtime_skip_invalid_payload_rate",
            "runtime_skip_payload_truncated_rate",
            "events_with_run_id_pct",
        }
        all_go_required_pass = all(
            per_metric.get(metric, {}).get("status") == "pass"
            for metric in go_required_metrics
        )

        if artifact_rollback_failures:
            overall_recommendation = "rollback_artifacts"
        elif runtime_rollback_failures:
            overall_recommendation = "rollback_runtime"
        elif all_go_required_pass and exposure_count >= sampled_minimum_exposures:
            overall_recommendation = "go"
        else:
            overall_recommendation = "hold"

        return {
            "window_hours": normalized_window_hours,
            "generated_at": now.isoformat(),
            "sampled_event_count": total_ui_events,
            "metrics": {
                "exposure_count": exposure_count,
                "render_attempt_count": render_attempt_count,
                "render_success_rate": render_success_rate,
                "render_failure_rate": render_failure_rate,
                "fallback_rate_by_reason": fallback_rate_by_reason,
                "interaction_rate": interaction_rate,
                "runtime_attempt_rate": runtime_attempt_rate,
                "runtime_success_rate": runtime_success_rate,
                "runtime_failure_rate": runtime_failure_rate,
                "runtime_skip_mix": runtime_skip_mix,
                "data_quality": data_quality,
            },
            "thresholds": {
                "per_metric": per_metric,
                "overall_recommendation": overall_recommendation,
                "failed_conditions": failed_conditions,
                "sample": {
                    "exposure_count": exposure_count,
                    "payload_detected_count": payload_detected_count,
                    "render_attempt_count": render_attempt_count,
                    "runtime_attempt_count": runtime_attempt_count,
                    "minimum_exposure_count_for_go": sampled_minimum_exposures,
                },
            },
        }
