"""GGUF model management endpoints."""

from __future__ import annotations

import logging
import pathlib
from typing import Any

from litestar import Router, delete, get, post
from litestar.exceptions import HTTPException as LitestarHTTPException

from metis_app.api.models import GgufRegisterRequestModel, GgufValidateRequestModel
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


def _save_registry(registry: dict[str, Any]) -> None:
    from metis_app.models.app_model import AppModel

    model = AppModel()
    current = dict(model.settings)
    current["local_model_registry"] = registry
    model.save_settings(current)


@get("/v1/gguf/catalog")
def list_catalog(use_case: str = "general") -> list[dict[str, Any]]:
    """List known GGUF models from the embedded catalog."""
    result = _RECOMMENDER.recommend_models(use_case=use_case, limit=50)
    rows = result.get("rows", [])
    return [serialize_catalog_entry(item) for item in rows]


@get("/v1/gguf/hardware")
def get_hardware() -> dict[str, Any]:
    """Get detected hardware profile for GGUF recommendations."""
    return hardware_payload_from_recommender(_RECOMMENDER)


@get("/v1/gguf/installed")
def list_installed() -> list[dict[str, Any]]:
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


@post("/v1/gguf/validate", status_code=200)
def validate_model(data: GgufValidateRequestModel) -> dict[str, Any]:
    """Validate a GGUF model path and return metadata."""
    try:
        result = validate_model_path(data.model_path)
    except GgufValidationError as exc:
        raise LitestarHTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    if not result.filename_is_conventional:
        log.warning("GGUF file with unusual name validated: %s", result.payload["filename"])

    return result.payload


@post("/v1/gguf/refresh")
def refresh_catalog(use_case: str = "general") -> dict[str, Any]:
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


@post("/v1/gguf/register")
def register_model(payload: GgufRegisterRequestModel) -> dict[str, Any]:
    """Register a locally installed GGUF model into the registry."""
    if not payload.name or not payload.path:
        raise LitestarHTTPException(status_code=400, detail="name and path are required")

    model_path = pathlib.Path(payload.path).expanduser()
    if not model_path.exists():
        raise LitestarHTTPException(
            status_code=404,
            detail=f"Model file not found: {model_path}",
        )

    registry = _load_registry()
    updated = _REGISTRY.add_gguf(
        registry,
        name=payload.name,
        path=str(model_path),
        metadata=payload.metadata or {},
    )
    _save_registry(updated)

    entries = _REGISTRY.list_entries(updated)
    entry = next(
        (item for item in entries if item.name == payload.name and item.model_type == "gguf"),
        None,
    )
    if entry is None:
        raise LitestarHTTPException(status_code=500, detail="Failed to register model")

    return {
        "status": "registered",
        "id": entry.entry_id,
        "name": entry.name,
        "path": entry.path,
    }


@delete("/v1/gguf/installed/{model_id:str}", status_code=200)
def unregister_model(model_id: str) -> dict[str, Any]:
    """Unregister a GGUF model from the registry."""
    registry = _load_registry()
    entry = _REGISTRY.get_entry(registry, model_id)
    if entry is None:
        raise LitestarHTTPException(status_code=404, detail="Model not found in registry")

    updated = _REGISTRY.remove_entry(registry, model_id)
    _save_registry(updated)
    return {"status": "unregistered", "id": model_id}


router = Router(
    path="",
    route_handlers=[
        list_catalog,
        get_hardware,
        list_installed,
        validate_model,
        refresh_catalog,
        register_model,
        unregister_model,
    ],
    tags=["gguf"],
)
