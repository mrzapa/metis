"""Tests for the M14 Phase 6 Forge trace-integration service.

Phase 6 surfaces per-technique recent-uses on the gallery cards.
The service reads from the existing ``TraceStore`` and filters by the
``trace_event_types`` declared on each ``TechniqueDescriptor`` — no
new persistence layer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from metis_app.services.forge_registry import TechniqueDescriptor
from metis_app.services.trace_store import TraceStore


def _make_descriptor(
    *,
    slug: str = "test-tech",
    trace_event_types: tuple[str, ...] = (),
) -> TechniqueDescriptor:
    """Build a throwaway descriptor for trace-filtering tests.

    The trace service should only care about ``id`` (for logging) and
    ``trace_event_types``; everything else here is just plumbing the
    dataclass requires.
    """
    return TechniqueDescriptor(
        id=slug,
        name=slug.replace("-", " ").title(),
        description="test",
        pillar="cortex",
        setting_keys=(),
        enabled_predicate=lambda _settings: False,
        trace_event_types=trace_event_types,
    )


def _seed(
    store: TraceStore,
    *,
    run_id: str,
    event_type: str,
    stage: str = "retrieval",
    timestamp: str | None = None,
    payload: dict | None = None,
) -> None:
    """Append a single TraceEvent. ``timestamp`` is overridden after
    create() to let tests place events at arbitrary points in time."""
    event = store.append_event(
        run_id=run_id,
        stage=stage,
        event_type=event_type,
        payload=payload or {},
    )
    if timestamp is None:
        return
    # Rewrite the runs.jsonl + per-run file with the desired timestamp
    # so the seven-day window math has something to bite on.
    import json as _json
    import pathlib as _pathlib

    files = [store.runs_jsonl, store.runs_dir / f"{run_id}.jsonl"]
    for path in files:
        if not path.exists():
            continue
        rewritten: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = _json.loads(line)
            if row.get("event_id") == event.event_id:
                row["timestamp"] = timestamp
            rewritten.append(_json.dumps(row, sort_keys=True))
        _pathlib.Path(path).write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def test_recent_uses_for_technique_filters_by_event_type(tmp_path) -> None:
    """Only events whose ``event_type`` matches the descriptor's
    ``trace_event_types`` count as evidence the technique fired."""
    from metis_app.services.forge_trace import recent_uses_for_technique

    store = TraceStore(tmp_path)
    _seed(store, run_id="run-1", event_type="iteration_start")
    _seed(store, run_id="run-1", event_type="llm_response")  # noise
    _seed(store, run_id="run-2", event_type="iteration_complete")
    _seed(store, run_id="run-2", event_type="swarm_complete")  # noise

    descriptor = _make_descriptor(
        slug="iterrag",
        trace_event_types=("iteration_start", "iteration_complete"),
    )
    result = recent_uses_for_technique(descriptor=descriptor, store=store)
    assert isinstance(result, dict)
    events = result["events"]
    assert len(events) == 2
    types = {e["event_type"] for e in events}
    assert types == {"iteration_start", "iteration_complete"}


def test_recent_uses_for_technique_orders_newest_first_and_caps_limit(
    tmp_path,
) -> None:
    """The card mini-timeline shows the most-recent N first."""
    from metis_app.services.forge_trace import recent_uses_for_technique

    store = TraceStore(tmp_path)
    base = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(10):
        ts = (base + timedelta(minutes=i)).isoformat()
        _seed(
            store,
            run_id=f"run-{i}",
            event_type="iteration_start",
            timestamp=ts,
        )

    descriptor = _make_descriptor(
        slug="iterrag",
        trace_event_types=("iteration_start",),
    )
    result = recent_uses_for_technique(
        descriptor=descriptor, store=store, limit=3
    )
    events = result["events"]
    assert len(events) == 3
    # Newest first.
    timestamps = [e["timestamp"] for e in events]
    assert timestamps == sorted(timestamps, reverse=True)


def test_recent_uses_for_descriptor_without_markers_is_empty(tmp_path) -> None:
    """A descriptor that has no ``trace_event_types`` declared returns
    an empty result instead of every trace event in the store. The card
    will render a "no trace markers wired yet" empty state for these."""
    from metis_app.services.forge_trace import recent_uses_for_technique

    store = TraceStore(tmp_path)
    _seed(store, run_id="run-1", event_type="iteration_start")
    _seed(store, run_id="run-1", event_type="swarm_complete")

    descriptor = _make_descriptor(slug="no-markers", trace_event_types=())
    result = recent_uses_for_technique(descriptor=descriptor, store=store)
    assert result["events"] == []
    assert result["weekly_count"] == 0


def test_weekly_count_only_counts_events_in_seven_day_window(tmp_path) -> None:
    """The card face shows "Used X times this week"; events older than
    7 days don't earn the technique a counter bump."""
    from metis_app.services.forge_trace import recent_uses_for_technique

    store = TraceStore(tmp_path)
    now = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)
    # Two recent events (within 7 days) + one old (10 days ago).
    _seed(
        store,
        run_id="r-recent-1",
        event_type="iteration_start",
        timestamp=(now - timedelta(days=1)).isoformat(),
    )
    _seed(
        store,
        run_id="r-recent-2",
        event_type="iteration_start",
        timestamp=(now - timedelta(days=6)).isoformat(),
    )
    _seed(
        store,
        run_id="r-old",
        event_type="iteration_start",
        timestamp=(now - timedelta(days=10)).isoformat(),
    )

    descriptor = _make_descriptor(
        slug="iterrag",
        trace_event_types=("iteration_start",),
    )
    result = recent_uses_for_technique(
        descriptor=descriptor, store=store, now=now
    )
    assert result["weekly_count"] == 2


