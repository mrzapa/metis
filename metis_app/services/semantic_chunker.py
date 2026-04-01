"""Semantic-aware text chunking strategies.

Inspired by ApeRAG's hierarchical chunking approach, this module provides
chunking strategies that respect document structure (headings, paragraphs,
sentences) instead of blindly splitting on character boundaries.

Three strategies are available:

  - ``"fixed"``    – Original character-based sliding window (default).
  - ``"sentence"`` – Splits on sentence/paragraph boundaries while
                     respecting a token budget.
  - ``"markdown"`` – Splits on markdown heading boundaries, then falls
                     back to sentence splitting for oversized sections.

The public entry point is :func:`chunk_text_semantic` which dispatches to the
correct strategy based on the ``chunk_strategy`` setting.
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Sentence / paragraph boundary helpers
# ---------------------------------------------------------------------------

# Ordered from least to most disruptive split point.
_SPLIT_SEPARATORS: list[list[str]] = [
    ["\n\n"],                          # paragraph break
    ["\n"],                            # line break
    [".", "!", "?", "。", "！", "？"],  # sentence-ending punctuation
    [";", "；", ",", "，"],            # clause boundary
    [" ", "\t"],                       # word boundary (last resort)
]


def _split_at_separators(text: str, separators: list[str]) -> list[str]:
    """Split *text* at any of the given *separators*, keeping the separator
    attached to the preceding fragment."""
    parts: list[str] = [text]
    for sep in separators:
        new_parts: list[str] = []
        for part in parts:
            pieces = part.split(sep)
            for i, piece in enumerate(pieces[:-1]):
                new_parts.append(piece + sep)
            new_parts.append(pieces[-1])
        parts = new_parts
    return [p for p in parts if p]


def _merge_small_fragments(
    fragments: list[str],
    max_len: int,
) -> list[str]:
    """Greedily merge consecutive *fragments* while the combined length stays
    within *max_len* characters."""
    merged: list[str] = []
    current = ""
    for frag in fragments:
        if not current:
            current = frag
        elif len(current) + len(frag) <= max_len:
            current += frag
        else:
            merged.append(current)
            current = frag
    if current:
        merged.append(current)
    return merged


# ---------------------------------------------------------------------------
# Core recursive sentence splitter
# ---------------------------------------------------------------------------

def _recursive_split(
    text: str,
    chunk_size: int,
    overlap: int,
    level: int = 0,
) -> list[str]:
    """Recursively split *text* into chunks of at most *chunk_size* characters
    by trying progressively finer separators.

    At each level the text is first split at the separators for that level,
    oversized fragments are recursively split at the next level, and small
    adjacent fragments are merged back together.
    """
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    if level >= len(_SPLIT_SEPARATORS):
        # No more separator levels — hard-split at midpoint.
        mid = len(text) // 2
        left = _recursive_split(text[:mid], chunk_size, overlap, level + 1)
        right = _recursive_split(text[mid:], chunk_size, overlap, level + 1)
        return left + right

    # Split text at the current separator level.
    fragments = _split_at_separators(text, _SPLIT_SEPARATORS[level])

    # Recursively split any oversized fragments.
    refined: list[str] = []
    for frag in fragments:
        if len(frag) > chunk_size:
            refined.extend(
                _recursive_split(frag, chunk_size, overlap, level + 1)
            )
        else:
            refined.append(frag)

    # Merge small fragments back together.
    return _merge_small_fragments(refined, chunk_size)


# ---------------------------------------------------------------------------
# Markdown heading-aware splitter
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)", re.MULTILINE)


def _split_by_headings(text: str) -> list[dict[str, Any]]:
    """Split *text* on markdown headings and return a list of sections.

    Each section is a dict with keys:
      - ``level``: heading level (1-6) or 0 for preamble.
      - ``title``: heading text (empty for preamble).
      - ``body``:  section body including the heading line itself.
    """
    sections: list[dict[str, Any]] = []
    last_end = 0

    for m in _HEADING_RE.finditer(text):
        # Capture any text before this heading as body of the previous section.
        if m.start() > last_end:
            preamble = text[last_end:m.start()].strip()
            if preamble:
                if sections:
                    sections[-1]["body"] += "\n\n" + preamble
                else:
                    sections.append({"level": 0, "title": "", "body": preamble})

        level = len(m.group(1))
        title = m.group(2).strip()
        sections.append({"level": level, "title": title, "body": m.group(0)})
        last_end = m.end()

    # Trailing text after the last heading.
    trailing = text[last_end:].strip()
    if trailing:
        if sections:
            sections[-1]["body"] += "\n\n" + trailing
        else:
            sections.append({"level": 0, "title": "", "body": trailing})

    return sections if sections else [{"level": 0, "title": "", "body": text}]


def _chunk_markdown(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """Chunk *text* by first splitting on markdown headings and then applying
    sentence-level splitting to any sections that exceed *chunk_size*."""
    sections = _split_by_headings(text)
    chunks: list[str] = []
    for section in sections:
        body = section["body"]
        if len(body) <= chunk_size:
            chunks.append(body)
        else:
            # Over-sized section — split semantically.
            chunks.extend(_recursive_split(body, chunk_size, overlap))
    return chunks


# ---------------------------------------------------------------------------
# Strategy dispatcher
# ---------------------------------------------------------------------------

def chunk_text_semantic(
    text: str,
    chunk_size: int,
    overlap: int,
    strategy: str = "fixed",
) -> list[str]:
    """Chunk *text* using the requested *strategy*.

    Parameters
    ----------
    text:
        Raw document text.
    chunk_size:
        Maximum chunk length in characters.
    overlap:
        Character overlap between chunks (used only for ``"fixed"``
        strategy and as a guideline for others).
    strategy:
        One of ``"fixed"``, ``"sentence"``, or ``"markdown"``.

    Returns
    -------
    list[str]
        Non-empty chunks.
    """
    strategy = (strategy or "fixed").strip().lower()

    if strategy == "sentence":
        return _recursive_split(text, chunk_size, overlap)
    if strategy == "markdown":
        return _chunk_markdown(text, chunk_size, overlap)

    # Default: character-based sliding window (original METIS behaviour).
    from metis_app.services.index_service import chunk_text
    return chunk_text(text, chunk_size, overlap)


_META_MARKER_SYSTEM = (
    "You are a marker extraction expert. The document has [Paragraph N] tags "
    "every 128 tokens. Extract meta-markers as JSON:\n"
    '{{"marker": [{{"k": "question that retrieves this", '
    '"v": "focused info block 100-200 words", '
    '"paragraph_indices": [0, 1]}}]}}\n'
    "Rules:\n"
    "- k is ONE question summarising v, suitable as a retrieval query\n"
    "- v is a self-contained focused paragraph, 100-200 words, on ONE specific topic\n"
    "- Each marker covers 1-3 paragraphs MAX\n"
    "- Generate at least {expected_count} markers (doc_tokens / 128), more is better\n"
    "- Every paragraph must appear in at least one marker\n"
    "- Replace pronouns with explicit names where ambiguous\n"
    "- Return ONLY valid JSON"
)

_META_MARKER_SEGMENT = 128


def _insert_paragraph_tags(text: str) -> tuple[str, int]:
    words = text.split()
    tagged_parts: list[str] = []
    para_idx = 0
    for i in range(0, len(words), _META_MARKER_SEGMENT):
        segment = words[i : i + _META_MARKER_SEGMENT]
        tagged_parts.append(f"[Paragraph {para_idx}]\n" + " ".join(segment))
        para_idx += 1
    return "\n\n".join(tagged_parts), para_idx


def _parse_marker_json(raw: str) -> list[dict]:
    import json as _json
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end <= start:
        return []
    try:
        payload = _json.loads(raw[start:end])
    except Exception:
        return []
    return list(payload.get("marker") or [])


def chunk_text_meta_marker(
    text: str,
    settings: dict,
    *,
    max_retries: int = 3,
) -> list[dict]:
    from metis_app.utils.llm_providers import create_llm

    tagged_text, n_paragraphs = _insert_paragraph_tags(text)
    if n_paragraphs == 0:
        return []

    doc_tokens = len(text.split())
    expected_count = max(1, doc_tokens // _META_MARKER_SEGMENT)

    llm = create_llm(settings)
    markers: list[dict] = []
    covered: set[int] = set()

    for _attempt in range(max_retries):
        system_prompt = _META_MARKER_SYSTEM.format(expected_count=expected_count)
        try:
            response = llm.invoke([
                {"type": "system", "content": system_prompt},
                {"type": "human", "content": tagged_text},
            ])
            raw = str(getattr(response, "content", response) or "")
        except Exception:
            raw = ""
        attempt_markers = _parse_marker_json(raw)
        if not attempt_markers:
            continue

        attempt_covered: set[int] = set()
        valid_attempt: list[dict] = []
        for m in attempt_markers:
            k = str(m.get("k") or "").strip()
            v = str(m.get("v") or "").strip()
            indices = [int(i) for i in (m.get("paragraph_indices") or []) if isinstance(i, (int, float))]
            if not k or not v:
                continue
            valid_attempt.append({"marker_key": k, "text": v, "paragraph_indices": indices})
            attempt_covered.update(indices)

        if not markers or len(attempt_covered) > len(covered):
            markers = valid_attempt
            covered = attempt_covered

        if n_paragraphs == 0 or len(covered) / n_paragraphs >= 0.95:
            break

    para_words = text.split()
    for para_idx in range(n_paragraphs):
        if para_idx not in covered:
            start = para_idx * _META_MARKER_SEGMENT
            end = min(start + _META_MARKER_SEGMENT, len(para_words))
            para_text = " ".join(para_words[start:end]).strip()
            if para_text:
                markers.append({
                    "marker_key": para_text,
                    "text": para_text,
                    "paragraph_indices": [para_idx],
                })

    return markers
