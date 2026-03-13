"""UI-free indexing helpers for engine consumers."""

from __future__ import annotations

from dataclasses import dataclass
import pathlib
from typing import Any, Callable

from axiom_app.services.index_service import _DEFAULT_INDEX_DIR, load_index_manifest
from axiom_app.services.vector_store import resolve_vector_store

_DEFAULT_INDEX_STORAGE_DIR = _DEFAULT_INDEX_DIR


@dataclass(slots=True)
class IndexBuildRequest:
    document_paths: list[str]
    settings: dict[str, Any]
    index_id: str | None = None


@dataclass(slots=True)
class IndexBuildResult:
    manifest_path: pathlib.Path
    index_id: str
    document_count: int
    chunk_count: int
    embedding_signature: str
    vector_backend: str


def build_index(
    req: IndexBuildRequest,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    cancel_token: Any | None = None,
) -> IndexBuildResult:
    """Build and persist an index using the existing vector-store pipeline."""

    if not req.document_paths:
        raise ValueError("document_paths must contain at least one document.")

    adapter = resolve_vector_store(req.settings)
    available, reason = adapter.is_available(req.settings)
    if not available:
        raise RuntimeError(f"Vector backend unavailable: {reason}")

    bundle = adapter.build(
        [str(path) for path in req.document_paths],
        dict(req.settings),
        post_message=progress_cb,
        cancel_token=cancel_token,
    )
    requested_index_id = str(req.index_id or "").strip()
    if requested_index_id:
        bundle.index_id = requested_index_id

    manifest_path = pathlib.Path(adapter.save(bundle, index_dir=_DEFAULT_INDEX_STORAGE_DIR))
    manifest = load_index_manifest(manifest_path)
    return IndexBuildResult(
        manifest_path=manifest_path,
        index_id=str(manifest.index_id or bundle.index_id),
        document_count=int(manifest.document_count),
        chunk_count=int(manifest.chunk_count),
        embedding_signature=str(manifest.embedding_signature or bundle.embedding_signature),
        vector_backend=str(manifest.backend or bundle.vector_backend),
    )
