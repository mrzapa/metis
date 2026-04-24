"""Seedling lifecycle endpoints."""

from __future__ import annotations

from litestar import Router, get

from metis_app.seedling import get_seedling_status, list_seedling_activity_events


@get("/v1/seedling/status", sync_to_thread=False)
def get_status() -> dict:
    payload = get_seedling_status().to_dict()
    payload["activity_events"] = list_seedling_activity_events()
    return payload


router = Router(
    path="",
    route_handlers=[get_status],
    tags=["seedling"],
)
