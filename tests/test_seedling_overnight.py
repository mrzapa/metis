"""Tests for the Phase 4b overnight reflection scheduler + runner."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pathlib

from metis_app.seedling.overnight import (
    build_overnight_prompt,
    compute_model_status,
    is_cadence_due,
    is_quiet_window,
    maybe_run_overnight_reflection,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gguf_settings(*, tmp_path: pathlib.Path, enabled: bool = True, model_present: bool = True) -> dict:
    model_path = tmp_path / "model.gguf"
    if model_present:
        model_path.write_bytes(b"\0" * 32)
    return {
        "assistant_runtime": {
            "local_gguf_model_path": str(model_path),
            "local_gguf_context_length": 2048,
            "local_gguf_gpu_layers": 0,
            "local_gguf_threads": 0,
        },
        "seedling_backend_reflection_enabled": enabled,
        "seedling_reflection_cadence_hours": 24,
        "seedling_reflection_quiet_window_minutes": 30,
    }


# ---------------------------------------------------------------------------
# compute_model_status
# ---------------------------------------------------------------------------


def test_compute_model_status_frontend_only_when_no_path() -> None:
    assert compute_model_status({}) == "frontend_only"
    assert compute_model_status({"assistant_runtime": {}}) == "frontend_only"


def test_compute_model_status_backend_disabled_when_toggle_off(tmp_path) -> None:
    settings = _gguf_settings(tmp_path=tmp_path, enabled=False)
    assert compute_model_status(settings) == "backend_disabled"


def test_compute_model_status_backend_configured_when_toggle_on_and_file_exists(tmp_path) -> None:
    settings = _gguf_settings(tmp_path=tmp_path, enabled=True)
    assert compute_model_status(settings) == "backend_configured"


def test_compute_model_status_backend_unavailable_when_path_missing(tmp_path) -> None:
    settings = _gguf_settings(tmp_path=tmp_path, enabled=True, model_present=False)
    assert compute_model_status(settings) == "backend_unavailable"


def test_compute_model_status_backend_disabled_when_path_missing_and_toggle_off(tmp_path) -> None:
    """Missing GGUF + toggle off should be reported as ``backend_disabled``,
    not ``backend_unavailable`` — the user hasn't even tried to opt in."""
    settings = _gguf_settings(tmp_path=tmp_path, enabled=False, model_present=False)
    assert compute_model_status(settings) == "backend_disabled"


# ---------------------------------------------------------------------------
# Cadence + quiet gates
# ---------------------------------------------------------------------------


def test_is_cadence_due_first_run_always_true() -> None:
    settings = {"seedling_reflection_cadence_hours": 24}
    now = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
    assert is_cadence_due(settings, last_overnight_attempt_at=None, now=now) is True


def test_is_cadence_due_blocks_inside_window() -> None:
    settings = {"seedling_reflection_cadence_hours": 24}
    now = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=12)
    assert is_cadence_due(settings, last_overnight_attempt_at=last, now=now) is False


def test_is_cadence_due_passes_after_window() -> None:
    settings = {"seedling_reflection_cadence_hours": 24}
    now = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=25)
    assert is_cadence_due(settings, last_overnight_attempt_at=last, now=now) is True


def test_is_cadence_due_zero_means_every_tick() -> None:
    settings = {"seedling_reflection_cadence_hours": 0}
    now = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
    last = now - timedelta(seconds=1)
    assert is_cadence_due(settings, last_overnight_attempt_at=last, now=now) is True


def test_is_quiet_window_treats_unknown_activity_as_quiet() -> None:
    settings = {"seedling_reflection_quiet_window_minutes": 30}
    now = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
    assert is_quiet_window(settings, last_user_activity_at=None, now=now) is True


def test_is_quiet_window_blocks_active_user() -> None:
    settings = {"seedling_reflection_quiet_window_minutes": 30}
    now = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
    last_activity = now - timedelta(minutes=5)
    assert is_quiet_window(settings, last_user_activity_at=last_activity, now=now) is False


