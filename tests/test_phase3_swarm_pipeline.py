"""Tests for Phase 3 MiroShark-integration additions.

Covers:
- streaming._format_swarm_report (pure function)
- streaming._classify_source_tiers (mocked LLM)
- swarm_service.stream_swarm_simulation (mocked LLM via monkeypatching create_llm)
- querying.query_swarm (mocked swarm service)
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# _format_swarm_report
# ---------------------------------------------------------------------------

def _make_report_dict(
    *,
    summary: str = "A policy document about renewable energy.",
    topics: list[str] | None = None,
    agents: list[dict] | None = None,
    rounds: list[dict] | None = None,
    consensus: list[str] | None = None,
    contested: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "document_summary": summary,
        "topics": topics or ["renewable energy", "climate policy"],
        "agents": agents or [
            {"name": "Alice", "stance_summary": "Pro-solar advocate"},
            {"name": "Bob", "stance_summary": "Skeptical economist"},
        ],
        "rounds": rounds or [
            {
                "round_num": 1,
                "posts": [
                    {"agent_name": "Alice", "text": "Solar is clearly the future."},
                    {"agent_name": "Bob", "text": "The economics are uncertain."},
                ],
                "belief_snapshots": {},
            }
        ],
        "consensus_topics": consensus or ["energy transition"],
        "contested_topics": contested or ["carbon pricing"],
    }


def test_format_swarm_report_includes_summary():
    from metis_app.engine.streaming import _format_swarm_report

    report = _make_report_dict(summary="Key document about AI governance.")
    result = _format_swarm_report(report)
    assert "AI governance" in result
    assert "Document Overview" in result


def test_format_swarm_report_includes_topics():
    from metis_app.engine.streaming import _format_swarm_report

    report = _make_report_dict(topics=["topic_alpha", "topic_beta"])
    result = _format_swarm_report(report)
    assert "topic_alpha" in result
    assert "topic_beta" in result


def test_format_swarm_report_includes_agent_names():
    from metis_app.engine.streaming import _format_swarm_report

    report = _make_report_dict(agents=[
        {"name": "XYZ_Agent", "stance_summary": "Neutral observer"},
    ])
    result = _format_swarm_report(report)
    assert "XYZ_Agent" in result
    assert "Neutral observer" in result


def test_format_swarm_report_includes_consensus_and_contested():
    from metis_app.engine.streaming import _format_swarm_report

    report = _make_report_dict(
        consensus=["shared_goal"],
        contested=["disputed_method"],
    )
    result = _format_swarm_report(report)
    assert "shared_goal" in result
    assert "disputed_method" in result
    assert "Consensus" in result
    assert "Contested" in result


def test_format_swarm_report_shows_last_round_posts():
    from metis_app.engine.streaming import _format_swarm_report

    report = _make_report_dict(rounds=[
        {"round_num": 1, "posts": [{"agent_name": "A", "text": "round1 text"}], "belief_snapshots": {}},
        {"round_num": 2, "posts": [{"agent_name": "B", "text": "final_round_post_unique"}], "belief_snapshots": {}},
    ])
    result = _format_swarm_report(report)
    assert "final_round_post_unique" in result


def test_format_swarm_report_empty_dict_returns_string():
    from metis_app.engine.streaming import _format_swarm_report

    result = _format_swarm_report({})
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _classify_source_tiers
# ---------------------------------------------------------------------------

def _fake_llm_invoke(messages: list[dict]) -> Any:
    """LLM that always returns a JSON array of tiers."""
    response = MagicMock()
    response.content = '["Supporting", "Refuting", "Contested"]'
    return response


def test_classify_source_tiers_returns_correct_labels():
    from metis_app.engine.streaming import _classify_source_tiers

    sources = [
        {"snippet": "This clearly supports the claim."},
        {"snippet": "This contradicts the claim entirely."},
        {"snippet": "This is somewhat related but mixed."},
    ]
    llm = MagicMock()
    llm.invoke.side_effect = _fake_llm_invoke

    result = _classify_source_tiers("Does renewable energy reduce costs?", sources, llm)
    assert result == ["Supporting", "Refuting", "Contested"]


def test_classify_source_tiers_empty_sources():
    from metis_app.engine.streaming import _classify_source_tiers

    llm = MagicMock()
    result = _classify_source_tiers("any question", [], llm)
    assert result == []
    llm.invoke.assert_not_called()


def test_classify_source_tiers_falls_back_on_llm_failure():
    from metis_app.engine.streaming import _classify_source_tiers

    sources = [{"snippet": "abc"}, {"snippet": "def"}]
    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("LLM offline")

    result = _classify_source_tiers("question", sources, llm)
    assert result == ["Supporting", "Supporting"]


def test_classify_source_tiers_falls_back_on_wrong_length():
    from metis_app.engine.streaming import _classify_source_tiers

    # LLM returns fewer tiers than sources
    sources = [{"snippet": "a"}, {"snippet": "b"}, {"snippet": "c"}]
    llm = MagicMock()
    response = MagicMock()
    response.content = '["Supporting"]'
    llm.invoke.return_value = response

    result = _classify_source_tiers("question", sources, llm)
    # Wrong-length array → fallback to all Supporting
    assert result == ["Supporting", "Supporting", "Supporting"]


def test_classify_source_tiers_normalises_unknown_tier_to_contested():
    from metis_app.engine.streaming import _classify_source_tiers

    sources = [{"snippet": "x"}, {"snippet": "y"}]
    llm = MagicMock()
    response = MagicMock()
    response.content = '["Supporting", "WeirdTier"]'
    llm.invoke.return_value = response

    result = _classify_source_tiers("q", sources, llm)
    assert result[0] == "Supporting"
    assert result[1] == "Contested"  # Unknown → Contested


# ---------------------------------------------------------------------------
# stream_swarm_simulation event types
# ---------------------------------------------------------------------------

def _build_minimal_swarm_env(monkeypatch):
    """Monkeypatch create_llm in swarm_service to return a fast fake LLM."""
    fake_llm = MagicMock()

    def _invoke(messages):
        # Detect what the swarm service is asking and return minimal valid JSON
        text = " ".join(str(m.get("content", "")) for m in messages)
        if "JSON array" in text and "topic" in text.lower():
            r = MagicMock()
            r.content = '["policy", "economics"]'
            return r
        if "JSON array" in text or "persona" in text.lower():
            r = MagicMock()
            r.content = json.dumps([
                {
                    "name": "TestAgent",
                    "persona_type": "individual",
                    "background": "A researcher.",
                    "stance_summary": "Supportive.",
                    "initial_beliefs": {"policy": 0.7, "economics": 0.4},
                }
            ])
            return r
        # Default: return a short response for post generation
        r = MagicMock()
        r.content = "I agree with this approach."
        return r

    fake_llm.invoke.side_effect = _invoke
    monkeypatch.setattr("metis_app.services.swarm_service.create_llm", lambda _: fake_llm)
    return fake_llm


def test_stream_swarm_simulation_yields_ordered_events(monkeypatch):
    _build_minimal_swarm_env(monkeypatch)

    from metis_app.services.swarm_service import stream_swarm_simulation

    events = list(stream_swarm_simulation(
        context_text="Renewable energy policy discussion document.",
        settings={"llm_provider": "openai", "llm_model": "gpt-4o"},
        n_personas=1,
        n_rounds=1,
        topics=["policy"],
    ))

    event_types = [e["event"] for e in events]
    assert "topics_extracted" in event_types
    assert "persona_created" in event_types
    assert "simulation_round" in event_types
    assert "simulation_complete" in event_types


def test_stream_swarm_simulation_simulation_complete_has_report(monkeypatch):
    _build_minimal_swarm_env(monkeypatch)

    from metis_app.services.swarm_service import stream_swarm_simulation

    events = list(stream_swarm_simulation(
        context_text="Document text.",
        settings={},
        n_personas=1,
        n_rounds=1,
        topics=["topic"],
    ))

    complete_event = next(e for e in events if e["event"] == "simulation_complete")
    assert "report" in complete_event
    report = complete_event["report"]
    assert "topics" in report
    assert isinstance(report["agents"], list)


def test_stream_swarm_simulation_persona_created_has_name(monkeypatch):
    _build_minimal_swarm_env(monkeypatch)

    from metis_app.services.swarm_service import stream_swarm_simulation

    events = list(stream_swarm_simulation(
        context_text="Document text.",
        settings={},
        n_personas=1,
        n_rounds=1,
        topics=["topic"],
    ))

    persona_events = [e for e in events if e["event"] == "persona_created"]
    assert len(persona_events) >= 1
    # persona_created event has an 'agent' sub-dict with a 'name' field
    assert "agent" in persona_events[0]
    assert "name" in persona_events[0]["agent"]


# ---------------------------------------------------------------------------
# query_swarm
# ---------------------------------------------------------------------------

def _make_mock_report():
    """Build a minimal SimulationReport-like object with to_dict()."""
    from metis_app.services.swarm_service import (
        BeliefState,
        SimulationReport,
        SimulationRound,
        SwarmAgent,
    )

    agent = SwarmAgent(
        agent_id="a1",
        name="MockAgent",
        persona_type="individual",
        background="Background text.",
        stance_summary="Supportive.",
        belief=BeliefState(topic_stance={"topic": 0.5}),
    )
    rnd = SimulationRound(
        round_num=1,
        posts=[{"agent_name": "MockAgent", "text": "My post."}],
    )
    return SimulationReport(
        document_summary="Mock summary.",
        topics=["topic"],
        agents=[agent],
        rounds=[rnd],
        final_beliefs={"MockAgent": {"topic": 0.5}},
        consensus_topics=["topic"],
        contested_topics=[],
    )


def test_query_swarm_returns_swarm_query_result(tmp_path, monkeypatch):
    """query_swarm should return a SwarmQueryResult with populated fields."""

    from metis_app.engine.querying import SwarmQueryRequest, SwarmQueryResult

    mock_report = _make_mock_report()

    # Patch the entire retrieval + swarm chain
    monkeypatch.setattr(
        "metis_app.engine.querying.load_index_manifest",
        lambda p: MagicMock(backend="json"),
    )
    monkeypatch.setattr(
        "metis_app.engine.querying.resolve_vector_store",
        lambda _: MagicMock(
            is_available=lambda _: (True, ""),
            load=lambda _: MagicMock(),
        ),
    )

    mock_retrieval_result = MagicMock()
    mock_retrieval_result.result.context_block = "Some retrieved context."
    mock_retrieval_result.result.sources = []
    monkeypatch.setattr(
        "metis_app.engine.querying.execute_retrieval_plan",
        lambda **_: mock_retrieval_result,
    )

    with patch(
        "metis_app.engine.querying.query_swarm.__globals__[\"run_swarm_simulation\"]",
        return_value=mock_report,
        create=True,
    ):
        # Use a simpler approach: patch the import inside query_swarm
        with patch.dict("sys.modules", {
            # swarm_service is already real; patch run_swarm_simulation directly
        }):
            import metis_app.services.swarm_service as ss_mod
            orig = ss_mod.run_swarm_simulation
            ss_mod.run_swarm_simulation = lambda **_: mock_report

            try:
                req = SwarmQueryRequest(
                    manifest_path=tmp_path / "manifest.json",
                    question="What are the key debates in this document?",
                    settings={"vector_db_type": "json", "llm_provider": "openai"},
                    n_personas=2,
                    n_rounds=1,
                )
                result = __import__(
                    "metis_app.engine.querying", fromlist=["query_swarm"]
                ).query_swarm(req)
            finally:
                ss_mod.run_swarm_simulation = orig

    assert isinstance(result, SwarmQueryResult)
    assert result.selected_mode == "Simulation"
    assert "Mock summary." in result.answer_text
    assert isinstance(result.report, dict)
    assert result.run_id != ""


def test_query_swarm_raises_on_empty_question(tmp_path):
    from metis_app.engine.querying import SwarmQueryRequest, query_swarm

    import pytest
    with pytest.raises(ValueError, match="question must not be empty"):
        query_swarm(SwarmQueryRequest(
            manifest_path=tmp_path / "m.json",
            question="   ",
            settings={},
        ))


def test_swarm_query_result_selected_mode_is_simulation():
    from metis_app.engine.querying import SwarmQueryResult

    r = SwarmQueryResult(
        run_id="test-123",
        answer_text="Some answer",
        report={},
        sources=[],
    )
    assert r.selected_mode == "Simulation"
