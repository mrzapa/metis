"""Shared GGUF serialization logic for FastAPI and Litestar routes."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Any

from axiom_app.services.local_llm_recommender import (
    is_instruct_filename,
    quant_from_filename,
    validate_gguf_filename,
)

_CAVEAT_HINTS = (
    "advisory",
    "bottleneck",
    "insufficient",
    "limited",
    "overridden",
    "reduced",
    "slow",
    "spilling",
    "tight",
)


class GgufValidationError(ValueError):
    """Framework-agnostic GGUF validation error carrying HTTP-compatible details."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(slots=True, frozen=True)
class GgufPathValidationResult:
    """Validated GGUF model-path result used by route adapters."""

    payload: dict[str, Any]
    filename_is_conventional: bool


def is_caveat(note: str) -> bool:
    """Identify if a note contains caveat-indicating keywords.
    
    Args:
        note: Note text to check.
        
    Returns:
        True if note contains caveat keywords, False otherwise.
    """
    lowered = str(note or "").strip().lower()
    return any(token in lowered for token in _CAVEAT_HINTS)


def extract_caveats(notes_list: list[str]) -> list[str]:
    """Filter notes list for items matching caveat patterns.
    
    Args:
        notes_list: List of note strings to filter.
        
    Returns:
        List of strings identified as caveats.
    """
    return [note for note in notes_list if is_caveat(note)]


def build_recommendation_summary(entry_dict: dict[str, Any]) -> str:
    """Generate human-readable summary of why model fits hardware.
    
    Constructs a one-line summary incorporating fit level, run mode, quantization,
    context length, memory requirements, and estimated throughput.
    
    Args:
        entry_dict: Raw GGUF catalog entry dict from recommender.
        
    Returns:
        Human-readable summary string.
    """
    fit_level = str(entry_dict.get("fit_level") or "unknown").replace("_", " ").strip()
    run_mode = str(entry_dict.get("run_mode") or "cpu_only").replace("_", " ").strip()
    quant = str(entry_dict.get("best_quant") or "default quant")
    context_length = max(int(entry_dict.get("recommended_context_length") or 2048), 256)
    memory_required = float(entry_dict.get("memory_required_gb") or 0.0)
    memory_available = float(entry_dict.get("memory_available_gb") or 0.0)
    estimated_tps = float(entry_dict.get("estimated_tps") or 0.0)
    
    return (
        f"{fit_level.title()} fit on {run_mode} with {quant} at {context_length:,}-token context. "
        f"Needs about {memory_required:.1f} GB from {memory_available:.1f} GB available and is estimated around "
        f"{estimated_tps:.1f} tok/s."
    )


def serialize_catalog_entry(entry_dict: dict[str, Any]) -> dict[str, Any]:
    """Normalize a catalog entry dict into standard output shape.
    
    Converts raw GGUF recommender output into canonical form with all required
    fields, proper types, and computed values (caveats, summary).
    
    Args:
        entry_dict: Raw entry from LocalLlmRecommenderService.recommend_models().
        
    Returns:
        Dict with all fields required by GgufCatalogEntryModel (framework-agnostic).
    """
    notes = [str(note) for note in (entry_dict.get("notes") or [])]
    caveats = extract_caveats(notes)
    score_components = {
        str(key): float(value)
        for key, value in dict(entry_dict.get("score_components") or {}).items()
    }
    
    return {
        "model_name": entry_dict.get("model_name", ""),
        "provider": entry_dict.get("provider", ""),
        "parameter_count": entry_dict.get("parameter_count", ""),
        "architecture": entry_dict.get("architecture", ""),
        "use_case": entry_dict.get("use_case", ""),
        "fit_level": entry_dict.get("fit_level", ""),
        "run_mode": entry_dict.get("run_mode", ""),
        "best_quant": entry_dict.get("best_quant", ""),
        "estimated_tps": float(entry_dict.get("estimated_tps", 0.0) or 0.0),
        "memory_required_gb": float(entry_dict.get("memory_required_gb", 0.0) or 0.0),
        "memory_available_gb": float(entry_dict.get("memory_available_gb", 0.0) or 0.0),
        "recommended_context_length": entry_dict.get("recommended_context_length", 2048),
        "score": float(entry_dict.get("score", 0.0) or 0.0),
        "recommendation_summary": build_recommendation_summary(entry_dict),
        "notes": notes,
        "caveats": caveats,
        "score_components": score_components,
        "source_repo": entry_dict.get("source_repo", ""),
        "source_provider": entry_dict.get("source_provider", ""),
    }


def serialize_hardware_profile(hardware: Any) -> dict[str, Any]:
    """Normalize a detected hardware profile into the GGUF hardware response contract."""
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


def hardware_payload_from_recommender(recommender: Any) -> dict[str, Any]:
    """Detect hardware using the recommender and return normalized payload."""
    return serialize_hardware_profile(recommender.detect_hardware())


def validate_model_path(model_path: str) -> GgufPathValidationResult:
    """Validate a GGUF model path and return normalized response payload.

    Raises:
        GgufValidationError: If the model path fails any validation check.
    """
    path_str = model_path
    if not path_str:
        raise GgufValidationError(status_code=400, detail="model_path is required")

    path = pathlib.Path(path_str).expanduser()

    if not path.exists():
        raise GgufValidationError(status_code=404, detail=f"Model file not found: {path}")

    if not path.is_file():
        raise GgufValidationError(status_code=400, detail=f"Path is not a file: {path}")

    if path.suffix.lower() != ".gguf":
        raise GgufValidationError(
            status_code=400,
            detail="Model file must have .gguf extension",
        )

    filename = path.name
    payload = {
        "valid": True,
        "path": str(path),
        "filename": filename,
        "file_size_bytes": path.stat().st_size,
        "quant": quant_from_filename(filename),
        "is_instruct": is_instruct_filename(filename),
    }
    return GgufPathValidationResult(
        payload=payload,
        filename_is_conventional=validate_gguf_filename(filename),
    )