def test_is_quiet_window_passes_after_idle_window() -> None:
    settings = {"seedling_reflection_quiet_window_minutes": 30}
    now = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
    last_activity = now - timedelta(minutes=45)
    assert is_quiet_window(settings, last_user_activity_at=last_activity, now=now) is True


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def test_build_overnight_prompt_handles_empty_activity() -> None:
    system, user = build_overnight_prompt()
    assert "METIS" in system
    assert "no recorded activity" in user.lower()


def test_build_overnight_prompt_includes_reflections_and_comets_and_stars() -> None:
    system, user = build_overnight_prompt(
        recent_reflections=[
            {"title": "Captured a follow-up", "summary": "Look at PR #545."},
        ],
        recent_comets=[
            {"news_item": {"title": "Bonsai 1.7B WebGPU demo"}},
        ],
        recent_stars=[
            {"title": "Star: ADR 0013 runtime pivot"},
        ],
    )
    assert "Captured a follow-up" in user
    assert "Bonsai 1.7B WebGPU demo" in user
    assert "Star: ADR 0013 runtime pivot" in user
    assert system  # non-empty


# ---------------------------------------------------------------------------
# maybe_run_overnight_reflection
# ---------------------------------------------------------------------------


def _stub_persist(captured: list[dict]):
    def _record(**kwargs):
        captured.append(kwargs)
        return {"ok": True, "memory_entry": {"summary": kwargs["summary"]}}
    return _record


def test_runner_skips_when_model_status_not_backend_configured(tmp_path) -> None:
    settings = _gguf_settings(tmp_path=tmp_path, enabled=False)
    captured: list[dict] = []
    result = maybe_run_overnight_reflection(
        settings=settings,
        record_external_reflection=_stub_persist(captured),
        last_overnight_attempt_at=None,
        last_user_activity_at=None,
        generator=lambda *_: "should not be called",
    )
    assert result["ran"] is False
    assert "model_status" in (result["reason"] or "")
    assert captured == []


def test_runner_skips_when_cadence_not_due(tmp_path) -> None:
    settings = _gguf_settings(tmp_path=tmp_path)
    now = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
    captured: list[dict] = []
    result = maybe_run_overnight_reflection(
        settings=settings,
        record_external_reflection=_stub_persist(captured),
        last_overnight_attempt_at=now - timedelta(hours=4),
        last_user_activity_at=None,
        generator=lambda *_: "should not be called",
        now=now,
    )
    assert result["ran"] is False
    assert result["reason"] == "cadence_not_due"
    assert captured == []


def test_runner_skips_when_user_active(tmp_path) -> None:
    settings = _gguf_settings(tmp_path=tmp_path)
    now = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
    captured: list[dict] = []
    result = maybe_run_overnight_reflection(
        settings=settings,
        record_external_reflection=_stub_persist(captured),
        last_overnight_attempt_at=now - timedelta(days=2),
        last_user_activity_at=now - timedelta(minutes=5),
        generator=lambda *_: "should not be called",
        now=now,
    )
    assert result["ran"] is False
    assert result["reason"] == "user_active"
    assert captured == []


def test_runner_runs_and_persists_when_all_gates_open(tmp_path) -> None:
    settings = _gguf_settings(tmp_path=tmp_path)
    now = datetime(2026, 4, 26, 6, 0, tzinfo=timezone.utc)
    captured: list[dict] = []

    def _generator(system: str, user: str, settings_arg: dict) -> str:
        assert "METIS" in system
        return (
            "Yesterday you absorbed two news items about local-first AI.\n"
            "Follow-ups: review the WebGPU demo, finish ADR 0009 draft."
        )

    result = maybe_run_overnight_reflection(
        settings=settings,
        record_external_reflection=_stub_persist(captured),
        last_overnight_attempt_at=None,
        last_user_activity_at=now - timedelta(hours=2),
        activity={
            "recent_reflections": [{"title": "Atlas auto-save", "summary": "Saved."}],
            "recent_comets": [{"news_item": {"title": "Bonsai demo"}}],
        },
        generator=_generator,
        now=now,
    )
    assert result["ran"] is True
    assert result["reason"] is None
    assert captured and captured[0]["kind"] == "overnight"
    assert captured[0]["trigger"] == "overnight"
    assert "Yesterday you absorbed" in captured[0]["summary"]
    assert captured[0]["source_event"]["source"] == "seedling"


