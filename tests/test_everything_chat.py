"""Tests for M24 Phase 5 / Task 5.3 — _all_stars virtual retrieval.

Two surfaces exercised:

* :func:`_merge_everything_chat_sources` — pure merge helper; verified
  in isolation so the source-ranking + context-block assembly logic
  is pinned without standing up the LLM stack.
* :meth:`WorkspaceOrchestrator._run_everything_chat` — happy-path
  aggregation across two indexes, mocked so neither retrieval nor
  the LLM round-trips for real. Confirms the sentinel ``_all_stars``
  path is wired and that responses reference both indexes.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from metis_app.engine.querying import RagQueryRequest, RagQueryResult
from metis_app.services.workspace_orchestrator import (
    ALL_STARS_MARKER,
    WorkspaceOrchestrator,
    _merge_everything_chat_sources,
)


def _make_per_index_result(
    *,
    run_id: str,
    sources: list[dict[str, Any]],
    top_score: float,
) -> RagQueryResult:
    return RagQueryResult(
        run_id=run_id,
        answer_text=f"answer for {run_id}",
        sources=sources,
        context_block="legacy block, ignored by the merger",
        top_score=top_score,
        selected_mode="Q&A",
    )


class TestMergeEverythingChatSources:
    def test_orders_sources_by_score_descending(self) -> None:
        result_a = _make_per_index_result(
            run_id="A",
            sources=[{"score": 0.4, "title": "a-low", "snippet": "a low"}],
            top_score=0.4,
        )
        result_b = _make_per_index_result(
            run_id="B",
            sources=[
                {"score": 0.9, "title": "b-high", "snippet": "b high"},
                {"score": 0.5, "title": "b-mid", "snippet": "b mid"},
            ],
            top_score=0.9,
        )

        merged = _merge_everything_chat_sources([result_a, result_b])

        assert [s["title"] for s in merged["sources"]] == [
            "b-high",
            "b-mid",
            "a-low",
        ]
        assert merged["top_score"] == pytest.approx(0.9)
        assert "[S1] b-high" in merged["context_block"]
        assert "[S2] b-mid" in merged["context_block"]
        assert "[S3] a-low" in merged["context_block"]

    def test_handles_empty_input(self) -> None:
        merged = _merge_everything_chat_sources([])
        assert merged["sources"] == []
        assert merged["context_block"] == ""
        assert merged["top_score"] == 0.0


class TestRunEverythingChat:
    def test_aggregates_results_across_indexes(self) -> None:
        orchestrator = WorkspaceOrchestrator.__new__(WorkspaceOrchestrator)
        orchestrator._nyx_catalog = None  # type: ignore[attr-defined]

        settings = {
            "landing_constellation_user_stars": [
                {"id": "star-1", "linkedManifestPaths": ["idx-a"]},
                {"id": "star-2", "activeManifestPath": "idx-b"},
            ],
            "system_instructions": "test",
            "llm_provider": "mock",
        }

        # Stub _resolve_query_settings so the test doesn't need a real
        # settings_store on disk.
        with (
            patch.object(
                WorkspaceOrchestrator,
                "_resolve_query_settings",
                return_value=settings,
            ),
            patch(
                "metis_app.services.workspace_orchestrator.query_rag",
            ) as fake_query_rag,
            patch(
                "metis_app.utils.llm_providers.create_llm",
            ) as fake_create_llm,
        ):
            fake_query_rag.side_effect = [
                _make_per_index_result(
                    run_id="A",
                    sources=[
                        {
                            "score": 0.8,
                            "title": "from-idx-a",
                            "snippet": "alpha snippet",
                        }
                    ],
                    top_score=0.8,
                ),
                _make_per_index_result(
                    run_id="B",
                    sources=[
                        {
                            "score": 0.7,
                            "title": "from-idx-b",
                            "snippet": "beta snippet",
                        }
                    ],
                    top_score=0.7,
                ),
            ]
            fake_llm = fake_create_llm.return_value
            fake_llm.invoke.return_value = type(
                "FakeLLMResponse", (), {"content": "Aggregated answer."}
            )()

            result = orchestrator._run_everything_chat(
                RagQueryRequest(
                    manifest_path=ALL_STARS_MARKER,
                    question="what spans both?",
                    settings={},
                )
            )

        # Both indexes were retrieved against.
        assert fake_query_rag.call_count == 2
        manifest_paths_used = sorted(
            str(call.args[0].manifest_path) for call in fake_query_rag.call_args_list
        )
        assert manifest_paths_used == ["idx-a", "idx-b"]

        # The merged result references sources from both.
        titles = {source["title"] for source in result.sources}
        assert titles == {"from-idx-a", "from-idx-b"}
        assert result.answer_text == "Aggregated answer."
        assert result.top_score == pytest.approx(0.8)
        assert result.retrieval_plan["stages"][0]["stage_type"] == ALL_STARS_MARKER
        assert result.retrieval_plan["stages"][0]["payload"]["index_count"] == 2

    def test_no_attached_indexes_returns_friendly_fallback(self) -> None:
        orchestrator = WorkspaceOrchestrator.__new__(WorkspaceOrchestrator)
        orchestrator._nyx_catalog = None  # type: ignore[attr-defined]

        with patch.object(
            WorkspaceOrchestrator,
            "_resolve_query_settings",
            return_value={"landing_constellation_user_stars": []},
        ):
            result = orchestrator._run_everything_chat(
                RagQueryRequest(
                    manifest_path=ALL_STARS_MARKER,
                    question="anything?",
                    settings={},
                )
            )

        assert result.fallback["triggered"] is True
        assert result.fallback["reason"] == "no_attached_indexes"
        assert "no attached indexes" in result.answer_text.lower()
        assert result.sources == []
        # selected_mode must NOT be the sentinel — that would leak the
        # internal manifest marker to the frontend. It should mirror the
        # default mode resolution used elsewhere.
        assert result.selected_mode != ALL_STARS_MARKER

    def test_no_index_path_persists_session_bookkeeping(self) -> None:
        """When a session_id is supplied AND there are no attached indexes,
        the user message + fallback assistant message must still hit the
        session repository — the early-return previously dropped both.
        """
        from unittest.mock import MagicMock

        orchestrator = WorkspaceOrchestrator.__new__(WorkspaceOrchestrator)
        orchestrator._nyx_catalog = None  # type: ignore[attr-defined]

        prepare_calls: list[tuple[Any, ...]] = []
        append_calls: list[dict[str, Any]] = []

        def fake_prepare(self_: Any, session_id: str, *args: Any, **kwargs: Any) -> None:
            prepare_calls.append((session_id, args, kwargs))

        def fake_append(self_: Any, session_id: str, **kwargs: Any) -> None:
            append_calls.append({"session_id": session_id, **kwargs})

        with (
            patch.object(
                WorkspaceOrchestrator,
                "_resolve_query_settings",
                return_value={"landing_constellation_user_stars": []},
            ),
            patch.object(
                WorkspaceOrchestrator,
                "_prepare_session_for_query",
                fake_prepare,
            ),
            patch.object(
                WorkspaceOrchestrator,
                "append_message",
                fake_append,
            ),
        ):
            result = orchestrator._run_everything_chat(
                RagQueryRequest(
                    manifest_path=ALL_STARS_MARKER,
                    question="anything?",
                    settings={},
                ),
                session_id="sess-no-idx",
            )

        # Session was prepared exactly once with the sentinel marker.
        assert len(prepare_calls) == 1
        assert prepare_calls[0][0] == "sess-no-idx"
        assert prepare_calls[0][2].get("manifest_path") == ALL_STARS_MARKER

        # Both user + assistant turns were appended.
        roles = [call.get("role") for call in append_calls]
        assert roles == ["user", "assistant"]
        assert append_calls[0]["session_id"] == "sess-no-idx"
        assert append_calls[0]["content"] == "anything?"
        assert append_calls[1]["session_id"] == "sess-no-idx"
        assert append_calls[1]["content"] == result.answer_text


class TestCollectAttachedManifestPaths:
    """Coverage for ``_collect_attached_manifest_paths`` defensive shapes."""

    def test_string_linked_manifest_paths_is_treated_as_single_path(self) -> None:
        """A legacy / corrupted ``linkedManifestPaths`` stored as a plain
        string must NOT iterate by character. Normalise to a one-element
        list so the path flows through dedupe intact.
        """
        orchestrator = WorkspaceOrchestrator.__new__(WorkspaceOrchestrator)
        settings = {
            "landing_constellation_user_stars": [
                {"id": "star-1", "linkedManifestPaths": "lone/manifest.json"},
            ],
        }
        paths = orchestrator._collect_attached_manifest_paths(settings)
        assert paths == ["lone/manifest.json"]

    def test_non_list_non_string_linked_manifest_paths_is_ignored(self) -> None:
        """A wholly unexpected shape (dict, int) is ignored, not iterated."""
        orchestrator = WorkspaceOrchestrator.__new__(WorkspaceOrchestrator)
        settings = {
            "landing_constellation_user_stars": [
                {"id": "s1", "linkedManifestPaths": {"unexpected": "shape"}},
                {"id": "s2", "linkedManifestPaths": 42},
                {"id": "s3", "activeManifestPath": "good/path.json"},
            ],
        }
        paths = orchestrator._collect_attached_manifest_paths(settings)
        assert paths == ["good/path.json"]


class TestResolveIndexIdFromManifest:
    """Sentinel-branch coverage for `_resolve_index_id_from_manifest`.

    Everything chat sessions persist with ``index_id="_all_stars"``
    so they can be distinguished from regular unattached sessions
    (which carry ``index_id=""``) in the session DB. Prior to the
    sentinel branch, the manifest-path lookup fell through and
    returned ``""`` for the marker, losing that signal.
    """

    def test_all_stars_marker_returns_sentinel(self) -> None:
        orchestrator = WorkspaceOrchestrator.__new__(WorkspaceOrchestrator)
        # No ``list_indexes`` should be hit — the sentinel branch
        # short-circuits before the lookup. We monkey-patch it to
        # raise to make that explicit.
        with patch.object(
            WorkspaceOrchestrator,
            "list_indexes",
            side_effect=AssertionError("list_indexes must not be called"),
        ):
            assert (
                orchestrator._resolve_index_id_from_manifest(ALL_STARS_MARKER)
                == ALL_STARS_MARKER
            )

    def test_empty_manifest_returns_empty_string(self) -> None:
        orchestrator = WorkspaceOrchestrator.__new__(WorkspaceOrchestrator)
        assert orchestrator._resolve_index_id_from_manifest("") == ""
        assert orchestrator._resolve_index_id_from_manifest(None) == ""
