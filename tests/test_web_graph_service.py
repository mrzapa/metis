"""Tests for WebGraphService."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("langchain_core")

from metis_app.services.web_graph_service import WebGraphService, create_web_graph_service
from metis_app.utils.web_search import WebSearchResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE_GRAPH = {
    "moc": {
        "title": "Map of Content: Attention Mechanism",
        "content": "# Map of Content: Attention Mechanism\n\nCore concept.\n\n## Concepts\n- [[Query Key Value]]\n\n## Patterns\n- [[Scaled Dot Product]]\n\n## Gotchas\n- [[Quadratic Complexity]]",
    },
    "concepts": [
        {
            "title": "Query Key Value",
            "content": "# Query Key Value\n\nThe three vectors used in [[Scaled Dot Product]] attention.",
        }
    ],
    "patterns": [
        {
            "title": "Scaled Dot Product",
            "content": "# Scaled Dot Product\n\nDivide by sqrt(d_k) to prevent vanishing gradients. See also [[Query Key Value]].",
        }
    ],
    "gotchas": [
        {
            "title": "Quadratic Complexity",
            "content": "# Quadratic Complexity\n\nAttention is O(n^2) in sequence length. Watch for [[Query Key Value]] memory growth.",
        }
    ],
}

_SAMPLE_RESULTS = [
    WebSearchResult(
        title="Attention Is All You Need",
        url="https://example.com/attention",
        snippet="Transformer architecture paper.",
        content="Full content about attention mechanisms.",
    ),
    WebSearchResult(
        title="Illustrated Transformer",
        url="https://example.com/illustrated",
        snippet="Visual explanation of transformers.",
        content="Content about query, key, value vectors.",
    ),
]


def _make_service(tmp_path: Path) -> tuple[WebGraphService, MagicMock, MagicMock]:
    mock_web_search = MagicMock(return_value=_SAMPLE_RESULTS)
    mock_page_fetcher = MagicMock(return_value="Fetched page content about the topic.")
    service = WebGraphService(
        web_search=mock_web_search,
        page_fetcher=mock_page_fetcher,
        temp_dir=str(tmp_path),
    )
    return service, mock_web_search, mock_page_fetcher


# ---------------------------------------------------------------------------
# Tests: _write_temp_folder
# ---------------------------------------------------------------------------


def test_write_temp_folder_creates_md_files(tmp_path: Path) -> None:
    service, _, _ = _make_service(tmp_path)
    work_dir, paths = service._write_temp_folder(_SAMPLE_GRAPH)
    assert len(paths) == 4  # 1 moc + 1 concept + 1 pattern + 1 gotcha
    for p in paths:
        assert p.suffix == ".md"
        assert p.exists()
        assert len(p.read_text(encoding="utf-8")) > 0


def test_write_temp_folder_moc_prefix(tmp_path: Path) -> None:
    service, _, _ = _make_service(tmp_path)
    _, paths = service._write_temp_folder(_SAMPLE_GRAPH)
    moc_files = [p for p in paths if p.name.startswith("moc_")]
    assert len(moc_files) == 1


def test_wikilinks_appear_in_nodes(tmp_path: Path) -> None:
    service, _, _ = _make_service(tmp_path)
    _, paths = service._write_temp_folder(_SAMPLE_GRAPH)
    all_content = " ".join(p.read_text(encoding="utf-8") for p in paths)
    assert "[[" in all_content, "Wikilinks must appear in at least one node"


# ---------------------------------------------------------------------------
# Tests: _generate_graph
# ---------------------------------------------------------------------------


def test_generate_graph_parses_json(tmp_path: Path) -> None:
    service, _, _ = _make_service(tmp_path)
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content=json.dumps(_SAMPLE_GRAPH))
    result = service._generate_graph("Attention Mechanism", _SAMPLE_RESULTS, mock_llm)
    assert "moc" in result
    assert "concepts" in result
    assert isinstance(result["concepts"], list)


def test_generate_graph_strips_markdown_fences(tmp_path: Path) -> None:
    service, _, _ = _make_service(tmp_path)
    mock_llm = MagicMock()
    fenced = f"```json\n{json.dumps(_SAMPLE_GRAPH)}\n```"
    mock_llm.invoke.return_value = MagicMock(content=fenced)
    result = service._generate_graph("Attention Mechanism", _SAMPLE_RESULTS, mock_llm)
    assert "moc" in result


def test_generate_graph_raises_on_invalid_json(tmp_path: Path) -> None:
    service, _, _ = _make_service(tmp_path)
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="not json at all")
    with pytest.raises(ValueError, match="valid JSON"):
        service._generate_graph("Attention Mechanism", _SAMPLE_RESULTS, mock_llm)


# ---------------------------------------------------------------------------
# Tests: _search_and_scrape
# ---------------------------------------------------------------------------


def test_search_and_scrape_enriches_content(tmp_path: Path) -> None:
    service, mock_search, mock_fetcher = _make_service(tmp_path)
    results = service._search_and_scrape("Attention Mechanism", n_results=2)
    assert mock_search.called
    assert mock_fetcher.call_count == len(_SAMPLE_RESULTS)
    for r in results:
        assert r.content  # must have content after enrichment


def test_search_and_scrape_falls_back_to_snippet_on_empty_fetch(tmp_path: Path) -> None:
    mock_web_search = MagicMock(return_value=_SAMPLE_RESULTS[:1])
    mock_page_fetcher = MagicMock(return_value="")  # empty fetch
    service = WebGraphService(web_search=mock_web_search, page_fetcher=mock_page_fetcher, temp_dir=str(tmp_path))
    results = service._search_and_scrape("topic")
    assert results[0].content == _SAMPLE_RESULTS[0].snippet


# ---------------------------------------------------------------------------
# Tests: _node_type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("moc_attention.md", "moc"),
        ("concept_query_key_value.md", "concept"),
        ("pattern_scaled_dot.md", "pattern"),
        ("gotcha_quadratic.md", "gotcha"),
        ("unknown_file.md", "unknown"),
    ],
)
def test_node_type(filename: str, expected: str) -> None:
    assert WebGraphService._node_type(filename) == expected


# ---------------------------------------------------------------------------
# Tests: build (integration with mocked LLM + orchestrator)
# ---------------------------------------------------------------------------


def test_build_returns_expected_keys(tmp_path: Path) -> None:
    service, _, _ = _make_service(tmp_path)

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content=json.dumps(_SAMPLE_GRAPH))

    mock_orchestrator = MagicMock()
    mock_orchestrator.build_index.return_value = MagicMock(
        index_id="webgraph_abc123",
        manifest_path="/tmp/manifest.json",
        document_count=4,
        chunk_count=12,
    )

    with patch("metis_app.services.web_graph_service.create_llm", return_value=mock_llm):
        result = service.build(
            topic="Attention Mechanism",
            settings={"llm_provider": "openai"},
            orchestrator=mock_orchestrator,
            index_id="webgraph_abc123",
        )

    assert result["index_id"] == "webgraph_abc123"
    assert result["topic"] == "Attention Mechanism"
    assert isinstance(result["nodes"], list)
    assert len(result["nodes"]) == 4
    assert len(result["sources"]) == 2
    assert result["document_count"] == 4


def test_build_raises_on_no_results(tmp_path: Path) -> None:
    mock_web_search = MagicMock(return_value=[])
    mock_page_fetcher = MagicMock(return_value="")
    service = WebGraphService(web_search=mock_web_search, page_fetcher=mock_page_fetcher, temp_dir=str(tmp_path))

    mock_orchestrator = MagicMock()
    with pytest.raises(ValueError, match="No web results"):
        service.build("empty topic", {}, mock_orchestrator)


def test_build_calls_orchestrator_with_md_paths(tmp_path: Path) -> None:
    service, _, _ = _make_service(tmp_path)
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content=json.dumps(_SAMPLE_GRAPH))
    mock_orchestrator = MagicMock()
    mock_orchestrator.build_index.return_value = MagicMock(
        index_id="x", manifest_path="/tmp/m.json", document_count=4, chunk_count=8
    )
    with patch("metis_app.services.web_graph_service.create_llm", return_value=mock_llm):
        service.build("topic", {}, mock_orchestrator)

    call_args = mock_orchestrator.build_index.call_args
    paths_arg = call_args[0][0]  # first positional arg = list of paths
    assert all(p.endswith(".md") for p in paths_arg)


# ---------------------------------------------------------------------------
# Tests: create_web_graph_service factory
# ---------------------------------------------------------------------------


def test_create_web_graph_service_returns_instance() -> None:
    with (
        patch("metis_app.services.web_graph_service.create_web_search", return_value=MagicMock()),
        patch("metis_app.services.web_graph_service.create_page_fetcher", return_value=MagicMock()),
    ):
        service = create_web_graph_service({"llm_provider": "openai"})
    assert isinstance(service, WebGraphService)