def test_runner_treats_empty_generation_as_skipped(tmp_path) -> None:
    settings = _gguf_settings(tmp_path=tmp_path)
    now = datetime(2026, 4, 26, 6, 0, tzinfo=timezone.utc)
    captured: list[dict] = []
    result = maybe_run_overnight_reflection(
        settings=settings,
        record_external_reflection=_stub_persist(captured),
        last_overnight_attempt_at=None,
        last_user_activity_at=now - timedelta(hours=4),
        generator=lambda *_: "   ",
        now=now,
    )
    assert result["ran"] is False
    assert result["reason"] == "empty_generation"
    assert captured == []


def test_runner_records_generator_error_without_persisting(tmp_path) -> None:
    settings = _gguf_settings(tmp_path=tmp_path)
    now = datetime(2026, 4, 26, 6, 0, tzinfo=timezone.utc)
    captured: list[dict] = []

    def _bad_generator(*_args) -> str:
        raise RuntimeError("simulated llama-cpp init failure")

    result = maybe_run_overnight_reflection(
        settings=settings,
        record_external_reflection=_stub_persist(captured),
        last_overnight_attempt_at=None,
        last_user_activity_at=now - timedelta(hours=4),
        generator=_bad_generator,
        now=now,
    )
    assert result["ran"] is False
    assert result["reason"] == "generator_error"
    assert "simulated" in result["error"]
    assert captured == []


def test_runner_propagates_persist_skip(tmp_path) -> None:
    """If ``record_external_reflection`` returns ok=False (cooldown,
    paused, automatic-writes-disabled), the runner reports skipped."""
    settings = _gguf_settings(tmp_path=tmp_path)
    now = datetime(2026, 4, 26, 6, 0, tzinfo=timezone.utc)

    def _record(**kwargs):
        return {"ok": False, "reason": "writes_disabled"}

    result = maybe_run_overnight_reflection(
        settings=settings,
        record_external_reflection=_record,
        last_overnight_attempt_at=None,
        last_user_activity_at=now - timedelta(hours=4),
        generator=lambda *_: "Some overnight reflection text.",
        now=now,
    )
    assert result["ran"] is False
    assert result["reason"] == "persist_skipped:writes_disabled"


# ---------------------------------------------------------------------------
# worker.set_overnight_status — literal fallback (architect review)
# ---------------------------------------------------------------------------


def test_set_overnight_status_literal_fallback_keeps_existing_value(tmp_path) -> None:
    """A typo or unknown ``model_status`` literal must not poison the cache.

    The worker silently keeps the existing value rather than persist a
    bogus enum string. Production callers always feed a valid literal
    via ``compute_model_status``; this guard exists for future
    refactors that pass the value across module boundaries.
    """
    from metis_app.seedling.scheduler import SeedlingSchedule
    from metis_app.seedling.status import SeedlingStatusCache
    from metis_app.seedling.worker import SeedlingWorker

    cache = SeedlingStatusCache(tmp_path / "status.json")
    worker = SeedlingWorker(
        schedule=SeedlingSchedule(tick_interval_seconds=60),
        status_cache=cache,
    )
    # Known-good literal lands.
    worker.set_overnight_status(model_status="backend_configured")
    assert worker.status.model_status == "backend_configured"

    # Unknown literal silently ignored — existing value kept.
    worker.set_overnight_status(model_status="BACKEND_CONFIGURED")
    assert worker.status.model_status == "backend_configured"
    worker.set_overnight_status(model_status="totally_made_up")
    assert worker.status.model_status == "backend_configured"

    # Also a no-op when the value is unchanged (no spurious cache write).
    worker.set_overnight_status(model_status="backend_configured")
    assert worker.status.model_status == "backend_configured"


