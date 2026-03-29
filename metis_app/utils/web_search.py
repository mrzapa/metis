"""Web search utility for autonomous research (adapted from 724-office tool patterns)."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    content: str


def create_web_search(settings: dict[str, Any]) -> Callable[[str], list[WebSearchResult]]:
    """Return a search callable configured from settings.

    Uses Tavily when web_search_api_key is set; falls back to DuckDuckGo HTML scrape.
    """
    api_key = str(settings.get("web_search_api_key") or "").strip()

    def search(query: str, n_results: int = 5) -> list[WebSearchResult]:
        if api_key:
            return _tavily_search(query, n_results=n_results, api_key=api_key)
        return _ddg_search(query, n_results=n_results)

    return search


def _tavily_search(query: str, *, n_results: int, api_key: str) -> list[WebSearchResult]:
    """Call Tavily search API. Falls back to DuckDuckGo if tavily-python not installed or on error."""
    try:
        from tavily import TavilyClient  # type: ignore[import-untyped]
    except ImportError as exc:
        _log.warning("tavily-python not installed; falling back to DuckDuckGo: %s", exc)
        return _ddg_search(query, n_results=n_results)

    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(query, max_results=n_results, include_raw_content=False)
        results = []
        for item in response.get("results", []):
            full_content = str(item.get("content") or "")
            results.append(
                WebSearchResult(
                    title=str(item.get("title") or ""),
                    url=str(item.get("url") or ""),
                    snippet=full_content[:500],
                    content=full_content,
                )
            )
        return results
    except Exception as exc:
        _log.warning("Tavily search failed; falling back to DuckDuckGo: %s", exc)
        return _ddg_search(query, n_results=n_results)


def _ddg_search(query: str, *, n_results: int = 5) -> list[WebSearchResult]:
    """DuckDuckGo Instant Answer API fallback (no key required, limited results)."""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MetisAI/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        _log.warning("DuckDuckGo search failed: %s", exc)
        return []

    results: list[WebSearchResult] = []
    abstract = data.get("AbstractText", "")
    abstract_url = data.get("AbstractURL", "")
    abstract_added = False
    if abstract and abstract_url:
        results.append(
            WebSearchResult(
                title=data.get("Heading", query),
                url=abstract_url,
                snippet=abstract[:500],
                content=abstract,
            )
        )
        abstract_added = True
    for item in data.get("RelatedTopics", []):
        if len(results) >= n_results:
            break
        if isinstance(item, dict) and item.get("Text") and item.get("FirstURL"):
            results.append(
                WebSearchResult(
                    title=item.get("Text", "")[:80],
                    url=item.get("FirstURL", ""),
                    snippet=item.get("Text", "")[:500],
                    content=item.get("Text", ""),
                )
            )
    return results
