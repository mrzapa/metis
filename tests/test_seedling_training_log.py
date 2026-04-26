"""Phase 7 — tests for ``metis_app.seedling.training_log``.

Two layers:

1. **Unit tests** on the writer (schema shape, append behaviour,
   privacy off-switch, malformed-line tolerance).
2. **Integration tests** on the overnight wiring — driving
   ``maybe_run_overnight_reflection`` with a real-on-disk training-log
   writer and verifying the JSONL ends up as expected.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timedelta, timezone

from metis_app.seedling.overnight import maybe_run_overnight_reflection
from metis_app.seedling.training_log import (
    DEFAULT_LOG_FILENAME,
    TRAINING_LOG_SCHEMA_VERSION,
    is_enabled,
    read_training_log,
    record_training_sample,
    resolve_training_log_path,
)


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------


def _gguf_settings(
    *, tmp_path: pathlib.Path, enabled: bool = True, training_log_path: str = ""
) -> dict:
    model_path = tmp_path / "model.gguf"
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
        "seedling_training_log_enabled": True,
        "seedling_training_log_path": training_log_path,
    }


# ---------------------------------------------------------------------------
# resolve_training_log_path / is_enabled
# ---------------------------------------------------------------------------


def test_default_path_resolves_to_cwd_filename() -> None:
    """No setting override → cwd-relative ``seedling_training_log.jsonl``."""
    resolved = resolve_training_log_path({})
    assert resolved.name == DEFAULT_LOG_FILENAME


def test_explicit_path_overrides_default(tmp_path) -> None:
    custom = tmp_path / "subdir" / "custom.jsonl"
    resolved = resolve_training_log_path(
        {"seedling_training_log_path": str(custom)}
    )
    assert resolved == custom


def test_blank_path_falls_back_to_default() -> None:
    """An empty string is treated as 'not set', not as the cwd path
    literally — we don't want a malformed ``''`` setting to write
    to ``./``."""
    assert (
        resolve_training_log_path({"seedling_training_log_path": ""}).name
        == DEFAULT_LOG_FILENAME
    )


def test_is_enabled_default_true() -> None:
    """Phase 7 default-on; the setting is the privacy off-switch."""
    assert is_enabled({}) is True
    assert is_enabled(None) is True


def test_is_enabled_false_when_explicitly_disabled() -> None:
    assert is_enabled({"seedling_training_log_enabled": False}) is False


# ---------------------------------------------------------------------------
# record_training_sample — schema + append behaviour
# ---------------------------------------------------------------------------


def test_record_writes_jsonl_with_full_schema(tmp_path) -> None:
    log_path = tmp_path / "training.jsonl"
    fixed_now = datetime(2026, 4, 26, 3, 14, 0, tzinfo=timezone.utc)
    result = record_training_sample(
        kind="overnight",
        system_prompt="You are METIS.",
        user_prompt="Reflect on yesterday.",
        model_output="The user explored two faculties.",
        retrieved_context={
            "recent_reflections": [{"title": "Atlas save"}],
            "recent_comets": [],
            "recent_stars": [],
        },
        trace_id="memory:abc-123",
        feedback=[
            {
                "feedback_id": "fb-1",
                "session_id": "sess-1",
                "run_id": "run-1",
                "vote": 1,
                "note": "good",
                "ts": "2026-04-25T10:00:00Z",
            }
        ],
        log_path=log_path,
        now=fixed_now,
    )

    assert result["ok"] is True
    assert result["reason"] is None
    assert result["path"] == str(log_path)

    rows = read_training_log(log_path)
    assert len(rows) == 1
    record = rows[0]

    # Every documented field is present, with the right types.
    assert record["schema_version"] == TRAINING_LOG_SCHEMA_VERSION
    assert record["ts"] == fixed_now.isoformat()
    assert record["kind"] == "overnight"
    assert record["trace_id"] == "memory:abc-123"
    assert record["system_prompt"] == "You are METIS."
    assert record["user_prompt"] == "Reflect on yesterday."
    assert record["model_output"] == "The user explored two faculties."
    assert record["retrieved_context"]["recent_reflections"] == [
        {"title": "Atlas save"}
    ]
    assert record["retrieved_context"]["recent_comets"] == []
    assert record["retrieved_context"]["recent_stars"] == []
    assert isinstance(record["feedback"], list)
    assert record["feedback"][0]["vote"] == 1


def test_record_appends_one_record_per_call(tmp_path) -> None:
    """JSONL contract: each call is a new line, never an array."""
    log_path = tmp_path / "training.jsonl"
    for i in range(3):
        record_training_sample(
            kind="overnight",
            system_prompt="sys",
            user_prompt=f"user {i}",
            model_output="out",
            log_path=log_path,
        )

    rows = read_training_log(log_path)
    assert len(rows) == 3
    assert [r["user_prompt"] for r in rows] == ["user 0", "user 1", "user 2"]

    # Raw file: 3 lines, each parseable as standalone JSON. Belt-and-braces
    # check that the writer is genuinely producing JSONL (no trailing
    # comma, no array wrapper).
    with log_path.open("r", encoding="utf-8") as fh:
        raw_lines = [line.strip() for line in fh if line.strip()]
    assert len(raw_lines) == 3
    for line in raw_lines:
        json.loads(line)  # raises if any line isn't valid JSON


def test_record_no_op_when_disabled(tmp_path) -> None:
    """Privacy off-switch: writer must not touch disk when disabled."""
    log_path = tmp_path / "training.jsonl"
    result = record_training_sample(
        kind="overnight",
        system_prompt="sys",
        user_prompt="user",
        model_output="out",
        settings={"seedling_training_log_enabled": False},
        log_path=log_path,
    )
    assert result["ok"] is False
    assert result["reason"] == "training_log_disabled"
    assert not log_path.exists()


def test_record_creates_parent_directories(tmp_path) -> None:
    """Long-running workspaces may configure a path that doesn't yet
    exist (e.g. ``~/.metis/logs/...``). Writer should mkdir -p."""
    log_path = tmp_path / "deep" / "subdir" / "tree" / "training.jsonl"
    assert not log_path.parent.exists()
    result = record_training_sample(
        kind="overnight",
        system_prompt="sys",
        user_prompt="user",
        model_output="out",
        log_path=log_path,
    )
    assert result["ok"] is True
    assert log_path.exists()
    assert len(read_training_log(log_path)) == 1


def test_record_handles_unicode_prompts(tmp_path) -> None:
    """``ensure_ascii=False`` posture: CJK / emoji / accented characters
    survive the round-trip without ``\\u`` escaping that would inflate
    the file."""
    log_path = tmp_path / "training.jsonl"
    text = "今日のメモ: 🌱 → 🌳 (résumé)"
    record_training_sample(
        kind="overnight",
        system_prompt="sys",
        user_prompt=text,
        model_output=text,
        log_path=log_path,
    )
    raw = log_path.read_text(encoding="utf-8")
    assert "🌱" in raw  # not 🌱
    assert "今日" in raw  # not 今日

    rows = read_training_log(log_path)
    assert rows[0]["user_prompt"] == text


def test_record_coerces_none_fields_to_empty_strings(tmp_path) -> None:
    """Defensive: callers should not pass ``None`` in string fields,
    but the writer normalises to empty strings rather than crashing or
    emitting JSON nulls — schema_version=1 says all string fields are
    strings."""
    log_path = tmp_path / "training.jsonl"
    record_training_sample(
        kind="",
        system_prompt="",
        user_prompt="",
        model_output="",
        retrieved_context=None,
        trace_id="",
        feedback=None,
        log_path=log_path,
    )
    record = read_training_log(log_path)[0]
    assert record["kind"] == ""
    assert record["trace_id"] == ""
    assert record["retrieved_context"] == {}
    assert record["feedback"] == []


def test_read_training_log_skips_malformed_lines(tmp_path) -> None:
    """Crash mid-write or manual edit must not poison the dataset —
    bad lines are dropped (and warned), good lines flow through."""
    log_path = tmp_path / "training.jsonl"
    log_path.write_text(
        '{"schema_version":"1","kind":"overnight"}\n'
        "this is not json\n"
        '{"schema_version":"1","kind":"while_you_work"}\n',
        encoding="utf-8",
    )
    records = read_training_log(log_path)
    assert len(records) == 2
    assert {r["kind"] for r in records} == {"overnight", "while_you_work"}


def test_read_limit_returns_tail(tmp_path) -> None:
    log_path = tmp_path / "training.jsonl"
    for i in range(5):
        record_training_sample(
            kind="overnight",
            system_prompt="sys",
            user_prompt=f"u{i}",
            model_output="out",
            log_path=log_path,
        )
    tail = read_training_log(log_path, limit=2)
    assert [r["user_prompt"] for r in tail] == ["u3", "u4"]


def test_read_missing_file_returns_empty(tmp_path) -> None:
    assert read_training_log(tmp_path / "does-not-exist.jsonl") == []


def test_record_appends_across_separate_calls(tmp_path) -> None:
    """Two separate ``record_training_sample`` invocations (simulating
    two distinct overnight cycles) must produce two append-only lines —
    the second call must not truncate the first. Catches a regression
    where the writer accidentally opened in ``"w"`` mode."""
    log_path = tmp_path / "training.jsonl"

    record_training_sample(
        kind="overnight",
        system_prompt="day 1 system",
        user_prompt="day 1 user",
        model_output="day 1 out",
        log_path=log_path,
    )
    # Independent second cycle — separate file-open, separate write.
    record_training_sample(
        kind="overnight",
        system_prompt="day 2 system",
        user_prompt="day 2 user",
        model_output="day 2 out",
        log_path=log_path,
    )

    rows = read_training_log(log_path)
    assert [r["user_prompt"] for r in rows] == ["day 1 user", "day 2 user"]
    assert [r["model_output"] for r in rows] == ["day 1 out", "day 2 out"]


def test_is_enabled_treats_string_false_as_disabled() -> None:
    """Defensive coercion: a malformed JSON settings file with
    ``"seedling_training_log_enabled": "false"`` must NOT silently
    enable the log via Python truthy-evaluation of a non-empty string."""
    assert is_enabled({"seedling_training_log_enabled": "false"}) is False
    assert is_enabled({"seedling_training_log_enabled": "FALSE"}) is False
    assert is_enabled({"seedling_training_log_enabled": "0"}) is False
    assert is_enabled({"seedling_training_log_enabled": ""}) is False
    # Non-falsey strings still enable.
    assert is_enabled({"seedling_training_log_enabled": "yes"}) is True
    assert is_enabled({"seedling_training_log_enabled": True}) is True


# ---------------------------------------------------------------------------
# Lifecycle helper — _collect_feedback_for_reflections
# ---------------------------------------------------------------------------


class _StubSessionDetail:
    """Tiny stand-in for ``SessionDetail`` exposing only the
    ``feedback`` attribute; the lifecycle helper only reads that."""

    def __init__(self, feedback: list) -> None:
        self.feedback = feedback


class _StubFeedback:
    def __init__(
        self,
        *,
        feedback_id: str,
        session_id: str,
        run_id: str = "",
        vote: int = 0,
        note: str = "",
        ts: str = "",
    ) -> None:
        self.feedback_id = feedback_id
        self.session_id = session_id
        self.run_id = run_id
        self.vote = vote
        self.note = note
        self.ts = ts


class _StubOrchestratorForFeedback:
    def __init__(
        self,
        sessions: dict[str, _StubSessionDetail | None],
    ) -> None:
        self._sessions = sessions
        self.get_session_calls: list[str] = []

    def get_session(self, session_id: str):
        self.get_session_calls.append(session_id)
        return self._sessions.get(session_id)


def test_collect_feedback_dedupes_repeated_session_ids() -> None:
    """The lifecycle helper walks all entries in ``recent_reflections``,
    but several memories may share a ``session_id``. We must fetch the
    SessionDetail once per unique session — otherwise repeated lookups
    inflate disk reads and accidentally duplicate feedback rows."""
    from metis_app.seedling.lifecycle import _collect_feedback_for_reflections

    detail = _StubSessionDetail(
        feedback=[
            _StubFeedback(feedback_id="fb-1", session_id="s1", vote=1, note="ok"),
        ]
    )
    orch = _StubOrchestratorForFeedback({"s1": detail, "s2": None})

    # Three reflections: two from s1 (deduped), one from s2 (no detail).
    recent = [
        {"session_id": "s1", "title": "first"},
        {"session_id": "s1", "title": "second"},
        {"session_id": "s2", "title": "third"},
    ]
    feedback = _collect_feedback_for_reflections(orch, recent)

    # ``get_session`` was called once per *unique* session_id.
    assert orch.get_session_calls == ["s1", "s2"]
    # Only s1 has feedback; s2's SessionDetail is None and contributes
    # nothing. Output contains exactly one row.
    assert len(feedback) == 1
    assert feedback[0]["feedback_id"] == "fb-1"
    assert feedback[0]["vote"] == 1


def test_collect_feedback_handles_missing_session_id() -> None:
    """Reflections without a session_id (e.g. while-you-work entries
    with no session binding) must be skipped without lookups."""
    from metis_app.seedling.lifecycle import _collect_feedback_for_reflections

    orch = _StubOrchestratorForFeedback({})
    recent = [
        {"title": "anonymous"},  # no session_id
        {"session_id": "", "title": "empty session_id"},  # blank
    ]
    feedback = _collect_feedback_for_reflections(orch, recent)
    assert feedback == []
    assert orch.get_session_calls == []


def test_collect_feedback_returns_empty_when_no_reflections() -> None:
    from metis_app.seedling.lifecycle import _collect_feedback_for_reflections

    orch = _StubOrchestratorForFeedback({})
    assert _collect_feedback_for_reflections(orch, None) == []
    assert _collect_feedback_for_reflections(orch, []) == []
    assert orch.get_session_calls == []


# ---------------------------------------------------------------------------
# Integration — overnight runner + training-log writer wired together
# ---------------------------------------------------------------------------


def _stub_persist(captured: list[dict]):
    def _record(**kwargs):
        captured.append(kwargs)
        return {
            "ok": True,
            "memory_entry": {
                "entry_id": "mem-xyz",
                "summary": kwargs["summary"],
            },
        }

    return _record


def test_overnight_runner_writes_training_sample_on_success(tmp_path) -> None:
    """Phase 7 integration: a successful overnight cycle appends one
    record to the configured JSONL log with the matching trace_id."""
    log_path = tmp_path / "training.jsonl"
    settings = _gguf_settings(tmp_path=tmp_path, training_log_path=str(log_path))
    now = datetime(2026, 4, 26, 6, 0, tzinfo=timezone.utc)
    captured: list[dict] = []

    def _generator(system: str, user: str, settings_arg: dict) -> str:
        return "Yesterday's signal: faculties widening."

    result = maybe_run_overnight_reflection(
        settings=settings,
        record_external_reflection=_stub_persist(captured),
        last_overnight_attempt_at=None,
        last_user_activity_at=now - timedelta(hours=2),
        activity={
            "recent_reflections": [
                {"title": "Atlas auto-save", "summary": "Saved.", "session_id": "s1"}
            ],
            "recent_comets": [{"news_item": {"title": "Bonsai demo"}}],
        },
        generator=_generator,
        record_training_sample=record_training_sample,
        feedback=[
            {
                "feedback_id": "fb-1",
                "session_id": "s1",
                "run_id": "run-1",
                "vote": 1,
                "note": "good",
                "ts": "2026-04-25T10:00:00Z",
            }
        ],
        now=now,
    )

    assert result["ran"] is True

    # The training log file was created and contains the expected
    # record with the matching trace_id pointing at the persisted memory.
    rows = read_training_log(log_path)
    assert len(rows) == 1
    record = rows[0]
    assert record["kind"] == "overnight"
    assert record["trace_id"] == "memory:mem-xyz"
    assert record["model_output"] == "Yesterday's signal: faculties widening."
    # Retrieved context round-trips through the activity payload.
    assert record["retrieved_context"]["recent_reflections"][0]["title"] == "Atlas auto-save"
    # Feedback flowed through.
    assert record["feedback"][0]["vote"] == 1


def test_overnight_runner_skips_training_log_when_writer_omitted(tmp_path) -> None:
    """Phase 7: the training-log writer is *optional*. Tests and older
    callers that don't pass it must still work — the runner just skips
    the capture."""
    log_path = tmp_path / "training.jsonl"
    settings = _gguf_settings(tmp_path=tmp_path, training_log_path=str(log_path))
    now = datetime(2026, 4, 26, 6, 0, tzinfo=timezone.utc)
    captured: list[dict] = []

    result = maybe_run_overnight_reflection(
        settings=settings,
        record_external_reflection=_stub_persist(captured),
        last_overnight_attempt_at=None,
        last_user_activity_at=now - timedelta(hours=2),
        generator=lambda *_: "out",
        # record_training_sample omitted entirely.
        now=now,
    )
    assert result["ran"] is True
    assert not log_path.exists()


def test_overnight_runner_swallows_training_log_errors(tmp_path) -> None:
    """Phase 7 robustness: a writer that raises must not demote the
    reflection. The training log is auxiliary — the primary contract
    is the memory entry + activity event."""
    settings = _gguf_settings(tmp_path=tmp_path)
    now = datetime(2026, 4, 26, 6, 0, tzinfo=timezone.utc)
    captured: list[dict] = []

    def _broken_writer(**kwargs):
        raise OSError("disk on fire")

    result = maybe_run_overnight_reflection(
        settings=settings,
        record_external_reflection=_stub_persist(captured),
        last_overnight_attempt_at=None,
        last_user_activity_at=now - timedelta(hours=2),
        generator=lambda *_: "out",
        record_training_sample=_broken_writer,
        now=now,
    )
    # Reflection still ran successfully — the writer error is swallowed.
    assert result["ran"] is True
    assert result["reason"] is None
    # And the persistence path was hit normally.
    assert len(captured) == 1


def test_overnight_runner_skips_training_log_when_disabled(tmp_path) -> None:
    """Setting-driven privacy off-switch: even with the writer wired,
    a disabled flag must skip disk writes."""
    log_path = tmp_path / "training.jsonl"
    settings = _gguf_settings(tmp_path=tmp_path, training_log_path=str(log_path))
    settings["seedling_training_log_enabled"] = False
    now = datetime(2026, 4, 26, 6, 0, tzinfo=timezone.utc)
    captured: list[dict] = []

    result = maybe_run_overnight_reflection(
        settings=settings,
        record_external_reflection=_stub_persist(captured),
        last_overnight_attempt_at=None,
        last_user_activity_at=now - timedelta(hours=2),
        generator=lambda *_: "out",
        record_training_sample=record_training_sample,
        now=now,
    )
    assert result["ran"] is True
    assert not log_path.exists()
