"""Settings endpoints."""

from __future__ import annotations

import os
from typing import Any

from litestar import Router, get, post
from litestar.exceptions import HTTPException as LitestarHTTPException

import metis_app.settings_store as _store
from metis_app.api.settings import SettingsUpdateRequest

_API_KEY_PREFIX = "api_key_"


@get("/v1/settings", sync_to_thread=False)
def get_settings() -> dict[str, Any]:
    """Return active settings with api_key_* fields redacted."""
    return _store.safe_settings(_store.load_settings())


@post("/v1/settings")
def post_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept partial settings updates and persist them."""
    updates = dict(payload.get("updates") or payload)
    validated = SettingsUpdateRequest.model_validate({"updates": updates})
    denied = [key for key in validated.updates if key.startswith(_API_KEY_PREFIX)]
    if denied and os.getenv("METIS_ALLOW_API_KEY_WRITE", "").strip() != "1":
        raise LitestarHTTPException(
            status_code=403,
            detail=(
                f"Updating API key fields is not permitted via this endpoint: {denied}. "
                "Set METIS_ALLOW_API_KEY_WRITE=1 to override."
            ),
        )
    try:
        merged = _store.save_settings(validated.updates)
    except OSError as exc:
        raise LitestarHTTPException(status_code=503, detail=str(exc)) from exc
    return _store.safe_settings(merged)


router = Router(
    path="", route_handlers=[get_settings, post_settings], tags=["settings"]
)
