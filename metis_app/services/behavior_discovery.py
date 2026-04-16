"""Semantic Observability — behavior discovery over the trace store.

Implements the "ontology follows execution" principle: reads raw METIS traces
and surfaces emergent behavioral patterns without requiring predefined metrics.

Discovery pipeline:
    1. Read recent runs from TraceStore
    2. Compute a lightweight BehaviorProfile per run (rule-based, no LLM needed)
    3. Cluster runs by strategy_fingerprint + skill combination
    4. Flag anomalies using heuristic thresholds
    5. Optionally generate an LLM behavioral narrative per run

Usage::

    svc = BehaviorDiscoveryService()
    result = svc.discover(limit=50)
    semantic = svc.describe_run("some-run-id", settings=settings)
"""

from __future__ import annotations

import json
import pathlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_DEFAULT_TRACE_DIR = _REPO_ROOT / "traces"

# ---------------------------------------------------------------------------
# Heuristic thresholds for anomaly detection
# ---------------------------------------------------------------------------
_ANOMALY_HIGH_ITERATIONS = 3          # iteration_count above this → flagged
_ANOMALY_ZERO_CITATIONS = True         # zero citations in final → flagged
_ANOMALY_LOW_CONVERGENCE = 0.5         # convergence_score below this → flagged
_ANOMALY_STRATEGY_SWITCH = True        # strategy changes mid-run → flagged


@dataclass
class BehaviorProfile:
    """Distilled behavioral summary for a single run.

    All fields are derived from the raw trace events without calling an LLM.
    """

    run_id: str
    query_preview: str = ""          # First 120 chars of the question
    mode: str = ""                   # RAG mode (Q&A, Research, Evidence Pack, …)
    primary_skill: str = ""          # Primary skill_id activated
    strategy_fingerprint: str = "direct_synthesis"
    iterations_used: int = 0
    gap_count_total: int = 0
    citation_count: int = 0
    citation_diversity_score: float = 1.0
    convergence_score: float = 0.0
    source_count: int = 0
    retrieval_delta_per_iter: list[int] = field(default_factory=list)
    fallback_triggered: bool = False
    had_error: bool = False
    first_seen: str = ""             # ISO timestamp of run_started
    interestingness_score: float = 0.0
    anomalies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiscoveryResult:
    """Aggregated output of a discovery scan over N recent runs."""

    profiles: list[BehaviorProfile]
    clusters: dict[str, list[str]]   # cluster_key → [run_id, …]
    anomalous_run_ids: list[str]
    strategy_histogram: dict[str, int]
    total_runs_scanned: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "profiles": [p.to_dict() for p in self.profiles],
            "clusters": self.clusters,
            "anomalous_run_ids": self.anomalous_run_ids,
            "strategy_histogram": self.strategy_histogram,
            "total_runs_scanned": self.total_runs_scanned,
        }


