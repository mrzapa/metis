"""Tests for glossary-based query expansion in the retrieval pipeline.

These tests target ``apply_glossary_expansion`` directly so they have no
dependency on real embeddings, vector backends, or LLMs.
"""

from __future__ import annotations

from metis_app.services.retrieval_pipeline import apply_glossary_expansion


def test_no_glossary_returns_question_unchanged() -> None:
    expanded, matches = apply_glossary_expansion("What is GDPR?", {})
    assert expanded == "What is GDPR?"
    assert matches == []


def test_term_match_appends_synonyms() -> None:
    settings = {
        "glossary": {
            "GDPR": ["General Data Protection Regulation", "EU privacy law"],
        }
    }
    expanded, matches = apply_glossary_expansion("Tell me about GDPR penalties.", settings)
    assert "Tell me about GDPR penalties." in expanded
    assert "General Data Protection Regulation" in expanded
    assert "EU privacy law" in expanded
    assert matches == [
        ("GDPR", ["General Data Protection Regulation", "EU privacy law"])
    ]


def test_synonym_match_adds_canonical_term() -> None:
    settings = {
        "glossary": {
            "GDPR": ["General Data Protection Regulation"],
        }
    }
    # User typed the long form — should add the acronym.
    expanded, matches = apply_glossary_expansion(
        "What does General Data Protection Regulation cover?", settings
    )
    assert "GDPR" in expanded
    # Original synonym is already in the question; should NOT be re-appended.
    assert expanded.count("General Data Protection Regulation") == 1
    assert matches[0][0] == "GDPR"
    assert "GDPR" in matches[0][1]


def test_no_match_returns_unchanged() -> None:
    settings = {"glossary": {"GDPR": ["EU regulation"]}}
    expanded, matches = apply_glossary_expansion("What is the weather today?", settings)
    assert expanded == "What is the weather today?"
    assert matches == []


def test_match_is_case_insensitive() -> None:
    settings = {"glossary": {"GDPR": ["EU privacy law"]}}
    expanded, matches = apply_glossary_expansion("the gdpr in detail", settings)
    assert "EU privacy law" in expanded
    assert matches and matches[0][0] == "GDPR"


def test_partial_word_does_not_match() -> None:
    """Word boundaries: 'Apple' in glossary should not match 'pineapple'."""
    settings = {"glossary": {"Apple": ["AAPL", "Apple Inc."]}}
    expanded, matches = apply_glossary_expansion("I love pineapple cake.", settings)
    assert expanded == "I love pineapple cake."
    assert matches == []


def test_multiple_matches_are_deduped_across_terms() -> None:
    settings = {
        "glossary": {
            "AI": ["artificial intelligence", "machine intelligence"],
            "ML": ["machine learning", "machine intelligence"],  # shared synonym
        }
    }
    expanded, matches = apply_glossary_expansion("AI vs ML?", settings)
    # "machine intelligence" appears in both lists but should only be added once.
    assert expanded.count("machine intelligence") == 1
    assert {m[0] for m in matches} == {"AI", "ML"}


def test_empty_synonym_list_is_safe() -> None:
    settings = {"glossary": {"FOO": []}}
    expanded, matches = apply_glossary_expansion("FOO matters", settings)
    # Term matches but no synonyms to add → original returned, no audit entry.
    assert expanded == "FOO matters"
    assert matches == []


def test_malformed_glossary_is_ignored() -> None:
    settings = {"glossary": "not a dict"}  # type: ignore[dict-item]
    expanded, matches = apply_glossary_expansion("anything", settings)
    assert expanded == "anything"
    assert matches == []
