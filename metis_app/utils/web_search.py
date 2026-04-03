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
    if abstract and abstract_url:
        results.append(
            WebSearchResult(
                title=data.get("Heading", query),
                url=abstract_url,
                snippet=abstract[:500],
                content=abstract,
            )
        )
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


def fetch_page_content(url: str, max_chars: int = 2000) -> str:
    """Fetch main content from a URL via Jina Reader (r.jina.ai).

    Falls back to an empty string on any error so callers degrade gracefully.
    No external dependencies — uses stdlib urllib only.
    """
    jina_url = f"https://r.jina.ai/{url}"
    try:
        req = urllib.request.Request(
            jina_url,
            headers={"User-Agent": "MetisAI/1.0", "Accept": "text/plain"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return resp.read().decode("utf-8", errors="replace")[:max_chars]
    except Exception as exc:  # noqa: BLE001
        _log.debug("Jina Reader fetch failed for %s: %s", url, exc)
        return ""


def create_page_fetcher(settings: dict) -> callable:  # type: ignore[type-arg]
    """Return a page-content fetcher.

    Respects ``web_scrape_full_content`` setting (future: max_chars).
    Returns a zero-arg-per-call wrapper around :func:`fetch_page_content`.
    """
    max_chars = 2000 if settings.get("web_scrape_full_content") else 1000

    def _fetch(url: str) -> str:
        return fetch_page_content(url, max_chars=max_chars)

    return _fetch
