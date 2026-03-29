"""Read-only index registry helpers for engine consumers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from metis_app.models.parity_types import IndexManifest
from metis_app.services.index_service import (
    _DEFAULT_INDEX_DIR,
    delete_persisted_index,
    list_index_manifests,
)

_DEFAULT_INDEX_STORAGE_DIR = _DEFAULT_INDEX_DIR


def _resolve_index_dir(index_dir: Path | str | None) -> Path:
    return Path(_DEFAULT_INDEX_STORAGE_DIR if index_dir is None else index_dir)


def _serialize_manifest(manifest: IndexManifest) -> dict[str, Any]:
    return {
        "index_id": str(manifest.index_id or ""),
        "backend": str(manifest.backend or "json"),
        "created_at": str(manifest.created_at or ""),
        "document_count": int(manifest.document_count or 0),
        "chunk_count": int(manifest.chunk_count or 0),
        "manifest_path": str(manifest.manifest_path or ""),
        "embedding_signature": str(manifest.embedding_signature or ""),
        "collection_name": str(manifest.collection_name or ""),
        "legacy_compat": bool(manifest.legacy_compat),
        "brain_pass": dict((manifest.metadata or {}).get("brain_pass") or {}),
        "metadata": dict(manifest.metadata or {}),
    }


def list_indexes(index_dir: Path | str | None = None) -> list[dict[str, Any]]:
    """List persisted index manifests as engine-safe metadata dictionaries."""

    return [
        _serialize_manifest(manifest)
        for manifest in list_index_manifests(_resolve_index_dir(index_dir))
    ]


def get_index(index_id: str, index_dir: Path | str | None = None) -> dict[str, Any] | None:
    """Return persisted index metadata for an exact index identifier match."""

    wanted = str(index_id or "")
    for manifest in list_index_manifests(_resolve_index_dir(index_dir)):
        if str(manifest.index_id or "") == wanted:
            return _serialize_manifest(manifest)
    return None


def delete_index(manifest_path: str | Path) -> dict[str, Any]:
    """Delete a persisted index by manifest or bundle path."""

    return delete_persisted_index(manifest_path)


__all__ = ["delete_index", "get_index", "list_indexes"]