def test_recent_uses_returns_minimal_event_shape(tmp_path) -> None:
    """The frontend only needs run_id, timestamp, stage, event_type,
    and a one-line preview — not the entire payload (which can be
    huge for retrieval_results, prompt dumps, etc). Phase 6's promise
    is "trace integration", not "trace dump"."""
    from metis_app.services.forge_trace import recent_uses_for_technique

    store = TraceStore(tmp_path)
    _seed(
        store,
        run_id="run-1",
        event_type="iteration_complete",
        stage="reflection",
        payload={"summary": "converged after 3 iterations"},
    )

    descriptor = _make_descriptor(
        slug="iterrag",
        trace_event_types=("iteration_complete",),
    )
    result = recent_uses_for_technique(descriptor=descriptor, store=store)
    event = result["events"][0]
    assert set(event.keys()) == {"run_id", "timestamp", "stage", "event_type", "preview"}
    assert event["run_id"] == "run-1"
    assert event["stage"] == "reflection"
    assert event["event_type"] == "iteration_complete"
    assert "converged" in event["preview"].lower()


def test_recent_uses_handles_missing_runs_jsonl(tmp_path) -> None:
    """Empty trace dir is the default in fresh installs — the service
    must return an empty payload rather than blow up."""
    from metis_app.services.forge_trace import recent_uses_for_technique

    store = TraceStore(tmp_path)
    descriptor = _make_descriptor(
        slug="iterrag",
        trace_event_types=("iteration_start",),
    )
    result = recent_uses_for_technique(descriptor=descriptor, store=store)
    assert result == {"events": [], "weekly_count": 0}


def test_recent_uses_skips_corrupt_lines(tmp_path) -> None:
    """A truncated JSON line in the middle of runs.jsonl shouldn't
    break the gallery — skip and keep going. ``TraceStore.read_run``
    already does this; the service must too."""
    from metis_app.services.forge_trace import recent_uses_for_technique

    store = TraceStore(tmp_path)
    _seed(store, run_id="run-1", event_type="iteration_start")
    # Append a corrupt line.
    with store.runs_jsonl.open("a", encoding="utf-8") as handle:
        handle.write("{not valid json}\n")
    _seed(store, run_id="run-2", event_type="iteration_start")

    descriptor = _make_descriptor(
        slug="iterrag",
        trace_event_types=("iteration_start",),
    )
    result = recent_uses_for_technique(descriptor=descriptor, store=store)
    assert len(result["events"]) == 2


