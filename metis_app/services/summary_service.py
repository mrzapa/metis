"""Map-reduce document summarisation for index bundles.

Inspired by ApeRAG's ``SummaryIndexer``, this module generates a concise
summary of each document during the indexing phase.  The summary is
embedded alongside regular chunks so that high-level "what is this about?"
queries can match against it.

The summarisation uses a simple map-reduce strategy:

1. **Map** – each chunk is summarised independently (1-2 sentences).
2. **Reduce** – chunk summaries are combined into a final document
   summary (2-4 sentences).

The :func:`generate_document_summary` function is called from the
indexing pipeline when the ``build_digest_index`` setting is ``True``.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_CHUNK_SUMMARY_PROMPT = (
    "Summarise the following text excerpt in 1–2 concise sentences. "
    "Use the same language as the source text. "
    "Output ONLY the summary — no preamble, labels, or extra formatting.\n\n"
    "Text:\n{text}\n\nSummary:"
)

_REDUCE_PROMPT = (
    "Below are summaries of consecutive sections of a document. "
    "Combine them into a single coherent summary of 2–4 sentences. "
    "Use the same language as the source material. "
    "Highlight the document's main topic and most important insights. "
    "Output ONLY the final summary — no preamble, labels, or extra formatting.\n\n"
    "Section summaries:\n{summaries}\n\nFinal summary:"
)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _invoke_llm(llm: Any, system: str, user: str) -> str:
    """Call *llm* and return the response text, or empty string on failure."""
    try:
        resp = llm.invoke([
            {"type": "system", "content": system},
            {"type": "human", "content": user},
        ])
        return str(getattr(resp, "content", resp) or "").strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM invocation failed during summarisation: %s", exc)
        return ""


def _summarise_chunk(chunk_text: str, llm: Any) -> str:
    """Map step: produce a short summary of a single chunk."""
    if not chunk_text.strip():
        return ""
    prompt = _CHUNK_SUMMARY_PROMPT.format(text=chunk_text)
    return _invoke_llm(
        llm,
        "You produce brief, accurate text summaries.",
        prompt,
    )


def _reduce_summaries(summaries: list[str], llm: Any) -> str:
    """Reduce step: combine chunk summaries into a final document summary."""
    combined = "\n\n".join(f"- {s}" for s in summaries if s)
    prompt = _REDUCE_PROMPT.format(summaries=combined)
    return _invoke_llm(
        llm,
        "You combine section summaries into a single coherent document summary.",
        prompt,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_document_summary(
    chunks: list[str],
    llm: Any,
    *,
    max_map_chunks: int = 30,
) -> str:
    """Generate a document-level summary using map-reduce over *chunks*.

    Parameters
    ----------
    chunks:
        List of chunk texts from the document (already split).
    llm:
        An LLM instance that supports ``.invoke()`` (LangChain style).
    max_map_chunks:
        Maximum number of chunks to summarise individually in the map
        phase (to limit API calls for very large documents).

    Returns
    -------
    str
        A concise document summary, or an empty string on failure.
    """
    if not chunks:
        return ""

    # Small documents: summarise directly.
    combined = "\n\n".join(chunks)
    if len(combined) < 4000:
        result = _summarise_chunk(combined, llm)
        return result if result else ""

    # Map phase: summarise each chunk.
    step = max(1, len(chunks) // max_map_chunks) if len(chunks) > max_map_chunks else 1
    selected = chunks[::step][:max_map_chunks]

    chunk_summaries: list[str] = []
    for chunk in selected:
        summary = _summarise_chunk(chunk, llm)
        if summary:
            chunk_summaries.append(summary)

    if not chunk_summaries:
        return ""

    # Reduce phase: combine summaries.
    final = _reduce_summaries(chunk_summaries, llm)
    return final if final else ""


def build_summary_chunk(
    summary: str,
    source: str,
    file_path: str,
) -> dict[str, Any]:
    """Wrap a document summary as an index chunk dict.

    The resulting chunk can be appended to ``IndexBundle.chunks`` so that
    the summary is embedded and searchable alongside regular chunks.
    """
    return {
        "id": f"{source}::summary",
        "text": summary,
        "source": source,
        "chunk_idx": -1,
        "file_path": file_path,
        "source_path": file_path,
        "title": source,
        "label": f"{source} (summary)",
        "section_hint": "Document Summary",
        "header_path": "Summary",
        "breadcrumb": f"{source} > Summary",
        "locator": "summary",
        "anchor": "summary",
        "excerpt": summary[:320],
        "type": "summary",
        "char_span": [0, 0],
        "metadata": {
            "source_path": file_path,
            "char_span": [0, 0],
            "header_path": "Summary",
            "content_type": "summary",
        },
    }


__all__ = [
    "build_summary_chunk",
    "generate_document_summary",
]
