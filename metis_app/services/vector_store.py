"""Vector-store routing layer for MVC parity."""

from __future__ import annotations

from abc import ABC, abstractmethod
import importlib.util
import os
import pathlib
import re
from typing import Any, Callable
from urllib.parse import urlparse

from metis_app.services.index_service import (
    IndexBundle,
    QueryResult,
    build_index_bundle,
    build_query_result,
    list_index_manifests,
    load_index_bundle,
    load_index_manifest,
    persist_index_bundle,
    query_index_bundle,
    resolve_manifest_storage_dir,
    select_hit_indices,
)
from metis_app.utils.embedding_providers import create_embeddings
from metis_app.utils.mock_embeddings import MockEmbeddings

_EMB_DIM = 32
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _simple_chunk_metadata(chunk: dict[str, Any], idx: int) -> dict[str, Any]:
    return {
        "chunk_id": str(chunk.get("id") or f"chunk-{idx}"),
        "chunk_idx": int(chunk.get("chunk_idx", idx)),
        "source": str(chunk.get("source") or ""),
        "file_path": str(chunk.get("file_path") or ""),
        "section_hint": str(chunk.get("section_hint") or ""),
        "header_path": str(chunk.get("header_path") or ""),
        "locator": str(chunk.get("locator") or ""),
        "anchor": str(chunk.get("anchor") or ""),
        "label": str(chunk.get("label") or chunk.get("source") or ""),
    }


def _chunk_id_lookup(bundle: IndexBundle) -> dict[str, int]:
    result: dict[str, int] = {}
    for idx, chunk in enumerate(bundle.chunks):
        result[str(chunk.get("id") or f"chunk-{idx}")] = idx
    return result


def _normalized_distance_score(distance: Any) -> float:
    try:
        numeric = float(distance)
    except (TypeError, ValueError):
        return 0.0
    if numeric <= 1.0:
        return max(0.0, 1.0 - numeric)
    return 1.0 / (1.0 + numeric)


def _native_query_limit(bundle: IndexBundle, settings: dict[str, Any]) -> int:
    top_k = max(1, int(settings.get("top_k", 3) or 3))
    return max(1, min(len(bundle.chunks), max(top_k * 3, top_k)))


def _collection_name(index_id: str, *, uppercase_first: bool = False) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", str(index_id or "").strip()).strip("_")
    if not value:
        value = "metis_index"
    if uppercase_first:
        if not value[0].isalpha():
            value = f"METIS_{value}"
        return value[:1].upper() + value[1:]
    if not value[0].isalnum():
        value = f"metis_{value}"
    return value.lower()


def _load_query_embeddings(settings: dict[str, Any]) -> Any:
    try:
        return create_embeddings(settings)
    except (ValueError, ImportError):
        return MockEmbeddings(dimensions=_EMB_DIM)


