from __future__ import annotations

import json
import uuid

from metis_app.engine.runs import RunEvent, make_run_id, now_iso_utc
from metis_app.services.trace_store import TraceStore


class _CustomValue:
    def __str__(self) -> str:
        return "custom-value"


def test_trace_store_append_read_and_project_events(tmp_path) -> None:
    store = TraceStore(tmp_path)
    event = store.append_event(
        run_id="run-1",
        stage="synthesis",
        event_type="llm_response",
        iteration=2,
        latency_ms=15,
        payload={"response_preview": "hello", "nested": {"count": 1}},
        citations_chosen=["S1", "S2"],
    )

    rows = store.read_run("run-1")

    assert len(rows) == 1
    assert rows[0]["event_id"] == event.event_id
    assert rows[0]["iteration"] == 2
    assert rows[0]["payload"] == {"response_preview": "hello", "nested": {"count": 1}}
    assert rows[0]["citations_chosen"] == ["S1", "S2"]

    aggregated = store.read_runs(["run-1"])

    assert aggregated == {"run-1": rows}

    run_events = store.read_run_events("run-1")

    assert run_events == [
        {
            "run_id": "run-1",
            "timestamp": rows[0]["timestamp"],
            "stage": "synthesis",
            "event_type": "llm_response",
            "payload": {"response_preview": "hello", "nested": {"count": 1}},
            "citations_chosen": ["S1", "S2"],
        }
    ]
    json.dumps(run_events)


def test_trace_store_projection_normalizes_compact_run_event_shape(tmp_path) -> None:
    store = TraceStore(tmp_path)
    raw_row = {
        "run_id": "run-2",
        "timestamp": "2026-03-13T10:00:00+00:00",
        "stage": "validation",
        "event_type": "claim_grounding",
        "payload": "not-a-dict",
    }
    (store.runs_dir / "run-2.jsonl").write_text(json.dumps(raw_row) + "\n", encoding="utf-8")

    run_events = store.read_run_events("run-2")

    assert run_events == [
        {
            "run_id": "run-2",
            "timestamp": "2026-03-13T10:00:00+00:00",
            "stage": "validation",
            "event_type": "claim_grounding",
            "payload": {},
            "citations_chosen": None,
        }
    ]
    json.dumps(run_events)


def test_run_event_to_payload_normalizes_nested_values_for_json() -> None:
    event = RunEvent(
        run_id="run-3",
        timestamp="2026-03-13T11:00:00+00:00",
        stage="grounding",
        event_type="langextract_html",
        payload={
            5: "five",
            "items": (1, 2, 3),
            "mapping": {"path": _CustomValue()},
            "labels": {"alpha", "beta"},
            "custom": _CustomValue(),
        },
        citations_chosen=None,
    )

    payload = event.to_payload()

    assert payload["run_id"] == "run-3"
    assert payload["timestamp"] == "2026-03-13T11:00:00+00:00"
    assert payload["stage"] == "grounding"
    assert payload["event_type"] == "langextract_html"
    assert payload["payload"]["5"] == "five"
    assert payload["payload"]["items"] == [1, 2, 3]
    assert payload["payload"]["mapping"] == {"path": "custom-value"}
    assert sorted(payload["payload"]["labels"]) == ["alpha", "beta"]
    assert payload["payload"]["custom"] == "custom-value"
    assert payload["citations_chosen"] is None
    json.dumps(payload)


def test_run_event_helpers_return_serializable_identifiers() -> None:
    timestamp = now_iso_utc()
    run_id = make_run_id()

    assert isinstance(timestamp, str)
    assert timestamp
    assert str(uuid.UUID(run_id)) == run_id


# ---------------------------------------------------------------------------
# aggregate_metrics
# ---------------------------------------------------------------------------


