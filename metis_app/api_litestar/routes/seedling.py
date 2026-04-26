"""Seedling lifecycle endpoints."""

from __future__ import annotations

from litestar import Router, get

import metis_app.settings_store as _settings_store
from metis_app.seedling import (
    get_seedling_status,
    get_seedling_worker,
    list_seedling_activity_events,
)
from metis_app.seedling.overnight import compute_model_status


@get("/v1/seedling/status", sync_to_thread=False)
def get_status() -> dict:
    """Return the current Seedling status payload.

    ``model_status`` is recomputed on every request so the dock sees
    settings changes within one poll. The cached value is updated as a
    side-effect — the next overnight scheduling decision picks it up
    without waiting for the next worker tick.
    """
    settings = _settings_store.load_settings()
    fresh_model_status = compute_model_status(settings)
    try:
        get_seedling_worker().set_overnight_status(model_status=fresh_model_status)
    except Exception:
        # Status reads must never fail because the worker is mid-shutdown.
        pass

    payload = get_seedling_status().to_dict()
    payload["model_status"] = fresh_model_status
    payload["activity_events"] = list_seedling_activity_events()
    return payload


router = Router(
    path="",
    route_handlers=[get_status],
    tags=["seedling"],
)
