"""Plain-Python orchestration for one news-comet poll cycle.

Both the HTTP poll endpoint (``POST /v1/comets/poll``) and the
Seedling worker tick (Phase 2 + Phase 3, ADR 0013) call into
:func:`run_poll_cycle`. Keeping it out of ``routes/comets.py`` means
the worker never has to round-trip HTTP to itself.

This module is intentionally thin: it composes the existing
:class:`NewsIngestService` (fetch + classify), the existing
:class:`CometDecisionEngine` (score + decide), and the new
:class:`NewsFeedRepository` (durable home from ADR 0008). It does
**not** load a Seedling model — per ADR 0013, Phase 3 is feed-storage
+ ingestion + decisioning only.
"""

from __future__ import annotations

import logging
from typing import Any

from metis_app.models.comet_event import CometEvent
from metis_app.services.comet_decision_engine import CometDecisionEngine
from metis_app.services.news_feed_repository import (
    NewsFeedRepository,
    get_default_repository,
)
from metis_app.services.news_ingest_service import NewsIngestService

log = logging.getLogger(__name__)


def resolve_feed_repository() -> NewsFeedRepository:
    """Return the feed repository bound to the configured DB path.

    Both the HTTP route handlers in ``routes/comets.py`` and the
    Seedling worker tick in ``seedling/lifecycle.py`` call into this
    helper so the configured ``seedling_feed_db_path`` reaches the
    singleton on **first access**, regardless of which surface fires
    first. Without it, an early API hit (e.g.
    ``GET /v1/comets/active``) would bind the singleton to
    ``<repo_root>/news_items.db`` and silently ignore the override
    forever — Codex P1 from PR #545.

    The override is captured on first call only; runtime swaps are
    intentionally a no-op (would invalidate in-flight cursors). Tests
    that need an isolated repo install one via
    ``reset_default_repository(NewsFeedRepository(":memory:"))``.
    """
    try:
        import metis_app.settings_store as _settings_store

        configured_path = _settings_store.load_settings().get(
            "seedling_feed_db_path", ""
        )
    except Exception:  # noqa: BLE001
        configured_path = ""
    if configured_path:
        return get_default_repository(configured_path)
    return get_default_repository()


# Module-level singletons used by the HTTP route. Tests can replace
# them via the public reset helpers below.
_default_ingest: NewsIngestService | None = None
_default_engine: CometDecisionEngine | None = None


def get_default_ingest_service() -> NewsIngestService:
    global _default_ingest
    if _default_ingest is None:
        _default_ingest = NewsIngestService(repository=resolve_feed_repository())
    return _default_ingest


def reset_default_ingest_service(service: NewsIngestService | None = None) -> None:
    global _default_ingest
    _default_ingest = service


def get_default_engine() -> CometDecisionEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = CometDecisionEngine()
    return _default_engine


def reset_default_engine(engine: CometDecisionEngine | None = None) -> None:
    global _default_engine
    _default_engine = engine


def run_poll_cycle(
    settings: dict[str, Any],
    *,
    ingest: NewsIngestService | None = None,
    engine: CometDecisionEngine | None = None,
    repository: NewsFeedRepository | None = None,
    indexes: list[Any] | None = None,
) -> dict[str, Any]:
    """Run one fetch → classify → decide → persist cycle.

    Returns a payload with the same shape as the existing
    ``poll_comets`` route (``comets``, ``total_active``, optional
    ``message``) so the HTTP handler stays a thin wrapper.

    *indexes* is injected by the route handler. The worker tick can
    pass ``None`` to force a lazy lookup, but to avoid double-loading
    indexes per tick the worker is expected to pre-resolve them and
    pass the same list each cycle.
    """
    if not settings.get("news_comets_enabled", False):
        return {"comets": [], "message": "News comets disabled"}

    ingest_service = ingest or get_default_ingest_service()
    decision_engine = engine or get_default_engine()
    repo = repository or resolve_feed_repository()

    if indexes is None:
        # Lazy import to avoid circular references at module load time.
        from metis_app.engine import list_indexes  # noqa: WPS433

        indexes = list_indexes()

    events = ingest_service.ingest(settings)
    if not events:
        return {"comets": [], "message": "No new items"}

    decided: list[CometEvent] = decision_engine.evaluate_batch(events, indexes, settings)

    max_active = min(100, max(1, int(settings.get("news_comet_max_active", 5))))
    active_count = repo.list_active_count()
    slots = max(0, max_active - active_count)
    new_comets = decided[:slots]

    persisted: list[CometEvent] = []
    for event in new_comets:
        if repo.record_comet(event):
            persisted.append(event)

    return {
        "comets": [c.to_dict() for c in persisted],
        "total_active": repo.list_active_count(),
    }