def test_set_overnight_status_bumps_last_overnight_reflection_at(tmp_path) -> None:
    """The bump path used by the lifecycle hook on a successful cycle."""
    from metis_app.seedling.scheduler import SeedlingSchedule
    from metis_app.seedling.status import SeedlingStatusCache
    from metis_app.seedling.worker import SeedlingWorker

    cache = SeedlingStatusCache(tmp_path / "status.json")
    worker = SeedlingWorker(
        schedule=SeedlingSchedule(tick_interval_seconds=60),
        status_cache=cache,
    )
    assert worker.status.last_overnight_reflection_at is None

    worker.set_overnight_status(last_overnight_reflection_at="2026-04-26T06:30:00+00:00")
    assert worker.status.last_overnight_reflection_at == "2026-04-26T06:30:00+00:00"

    # Empty string clears the field.
    worker.set_overnight_status(last_overnight_reflection_at="")
    assert worker.status.last_overnight_reflection_at is None


# ---------------------------------------------------------------------------
# Lifecycle integration — _maybe_run_overnight + worker bump (architect review)
# ---------------------------------------------------------------------------


def test_lifecycle_overnight_integration_persists_and_bumps_worker(
    tmp_path, monkeypatch
) -> None:
    """End-to-end: a successful overnight cycle must (a) call
    ``record_companion_reflection`` on the orchestrator and (b) bump
    ``worker.status.last_overnight_reflection_at`` so the next tick's
    cadence gate trips.
    """
    from datetime import datetime, timezone

    from metis_app.seedling import lifecycle
    from metis_app.seedling.scheduler import SeedlingSchedule
    from metis_app.seedling.status import SeedlingStatusCache
    from metis_app.seedling.worker import SeedlingWorker

    # Install a fresh worker into the lifecycle singleton.
    cache = SeedlingStatusCache(tmp_path / "status.json")
    worker = SeedlingWorker(
        schedule=SeedlingSchedule(tick_interval_seconds=60),
        status_cache=cache,
    )
    lifecycle.reset_seedling_worker(worker)
    assert worker.status.last_overnight_reflection_at is None

    # Settings that satisfy compute_model_status == "backend_configured".
    fake_settings = _gguf_settings(tmp_path=tmp_path, enabled=True)

    monkeypatch.setattr(
        "metis_app.settings_store.load_settings", lambda: dict(fake_settings)
    )

    # Stub the workspace orchestrator: we only need
    # `record_companion_reflection`, `list_assistant_memory`, and
    # `get_assistant_snapshot`. The Phase 4a `record_companion_reflection`
    # path goes through `record_external_reflection` and returns
    # ``ok=True`` only if the gate passes — bypass the gate by
    # returning a synthetic OK payload directly.
    persist_calls: list[dict] = []

    class _FakeOrchestrator:
        def list_assistant_memory(self, limit=6):
            return [{"title": "earlier reflection", "summary": "did things"}]

        def get_assistant_snapshot(self):
            # last_reflection_at way in the past so quiet window passes.
            return {"status": {"last_reflection_at": "2026-04-25T00:00:00+00:00"}}

        def record_companion_reflection(self, **kwargs):
            persist_calls.append(kwargs)
            return {
                "ok": True,
                "kind": kwargs.get("kind"),
                "memory_entry": {"summary": kwargs.get("summary")},
            }

    monkeypatch.setattr(
        "metis_app.services.workspace_orchestrator.WorkspaceOrchestrator",
        _FakeOrchestrator,
    )
    # Stub the generator so it doesn't touch llama-cpp.
    monkeypatch.setattr(
        "metis_app.seedling.overnight._default_generator",
        lambda system, user, settings: "Yesterday you absorbed two items. "
        "Follow-ups: revisit the WebGPU demo.",
    )

    # Run one tick's worth of work.
    result = lifecycle._default_tick_work()

    # The runner reported a successful cycle.
    assert isinstance(result, dict)
    overnight_payload = result.get("overnight") or result
    assert overnight_payload.get("ran") is True
    # Persistence actually fired.
    assert len(persist_calls) == 1
    assert persist_calls[0]["kind"] == "overnight"
    assert "WebGPU demo" in persist_calls[0]["summary"]
    # Worker status now carries the bump.
    assert worker.status.last_overnight_reflection_at is not None
    bumped = datetime.fromisoformat(
        worker.status.last_overnight_reflection_at.replace("Z", "+00:00")
    )
    assert (datetime.now(timezone.utc) - bumped).total_seconds() < 5

    # Cleanup.
    lifecycle.reset_seedling_worker(None)


