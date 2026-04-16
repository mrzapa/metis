"""Web Graph Service — builds a wikilinked knowledge-graph index from web sources."""

from __future__ import annotations

import json
import logging
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

from metis_app.utils.llm_providers import create_llm
from metis_app.utils.web_search import WebSearchResult, create_page_fetcher, create_web_search

_log = logging.getLogger(__name__)

_GRAPH_PROMPT = """\
You are a knowledge-graph architect. Given a topic and a list of web sources, produce a
structured knowledge graph as valid JSON (no markdown fences, no extra text).

Schema:
{{
  "moc": {{
    "title": "Map of Content: <topic>",
    "content": "# Map of Content: <topic>\\n\\n<intro paragraph>\\n\\n## Concepts\\n<wikilinked list>\\n\\n## Patterns\\n<wikilinked list>\\n\\n## Gotchas\\n<wikilinked list>"
  }},
  "concepts": [
    {{"title": "<Concept Name>", "content": "# <Concept Name>\\n\\n<2-3 sentences with [[wikilinks]] to related nodes>"}}
  ],
  "patterns": [
    {{"title": "<Pattern Name>", "content": "# <Pattern Name>\\n\\n<2-3 sentences describing when/how to use it, with [[wikilinks]]>"}}
  ],
  "gotchas": [
    {{"title": "<Gotcha Name>", "content": "# <Gotcha Name>\\n\\n<2-3 sentences on what goes wrong and how to avoid it, with [[wikilinks]]>"}}
  ]
}}

Rules:
- Include 3-5 concepts, 2-3 patterns, 2-3 gotchas.
- Every concept/pattern/gotcha node MUST have at least one [[wikilink]] to another node by exact title.
- The MOC links to all concept/pattern/gotcha nodes.
- Derive content only from the provided sources. Do not hallucinate.
- Output raw JSON only — no code fences, no commentary.

Topic: {topic}

Sources:
{sources}
"""


def _slugify(title: str) -> str:
    """Convert a title to a safe filename slug."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")[:60]


class WebGraphService:
    """On-demand pipeline: topic → search → scrape → LLM → multi-node markdown folder → index."""

    def __init__(
        self,
        web_search: Any,
        page_fetcher: Any,
        temp_dir: str | None = None,
    ) -> None:
        self._web_search = web_search
        self._page_fetcher = page_fetcher
        self._temp_dir = temp_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        topic: str,
        settings: dict[str, Any],
        orchestrator: Any,
        index_id: str | None = None,
    ) -> dict[str, Any]:
        """Run the full pipeline and return a result dict."""
        _log.info("WebGraphService.build: topic=%r", topic)

        results = self._search_and_scrape(topic)
        if not results:
            raise ValueError(f"No web results found for topic: {topic!r}")

        llm = create_llm(settings)
        graph_nodes = self._generate_graph(topic, results, llm)

        work_dir, doc_paths = self._write_temp_folder(graph_nodes)

        used_index_id = index_id or f"webgraph_{uuid.uuid4().hex[:8]}"
        engine_result = orchestrator.build_index(
            [str(p) for p in doc_paths],
            settings,
            index_id=used_index_id,
        )

        nodes_meta = [
            {
                "filename": p.name,
                "node_type": self._node_type(p.name),
                "title": p.stem.replace("_", " ").title(),
            }
            for p in doc_paths
        ]

        return {
            "index_id": engine_result.index_id,
            "manifest_path": str(engine_result.manifest_path),
            "topic": topic,
            "nodes": nodes_meta,
            "sources": [r.url for r in results],
            "document_count": engine_result.document_count,
            "chunk_count": engine_result.chunk_count,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _search_and_scrape(self, topic: str, n_results: int = 5) -> list[WebSearchResult]:
        """Search for topic and enrich results with full page content."""
        results: list[WebSearchResult] = self._web_search(topic, n_results=n_results)
        enriched: list[WebSearchResult] = []
        for r in results:
            full_text = self._page_fetcher(r.url)
            enriched.append(
                WebSearchResult(
                    title=r.title,
                    url=r.url,
                    snippet=r.snippet,
                    content=full_text if full_text else r.snippet,
                )
            )
        return enriched

    def _generate_graph(
        self,
        topic: str,
        results: list[WebSearchResult],
        llm: Any,
    ) -> dict[str, Any]:
        """Call LLM to produce structured knowledge-graph JSON."""
        sources_text = "\n\n".join(
            f"[{i + 1}] {r.title} ({r.url})\n{r.content[:800]}"
            for i, r in enumerate(results)
        )
        prompt = _GRAPH_PROMPT.format(topic=topic, sources=sources_text)
        from langchain_core.messages import HumanMessage

        response = llm.invoke([HumanMessage(content=prompt)])
        raw = response.content.strip()

        # Strip accidental markdown fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            _log.warning("LLM returned invalid JSON for graph; exc=%s\nraw=%r", exc, raw[:200])
            raise ValueError("LLM did not return valid JSON for the knowledge graph.") from exc

    def _write_temp_folder(
        self,
        graph_nodes: dict[str, Any],
    ) -> tuple[Path, list[Path]]:
        """Write each graph node to a .md file in a temp directory."""
        work_dir = Path(self._temp_dir or tempfile.mkdtemp(prefix="metis_webgraph_"))
        work_dir.mkdir(parents=True, exist_ok=True)

        paths: list[Path] = []

        # MOC node
        moc = graph_nodes.get("moc", {})
        if moc:
            title_slug = _slugify(moc.get("title", "moc"))
            p = work_dir / f"moc_{title_slug}.md"
            p.write_text(moc.get("content", ""), encoding="utf-8")
            paths.append(p)

        # Typed nodes
        for node_type in ("concepts", "patterns", "gotchas"):
            for node in graph_nodes.get(node_type, []):
                title = node.get("title", "untitled")
                slug = _slugify(title)
                prefix = node_type.rstrip("s")  # concept / pattern / gotcha
                p = work_dir / f"{prefix}_{slug}.md"
                p.write_text(node.get("content", ""), encoding="utf-8")
                paths.append(p)

        return work_dir, paths

    @staticmethod
    def _node_type(filename: str) -> str:
        """Derive node_type from filename prefix."""
        for prefix in ("moc", "concept", "pattern", "gotcha"):
            if filename.startswith(prefix):
                return prefix
        return "unknown"


def create_web_graph_service(settings: dict[str, Any]) -> WebGraphService:
    """Factory — mirrors the pattern of ``create_web_search``."""
    web_search = create_web_search(settings)
    page_fetcher = create_page_fetcher(settings)
    return WebGraphService(web_search=web_search, page_fetcher=page_fetcher)