class TestAggregateMetrics:
    def test_empty_store_returns_zero_counts(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        metrics = store.aggregate_metrics()

        assert metrics["total_events"] == 0
        assert metrics["event_type_counts"] == {}
        assert metrics["status_counts"] == {}
        assert metrics["duration_ms"]["count"] == 0
        assert metrics["duration_ms"]["avg_ms"] is None
        assert metrics["last_run_id"] is None

    def test_counts_by_event_type(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        store.append_event(run_id="r1", stage="synthesis", event_type="final", payload={})
        store.append_event(run_id="r1", stage="synthesis", event_type="final", payload={})
        store.append_event(run_id="r1", stage="retrieval", event_type="run_started", payload={})

        metrics = store.aggregate_metrics()

        assert metrics["total_events"] == 3
        assert metrics["event_type_counts"]["final"] == 2
        assert metrics["event_type_counts"]["run_started"] == 1

    def test_counts_by_status(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        store.append_event(run_id="r1", stage="s", event_type="validation_pass", payload={"status": "success"})
        store.append_event(run_id="r1", stage="s", event_type="validation_fail", payload={"status": "error"})
        store.append_event(run_id="r1", stage="s", event_type="validation_fail", payload={"status": "error"})

        metrics = store.aggregate_metrics()

        assert metrics["status_counts"]["success"] == 1
        assert metrics["status_counts"]["error"] == 2

    def test_duration_aggregates_from_latency_ms(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        store.append_event(run_id="r1", stage="s", event_type="stage_end", latency_ms=100, payload={})
        store.append_event(run_id="r1", stage="s", event_type="stage_end", latency_ms=200, payload={})
        store.append_event(run_id="r1", stage="s", event_type="stage_end", latency_ms=300, payload={})

        metrics = store.aggregate_metrics()
        dur = metrics["duration_ms"]

        assert dur["count"] == 3
        assert dur["total_ms"] == 600
        assert dur["avg_ms"] == 200
        assert dur["min_ms"] == 100
        assert dur["max_ms"] == 300

    def test_duration_aggregates_from_payload_duration_ms(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        store.append_event(run_id="r1", stage="s", event_type="stage_end", payload={"duration_ms": 150})

        metrics = store.aggregate_metrics()
        dur = metrics["duration_ms"]

        assert dur["count"] == 1
        assert dur["total_ms"] == 150
        assert dur["avg_ms"] == 150

    def test_last_run_id_reflects_most_recent_event(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        store.append_event(run_id="run-first", stage="s", event_type="run_started", payload={})
        store.append_event(run_id="run-second", stage="s", event_type="final", payload={})

        metrics = store.aggregate_metrics()

        assert metrics["last_run_id"] == "run-second"

    def test_limit_parameter_bounds_events_scanned(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        for _ in range(20):
            store.append_event(run_id="r1", stage="s", event_type="token", payload={})

        metrics = store.aggregate_metrics(limit=5)

        assert metrics["total_events"] == 5

    def test_result_is_json_serializable(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        store.append_event(run_id="r1", stage="s", event_type="final", payload={"status": "success"})

        metrics = store.aggregate_metrics()

        import json
        json.dumps(metrics)  # must not raise


class TestAggregateUiArtifactSummary:
    @staticmethod
    def _write_ui_event_lines(store: TraceStore, rows: list[dict[str, object]]) -> None:
        lines = [json.dumps(row, sort_keys=True) for row in rows]
        store.runs_jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_aggregation_math_on_known_fixtures(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        self._write_ui_event_lines(
            store,
            [
                {
                    "run_id": "run-1",
                    "timestamp": "2026-03-23T10:00:00+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_payload_detected",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:00Z",
                        "telemetry": {"has_valid_artifacts": True},
                    },
                },
                {
                    "run_id": "run-1",
                    "timestamp": "2026-03-23T10:00:01+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_render_attempt",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:01Z",
                        "telemetry": {},
                    },
                },
                {
                    "run_id": "run-1",
                    "timestamp": "2026-03-23T10:00:02+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_render_success",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:02Z",
                        "telemetry": {},
                    },
                },
                {
                    "run_id": "run-1",
                    "timestamp": "2026-03-23T10:00:03+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_interaction",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:03Z",
                        "telemetry": {},
                    },
                },
                {
                    "run_id": "run-1",
                    "timestamp": "2026-03-23T10:00:04+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_runtime_attempt",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:04Z",
                        "telemetry": {},
                    },
                },
                {
                    "run_id": "run-1",
                    "timestamp": "2026-03-23T10:00:05+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_runtime_success",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:05Z",
                        "telemetry": {},
                    },
                },
                {
                    "run_id": "run-1",
                    "timestamp": "2026-03-23T10:00:06+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_render_fallback_markdown",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:06Z",
                        "telemetry": {"reason": "invalid_payload"},
                    },
                },
            ],
        )

        summary = store.aggregate_ui_artifact_summary(window_hours=200_000)
        metrics = summary["metrics"]

        assert metrics["exposure_count"] == 1
        assert metrics["render_attempt_count"] == 1
        assert metrics["render_success_rate"] == 1.0
        assert metrics["render_failure_rate"] == 0.0
        assert metrics["interaction_rate"] == 1.0
        assert metrics["runtime_attempt_rate"] == 1.0
        assert metrics["runtime_success_rate"] == 1.0
        assert metrics["runtime_failure_rate"] == 0.0
        assert metrics["fallback_rate_by_reason"]["invalid_payload"] == 1.0

    def test_handles_malformed_payloads_without_crashing(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        store.runs_jsonl.write_text(
            "\n".join(
                [
                    "not-json",
                    json.dumps({"event_type": "artifact_render_attempt", "payload": "oops"}),
                    json.dumps(
                        {
                            "run_id": "run-1",
                            "event_type": "artifact_runtime_skipped",
                            "payload": {
                                "source": "chat_artifact_boundary",
                                "telemetry": {"reason": "payload_truncated"},
                            },
                        }
                    ),
                    json.dumps({"event_type": "unknown_event", "payload": {}}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        summary = store.aggregate_ui_artifact_summary(window_hours=200_000)
        assert summary["sampled_event_count"] == 2
        assert summary["metrics"]["render_attempt_count"] == 0
        assert summary["metrics"]["runtime_skip_mix"]["payload_truncated"] == 1.0

    def test_missing_run_id_rows_are_excluded_from_rollout_denominators(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        base_payload = {
            "source": "chat_artifact_boundary",
            "client_timestamp": "2026-03-23T10:00:00Z",
            "telemetry": {},
        }
        self._write_ui_event_lines(
            store,
            [
                {
                    "run_id": "run-1",
                    "timestamp": "2026-03-23T10:00:00+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_payload_detected",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:00Z",
                        "telemetry": {"has_valid_artifacts": True},
                    },
                },
                {
                    "timestamp": "2026-03-23T10:00:00+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_payload_detected",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:00Z",
                        "telemetry": {"has_valid_artifacts": True},
                    },
                },
                {
                    "run_id": "run-1",
                    "timestamp": "2026-03-23T10:00:01+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_render_attempt",
                    "payload": base_payload,
                },
                {
                    "timestamp": "2026-03-23T10:00:01+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_render_attempt",
                    "payload": base_payload,
                },
                {
                    "run_id": "run-1",
                    "timestamp": "2026-03-23T10:00:02+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_render_success",
                    "payload": base_payload,
                },
                {
                    "timestamp": "2026-03-23T10:00:02+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_render_failure",
                    "payload": base_payload,
                },
                {
                    "run_id": "run-1",
                    "timestamp": "2026-03-23T10:00:03+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_interaction",
                    "payload": base_payload,
                },
                {
                    "timestamp": "2026-03-23T10:00:03+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_interaction",
                    "payload": base_payload,
                },
                {
                    "run_id": "run-1",
                    "timestamp": "2026-03-23T10:00:04+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_runtime_attempt",
                    "payload": base_payload,
                },
                {
                    "timestamp": "2026-03-23T10:00:04+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_runtime_attempt",
                    "payload": base_payload,
                },
                {
                    "run_id": "run-1",
                    "timestamp": "2026-03-23T10:00:05+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_runtime_success",
                    "payload": base_payload,
                },
                {
                    "timestamp": "2026-03-23T10:00:05+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_runtime_failure",
                    "payload": base_payload,
                },
                {
                    "run_id": "run-1",
                    "timestamp": "2026-03-23T10:00:06+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_render_fallback_markdown",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:06Z",
                        "telemetry": {"reason": "invalid_payload"},
                    },
                },
                {
                    "timestamp": "2026-03-23T10:00:06+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_render_fallback_markdown",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:06Z",
                        "telemetry": {"reason": "invalid_payload"},
                    },
                },
            ],
        )

        summary = store.aggregate_ui_artifact_summary(window_hours=200_000)
        metrics = summary["metrics"]

        assert summary["sampled_event_count"] == 14
        assert metrics["exposure_count"] == 1
        assert metrics["render_attempt_count"] == 1
        assert metrics["render_success_rate"] == 1.0
        assert metrics["render_failure_rate"] == 0.0
        assert metrics["interaction_rate"] == 1.0
        assert metrics["runtime_attempt_rate"] == 1.0
        assert metrics["runtime_success_rate"] == 1.0
        assert metrics["runtime_failure_rate"] == 0.0
        assert metrics["fallback_rate_by_reason"]["invalid_payload"] == 1.0
        assert metrics["data_quality"]["events_with_run_id_pct"] == 50.0

    def test_zero_denominator_metrics_return_none(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        self._write_ui_event_lines(
            store,
            [
                {
                    "run_id": "run-1",
                    "timestamp": "2026-03-23T10:00:00+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_boundary_flag_state",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:00Z",
                        "telemetry": {"state": "enabled"},
                    },
                }
            ],
        )

        summary = store.aggregate_ui_artifact_summary(window_hours=200_000)
        metrics = summary["metrics"]

        assert metrics["render_success_rate"] is None
        assert metrics["render_failure_rate"] is None
        assert metrics["runtime_attempt_rate"] is None
        assert metrics["runtime_success_rate"] is None
        assert metrics["runtime_failure_rate"] is None

    def test_recommendation_transitions_to_go(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        rows: list[dict[str, object]] = []
        for idx in range(400):
            run_id = f"run-{idx}"
            base_payload = {
                "source": "chat_artifact_boundary",
                "client_timestamp": "2026-03-23T10:00:00Z",
                "telemetry": {},
            }
            rows.append(
                {
                    "run_id": run_id,
                    "timestamp": "2026-03-23T10:00:00+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_payload_detected",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:00Z",
                        "telemetry": {"has_valid_artifacts": True},
                    },
                }
            )
            rows.append(
                {
                    "run_id": run_id,
                    "timestamp": "2026-03-23T10:00:01+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_render_attempt",
                    "payload": base_payload,
                }
            )
            rows.append(
                {
                    "run_id": run_id,
                    "timestamp": "2026-03-23T10:00:02+00:00",
                    "stage": "ui_artifact",
                    "event_type": (
                        "artifact_render_failure" if idx == 0 else "artifact_render_success"
                    ),
                    "payload": base_payload,
                }
            )
            rows.append(
                {
                    "run_id": run_id,
                    "timestamp": "2026-03-23T10:00:03+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_runtime_attempt",
                    "payload": base_payload,
                }
            )
            rows.append(
                {
                    "run_id": run_id,
                    "timestamp": "2026-03-23T10:00:04+00:00",
                    "stage": "ui_artifact",
                    "event_type": (
                        "artifact_runtime_failure" if idx == 1 else "artifact_runtime_success"
                    ),
                    "payload": base_payload,
                }
            )
            if idx < 40:
                rows.append(
                    {
                        "run_id": run_id,
                        "timestamp": "2026-03-23T10:00:05+00:00",
                        "stage": "ui_artifact",
                        "event_type": "artifact_interaction",
                        "payload": base_payload,
                    }
                )
            if idx < 4:
                rows.append(
                    {
                        "run_id": run_id,
                        "timestamp": "2026-03-23T10:00:06+00:00",
                        "stage": "ui_artifact",
                        "event_type": "artifact_runtime_skipped",
                        "payload": {
                            "source": "chat_artifact_boundary",
                            "client_timestamp": "2026-03-23T10:00:00Z",
                            "telemetry": {"reason": "invalid_payload"},
                        },
                    }
                )
            if idx < 10:
                rows.append(
                    {
                        "run_id": run_id,
                        "timestamp": "2026-03-23T10:00:06+00:00",
                        "stage": "ui_artifact",
                        "event_type": "artifact_runtime_skipped",
                        "payload": {
                            "source": "chat_artifact_boundary",
                            "client_timestamp": "2026-03-23T10:00:00Z",
                            "telemetry": {"reason": "payload_truncated"},
                        },
                    }
                )

        self._write_ui_event_lines(store, rows)
        summary = store.aggregate_ui_artifact_summary(window_hours=200_000, limit=200_000)

        assert summary["thresholds"]["overall_recommendation"] == "go"
        assert summary["thresholds"]["failed_conditions"] == []

    def test_recommendation_transitions_to_hold(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        rows: list[dict[str, object]] = []
        for idx in range(100):
            run_id = f"run-{idx}"
            base_payload = {
                "source": "chat_artifact_boundary",
                "client_timestamp": "2026-03-23T10:00:00Z",
                "telemetry": {},
            }
            rows.append(
                {
                    "run_id": run_id,
                    "timestamp": "2026-03-23T10:00:00+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_payload_detected",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:00Z",
                        "telemetry": {"has_valid_artifacts": True},
                    },
                }
            )
            rows.append(
                {
                    "run_id": run_id,
                    "timestamp": "2026-03-23T10:00:01+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_render_attempt",
                    "payload": base_payload,
                }
            )
            rows.append(
                {
                    "run_id": run_id,
                    "timestamp": "2026-03-23T10:00:02+00:00",
                    "stage": "ui_artifact",
                    "event_type": (
                        "artifact_render_failure" if idx == 0 else "artifact_render_success"
                    ),
                    "payload": base_payload,
                }
            )

        self._write_ui_event_lines(store, rows)
        summary = store.aggregate_ui_artifact_summary(window_hours=200_000)
        assert summary["thresholds"]["overall_recommendation"] == "hold"

    def test_recommendation_transitions_to_rollback_artifacts(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        rows: list[dict[str, object]] = []
        for idx in range(100):
            rows.append(
                {
                    "run_id": f"run-{idx}",
                    "timestamp": "2026-03-23T10:00:00+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_payload_detected",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:00Z",
                        "telemetry": {"has_valid_artifacts": True},
                    },
                }
            )
            rows.append(
                {
                    "run_id": f"run-{idx}",
                    "timestamp": "2026-03-23T10:00:01+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_render_attempt",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:01Z",
                        "telemetry": {},
                    },
                }
            )
            rows.append(
                {
                    "run_id": f"run-{idx}",
                    "timestamp": "2026-03-23T10:00:02+00:00",
                    "stage": "ui_artifact",
                    "event_type": (
                        "artifact_render_failure" if idx < 5 else "artifact_render_success"
                    ),
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:02Z",
                        "telemetry": {},
                    },
                }
            )

        self._write_ui_event_lines(store, rows)
        summary = store.aggregate_ui_artifact_summary(window_hours=200_000)

        assert summary["thresholds"]["overall_recommendation"] == "rollback_artifacts"
        assert any(
            condition.startswith("render_failure_rate")
            for condition in summary["thresholds"]["failed_conditions"]
        )

    def test_recommendation_transitions_to_rollback_runtime(self, tmp_path) -> None:
        store = TraceStore(tmp_path)
        rows: list[dict[str, object]] = []
        for idx in range(120):
            rows.append(
                {
                    "run_id": f"run-{idx}",
                    "timestamp": "2026-03-23T10:00:00+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_payload_detected",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:00Z",
                        "telemetry": {"has_valid_artifacts": True},
                    },
                }
            )
            rows.append(
                {
                    "run_id": f"run-{idx}",
                    "timestamp": "2026-03-23T10:00:01+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_render_attempt",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:01Z",
                        "telemetry": {},
                    },
                }
            )
            rows.append(
                {
                    "run_id": f"run-{idx}",
                    "timestamp": "2026-03-23T10:00:02+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_render_success",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:02Z",
                        "telemetry": {},
                    },
                }
            )
            rows.append(
                {
                    "run_id": f"run-{idx}",
                    "timestamp": "2026-03-23T10:00:03+00:00",
                    "stage": "ui_artifact",
                    "event_type": "artifact_runtime_attempt",
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:03Z",
                        "telemetry": {},
                    },
                }
            )
            rows.append(
                {
                    "run_id": f"run-{idx}",
                    "timestamp": "2026-03-23T10:00:04+00:00",
                    "stage": "ui_artifact",
                    "event_type": (
                        "artifact_runtime_failure" if idx < 3 else "artifact_runtime_success"
                    ),
                    "payload": {
                        "source": "chat_artifact_boundary",
                        "client_timestamp": "2026-03-23T10:00:04Z",
                        "telemetry": {},
                    },
                }
            )

        self._write_ui_event_lines(store, rows)
        summary = store.aggregate_ui_artifact_summary(window_hours=200_000)

        assert summary["thresholds"]["overall_recommendation"] == "rollback_runtime"
        assert any(
            condition.startswith("runtime_failure_rate")
            for condition in summary["thresholds"]["failed_conditions"]
        )


