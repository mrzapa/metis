"""Phase 4b — overnight reflection scheduling and runner (ADR 0013 §3).

The Seedling worker tick calls into :func:`maybe_run_overnight_reflection`
once per tick. The function decides whether the cadence is due, whether
the user is quiet enough to start, and whether the backend reflection
toggle + ``model_status`` allow the cycle. When everything lines up, it
loads the user's configured GGUF (lazily, via an injectable generator),
builds a structured prompt, and persists the resulting text via
:meth:`AssistantCompanionService.record_external_reflection` with
``kind="overnight"`` (which lands in ``AssistantMemoryEntry`` as
``kind="overnight_reflection"``).

The actual model call is **injectable**. Production uses
``LocalLlamaCppChatModel`` lazy-loaded from
``metis_app.utils.llm_providers``. Tests stub the generator to avoid
loading a real GGUF.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import logging
import pathlib
from typing import Any

from .status import SeedlingModelStatus

log = logging.getLogger(__name__)


# Generator signature: takes (system_prompt, user_prompt, settings) and
# returns the generated reflection text. Returning an empty string is
# treated as "model produced nothing useful" — the runner skips
# persistence rather than write a blank memory entry.
OvernightGenerator = Callable[[str, str, dict[str, Any]], str]


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def compute_model_status(settings: dict[str, Any]) -> SeedlingModelStatus:
    """Return the four-value enum from ADR 0013 §2.

    Pure function over settings — does **not** attempt to load the
    GGUF. ``backend_unavailable`` only surfaces after a runner attempt
    has failed; the runner records that state into the cache before
    the next status read picks it up.
    """
    runtime = settings.get("assistant_runtime") or {}
    if not isinstance(runtime, dict):
        runtime = {}
    raw_path = str(runtime.get("local_gguf_model_path") or "").strip()
    if not raw_path:
        return "frontend_only"

    expanded = pathlib.Path(raw_path).expanduser()
    if not expanded.is_file():
        # The user pointed at a path that no longer exists. Treat it as
        # ``backend_unavailable`` so the dock surfaces a clear message
        # rather than silently falling back to ``frontend_only``.
        if bool(settings.get("seedling_backend_reflection_enabled", False)):
            return "backend_unavailable"
        return "backend_disabled"

    if not bool(settings.get("seedling_backend_reflection_enabled", False)):
        return "backend_disabled"
    return "backend_configured"


def is_quiet_window(
    settings: dict[str, Any],
    *,
    last_user_activity_at: datetime | None,
    now: datetime,
) -> bool:
    """Has the user been idle long enough to start an overnight cycle?"""
    quiet_minutes = max(
        0,
        int(settings.get("seedling_reflection_quiet_window_minutes", 30)),
    )
    if quiet_minutes <= 0:
        return True
    if last_user_activity_at is None:
        return True
    elapsed_seconds = (now - last_user_activity_at).total_seconds()
    return elapsed_seconds >= quiet_minutes * 60


def is_cadence_due(
    settings: dict[str, Any],
    *,
    last_overnight_reflection_at: datetime | None,
    now: datetime,
) -> bool:
    """Have we waited long enough since the last overnight reflection?"""
    cadence_hours = max(
        0.0,
        float(settings.get("seedling_reflection_cadence_hours", 24)),
    )
    if cadence_hours <= 0.0:
        # A cadence of zero means "every tick" — useful for tests
        # but the production default is 24h.
        return True
    if last_overnight_reflection_at is None:
        return True
    elapsed_seconds = (now - last_overnight_reflection_at).total_seconds()
    return elapsed_seconds >= cadence_hours * 3600.0


_DEFAULT_SYSTEM_PROMPT = (
    "You are METIS, the user's local-first research companion. Once a day "
    "you reflect on the prior day's learning. Write a short summary "
    "(2-4 sentences) of what stood out, then list at most three concrete "
    "follow-ups the user should consider next. Be specific, never generic, "
    "and only reference material that actually appeared in the activity "
    "you were given. If the activity is empty, say so plainly."
)


def build_overnight_prompt(
    *,
    recent_reflections: list[dict[str, Any]] | None = None,
    recent_comets: list[dict[str, Any]] | None = None,
    recent_stars: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Build a (system, user) pair from the prior day's activity.

    The user prompt is intentionally compact (target <2 KB). The
    overnight model is small (the user's configured GGUF, often
    Phi/Qwen-class), so a long context is wasted — and the morning
    summary should be skimmable.
    """
    sections: list[str] = []
    reflections = list(recent_reflections or [])[:6]
    if reflections:
        sections.append("Recent reflections (newest first):")
        for entry in reflections:
            title = str(entry.get("title") or "").strip() or "(untitled)"
            summary = str(entry.get("summary") or "").strip()
            sections.append(f"- {title}: {summary}"[:400])

    comets = list(recent_comets or [])[:8]
    if comets:
        sections.append("\nNews items absorbed today:")
        for comet in comets:
            news = comet.get("news_item") or {}
            title = str(news.get("title") or comet.get("title") or "").strip()
            if title:
                sections.append(f"- {title}"[:300])

    stars = list(recent_stars or [])[:6]
    if stars:
        sections.append("\nNew stars indexed today:")
        for star in stars:
            title = str(star.get("title") or "").strip()
            if title:
                sections.append(f"- {title}"[:300])

    if not sections:
        user_prompt = "There was no recorded activity in the prior day."
    else:
        user_prompt = "\n".join(sections)

    return _DEFAULT_SYSTEM_PROMPT, user_prompt