class BehaviorDiscoveryService:
    """Surface emergent agent behaviors from the METIS trace store.

    All heavy discovery methods are synchronous and CPU-bound (file I/O +
    light computation).  Call from thread pools if needed in async contexts.
    """

    def __init__(self, trace_dir: str | pathlib.Path | None = None) -> None:
        self._trace_dir = pathlib.Path(trace_dir or _DEFAULT_TRACE_DIR)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def discover(self, *, limit: int = 100) -> DiscoveryResult:
        """Scan the last *limit* distinct runs and return a DiscoveryResult."""
        run_ids = self._list_recent_run_ids(limit=limit)
        profiles = [self._profile_run(rid) for rid in run_ids]
        clusters = self._cluster(profiles)
        anomalous = [p.run_id for p in profiles if p.anomalies]
        histogram: dict[str, int] = {}
        for p in profiles:
            histogram[p.strategy_fingerprint] = histogram.get(p.strategy_fingerprint, 0) + 1
        return DiscoveryResult(
            profiles=profiles,
            clusters=clusters,
            anomalous_run_ids=anomalous,
            strategy_histogram=histogram,
            total_runs_scanned=len(profiles),
        )

    def get_run_profile(self, run_id: str) -> BehaviorProfile | None:
        """Return the BehaviorProfile for a single run, or None if not found."""
        events = self._read_run_events(run_id)
        if not events:
            return None
        return self._build_profile(run_id, events)

    def describe_run(self, run_id: str, *, settings: dict[str, Any]) -> dict[str, Any]:
        """Return enriched semantic description for *run_id*.

        Includes the BehaviorProfile plus an LLM-generated narrative if a
        provider is configured in *settings*.  Falls back gracefully if the
        LLM is unavailable.
        """
        profile = self.get_run_profile(run_id)
        if profile is None:
            return {"run_id": run_id, "error": "run_not_found"}

        narrative = self._generate_narrative(profile, settings=settings)
        return {
            **profile.to_dict(),
            "narrative": narrative,
        }

    # ------------------------------------------------------------------
    # Internal: trace reading
    # ------------------------------------------------------------------

    def _list_recent_run_ids(self, *, limit: int) -> list[str]:
        """Return up to *limit* distinct run_ids from the most-recent events."""
        runs_file = self._trace_dir / "runs.jsonl"
        if not runs_file.exists():
            return []
        lines = runs_file.read_text(encoding="utf-8", errors="replace").splitlines()
        seen: list[str] = []
        seen_set: set[str] = set()
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = str(row.get("run_id") or "").strip()
            if rid and rid not in seen_set:
                seen_set.add(rid)
                seen.append(rid)
            if len(seen) >= limit:
                break
        return list(reversed(seen))

    def _read_run_events(self, run_id: str) -> list[dict[str, Any]]:
        """Return all trace events for *run_id* from the per-run JSONL file."""
        per_run_file = self._trace_dir / "runs" / f"{run_id}.jsonl"
        if per_run_file.exists():
            lines = per_run_file.read_text(encoding="utf-8", errors="replace").splitlines()
        else:
            # Fall back to scanning the global runs.jsonl
            global_file = self._trace_dir / "runs.jsonl"
            if not global_file.exists():
                return []
            all_lines = global_file.read_text(encoding="utf-8", errors="replace").splitlines()
            lines = [
                ln for ln in all_lines
                if f'"run_id": "{run_id}"' in ln or f'"run_id":"{run_id}"' in ln
            ]
        events: list[dict[str, Any]] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    events.append(row)
            except json.JSONDecodeError:
                continue
        return events

    # ------------------------------------------------------------------
    # Internal: profiling
    # ------------------------------------------------------------------

    def _profile_run(self, run_id: str) -> BehaviorProfile:
        events = self._read_run_events(run_id)
        return self._build_profile(run_id, events)

    def _build_profile(self, run_id: str, events: list[dict[str, Any]]) -> BehaviorProfile:  # noqa: C901
        profile = BehaviorProfile(run_id=run_id)

        strategy_seen: set[str] = set()
        retrieval_deltas: list[int] = []

        for event in events:
            event_type = str(event.get("event_type") or "").strip()
            payload = event.get("payload") or {}
            if not isinstance(payload, dict):
                payload = {}

            if event_type == "run_started":
                profile.first_seen = str(event.get("timestamp") or "")
                # mode and skill info come from skill_selection payload
                mode = str(payload.get("mode") or payload.get("selected_mode") or "")
                if mode:
                    profile.mode = mode

            elif event_type == "skill_selection":
                profile.primary_skill = str(payload.get("primary") or "")
                if not profile.mode:
                    profile.mode = str(payload.get("mode") or "")

            elif event_type == "retrieval_complete":
                srcs = payload.get("sources") or []
                profile.source_count = max(profile.source_count, len(srcs) if isinstance(srcs, list) else 0)

            elif event_type == "gaps_identified":
                gaps = payload.get("gaps") or []
                profile.gap_count_total += len(gaps) if isinstance(gaps, list) else 0
                fp = str(payload.get("strategy_fingerprint") or "gap_fill")
                strategy_seen.add(fp)

            elif event_type == "refinement_retrieval":
                delta = payload.get("retrieval_delta")
                if isinstance(delta, int):
                    retrieval_deltas.append(delta)
                fp = str(payload.get("strategy_fingerprint") or "gap_fill")
                strategy_seen.add(fp)

            elif event_type == "iteration_complete":
                profile.iterations_used = int(payload.get("iterations_used") or 0)
                profile.convergence_score = float(payload.get("convergence_score") or 0.0)
                profile.citation_count = int(payload.get("citation_count") or 0)
                profile.citation_diversity_score = float(payload.get("citation_diversity_score") or 1.0)
                profile.gap_count_total = int(payload.get("gap_count_total") or profile.gap_count_total)
                fp = str(payload.get("strategy_fingerprint") or "")
                if fp:
                    profile.strategy_fingerprint = fp

            elif event_type == "final":
                answer = str(payload.get("answer_text") or "")
                fp = str(payload.get("strategy_fingerprint") or "")
                if fp:
                    strategy_seen.add(fp)
                # Count citations from answer text
                if not profile.citation_count:
                    profile.citation_count = len(set(re.findall(r"\[S\d+\]", answer)))
                fallback = payload.get("fallback") or {}
                if isinstance(fallback, dict):
                    profile.fallback_triggered = bool(fallback.get("triggered"))
                # Extract query preview from retrieval block if not set
                if not profile.query_preview:
                    # The question travels in the context_block or as a field
                    q = str(payload.get("query_text") or "")
                    profile.query_preview = q[:120]

            elif event_type in {"error", "tool_error"}:
                profile.had_error = True

        # Determine effective strategy fingerprint
        if not profile.strategy_fingerprint or profile.strategy_fingerprint == "direct_synthesis":
            if strategy_seen:
                # Prefer most specific strategy
                for fp in ("convergence", "gap_fill", "sub_query_expansion", "fallback", "direct_synthesis"):
                    if fp in strategy_seen:
                        profile.strategy_fingerprint = fp
                        break
            elif profile.iterations_used == 0:
                profile.strategy_fingerprint = "direct_synthesis"

        profile.retrieval_delta_per_iter = retrieval_deltas
        self._score_interestingness(profile)
        self._detect_anomalies(profile)
        return profile

    def _score_interestingness(self, profile: BehaviorProfile) -> None:
        """Compute a scalar interestingness score using heuristics."""
        score = 0.0
        # High iteration count is interesting
        score += min(profile.iterations_used * 0.15, 0.45)
        # Zero citations is interesting (possible hallucination risk)
        if profile.citation_count == 0 and profile.source_count > 0:
            score += 0.2
        # Low convergence after many iterations is interesting
        if profile.iterations_used > 1 and profile.convergence_score < _ANOMALY_LOW_CONVERGENCE:
            score += 0.15
        # Fallback triggered is interesting
        if profile.fallback_triggered:
            score += 0.1
        # Errors are interesting
        if profile.had_error:
            score += 0.25
        # High citation diversity is mildly interesting (agent explored lots of sources)
        if profile.citation_diversity_score > 0.8 and profile.iterations_used > 1:
            score += 0.05
        profile.interestingness_score = round(min(score, 1.0), 4)

    def _detect_anomalies(self, profile: BehaviorProfile) -> None:
        anomalies: list[str] = []
        if profile.iterations_used > _ANOMALY_HIGH_ITERATIONS:
            anomalies.append(f"high_iteration_count:{profile.iterations_used}")
        if profile.citation_count == 0 and profile.source_count > 0:
            anomalies.append("zero_citations_despite_retrieval")
        if profile.iterations_used > 1 and profile.convergence_score < _ANOMALY_LOW_CONVERGENCE:
            anomalies.append(f"low_convergence:{profile.convergence_score:.2f}")
        if profile.fallback_triggered:
            anomalies.append("fallback_triggered")
        if profile.had_error:
            anomalies.append("had_error")
        profile.anomalies = anomalies

    # ------------------------------------------------------------------
    # Internal: clustering
    # ------------------------------------------------------------------

    def _cluster(self, profiles: list[BehaviorProfile]) -> dict[str, list[str]]:
        """Rule-based clustering by strategy_fingerprint + mode + primary_skill."""
        clusters: dict[str, list[str]] = {}
        for p in profiles:
            key = f"{p.strategy_fingerprint}|{p.mode or 'unknown'}|{p.primary_skill or 'none'}"
            clusters.setdefault(key, []).append(p.run_id)
        return clusters

    # ------------------------------------------------------------------
    # Internal: LLM narrative generation
    # ------------------------------------------------------------------

    def _generate_narrative(
        self,
        profile: BehaviorProfile,
        *,
        settings: dict[str, Any],
    ) -> str:
        """Generate a 1-2 sentence behavioral narrative using the configured LLM.

        Returns an empty string if the LLM is unavailable or raises.
        """
        try:
            from metis_app.utils.llm_providers import create_llm
            from metis_app.engine.querying import _response_text

            llm = create_llm(settings)
            system = (
                "You are a concise technical analyst. "
                "Given a behavioral profile of an AI agent run, write exactly 1-2 sentences "
                "describing what the agent did — tactics used, whether it succeeded, and any "
                "notable anomalies. Be specific and avoid generic language."
            )
            profile_summary = (
                f"mode={profile.mode or 'unknown'}, "
                f"strategy={profile.strategy_fingerprint}, "
                f"iterations={profile.iterations_used}, "
                f"gaps_found={profile.gap_count_total}, "
                f"citations={profile.citation_count}, "
                f"diversity={profile.citation_diversity_score:.2f}, "
                f"convergence={profile.convergence_score:.2f}, "
                f"sources={profile.source_count}, "
                f"fallback={profile.fallback_triggered}, "
                f"error={profile.had_error}, "
                f"anomalies={profile.anomalies}"
            )
            response = llm.invoke([
                {"type": "system", "content": system},
                {"type": "human", "content": f"Profile: {profile_summary}"},
            ])
            return str(_response_text(response) or "").strip()
        except Exception:  # noqa: BLE001
            return ""
