from __future__ import annotations

import json

from metis_app.models.brain_graph import BrainGraph
from metis_app.models.session_types import SessionDetail, SessionSummary
from metis_app.services.assistant_companion import AssistantCompanionService
from metis_app.services.assistant_repository import AssistantRepository


def _session(
    session_id: str,
    *,
    title: str,
    mode: str = "Research",
    primary_skill_id: str = "qa-core",
    skill_ids: list[str] | None = None,
    index_id: str = "",
) -> SessionSummary:
    selected = list(skill_ids or [primary_skill_id])
    return SessionSummary(
        session_id=session_id,
        created_at="2026-03-08T12:00:00Z",
        updated_at="2026-03-08T13:00:00Z",
        title=title,
        summary="Short summary",
        active_profile=primary_skill_id,
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
        extra_json=json.dumps(
            {
                "skills": {
                    "selected": selected,
                    "primary": primary_skill_id,
                    "reasons": {skill_id: "test" for skill_id in selected},
                }
            }
        ),
    )


def test_brain_graph_builds_root_categories_for_empty_state() -> None:
    graph = BrainGraph().build_from_indexes_and_sessions([], [])

    assert {"category:brain", "category:indexes", "category:sessions"} <= set(graph.nodes)
    assert graph.get_node("category:brain") is not None
    assert graph.get_node("category:brain").x == 0.0
    assert graph.get_node("category:brain").y == 0.0


def test_brain_graph_links_sessions_to_indexes_modes_and_skills() -> None:
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
        _session(
            "sess-1",
            title="Read notes",
            mode="Research",
            primary_skill_id="research-claims",
            skill_ids=["research-claims", "qa-core"],
            index_id="books",
        ),
        _session(
            "sess-2",
            title="Executive recap",
            mode="Summary",
            primary_skill_id="summary-blinkist",
            skill_ids=["summary-blinkist"],
            index_id="BooksCollection",
        ),
    ]

    graph = BrainGraph().build_from_indexes_and_sessions(indexes, sessions)

    assert "index:books" in graph.nodes
    assert "session:sess-1" in graph.nodes
    assert "session:sess-2" in graph.nodes
    assert "category:mode:research" in graph.nodes
    assert "category:skill:research-claims" in graph.nodes
    assert any(
        edge.edge_type == "uses_index"
        and edge.source_id == "session:sess-1"
        and edge.target_id == "index:books"
        for edge in graph.edges
    )
    assert any(
        edge.edge_type == "category_member"
        and edge.source_id == "session:sess-1"
        and edge.target_id == "category:skill:research-claims"
        for edge in graph.edges
    )


def test_brain_graph_computes_edge_weights_from_usage_and_confidence() -> None:
    indexes = [{"index_id": "books", "collection_name": "BooksCollection"}]
    sessions = [
        _session("sess-1", title="A", index_id="books"),
        _session("sess-2", title="B", index_id="BooksCollection"),
    ]
    assistant_payload = {
        "identity": {"companion_enabled": True},
        "memory": [
            {
                "entry_id": "memory-1",
                "title": "M1",
                "summary": "S",
            }
        ],
        "brain_links": [
            {
                "source_node_id": "memory:memory-1",
                "target_node_id": "category:brain",
                "relation": "learned_from_session",
                "confidence": 0.42,
                "metadata": {"scope": "assistant_learned"},
            }
        ],
    }

    graph = BrainGraph().build_from_indexes_and_sessions(indexes, sessions, assistant_payload)
    uses_index_edge = next(
        edge
        for edge in graph.edges
        if edge.edge_type == "uses_index" and edge.target_id == "index:books"
    )
    session_mode_edge = next(
        edge
        for edge in graph.edges
        if edge.edge_type == "category_member"
        and edge.source_id == "session:sess-1"
        and edge.target_id == "category:mode:research"
    )
    learned_edge = next(
        edge
        for edge in graph.edges
        if edge.edge_type == "learned_from_session"
    )

    assert uses_index_edge.weight == 2.0
    assert session_mode_edge.weight == 2.0
    assert learned_edge.weight == 0.42


def test_brain_graph_can_preserve_positions_from_previous_graph() -> None:
    previous = BrainGraph().build_from_indexes_and_sessions([], [_session("sess-1", title="Read notes")])
    previous.nodes["session:sess-1"].x = 420.0
    previous.nodes["session:sess-1"].y = -120.0

    current = BrainGraph().build_from_indexes_and_sessions([], [_session("sess-1", title="Read notes")])
    current.copy_positions_from(previous)

    assert current.nodes["session:sess-1"].x == 420.0
    assert current.nodes["session:sess-1"].y == -120.0


