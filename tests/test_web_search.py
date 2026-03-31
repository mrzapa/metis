# tests/test_web_search.py
from __future__ import annotations
from unittest.mock import MagicMock
from metis_app.utils.web_search import create_web_search, WebSearchResult

def test_create_web_search_returns_callable_without_api_key():
    search = create_web_search({})
    assert callable(search)

def test_web_search_result_dataclass():
    r = WebSearchResult(title="T", url="http://x.com", snippet="S", content="C")
    assert r.title == "T"
    assert r.url == "http://x.com"

def test_duckduckgo_fallback_called_when_no_tavily_key(monkeypatch):
    mock_ddg = MagicMock(return_value=[
        WebSearchResult(title="T", url="u", snippet="s", content="c")
    ])
    monkeypatch.setattr("metis_app.utils.web_search._ddg_search", mock_ddg)
    search = create_web_search({})
    results = search("test query", n_results=3)
    mock_ddg.assert_called_once_with("test query", n_results=3)
    assert len(results) == 1

def test_tavily_search_called_when_api_key_present(monkeypatch):
    mock_tavily = MagicMock(return_value=[
        WebSearchResult(title="T", url="u", snippet="s", content="c")
    ])
    monkeypatch.setattr("metis_app.utils.web_search._tavily_search", mock_tavily)
    search = create_web_search({"web_search_api_key": "test-key-abc"})
    results = search("test query", n_results=5)
    mock_tavily.assert_called_once_with("test query", n_results=5, api_key="test-key-abc")
    assert len(results) == 1


def test_tavily_search_falls_back_to_ddg_on_client_error(monkeypatch):
    """_tavily_search should fall back to DDG if the Tavily client raises."""
    from metis_app.utils.web_search import _tavily_search, WebSearchResult
    mock_ddg = MagicMock(return_value=[
        WebSearchResult(title="DDG", url="u", snippet="s", content="c")
    ])
    monkeypatch.setattr("metis_app.utils.web_search._ddg_search", mock_ddg)

    class FakeClient:
        def __init__(self, api_key): pass
        def search(self, *a, **kw): raise RuntimeError("rate limit")

    # Temporarily replace TavilyClient inside the module
    import sys
    fake_tavily_mod = type(sys)("tavily")
    fake_tavily_mod.TavilyClient = FakeClient
    monkeypatch.setitem(sys.modules, "tavily", fake_tavily_mod)

    results = _tavily_search("test query", n_results=3, api_key="key123")
    mock_ddg.assert_called_once_with("test query", n_results=3)
    assert results[0].title == "DDG"
