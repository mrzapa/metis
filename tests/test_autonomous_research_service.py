from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from metis_app.services.autonomous_research_service import AutonomousResearchService
from metis_app.utils.web_search import WebSearchResult


MOCK_INDEXES = [
    {"index_id": "auto_knowledge_abc", "document_count": 3},
    {"index_id": "auto_emergence_xyz", "document_count": 1},
    {"index_id": "user_strategy_001",  "document_count": 5},
]


def test_scan_faculty_gaps_returns_sparsest_faculty():
    svc = AutonomousResearchService(web_search=MagicMock())
    faculty = svc.scan_faculty_gaps(MOCK_INDEXES)
    # Both knowledge and emergence each have 1 auto index (stars counted by index, not document_count).
    # They tie at count=1; tie-break uses FACULTY_ORDER position → knowledge (index 1) < emergence (index 10).
    assert faculty == "knowledge"


def test_scan_faculty_gaps_returns_unrepresented_faculty_first():
    svc = AutonomousResearchService(web_search=MagicMock())
    # no auto_ indexes at all → pick first faculty in the list
    faculty = svc.scan_faculty_gaps([{"index_id": "user_manual", "document_count": 10}])
    assert faculty == "perception"  # first faculty in FACULTY_ORDER


def test_scan_faculty_gaps_returns_none_when_all_faculties_have_enough_stars():
    svc = AutonomousResearchService(web_search=MagicMock())
    # 3+ stars per faculty → no gap
    many = [
        {"index_id": f"auto_{fac}_{i}", "document_count": 1}
        for fac in ["perception", "knowledge", "memory", "reasoning", "skills",
                    "strategy", "personality", "values", "synthesis", "autonomy", "emergence"]
        for i in range(3)
    ]
    result = svc.scan_faculty_gaps(many)
    assert result is None


def test_save_temp_document_writes_file(tmp_path):
    svc = AutonomousResearchService(web_search=MagicMock(), temp_dir=tmp_path)
    content = "# Test\nSome content."
    path = svc.save_temp_document(content, "reasoning")
    assert path.exists()
    assert "auto_research_reasoning_" in path.name
    assert path.read_text(encoding="utf-8") == content


def test_formulate_query_calls_llm(monkeypatch):
    import sys
    import types

    fake_langchain_core = types.ModuleType("langchain_core")
    fake_langchain_core_messages = types.ModuleType("langchain_core.messages")
    fake_langchain_core_messages.HumanMessage = lambda content: {"role": "user", "content": content}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_core", fake_langchain_core)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", fake_langchain_core_messages)

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="What is emergence in complex systems?")
    svc = AutonomousResearchService(web_search=MagicMock())
    query = svc.formulate_query("emergence", "Novel capability and adaptation", mock_llm)
    assert isinstance(query, str) and len(query) > 5
    mock_llm.invoke.assert_called_once()


def test_synthesize_document_returns_markdown(monkeypatch):
    import sys
    import types

    fake_langchain_core = types.ModuleType("langchain_core")
    fake_langchain_core_messages = types.ModuleType("langchain_core.messages")
    fake_langchain_core_messages.HumanMessage = lambda content: {"role": "user", "content": content}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_core", fake_langchain_core)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", fake_langchain_core_messages)

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(
        content="# Emergence\n\nEmergence is the arising of novel properties."
    )
    svc = AutonomousResearchService(web_search=MagicMock())
    results = [WebSearchResult(title="T", url="http://x.com", snippet="S", content="C")]
    doc = svc.synthesize_document("emergence", "What is emergence?", results, mock_llm)
    assert isinstance(doc, str) and len(doc) > 20
    mock_llm.invoke.assert_called_once()


def test_run_returns_none_when_no_faculty_gaps():
    """run() should return None when scan_faculty_gaps returns None."""
    svc = AutonomousResearchService(web_search=MagicMock())
    # 3 auto indexes per faculty → no gaps
    indexes = [
        {"index_id": f"auto_{fac}_{i}", "document_count": 1}
        for fac in ["perception", "knowledge", "memory", "reasoning", "skills",
                    "strategy", "personality", "values", "synthesis", "autonomy", "emergence"]
        for i in range(3)
    ]
    result = svc.run(settings={}, indexes=indexes, orchestrator=MagicMock())
    assert result is None