def test_brain_graph_embeds_assistant_subgraph_with_metadata_and_links() -> None:
    assistant_payload = {
        "identity": {
            "assistant_id": "metis-companion",
            "name": "Guide",
            "archetype": "Research companion",
            "greeting": "Hello from the companion.",
            "companion_enabled": True,
        },
        "status": {
            "runtime_provider": "local_gguf",
            "runtime_model": "metis-q4",
            "paused": True,
            "latest_summary": "A short reflection.",
        },
        "memory": [
            {
                "entry_id": "memory-1",
                "created_at": "2026-03-08T12:30:00Z",
                "kind": "reflection",
                "title": "Learned from a completed run",
                "summary": "Captured a short next step.",
                "confidence": 0.9,
                "trigger": "completed_run",
                "session_id": "sess-1",
                "run_id": "run-1",
            }
        ],
        "playbooks": [
            {
                "playbook_id": "playbook-1",
                "created_at": "2026-03-08T12:31:00Z",
                "title": "Follow-up pattern",
                "bullets": ["Lead with the next step."],
                "source_session_id": "sess-1",
                "source_run_id": "run-1",
                "confidence": 0.8,
            }
        ],
        "brain_links": [
            {
                "source_node_id": "memory:memory-1",
                "target_node_id": "assistant:metis",
                "relation": "belongs_to",
                "label": "Belongs To",
                "summary": "Captured a short next step.",
                "confidence": 0.9,
                "metadata": {"scope": "assistant_learned", "note": "derived"},
            }
        ],
    }

    graph = BrainGraph().build_from_indexes_and_sessions([], [], assistant_payload)

    assert "category:assistant" in graph.nodes
    assert "assistant:metis" in graph.nodes
    assert "category:assistant:memory" in graph.nodes
    assert "category:assistant:playbooks" in graph.nodes
    assert graph.get_node("category:assistant").node_type == "category"
    assert graph.get_node("category:assistant").metadata["scope"] == "assistant_self"
    assert graph.get_node("category:assistant:memory").node_type == "category"
    assert graph.get_node("category:assistant:memory").metadata["category_kind"] == "assistant_memory"
    assert graph.get_node("category:assistant:memory").metadata["scope"] == "assistant_self"
    assert graph.get_node("category:assistant:memory").metadata["member_ids"] == ["memory:memory-1"]
    assert graph.get_node("category:assistant:memory").metadata["member_count"] == 1
    assert graph.get_node("category:assistant:playbooks").node_type == "category"
    assert graph.get_node("category:assistant:playbooks").metadata["category_kind"] == "assistant_playbooks"
    assert graph.get_node("category:assistant:playbooks").metadata["scope"] == "assistant_self"
    assert graph.get_node("category:assistant:playbooks").metadata["member_ids"] == ["playbook:playbook-1"]
    assert graph.get_node("category:assistant:playbooks").metadata["member_count"] == 1
    assert graph.get_node("assistant:metis").node_type == "assistant"
    assert graph.get_node("assistant:metis").metadata["scope"] == "assistant_self"
    assert graph.get_node("assistant:metis").metadata["runtime_provider"] == "local_gguf"
    assert graph.get_node("assistant:metis").metadata["runtime_model"] == "metis-q4"
    assert graph.get_node("assistant:metis").metadata["paused"] is True
    assert graph.get_node("assistant:metis").metadata["latest_summary"] == "A short reflection."
    assert graph.get_node("memory:memory-1").node_type == "memory"
    assert graph.get_node("memory:memory-1").metadata["scope"] == "assistant_learned"
    assert graph.get_node("playbook:playbook-1").node_type == "playbook"
    assert graph.get_node("playbook:playbook-1").metadata["scope"] == "assistant_self"
    assert any(
        edge.edge_type == "category_member"
        and edge.source_id == "assistant:metis"
        and edge.target_id == "category:assistant"
        and edge.metadata["scope"] == "assistant_self"
        for edge in graph.edges
    )
    assert any(
        edge.edge_type == "category_member"
        and edge.source_id == "category:assistant"
        and edge.target_id == "category:brain"
        and edge.metadata["scope"] == "assistant_self"
        for edge in graph.edges
    )
    assert any(
        edge.edge_type == "belongs_to"
        and edge.source_id == "memory:memory-1"
        and edge.target_id == "assistant:metis"
        and edge.metadata["note"] == "derived"
        and edge.metadata["scope"] == "assistant_learned"
        for edge in graph.edges
    )


