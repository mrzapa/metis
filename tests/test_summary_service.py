"""Tests for metis_app.services.summary_service."""

from __future__ import annotations

from metis_app.services.summary_service import (
    build_summary_chunk,
    generate_document_summary,
)


class _StubLLM:
    """A deterministic LLM stub for testing summary generation."""

    def invoke(self, messages: list[dict]) -> object:
        user = next(
            (m["content"] for m in messages if m.get("type") == "human"),
            "",
        )
        if "Combine" in user or "section summaries" in user.lower():
            return _Resp("This document covers key topics in AI and ML.")
        if "Summarise" in user or "Summarize" in user or "Summary:" in user:
            return _Resp("A brief summary of the chunk content.")
        return _Resp("Generic LLM response.")


class _Resp:
    def __init__(self, content: str):
        self.content = content


def test_generate_summary_short_document() -> None:
    """A short document should be summarised directly (no map-reduce)."""
    chunks = ["Short document about AI."]
    llm = _StubLLM()
    result = generate_document_summary(chunks, llm)
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_summary_empty_chunks_returns_empty() -> None:
    """No chunks should produce an empty summary."""
    result = generate_document_summary([], _StubLLM())
    assert result == ""


def test_generate_summary_long_document_uses_map_reduce() -> None:
    """A long document should go through the map-reduce pipeline."""
    # Create enough text to trigger map-reduce (> 4000 chars).
    chunks = [f"Chunk {i}: " + "x" * 500 for i in range(10)]
    llm = _StubLLM()
    result = generate_document_summary(chunks, llm)
    assert isinstance(result, str)
    assert len(result) > 0
    # Should contain the reduce-phase output.
    assert "key topics" in result.lower() or "AI" in result


def test_generate_summary_handles_llm_failure() -> None:
    """If the LLM raises an exception, an empty string is returned."""

    class FailLLM:
        def invoke(self, messages):
            raise RuntimeError("LLM unavailable")

    result = generate_document_summary(["Some content."], FailLLM())
    assert result == ""


def test_build_summary_chunk_has_required_keys() -> None:
    """The summary chunk dict should contain all keys expected by IndexBundle."""
    chunk = build_summary_chunk(
        summary="A document about AI.",
        source="notes.txt",
        file_path="/tmp/notes.txt",
    )
    assert chunk["id"] == "notes.txt::summary"
    assert chunk["text"] == "A document about AI."
    assert chunk["type"] == "summary"
    assert chunk["source"] == "notes.txt"
    assert chunk["section_hint"] == "Document Summary"
    assert chunk["metadata"]["content_type"] == "summary"


def test_build_summary_chunk_truncates_excerpt() -> None:
    """Excerpt should be capped at 320 characters."""
    long_summary = "a" * 500
    chunk = build_summary_chunk(long_summary, "doc.txt", "/tmp/doc.txt")
    assert len(chunk["excerpt"]) == 320


def test_max_map_chunks_limits_api_calls() -> None:
    """max_map_chunks should limit the number of chunks passed to the LLM."""
    call_count = 0

    class CountingLLM:
        def invoke(self, messages):
            nonlocal call_count
            call_count += 1
            return _Resp("summary")

    chunks = [f"Chunk {i}: " + "x" * 500 for i in range(50)]
    generate_document_summary(chunks, CountingLLM(), max_map_chunks=5)
    # map phase: at most 5, plus reduce phase: 1.
    assert call_count <= 6
