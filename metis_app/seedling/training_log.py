"""Phase 7 — LoRA on-deck: training-data log writer.

Captures the overnight reflection cycle's
``(prompt, retrieved context, model output, user feedback, trace_id)``
tuple as JSONL so **M18 (LoRA fine-tuning)** and **M16 (Personal
evals)** have a stable on-disk format to consume without M13 actually
shipping training code.

The schema is versioned (``schema_version="1"``). Breaking changes bump
the version; consumers read it per-line and skip/migrate as needed.
M16 is the primary downstream today — keep the schema stable, per the
plan-doc *Coordination risks* section.

This module deliberately writes **JSONL** (newline-delimited JSON)
rather than a SQLite DB:

- Append-only by design — atomic per-line on POSIX/Windows for short
  records.
- Streaming-friendly for ML training pipelines (`load_dataset(...)`).
- No schema migrations — each line carries its own ``schema_version``.

**Privacy posture:** raw prompts and model output land on disk. The
``seedling_training_log_enabled`` setting is the off-switch (default
true). The default path is ``<workspace_root>/seedling_training_log.jsonl``;
override via ``seedling_training_log_path``.

**Not this phase:** rotation, compression, encryption, S3 upload, any
training code, any UI. The deliverable is the file, nothing else (per
the plan-doc *Phase 7 (stretch) — LoRA on-deck* contract).
"""

from __future__ import annotations

import json
import logging
import pathlib
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)


TRAINING_LOG_SCHEMA_VERSION = "1"
"""Bump on breaking schema changes. Consumers (M16, M18) read this field
per-line to decide skip / migrate / fail-loud on an unknown version."""


DEFAULT_LOG_FILENAME = "seedling_training_log.jsonl"


def _default_user_home_log_dir() -> pathlib.Path:
    """Pick a stable per-user log directory.

    Resolution rules:

    - **Windows**: ``%APPDATA%\\metis``. Falls back to ``~/.metis``
      if ``APPDATA`` is unset (rare; usually only when running
      under a stripped-down service account).
    - **POSIX (macOS, Linux)**: ``~/.metis``. We deliberately do
      *not* honour ``XDG_DATA_HOME`` — METIS already stores
      ``assistant_state.json``, ``skill_candidates.db``, etc.
      under a per-user home via per-feature defaults, so the
      training log fits the established convention.

    The directory is **not** created here; ``record_training_sample``
    handles ``mkdir -p`` lazily on first write. We compute the path
    eagerly so the resolution is testable without disk side-effects.
    """
    import os
    import platform

    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            return pathlib.Path(appdata) / "metis"
        # APPDATA missing — fall through to the POSIX-style home.
    return pathlib.Path.home() / ".metis"


def resolve_training_log_path(
    settings: dict[str, Any] | None = None,
) -> pathlib.Path:
    """Return the configured JSONL path, defaulting to a per-user home.

    Resolution rules (precedence high → low):

    1. ``settings["seedling_training_log_path"]`` if non-empty.
    2. Per-user home — ``%APPDATA%\\metis\\seedling_training_log.jsonl``
       on Windows, ``~/.metis/seedling_training_log.jsonl`` on POSIX.

    **Path-stability fix (M13 retro, 2026-04-26).** The Phase 7 v0
    default was cwd-relative, which fragmented logs across server
    restarts whenever the Litestar app was launched from different
    working directories. The new per-user-home default keeps the log
    in one place across restarts, matches the convention METIS
    already uses for ``assistant_state.json`` /
    ``skill_candidates.db`` / etc., and removes the operator
    footgun. The ``seedling_training_log_path`` setting still wins
    when set — operators with bespoke layouts (read-only home,
    encrypted volume, network share) keep their override. Tests pass
    an explicit ``log_path`` to avoid touching the real user home.

    Unlike the comet feed singleton in
    :func:`metis_app.services.comet_pipeline.resolve_feed_repository`,
    we do **not** cache the resolved path: the writer is a one-shot
    per overnight cycle, so runtime setting changes take effect on
    the next cycle without server restart.
    """
    cfg = dict(settings or {})
    explicit = str(cfg.get("seedling_training_log_path") or "").strip()
    if explicit:
        return pathlib.Path(explicit)
    return _default_user_home_log_dir() / DEFAULT_LOG_FILENAME