def test_brain_graph_skips_assistant_subgraph_when_disabled() -> None:
    graph = BrainGraph().build_from_indexes_and_sessions(
        [],
        [],
        {"identity": {"companion_enabled": False}},
    )

    assert "category:assistant" not in graph.nodes
    assert "assistant:metis" not in graph.nodes


def test_brain_graph_carries_faculty_metadata_from_brain_pass() -> None:
    graph = BrainGraph().build_from_indexes_and_sessions(
        [
            {
                "index_id": "faculty-index",
                "brain_pass": {
                    "placement": {
                        "faculty_id": "knowledge",
                        "secondary_faculty_id": "reasoning",
                    }
                },
            }
        ],
        [],
    )

    node = graph.get_node("index:faculty-index")
    assert node is not None
    assert node.metadata["faculty_id"] == "knowledge"
    assert node.metadata["secondary_faculty_id"] == "reasoning"
    assert node.metadata["brain_pass"]["placement"]["faculty_id"] == "knowledge"


# ---------------------------------------------------------------------------
# M13 Phase 6 — assistant-scope density signal
# ---------------------------------------------------------------------------


def test_compute_assistant_density_returns_zero_for_empty_graph() -> None:
    graph = BrainGraph()
    assert graph.compute_assistant_density() == 0.0


def test_compute_assistant_density_returns_zero_when_only_workspace_nodes() -> None:
    """With no companion enabled, the graph still has root + index +
    session categories but no assistant subgraph. Density must be 0."""
    graph = BrainGraph().build_from_indexes_and_sessions(
        [{"index_id": "books"}],
        [],
        assistant_payload={"identity": {"companion_enabled": False}},
    )
    assert graph.compute_assistant_density() == 0.0


def test_compute_assistant_density_zero_without_learned_edges() -> None:
    """Reflections alone don't move density — what matters is
    *learned* cross-link edges. A companion that has produced 8
    memories but never linked any of them to a session/index sits at
    0.0 density."""
    graph = BrainGraph().build_from_indexes_and_sessions(
        [],
        [],
        assistant_payload={
            "identity": {"companion_enabled": True, "name": "Guide"},
            "memory": [
                {
                    "entry_id": f"memory-{i}",
                    "title": f"Reflection {i}",
                    "summary": "ok",
                    "kind": "reflection",
                }
                for i in range(8)
            ],
            "playbooks": [],
            "brain_links": [],
        },
    )
    assert graph.compute_assistant_density() == 0.0


def test_compute_assistant_density_grows_with_learned_cross_links() -> None:
    """Adding ``assistant_learned``-scope brain links between memories
    and the assistant raises density toward 1.0."""
    memory_payload = [
        {"entry_id": f"m{i}", "title": f"M{i}", "summary": "x", "kind": "reflection"}
        for i in range(4)
    ]
    # Sparse: 1 learned edge total over 4 artefacts → 1 / (2 * 4) = 0.125.
    sparse_links = [
        {
            "source_node_id": "memory:m0",
            "target_node_id": "assistant:metis",
            "relation": "learned_from_session",
            "summary": "first link",
            "metadata": {"scope": "assistant_learned"},
        },
    ]
    sparse = BrainGraph().build_from_indexes_and_sessions(
        [],
        [],
        assistant_payload={
            "identity": {"companion_enabled": True, "name": "Guide"},
            "memory": memory_payload,
            "playbooks": [],
            "brain_links": sparse_links,
        },
    )
    sparse_density = sparse.compute_assistant_density()
    assert sparse_density > 0.0
    assert sparse_density < 0.5

    # Dense: 2 learned edges per memory → 8 / (2 * 4) = 1.0 (cap).
    dense_links: list[dict] = []
    for i in range(4):
        dense_links.append(
            {
                "source_node_id": f"memory:m{i}",
                "target_node_id": "assistant:metis",
                "relation": "learned_from_session",
                "summary": f"link out {i}",
                "metadata": {"scope": "assistant_learned"},
            }
        )
        dense_links.append(
            {
                "source_node_id": "assistant:metis",
                "target_node_id": f"memory:m{i}",
                "relation": "remembers",
                "summary": f"link back {i}",
                "metadata": {"scope": "assistant_learned"},
            }
        )
    dense = BrainGraph().build_from_indexes_and_sessions(
        [],
        [],
        assistant_payload={
            "identity": {"companion_enabled": True, "name": "Guide"},
            "memory": memory_payload,
            "playbooks": [],
            "brain_links": dense_links,
        },
    )
    dense_density = dense.compute_assistant_density()
    assert dense_density > sparse_density
    assert dense_density == 1.0


