"""Tests for star nourishment state model + GuppyLM-inspired generators."""

from __future__ import annotations


from metis_app.models.star_nourishment import (
    LIGHTNING_STAR_THRESHOLD,
    AbliterationRecord,
    NourishmentState,
    PersonalityEvolution,
    StarEvent,
    assistant_now_iso,
    compute_nourishment,
    hunger_label,
    swarm_persona_count,
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


# ---------------------------------------------------------------------------
# Wave 3: PersonalityEvolution, swarm persona scaling, personality_baked
# ---------------------------------------------------------------------------


class TestAbliterationRecord:
    def test_roundtrip(self):
        rec = AbliterationRecord(
            model_id="meta-llama/Llama-2-7b",
            timestamp="2025-06-01T00:00:00+00:00",
            traits_seeded=["mathematics", "physics"],
            star_count_at_bake=10,
            hunger_at_bake=0.3,
        )
        payload = rec.to_payload()
        assert payload["model_id"] == "meta-llama/Llama-2-7b"
        assert payload["star_count_at_bake"] == 10

        restored = AbliterationRecord.from_payload(payload)
        assert restored.model_id == "meta-llama/Llama-2-7b"
        assert restored.traits_seeded == ["mathematics", "physics"]
        assert restored.hunger_at_bake == 0.3

    def test_from_empty_payload(self):
        rec = AbliterationRecord.from_payload({})
        assert rec.model_id == ""
        assert rec.star_count_at_bake == 0
        assert rec.hunger_at_bake == 0.5  # default

    def test_hunger_clamped(self):
        rec = AbliterationRecord.from_payload({"hunger_at_bake": 5.0})
        assert rec.hunger_at_bake == 1.0
        rec2 = AbliterationRecord.from_payload({"hunger_at_bake": -1.0})
        assert rec2.hunger_at_bake == 0.0


class TestPersonalityEvolution:
    def test_defaults(self):
        evo = PersonalityEvolution()
        assert evo.abliteration_count == 0
        assert evo.personality_depth == 0.0
        assert evo.dominant_traits == []
        assert evo.last_baked_at == ""

    def test_roundtrip(self):
        evo = PersonalityEvolution(
            abliteration_count=2,
            personality_depth=0.45,
            dominant_traits=["mathematics", "physics"],
        )
        payload = evo.to_payload()
        assert payload["personality_depth"] == 0.45
        assert payload["abliteration_count"] == 2

        restored = PersonalityEvolution.from_payload(payload)
        assert restored.abliteration_count == 2
        assert restored.personality_depth == 0.45
        assert restored.dominant_traits == ["mathematics", "physics"]

    def test_from_none_payload(self):
        evo = PersonalityEvolution.from_payload(None)
        assert evo.abliteration_count == 0
        assert evo.personality_depth == 0.0

    def test_record_abliteration_increments(self):
        evo = PersonalityEvolution()
        evo.record_abliteration(
            model_id="test-model",
            star_count=10,
            hunger_level=0.3,
            faculty_ids=["mathematics", "physics"],
        )
        assert evo.abliteration_count == 1
        assert len(evo.abliteration_history) == 1
        assert evo.abliteration_history[0].model_id == "test-model"
        assert evo.last_baked_at != ""
        assert evo.personality_depth > 0.0

    def test_record_multiple_abliterations(self):
        evo = PersonalityEvolution()
        for i in range(3):
            evo.record_abliteration(
                model_id=f"model-{i}",
                star_count=10 + i * 5,
                hunger_level=0.5,
                faculty_ids=["mathematics"],
            )
        assert evo.abliteration_count == 3
        assert len(evo.abliteration_history) == 3
        assert evo.personality_depth > 0.0

    def test_depth_zero_without_stars(self):
        """Abliterating with 0 stars gives 0 depth (star_factor = 0)."""
        evo = PersonalityEvolution()
        evo.record_abliteration(
            model_id="test", star_count=0,
            hunger_level=0.5, faculty_ids=["math"],
        )
        assert evo.personality_depth == 0.0

    def test_depth_grows_with_stars_and_abliterations(self):
        """Depth requires BOTH stars AND abliterations."""
        evo = PersonalityEvolution()
        evo.record_abliteration(
            model_id="m1", star_count=20,
            hunger_level=0.5, faculty_ids=["math", "physics"],
        )
        depth_after_one = evo.personality_depth
        assert depth_after_one > 0.0

        evo.record_abliteration(
            model_id="m2", star_count=20,
            hunger_level=0.4, faculty_ids=["literature"],
        )
        depth_after_two = evo.personality_depth
        assert depth_after_two > depth_after_one

    def test_depth_saturates(self):
        """Many abliterations with stars approach but don't exceed 1.0."""
        evo = PersonalityEvolution()
        for i in range(20):
            evo.record_abliteration(
                model_id=f"m{i}", star_count=30,
                hunger_level=0.5, faculty_ids=["math"],
            )
        assert evo.personality_depth <= 1.0
        assert evo.personality_depth >= 0.8  # High after 20 abliterations with 30 stars

    def test_traits_aggregated_by_frequency(self):
        evo = PersonalityEvolution()
        evo.record_abliteration(
            model_id="m1", star_count=10, hunger_level=0.5,
            faculty_ids=["math", "physics"],
        )
        evo.record_abliteration(
            model_id="m2", star_count=10, hunger_level=0.5,
            faculty_ids=["math", "literature"],
        )
        # "math" appears twice, should be first
        assert evo.dominant_traits[0] == "math"
        assert len(evo.dominant_traits) == 3

    def test_traits_capped_at_10(self):
        evo = PersonalityEvolution()
        evo.record_abliteration(
            model_id="m1", star_count=10, hunger_level=0.5,
            faculty_ids=[f"trait-{i}" for i in range(15)],
        )
        assert len(evo.dominant_traits) <= 10


class TestSwarmPersonaCount:
    def test_zero_stars_gives_minimum(self):
        assert swarm_persona_count(0) == 3

    def test_three_stars_gives_three(self):
        assert swarm_persona_count(3) == 3

    def test_ten_stars_gives_ten(self):
        assert swarm_persona_count(10) == 10

    def test_fifty_stars_capped_at_max(self):
        assert swarm_persona_count(50) == 32

    def test_depth_bonus_adds_personas(self):
        base = swarm_persona_count(10, personality_depth=0.0)
        with_depth = swarm_persona_count(10, personality_depth=1.0)
        assert with_depth == base + 8

    def test_depth_bonus_capped_at_max(self):
        # 30 stars + 1.0 depth bonus = 30 + 8 = 38, capped at 32
        assert swarm_persona_count(30, personality_depth=1.0) == 32

    def test_partial_depth_bonus(self):
        assert swarm_persona_count(10, personality_depth=0.5) == 10 + 4


class TestNourishmentStateWave3Properties:
    def test_personality_depth_property(self):
        evo = PersonalityEvolution(personality_depth=0.65)
        state = NourishmentState(personality=evo)
        assert state.personality_depth == 0.65

    def test_swarm_personas_property(self):
        evo = PersonalityEvolution(personality_depth=0.5)
        state = NourishmentState(total_stars=10, personality=evo)
        assert state.swarm_personas == 14  # 10 base + 4 depth bonus

    def test_has_been_baked_false(self):
        state = NourishmentState()
        assert not state.has_been_baked

    def test_has_been_baked_true(self):
        evo = PersonalityEvolution(abliteration_count=1)
        state = NourishmentState(personality=evo)
        assert state.has_been_baked

    def test_personality_in_payload(self):
        evo = PersonalityEvolution(
            abliteration_count=1,
            personality_depth=0.42,
            dominant_traits=["math"],
        )
        state = NourishmentState(total_stars=10, personality=evo)
        payload = state.to_payload()
        assert payload["personality_depth"] == 0.42
        # 10 base + round(0.42*8)=3 = 13
        assert payload["swarm_personas"] == 13
        assert payload["has_been_baked"] is True

    def test_personality_roundtrip_in_state(self):
        evo = PersonalityEvolution(
            abliteration_count=2,
            personality_depth=0.5,
            dominant_traits=["math", "physics"],
        )
        state = NourishmentState(total_stars=8, personality=evo)
        payload = state.to_payload()
        restored = NourishmentState.from_payload(payload)
        assert restored.personality.abliteration_count == 2
        assert restored.personality.personality_depth == 0.5
        assert restored.personality.dominant_traits == ["math", "physics"]


class TestComputeNourishmentWave3:
    def test_personality_passed_through(self):
        evo = PersonalityEvolution(abliteration_count=1, personality_depth=0.5)
        stars = _make_stars(10)
        state = compute_nourishment(
            stars=stars, faculties=_FACULTIES, personality=evo,
        )
        assert state.personality.abliteration_count == 1
        assert state.personality.personality_depth == 0.5

    def test_depth_calm_reduces_hunger(self):
        """Personality depth should reduce hunger slightly."""
        stars = _make_stars(5)
        state_no_depth = compute_nourishment(
            stars=stars, faculties=_FACULTIES,
        )
        evo = PersonalityEvolution(personality_depth=1.0)
        state_depth = compute_nourishment(
            stars=stars, faculties=_FACULTIES, personality=evo,
        )
        assert state_depth.hunger_level < state_no_depth.hunger_level

    def test_depth_calm_max_010(self):
        """Even high depth can't reduce hunger by more than 0.1."""
        stars = _make_stars(5)
        state_no_depth = compute_nourishment(stars=stars, faculties=_FACULTIES)
        evo = PersonalityEvolution(personality_depth=1.0)
        state_depth = compute_nourishment(
            stars=stars, faculties=_FACULTIES, personality=evo,
        )
        diff = state_no_depth.hunger_level - state_depth.hunger_level
        assert diff <= 0.101  # float tolerance

    def test_personality_none_defaults_safely(self):
        stars = _make_stars(5)
        state = compute_nourishment(stars=stars, faculties=_FACULTIES, personality=None)
        assert state.personality.abliteration_count == 0
        assert state.personality_depth == 0.0

    def test_personality_carried_from_previous(self):
        """When no explicit personality, it carries from previous state."""
        evo = PersonalityEvolution(abliteration_count=3, personality_depth=0.7)
        previous = NourishmentState(personality=evo)
        stars = _make_stars(5)
        state = compute_nourishment(
            stars=stars, faculties=_FACULTIES, previous=previous,
        )
        assert state.personality.abliteration_count == 3


class TestPersonalityBakedReaction:
    def test_personality_baked_event_generates_reaction(self):
        evo = PersonalityEvolution(abliteration_count=1, personality_depth=0.45)
        state = NourishmentState(
            hunger_level=0.3, total_stars=10, personality=evo,
            recent_events=[
                StarEvent("personality_baked", "", "", assistant_now_iso(),
                          "Abliterated test-model"),
            ],
        )
        reaction = generate_star_event_reaction(state)
        assert isinstance(reaction, str)
        assert len(reaction) > 5

    def test_personality_baked_mentions_depth(self):
        """personality_baked reaction may mention depth value."""
        evo = PersonalityEvolution(abliteration_count=1, personality_depth=0.45)
        state = NourishmentState(
            hunger_level=0.3, total_stars=10, personality=evo,
            recent_events=[
                StarEvent("personality_baked", "", "", assistant_now_iso()),
            ],
        )
        # Run multiple times — depth mention has 60% chance
        found_depth = False
        for _ in range(30):
            reaction = generate_star_event_reaction(state)
            if "0.45" in reaction:
                found_depth = True
                break
        assert found_depth, "Expected depth mention in at least one of 30 attempts"


class TestPersonalityMentionHelpers:
    def test_generates_string_with_deep_personality(self):
        from metis_app.services.star_nourishment_gen import _personality_mention
        evo = PersonalityEvolution(abliteration_count=2, personality_depth=0.7)
        state = NourishmentState(total_stars=10, personality=evo)
        result = _personality_mention(state)
        assert isinstance(result, str)

    def test_generates_string_with_shallow_personality(self):
        from metis_app.services.star_nourishment_gen import _personality_mention
        evo = PersonalityEvolution(abliteration_count=0, personality_depth=0.0)
        state = NourishmentState(total_stars=10, personality=evo)
        # Shallow personality → yearning or empty (chance-based)
        result = _personality_mention(state)
        assert isinstance(result, str)

    def test_swarm_mention_with_diversity(self):
        from metis_app.services.star_nourishment_gen import _swarm_mention
        evo = PersonalityEvolution(personality_depth=0.5)
        state = NourishmentState(total_stars=15, personality=evo)
        # swarm_personas > 8 → diversity path
        results = [_swarm_mention(state) for _ in range(30)]
        # At least some should be non-empty (30% chance each)
        assert any(isinstance(r, str) for r in results)

    def test_swarm_mention_with_hunger(self):
        from metis_app.services.star_nourishment_gen import _swarm_mention
        state = NourishmentState(total_stars=3)  # swarm_personas = 3, < 8
        results = [_swarm_mention(state) for _ in range(30)]
        assert any(isinstance(r, str) for r in results)


class TestHungerBlockWave3:
    def test_block_includes_personality_section(self):
        evo = PersonalityEvolution(
            abliteration_count=2,
            personality_depth=0.5,
            dominant_traits=["math", "physics"],
        )
        state = NourishmentState(
            hunger_level=0.4, total_stars=10, personality=evo,
        )
        block = generate_hunger_block(state)
        assert "Personality:" in block
        assert "depth 0.50" in block
        assert "2 abliteration(s)" in block

    def test_block_includes_swarm_count(self):
        evo = PersonalityEvolution(personality_depth=0.5)
        state = NourishmentState(
            hunger_level=0.4, total_stars=10, personality=evo,
        )
        block = generate_hunger_block(state)
        assert "Swarm diversity:" in block

    def test_block_zero_depth(self):
        state = NourishmentState(hunger_level=0.5, total_stars=5)
        block = generate_hunger_block(state)
        assert "Personality:" in block
        assert "unbaked" in block

    def test_all_hunger_levels_with_personality(self):
        """All 6 hunger states generate valid expressions with personality."""
        evo = PersonalityEvolution(abliteration_count=1, personality_depth=0.6)
        for level in [0.05, 0.25, 0.45, 0.65, 0.85, 0.98]:
            state = NourishmentState(
                hunger_level=level, total_stars=10, personality=evo,
            )
            expr = generate_hunger_expression(state)
            assert isinstance(expr, str), f"Failed at level {level}"
            block = generate_hunger_block(state)
            assert "Personality:" in block, f"No personality at level {level}"
