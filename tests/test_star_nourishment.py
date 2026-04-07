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
