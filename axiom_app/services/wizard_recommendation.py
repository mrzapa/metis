"""Monolith-style setup recommendation and cost-estimation helpers."""

from __future__ import annotations

from datetime import datetime
import os
import pathlib
from typing import Any

from axiom_app.services.index_service import load_index_bundle, load_index_manifest

TOKENS_TO_CHARS_RATIO = 4


def humanize_bytes(num_bytes: int) -> str:
    value = float(max(0, int(num_bytes or 0)))
    for suffix in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or suffix == "TB":
            return f"{value:.1f} {suffix}" if suffix != "B" else f"{int(value)} B"
        value /= 1024
    return f"{int(num_bytes or 0)} B"


def gather_auto_metadata(
    *,
    file_path: str | None = None,
    index_path: str | None = None,
) -> dict[str, Any]:
    metadata = {
        "file_type": "unknown",
        "size_bytes": 0,
        "estimated_pages": 0,
        "has_images": False,
        "chunk_count": 0,
        "estimated_tokens": 0,
        "source": "file" if file_path else "index",
        "modified_at": "",
    }
    candidate = pathlib.Path(file_path) if file_path else None
    if candidate and candidate.is_file():
        ext = candidate.suffix.lower() or "(no extension)"
        metadata["file_type"] = ext
        try:
            size_bytes = int(candidate.stat().st_size)
            metadata["size_bytes"] = size_bytes
            metadata["estimated_tokens"] = max(1, round(size_bytes / max(1, TOKENS_TO_CHARS_RATIO)))
            metadata["modified_at"] = datetime.fromtimestamp(candidate.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            pass
        if ext == ".pdf":
            try:
                from pypdf import PdfReader

                reader = PdfReader(str(candidate))
                metadata["estimated_pages"] = len(reader.pages)
                for page in reader.pages[: min(8, len(reader.pages))]:
                    resources = page.get("/Resources") or {}
                    xobj = resources.get("/XObject") if hasattr(resources, "get") else None
                    if xobj:
                        metadata["has_images"] = True
                        break
            except Exception:
                pass
        elif ext in {".epub", ".pptx", ".docx"}:
            metadata["has_images"] = True
        return metadata

    candidate_index = pathlib.Path(index_path) if index_path else None
    if not candidate_index:
        return metadata
    metadata["source"] = "index"
    root = candidate_index.parent if candidate_index.is_file() and candidate_index.name == "manifest.json" else candidate_index
    if candidate_index.is_file() and candidate_index.suffix.lower() == ".json" and candidate_index.name != "manifest.json":
        root = candidate_index
    if root.exists():
        if root.is_dir():
            total_size = 0
            for file in root.rglob("*"):
                if file.is_file():
                    try:
                        total_size += int(file.stat().st_size)
                    except OSError:
                        continue
            metadata["size_bytes"] = total_size
        else:
            try:
                metadata["size_bytes"] = int(root.stat().st_size)
            except OSError:
                pass
        metadata["estimated_tokens"] = max(
            1,
            round(int(metadata["size_bytes"] or 0) / max(1, TOKENS_TO_CHARS_RATIO)),
        )

    try:
        manifest = load_index_manifest(candidate_index)
        metadata["chunk_count"] = int(manifest.chunk_count or 0)
        source_files = [str(item) for item in (manifest.source_files or []) if str(item).strip()]
        if source_files:
            metadata["file_type"] = pathlib.Path(source_files[0]).suffix.lower() or metadata["file_type"]
    except Exception:
        manifest = None

    try:
        bundle = load_index_bundle(candidate_index)
        metadata["chunk_count"] = max(int(metadata["chunk_count"] or 0), len(bundle.chunks))
        if bundle.documents:
            metadata["file_type"] = pathlib.Path(bundle.documents[0]).suffix.lower() or metadata["file_type"]
    except Exception:
        pass
    return metadata


def recommend_auto_settings(
    *,
    file_path: str | None = None,
    index_path: str | None = None,
) -> dict[str, Any]:
    md = gather_auto_metadata(file_path=file_path, index_path=index_path)
    size_mb = float(md.get("size_bytes", 0)) / (1024 * 1024)
    file_type = str(md.get("file_type") or "unknown").lower()
    pages = int(md.get("estimated_pages") or 0)

    if file_type in {".txt", ".md", ".html", ".htm"} and size_mb <= 1.5:
        chunk_size, overlap = 400, 100
        retrieve_k, final_k = 18, 4
        mmr_lambda, use_reranker = 0.55, False
        digest_on, comp_on, comp_depth = False, False, "Standard"
    elif file_type == ".pdf" and (pages >= 120 or size_mb >= 8):
        chunk_size, overlap = 800, 200
        retrieve_k, final_k = 34, 9
        mmr_lambda, use_reranker = 0.4, True
        digest_on, comp_on, comp_depth = True, True, "Deep"
    elif file_type == ".pdf":
        chunk_size, overlap = 650, 170
        retrieve_k, final_k = 26, 6
        mmr_lambda, use_reranker = 0.45, True
        digest_on, comp_on, comp_depth = True, False, "Standard"
    else:
        chunk_size, overlap = 550, 130
        retrieve_k, final_k = 22, 5
        mmr_lambda, use_reranker = 0.5, True
        digest_on, comp_on, comp_depth = True, False, "Standard"

    if md.get("has_images"):
        retrieve_k = max(retrieve_k, 28)
        final_k = max(final_k, 7)
        mmr_lambda = min(mmr_lambda, 0.45)

    recommendation = {
        "metadata": md,
        "chunk_size": chunk_size,
        "chunk_overlap": overlap,
        "retrieval_k": retrieve_k,
        "final_k": final_k,
        "fallback_final_k": final_k,
        "mmr_lambda": mmr_lambda,
        "use_reranker": use_reranker,
        "build_digest_index": digest_on,
        "build_comprehension_index": comp_on,
        "comprehension_extraction_depth": comp_depth,
        "prefer_comprehension_index": True,
        "retrieval_mode": "hierarchical" if digest_on else "flat",
        "agentic_mode": bool(comp_on or final_k >= 7),
        "agentic_max_iterations": 3 if comp_on else 2,
        "deepread_mode": bool(comp_on and (pages >= 100 or size_mb >= 6)),
    }
    return recommendation


def describe_auto_recommendation(rec: dict[str, Any]) -> str:
    md = dict(rec.get("metadata") or {})
    details = [
        humanize_bytes(int(md.get("size_bytes") or 0)),
        str(md.get("file_type") or "unknown"),
    ]
    if md.get("estimated_pages"):
        details.append(f"{int(md['estimated_pages'])} pages")
    if md.get("has_images"):
        details.append("images detected")
    return (
        "Auto recommendation from "
        f"{md.get('source', 'unknown')} metadata ({', '.join(details)}): "
        f"chunk {rec.get('chunk_size')}/{rec.get('chunk_overlap')}, "
        f"k={rec.get('retrieval_k')}->{rec.get('final_k')}, "
        f"MMR {rec.get('mmr_lambda')}, reranker {'on' if rec.get('use_reranker') else 'off'}, "
        f"digest {'on' if rec.get('build_digest_index') else 'off'}"
    )


def estimate_setup_cost(
    recommendation: dict[str, Any],
    *,
    llm_provider: str,
    embedding_provider: str,
) -> str:
    md = dict(recommendation.get("metadata") or {})
    estimated_tokens = int(md.get("estimated_tokens") or 0)
    llm_name = str(llm_provider or "").strip().lower()
    embedding_name = str(embedding_provider or "").strip().lower()
    if llm_name in {"mock", "local_lm_studio", "local_gguf"} and embedding_name in {
        "mock",
        "local_huggingface",
        "local_sentence_transformers",
    }:
        return "Mock/local providers: low cost. Runtime depends mainly on local hardware."

    ingest_multiplier = 1.0
    if recommendation.get("build_digest_index"):
        ingest_multiplier += 0.35
    if recommendation.get("build_comprehension_index"):
        depth = str(recommendation.get("comprehension_extraction_depth") or "Standard").lower()
        depth_multiplier = {"light": 1.4, "standard": 1.8, "deep": 2.6, "exhaustive": 3.2}.get(depth, 1.8)
        ingest_multiplier += depth_multiplier

    ingest_tokens = max(1, round(estimated_tokens * ingest_multiplier))
    retrieval_tokens = max(
        1,
        round(
            int(recommendation.get("retrieval_k") or 0)
            * max(120, int(recommendation.get("chunk_size") or 0) // 3)
            / max(1, TOKENS_TO_CHARS_RATIO)
        ),
    )
    provider_label = llm_provider or "selected LLM"
    return (
        f"Estimated ingestion load: ~{ingest_tokens:,} tokens. "
        f"Typical query context: ~{retrieval_tokens:,} tokens plus answer tokens on {provider_label}. "
        "Actual cloud cost depends on model pricing and prompt length."
    )


def resolve_index_option_path(option_path: str) -> str:
    path = pathlib.Path(str(option_path or ""))
    if not path:
        return ""
    if path.exists():
        return str(path)
    return os.path.abspath(str(path))
