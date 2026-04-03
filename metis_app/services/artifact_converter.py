"""Semantic Observability — convert human-labeled trace runs into durable artifacts.

Converts a "reinforce" or "suppress" labeled run into reusable system artifacts:
  - SKILL.md  (drops into skills/ directory)
  - golden eval case  (appends to evals/golden_dataset.jsonl)

Both outputs are derived purely from the trace data — no additional LLM calls
are needed for the skill export; an optional LLM summary is added if available.
"""

from __future__ import annotations

import json
import pathlib
import textwrap
import uuid
from datetime import datetime, timezone
from typing import Any

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_SKILLS_DIR = _REPO_ROOT / "skills"
_EVALS_DIR = _REPO_ROOT / "evals"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArtifactConverter:
    """Convert labeled trace runs into reusable METIS artifacts."""

    def __init__(
        self,
        skills_dir: str | pathlib.Path | None = None,
        evals_dir: str | pathlib.Path | None = None,
    ) -> None:
        self._skills_dir = pathlib.Path(skills_dir or _SKILLS_DIR)
        self._evals_dir = pathlib.Path(evals_dir or _EVALS_DIR)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export_as_skill(
        self,
        run_id: str,
        profile: dict[str, Any],
        *,
        skill_id: str = "",
        feedback_note: str = "",
    ) -> dict[str, Any]:
        """Derive a SKILL.md from a reinforce-labeled run's behavioral profile.

        Parameters
        ----------
        run_id:
            The trace run this skill is derived from.
        profile:
            BehaviorProfile dict (from BehaviorDiscoveryService.get_run_profile).
        skill_id:
            Override the generated skill_id.  Defaults to ``obs_<run_id[:8]>``.
        feedback_note:
            Human note from the feedback record — used as description.

        Returns a dict with ``skill_id``, ``skill_path``, and ``content``.
        """
        sid = str(skill_id or "").strip() or f"obs_{run_id[:8]}"
        mode = str(profile.get("mode") or "Q&A")
        strategy = str(profile.get("strategy_fingerprint") or "direct_synthesis")
        iterations = int(profile.get("iterations_used") or 0)
        description = (
            str(feedback_note or "").strip()
            or f"Auto-derived skill from run {run_id}: strategy={strategy}, mode={mode}."
        )

        # Build runtime_overrides from the profile's observed settings
        overrides: dict[str, Any] = {}
        if iterations > 1:
            overrides["agentic_mode"] = True
            overrides["agentic_max_iterations"] = max(2, iterations)
        if mode:
            overrides["selected_mode"] = mode

        triggers_query: list[str] = []
        if strategy in ("gap_fill", "convergence"):
            triggers_query.append("deep dive")
            triggers_query.append("research")
        elif strategy == "sub_query_expansion":
            triggers_query.append("explore")
            triggers_query.append("what are")
        triggers_mode: list[str] = []
        if mode:
            triggers_mode.append(mode)

        overrides_yaml = ""
        if overrides:
            overrides_yaml = "runtime_overrides:\n"
            for k, v in overrides.items():
                overrides_yaml += f"  {k}: {json.dumps(v)}\n"

        triggers_yaml = ""
        if triggers_query or triggers_mode:
            triggers_yaml = "triggers:\n"
            if triggers_query:
                triggers_yaml += "  query: [" + ", ".join(f'"{t}"' for t in triggers_query) + "]\n"
            if triggers_mode:
                triggers_yaml += "  mode: [" + ", ".join(f'"{m}"' for m in triggers_mode) + "]\n"

        content = textwrap.dedent(f"""\
            ---
            skill_id: {sid}
            name: "{description[:80]}"
            description: >
              {description}
              Derived from trace run {run_id} on {_utc_now()[:10]}.
              Observed strategy: {strategy}, mode: {mode}, iterations: {iterations}.
            enabled_by_default: false
            priority: 50
            {triggers_yaml}{overrides_yaml}---

            # {sid}

            {description}

            **Derived from:** trace run `{run_id}`
            **Strategy observed:** `{strategy}`
            **Mode:** `{mode}`
            **Iterations:** {iterations}
        """)

        skill_dir = self._skills_dir / sid
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(content, encoding="utf-8")

        return {
            "skill_id": sid,
            "skill_path": str(skill_path),
            "content": content,
        }

    def export_as_eval(
        self,
        run_id: str,
        profile: dict[str, Any],
        events: list[dict[str, Any]],
        *,
        feedback_note: str = "",
        label: str = "reinforce",
    ) -> dict[str, Any]:
        """Package a run as a golden eval case and append to evals/golden_dataset.jsonl.

        The eval case captures:
          - query text (from run events)
          - retrieved context chunks (from retrieval_complete event)
          - expected response strategy and citation pattern
          - behavioral assertions

        Returns the eval case dict.
        """
        query_text = self._extract_query(events)
        context_chunks = self._extract_context_chunks(events)
        final_answer_preview = self._extract_final_answer(events)
        strategy = str(profile.get("strategy_fingerprint") or "direct_synthesis")
        mode = str(profile.get("mode") or "")

        eval_case: dict[str, Any] = {
            "eval_id": str(uuid.uuid4()),
            "derived_from_run": run_id,
            "created_at": _utc_now(),
            "label": label,
            "feedback_note": feedback_note,
            "query": query_text,
            "mode": mode,
            "context_chunks": context_chunks[:10],  # cap to 10 chunks
            "expected_strategy": strategy,
            "expected_min_iterations": int(profile.get("iterations_used") or 0),
            "expected_min_citations": max(0, int(profile.get("citation_count") or 0) - 1),
            "answer_preview": final_answer_preview[:500],
            "assertions": self._build_assertions(profile),
        }

        self._evals_dir.mkdir(parents=True, exist_ok=True)
        golden_path = self._evals_dir / "golden_dataset.jsonl"
        with golden_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(eval_case, ensure_ascii=False) + "\n")

        return eval_case

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_query(self, events: list[dict[str, Any]]) -> str:
        for event in events:
            payload = event.get("payload") or {}
            if isinstance(payload, dict):
                q = str(payload.get("query_text") or "").strip()
                if q:
                    return q
                # Try to get from prompt field
                prompt = event.get("prompt") or {}
                if isinstance(prompt, dict):
                    user_msg = str(prompt.get("user") or "").strip()
                    if user_msg:
                        return user_msg[:500]
        return ""

    def _extract_context_chunks(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for event in events:
            event_type = str(event.get("event_type") or "")
            if event_type not in {"retrieval_complete", "retrieval_augmented"}:
                continue
            payload = event.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            retrieval = payload.get("retrieval_results") or {}
            sources = (
                retrieval.get("sources")
                if isinstance(retrieval, dict)
                else payload.get("sources")
                if isinstance(payload.get("sources"), list)
                else []
            )
            if sources and isinstance(sources, list):
                return [
                    {"snippet": str(s.get("snippet") or ""), "source": str(s.get("source") or ""), "score": float(s.get("score") or 0.0)}
                    for s in sources[:10]
                    if isinstance(s, dict)
                ]
        return []

    def _extract_final_answer(self, events: list[dict[str, Any]]) -> str:
        for event in reversed(events):
            if str(event.get("event_type") or "") == "final":
                payload = event.get("payload") or {}
                if isinstance(payload, dict):
                    return str(payload.get("answer_text") or "")
        return ""

    def _build_assertions(self, profile: dict[str, Any]) -> list[dict[str, Any]]:
        assertions: list[dict[str, Any]] = []
        strategy = str(profile.get("strategy_fingerprint") or "")
        if strategy:
            assertions.append({"type": "strategy_fingerprint", "expected": strategy})
        min_cit = max(0, int(profile.get("citation_count") or 0) - 1)
        if min_cit > 0:
            assertions.append({"type": "min_citations", "expected": min_cit})
        iters = int(profile.get("iterations_used") or 0)
        if iters > 0:
            assertions.append({"type": "min_iterations", "expected": iters})
        if not profile.get("had_error"):
            assertions.append({"type": "no_error"})
        return assertions