def test_run_returns_none_when_web_search_empty(monkeypatch):
    """run() should return None when web search returns no results."""
    import sys
    import types

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="search query")

    fake_llm_providers = types.ModuleType("metis_app.utils.llm_providers")
    fake_llm_providers.create_llm = lambda s: mock_llm
    monkeypatch.setitem(sys.modules, "metis_app.utils.llm_providers", fake_llm_providers)

    empty_search = MagicMock(return_value=[])
    svc = AutonomousResearchService(web_search=empty_search)
    result = svc.run(settings={}, indexes=[], orchestrator=MagicMock())
    assert result is None


def test_scan_faculty_gaps_uses_demand_scores_for_ordering():
    """High-demand faculty with zero indexes should be prioritised over low-demand."""
    svc = AutonomousResearchService(web_search=MagicMock())
    # reasoning (index 3 in FACULTY_ORDER) has no auto-indexes
    # perception (index 0) has no auto-indexes
    # If reasoning has higher demand, it should come first
    indexes = []  # all faculties have zero coverage
    demand_scores = {"perception": 1, "reasoning": 5}  # reasoning is in higher demand
    faculty = svc.scan_faculty_gaps(indexes, demand_scores=demand_scores)
    assert faculty == "reasoning"


def test_scan_faculty_gaps_falls_back_to_faculty_order_without_demand_scores():
    """Without demand_scores, original tie-break by FACULTY_ORDER still applies."""
    svc = AutonomousResearchService(web_search=MagicMock())
    indexes = []
    faculty = svc.scan_faculty_gaps(indexes)
    assert faculty == "perception"  # first in FACULTY_ORDER


def test_scan_faculty_gaps_counts_indexes_not_documents():
    """Each auto_ index should count as 1 star regardless of document_count."""
    svc = AutonomousResearchService(web_search=MagicMock())
    # One auto_perception index with 100 documents should still count as 1 star
    indexes = [{"index_id": "auto_perception_abc", "document_count": 100}]
    faculty = svc.scan_faculty_gaps(indexes)
    # With the fix: perception = 1 star (not 100), below threshold of 3.
    # perception is the only faculty in sparse_represented (0 < 1 < 3).
    # All other faculties are unrepresented (0), which do NOT appear in sparse_represented,
    # so the first pass returns perception as the sole sparse-but-started faculty.
    # This proves document_count is ignored — if it were counted, perception would be 100
    # and well above the threshold, causing a different faculty to be returned.
    assert faculty == "perception"


def test_run_batch_returns_list_of_results():
    """run_batch calls run() once per faculty gap up to concurrency limit."""
    svc = AutonomousResearchService(web_search=MagicMock())
    svc.run = MagicMock(return_value={"faculty_id": "perception", "index_id": "x"})

    # Simulate 2 gaps with concurrency=2
    results = asyncio.run(
        svc.run_batch(
            faculty_ids=["perception", "memory"],
            settings={},
            orchestrator=MagicMock(),
            concurrency=2,
            request_delay_ms=0,
        )
    )
    assert len(results) == 2


def test_run_emits_scanning_phase_via_progress_cb():
    """run() calls progress_cb with phase='scanning' before any other phase."""
    svc = AutonomousResearchService(web_search=MagicMock())
    # No faculty gaps → only the scanning event fires, then skipped.
    indexes = [
        {"index_id": f"auto_{fac}_{i}", "document_count": 1}
        for fac in ["perception", "knowledge", "memory", "reasoning", "skills",
                    "strategy", "personality", "values", "synthesis", "autonomy", "emergence"]
        for i in range(3)
    ]
    events: list[dict] = []
    svc.run(settings={}, indexes=indexes, orchestrator=MagicMock(), progress_cb=events.append)
    phases = [e["phase"] for e in events]
    assert "scanning" in phases
    assert phases[0] == "scanning"


