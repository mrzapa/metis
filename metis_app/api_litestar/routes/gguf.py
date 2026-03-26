"""GGUF model management endpoints."""

from __future__ import annotations

import logging
from typing import Any

from litestar import get, post
from litestar.exceptions import HTTPException as LitestarHTTPException

from metis_app.services.gguf_serialization import (
    GgufValidationError,
    hardware_payload_from_recommender,
    serialize_catalog_entry,
    validate_model_path,
)
from metis_app.services.local_llm_recommender import LocalLlmRecommenderService
from metis_app.services.local_model_registry import LocalModelRegistryService

log = logging.getLogger(__name__)

_RECOMMENDER = LocalLlmRecommenderService()
_REGISTRY = LocalModelRegistryService()


def _load_registry() -> dict[str, Any]:
    from metis_app.models.app_model import AppModel

    model = AppModel()
    return model.settings.get("local_model_registry", {})


@get("/v1/gguf/catalog")
async def list_catalog(use_case: str = "general") -> list[dict[str, Any]]:
    """List known GGUF models from the embedded catalog."""
    result = _RECOMMENDER.recommend_models(use_case=use_case, limit=50)
    rows = result.get("rows", [])
    return [serialize_catalog_entry(item) for item in rows]


@get("/v1/gguf/hardware")
async def get_hardware() -> dict[str, Any]:
    """Get detected hardware profile for GGUF recommendations."""
    return hardware_payload_from_recommender(_RECOMMENDER)


@get("/v1/gguf/installed")
async def list_installed() -> list[dict[str, Any]]:
    """List locally installed GGUF models from the model registry."""
    registry = _load_registry()
    entries = _REGISTRY.list_entries(registry)
    gguf_entries = [e for e in entries if e.model_type == "gguf"]
    return [
        {
            "id": entry.entry_id,
            "name": entry.name,
            "path": entry.path,
            "metadata": entry.metadata,
        }
        for entry in gguf_entries
    ]


@post("/v1/gguf/validate")
async def validate_model(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a GGUF model path and return metadata."""
    try:
        result = validate_model_path(data.get("model_path", ""))
    except GgufValidationError as exc:
        raise LitestarHTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    if not result.filename_is_conventional:
        log.warning("GGUF file with unusual name validated: %s", result.payload["filename"])

    return result.payload


@post("/v1/gguf/refresh")
async def refresh_catalog(use_case: str = "general") -> dict[str, Any]:
    """Refresh catalog metadata and return updated recommendations."""
    _RECOMMENDER.invalidate_hardware_cache()
    _RECOMMENDER.invalidate_repo_cache()
    result = _RECOMMENDER.recommend_models(use_case=use_case, limit=50)
    return {
        "status": "refreshed",
        "use_case": use_case,
        "hardware": result.get("hardware", {}),
        "advisory_only": result.get("advisory_only", False),
    }
