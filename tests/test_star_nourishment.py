"""Tests for star nourishment state model + GuppyLM-inspired generators."""

from __future__ import annotations

import pytest

from metis_app.models.star_nourishment import (
    FACULTY_GAP_THRESHOLD,
    LIGHTNING_STAR_THRESHOLD,
    FacultyNourishment,
    NourishmentState,
    StarEvent,
    assistant_now_iso,
    compute_nourishment,
    hunger_label,
)
from metis_app.services.star_nourishment_gen import (
    generate_hunger_block,
    generate_hunger_expression,
    generate_star_event_reaction,
    join_sentences,
    maybe,
    pick,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FACULTIES = [
    {"id": "mathematics", "name": "Mathematics"},
    {"id": "physics", "name": "Physics"},
    {"id": "literature", "name": "Literature"},
]


def _make_stars(n: int, faculty_id: str = "mathematics") -> list[dict]:
    return [
        {"id": f"star-{i}", "primaryDomainId": faculty_id, "stage": "integrated"}
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# hunger_label
# ---------------------------------------------------------------------------

class TestHungerLabel:
    def test_zero_is_satiated(self):
        assert hunger_label(0.0) == "satiated"

    def test_one_is_starving(self):
        assert hunger_label(1.0) == "starving"

    def test_mid_is_curious(self):
        assert hunger_label(0.45) == "curious"


# ---------------------------------------------------------------------------
# StarEvent
# ---------------------------------------------------------------------------

class TestStarEvent:
    def test_roundtrip(self):
        ev = StarEvent(
            event_type="star_added",
            star_id="s1",
            faculty_id="math",
            timestamp="2025-01-01T00:00:00+00:00",
            detail="Added scroll star",
        )
        payload = ev.to_payload()
        restored = StarEvent.from_payload(payload)
        assert restored.event_type == "star_added"
        assert restored.star_id == "s1"
        assert restored.detail == "Added scroll star"

    def test_from_empty_payload(self):
        ev = StarEvent.from_payload({})
        assert ev.event_type == "star_added"
        assert ev.star_id == ""


# ---------------------------------------------------------------------------
# NourishmentState
# ---------------------------------------------------------------------------

class TestNourishmentState:
    def test_defaults(self):
        state = NourishmentState()
        assert state.hunger_level == 0.5
        assert state.total_stars == 0
        assert state.hunger_name == "curious"
        assert not state.lightning_eligible

    def test_from_payload_roundtrip(self):
        state = NourishmentState(
            hunger_level=0.8,
            total_stars=5,
            integrated_stars=3,
            lightning_eligible=False,
        )
        payload = state.to_payload()
        assert payload["hunger_name"] == "ravenous"
        assert payload["is_starving"] is False

        restored = NourishmentState.from_payload(payload)
        assert restored.hunger_level == 0.8
        assert restored.total_stars == 5

    def test_from_none_payload(self):
        state = NourishmentState.from_payload(None)
        assert state.hunger_level == 0.5

    def test_is_starving(self):
        state = NourishmentState(hunger_level=0.95)
        assert state.is_starving

    def test_has_recent_loss(self):
        state = NourishmentState(
            recent_events=[
                StarEvent("star_removed", "s1", "math", "2025-01-01T00:00:00+00:00"),
            ]
        )
        assert state.has_recent_loss

    def test_no_recent_loss_when_only_adds(self):
        state = NourishmentState(
            recent_events=[
                StarEvent("star_added", "s1", "math", "2025-01-01T00:00:00+00:00"),
            ]
        )
        assert not state.has_recent_loss


# ---------------------------------------------------------------------------
# compute_nourishment
# ---------------------------------------------------------------------------

class TestComputeNourishment:
    def test_empty_stars_maximum_hunger(self):
        state = compute_nourishment(stars=[], faculties=_FACULTIES)
        assert state.hunger_level == 1.0
        assert state.total_stars == 0
        assert state.hunger_name == "starving"

    def test_many_stars_low_hunger(self):
        stars = _make_stars(30)
        state = compute_nourishment(stars=stars, faculties=_FACULTIES)
        assert state.hunger_level < 0.3
        assert state.total_stars == 30

    def test_lightning_eligibility(self):
        stars = _make_stars(LIGHTNING_STAR_THRESHOLD)
        state = compute_nourishment(stars=stars, faculties=_FACULTIES)
        assert state.lightning_eligible

    def test_not_lightning_eligible(self):
        stars = _make_stars(LIGHTNING_STAR_THRESHOLD - 1)
        state = compute_nourishment(stars=stars, faculties=_FACULTIES)
        assert not state.lightning_eligible

    def test_faculty_gaps_detected(self):
        # Only math stars, physics and literature are gaps
        stars = _make_stars(5, faculty_id="mathematics")
        state = compute_nourishment(stars=stars, faculties=_FACULTIES)
        assert "physics" in state.faculty_gaps
        assert "literature" in state.faculty_gaps
        assert "mathematics" not in state.faculty_gaps

    def test_events_carried_forward(self):
        ev = StarEvent("star_added", "s1", "math", assistant_now_iso())
        state = compute_nourishment(stars=_make_stars(5), faculties=_FACULTIES, events=[ev])
        assert len(state.recent_events) == 1
        assert state.recent_events[0].star_id == "s1"

    def test_previous_events_merged(self):
        ev1 = StarEvent("star_added", "s1", "math", assistant_now_iso())
        ev2 = StarEvent("star_added", "s2", "math", assistant_now_iso())
        previous = NourishmentState(recent_events=[ev1])
        state = compute_nourishment(
            stars=_make_stars(5), faculties=_FACULTIES,
            previous=previous, events=[ev2],
        )
        assert len(state.recent_events) == 2


# ---------------------------------------------------------------------------
# GuppyLM-inspired generators
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_pick_returns_one(self):
        result = pick("a", "b", "c")
        assert result in {"a", "b", "c"}

    def test_maybe_returns_text_or_empty(self):
        # With chance=1.0 it always returns
        assert maybe("hello", 1.0) == "hello"
        # With chance=0.0 it never returns
        assert maybe("hello", 0.0) == ""

    def test_join_sentences_skips_empty(self):
        assert join_sentences("hello", "", "world") == "hello world"


class TestHungerExpressions:
    def test_satiated_expression(self):
        state = NourishmentState(hunger_level=0.05, total_stars=20, lightning_eligible=True)
        expr = generate_hunger_expression(state)
        assert isinstance(expr, str)
        assert len(expr) > 10

    def test_starving_expression(self):
        state = NourishmentState(hunger_level=0.95, total_stars=1)
        expr = generate_hunger_expression(state)
        assert isinstance(expr, str)
        assert len(expr) > 10

    def test_all_hunger_levels_generate(self):
        for level_name, (lo, _) in [
            ("satiated", (0.0, 0.15)),
            ("content", (0.2, 0.35)),
            ("curious", (0.4, 0.55)),
            ("hungry", (0.6, 0.75)),
            ("ravenous", (0.8, 0.90)),
            ("starving", (0.95, 1.0)),
        ]:
            state = NourishmentState(hunger_level=lo, total_stars=5)
            expr = generate_hunger_expression(state)
            assert isinstance(expr, str), f"Failed for {level_name}"


class TestHungerBlock:
    def test_block_contains_state_info(self):
        state = NourishmentState(hunger_level=0.7, total_stars=5, faculty_gaps=["physics"])
        block = generate_hunger_block(state)
        assert "Constellation Nourishment State" in block
        assert "Stars: 5" in block
        assert "Anti-sandbagging" in block
        assert "Anti-sycophancy" in block

    def test_block_mentions_lightning(self):
        state = NourishmentState(hunger_level=0.1, total_stars=15, lightning_eligible=True)
        block = generate_hunger_block(state)
        assert "ACTIVE" in block

    def test_block_mentions_recent_loss(self):
        state = NourishmentState(
            hunger_level=0.7,
            total_stars=3,
            recent_events=[
                StarEvent("star_removed", "s1", "math", "2025-01-01T00:00:00+00:00"),
            ],
        )
        block = generate_hunger_block(state)
        assert "RECENT STAR LOSS" in block


class TestStarEventReaction:
    def test_star_added_reaction(self):
        state = NourishmentState(
            hunger_level=0.3,
            total_stars=10,
            recent_events=[
                StarEvent("star_added", "s1", "math", assistant_now_iso(), "Scroll star added"),
            ],
        )
        reaction = generate_star_event_reaction(state)
        assert isinstance(reaction, str)
        assert len(reaction) > 5

    def test_star_removed_reaction(self):
        state = NourishmentState(
            hunger_level=0.8,
            total_stars=3,
            recent_events=[
                StarEvent("star_removed", "s1", "math", assistant_now_iso()),
            ],
        )
        reaction = generate_star_event_reaction(state)
        assert isinstance(reaction, str)
        assert "hunger" in reaction.lower() or "gap" in reaction.lower() or "torn" in reaction.lower() or "removed" in reaction.lower() or "lost" in reaction.lower() or "spikes" in reaction.lower()

    def test_no_events_empty_reaction(self):
        state = NourishmentState()
        assert generate_star_event_reaction(state) == ""


# ---------------------------------------------------------------------------
# Wave 2: TopologySignal + topology-nourishment fusion
# ---------------------------------------------------------------------------

from metis_app.models.star_nourishment import TopologySignal  # noqa: E402


class TestTopologySignal:
    def test_defaults(self):
        sig = TopologySignal()
        assert sig.betti_0 == 1
        assert sig.betti_1 == 0
        assert sig.scaffold_edge_count == 0
        assert sig.strongest_persistence == 0.0
        assert sig.isolated_faculties == []
        assert sig.summary == ""

    def test_roundtrip(self):
        sig = TopologySignal(
            betti_0=3,
            betti_1=2,
            scaffold_edge_count=7,
            strongest_persistence=0.85,
            isolated_faculties=["arts", "history"],
            summary="3 components, 2 loops",
        )
        payload = sig.to_payload()
        assert payload["betti_0"] == 3
        assert payload["betti_1"] == 2
        assert payload["isolated_faculties"] == ["arts", "history"]

        restored = TopologySignal.from_payload(payload)
        assert restored.betti_0 == 3
        assert restored.betti_1 == 2
        assert restored.isolated_faculties == ["arts", "history"]

    def test_from_none_payload(self):
        sig = TopologySignal.from_payload(None)
        assert sig.betti_0 == 1


class TestNourishmentTopologyIntegration:
    def test_topology_in_nourishment_state(self):
        topo = TopologySignal(betti_0=1, betti_1=1, scaffold_edge_count=5)
        state = NourishmentState(topology=topo)
        assert state.integration_loops == 1
        assert not state.is_fragmented

    def test_fragmented_state(self):
        topo = TopologySignal(betti_0=3, betti_1=0)
        state = NourishmentState(topology=topo)
        assert state.is_fragmented
        assert state.integration_loops == 0

    def test_topology_roundtrip_in_state(self):
        topo = TopologySignal(betti_0=1, betti_1=3, isolated_faculties=["arts"])
        state = NourishmentState(hunger_level=0.4, topology=topo)
        payload = state.to_payload()
        assert payload["integration_loops"] == 3
        assert payload["is_fragmented"] is False

        restored = NourishmentState.from_payload(payload)
        assert restored.topology is not None
        assert restored.topology.betti_1 == 3
        assert restored.topology.isolated_faculties == ["arts"]

    def test_compute_nourishment_with_topology_pressure(self):
        """Topology with no loops and isolated faculties should increase hunger."""
        stars = _make_stars(10, faculty_id="mathematics")
        topo_no_loops = TopologySignal(
            betti_0=2,
            betti_1=0,
            scaffold_edge_count=3,
            isolated_faculties=["physics", "literature"],
        )
        state_with_topo = compute_nourishment(
            stars=stars, faculties=_FACULTIES, topology=topo_no_loops,
        )
        state_without_topo = compute_nourishment(
            stars=stars, faculties=_FACULTIES,
        )
        # Topology pressure should make hunger higher
        assert state_with_topo.hunger_level >= state_without_topo.hunger_level

    def test_compute_nourishment_topology_none_is_safe(self):
        """Passing topology=None defaults to a neutral TopologySignal."""
        stars = _make_stars(5)
        state = compute_nourishment(stars=stars, faculties=_FACULTIES, topology=None)
        assert state.total_stars == 5
        # topology=None defaults to a neutral signal, not None
        assert state.topology.betti_0 == 1
        assert state.topology.betti_1 == 0


class TestTopologyAwareExpressions:
    def _state_with_topo(self, **topo_kwargs) -> NourishmentState:
        topo = TopologySignal(**topo_kwargs)
        return NourishmentState(
            hunger_level=0.6,
            total_stars=5,
            faculty_gaps=["physics"],
            topology=topo,
        )

    def test_expression_with_loops(self):
        state = self._state_with_topo(betti_1=3, scaffold_edge_count=5)
        expr = generate_hunger_expression(state)
        assert isinstance(expr, str)
        assert len(expr) > 10

    def test_expression_with_fragmentation(self):
        state = self._state_with_topo(betti_0=4, betti_1=0)
        expr = generate_hunger_expression(state)
        assert isinstance(expr, str)
        assert len(expr) > 10

    def test_expression_with_isolation(self):
        state = self._state_with_topo(isolated_faculties=["arts", "history"])
        expr = generate_hunger_expression(state)
        assert isinstance(expr, str)
        assert len(expr) > 10

    def test_hunger_block_includes_topology(self):
        topo = TopologySignal(
            betti_0=2, betti_1=1, scaffold_edge_count=4,
            isolated_faculties=["arts"],
        )
        state = NourishmentState(
            hunger_level=0.5, total_stars=8, topology=topo,
        )
        block = generate_hunger_block(state)
        assert "Topology:" in block
        assert "2 region(s)" in block
        assert "1 integration loop(s)" in block
        assert "Isolated faculties" in block
        assert "arts" in block

    def test_hunger_block_no_explicit_topology(self):
        """Default topology signal still appears in block (neutral values)."""
        state = NourishmentState(hunger_level=0.5, total_stars=5)
        block = generate_hunger_block(state)
        assert "Constellation Nourishment State" in block
        # Default topology (betti_0=1, betti_1=0) is still rendered
        assert "Topology:" in block
        assert "FRAGMENTED" not in block  # betti_0=1 is not fragmented

    def test_fragmented_block_includes_warning(self):
        topo = TopologySignal(betti_0=3, betti_1=0)
        state = NourishmentState(
            hunger_level=0.7, total_stars=5, topology=topo,
        )
        block = generate_hunger_block(state)
        assert "FRAGMENTED" in block

    def test_all_hunger_levels_with_topology(self):
        """All 6 hunger states generate valid expressions with topology present."""
        topo = TopologySignal(betti_0=2, betti_1=1, isolated_faculties=["arts"])
        for level in [0.05, 0.25, 0.45, 0.65, 0.85, 0.98]:
            state = NourishmentState(
                hunger_level=level, total_stars=5, topology=topo,
            )
            expr = generate_hunger_expression(state)
            assert isinstance(expr, str), f"Failed at level {level}"
            block = generate_hunger_block(state)
            assert "Topology:" in block, f"No topology at level {level}"