def test_run_emits_skipped_phase_when_no_gaps():
    """run() emits phase='skipped' when scan_faculty_gaps returns None."""
    svc = AutonomousResearchService(web_search=MagicMock())
    indexes = [
        {"index_id": f"auto_{fac}_{i}", "document_count": 1}
        for fac in ["perception", "knowledge", "memory", "reasoning", "skills",
                    "strategy", "personality", "values", "synthesis", "autonomy", "emergence"]
        for i in range(3)
    ]
    events: list[dict] = []
    svc.run(settings={}, indexes=indexes, orchestrator=MagicMock(), progress_cb=events.append)
    phases = [e["phase"] for e in events]
    assert "skipped" in phases


def test_run_progress_cb_receives_all_required_keys():
    """Every progress_cb event must contain phase, faculty_id, and detail."""
    svc = AutonomousResearchService(web_search=MagicMock())
    events: list[dict] = []
    svc.run(settings={}, indexes=[], orchestrator=MagicMock(), progress_cb=events.append)
    for event in events:
        assert "phase" in event, f"Missing 'phase' in {event}"
        assert "detail" in event, f"Missing 'detail' in {event}"
        assert "faculty_id" in event, f"Missing 'faculty_id' in {event}"


def test_run_batch_threads_progress_cb_to_run():
    """run_batch passes progress_cb to each run() invocation."""
    collected: list[dict] = []

    svc = AutonomousResearchService(web_search=MagicMock())

    def fake_run(**kwargs):  # noqa: ANN202
        cb = kwargs.get("progress_cb")
        if cb:
            cb({"phase": "scanning", "faculty_id": None, "detail": "test"})
        return None

    svc.run = fake_run  # type: ignore[method-assign]

    asyncio.run(
        svc.run_batch(
            faculty_ids=["perception"],
            settings={},
            orchestrator=MagicMock(),
            concurrency=1,
            request_delay_ms=0,
            progress_cb=collected.append,
        )
    )
    assert any(e["phase"] == "scanning" for e in collected)


def test_run_with_target_faculty_id_skips_scan():
    """run() with target_faculty_id bypasses scan_faculty_gaps and uses the supplied faculty."""
    svc = AutonomousResearchService(web_search=MagicMock())

    scan_called = []
    original_scan = svc.scan_faculty_gaps
    def capturing_scan(*args, **kwargs):
        scan_called.append(True)
        return original_scan(*args, **kwargs)
    svc.scan_faculty_gaps = capturing_scan  # type: ignore[method-assign]

    # All faculties fully covered → normally scan returns None and run() exits early.
    # With target_faculty_id, run() should skip the scan entirely and proceed to query.
    fully_covered = [
        {"index_id": f"auto_{fac}_{i}", "document_count": 1}
        for fac in ["perception", "knowledge", "memory", "reasoning", "skills",
                    "strategy", "personality", "values", "synthesis", "autonomy", "emergence"]
        for i in range(3)
    ]

    events: list[dict] = []
    # run() will try to create LLM — patch it to bail at formulation
    import sys, types
    fake_lp = types.ModuleType("metis_app.utils.llm_providers")
    fake_lp.create_llm = lambda s: MagicMock(invoke=MagicMock(return_value=MagicMock(content="")))
    original = sys.modules.get("metis_app.utils.llm_providers")
    sys.modules["metis_app.utils.llm_providers"] = fake_lp
    try:
        svc.run(
            settings={},
            indexes=fully_covered,
            orchestrator=MagicMock(),
            target_faculty_id="reasoning",
            progress_cb=events.append,
        )
    finally:
        if original is None:
            sys.modules.pop("metis_app.utils.llm_providers", None)
        else:
            sys.modules["metis_app.utils.llm_providers"] = original

    # Scan was NOT called
    assert not scan_called, "scan_faculty_gaps should be skipped when target_faculty_id is set"
    # The formulating event should mention "reasoning"
    formulating = [e for e in events if e["phase"] == "formulating"]
    assert formulating, "Expected a formulating event"
    assert formulating[0]["faculty_id"] == "reasoning"