def _parse_optional_int(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer if provided.") from exc


def _parse_boolish(value: Any, *, field_name: str, default: bool | None = None) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return default
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    raise ValueError(f"{field_name} must be a boolean-like value (true/false).")


def normalize_weaviate_settings(settings: dict[str, Any]) -> dict[str, Any]:
    raw_url = str(settings.get("weaviate_url", "") or "").strip()
    if not raw_url:
        raise ValueError("weaviate_url is not configured.")
    parsed = urlparse(raw_url if "://" in raw_url else f"http://{raw_url}")
    if not parsed.hostname:
        raise ValueError("Invalid weaviate_url.")

    http_secure = parsed.scheme == "https"
    http_port = int(parsed.port or (443 if http_secure else 80))
    grpc_host = str(settings.get("weaviate_grpc_host", "") or "").strip() or parsed.hostname
    grpc_secure = _parse_boolish(
        settings.get("weaviate_grpc_secure"),
        field_name="weaviate_grpc_secure",
        default=http_secure,
    )
    grpc_port = _parse_optional_int(
        settings.get("weaviate_grpc_port"),
        field_name="weaviate_grpc_port",
    )
    if grpc_port is None:
        grpc_port = 443 if grpc_secure and http_secure else 50051
    api_key = str(settings.get("weaviate_api_key", "") or "").strip()
    normalized_url = f"{'https' if http_secure else 'http'}://{parsed.hostname}:{http_port}"
    return {
        "weaviate_url": normalized_url,
        "weaviate_http_host": parsed.hostname,
        "weaviate_http_port": http_port,
        "weaviate_http_secure": http_secure,
        "weaviate_grpc_host": grpc_host,
        "weaviate_grpc_port": grpc_port,
        "weaviate_grpc_secure": bool(grpc_secure),
        "weaviate_api_key": api_key,
    }


def weaviate_test_settings_from_env(env: dict[str, str] | None = None) -> dict[str, Any]:
    source = env or os.environ
    settings = {
        "weaviate_url": source.get("METIS_TEST_WEAVIATE_URL", ""),
        "weaviate_api_key": source.get("METIS_TEST_WEAVIATE_API_KEY", ""),
        "weaviate_grpc_host": source.get("METIS_TEST_WEAVIATE_GRPC_HOST", ""),
        "weaviate_grpc_port": source.get("METIS_TEST_WEAVIATE_GRPC_PORT", ""),
        "weaviate_grpc_secure": source.get("METIS_TEST_WEAVIATE_GRPC_SECURE", ""),
    }
    return normalize_weaviate_settings(settings)


def _manifest_vector_path(bundle: IndexBundle, fallback_name: str) -> pathlib.Path:
    manifest = load_index_manifest(bundle.index_path)
    if manifest.legacy_compat:
        raise RuntimeError(
            f"{bundle.vector_backend} indexes require a manifest-backed persisted store."
        )
    root = pathlib.Path(manifest.manifest_path).parent
    raw = str(manifest.vector_store_path or bundle.metadata.get("vector_store_path") or fallback_name)
    path = pathlib.Path(raw)
    return path if path.is_absolute() else root / path


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
        manifest = persist_index_bundle(
            bundle,
            backend=self.backend_name,
            target_dir=resolve_manifest_storage_dir(bundle, target_path=target_path, index_dir=index_dir),
        )
        return pathlib.Path(manifest.manifest_path)

    def load(self, path: str | pathlib.Path) -> IndexBundle:
        bundle = load_index_bundle(path)
        bundle.vector_backend = str(bundle.vector_backend or self.backend_name)
        return bundle

    def query(self, bundle: IndexBundle, question: str, settings: dict[str, Any]) -> QueryResult:
        return query_index_bundle(bundle, question, settings)

    def list_indexes(self, index_dir: str | pathlib.Path) -> list[pathlib.Path]:
        return [pathlib.Path(item.manifest_path) for item in list_index_manifests(index_dir)]

    def delete(self, path: str | pathlib.Path) -> None:
        target = pathlib.Path(path)
        if target.is_dir():
            for child in sorted(target.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    child.rmdir()
            target.rmdir()
            return
        if target.exists():
            target.unlink()


class JsonVectorStoreAdapter(VectorStoreAdapter):
    backend_name = "json"

    def is_available(self, settings: dict[str, Any]) -> tuple[bool, str]:
        _ = settings
        return True, ""

    def save(
        self,
        bundle: IndexBundle,
        *,
        target_path: str | pathlib.Path | None = None,
        index_dir: str | pathlib.Path | None = None,
    ) -> pathlib.Path:
        if target_path is not None:
            path = pathlib.Path(target_path)
            if path.suffix.lower() == ".json" and path.name != "manifest.json":
                from metis_app.services.index_service import save_index_bundle

                bundle.vector_backend = self.backend_name
                return save_index_bundle(bundle, target_path=path)
        return super().save(bundle, target_path=target_path, index_dir=index_dir)


class ChromaVectorStoreAdapter(VectorStoreAdapter):
    backend_name = "chroma"

    def is_available(self, settings: dict[str, Any]) -> tuple[bool, str]:
        _ = settings
        if importlib.util.find_spec("chromadb") is None:
            return False, "chromadb is not installed."
        return True, ""

    def save(
        self,
        bundle: IndexBundle,
        *,
        target_path: str | pathlib.Path | None = None,
        index_dir: str | pathlib.Path | None = None,
    ) -> pathlib.Path:
        target = resolve_manifest_storage_dir(bundle, target_path=target_path, index_dir=index_dir)
        if target.suffix.lower() == ".json" and target.name != "manifest.json":
            raise ValueError("Chroma indexes must be stored as a directory or manifest.json path.")

        from chromadb import PersistentClient

        vector_store_dir = target / "chroma"
        vector_store_dir.mkdir(parents=True, exist_ok=True)
        client = PersistentClient(path=str(vector_store_dir))
        collection_name = _collection_name(bundle.index_id)
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
        collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        ids: list[str] = []
        documents: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict[str, Any]] = []
        for idx, chunk in enumerate(bundle.chunks):
            ids.append(str(chunk.get("id") or f"chunk-{idx}"))
            documents.append(str(chunk.get("text") or ""))
            embeddings.append([float(value) for value in bundle.embeddings[idx]])
            metadatas.append(_simple_chunk_metadata(chunk, idx))
        if ids:
            collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )

        manifest = persist_index_bundle(
            bundle,
            backend=self.backend_name,
            target_dir=target,
            vector_store_path=vector_store_dir,
            collection_name=collection_name,
            restore_requirements={"python_package": "chromadb"},
            manifest_metadata={"storage_kind": "chroma-persistent"},
        )
        return pathlib.Path(manifest.manifest_path)

    def query(self, bundle: IndexBundle, question: str, settings: dict[str, Any]) -> QueryResult:
        from chromadb import PersistentClient

        vector_store_dir = _manifest_vector_path(bundle, "chroma")
        manifest = load_index_manifest(bundle.index_path)
        client = PersistentClient(path=str(vector_store_dir))
        collection = client.get_collection(manifest.collection_name or _collection_name(bundle.index_id))
        embeddings = _load_query_embeddings(settings)
        query_vector = embeddings.embed_query(question)
        limit = _native_query_limit(bundle, settings)
        raw = collection.query(
            query_embeddings=[query_vector],
            n_results=limit,
            include=["distances", "metadatas", "documents"],
        )

        ids = ((raw.get("ids") or [[]])[0]) if isinstance(raw, dict) else []
        distances = ((raw.get("distances") or [[]])[0]) if isinstance(raw, dict) else []
        metadatas = ((raw.get("metadatas") or [[]])[0]) if isinstance(raw, dict) else []
        lookup = _chunk_id_lookup(bundle)
        ranked: list[int] = []
        scores: dict[int, float] = {}
        for pos, chunk_id in enumerate(ids):
            idx = lookup.get(str(chunk_id))
            if idx is None and pos < len(metadatas):
                try:
                    idx = int((metadatas[pos] or {}).get("chunk_idx"))
                except (TypeError, ValueError, AttributeError):
                    idx = None
            if idx is None or idx in scores:
                continue
            ranked.append(idx)
            scores[idx] = _normalized_distance_score(distances[pos] if pos < len(distances) else None)
        hits = select_hit_indices(bundle, question, ranked, settings)
        return build_query_result(bundle, question, hits, scores, settings=settings)


