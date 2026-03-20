"""Shared index build, persistence, and retrieval helpers.

Concurrency notes:
  - Index bundles are written atomically using temp directory staging + rename.
  - This ensures readers never see partial/corrupted index state.
  - Concurrent index builds to the same location are not supported - the last
    writer wins. Use unique index IDs to avoid conflicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import pathlib
import re
import shutil
import tempfile
from typing import Any, Callable

from axiom_app.models.parity_types import IndexManifest
from axiom_app.models.session_types import EvidenceSource
from axiom_app.services.reranker import rerank_hits
from axiom_app.services.semantic_chunker import chunk_text_semantic
from axiom_app.utils.document_loader import load_document
from axiom_app.utils.embedding_providers import create_embeddings
from axiom_app.utils.knowledge_graph import (
    KnowledgeGraph,
    build_knowledge_graph,
    collect_graph_chunk_candidates,
)
from axiom_app.utils.mock_embeddings import MockEmbeddings

_HERE = pathlib.Path(__file__).resolve().parent
_PACKAGE_ROOT = _HERE.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_DEFAULT_INDEX_DIR = _REPO_ROOT / "indexes"
_EMB_DIM = 32
_MANIFEST_FILE = "manifest.json"
_BUNDLE_FILE = "bundle.json"
_ARTIFACTS_DIR = "artifacts"


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    overlap = max(0, min(overlap, chunk_size - 1))
    chunks: list[str] = []
    start = 0
    step = chunk_size - overlap
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += step
    return chunks


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    return dot / (n1 * n2) if n1 > 0 and n2 > 0 else 0.0


@dataclass(slots=True)
class IndexBundle:
    index_id: str
    created_at: str
    documents: list[str]
    chunks: list[dict[str, Any]]
    embeddings: list[list[float]]
    knowledge_graph: KnowledgeGraph | None = None
    entity_to_chunks: dict[str, set[int]] = field(default_factory=dict)
    index_path: str = ""
    vector_backend: str = "json"
    embedding_signature: str = ""
    semantic_regions: list[dict[str, Any]] = field(default_factory=list)
    document_outline: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    grounding_html_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        edges: dict[str, dict[str, list[str]]] = {}
        if self.knowledge_graph is not None:
            for src, targets in self.knowledge_graph.edges.items():
                edges[src] = {
                    tgt: sorted(relations) for tgt, relations in targets.items()
                }
        return {
            "index_id": self.index_id,
            "created_at": self.created_at,
            "documents": list(self.documents),
            "chunks": list(self.chunks),
            "embeddings": list(self.embeddings),
            "knowledge_graph": {
                "nodes": dict(
                    self.knowledge_graph.nodes if self.knowledge_graph else {}
                ),
                "edges": edges,
            },
            "entity_to_chunks": {
                key: sorted(values)
                for key, values in (self.entity_to_chunks or {}).items()
            },
            "index_path": self.index_path,
            "vector_backend": self.vector_backend,
            "embedding_signature": self.embedding_signature,
            "semantic_regions": list(self.semantic_regions),
            "document_outline": list(self.document_outline),
            "events": list(self.events),
            "grounding_html_path": self.grounding_html_path,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "IndexBundle":
        graph = None
        graph_payload = payload.get("knowledge_graph") or {}
        if isinstance(graph_payload, dict):
            graph = KnowledgeGraph()
            graph.nodes = dict(graph_payload.get("nodes") or {})
            edge_payload = graph_payload.get("edges") or {}
            for src, targets in edge_payload.items():
                graph.edges[str(src)] = {}
                if not isinstance(targets, dict):
                    continue
                for tgt, relations in targets.items():
                    graph.edges[str(src)][str(tgt)] = {
                        str(item) for item in (relations or [])
                    }
        entity_to_chunks = {
            str(key): {int(item) for item in (values or [])}
            for key, values in (payload.get("entity_to_chunks") or {}).items()
        }
        return cls(
            index_id=str(payload.get("index_id") or ""),
            created_at=str(payload.get("created_at") or ""),
            documents=[str(item) for item in (payload.get("documents") or [])],
            chunks=[
                dict(item)
                for item in (payload.get("chunks") or [])
                if isinstance(item, dict)
            ],
            embeddings=[
                [float(value) for value in vector]
                for vector in (payload.get("embeddings") or [])
            ],
            knowledge_graph=graph,
            entity_to_chunks=entity_to_chunks,
            index_path=str(payload.get("index_path") or ""),
            vector_backend=str(payload.get("vector_backend") or "json"),
            embedding_signature=str(payload.get("embedding_signature") or ""),
            semantic_regions=[
                dict(item)
                for item in (payload.get("semantic_regions") or [])
                if isinstance(item, dict)
            ],
            document_outline=[
                dict(item)
                for item in (payload.get("document_outline") or [])
                if isinstance(item, dict)
            ],
            events=[
                dict(item)
                for item in (payload.get("events") or [])
                if isinstance(item, dict)
            ],
            grounding_html_path=str(payload.get("grounding_html_path") or ""),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class QueryResult:
    prompt: str
    context_block: str
    sources: list[EvidenceSource]
    hit_indices: list[int]
    top_score: float


def _build_parent_child_windows(
    child_chunks: list[dict[str, Any]],
    *,
    parent_chunk_size: int,
    parent_chunk_overlap: int,
) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    if not child_chunks:
        return groups

    start = 0
    while start < len(child_chunks):
        group: list[dict[str, Any]] = []
        total_len = 0
        idx = start
        while idx < len(child_chunks):
            chunk = child_chunks[idx]
            addition = len(str(chunk.get("text") or "")) + (2 if group else 0)
            if group and total_len + addition > parent_chunk_size:
                break
            group.append(chunk)
            total_len += addition
            idx += 1

        if not group:
            group = [child_chunks[start]]
            idx = start + 1

        groups.append(group)
        if idx >= len(child_chunks):
            break

        overlap_len = 0
        next_start = idx
        while next_start > start:
            candidate = child_chunks[next_start - 1]
            addition = len(str(candidate.get("text") or "")) + (2 if overlap_len else 0)
            if overlap_len + addition > parent_chunk_overlap:
                break
            overlap_len += addition
            next_start -= 1
        start = max(next_start, start + 1)
    return groups


def _allowed_hit_types(settings: dict[str, Any]) -> set[str]:
    retrieval_mode = str(settings.get("retrieval_mode", "flat") or "flat").strip().lower()
    if retrieval_mode == "hierarchical":
        return {"chunk", "child_chunk", "faq"}
    return {"chunk", "child_chunk", "summary", "faq"}


def _chunk_is_allowed(chunk: dict[str, Any], settings: dict[str, Any]) -> bool:
    allowed = _allowed_hit_types(settings)
    chunk_type = str(chunk.get("type") or "chunk").strip().lower()
    return chunk_type in allowed


def _chunk_index_lookup(bundle: IndexBundle) -> dict[str, int]:
    lookup: dict[str, int] = {}
    for idx, chunk in enumerate(bundle.chunks):
        lookup[str(chunk.get("id") or f"chunk-{idx}")] = idx
    return lookup


def _best_score_for_hits(
    score_lookup: dict[int, float] | list[float],
    hit_indices: list[int],
) -> float:
    return max((_score_for_index(score_lookup, idx) for idx in hit_indices), default=0.0)


def _build_hierarchical_sources(
    bundle: IndexBundle,
    hit_indices: list[int],
    score_lookup: dict[int, float] | list[float],
    *,
    top_k: int,
) -> tuple[list[EvidenceSource], list[str], list[int], float]:
    lookup = _chunk_index_lookup(bundle)
    grouped_hits: dict[str, dict[str, Any]] = {}
    group_order: list[str] = []

    for idx in hit_indices:
        if idx < 0 or idx >= len(bundle.chunks):
            continue
        chunk = bundle.chunks[idx]
        chunk_id = str(chunk.get("id") or f"chunk-{idx}")
        metadata = dict(chunk.get("metadata") or {})
        parent_chunk_id = str(metadata.get("parent_chunk_id") or chunk.get("parent_chunk_id") or chunk_id)
        parent_idx = lookup.get(parent_chunk_id, idx)
        if parent_chunk_id not in grouped_hits:
            grouped_hits[parent_chunk_id] = {
                "parent_idx": parent_idx,
                "child_hit_indices": [],
                "best_score": 0.0,
            }
            group_order.append(parent_chunk_id)
        grouped_hits[parent_chunk_id]["child_hit_indices"].append(idx)
        grouped_hits[parent_chunk_id]["best_score"] = max(
            float(grouped_hits[parent_chunk_id]["best_score"] or 0.0),
            _score_for_index(score_lookup, idx),
        )

    ranked_group_ids = sorted(
        group_order,
        key=lambda group_id: (
            -float(grouped_hits[group_id]["best_score"] or 0.0),
            group_order.index(group_id),
        ),
    )[:top_k]

    sources: list[EvidenceSource] = []
    context_parts: list[str] = []
    selected_hit_indices: list[int] = []
    top_score = 0.0

    for rank, group_id in enumerate(ranked_group_ids, start=1):
        group = grouped_hits[group_id]
        parent_idx = int(group["parent_idx"])
        if parent_idx < 0 or parent_idx >= len(bundle.chunks):
            continue
        parent_chunk = bundle.chunks[parent_idx]
        child_hits = [int(item) for item in group.get("child_hit_indices", [])]
        matched_previews = [
            str(bundle.chunks[child_idx].get("excerpt") or bundle.chunks[child_idx].get("text") or "").strip()
            for child_idx in child_hits
            if 0 <= child_idx < len(bundle.chunks)
        ]
        best_score = float(group.get("best_score") or 0.0)
        if rank == 1:
            top_score = best_score
        selected_hit_indices.extend(child_hits)
        sid = f"S{rank}"
        source = EvidenceSource(
            sid=sid,
            source=str(parent_chunk.get("source") or "unknown"),
            snippet=str(parent_chunk.get("text") or "").strip(),
            chunk_id=str(parent_chunk.get("id") or ""),
            chunk_idx=int(parent_chunk.get("chunk_idx", rank - 1)),
            score=best_score,
            title=str(parent_chunk.get("source") or "unknown"),
            label=str(parent_chunk.get("label") or parent_chunk.get("source") or "unknown"),
            section_hint=str(parent_chunk.get("section_hint") or ""),
            locator=str(parent_chunk.get("locator") or ""),
            entry_type=str(parent_chunk.get("type") or "parent_chunk"),
            file_path=str(parent_chunk.get("file_path") or ""),
            anchor=str(parent_chunk.get("anchor") or ""),
            excerpt=str(parent_chunk.get("excerpt") or parent_chunk.get("text") or ""),
            header_path=str(parent_chunk.get("header_path") or ""),
            breadcrumb=str(parent_chunk.get("breadcrumb") or parent_chunk.get("header_path") or ""),
            metadata={
                "index_id": bundle.index_id,
                "vector_backend": bundle.vector_backend,
                "matched_child_chunk_ids": [
                    str(bundle.chunks[child_idx].get("id") or f"chunk-{child_idx}")
                    for child_idx in child_hits
                    if 0 <= child_idx < len(bundle.chunks)
                ],
                "matched_child_count": len(child_hits),
                "matched_child_previews": [preview for preview in matched_previews if preview][:3],
                **dict(parent_chunk.get("metadata") or {}),
            },
        )
        sources.append(source)
        focus_hint = ""
        if matched_previews:
            focus_hint = f"\nMatched child hits:\n- " + "\n- ".join(preview[:220] for preview in matched_previews[:3])
        context_parts.append(
            f"[{sid}] {source.source} > {source.section_hint or source.breadcrumb or source.source} "
            f"(score={best_score:.3f}, matched_children={len(child_hits)}):\n{source.snippet}{focus_hint}"
        )

    return (
        sources,
        context_parts,
        [idx for idx in selected_hit_indices if 0 <= idx < len(bundle.chunks)],
        top_score,
    )


def _embedding_signature(settings: dict[str, Any]) -> str:
    provider = str(
        settings.get("embedding_provider") or settings.get("embeddings_backend") or ""
    ).strip()
    model = str(
        settings.get("embedding_model")
        or settings.get("embedding_model_custom")
        or settings.get("sentence_transformers_model")
        or settings.get("local_st_model_name")
        or ""
    ).strip()
    return f"{provider}:{model}".strip(":")


def _extract_outline_nodes(text: str, source_path: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []
    for idx, match in enumerate(
        re.finditer(r"^(#{1,6})\s+(.+)$", text, flags=re.MULTILINE), start=1
    ):
        level = len(match.group(1))
        title = match.group(2).strip()
        while stack and int(stack[-1]["level"]) >= level:
            stack.pop()
        parent_id = str(stack[-1]["id"]) if stack else ""
        header_path = [str(item["node_title"]) for item in stack] + [title]
        node = {
            "id": f"outline-{idx}",
            "parent_id": parent_id,
            "node_title": title,
            "level": level,
            "header_path": header_path,
            "char_span": [match.start(), match.end()],
            "page_span": [None, None],
            "file_path": source_path,
        }
        nodes.append(node)
        stack.append(node)
    if nodes:
        return nodes
    source_name = pathlib.Path(source_path).name
    return [
        {
            "id": "outline-root",
            "parent_id": "",
            "node_title": source_name,
            "level": 1,
            "header_path": [source_name],
            "char_span": [0, len(text)],
            "page_span": [None, None],
            "file_path": source_path,
        }
    ]


def _heading_for_offset(
    outline_nodes: list[dict[str, Any]], offset: int
) -> dict[str, Any]:
    selected = outline_nodes[0] if outline_nodes else {}
    for node in outline_nodes:
        span = node.get("char_span") or [0, 0]
        start = int(span[0] or 0)
        if start <= offset:
            selected = node
        else:
            break
    return selected


def _extract_events(text: str, source_name: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    date_pattern = re.compile(
        r"\b(?:\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
        re.IGNORECASE,
    )
    for sentence in sentences:
        snippet = " ".join(sentence.split()).strip()
        if len(snippet) < 24 or not date_pattern.search(snippet):
            continue
        date_match = date_pattern.search(snippet)
        events.append(
            {
                "date": date_match.group(0) if date_match else "undated",
                "actors": [source_name],
                "action": snippet[:220],
                "impact": snippet[220:440],
                "source_citation": "",
            }
        )
        if len(events) >= 12:
            break
    return events


def _semantic_regions_for_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks, start=1):
        regions.append(
            {
                "region_label": f"R{idx}",
                "region_type": "chunk",
                "page": None,
                "bbox": {},
                "chunk_id": str(chunk.get("id") or ""),
                "header_path": str(chunk.get("header_path") or ""),
                "file_path": str(chunk.get("file_path") or ""),
            }
        )
    return regions


def _manifest_path(path: str | pathlib.Path) -> pathlib.Path:
    raw = pathlib.Path(path)
    return raw / _MANIFEST_FILE if raw.is_dir() else raw


def _is_manifest_reference(path: pathlib.Path) -> bool:
    return path.name == _MANIFEST_FILE or path.is_dir()


def _load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _relative_to(root: pathlib.Path, value: str | pathlib.Path | None) -> str:
    if not value:
        return ""
    path = pathlib.Path(value)
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _resolve_from_manifest_root(root: pathlib.Path, path_value: str) -> pathlib.Path:
    path = pathlib.Path(path_value)
    return path if path.is_absolute() else root / path


def _legacy_manifest_for_bundle(
    path: pathlib.Path, bundle: IndexBundle
) -> IndexManifest:
    return IndexManifest(
        index_id=bundle.index_id or path.stem,
        backend=str(bundle.vector_backend or "json"),
        created_at=bundle.created_at or datetime.now(timezone.utc).isoformat(),
        embedding_signature=str(bundle.embedding_signature or ""),
        source_files=list(bundle.documents),
        manifest_path=str(path),
        bundle_path=str(path),
        vector_store_path="",
        collection_name=str(
            bundle.metadata.get("collection_name") or bundle.index_id or ""
        ),
        document_count=len(bundle.documents),
        chunk_count=len(bundle.chunks),
        outline_path="",
        semantic_regions_path="",
        events_path="",
        grounding_artifact_path=str(bundle.grounding_html_path or ""),
        restore_requirements={},
        metadata=dict(bundle.metadata or {}),
        legacy_compat=True,
    )


def _atomic_dir_stage(
    target_dir: pathlib.Path,
    stage_files: dict[pathlib.Path, Any],
    artifacts: dict[pathlib.Path, pathlib.Path] | None = None,
) -> None:
    """Atomically stage files to target_dir using temp dir + rename.

    Writes all files to a temporary directory in the same parent as target,
    then atomically renames it to the final name.

    Args:
        target_dir: The final directory path (will be replaced)
        stage_files: Dict of relative_path -> content (dict or list for JSON)
        artifacts: Dict of relative_path -> source_path for file copies
    """
    parent = target_dir.parent
    parent.mkdir(parents=True, exist_ok=True)

    tmp_dir = tempfile.mkdtemp(prefix=".index_stage_", dir=parent)
    try:
        tmp_path = pathlib.Path(tmp_dir)

        for rel_path, content in stage_files.items():
            file_path = tmp_path / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            _write_json(file_path, content)

        if artifacts:
            artifacts_dir = tmp_path / _ARTIFACTS_DIR
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            for rel_path, src_path in artifacts.items():
                dst = tmp_path / rel_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dst)

        if target_dir.exists():
            shutil.rmtree(target_dir)
        os.replace(tmp_path, target_dir)
    except Exception:
        try:
            shutil.rmtree(tmp_path)
        except OSError:
            pass
        raise


def resolve_manifest_storage_dir(
    bundle: IndexBundle,
    *,
    target_path: str | pathlib.Path | None = None,
    index_dir: str | pathlib.Path | None = None,
) -> pathlib.Path:
    if target_path is not None:
        target = pathlib.Path(target_path)
        if target.name == _MANIFEST_FILE:
            return target.parent
        if target.suffix:
            return target
        return target
    root = pathlib.Path(index_dir) if index_dir is not None else _DEFAULT_INDEX_DIR
    return root / str(bundle.index_id or "axiom-index")


def persist_index_bundle(
    bundle: IndexBundle,
    *,
    backend: str | None = None,
    target_dir: str | pathlib.Path | None = None,
    index_dir: str | pathlib.Path | None = None,
    vector_store_path: str | pathlib.Path | None = None,
    collection_name: str = "",
    restore_requirements: dict[str, Any] | None = None,
    manifest_metadata: dict[str, Any] | None = None,
) -> IndexManifest:
    backend_name = str(backend or bundle.vector_backend or "json")
    root = (
        pathlib.Path(target_dir)
        if target_dir is not None
        else resolve_manifest_storage_dir(bundle, index_dir=index_dir)
    )
    root.mkdir(parents=True, exist_ok=True)

    manifest_path = root / _MANIFEST_FILE
    bundle_path = root / _BUNDLE_FILE
    outline_path = pathlib.Path(_ARTIFACTS_DIR) / "document_outline.json"
    semantic_regions_path = pathlib.Path(_ARTIFACTS_DIR) / "semantic_regions.json"
    events_path = pathlib.Path(_ARTIFACTS_DIR) / "events.json"

    grounding_artifact_path = ""
    artifacts: dict[pathlib.Path, pathlib.Path] = {}
    grounding_source = str(bundle.grounding_html_path or "").strip()
    if grounding_source:
        source_path = pathlib.Path(grounding_source)
        if source_path.exists() and source_path.is_file():
            grounding_artifact_rel = pathlib.Path(_ARTIFACTS_DIR) / source_path.name
            artifacts[grounding_artifact_rel] = source_path
            grounding_artifact_path = str(grounding_artifact_rel)
        else:
            grounding_artifact_path = grounding_source

    merged_metadata = {
        **dict(bundle.metadata or {}),
        **dict(manifest_metadata or {}),
        "collection_name": str(
            collection_name or bundle.metadata.get("collection_name") or ""
        ),
        "vector_store_path": str(vector_store_path) if vector_store_path else "",
        "restore_requirements": dict(restore_requirements or {}),
    }
    bundle.vector_backend = backend_name
    bundle.index_path = str(manifest_path)
    bundle.grounding_html_path = grounding_artifact_path
    bundle.metadata = merged_metadata

    stage_files = {
        bundle_path.relative_to(root): bundle.to_payload(),
        outline_path: list(bundle.document_outline),
        semantic_regions_path: list(bundle.semantic_regions),
        events_path: list(bundle.events),
    }

    _atomic_dir_stage(root, stage_files, artifacts)

    manifest = IndexManifest(
        index_id=str(bundle.index_id or root.name),
        backend=backend_name,
        created_at=str(bundle.created_at or datetime.now(timezone.utc).isoformat()),
        embedding_signature=str(bundle.embedding_signature or ""),
        source_files=list(bundle.documents),
        manifest_path=str(manifest_path),
        bundle_path=_BUNDLE_FILE,
        vector_store_path=str(vector_store_path) if vector_store_path else "",
        collection_name=str(
            collection_name
            or merged_metadata.get("collection_name")
            or bundle.index_id
            or ""
        ),
        document_count=len(bundle.documents),
        chunk_count=len(bundle.chunks),
        outline_path=str(outline_path),
        semantic_regions_path=str(semantic_regions_path),
        events_path=str(events_path),
        grounding_artifact_path=grounding_artifact_path,
        restore_requirements=dict(restore_requirements or {}),
        metadata=merged_metadata,
    )

    _write_json(manifest_path, manifest.to_payload())
    return manifest


def save_index_bundle(
    bundle: IndexBundle,
    *,
    target_path: str | pathlib.Path | None = None,
    index_dir: str | pathlib.Path | None = None,
) -> pathlib.Path:
    if target_path is not None:
        out_path = pathlib.Path(target_path)
        if out_path.suffix.lower() == ".json" and out_path.name != _MANIFEST_FILE:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            bundle.index_path = str(out_path)
            out_path.write_text(
                json.dumps(bundle.to_payload(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return out_path
        manifest = persist_index_bundle(
            bundle,
            backend=bundle.vector_backend,
            target_dir=resolve_manifest_storage_dir(bundle, target_path=out_path),
        )
        return pathlib.Path(manifest.manifest_path)

    manifest = persist_index_bundle(
        bundle,
        backend=bundle.vector_backend,
        index_dir=index_dir,
    )
    return pathlib.Path(manifest.manifest_path)


def refresh_index_bundle(bundle: IndexBundle) -> pathlib.Path:
    """Rewrite bundle/manifest metadata in-place for an existing persisted index."""
    candidate = pathlib.Path(str(bundle.index_path or ""))
    if not candidate.exists() and candidate.name != _MANIFEST_FILE:
        raise FileNotFoundError(f"Persisted index not found: {candidate}")
    manifest = load_index_manifest(candidate)
    if manifest.legacy_compat:
        return save_index_bundle(bundle, target_path=manifest.manifest_path)

    root = pathlib.Path(manifest.manifest_path).parent
    vector_store_path = (
        _resolve_from_manifest_root(root, manifest.vector_store_path)
        if manifest.vector_store_path
        else None
    )
    rewritten = persist_index_bundle(
        bundle,
        backend=manifest.backend,
        target_dir=root,
        vector_store_path=vector_store_path,
        collection_name=manifest.collection_name,
        restore_requirements=manifest.restore_requirements,
        manifest_metadata=manifest.metadata,
    )
    return pathlib.Path(rewritten.manifest_path)


def load_index_manifest(path: str | pathlib.Path) -> IndexManifest:
    candidate = pathlib.Path(path)
    if candidate.is_dir():
        candidate = candidate / _MANIFEST_FILE
    if candidate.name == _MANIFEST_FILE:
        payload = _load_json(candidate)
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid manifest payload: {candidate}")
        manifest = IndexManifest.from_payload(payload)
        manifest.manifest_path = str(candidate)
        return manifest

    bundle = load_index_bundle(candidate)
    return _legacy_manifest_for_bundle(candidate, bundle)


def list_index_manifests(index_dir: str | pathlib.Path) -> list[IndexManifest]:
    root = pathlib.Path(index_dir)
    if not root.exists():
        return []
    manifests: list[IndexManifest] = []
    for path in sorted(root.glob(f"*/{_MANIFEST_FILE}")):
        try:
            manifests.append(load_index_manifest(path))
        except Exception:
            continue
    for path in sorted(root.glob("*.json")):
        if path.name == _MANIFEST_FILE:
            continue
        try:
            manifests.append(load_index_manifest(path))
        except Exception:
            continue
    return manifests


def load_index_bundle(path: str | pathlib.Path) -> IndexBundle:
    candidate = pathlib.Path(path)
    if _is_manifest_reference(candidate):
        manifest = load_index_manifest(candidate)
        if manifest.legacy_compat and manifest.bundle_path == str(candidate):
            payload = _load_json(candidate)
            bundle = IndexBundle.from_payload(
                payload if isinstance(payload, dict) else {}
            )
            bundle.index_path = str(candidate)
            return bundle

        root = pathlib.Path(manifest.manifest_path).parent
        bundle_path = _resolve_from_manifest_root(root, manifest.bundle_path)
        payload = _load_json(bundle_path)
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid bundle payload: {bundle_path}")
        bundle = IndexBundle.from_payload(payload)
        bundle.index_path = str(manifest.manifest_path)
        bundle.vector_backend = str(manifest.backend or bundle.vector_backend or "json")
        if not bundle.embedding_signature:
            bundle.embedding_signature = str(manifest.embedding_signature or "")
        if not bundle.document_outline and manifest.outline_path:
            outline_path = _resolve_from_manifest_root(root, manifest.outline_path)
            if outline_path.exists():
                outline_payload = _load_json(outline_path)
                if isinstance(outline_payload, list):
                    bundle.document_outline = [
                        dict(item) for item in outline_payload if isinstance(item, dict)
                    ]
        if not bundle.semantic_regions and manifest.semantic_regions_path:
            regions_path = _resolve_from_manifest_root(
                root, manifest.semantic_regions_path
            )
            if regions_path.exists():
                regions_payload = _load_json(regions_path)
                if isinstance(regions_payload, list):
                    bundle.semantic_regions = [
                        dict(item) for item in regions_payload if isinstance(item, dict)
                    ]
        if not bundle.events and manifest.events_path:
            events_path = _resolve_from_manifest_root(root, manifest.events_path)
            if events_path.exists():
                events_payload = _load_json(events_path)
                if isinstance(events_payload, list):
                    bundle.events = [
                        dict(item) for item in events_payload if isinstance(item, dict)
                    ]
        if manifest.grounding_artifact_path:
            grounding_path = _resolve_from_manifest_root(
                root, manifest.grounding_artifact_path
            )
            bundle.grounding_html_path = (
                str(grounding_path)
                if grounding_path.exists()
                else str(manifest.grounding_artifact_path)
            )
        bundle.metadata = {
            **dict(bundle.metadata or {}),
            **dict(manifest.metadata or {}),
            "manifest_path": str(manifest.manifest_path),
            "collection_name": str(manifest.collection_name or ""),
            "vector_store_path": str(manifest.vector_store_path or ""),
            "restore_requirements": dict(manifest.restore_requirements or {}),
        }
        return bundle

    payload = _load_json(candidate)
    bundle = IndexBundle.from_payload(payload if isinstance(payload, dict) else {})
    bundle.index_path = str(candidate)
    return bundle


def build_index_bundle(
    documents: list[str],
    settings: dict[str, Any],
    *,
    post_message: Callable[[dict[str, Any]], None] | None = None,
    cancel_token: Any | None = None,
) -> IndexBundle:
    chunk_size = int(settings.get("chunk_size", 800))
    overlap = int(settings.get("chunk_overlap", 100))
    use_kreuzberg = str(settings.get("document_loader", "auto") or "auto") != "plain"

    try:
        emb = create_embeddings(settings)
    except (ValueError, ImportError):
        emb = MockEmbeddings(dimensions=_EMB_DIM)

    chunk_strategy = str(
        settings.get("chunk_strategy", "fixed") or "fixed"
    ).strip().lower()
    parent_chunk_size = max(
        chunk_size + 1,
        int(settings.get("parent_chunk_size") or max(chunk_size * 3, 2400)),
    )
    parent_chunk_overlap = max(
        0,
        min(
            parent_chunk_size - 1,
            int(settings.get("parent_chunk_overlap") or max(overlap * 2, min(chunk_size, 240))),
        ),
    )

    all_chunks: list[dict[str, Any]] = []
    total_docs = max(1, len(documents))
    all_outline_nodes: list[dict[str, Any]] = []
    all_events: list[dict[str, Any]] = []
    # Collect per-document raw chunks for optional summary generation.
    per_doc_chunks: list[tuple[str, str, list[str]]] = []  # (source, path, chunks)
    for doc_idx, path in enumerate(documents, start=1):
        if cancel_token is not None and getattr(cancel_token, "cancelled", False):
            break
        source = pathlib.Path(path).name
        if callable(post_message):
            post_message({"type": "status", "text": f"Reading {source}…"})
        text = load_document(path, use_kreuzberg=use_kreuzberg)
        outline_nodes = _extract_outline_nodes(text, str(path))
        all_outline_nodes.extend(outline_nodes)
        all_events.extend(_extract_events(text, source))
        raw_chunks = chunk_text_semantic(text, chunk_size, overlap, strategy=chunk_strategy)
        per_doc_chunks.append((source, str(path), list(raw_chunks)))
        doc_child_chunks: list[dict[str, Any]] = []
        search_cursor = 0
        for idx, chunk in enumerate(raw_chunks):
            char_start = text.find(chunk, search_cursor)
            if char_start < 0:
                char_start = text.find(chunk)
            if char_start < 0:
                char_start = search_cursor
            char_end = char_start + len(chunk)
            search_cursor = max(char_end - overlap, char_start)
            heading = _heading_for_offset(outline_nodes, char_start)
            header_tokens = list(heading.get("header_path") or [])
            header_path = " > ".join(
                [str(item).strip() for item in header_tokens if str(item).strip()]
            )
            doc_child_chunks.append(
                {
                    "id": f"{source}::chunk{idx}",
                    "text": chunk,
                    "source": source,
                    "chunk_idx": idx,
                    "file_path": str(path),
                    "source_path": str(path),
                    "title": source,
                    "label": source,
                    "section_hint": str(heading.get("node_title") or source),
                    "header_path": header_path,
                    "breadcrumb": header_path or source,
                    "locator": f"chunk {idx}",
                    "anchor": f"chunk-{idx}",
                    "excerpt": chunk[:320],
                    "type": "child_chunk",
                    "char_span": [char_start, char_end],
                    "metadata": {
                        "source_path": str(path),
                        "char_span": [char_start, char_end],
                        "header_path": header_path,
                        "content_type": "child_chunk",
                    },
                }
            )
        all_chunks.extend(doc_child_chunks)
        parent_windows = _build_parent_child_windows(
            doc_child_chunks,
            parent_chunk_size=parent_chunk_size,
            parent_chunk_overlap=parent_chunk_overlap,
        )
        for parent_idx, window in enumerate(parent_windows):
            if not window:
                continue
            parent_id = f"{source}::parent{parent_idx}"
            first_child = window[0]
            last_child = window[-1]
            char_start = int((first_child.get("char_span") or [0, 0])[0] or 0)
            char_end = int((last_child.get("char_span") or [0, 0])[1] or char_start)
            parent_text = "\n\n".join(str(child.get("text") or "") for child in window).strip()
            child_ids = [str(child.get("id") or "") for child in window if str(child.get("id") or "").strip()]
            section_hint = str(first_child.get("section_hint") or source)
            header_path = str(first_child.get("header_path") or "")
            for child in window:
                child_metadata = dict(child.get("metadata") or {})
                child_metadata["parent_chunk_id"] = parent_id
                child_metadata["content_type"] = "child_chunk"
                child["metadata"] = child_metadata
            all_chunks.append(
                {
                    "id": parent_id,
                    "text": parent_text,
                    "source": source,
                    "chunk_idx": parent_idx,
                    "file_path": str(path),
                    "source_path": str(path),
                    "title": source,
                    "label": f"{source} (context {parent_idx + 1})",
                    "section_hint": section_hint,
                    "header_path": header_path,
                    "breadcrumb": header_path or source,
                    "locator": f"context {parent_idx + 1}",
                    "anchor": f"context-{parent_idx + 1}",
                    "excerpt": parent_text[:320],
                    "type": "parent_chunk",
                    "char_span": [char_start, char_end],
                    "metadata": {
                        "source_path": str(path),
                        "char_span": [char_start, char_end],
                        "header_path": header_path,
                        "child_chunk_ids": child_ids,
                        "child_count": len(child_ids),
                        "content_type": "parent_chunk",
                    },
                }
            )
        if callable(post_message):
            post_message(
                {
                    "type": "progress",
                    "current": doc_idx,
                    "total": total_docs,
                }
            )
            post_message(
                {
                    "type": "log",
                    "text": f"  {source}: {len(raw_chunks)} chunk(s) prepared",
                }
            )

    if callable(post_message):
        post_message({"type": "status", "text": "Computing embeddings…"})

    # ── Document summary generation (map-reduce) ──────────────────────
    build_digest = settings.get("build_digest_index", False)
    if build_digest and per_doc_chunks:
        if callable(post_message):
            post_message({"type": "status", "text": "Generating document summaries…"})
        try:
            from axiom_app.services.summary_service import (
                build_summary_chunk,
                generate_document_summary,
            )
            from axiom_app.utils.llm_providers import create_llm

            llm = create_llm(settings)
            for source, file_path, doc_chunk_texts in per_doc_chunks:
                summary = generate_document_summary(doc_chunk_texts, llm)
                if summary:
                    all_chunks.append(
                        build_summary_chunk(summary, source, file_path)
                    )
                    if callable(post_message):
                        post_message(
                            {"type": "log", "text": f"  {source}: summary generated"}
                        )
        except Exception as exc:  # noqa: BLE001
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "Summary generation failed: %s", exc
            )
            # Summary generation is best-effort; do not fail the build.
            if callable(post_message):
                post_message(
                    {"type": "log", "text": "  (summary generation skipped — LLM unavailable)"}
                )

    embeddings = emb.embed_documents([chunk["text"] for chunk in all_chunks])
    graph, entity_to_chunks = build_knowledge_graph(
        [chunk["text"] for chunk in all_chunks]
    )
    digest = hashlib.sha1(
        "||".join(sorted(str(path) for path in documents)).encode(
            "utf-8", errors="ignore"
        )
    ).hexdigest()[:12]
    return IndexBundle(
        index_id=f"axiom-{digest}",
        created_at=datetime.now(timezone.utc).isoformat(),
        documents=list(documents),
        chunks=all_chunks,
        embeddings=embeddings,
        knowledge_graph=graph,
        entity_to_chunks=entity_to_chunks,
        vector_backend=str(settings.get("vector_db_type", "json") or "json"),
        embedding_signature=_embedding_signature(settings),
        semantic_regions=_semantic_regions_for_chunks(all_chunks),
        document_outline=all_outline_nodes,
        events=all_events,
        metadata={
            "selected_source_paths": list(documents),
            "document_title": pathlib.Path(documents[0]).name if documents else "",
            "parent_child_enabled": True,
            "parent_chunk_size": parent_chunk_size,
            "parent_chunk_overlap": parent_chunk_overlap,
        },
    )


def _score_for_index(score_lookup: dict[int, float] | list[float], idx: int) -> float:
    if isinstance(score_lookup, dict):
        return float(score_lookup.get(idx, 0.0) or 0.0)
    if 0 <= idx < len(score_lookup):
        return float(score_lookup[idx] or 0.0)
    return 0.0


def select_hit_indices(
    bundle: IndexBundle,
    question: str,
    ranked_indices: list[int],
    settings: dict[str, Any],
) -> list[int]:
    top_k = int(settings.get("top_k", 3))
    kg_mode = str(settings.get("kg_query_mode", "hybrid") or "hybrid")
    use_reranker = bool(settings.get("use_reranker", False))
    ranked_indices = [
        idx for idx in ranked_indices
        if 0 <= idx < len(bundle.chunks) and _chunk_is_allowed(bundle.chunks[idx], settings)
    ]
    graph_hits: list[int] = []
    if bundle.knowledge_graph is not None and bundle.entity_to_chunks:
        graph_hits = collect_graph_chunk_candidates(
            graph=bundle.knowledge_graph,
            entity_to_chunks=bundle.entity_to_chunks,
            question=question,
            mode=kg_mode,
            limit=max(top_k * 3, top_k),
        )
        graph_hits = [
            idx for idx in graph_hits
            if 0 <= idx < len(bundle.chunks) and _chunk_is_allowed(bundle.chunks[idx], settings)
        ]

    if use_reranker:
        return rerank_hits(bundle, question, ranked_indices, graph_hits, settings)

    if kg_mode in {"naive", "bypass"} or not graph_hits:
        return ranked_indices[:top_k]

    hit_set = set(graph_hits)
    return (graph_hits + [idx for idx in ranked_indices if idx not in hit_set])[:top_k]


def build_query_result(
    bundle: IndexBundle,
    question: str,
    hit_indices: list[int],
    score_lookup: dict[int, float] | list[float],
    settings: dict[str, Any] | None = None,
) -> QueryResult:
    resolved_settings = dict(settings or {})
    top_k = int(resolved_settings.get("top_k", 5) or 5)
    retrieval_mode = str(resolved_settings.get("retrieval_mode", "flat") or "flat").strip().lower()
    if retrieval_mode == "hierarchical":
        sources, context_parts, selected_hits, top_score = _build_hierarchical_sources(
            bundle,
            hit_indices,
            score_lookup,
            top_k=top_k,
        )
        return QueryResult(
            prompt=question,
            context_block="\n\n".join(context_parts)
            if context_parts
            else "(no relevant passages found)",
            sources=sources,
            hit_indices=selected_hits,
            top_score=top_score,
        )

    sources: list[EvidenceSource] = []
    context_parts: list[str] = []
    for rank, idx in enumerate(hit_indices, start=1):
        if idx < 0 or idx >= len(bundle.chunks):
            continue
        chunk = bundle.chunks[idx]
        sid = f"S{rank}"
        score = _score_for_index(score_lookup, idx)
        source = EvidenceSource(
            sid=sid,
            source=str(chunk.get("source") or "unknown"),
            snippet=str(chunk.get("text") or "").strip(),
            chunk_id=str(chunk.get("id") or ""),
            chunk_idx=int(chunk.get("chunk_idx", rank - 1)),
            score=score,
            title=str(chunk.get("source") or "unknown"),
            label=str(chunk.get("label") or chunk.get("source") or "unknown"),
            section_hint=str(chunk.get("section_hint") or ""),
            locator=str(chunk.get("locator") or ""),
            entry_type=str(chunk.get("type") or "chunk"),
            file_path=str(chunk.get("file_path") or ""),
            anchor=str(chunk.get("anchor") or ""),
            excerpt=str(chunk.get("excerpt") or chunk.get("text") or ""),
            header_path=str(chunk.get("header_path") or ""),
            breadcrumb=str(chunk.get("breadcrumb") or chunk.get("header_path") or ""),
            metadata={
                "index_id": bundle.index_id,
                "vector_backend": bundle.vector_backend,
                **dict(chunk.get("metadata") or {}),
            },
        )
        sources.append(source)
        context_parts.append(
            f"[{sid}] {source.source} > chunk {source.chunk_idx} "
            f"(score={source.score:.3f}):\n{source.snippet}"
        )

    top_score = 0.0
    if hit_indices:
        top_score = _score_for_index(score_lookup, hit_indices[0])
    return QueryResult(
        prompt=question,
        context_block="\n\n".join(context_parts)
        if context_parts
        else "(no relevant passages found)",
        sources=sources,
        hit_indices=[idx for idx in hit_indices if 0 <= idx < len(bundle.chunks)],
        top_score=top_score,
    )


def query_index_bundle(
    bundle: IndexBundle,
    question: str,
    settings: dict[str, Any],
) -> QueryResult:
    try:
        emb = create_embeddings(settings)
    except (ValueError, ImportError):
        emb = MockEmbeddings(dimensions=_EMB_DIM)

    q_vec = emb.embed_query(question)
    scores = [cosine_similarity(q_vec, vector) for vector in bundle.embeddings]
    ranked = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
    hits = select_hit_indices(bundle, question, ranked, settings)
    return build_query_result(bundle, question, hits, scores, settings=settings)