# ---------------------------------------------------------------------------
# Audit log emission
# ---------------------------------------------------------------------------


class TestAuditEmission:
    def test_lifecycle_event_emits_info_audit_log(self, tmp_path, caplog) -> None:
        import logging
        store = TraceStore(tmp_path)

        with caplog.at_level(logging.INFO, logger="metis.trace"):
            store.append_event(run_id="r1", stage="synthesis", event_type="final", payload={})

        assert any("type=final" in r.message for r in caplog.records)

    def test_run_started_emits_audit_log(self, tmp_path, caplog) -> None:
        import logging
        store = TraceStore(tmp_path)

        with caplog.at_level(logging.INFO, logger="metis.trace"):
            store.append_event(run_id="r1", stage="retrieval", event_type="run_started", payload={})

        assert any("type=run_started" in r.message for r in caplog.records)

    def test_error_event_emits_warning(self, tmp_path, caplog) -> None:
        import logging
        store = TraceStore(tmp_path)

        with caplog.at_level(logging.WARNING, logger="metis.trace"):
            store.append_event(run_id="r1", stage="error", event_type="error", payload={"status": "error"})

        matching = [r for r in caplog.records if r.levelno >= logging.WARNING and "type=error" in r.message]
        assert matching

    def test_validation_fail_emits_warning(self, tmp_path, caplog) -> None:
        import logging
        store = TraceStore(tmp_path)

        with caplog.at_level(logging.WARNING, logger="metis.trace"):
            store.append_event(run_id="r1", stage="s", event_type="validation_fail", payload={"status": "error"})

        matching = [r for r in caplog.records if r.levelno >= logging.WARNING and "type=validation_fail" in r.message]
        assert matching

    def test_non_lifecycle_event_does_not_emit_audit_log(self, tmp_path, caplog) -> None:
        import logging
        store = TraceStore(tmp_path)

        with caplog.at_level(logging.DEBUG, logger="metis.trace"):
            store.append_event(run_id="r1", stage="retrieval", event_type="retrieval_complete", payload={})

        metis_trace_records = [r for r in caplog.records if r.name == "metis.trace"]
        assert not metis_trace_records

    def test_audit_log_includes_run_id_and_stage(self, tmp_path, caplog) -> None:
        import logging
        store = TraceStore(tmp_path)

        with caplog.at_level(logging.INFO, logger="metis.trace"):
            store.append_event(run_id="my-run-99", stage="synthesis", event_type="final", payload={})

        record = next(r for r in caplog.records if "type=final" in r.message)
        assert "run=my-run-99" in record.message
        assert "stage=synthesis" in record.message

    def test_audit_log_includes_latency_when_present(self, tmp_path, caplog) -> None:
        import logging
        store = TraceStore(tmp_path)

        with caplog.at_level(logging.INFO, logger="metis.trace"):
            store.append_event(run_id="r1", stage="s", event_type="final", latency_ms=42, payload={})

        record = next(r for r in caplog.records if "type=final" in r.message)
        assert "latency_ms=42" in record.message
