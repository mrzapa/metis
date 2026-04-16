from __future__ import annotations

import json

from metis_app.utils.knowledge_graph import (
    KnowledgeGraph,
    build_knowledge_graph,
    collect_graph_chunk_candidates,
    extract_query_entities,
    llm_extract_entities_and_relations,
    traverse_graph,
)


class _ScriptedLLM:
    """Minimal LangChain-shaped stub: returns scripted responses in order."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict]] = []

    def invoke(self, messages):
        self.calls.append(messages)
        if not self._responses:
            raise RuntimeError("ScriptedLLM exhausted")
        payload = self._responses.pop(0)
        return type("R", (), {"content": payload})()


def test_build_knowledge_graph_returns_entity_chunk_reverse_index() -> None:
    chunks = [
        "Ada Lovelace wrote notes about Charles Babbage.",
        "Charles Babbage designed the Analytical Engine.",
    ]

    graph, entity_to_chunks = build_knowledge_graph(chunks)

    assert isinstance(graph, KnowledgeGraph)
    assert "ada lovelace" in entity_to_chunks
    assert entity_to_chunks["ada lovelace"] == {0}
    assert "charles babbage" in entity_to_chunks
    assert entity_to_chunks["charles babbage"] == {0, 1}


def test_traverse_graph_respects_depth_limit() -> None:
    graph = KnowledgeGraph()
    graph.add_edge("alpha", "links", "beta")
    graph.add_edge("beta", "links", "gamma")

    depth_1 = traverse_graph(graph, "alpha", depth=1)
    depth_2 = traverse_graph(graph, "alpha", depth=2)

    assert depth_1 == ["alpha", "beta"]
    assert depth_2 == ["alpha", "beta", "gamma"]


def test_collect_graph_chunk_candidates_bypass_mode_skips_graph() -> None:
    graph = KnowledgeGraph()
    graph.add_edge("ada", "knows", "charles")

    out = collect_graph_chunk_candidates(
        graph=graph,
        entity_to_chunks={"ada": {1}, "charles": {2}},
        question="Tell me about Ada",
        mode="bypass",
        limit=5,
    )

    assert out == []


def test_extract_query_entities_falls_back_to_keywords() -> None:
    # no title-cased entities -> fallback keyword extraction should still work
    entities = extract_query_entities("what does recursion mean in algorithms")
    assert entities
    assert "recursion" in entities


def test_knowledge_graph_to_dict_round_trips() -> None:
    graph = KnowledgeGraph()
    graph.add_node("python", entity_type="LANGUAGE")
    graph.add_edge("python", "implements", "function")

    data = graph.to_dict()
    restored = KnowledgeGraph.from_dict(data)

    assert "python" in restored.nodes
    assert restored.nodes["python"]["type"] == "LANGUAGE"
    assert "function" in restored.edges.get("python", {})
    assert "implements" in restored.edges["python"]["function"]


def test_build_knowledge_graph_without_spacy_uses_heuristic() -> None:
    chunks = ["Alan Turing invented the Turing Machine."]
    graph, entity_to_chunks = build_knowledge_graph(chunks, use_spacy=False)

    assert isinstance(graph, KnowledgeGraph)
    # Rule-based extractor should find at least one proper-noun entity
    assert len(graph.nodes) > 0


# ---------------------------------------------------------------------------
# Description merging on KnowledgeGraph.add_node
# ---------------------------------------------------------------------------


def test_add_node_merges_descriptions_dedupes_and_caps_length() -> None:
    graph = KnowledgeGraph()
    graph.add_node("Apple Inc.", entity_type="ORG", description="Tech company.")
    graph.add_node("apple inc", entity_type="ORG", description="Tech company.")  # dup
    graph.add_node("APPLE INC", entity_type="ORG", description="Designs the iPhone.")

    node = graph.nodes["apple inc"]
    assert node["type"] == "ORG"
    # Both unique descriptions present, separated by " | "
    parts = [p.strip() for p in node["description"].split("|")]
    assert "Tech company." in parts
    assert "Designs the iPhone." in parts
    # Duplicate should not have been added a second time.
    assert sum(1 for p in parts if p == "Tech company.") == 1


def test_add_node_promotes_specific_type_over_generic() -> None:
    graph = KnowledgeGraph()
    graph.add_node("Alice", entity_type="ENTITY")
    graph.add_node("Alice", entity_type="PERSON")
    assert graph.nodes["alice"]["type"] == "PERSON"


# ---------------------------------------------------------------------------
# Gleaning (multi-pass LLM extraction)
# ---------------------------------------------------------------------------


def test_llm_extract_returns_descriptions_when_requested() -> None:
    payload = json.dumps({
        "entities": [
            {"type": "ORG", "text": "Apple", "description": "iPhone maker."},
        ],
        "relations": [],
    })
    llm = _ScriptedLLM([payload])
    entities, _ = llm_extract_entities_and_relations(
        "Apple makes the iPhone.", llm, return_descriptions=True
    )
    assert entities == [("ORG", "apple", "iPhone maker.")]


def test_llm_extract_gleaning_adds_missed_entities() -> None:
    pass1 = json.dumps({
        "entities": [{"type": "ORG", "text": "Apple"}],
        "relations": [],
    })
    pass2 = json.dumps({
        "entities": [{"type": "PERSON", "text": "Tim Cook"}],
        "relations": [],
    })
    llm = _ScriptedLLM([pass1, pass2])
    entities, _ = llm_extract_entities_and_relations(
        "Apple's CEO Tim Cook spoke.", llm, max_passes=2
    )
    names = {name for _, name in entities}
    assert names == {"apple", "tim cook"}
    # Both passes ran — gleaning surfaced the missed PERSON.
    assert len(llm.calls) == 2


def test_llm_extract_gleaning_converges_when_no_new_entities() -> None:
    pass1 = json.dumps({
        "entities": [{"type": "ORG", "text": "Apple"}],
        "relations": [],
    })
    # Second pass returns the same entity (already seen) → loop should stop.
    pass2 = json.dumps({
        "entities": [{"type": "ORG", "text": "apple"}],
        "relations": [],
    })
    llm = _ScriptedLLM([pass1, pass2, "should-not-be-called"])
    entities, _ = llm_extract_entities_and_relations(
        "Apple makes phones.", llm, max_passes=5
    )
    assert {name for _, name in entities} == {"apple"}
    # Exactly two calls — the third is never made because pass 2 added nothing.
    assert len(llm.calls) == 2


def test_llm_extract_falls_back_to_heuristic_on_error() -> None:
    class _BadLLM:
        def invoke(self, _messages):
            raise RuntimeError("network down")

    entities, _ = llm_extract_entities_and_relations(
        "Ada Lovelace met Charles Babbage.", _BadLLM()
    )
    # Heuristic fallback should still find proper-noun entities.
    assert any("ada" in name.lower() for _, name in entities)
