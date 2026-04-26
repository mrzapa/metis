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
    assert is_cadence_due(settings, last_overnight_reflection_at=None, now=now) is True


def test_is_cadence_due_blocks_inside_window() -> None:
    settings = {"seedling_reflection_cadence_hours": 24}
    now = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=12)
    assert is_cadence_due(settings, last_overnight_reflection_at=last, now=now) is False


def test_is_cadence_due_passes_after_window() -> None:
    settings = {"seedling_reflection_cadence_hours": 24}
    now = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=25)
    assert is_cadence_due(settings, last_overnight_reflection_at=last, now=now) is True


def test_is_cadence_due_zero_means_every_tick() -> None:
    settings = {"seedling_reflection_cadence_hours": 0}
    now = datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc)
    last = now - timedelta(seconds=1)
    assert is_cadence_due(settings, last_overnight_reflection_at=last, now=now) is True


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
        last_overnight_reflection_at=None,
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
        last_overnight_reflection_at=now - timedelta(hours=4),
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
        last_overnight_reflection_at=now - timedelta(days=2),
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
        last_overnight_reflection_at=None,
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
        last_overnight_reflection_at=None,
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
        last_overnight_reflection_at=None,
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
        last_overnight_reflection_at=None,
        last_user_activity_at=now - timedelta(hours=4),
        generator=lambda *_: "Some overnight reflection text.",
        now=now,
    )
    assert result["ran"] is False
    assert result["reason"] == "persist_skipped:writes_disabled"
