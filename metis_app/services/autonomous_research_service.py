"""Autonomous research pipeline for the METIS Companion.

Scans constellation faculties for sparse coverage, conducts web research,
synthesizes a document, and auto-indexes it as a new star.

Design adapted from 724-office's direct-Python autonomous agent patterns.
"""

from __future__ import annotations

import logging
import pathlib
import tempfile
import uuid
from typing import Any, Callable

# Typed shape emitted by the progress_cb at each pipeline phase.
# {"phase": str, "faculty_id": str | None, "detail": str}
ProgressEvent = dict[str, Any]

_log = logging.getLogger(__name__)

# The 11 constellation faculties in preferred gap-fill order
FACULTY_ORDER = [
    "perception", "knowledge", "memory", "reasoning", "skills",
    "strategy", "personality", "values", "synthesis", "autonomy", "emergence",
]

FACULTY_DESCRIPTIONS = {
    "perception":  "Sensory intake, pattern detection, and direct observation",
    "knowledge":   "Structured facts, concepts, and durable associations",
    "memory":      "Retention, recall, and context continuity",
    "reasoning":   "Inference, logic, and evidence-driven judgment",
    "skills":      "Procedural capability, practiced technique, and execution fluency",
    "strategy":    "Planning, tradeoffs, and directional choice",
    "personality": "Style, temperament, and expressive posture",
    "values":      "Principles, priorities, and constraints",
    "synthesis":   "Cross-domain integration and meaning-making",
    "autonomy":    "Independent intent, self-direction, and self-governance",
    "emergence":   "Novel capability, adaptation, and new structure from existing parts",
}

# Minimum auto-generated indexes (stars) per faculty before it's no longer considered sparse
_MIN_STARS_PER_FACULTY = 3


