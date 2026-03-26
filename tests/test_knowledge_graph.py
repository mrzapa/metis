from __future__ import annotations

from metis_app.utils.knowledge_graph import (
    KnowledgeGraph,
    build_knowledge_graph,
    collect_graph_chunk_candidates,
    extract_query_entities,
    traverse_graph,
)


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