def test_compute_assistant_density_ignores_assistant_self_edges() -> None:
    """Structural ``assistant_self``-scope edges (the
    ``category_member`` ones the subgraph builder always emits) must
    NOT count toward density. Otherwise every memory inflates the
    metric without representing real learning."""
    graph = BrainGraph().build_from_indexes_and_sessions(
        [],
        [],
        assistant_payload={
            "identity": {"companion_enabled": True, "name": "Guide"},
            "memory": [
                {"entry_id": "m0", "title": "M0", "summary": "x", "kind": "reflection"},
            ],
            "playbooks": [],
            # ``assistant_self``-scope cross-link must be ignored.
            "brain_links": [
                {
                    "source_node_id": "memory:m0",
                    "target_node_id": "assistant:metis",
                    "relation": "belongs_to",
                    "summary": "self-scope link",
                    "metadata": {"scope": "assistant_self"},
                }
            ],
        },
    )
    assert graph.compute_assistant_density() == 0.0


def test_compute_assistant_density_does_not_dilute_with_playbooks() -> None:
    """Phase 6 P2 regression (Codex review on PR #558): the current
    ``AssistantCompanionService.reflect`` codepath emits playbook
    cross-links with ``scope=assistant_self`` (the structural
    ``playbook→assistant`` belongs-to edge). If playbooks counted
    toward the artefact denominator, every playbook would lower
    density without ever raising the numerator — gating Bloom→Elder
    on a metric that *gets worse* as the companion produces more
    learning is the opposite of the intent.

    Two graphs with identical memory + identical learned cross-links;
    the second one adds 4 playbooks. Density must be unchanged."""
    memory_payload = [
        {"entry_id": f"m{i}", "title": f"M{i}", "summary": "x", "kind": "reflection"}
        for i in range(2)
    ]
    learned_links = [
        {
            "source_node_id": f"memory:m{i}",
            "target_node_id": "assistant:metis",
            "relation": "learned_from_session",
            "summary": f"link {i}",
            "metadata": {"scope": "assistant_learned"},
        }
        for i in range(2)
    ] + [
        {
            "source_node_id": "assistant:metis",
            "target_node_id": f"memory:m{i}",
            "relation": "remembers",
            "summary": f"back {i}",
            "metadata": {"scope": "assistant_learned"},
        }
        for i in range(2)
    ]

    without_playbooks = BrainGraph().build_from_indexes_and_sessions(
        [],
        [],
        assistant_payload={
            "identity": {"companion_enabled": True, "name": "Guide"},
            "memory": memory_payload,
            "playbooks": [],
            "brain_links": learned_links,
        },
    )

    with_playbooks = BrainGraph().build_from_indexes_and_sessions(
        [],
        [],
        assistant_payload={
            "identity": {"companion_enabled": True, "name": "Guide"},
            "memory": memory_payload,
            "playbooks": [
                {
                    "playbook_id": f"pb{i}",
                    "title": f"PB {i}",
                    "bullets": ["b"],
                }
                for i in range(4)
            ],
            "brain_links": learned_links
            + [
                # Mirror what reflect() emits today: structural
                # playbook→assistant ``belongs_to`` with
                # ``scope=assistant_self``. These must not contribute
                # to either side of the ratio.
                {
                    "source_node_id": f"playbook:pb{i}",
                    "target_node_id": "assistant:metis",
                    "relation": "belongs_to",
                    "summary": "structural",
                    "metadata": {"scope": "assistant_self"},
                }
                for i in range(4)
            ],
        },
    )

    baseline = without_playbooks.compute_assistant_density()
    with_pb = with_playbooks.compute_assistant_density()

    # 4 learned edges / (2 target × 2 memory artefacts) = 1.0 in both.
    assert baseline == 1.0
    assert with_pb == baseline


# ---------------------------------------------------------------------------
# M13 Phase 6 — end-to-end seam: ``reflect()`` → snapshot → density.
# ---------------------------------------------------------------------------


class _StubSessionRepo:
    """Tiny stand-in for ``SessionRepository`` exposing only ``get_session``.

    The Phase 6 density signal cares about edges sourced from the real
    ``AssistantCompanionService.reflect`` codepath; that path consults
    the session repo to find the session's bound ``index_id`` so it can
    emit a ``memory→index`` ``assistant_learned`` link. We give it just
    enough of an interface to round-trip the index_id without spinning
    up SQLite."""

    def __init__(self, sessions: dict[str, SessionSummary]) -> None:
        self._sessions = dict(sessions)

    def get_session(self, session_id: str) -> SessionDetail | None:
        summary = self._sessions.get(session_id)
        if summary is None:
            return None
        return SessionDetail(summary=summary)


