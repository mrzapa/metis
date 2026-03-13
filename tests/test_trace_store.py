from __future__ import annotations

import json
import uuid

from axiom_app.engine.runs import RunEvent, make_run_id, now_iso_utc
from axiom_app.services.trace_store import TraceStore


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
