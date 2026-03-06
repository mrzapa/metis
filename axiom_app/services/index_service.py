"""Shared index build, persistence, and retrieval helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import pathlib
from typing import Any, Callable

from axiom_app.models.session_types import EvidenceSource
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

    def to_payload(self) -> dict[str, Any]:
        edges: dict[str, dict[str, list[str]]] = {}
        if self.knowledge_graph is not None:
            for src, targets in self.knowledge_graph.edges.items():
                edges[src] = {
                    tgt: sorted(relations)
                    for tgt, relations in targets.items()
                }
        return {
            "index_id": self.index_id,
            "created_at": self.created_at,
            "documents": list(self.documents),
            "chunks": list(self.chunks),
            "embeddings": list(self.embeddings),
            "knowledge_graph": {
                "nodes": dict(self.knowledge_graph.nodes if self.knowledge_graph else {}),
                "edges": edges,
            },
            "entity_to_chunks": {
                key: sorted(values)
                for key, values in (self.entity_to_chunks or {}).items()
            },
            "index_path": self.index_path,
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
        )


@dataclass(slots=True)
class QueryResult:
    prompt: str
    context_block: str
    sources: list[EvidenceSource]
    hit_indices: list[int]
    top_score: float


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

    all_chunks: list[dict[str, Any]] = []
    total_docs = max(1, len(documents))
    for doc_idx, path in enumerate(documents, start=1):
        if cancel_token is not None and getattr(cancel_token, "cancelled", False):
            break
        source = pathlib.Path(path).name
        if callable(post_message):
            post_message({"type": "status", "text": f"Reading {source}…"})
        text = load_document(path, use_kreuzberg=use_kreuzberg)
        raw_chunks = chunk_text(text, chunk_size, overlap)
        for idx, chunk in enumerate(raw_chunks):
            all_chunks.append(
                {
                    "id": f"{source}::chunk{idx}",
                    "text": chunk,
                    "source": source,
                    "chunk_idx": idx,
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

    embeddings = emb.embed_documents([chunk["text"] for chunk in all_chunks])
    graph, entity_to_chunks = build_knowledge_graph([chunk["text"] for chunk in all_chunks])
    digest = hashlib.sha1(
        "||".join(sorted(str(path) for path in documents)).encode("utf-8", errors="ignore")
    ).hexdigest()[:12]
    return IndexBundle(
        index_id=f"axiom-{digest}",
        created_at=datetime.now(timezone.utc).isoformat(),
        documents=list(documents),
        chunks=all_chunks,
        embeddings=embeddings,
        knowledge_graph=graph,
        entity_to_chunks=entity_to_chunks,
    )


def save_index_bundle(
    bundle: IndexBundle,
    *,
    target_path: str | pathlib.Path | None = None,
    index_dir: str | pathlib.Path | None = None,
) -> pathlib.Path:
    if target_path is not None:
        out_path = pathlib.Path(target_path)
    else:
        root = pathlib.Path(index_dir) if index_dir is not None else _DEFAULT_INDEX_DIR
        out_path = root / f"{bundle.index_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bundle.index_path = str(out_path)
    out_path.write_text(
        json.dumps(bundle.to_payload(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


def load_index_bundle(path: str | pathlib.Path) -> IndexBundle:
    payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    bundle = IndexBundle.from_payload(payload)
    bundle.index_path = str(pathlib.Path(path))
    return bundle


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

    top_k = int(settings.get("top_k", 3))
    kg_mode = str(settings.get("kg_query_mode", "hybrid") or "hybrid")
    graph_hits: list[int] = []
    if bundle.knowledge_graph is not None and bundle.entity_to_chunks:
        graph_hits = collect_graph_chunk_candidates(
            graph=bundle.knowledge_graph,
            entity_to_chunks=bundle.entity_to_chunks,
            question=question,
            mode=kg_mode,
            limit=max(top_k * 3, top_k),
        )

    if kg_mode in {"naive", "bypass"} or not graph_hits:
        hits = ranked[:top_k]
    else:
        hit_set = set(graph_hits)
        hits = (graph_hits + [idx for idx in ranked if idx not in hit_set])[:top_k]

    sources: list[EvidenceSource] = []
    context_parts: list[str] = []
    for rank, idx in enumerate(hits, start=1):
        chunk = bundle.chunks[idx]
        sid = f"S{rank}"
        source = EvidenceSource(
            sid=sid,
            source=str(chunk.get("source") or "unknown"),
            snippet=str(chunk.get("text") or "").strip(),
            chunk_id=str(chunk.get("id") or ""),
            chunk_idx=int(chunk.get("chunk_idx", rank - 1)),
            score=float(scores[idx]),
            title=str(chunk.get("source") or "unknown"),
            metadata={"index_id": bundle.index_id},
        )
        sources.append(source)
        context_parts.append(
            f"[{sid}] {source.source} > chunk {source.chunk_idx} "
            f"(score={source.score:.3f}):\n{source.snippet}"
        )

    return QueryResult(
        prompt=question,
        context_block="\n\n".join(context_parts) if context_parts else "(no relevant passages found)",
        sources=sources,
        hit_indices=hits,
        top_score=scores[hits[0]] if hits else 0.0,
    )
