"""Vector-store routing layer for MVC parity."""

from __future__ import annotations

from abc import ABC, abstractmethod
import importlib.util
import pathlib
from typing import Any, Callable

from axiom_app.services.index_service import (
    IndexBundle,
    QueryResult,
    build_index_bundle,
    load_index_bundle,
    query_index_bundle,
    save_index_bundle,
)


class VectorStoreAdapter(ABC):
    """Backend adapter used by the controller for build/load/query."""

    backend_name = "json"

    @abstractmethod
    def is_available(self, settings: dict[str, Any]) -> tuple[bool, str]:
        raise NotImplementedError

    def build(
        self,
        documents: list[str],
        settings: dict[str, Any],
        *,
        post_message: Callable[[dict[str, Any]], None] | None = None,
        cancel_token: Any | None = None,
    ) -> IndexBundle:
        bundle = build_index_bundle(
            documents,
            {**dict(settings), "vector_db_type": self.backend_name},
            post_message=post_message,
            cancel_token=cancel_token,
        )
        bundle.vector_backend = self.backend_name
        return bundle

    def save(
        self,
        bundle: IndexBundle,
        *,
        target_path: str | pathlib.Path | None = None,
        index_dir: str | pathlib.Path | None = None,
    ) -> pathlib.Path:
        bundle.vector_backend = self.backend_name
        return save_index_bundle(bundle, target_path=target_path, index_dir=index_dir)

    def load(self, path: str | pathlib.Path) -> IndexBundle:
        bundle = load_index_bundle(path)
        bundle.vector_backend = str(bundle.vector_backend or self.backend_name)
        return bundle

    def query(self, bundle: IndexBundle, question: str, settings: dict[str, Any]) -> QueryResult:
        return query_index_bundle(bundle, question, settings)

    def list_indexes(self, index_dir: str | pathlib.Path) -> list[pathlib.Path]:
        root = pathlib.Path(index_dir)
        if not root.exists():
            return []
        return sorted(root.glob("*.json"))


class JsonVectorStoreAdapter(VectorStoreAdapter):
    backend_name = "json"

    def is_available(self, settings: dict[str, Any]) -> tuple[bool, str]:
        _ = settings
        return True, ""


class ChromaVectorStoreAdapter(VectorStoreAdapter):
    backend_name = "chroma"

    def is_available(self, settings: dict[str, Any]) -> tuple[bool, str]:
        _ = settings
        if importlib.util.find_spec("chromadb") is None:
            return False, "chromadb is not installed."
        return True, ""


class WeaviateVectorStoreAdapter(VectorStoreAdapter):
    backend_name = "weaviate"

    def is_available(self, settings: dict[str, Any]) -> tuple[bool, str]:
        if importlib.util.find_spec("weaviate") is None:
            return False, "weaviate-client is not installed."
        if not str(settings.get("weaviate_url", "") or "").strip():
            return False, "weaviate_url is not configured."
        return True, ""


def resolve_vector_store(settings: dict[str, Any]) -> VectorStoreAdapter:
    backend = str(settings.get("vector_db_type", "") or "").strip().lower()
    if backend == "chroma":
        return ChromaVectorStoreAdapter()
    if backend == "weaviate":
        return WeaviateVectorStoreAdapter()
    return JsonVectorStoreAdapter()