def test_brain_graph_density_crosses_threshold_after_reflect_drives(
    tmp_path, monkeypatch
) -> None:
    """End-to-end Phase 6 seam: drive the *real* ``reflect()`` path
    twice across distinct sessions, build a workspace ``BrainGraph``
    from the resulting assistant snapshot, and verify
    ``compute_assistant_density`` crosses the v0 Elder threshold (0.5).

    Each ``reflect()`` produces:
      - 1 memory artefact (denominator)
      - 1 ``assistant→session`` ``assistant_learned`` link
      - 1 ``memory→index`` ``assistant_learned`` link (because the
        session has a bound ``index_id``)
      - structural ``assistant_self`` links (must NOT count)

    With 2 reflects → 2 artefacts and 4 ``assistant_learned`` edges, the
    expected density is ``min(1.0, 4 / (2 * 2))`` = ``1.0``."""

    sessions = {
        "sess-1": _session(
            "sess-1", title="First session", index_id="idx-alpha"
        ),
        "sess-2": _session(
            "sess-2", title="Second session", index_id="idx-beta"
        ),
    }
    indexes = [
        {"index_id": "idx-alpha", "collection_name": "alpha"},
        {"index_id": "idx-beta", "collection_name": "beta"},
    ]

    repo = AssistantRepository(tmp_path / "assistant_state.json")
    service = AssistantCompanionService(
        repository=repo,
        session_repo=_StubSessionRepo(sessions),
    )

    settings = {
        "assistant_identity": {
            "assistant_id": "metis-companion",
            "name": "Guide",
            "archetype": "Research companion",
            "companion_enabled": True,
        },
        "assistant_runtime": {"provider": "", "model": ""},
        "assistant_policy": {
            "reflection_enabled": True,
            "reflection_backend": "heuristic",
            "max_memory_entries": 8,
            "max_playbooks": 4,
            "max_brain_links": 32,
            "allow_automatic_writes": True,
        },
        "llm_provider": "mock",
        "llm_model": "mock-v1",
    }

    # Deterministic reflection content — we only care about the edge
    # topology, not the heuristic generator's exact wording.
    monkeypatch.setattr(
        service,
        "_generate_reflection",
        lambda *args, **kwargs: {
            "title": "Reflection",
            "summary": "A short next step.",
            "details": "Keep going.",
            "why": "A run finished.",
            "confidence": 0.8,
            "tags": [],
            "related_node_ids": [],
            "playbook_title": "",
            "playbook_bullets": [],
        },
    )

    first = service.reflect(
        trigger="completed_run",
        settings=settings,
        session_id="sess-1",
        run_id="run-1",
        force=True,
    )
    assert first["ok"] is True

    second = service.reflect(
        trigger="completed_run",
        settings=settings,
        session_id="sess-2",
        run_id="run-2",
        force=True,
    )
    assert second["ok"] is True

    snapshot = service.get_snapshot(settings)
    assistant_payload = {
        "identity": snapshot["identity"],
        "status": snapshot["status"],
        "memory": snapshot["memory"],
        "playbooks": snapshot["playbooks"],
        "brain_links": snapshot["brain_links"],
    }

    graph = BrainGraph().build_from_indexes_and_sessions(
        indexes,
        [sessions["sess-1"], sessions["sess-2"]],
        assistant_payload=assistant_payload,
    )

    # Sanity-check the seam: both memory artefacts and both index nodes
    # made it into the graph (otherwise the cross-edges would be silently
    # dropped by the ``source/target in self.nodes`` guard in
    # ``_add_assistant_subgraph``, and the density assertion below would
    # be a vacuous pass).
    memory_node_ids = [n for n in graph.nodes if n.startswith("memory:")]
    assert len(memory_node_ids) == 2, memory_node_ids
    assert "index:idx-alpha" in graph.nodes
    assert "index:idx-beta" in graph.nodes

    learned_edges = [
        edge
        for edge in graph.edges
        if isinstance(edge.metadata, dict)
        and edge.metadata.get("scope") == "assistant_learned"
    ]
    # 2 reflects × 2 learned edges each = 4 (assistant→session,
    # memory→index for each reflect).
    assert len(learned_edges) == 4, [
        (e.source_id, e.target_id, e.relation) for e in learned_edges
    ]

    density = graph.compute_assistant_density()
    assert density >= 0.5, density  # crosses the v0 Elder threshold
    assert density == 1.0  # exact: 4 learned / (2 target * 2 artefacts)
