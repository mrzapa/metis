"""GGUF model management routes for the Axiom v1 API."""

from __future__ import annotations

import logging
import pathlib
from typing import Any

from fastapi import APIRouter, HTTPException

from axiom_app.services.local_llm_recommender import (
    LocalLlmRecommenderService,
    validate_gguf_filename,
)
from axiom_app.services.local_model_registry import LocalModelRegistryService

from .models import (
    GgufCatalogEntryModel,
    GgufInstalledEntryModel,
    GgufRegisterRequestModel,
    GgufValidateRequestModel,
)

router = APIRouter(prefix="/v1/gguf", tags=["gguf"])

log = logging.getLogger(__name__)

_RECOMMENDER = LocalLlmRecommenderService()
_REGISTRY = LocalModelRegistryService()


def _load_registry() -> dict[str, Any]:
    from axiom_app.models.app_model import AppModel

    model = AppModel()
    return model.settings.get("local_model_registry", {})


def _save_registry(registry: dict[str, Any]) -> None:
    from axiom_app.models.app_model import AppModel

    model = AppModel()
    current = dict(model.settings)
    current["local_model_registry"] = registry
    model.save_settings(current)


@router.get("/catalog", response_model=list[GgufCatalogEntryModel])
def list_catalog(use_case: str = "general") -> list[GgufCatalogEntryModel]:
    """List known GGUF models from the embedded catalog with hardware-aware recommendations."""
    result = _RECOMMENDER.recommend_models(use_case=use_case, limit=50)
    rows = result.get("rows", [])
    return [
        GgufCatalogEntryModel(
            model_name=item.get("model_name", ""),
            provider=item.get("provider", ""),
            parameter_count=item.get("parameter_count", ""),
            architecture=item.get("architecture", ""),
            use_case=item.get("use_case", ""),
            fit_level=item.get("fit_level", ""),
            run_mode=item.get("run_mode", ""),
            best_quant=item.get("best_quant", ""),
            estimated_tps=item.get("estimated_tps", 0.0),
            memory_required_gb=item.get("memory_required_gb", 0.0),
            memory_available_gb=item.get("memory_available_gb", 0.0),
            recommended_context_length=item.get("recommended_context_length", 2048),
            source_repo=item.get("source_repo", ""),
            source_provider=item.get("source_provider", ""),
        )
        for item in rows
    ]


@router.get("/hardware")
def get_hardware() -> dict[str, Any]:
    """Get detected hardware profile for GGUF recommendations."""
    hardware = _RECOMMENDER.detect_hardware()
    return {
        "total_ram_gb": hardware.total_ram_gb,
        "available_ram_gb": hardware.available_ram_gb,
        "total_cpu_cores": hardware.total_cpu_cores,
        "cpu_name": hardware.cpu_name,
        "has_gpu": hardware.has_gpu,
        "gpu_vram_gb": hardware.gpu_vram_gb,
        "total_gpu_vram_gb": hardware.total_gpu_vram_gb,
        "gpu_name": hardware.gpu_name,
        "gpu_count": hardware.gpu_count,
        "unified_memory": hardware.unified_memory,
        "backend": hardware.backend,
        "detected": hardware.detected,
        "override_enabled": hardware.override_enabled,
        "notes": hardware.notes,
    }


@router.get("/installed", response_model=list[GgufInstalledEntryModel])
def list_installed() -> list[GgufInstalledEntryModel]:
    """List locally installed GGUF models from the model registry."""
    registry = _load_registry()
    entries = _REGISTRY.list_entries(registry)
    gguf_entries = [e for e in entries if e.model_type == "gguf"]
    return [
        GgufInstalledEntryModel(
            id=entry.entry_id,
            name=entry.name,
            path=entry.path,
            metadata=entry.metadata,
        )
        for entry in gguf_entries
    ]


@router.post("/validate")
def validate_model(payload: GgufValidateRequestModel) -> dict[str, Any]:
    """Validate a GGUF model path and return metadata if valid."""
    path_str = payload.model_path
    if not path_str:
        raise HTTPException(status_code=400, detail="model_path is required")

    path = pathlib.Path(path_str).expanduser()

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Model file not found: {path}")

    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"Path is not a file: {path}")

    if path.suffix.lower() != ".gguf":
        raise HTTPException(
            status_code=400, detail="Model file must have .gguf extension"
        )

    file_size = path.stat().st_size

    filename = path.name
    if not validate_gguf_filename(filename):
        log.warning("GGUF file with unusual name validated: %s", filename)

    from axiom_app.services.local_llm_recommender import (
        quant_from_filename,
        is_instruct_filename,
    )

    return {
        "valid": True,
        "path": str(path),
        "filename": filename,
        "file_size_bytes": file_size,
        "quant": quant_from_filename(filename),
        "is_instruct": is_instruct_filename(filename),
    }


@router.post("/refresh")
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


@router.post("/register")
def register_model(payload: GgufRegisterRequestModel) -> dict[str, Any]:
    """Register a locally installed GGUF model into the registry."""
    name = payload.name
    path = payload.path
    metadata = payload.metadata

    if not name or not path:
        raise HTTPException(status_code=400, detail="name and path are required")

    model_path = pathlib.Path(path).expanduser()
    if not model_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Model file not found: {model_path}"
        )

    registry = _load_registry()
    updated = _REGISTRY.add_gguf(
        registry, name=name, path=str(model_path), metadata=metadata or {}
    )
    _save_registry(updated)

    entries = _REGISTRY.list_entries(updated)
    entry = next(
        (e for e in entries if e.name == name and e.model_type == "gguf"), None
    )
    if entry is None:
        raise HTTPException(status_code=500, detail="Failed to register model")

    return {
        "status": "registered",
        "id": entry.entry_id,
        "name": entry.name,
        "path": entry.path,
    }


@router.delete("/installed/{model_id}")
def unregister_model(model_id: str) -> dict[str, Any]:
    """Unregister a GGUF model from the registry."""
    registry = _load_registry()
    entry = _REGISTRY.get_entry(registry, model_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Model not found in registry")

    updated = _REGISTRY.remove_entry(registry, model_id)
    _save_registry(updated)

    return {
        "status": "unregistered",
        "id": model_id,
    }