def maybe_run_overnight_reflection(
    *,
    settings: dict[str, Any],
    record_external_reflection: Callable[..., dict[str, Any]],
    last_overnight_reflection_at: datetime | None,
    last_user_activity_at: datetime | None,
    activity: dict[str, Any] | None = None,
    generator: OvernightGenerator | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Schedule + run one overnight reflection cycle if the gates are open.

    Returns a dict with ``ran: bool``, ``reason: str | None``, and the
    underlying ``record_external_reflection`` payload on success. The
    Seedling worker tick uses ``ran`` to decide whether to bump
    ``last_overnight_reflection_at`` in the status cache.
    """
    current = now or datetime.now(timezone.utc)
    model_status = compute_model_status(settings)
    if model_status != "backend_configured":
        return {"ran": False, "reason": f"model_status={model_status}"}

    if not is_cadence_due(
        settings,
        last_overnight_reflection_at=last_overnight_reflection_at,
        now=current,
    ):
        return {"ran": False, "reason": "cadence_not_due"}

    if not is_quiet_window(
        settings,
        last_user_activity_at=last_user_activity_at,
        now=current,
    ):
        return {"ran": False, "reason": "user_active"}

    activity_payload = dict(activity or {})
    system_prompt, user_prompt = build_overnight_prompt(
        recent_reflections=activity_payload.get("recent_reflections"),
        recent_comets=activity_payload.get("recent_comets"),
        recent_stars=activity_payload.get("recent_stars"),
    )

    gen = generator or _default_generator
    try:
        text = gen(system_prompt, user_prompt, settings)
    except Exception as exc:  # noqa: BLE001
        log.warning("Overnight generator raised: %s", exc, exc_info=True)
        return {"ran": False, "reason": "generator_error", "error": str(exc)}

    cleaned = (text or "").strip()
    if not cleaned:
        return {"ran": False, "reason": "empty_generation"}

    payload = record_external_reflection(
        summary=cleaned,
        why="Overnight reflection cycle.",
        trigger="overnight",
        kind="overnight",
        confidence=0.6,
        source_event={
            "source": "seedling",
            "kind": "overnight",
            "scheduled_at": current.isoformat(),
        },
        tags=["overnight"],
        settings=settings,
    )
    if not payload.get("ok"):
        return {
            "ran": False,
            "reason": f"persist_skipped:{payload.get('reason') or 'unknown'}",
            "result": payload,
        }
    return {"ran": True, "reason": None, "result": payload}


def _default_generator(
    system_prompt: str, user_prompt: str, settings: dict[str, Any]
) -> str:
    """Lazy-import the local GGUF chat model and run a single completion.

    Kept minimal: any failure (missing dependency, bad model file, OOM)
    propagates up so :func:`maybe_run_overnight_reflection` can record
    the failure rather than persist a blank memory entry. Production
    callers should monkeypatch this with a more robust adapter once
    Phase 4 measurement settles the right token/temp profile.
    """
    try:
        from metis_app.utils.llm_providers import (  # noqa: WPS433
            LocalLlamaCppChatModel,
        )
    except Exception as exc:
        raise RuntimeError(
            "Backend overnight reflection requested but llama-cpp-python "
            "is not importable. Configure a GGUF model and ensure the "
            "runtime is installed."
        ) from exc

    runtime = settings.get("assistant_runtime") or {}
    model_path = str(runtime.get("local_gguf_model_path") or "").strip()
    context_length = int(runtime.get("local_gguf_context_length") or 2048)
    gpu_layers = int(runtime.get("local_gguf_gpu_layers") or 0)
    threads = int(runtime.get("local_gguf_threads") or 0)
    max_new_tokens = max(
        16, int(settings.get("seedling_overnight_max_new_tokens", 256))
    )

    if not model_path:
        raise RuntimeError("Overnight reflection has no GGUF model path configured.")

    model = LocalLlamaCppChatModel(  # type: ignore[call-arg]
        model_path=model_path,
        n_ctx=context_length,
        n_gpu_layers=gpu_layers,
        n_threads=threads if threads > 0 else None,
    )
    response = model.invoke(  # type: ignore[attr-defined]
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_new_tokens,
    )
    if isinstance(response, dict):
        return str(response.get("content") or "")
    return str(response or "")
