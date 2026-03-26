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
