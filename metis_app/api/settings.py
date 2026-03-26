"""GET /v1/settings and POST /v1/settings endpoints."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

import metis_app.settings_store as _store

router = APIRouter()

_API_KEY_PREFIX = "api_key_"


class SettingsUpdateRequest(BaseModel):
    updates: dict[str, Any]

    model_config = ConfigDict(extra="forbid")


@router.get("/v1/settings")
def get_settings() -> dict[str, Any]:
    """Return the active settings profile with ``api_key_*`` fields redacted."""
    return _store.safe_settings(_store.load_settings())


@router.post("/v1/settings")
def post_settings(payload: SettingsUpdateRequest) -> dict[str, Any]:
    """Accept a partial settings update and persist it to settings.json.

    Security
    --------
    Keys that start with ``api_key_`` are **rejected** (HTTP 403) unless the
    environment variable ``METIS_ALLOW_API_KEY_WRITE=1`` is explicitly set.
    The response always has ``api_key_*`` fields stripped regardless of the
    env flag.

    Raises
    ------
    403
        When the update dict contains ``api_key_*`` keys and the env override
        is not active.
    503
        When settings.json cannot be written (propagated ``OSError``).
    """
    denied = [k for k in payload.updates if k.startswith(_API_KEY_PREFIX)]
    if denied and os.getenv("METIS_ALLOW_API_KEY_WRITE", "").strip() != "1":
        raise HTTPException(
            status_code=403,
            detail=(
                f"Updating API key fields is not permitted via this endpoint: {denied}. "
                "Set METIS_ALLOW_API_KEY_WRITE=1 to override."
            ),
        )
    try:
        merged = _store.save_settings(payload.updates)
    except OSError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _store.safe_settings(merged)