class WeaviateVectorStoreAdapter(VectorStoreAdapter):
    backend_name = "weaviate"

    def is_available(self, settings: dict[str, Any]) -> tuple[bool, str]:
        if importlib.util.find_spec("weaviate") is None:
            return False, "weaviate-client is not installed."
        try:
            normalized = normalize_weaviate_settings(settings)
        except ValueError as exc:
            return False, str(exc)
        ok, reason = self._preflight(normalized)
        if not ok:
            return False, reason
        return True, ""

    @staticmethod
    def _connect(settings: dict[str, Any]):
        import weaviate
        from weaviate.auth import AuthApiKey

        normalized = normalize_weaviate_settings(settings)
        api_key = str(normalized.get("weaviate_api_key", "") or "").strip()
        auth = AuthApiKey(api_key) if api_key else None
        client = weaviate.connect_to_custom(
            http_host=str(normalized["weaviate_http_host"]),
            http_port=int(normalized["weaviate_http_port"]),
            http_secure=bool(normalized["weaviate_http_secure"]),
            grpc_host=str(normalized["weaviate_grpc_host"]),
            grpc_port=int(normalized["weaviate_grpc_port"]),
            grpc_secure=bool(normalized["weaviate_grpc_secure"]),
            auth_credentials=auth,
            skip_init_checks=False,
        )
        client.connect()
        return client

    def _preflight(self, settings: dict[str, Any]) -> tuple[bool, str]:
        normalized = normalize_weaviate_settings(settings)
        try:
            client = self._connect(normalized)
        except Exception as exc:
            return (
                False,
                "Could not connect to Weaviate "
                f"at {normalized['weaviate_url']} "
                f"(gRPC {normalized['weaviate_grpc_host']}:{normalized['weaviate_grpc_port']}, "
                f"secure={normalized['weaviate_grpc_secure']}): {exc}",
            )
        try:
            if not client.is_ready():
                return False, f"Weaviate at {normalized['weaviate_url']} is not ready."
            client.collections.list_all(simple=True)
        except Exception as exc:
            return False, f"Weaviate preflight failed for {normalized['weaviate_url']}: {exc}"
        finally:
            client.close()
        return True, ""

    def save(
        self,
        bundle: IndexBundle,
        *,
        target_path: str | pathlib.Path | None = None,
        index_dir: str | pathlib.Path | None = None,
    ) -> pathlib.Path:
        target = resolve_manifest_storage_dir(bundle, target_path=target_path, index_dir=index_dir)
        if target.suffix.lower() == ".json" and target.name != "manifest.json":
            raise ValueError("Weaviate indexes must be stored as a directory or manifest.json path.")

        from weaviate.classes.config import Configure, DataType, Property
        from weaviate.classes.data import DataObject

        connection_settings = normalize_weaviate_settings(dict(bundle.metadata.get("weaviate_settings") or {}))
        if not connection_settings:
            raise ValueError("Weaviate settings were not provided on the bundle.")
        ok, reason = self._preflight(connection_settings)
        if not ok:
            raise RuntimeError(reason)
        client = self._connect(connection_settings)
        collection_name = _collection_name(bundle.index_id, uppercase_first=True)
        try:
            try:
                client.collections.delete(collection_name)
            except Exception:
                pass
            collection = client.collections.create(
                name=collection_name,
                vectorizer_config=Configure.Vectorizer.none(),
                properties=[
                    Property(name="chunk_id", data_type=DataType.TEXT),
                    Property(name="chunk_idx", data_type=DataType.INT),
                    Property(name="source", data_type=DataType.TEXT),
                    Property(name="file_path", data_type=DataType.TEXT),
                    Property(name="section_hint", data_type=DataType.TEXT),
                    Property(name="header_path", data_type=DataType.TEXT),
                    Property(name="locator", data_type=DataType.TEXT),
                    Property(name="anchor", data_type=DataType.TEXT),
                    Property(name="label", data_type=DataType.TEXT),
                    Property(name="text", data_type=DataType.TEXT),
                ],
            )
            objects = []
            for idx, chunk in enumerate(bundle.chunks):
                objects.append(
                    DataObject(
                        properties={
                            **_simple_chunk_metadata(chunk, idx),
                            "text": str(chunk.get("text") or ""),
                        },
                        vector=[float(value) for value in bundle.embeddings[idx]],
                    )
                )
            if objects:
                collection.data.insert_many(objects)
        finally:
            client.close()

        manifest = persist_index_bundle(
            bundle,
            backend=self.backend_name,
            target_dir=target,
            collection_name=collection_name,
            restore_requirements={
                "python_package": "weaviate-client",
                "weaviate_url": str(connection_settings.get("weaviate_url") or ""),
            },
            manifest_metadata={
                "storage_kind": "weaviate-collection",
                "weaviate_settings": connection_settings,
            },
        )
        return pathlib.Path(manifest.manifest_path)

    def build(
        self,
        documents: list[str],
        settings: dict[str, Any],
        *,
        post_message: Callable[[dict[str, Any]], None] | None = None,
        cancel_token: Any | None = None,
    ) -> IndexBundle:
        bundle = super().build(
            documents,
            settings,
            post_message=post_message,
            cancel_token=cancel_token,
        )
        bundle.metadata = {
            **dict(bundle.metadata or {}),
            "weaviate_settings": normalize_weaviate_settings(settings),
        }
        return bundle

    def query(self, bundle: IndexBundle, question: str, settings: dict[str, Any]) -> QueryResult:
        from weaviate.classes.query import MetadataQuery

        manifest = load_index_manifest(bundle.index_path)
        connection_settings = normalize_weaviate_settings({
            **dict(manifest.metadata.get("weaviate_settings") or {}),
            **{key: value for key, value in settings.items() if str(key).startswith("weaviate_")},
        })
        ok, reason = self._preflight(connection_settings)
        if not ok:
            raise RuntimeError(reason)
        client = self._connect(connection_settings)
        try:
            collection = client.collections.get(
                manifest.collection_name or _collection_name(bundle.index_id, uppercase_first=True)
            )
            embeddings = _load_query_embeddings(settings)
            query_vector = embeddings.embed_query(question)
            limit = _native_query_limit(bundle, settings)
            response = collection.query.near_vector(
                near_vector=query_vector,
                limit=limit,
                return_metadata=MetadataQuery(distance=True),
            )
            ranked: list[int] = []
            scores: dict[int, float] = {}
            lookup = _chunk_id_lookup(bundle)
            for item in getattr(response, "objects", []) or []:
                props = dict(getattr(item, "properties", {}) or {})
                idx = lookup.get(str(props.get("chunk_id") or ""))
                if idx is None:
                    try:
                        idx = int(props.get("chunk_idx"))
                    except (TypeError, ValueError):
                        idx = None
                if idx is None or idx in scores:
                    continue
                ranked.append(idx)
                scores[idx] = _normalized_distance_score(
                    getattr(getattr(item, "metadata", None), "distance", None)
                )
        finally:
            client.close()

        hits = select_hit_indices(bundle, question, ranked, settings)
        return build_query_result(bundle, question, hits, scores, settings=settings)

    def delete(self, path: str | pathlib.Path) -> None:
        target = pathlib.Path(path)
        manifest_path = target
        if target.is_dir():
            manifest_path = target / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = load_index_manifest(manifest_path)
                raw_settings = dict(manifest.metadata.get("weaviate_settings") or {})
                if raw_settings and manifest.collection_name:
                    normalized = normalize_weaviate_settings(raw_settings)
                    client = self._connect(normalized)
                    try:
                        if client.collections.exists(manifest.collection_name):
                            client.collections.delete(manifest.collection_name)
                    finally:
                        client.close()
            except Exception:
                pass
        directory = manifest_path.parent if manifest_path.name == "manifest.json" else target
        super().delete(directory)


def resolve_vector_store(settings: dict[str, Any]) -> VectorStoreAdapter:
    backend = str(settings.get("vector_db_type", "") or "").strip().lower()
    if backend == "chroma":
        return ChromaVectorStoreAdapter()
    if backend == "weaviate":
        return WeaviateVectorStoreAdapter()
    return JsonVectorStoreAdapter()