def test_compute_demand_scores_counts_user_indexes_per_faculty():
    """Non-auto indexes with brain_pass.placement.faculty_id increment demand."""
    svc = AutonomousResearchService(web_search=MagicMock())
    indexes = [
        {
            "index_id": "user_doc_1",
            "brain_pass": {"placement": {"faculty_id": "reasoning"}},
        },
        {
            "index_id": "user_doc_2",
            "brain_pass": {"placement": {"faculty_id": "reasoning"}},
        },
        {
            "index_id": "user_doc_3",
            "brain_pass": {"placement": {"faculty_id": "knowledge"}},
        },
        # auto_ indexes should not count toward demand
        {
            "index_id": "auto_reasoning_abc",
            "brain_pass": {"placement": {"faculty_id": "reasoning"}},
        },
    ]
    scores = svc.compute_demand_scores(indexes)
    assert scores["reasoning"] == 2
    assert scores["knowledge"] == 1
    assert scores.get("perception", 0) == 0


def test_compute_demand_scores_ignores_missing_placement():
    """Indexes without brain_pass.placement.faculty_id are skipped."""
    svc = AutonomousResearchService(web_search=MagicMock())
    indexes = [
        {"index_id": "user_doc_no_faculty", "brain_pass": {}},
        {"index_id": "user_doc_no_brain_pass"},
        {"index_id": "user_doc_valid", "brain_pass": {"placement": {"faculty_id": "memory"}}},
    ]
    scores = svc.compute_demand_scores(indexes)
    assert scores.get("memory", 0) == 1
    assert len([v for v in scores.values() if v > 0]) == 1


def test_compute_demand_scores_returns_empty_for_no_user_indexes():
    """Returns empty dict when no user-placed indexes exist."""
    svc = AutonomousResearchService(web_search=MagicMock())
    scores = svc.compute_demand_scores([])
    assert scores == {}


def test_run_passes_demand_scores_to_scan_faculty_gaps():
    """run() computes demand scores and passes them to scan_faculty_gaps."""
    svc = AutonomousResearchService(web_search=MagicMock())

    captured: dict = {}

    original_scan = svc.scan_faculty_gaps

    def capturing_scan(indexes, demand_scores=None):
        captured["demand_scores"] = demand_scores
        return original_scan(indexes, demand_scores=demand_scores)

    svc.scan_faculty_gaps = capturing_scan  # type: ignore[method-assign]

    # One user index assigned to "reasoning" → demand_scores={"reasoning": 1}
    indexes = [
        {"index_id": "user_doc_1", "brain_pass": {"placement": {"faculty_id": "reasoning"}}},
    ]
    # run() will try to create an LLM — patch llm_providers to avoid real calls
    import sys, types
    fake_lp = types.ModuleType("metis_app.utils.llm_providers")
    fake_lp.create_llm = lambda s: MagicMock(invoke=MagicMock(return_value=MagicMock(content="query")))
    original = sys.modules.get("metis_app.utils.llm_providers")
    sys.modules["metis_app.utils.llm_providers"] = fake_lp
    try:
        svc.run(settings={}, indexes=indexes, orchestrator=MagicMock())
    finally:
        if original is None:
            sys.modules.pop("metis_app.utils.llm_providers", None)
        else:
            sys.modules["metis_app.utils.llm_providers"] = original

    assert captured.get("demand_scores") == {"reasoning": 1}


def test_reverse_curriculum_prefers_high_demand_unrepresented_faculty():
    """End-to-end: compute_demand_scores + scan_faculty_gaps together."""
    svc = AutonomousResearchService(web_search=MagicMock())

    # User has uploaded 5 indexes tagged to "emergence", none to "perception".
    # Without demand scores: perception is first (FACULTY_ORDER index 0).
    # With demand scores: emergence has demand=5, perception has demand=0
    #   → emergence should be returned first.
    indexes = [
        {"index_id": f"user_doc_{i}", "brain_pass": {"placement": {"faculty_id": "emergence"}}}
        for i in range(5)
    ]
    # No auto_ indexes at all → all faculties are unrepresented

    # Baseline: without demand, perception (index 0) wins
    baseline = svc.scan_faculty_gaps(indexes)
    assert baseline == "perception"

    # With demand scores computed from same indexes:
    demand = svc.compute_demand_scores(indexes)
    assert demand == {"emergence": 5}
    result = svc.scan_faculty_gaps(indexes, demand_scores=demand)
    assert result == "emergence"