class AutonomousResearchService:
    """Run one autonomous research cycle: scan → query → search → synthesize → index."""

    def __init__(
        self,
        *,
        web_search: Callable,
        temp_dir: pathlib.Path | None = None,
    ) -> None:
        self._web_search = web_search
        self._temp_dir = temp_dir or pathlib.Path(tempfile.gettempdir()) / "metis_auto_research"
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        *,
        settings: dict[str, Any],
        indexes: list[dict[str, Any]],
        orchestrator: Any,
        progress_cb: Callable[[ProgressEvent], None] | None = None,
        target_faculty_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Full pipeline. Returns result dict or None if nothing to research.

        progress_cb receives a dict at each phase:
        {"phase": str, "faculty_id": str | None, "detail": str}
        """
        from metis_app.utils.llm_providers import create_llm

        def _emit(phase: str, faculty: str | None, detail: str) -> None:
            if progress_cb is not None:
                try:
                    progress_cb({"phase": phase, "faculty_id": faculty, "detail": detail})
                except Exception:  # noqa: BLE001
                    pass

        if target_faculty_id is not None:
            faculty_id = target_faculty_id
            _emit("targeted", faculty_id, f"Targeting faculty '{faculty_id}' directly…")
        else:
            _emit("scanning", None, "Scanning constellation for faculty gaps…")
            demand_scores = self.compute_demand_scores(indexes) or None  # {} → None so scan uses FACULTY_ORDER fallback
            faculty_id = self.scan_faculty_gaps(indexes, demand_scores=demand_scores)
            if faculty_id is None:
                _log.debug("autonomous_research: no faculty gaps found, skipping")
                _emit("skipped", None, "Constellation fully covered, skipping")
                return None

        faculty_desc = FACULTY_DESCRIPTIONS.get(faculty_id, faculty_id)

        _emit("formulating", faculty_id, f"Formulating research query for '{faculty_id}'…")
        try:
            llm = create_llm(settings)
            query = self.formulate_query(faculty_id, faculty_desc, llm)
        except Exception as exc:
            _log.warning("autonomous_research: LLM query formulation failed: %s", exc)
            return None

        if not query:
            _log.warning("autonomous_research: empty query for faculty %s, skipping", faculty_id)
            return None

        _log.info("autonomous_research: researching %s with query: %s", faculty_id, query)
        _emit("searching", faculty_id, f"Searching: {query}")
        search_results = self._web_search(query, n_results=5)
        if not search_results:
            _log.warning("autonomous_research: no search results for %s", faculty_id)
            return None

        _emit("synthesizing", faculty_id, f"Synthesising {len(search_results)} sources…")
        try:
            document_content = self.synthesize_document(faculty_id, query, search_results, llm)
        except Exception as exc:
            _log.warning("autonomous_research: synthesis failed: %s", exc)
            return None

        try:
            doc_path = self.save_temp_document(document_content, faculty_id)
        except OSError as exc:
            _log.error("autonomous_research: failed to write temp document: %s", exc)
            return None

        index_id = f"auto_{faculty_id}_{uuid.uuid4().hex[:8]}"
        _emit("indexing", faculty_id, f"Building star index: {index_id}")
        try:
            orchestrator.build_index([str(doc_path)], settings, index_id=index_id)
        except Exception as exc:
            _log.error("autonomous_research: index build failed: %s", exc)
            return None
        finally:
            # Clean up temp file whether build succeeded or failed
            try:
                doc_path.unlink(missing_ok=True)
            except OSError:
                pass

        sources = [r.url for r in search_results if r.url]
        title = self._extract_title(document_content)
        _emit("complete", faculty_id, f"New star added: {title}")
        return {
            "faculty_id": faculty_id,
            "index_id": index_id,
            "title": title,
            "sources": sources,
        }

    def scan_faculty_gaps(
        self,
        indexes: list[dict[str, Any]],
        demand_scores: dict[str, int] | None = None,
    ) -> str | None:
        """Return the faculty_id with the fewest auto-generated stars, or None if all covered.

        Priority:
        1. If any faculty has auto-stars but below the minimum threshold, return the sparsest.
        2. If no faculty has any auto-stars at all, return the first unrepresented faculty
           in FACULTY_ORDER.
        3. If all faculties meet the threshold, return None.

        When demand_scores is provided, higher-demand faculties are prioritised (reverse-curriculum).
        """
        faculty_counts: dict[str, int] = {fac: 0 for fac in FACULTY_ORDER}
        for idx in indexes:
            index_id = str(idx.get("index_id") or "")
            if not index_id.startswith("auto_"):
                continue
            parts = index_id.split("_")
            if len(parts) >= 2:
                faculty = parts[1]
                if faculty in faculty_counts:
                    faculty_counts[faculty] += 1  # count indexes (stars), not documents

        # Faculties that have at least one auto-star but are below the threshold
        sparse_represented = [
            (fac, count)
            for fac, count in faculty_counts.items()
            if 0 < count < _MIN_STARS_PER_FACULTY
        ]
        if sparse_represented:
            if demand_scores:
                # hardness = demand_score / count; higher hardness → research first
                return min(
                    sparse_represented,
                    key=lambda x: (
                        -(demand_scores.get(x[0], 0) / max(x[1], 1)),
                        FACULTY_ORDER.index(x[0]),
                    ),
                )[0]
            return min(sparse_represented, key=lambda x: (x[1], FACULTY_ORDER.index(x[0])))[0]

        # No partially-covered faculties — fall back to first unrepresented faculty
        # sorted by hardness (demand / max(count, 1)) descending when demand_scores provided.
        unrepresented = [fac for fac in FACULTY_ORDER if faculty_counts[fac] == 0]
        if unrepresented and demand_scores:
            unrepresented.sort(
                key=lambda f: (-(demand_scores.get(f, 0)), FACULTY_ORDER.index(f))
            )
        if unrepresented:
            return unrepresented[0]

        # All faculties are at or above the threshold
        return None

    def compute_demand_scores(self, indexes: list[dict[str, Any]]) -> dict[str, int]:
        """Count non-auto user indexes per faculty as a demand signal.

        Each user-uploaded index whose brain_pass.placement.faculty_id names a
        constellation faculty adds 1 demand point. Auto-generated indexes
        (index_id starts with 'auto_') are excluded — they represent supply,
        not demand.
        """
        scores: dict[str, int] = {}
        for idx in indexes:
            index_id = str(idx.get("index_id") or "")
            if index_id.startswith("auto_"):
                continue
            brain_pass = idx.get("brain_pass") or {}
            if not isinstance(brain_pass, dict):
                continue
            placement = brain_pass.get("placement") or {}
            if not isinstance(placement, dict):
                continue
            faculty = str(placement.get("faculty_id") or "").strip()
            if faculty:
                scores[faculty] = scores.get(faculty, 0) + 1
        return scores

    def formulate_query(self, faculty_id: str, faculty_desc: str, llm: Any) -> str:
        """Ask the LLM to generate a focused research query for the faculty."""
        from langchain_core.messages import HumanMessage
        prompt = (
            f"Generate a single focused web search query (under 15 words) to find a high-quality "
            f"educational resource about the following cognitive domain: "
            f"'{faculty_id}' — {faculty_desc}. "
            f"Return only the search query, nothing else."
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        return str(getattr(response, "content", response) or "").strip().strip('"')

    def synthesize_document(
        self,
        faculty_id: str,
        query: str,
        search_results: list[Any],
        llm: Any,
    ) -> str:
        """Synthesize a structured markdown research document from search results."""
        from langchain_core.messages import HumanMessage
        sources_text = "\n\n".join(
            f"Source: {r.url}\nTitle: {r.title}\n{r.content[:800]}"
            for r in search_results
        )
        faculty_desc = FACULTY_DESCRIPTIONS.get(faculty_id, faculty_id)
        prompt = (
            f"You are METIS, a research companion. Based on the following web sources, "
            f"write a concise, structured research note (300-500 words) about '{faculty_id}' "
            f"({faculty_desc}). Format as markdown with:\n"
            f"- A clear title (# Title)\n"
            f"- A summary paragraph\n"
            f"- 3-5 Key Findings as bullet points\n"
            f"- A Sources section listing URLs\n\n"
            f"Research query: {query}\n\n"
            f"Sources:\n{sources_text}"
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        return str(getattr(response, "content", response) or "").strip()

    def save_temp_document(self, content: str, faculty_id: str) -> pathlib.Path:
        """Write synthesized document to a temp .md file."""
        filename = f"auto_research_{faculty_id}_{uuid.uuid4().hex[:8]}.md"
        path = self._temp_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    async def run_batch(
        self,
        *,
        faculty_ids: list[str],
        settings: dict[str, Any],
        orchestrator: Any,
        concurrency: int = 1,
        request_delay_ms: int = 500,
        progress_cb: Callable[[ProgressEvent], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Run research for multiple faculty gaps concurrently.

        Uses an asyncio.Semaphore to cap concurrent tasks. Each task calls
        self.run() in a thread executor to avoid blocking the event loop.
        The target_faculty_id is passed to each run() call so the scan phase
        is bypassed and each task researches its assigned faculty directly.
        """
        import asyncio

        semaphore = asyncio.Semaphore(max(1, concurrency))
        delay_s = max(0, request_delay_ms) / 1000.0
        loop = asyncio.get_running_loop()

        async def _run_one(faculty_id: str) -> dict[str, Any] | None:
            async with semaphore:
                if delay_s > 0:
                    await asyncio.sleep(delay_s)
                return await loop.run_in_executor(
                    None,
                    lambda: self.run(
                        settings=settings,
                        indexes=[],
                        orchestrator=orchestrator,
                        target_faculty_id=faculty_id,
                        progress_cb=progress_cb,
                    ),
                )

        tasks = [_run_one(fid) for fid in faculty_ids]
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in raw if isinstance(r, dict)]

    def _extract_title(self, markdown: str) -> str:
        for line in markdown.splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped:
                return stripped[:120]
        return "Autonomous Research Note"
