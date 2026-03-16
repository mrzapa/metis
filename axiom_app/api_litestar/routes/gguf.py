"""GGUF model management endpoints."""

from __future__ import annotations

import logging
import pathlib
from typing import Any

from litestar import get, post
from litestar.exceptions import HTTPException as LitestarHTTPException

from axiom_app.services.local_llm_recommender import LocalLlmRecommenderService
from axiom_app.services.local_model_registry import LocalModelRegistryService

log = logging.getLogger(__name__)

_RECOMMENDER = LocalLlmRecommenderService()
_REGISTRY = LocalModelRegistryService()


def _load_registry() -> dict[str, Any]:
    from axiom_app.models.app_model import AppModel

    model = AppModel()
    return model.settings.get("local_model_registry", {})


@get("/v1/gguf/catalog")
async def list_catalog(use_case: str = "general") -> list[dict[str, Any]]:
    """List known GGUF models from the embedded catalog."""
    result = _RECOMMENDER.recommend_models(use_case=use_case, limit=50)
    rows = result.get("rows", [])
    return [
        {
            "model_name": item.get("model_name", ""),
            "provider": item.get("provider", ""),
            "parameter_count": item.get("parameter_count", ""),
            "architecture": item.get("architecture", ""),
            "use_case": item.get("use_case", ""),
            "fit_level": item.get("fit_level", ""),
            "run_mode": item.get("run_mode", ""),
            "best_quant": item.get("best_quant", ""),
            "estimated_tps": item.get("estimated_tps", 0.0),
            "memory_required_gb": item.get("memory_required_gb", 0.0),
            "memory_available_gb": item.get("memory_available_gb", 0.0),
            "recommended_context_length": item.get("recommended_context_length", 2048),
            "source_repo": item.get("source_repo", ""),
            "source_provider": item.get("source_provider", ""),
        }
        for item in rows
    ]


@get("/v1/gguf/hardware")
async def get_hardware() -> dict[str, Any]:
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
    from axiom_app.services.local_llm_recommender import (
        validate_gguf_filename,
        quant_from_filename,
        is_instruct_filename,
    )

    path_str = data.get("model_path", "")
    if not path_str:
        raise LitestarHTTPException(status_code=400, detail="model_path is required")

    path = pathlib.Path(path_str).expanduser()

    if not path.exists():
        raise LitestarHTTPException(
            status_code=404, detail=f"Model file not found: {path}"
        )

    if not path.is_file():
        raise LitestarHTTPException(
            status_code=400, detail=f"Path is not a file: {path}"
        )

    if path.suffix.lower() != ".gguf":
        raise LitestarHTTPException(
            status_code=400, detail="Model file must have .gguf extension"
        )

    file_size = path.stat().st_size

    filename = path.name
    if not validate_gguf_filename(filename):
        log.warning("GGUF file with unusual name validated: %s", filename)

    return {
        "valid": True,
        "path": str(path),
        "filename": filename,
        "file_size_bytes": file_size,
        "quant": quant_from_filename(filename),
        "is_instruct": is_instruct_filename(filename),
    }


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
