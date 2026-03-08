from __future__ import annotations

from axiom_app.models.brain_graph import BrainGraph
from axiom_app.models.session_types import SessionSummary


def _session(
    session_id: str,
    *,
    title: str,
    mode: str = "Research",
    profile: str = "Built-in: Default",
    index_id: str = "",
) -> SessionSummary:
    return SessionSummary(
        session_id=session_id,
        created_at="2026-03-08T12:00:00Z",
        updated_at="2026-03-08T13:00:00Z",
        title=title,
        summary="Short summary",
        active_profile=profile,
        mode=mode,
        index_id=index_id,
        vector_backend="json",
        llm_provider="mock",
        llm_model="mock-v1",
        embed_model="mock-embed",
        retrieve_k=5,
        final_k=3,
        mmr_lambda=0.5,
        agentic_iterations=0,
        extra_json="{}",
    )


def test_brain_graph_builds_root_categories_for_empty_state() -> None:
    graph = BrainGraph().build_from_indexes_and_sessions([], [])

    assert {"category:brain", "category:indexes", "category:sessions"} <= set(graph.nodes)
    assert graph.get_node("category:brain") is not None
    assert graph.get_node("category:brain").x == 0.0
    assert graph.get_node("category:brain").y == 0.0


def test_brain_graph_links_sessions_to_indexes_modes_and_profiles() -> None:
    indexes = [
        {
            "index_id": "books",
            "path": "indexes/books/manifest.json",
            "vector_backend": "json",
            "created_at": "2026-03-08T10:00:00Z",
            "document_count": 4,
            "chunk_count": 80,
            "collection_name": "BooksCollection",
            "source_files": ["book-a.pdf", "book-b.pdf"],
        }
    ]
    sessions = [
        _session("sess-1", title="Read notes", mode="Research", profile="Researcher", index_id="books"),
        _session("sess-2", title="Executive recap", mode="Summary", profile="Executive", index_id="BooksCollection"),
    ]

    graph = BrainGraph().build_from_indexes_and_sessions(indexes, sessions)

    assert "index:books" in graph.nodes
    assert "session:sess-1" in graph.nodes
    assert "session:sess-2" in graph.nodes
    assert "category:mode:research" in graph.nodes
    assert "category:profile:researcher" in graph.nodes
    assert any(
        edge.edge_type == "uses_index"
        and edge.source_id == "session:sess-1"
        and edge.target_id == "index:books"
        for edge in graph.edges
    )
    assert any(
        edge.edge_type == "uses_index"
        and edge.source_id == "session:sess-2"
        and edge.target_id == "index:books"
        for edge in graph.edges
    )


def test_brain_graph_can_preserve_positions_from_previous_graph() -> None:
    previous = BrainGraph().build_from_indexes_and_sessions([], [_session("sess-1", title="Read notes")])
    previous.nodes["session:sess-1"].x = 420.0
    previous.nodes["session:sess-1"].y = -120.0

    current = BrainGraph().build_from_indexes_and_sessions([], [_session("sess-1", title="Read notes")])
    current.copy_positions_from(previous)

    assert current.nodes["session:sess-1"].x == 420.0
    assert current.nodes["session:sess-1"].y == -120.0
