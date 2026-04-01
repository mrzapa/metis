from __future__ import annotations

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
