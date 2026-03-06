from __future__ import annotations

from axiom_app.models.session_types import EvidenceSource
from axiom_app.services.response_pipeline import (
    apply_claim_level_grounding,
    run_blinkist_summary_pipeline,
    run_tutor_pipeline,
)
from axiom_app.services.wizard_recommendation import (
    estimate_setup_cost,
    recommend_auto_settings,
)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _SequentialLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def invoke(self, _messages):
        if not self._responses:
            return _FakeResponse("")
        return _FakeResponse(self._responses.pop(0))


def _source() -> EvidenceSource:
    return EvidenceSource(
        sid="S1",
        source="notes.txt",
        title="Notes",
        snippet="Ada Lovelace wrote the first algorithm for Babbage's machine.",
        excerpt="Ada Lovelace wrote the first algorithm for Babbage's machine.",
        locator="p.1",
    )


def test_blinkist_summary_pipeline_renders_monolith_sections() -> None:
    plan_json = """
    {
      "premise": "The document argues that evidence-linked summaries improve trust.",
      "key_ideas": [{"title": "Evidence first", "what": "Ground claims in sources.", "why": "It improves trust.", "how": "Add citations.", "sources": ["S1"]}],
      "actionable_takeaways": [{"title": "Cite the answer", "steps": ["Attach citations"], "sources": ["S1"]}],
      "memorable_quotes": [{"quote": "Trust follows traceability.", "why_it_matters": "It captures the thesis.", "source_locator": "p.1", "sources": ["S1"]}],
      "key_takeaways": ["Evidence and clarity improve confidence."],
      "chapter_mini_summaries": [{"chapter": "Chapter 1", "summary": "Ground the answer.", "sources": ["S1"]}]
    }
    """
    llm = _SequentialLLM([plan_json, ""])

    result = run_blinkist_summary_pipeline(
        llm,
        query_text="Summarize the book.",
        context_block="Evidence-linked summaries improve trust.",
        sources=[_source()],
    )

    assert "1) Premise" in result.response_text
    assert "2) 10 Key Ideas" in result.response_text
    assert "6) Chapter-by-chapter mini-summaries" in result.response_text
    assert result.plan_payload["premise"].startswith("The document argues")


def test_tutor_pipeline_renders_flashcards_and_quiz() -> None:
    tutor_json = """
    {
      "lesson": {"concept": "Embeddings", "explanation": "Embeddings convert text into vectors.", "sources": ["S1"]},
      "analogies": [{"example": "Like map coordinates for meaning.", "sources": ["S1"]}],
      "socratic_questions": ["How would similar ideas cluster?"],
      "flashcards": [{"q": "What is an embedding?", "a": "A vector representation of text.", "sources": ["S1"]}],
      "quiz": {
        "questions": [{"question": "What do embeddings represent?"}],
        "answer_key": [{"answer": "Semantic meaning.", "why": "They map language into vector space.", "sources": ["S1"]}]
      }
    }
    """
    llm = _SequentialLLM([tutor_json])

    result = run_tutor_pipeline(
        llm,
        query_text="Teach me embeddings.",
        context_block="Embeddings convert text into vectors.",
        sources=[_source()],
    )

    assert "### Flashcards" in result.response_text
    assert "### Quiz" in result.response_text
    assert "Socratic Questions" in result.response_text


def test_claim_level_grounding_appends_citations() -> None:
    answer, notes = apply_claim_level_grounding(
        "The document states that Ada Lovelace wrote the first algorithm for Babbage's machine.",
        [_source()],
    )

    assert "[S1]" in answer
    assert notes


def test_wizard_recommendation_and_cost_estimation() -> None:
    rec = recommend_auto_settings()
    cost = estimate_setup_cost(
        rec,
        llm_provider="openai",
        embedding_provider="openai",
    )

    assert rec["chunk_size"] > 0
    assert rec["retrieval_k"] >= rec["final_k"]
    assert "Estimated ingestion load" in cost