def test_weekly_count_dedupes_per_run_for_iterative_techniques(tmp_path) -> None:
    """Iterative techniques like ``iterrag-convergence`` emit several
    marker events per run (``iteration_start`` + ``iteration_complete``
    + ``gaps_identified`` ...). The "uses this week" pill is a
    *runs-this-week* count, not a *marker-events-this-week* count —
    otherwise iterative techniques look artificially more used than
    one-event-per-run techniques and cross-card comparisons mislead.

    Regression for the Phase 6 Codex P2 review on PR #585.
    """
    from metis_app.services.forge_trace import recent_uses_for_technique

    store = TraceStore(tmp_path)
    now = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)
    base_ts = (now - timedelta(hours=1)).isoformat()
    # ONE run that emits THREE distinct iterrag markers — the natural
    # shape of a converged agentic loop.
    for event_type in ("iteration_start", "iteration_complete", "gaps_identified"):
        _seed(
            store,
            run_id="run-loop",
            event_type=event_type,
            stage="reflection",
            timestamp=base_ts,
        )

    descriptor = _make_descriptor(
        slug="iterrag",
        trace_event_types=(
            "iteration_start",
            "iteration_complete",
            "gaps_identified",
        ),
    )
    result = recent_uses_for_technique(
        descriptor=descriptor, store=store, now=now
    )
    assert result["weekly_count"] == 1, (
        "single run with three marker events should count as 1 use, "
        f"not {result['weekly_count']}"
    )


def test_weekly_use_counts_dedupes_per_run_in_bulk_scan(tmp_path) -> None:
    """The list-endpoint bulk path dedupes the same way the per-card
    detail path does — a single run that emits multiple markers
    counts as one across the whole gallery."""
    from metis_app.services.forge_trace import weekly_use_counts

    store = TraceStore(tmp_path)
    now = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)
    ts = (now - timedelta(hours=1)).isoformat()
    # Two distinct runs, each emitting two markers.
    for run_id in ("run-A", "run-B"):
        _seed(store, run_id=run_id, event_type="iteration_start", timestamp=ts)
        _seed(
            store,
            run_id=run_id,
            event_type="iteration_complete",
            timestamp=ts,
        )

    descriptors = (
        _make_descriptor(
            slug="iterrag",
            trace_event_types=("iteration_start", "iteration_complete"),
        ),
    )
    counts = weekly_use_counts(
        descriptors=descriptors, store=store, now=now
    )
    assert counts["iterrag"] == 2, (
        "two runs (each with two markers) should count as 2, "
        f"not {counts['iterrag']}"
    )


def test_weekly_count_falls_back_to_event_count_when_run_id_missing(tmp_path) -> None:
    """Trace rows with an empty/missing ``run_id`` can't be deduped
    sensibly — each one is its own "use". The fallback prevents a
    single broken row from collapsing the count to zero."""
    from metis_app.services.forge_trace import recent_uses_for_technique

    store = TraceStore(tmp_path)
    now = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)
    ts = (now - timedelta(hours=1)).isoformat()
    _seed(store, run_id="", event_type="iteration_start", timestamp=ts)
    _seed(store, run_id="", event_type="iteration_complete", timestamp=ts)

    descriptor = _make_descriptor(
        slug="iterrag",
        trace_event_types=("iteration_start", "iteration_complete"),
    )
    result = recent_uses_for_technique(
        descriptor=descriptor, store=store, now=now
    )
    # Two events with no run_id ⇒ each counted distinctly. Anything
    # else would silently zero the counter on a malformed jsonl line.
    assert result["weekly_count"] == 2


@pytest.mark.parametrize(
    ("slug", "expected_marker"),
    [
        ("iterrag-convergence", "iteration_complete"),
        ("sub-query-expansion", "subqueries"),
        ("swarm-personas", "swarm_complete"),
        ("citation-v2", "claim_grounding"),
    ],
)
def test_registry_descriptors_declare_trace_markers(
    slug: str, expected_marker: str
) -> None:
    """Smoke-test that the four marquee techniques the harvest
    inventory most clearly maps to trace events have at least the
    canonical marker declared. Other techniques are allowed to ship
    with empty trace markers — the card just renders a "no recent
    uses" empty state."""
    from metis_app.services.forge_registry import get_descriptor

    descriptor = get_descriptor(slug)
    assert descriptor is not None, f"descriptor {slug} missing from registry"
    assert expected_marker in descriptor.trace_event_types, (
        f"{slug} should declare {expected_marker} as a trace marker; "
        f"got {descriptor.trace_event_types}"
    )
