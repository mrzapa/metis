from __future__ import annotations

import pathlib
import uuid
from unittest.mock import MagicMock

import pytest

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
    # emergence has 1 auto star, knowledge has 3 — emergence is sparsest
    assert faculty == "emergence"


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


def test_formulate_query_calls_llm():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="What is emergence in complex systems?")
    svc = AutonomousResearchService(web_search=MagicMock())
    query = svc.formulate_query("emergence", "Novel capability and adaptation", mock_llm)
    assert isinstance(query, str) and len(query) > 5
    mock_llm.invoke.assert_called_once()


def test_synthesize_document_returns_markdown():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(
        content="# Emergence\n\nEmergence is the arising of novel properties."
    )
    svc = AutonomousResearchService(web_search=MagicMock())
    results = [WebSearchResult(title="T", url="http://x.com", snippet="S", content="C")]
    doc = svc.synthesize_document("emergence", "What is emergence?", results, mock_llm)
    assert isinstance(doc, str) and len(doc) > 20
    mock_llm.invoke.assert_called_once()