def is_enabled(settings: dict[str, Any] | None = None) -> bool:
    """Privacy off-switch. Default true.

    Disabling means the writer becomes a no-op that returns
    ``{"ok": False, "reason": "training_log_disabled"}``. The overnight
    runner treats both this and write failures as non-fatal — the
    reflection itself still lands.

    Coercion: an absent key resolves to True; ``False`` and known
    string falsey values (``"false"``, ``"0"``, empty string) resolve
    to False. Anything else (numbers, truthy strings, non-empty lists)
    coerces via ``bool()``. Defensive against malformed JSON settings
    where a string ``"false"`` would otherwise truthy-evaluate.
    """
    cfg = dict(settings or {})
    value = cfg.get("seedling_training_log_enabled", True)
    if value is False:
        return False
    if isinstance(value, str) and value.strip().lower() in {"false", "0", ""}:
        return False
    return bool(value)


def record_training_sample(
    *,
    kind: str,
    system_prompt: str,
    user_prompt: str,
    model_output: str,
    retrieved_context: dict[str, Any] | None = None,
    trace_id: str = "",
    feedback: list[dict[str, Any]] | None = None,
    settings: dict[str, Any] | None = None,
    log_path: pathlib.Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append one training sample to the JSONL log.

    **Schema** (``schema_version="1"``, all keys present even when empty):

    - ``schema_version``: ``str`` — bump on breaking schema changes.
    - ``ts``: ``str`` — ISO 8601 UTC timestamp of when the sample was
      logged.
    - ``kind``: ``str`` — categorises the sample. Today: ``"overnight"``
      for the Phase 4b cycle. Future kinds (e.g. ``"while_you_work"``)
      may be added — consumers should filter by kind.
    - ``trace_id``: ``str`` — usually the resulting memory entry id
      (``memory:<entry_id>``); blank if the sample was not persisted.
    - ``system_prompt``: ``str`` — system prompt fed to the model.
    - ``user_prompt``: ``str`` — user prompt fed to the model.
    - ``model_output``: ``str`` — raw completion text.
    - ``retrieved_context``: ``dict`` — opaque per-kind context payload.
      For ``kind="overnight"``, the keys are ``recent_reflections``,
      ``recent_comets``, ``recent_stars`` (lists of dicts as the
      overnight prompt builder consumed them).
    - ``feedback``: ``list[dict]`` — user feedback rows associated with
      this sample. For overnight, populated by the lifecycle from
      ``SessionFeedback`` rows for sessions referenced in
      ``recent_reflections``. Empty list when no feedback exists yet.

      **Inner-row v1 schema** (callers must produce these keys for
      every dict; downstream M16/M18 readers may rely on the shape):

      - ``feedback_id``: ``str`` — the SessionFeedback primary key.
      - ``session_id``: ``str`` — the session the feedback belongs to.
      - ``run_id``: ``str`` — the run within that session, blank
        when the feedback was attached to the session itself.
      - ``vote``: ``int`` — typically ``-1`` / ``0`` / ``1`` for
        thumbs-down / no-opinion / thumbs-up.
      - ``note``: ``str`` — free-text user comment, may be empty.
      - ``ts``: ``str`` — ISO 8601 timestamp of when the feedback
        was recorded.

    **Returns** ``{"ok": bool, "reason": str | None, "path": str}``.
    Failures are non-fatal — the caller's reflection success does not
    depend on the log writing successfully (privacy/disk-failure
    posture: log loss is preferable to reflection loss).
    """
    if not is_enabled(settings):
        return {"ok": False, "reason": "training_log_disabled", "path": ""}

    target = log_path or resolve_training_log_path(settings)
    timestamp = (now or datetime.now(timezone.utc)).isoformat()

    record: dict[str, Any] = {
        "schema_version": TRAINING_LOG_SCHEMA_VERSION,
        "ts": timestamp,
        "kind": str(kind or ""),
        "trace_id": str(trace_id or ""),
        "system_prompt": str(system_prompt or ""),
        "user_prompt": str(user_prompt or ""),
        "model_output": str(model_output or ""),
        "retrieved_context": dict(retrieved_context or {}),
        "feedback": list(feedback or []),
    }

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # JSONL: one JSON-encoded record per line, append-only.
        # ``ensure_ascii=False`` preserves non-ASCII text in prompts;
        # ``separators`` keeps each line compact.
        line = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        log.warning("Training-log append failed: %s", exc, exc_info=True)
        return {
            "ok": False,
            "reason": f"io_error:{exc.__class__.__name__}",
            "path": str(target),
        }

    return {"ok": True, "reason": None, "path": str(target)}


def record_overnight_feedback(
    *,
    target_trace_id: str,
    vote: int = 0,
    note: str = "",
    edited_summary: str = "",
    feedback_id: str = "",
    settings: dict[str, Any] | None = None,
    log_path: pathlib.Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Phase 7 retro — append a feedback record for an overnight card.

    Wraps :func:`record_training_sample` with
    ``kind="overnight_feedback"`` so the future UI surface
    (thumbs-up / edit-then-save on the morning card) lands in the
    same JSONL log as the originating overnight reflection. M16
    (Personal evals) reads both kinds back together when computing
    per-user improvement signal.

    **Schema_v1 inner shape for ``overnight_feedback`` lines**
    (additive to the v1 contract; the four base fields below are
    populated, the others are blank/empty):

    - ``trace_id``: ``"feedback:<feedback_id>"`` — distinguishes
      feedback rows from reflection rows in M16 readers.
    - ``kind``: ``"overnight_feedback"``.
    - ``feedback[0]``: dict with ``feedback_id``,
      ``target_trace_id``, ``vote`` (int, typically -1 / 0 / 1),
      ``note`` (free text), ``edited_summary`` (the user's edited
      version of the morning card; empty if they didn't edit),
      ``ts``.
    - ``system_prompt``, ``user_prompt``, ``model_output``: empty
      strings (no model invocation for a feedback event).
    - ``retrieved_context``: empty dict.

    The future UI calls this function on the user's
    thumbs-up / edit-then-save action. A complementary
    :func:`metis_app.seedling.activity.record_seedling_activity`
    event with ``kind="overnight_feedback"`` lets the dock surface
    the feedback in real time (already wired in the bridge's
    allow-list).

    Returns the same shape as :func:`record_training_sample`.
    """
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    fid = str(feedback_id or "").strip()
    if not fid:
        # Synthesise a deterministic id from the timestamp + target so
        # M16 dedup-by-id has something stable to grip when callers
        # don't supply one.
        fid = f"fb-{timestamp}-{target_trace_id}"
    feedback_row = {
        "feedback_id": fid,
        "target_trace_id": str(target_trace_id or ""),
        "vote": int(vote),
        "note": str(note or ""),
        "edited_summary": str(edited_summary or ""),
        "ts": timestamp,
    }
    return record_training_sample(
        kind="overnight_feedback",
        system_prompt="",
        user_prompt="",
        model_output="",
        retrieved_context={},
        trace_id=f"feedback:{fid}",
        feedback=[feedback_row],
        settings=settings,
        log_path=log_path,
        now=now,
    )


def read_training_log(
    log_path: pathlib.Path,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Read JSONL records back. Helper for tests + future M16 plumbing.

    Skips malformed lines (logs a warning) so partial corruption from
    e.g. a crash mid-write does not poison the rest of the dataset.
    Records older than ``limit`` are dropped from the tail (newest
    last in the file).
    """
    if not log_path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        with log_path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    out.append(json.loads(stripped))
                except json.JSONDecodeError as exc:
                    log.warning(
                        "Skipping malformed training-log line: %s", exc
                    )
    except OSError as exc:
        log.warning("Training-log read failed: %s", exc, exc_info=True)
        return []
    if limit is not None and limit >= 0:
        return out[-limit:]
    return out