def test_sparse_represented_beats_unrepresented_regardless_of_demand():
    """Partially-covered faculty (sparse_represented) always wins over zero-coverage faculty.

    scan_faculty_gaps has two passes: first it returns the sparsest partially-covered
    faculty (0 < stars < threshold); only if none exist does it fall back to the
    first unrepresented faculty (stars == 0). The demand/hardness sort applies
    within each pass, but a faculty in pass-1 always beats one in pass-2.
    """
    svc = AutonomousResearchService(web_search=MagicMock())

    # reasoning: 1 auto-star → enters sparse_represented (pass 1)
    # emergence: 0 auto-stars → enters unrepresented (pass 2)
    # Both have equal demand=5, but reasoning wins because pass 1 has priority.
    indexes = [{"index_id": "auto_reasoning_abc", "document_count": 1}]
    demand = {"reasoning": 5, "emergence": 5}
    result = svc.scan_faculty_gaps(indexes, demand_scores=demand)
    assert result == "reasoning"


def test_run_scanning_event_fires_with_nonempty_detail():
    """run() emits a 'scanning' progress event with a non-empty detail string."""
    svc = AutonomousResearchService(web_search=MagicMock())
    # All faculties fully covered → only 'scanning' and 'skipped' events fire
    indexes = [
        {"index_id": f"auto_{fac}_{i}", "document_count": 1}
        for fac in ["perception", "knowledge", "memory", "reasoning", "skills",
                    "strategy", "personality", "values", "synthesis", "autonomy", "emergence"]
        for i in range(3)
    ] + [
        # Add 2 user indexes with faculty placement to generate non-zero demand
        {"index_id": "user_1", "brain_pass": {"placement": {"faculty_id": "reasoning"}}},
        {"index_id": "user_2", "brain_pass": {"placement": {"faculty_id": "reasoning"}}},
    ]
    events: list[dict] = []
    svc.run(settings={}, indexes=indexes, orchestrator=MagicMock(), progress_cb=events.append)
    scanning_events = [e for e in events if e["phase"] == "scanning"]
    assert scanning_events, "No scanning event emitted"
    # The detail should mention demand signals when present
    detail = scanning_events[0]["detail"]
    assert isinstance(detail, str) and len(detail) > 0


def test_run_batch_passes_target_faculty_id_to_each_run():
    """run_batch must pass the correct target_faculty_id to each run() call."""
    import asyncio as _asyncio
    svc = AutonomousResearchService(web_search=MagicMock())

    received_faculty_ids: list[str] = []

    def capturing_run(**kwargs):
        fid = kwargs.get("target_faculty_id")
        if fid:
            received_faculty_ids.append(fid)
        return {"faculty_id": fid, "index_id": f"auto_{fid}_x"}

    svc.run = capturing_run  # type: ignore[method-assign]

    _asyncio.run(
        svc.run_batch(
            faculty_ids=["reasoning", "memory", "emergence"],
            settings={},
            orchestrator=MagicMock(),
            concurrency=3,
            request_delay_ms=0,
        )
    )

    assert sorted(received_faculty_ids) == ["emergence", "memory", "reasoning"]


def test_run_batch_respects_semaphore_concurrency():
    """run_batch serialises tasks correctly under concurrency=1."""
    import asyncio as _asyncio
    import threading

    svc = AutonomousResearchService(web_search=MagicMock())
    concurrent_count = [0]
    max_concurrent = [0]
    lock = threading.Lock()

    def slow_run(**kwargs):
        import time
        with lock:
            concurrent_count[0] += 1
            max_concurrent[0] = max(max_concurrent[0], concurrent_count[0])
        time.sleep(0.02)
        with lock:
            concurrent_count[0] -= 1
        return {"faculty_id": kwargs.get("target_faculty_id"), "index_id": "x"}

    svc.run = slow_run  # type: ignore[method-assign]

    _asyncio.run(
        svc.run_batch(
            faculty_ids=["perception", "knowledge", "memory"],
            settings={},
            orchestrator=MagicMock(),
            concurrency=1,
            request_delay_ms=0,
        )
    )

    assert max_concurrent[0] == 1, f"Expected max 1 concurrent, got {max_concurrent[0]}"