def test_lifecycle_records_failure_state_on_generator_error(
    tmp_path, monkeypatch
) -> None:
    """Codex P1 from PR #550: a generator failure must (a) flip
    ``model_status`` to ``backend_unavailable`` and (b) bump
    ``last_overnight_attempt_at`` so the next tick respects the
    cadence — *without* lying about a successful reflection."""
    from datetime import datetime, timezone

    from metis_app.seedling import lifecycle
    from metis_app.seedling.scheduler import SeedlingSchedule
    from metis_app.seedling.status import SeedlingStatusCache
    from metis_app.seedling.worker import SeedlingWorker

    cache = SeedlingStatusCache(tmp_path / "status.json")
    worker = SeedlingWorker(
        schedule=SeedlingSchedule(tick_interval_seconds=60),
        status_cache=cache,
    )
    lifecycle.reset_seedling_worker(worker)

    fake_settings = _gguf_settings(tmp_path=tmp_path, enabled=True)
    monkeypatch.setattr(
        "metis_app.settings_store.load_settings", lambda: dict(fake_settings)
    )

    class _Orchestrator:
        def list_assistant_memory(self, limit=6):
            return []

        def get_assistant_snapshot(self):
            return {"status": {"last_reflection_at": "2026-04-25T00:00:00+00:00"}}

        def record_companion_reflection(self, **_kwargs):
            raise AssertionError("persist must not be called when generator fails")

    monkeypatch.setattr(
        "metis_app.services.workspace_orchestrator.WorkspaceOrchestrator",
        _Orchestrator,
    )

    def _exploding_generator(*_args):
        raise RuntimeError("simulated llama-cpp failure")

    monkeypatch.setattr(
        "metis_app.seedling.overnight._default_generator", _exploding_generator
    )

    result = lifecycle._default_tick_work()
    # News comets are disabled in _gguf_settings, so the lifecycle
    # returns the overnight payload directly (not nested under "overnight").
    assert isinstance(result, dict)
    assert result.get("ran") is False
    assert result.get("reason") == "generator_error"

    # Cadence anchor bumped — next tick blocked until cadence window
    # elapses, no tight retry loop.
    assert worker.status.last_overnight_attempt_at is not None
    bumped = datetime.fromisoformat(
        worker.status.last_overnight_attempt_at.replace("Z", "+00:00")
    )
    assert (datetime.now(timezone.utc) - bumped).total_seconds() < 5

    # Success timestamp untouched — the UI's morning-after card must
    # not lie about a successful reflection.
    assert worker.status.last_overnight_reflection_at is None

    # model_status flipped to backend_unavailable — the dock pill now
    # reflects the runtime failure.
    assert worker.status.model_status == "backend_unavailable"

    lifecycle.reset_seedling_worker(None)


