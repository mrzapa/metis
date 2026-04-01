"""Tests for metis_app.services.semantic_chunker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from metis_app.services.semantic_chunker import (
    _insert_paragraph_tags,
    _parse_marker_json,
    chunk_text_meta_marker,
    chunk_text_semantic,
)


def test_fixed_strategy_matches_original_chunk_text() -> None:
    """The 'fixed' strategy delegates to the original chunk_text."""
    text = "abcdefghijklmnopqrstuvwxyz"
    result = chunk_text_semantic(text, chunk_size=10, overlap=2, strategy="fixed")
    assert len(result) > 0
    # First chunk starts at 0.
    assert result[0] == "abcdefghij"


def test_sentence_strategy_respects_sentence_boundaries() -> None:
    """'sentence' strategy should keep sentences intact when possible."""
    text = (
        "The quick brown fox jumps over the lazy dog. "
        "Pack my box with five dozen liquor jugs. "
        "How vexingly quick daft zebras jump."
    )
    result = chunk_text_semantic(text, chunk_size=80, overlap=0, strategy="sentence")
    assert len(result) >= 1
    # Each chunk should be <= 80 chars.
    for chunk in result:
        assert len(chunk) <= 80, f"Chunk too long ({len(chunk)}): {chunk!r}"
    # Reassembly: all original text should be present.
    reassembled = "".join(result)
    assert "quick brown fox" in reassembled
    assert "liquor jugs" in reassembled


def test_sentence_strategy_handles_short_text() -> None:
    """A text shorter than chunk_size is returned as a single chunk."""
    text = "Hello world."
    result = chunk_text_semantic(text, chunk_size=100, overlap=0, strategy="sentence")
    assert result == ["Hello world."]


def test_sentence_strategy_handles_empty_text() -> None:
    """Empty text returns an empty list."""
    result = chunk_text_semantic("", chunk_size=100, overlap=0, strategy="sentence")
    assert result == []


def test_markdown_strategy_splits_on_headings() -> None:
    """'markdown' strategy should split on heading boundaries."""
    text = (
        "# Introduction\n\n"
        "Some intro text.\n\n"
        "## Details\n\n"
        "More detailed information here.\n\n"
        "## Conclusion\n\n"
        "Final thoughts."
    )
    result = chunk_text_semantic(text, chunk_size=500, overlap=0, strategy="markdown")
    assert len(result) >= 1
    # Verify headings appear in the output.
    full = "\n".join(result)
    assert "Introduction" in full
    assert "Details" in full
    assert "Conclusion" in full


def test_markdown_strategy_splits_oversized_sections() -> None:
    """Sections exceeding chunk_size are further split."""
    body = "A " * 200  # ~400 chars
    text = f"# Big Section\n\n{body}"
    result = chunk_text_semantic(text, chunk_size=100, overlap=0, strategy="markdown")
    assert len(result) > 1
    for chunk in result:
        assert len(chunk) <= 100, f"Chunk too long: {len(chunk)}"


def test_unknown_strategy_defaults_to_fixed() -> None:
    """Unknown strategies fall back to the 'fixed' sliding window."""
    text = "a" * 50
    result_fixed = chunk_text_semantic(text, chunk_size=20, overlap=0, strategy="fixed")
    result_unknown = chunk_text_semantic(text, chunk_size=20, overlap=0, strategy="unknown")
    assert result_fixed == result_unknown


def test_sentence_strategy_preserves_all_content() -> None:
    """Every character of the original should appear in the chunks."""
    text = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth."
    result = chunk_text_semantic(text, chunk_size=40, overlap=0, strategy="sentence")
    reassembled = "".join(result)
    for word in ["First", "Second", "Third", "Fourth", "Fifth"]:
        assert word in reassembled


def test_markdown_strategy_no_headings_returns_all_text() -> None:
    """Text without headings should still be chunked correctly."""
    text = "Just some plain text without any markdown headings at all."
    result = chunk_text_semantic(text, chunk_size=100, overlap=0, strategy="markdown")
    assert len(result) == 1
    assert "plain text" in result[0]


# ---------------------------------------------------------------------------
# _insert_paragraph_tags
# ---------------------------------------------------------------------------


def test_insert_paragraph_tags_empty() -> None:
    tagged, n = _insert_paragraph_tags("")
    assert tagged == ""
    assert n == 0


def test_insert_paragraph_tags_short_text() -> None:
    # 10 words — fewer than 128, so exactly 1 paragraph (index 0)
    text = "one two three four five six seven eight nine ten"
    tagged, n = _insert_paragraph_tags(text)
    assert n == 1
    assert tagged.startswith("[Paragraph 0]")


def test_insert_paragraph_tags_multi_paragraph() -> None:
    # 260 words → 3 paragraphs: 128 + 128 + 4  (indices 0, 1, 2)
    text = " ".join(f"w{i}" for i in range(260))
    tagged, n = _insert_paragraph_tags(text)
    assert n == 3
    assert "[Paragraph 0]" in tagged
    assert "[Paragraph 1]" in tagged
    assert "[Paragraph 2]" in tagged


# ---------------------------------------------------------------------------
# _parse_marker_json
# ---------------------------------------------------------------------------


def test_parse_marker_json_valid() -> None:
    raw = '{"marker": [{"marker_key": "Q?", "text": "A.", "paragraph_indices": [0]}]}'
    result = _parse_marker_json(raw)
    assert len(result) == 1
    assert result[0]["marker_key"] == "Q?"
    assert result[0]["text"] == "A."
    assert result[0]["paragraph_indices"] == [0]


def test_parse_marker_json_with_codefence() -> None:
    raw = (
        "```json\n"
        '{"marker": [{"marker_key": "Q?", "text": "A.", "paragraph_indices": [0]}]}'
        "\n```"
    )
    result = _parse_marker_json(raw)
    assert len(result) == 1


def test_parse_marker_json_no_json() -> None:
    result = _parse_marker_json("This is not JSON at all.")
    assert result == []


def test_parse_marker_json_invalid_json() -> None:
    # No closing brace — end index will equal start index, triggering early return
    result = _parse_marker_json("{broken json")
    assert result == []


# ---------------------------------------------------------------------------
# chunk_text_meta_marker
# ---------------------------------------------------------------------------


def test_chunk_text_meta_marker_empty_text() -> None:
    result = chunk_text_meta_marker("", {})
    assert result == []


def test_chunk_text_meta_marker_with_mock_llm() -> None:
    mock_response = MagicMock()
    mock_response.content = (
        '{"marker": [{"k": "What is this about?", '
        '"v": "A short informative paragraph.", '
        '"paragraph_indices": [0]}]}'
    )
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_response

    with patch("metis_app.utils.llm_providers.create_llm", return_value=mock_llm):
        result = chunk_text_meta_marker("Short test text with some words here.", {})

    assert len(result) > 0
    for chunk in result:
        assert "marker_key" in chunk
        assert "text" in chunk
        assert "paragraph_indices" in chunk
        assert chunk["marker_key"]


def test_chunk_text_meta_marker_fallback_on_llm_failure() -> None:
    mock_response = MagicMock()
    mock_response.content = "not valid json"
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_response

    text = "Short test text with some words to form a single paragraph."
    with patch("metis_app.utils.llm_providers.create_llm", return_value=mock_llm):
        result = chunk_text_meta_marker(text, {})

    assert len(result) > 0
    for chunk in result:
        assert "marker_key" in chunk
        assert "text" in chunk