def test_status_route_keeps_backend_unavailable_sticky_over_fresh_configured(
    tmp_path, monkeypatch
) -> None:
    """Codex P1 follow-up: once the runtime is known broken, the status
    route must not advertise ``backend_configured`` next read just
    because settings still say so. A user-initiated settings change
    (toggle off or path empty) clears the sticky failure."""
    from litestar.testing import TestClient

    from metis_app.api_litestar import create_app
    from metis_app.seedling import lifecycle
    from metis_app.seedling.scheduler import SeedlingSchedule
    from metis_app.seedling.status import SeedlingStatusCache
    from metis_app.seedling.worker import SeedlingWorker

    cache = SeedlingStatusCache(tmp_path / "status.json")
    worker = SeedlingWorker(
        schedule=SeedlingSchedule(tick_interval_seconds=60),
        status_cache=cache,
    )
    lifecycle.reset_seedling_worker(worker)
    # Pre-poison the worker as if a prior tick discovered the runtime
    # is broken.
    worker.set_overnight_status(model_status="backend_unavailable")

    fake_settings = _gguf_settings(tmp_path=tmp_path, enabled=True)
    monkeypatch.setattr(
        "metis_app.settings_store.load_settings", lambda: dict(fake_settings)
    )

    with TestClient(app=create_app()) as client:
        resp = client.get("/v1/seedling/status")
        assert resp.status_code == 200
        # Even though compute_model_status(settings) == "backend_configured",
        # the cached "backend_unavailable" wins.
        assert resp.json()["model_status"] == "backend_unavailable"

        # Toggle off → settings derive backend_disabled. Sticky failure
        # cleared because the user explicitly changed policy; the next
        # opt-in attempt gets a fresh shot.
        fake_settings["seedling_backend_reflection_enabled"] = False
        resp2 = client.get("/v1/seedling/status")
        assert resp2.json()["model_status"] == "backend_disabled"

        # Toggle back on. The sticky was cleared on the disable read
        # above, so this read returns the fresh "backend_configured".
        fake_settings["seedling_backend_reflection_enabled"] = True
        resp3 = client.get("/v1/seedling/status")
        assert resp3.json()["model_status"] == "backend_configured"

    lifecycle.reset_seedling_worker(None)


def test_lifecycle_overnight_integration_skips_when_model_status_disabled(
    tmp_path, monkeypatch
) -> None:
    """When ``backend_reflection_enabled=False`` the overnight cycle is a
    clean no-op — ``record_companion_reflection`` is never invoked and
    the worker's ``last_overnight_*`` anchors stay unset.

    Note: the orchestrator IS constructed once per tick (Phase 5's
    growth-stage recompute uses it), so this test no longer asserts
    the orchestrator class isn't referenced — it asserts the
    overnight persistence path stays cold.
    """
    from metis_app.seedling import lifecycle
    from metis_app.seedling.scheduler import SeedlingSchedule
    from metis_app.seedling.status import SeedlingStatusCache
    from metis_app.seedling.worker import SeedlingWorker

    cache = SeedlingStatusCache(tmp_path / "status.json")
    worker = SeedlingWorker(
        schedule=SeedlingSchedule(tick_interval_seconds=60),
        status_cache=cache,
    )
    lifecycle.reset_seedling_worker(worker)

    fake_settings = _gguf_settings(tmp_path=tmp_path, enabled=False)
    monkeypatch.setattr(
        "metis_app.settings_store.load_settings", lambda: dict(fake_settings)
    )

    persist_calls: list[dict] = []

    class _Orchestrator:
        def list_assistant_memory(self, limit=6):
            return []

        def get_assistant_snapshot(self):
            return {"status": {"last_reflection_at": "2026-04-25T00:00:00+00:00"}}

        def record_companion_reflection(self, **kwargs):
            persist_calls.append(kwargs)
            return {"ok": False, "reason": "should-not-fire"}

        def list_indexes(self):
            return []

        def recompute_growth_stage(self, *, settings=None):
            # Phase 5 recompute is fine to run; just no-op.
            return {"stage": "seedling", "advanced_from": None}

    monkeypatch.setattr(
        "metis_app.services.workspace_orchestrator.WorkspaceOrchestrator",
        _Orchestrator,
    )

    result = lifecycle._default_tick_work()
    assert isinstance(result, dict)
    assert result.get("ran") is False
    assert "model_status" in (result.get("reason") or "")
    # Overnight persistence path stayed cold.
    assert persist_calls == []
    # Worker anchors never bumped.
    assert worker.status.last_overnight_reflection_at is None
    assert worker.status.last_overnight_attempt_at is None

    lifecycle.reset_seedling_worker(None)
