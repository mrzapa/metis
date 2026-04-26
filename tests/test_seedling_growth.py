"""Tests for the M13 Phase 5 growth-stage compute."""

from __future__ import annotations

import pytest

from metis_app.seedling.growth import (
    DEFAULT_THRESHOLDS,
    GrowthSignals,
    StageThresholds,
    compute_growth_stage,
    signals_from_counts,
)


# ---------------------------------------------------------------------------
# signals_from_counts coercion
# ---------------------------------------------------------------------------


def test_signals_from_counts_coerces_missing_keys_to_zero() -> None:
    s = signals_from_counts({})
    assert s == GrowthSignals()


def test_signals_from_counts_coerces_negatives_to_zero() -> None:
    s = signals_from_counts({
        "indexed_stars": -5,
        "indexed_faculties": "garbage",
        "reflections_total": None,
        "skill_candidates": 3,
        "promoted_skills": 1,
        "brain_graph_density": -0.4,
    })
    assert s.indexed_stars == 0
    assert s.indexed_faculties == 0
    assert s.reflections_total == 0
    assert s.skill_candidates == 3
    assert s.promoted_skills == 1
    assert s.brain_graph_density == 0.0


# ---------------------------------------------------------------------------
# Stage gates
# ---------------------------------------------------------------------------


def test_stays_seedling_when_below_sapling_threshold() -> None:
    decision = compute_growth_stage(
        signals=GrowthSignals(indexed_stars=9, reflections_total=1),
    )
    assert decision.stage == "seedling"
    assert decision.advanced_from is None


def test_advances_to_sapling_at_threshold() -> None:
    decision = compute_growth_stage(
        signals=GrowthSignals(indexed_stars=10, reflections_total=1),
    )
    assert decision.stage == "sapling"
    assert decision.advanced_from == "seedling"
    assert decision.reason == "advanced"


def test_does_not_advance_to_sapling_without_reflection() -> None:
    decision = compute_growth_stage(
        signals=GrowthSignals(indexed_stars=20, reflections_total=0),
    )
    assert decision.stage == "seedling"


def test_advances_to_bloom_when_full_threshold_met() -> None:
    decision = compute_growth_stage(
        signals=GrowthSignals(
            indexed_stars=50,
            indexed_faculties=6,
            skill_candidates=5,
            reflections_total=7,
        ),
        current_stage="sapling",
    )
    assert decision.stage == "bloom"
    assert decision.advanced_from == "sapling"


def test_does_not_advance_to_bloom_when_faculties_thin() -> None:
    decision = compute_growth_stage(
        signals=GrowthSignals(
            indexed_stars=50,
            indexed_faculties=4,  # below 6
            skill_candidates=5,
            reflections_total=7,
        ),
        current_stage="sapling",
    )
    assert decision.stage == "sapling"


def test_advances_to_elder_when_full_threshold_met() -> None:
    decision = compute_growth_stage(
        signals=GrowthSignals(
            indexed_stars=200,
            indexed_faculties=8,
            skill_candidates=5,
            reflections_total=30,
            promoted_skills=3,
        ),
        current_stage="bloom",
    )
    assert decision.stage == "elder"
    assert decision.advanced_from == "bloom"


def test_elder_blocked_when_promoted_skills_thin() -> None:
    decision = compute_growth_stage(
        signals=GrowthSignals(
            indexed_stars=200,
            indexed_faculties=8,
            skill_candidates=5,
            reflections_total=30,
            promoted_skills=2,  # below 3
        ),
        current_stage="bloom",
    )
    assert decision.stage == "bloom"


def test_elder_blocked_when_brain_graph_density_threshold_set_and_too_low() -> None:
    """Phase 6 will set ``elder_brain_graph_density`` to a positive
    number; until then the gate is open. Verify both branches."""
    signals = GrowthSignals(
        indexed_stars=300,
        indexed_faculties=8,
        skill_candidates=10,
        reflections_total=40,
        promoted_skills=5,
        brain_graph_density=0.10,
    )
    # v0: threshold is 0 → density gate ignored → advances.
    decision_v0 = compute_growth_stage(signals=signals, current_stage="bloom")
    assert decision_v0.stage == "elder"

    # Phase 6 hypothetical: threshold 0.25, density 0.10 → blocked.
    phase6 = StageThresholds(elder_brain_graph_density=0.25)
    decision_phase6 = compute_growth_stage(
        signals=signals,
        current_stage="bloom",
        thresholds=phase6,
    )
    assert decision_phase6.stage == "bloom"


# ---------------------------------------------------------------------------
# Monotonicity (no regression)
# ---------------------------------------------------------------------------


def test_no_regression_when_counts_drop() -> None:
    # User reaches Sapling, then deletes stars. Should NOT drop back.
    decision = compute_growth_stage(
        signals=GrowthSignals(indexed_stars=2, reflections_total=0),
        current_stage="sapling",
    )
    assert decision.stage == "sapling"
    assert decision.advanced_from is None
    assert decision.reason == "held"


def test_no_double_advance_on_repeat_call() -> None:
    """Idempotency: once advanced, calling again with the same signals
    returns the new stage with ``advanced_from=None`` so the orchestrator
    only fires the transition event once."""
    signals = GrowthSignals(indexed_stars=10, reflections_total=1)
    first = compute_growth_stage(signals=signals, current_stage="seedling")
    assert first.advanced_from == "seedling"
    second = compute_growth_stage(signals=signals, current_stage=first.stage)
    assert second.advanced_from is None


# ---------------------------------------------------------------------------
# Manual override
# ---------------------------------------------------------------------------


def test_override_can_demote_for_testing() -> None:
    decision = compute_growth_stage(
        signals=GrowthSignals(indexed_stars=200, reflections_total=30, promoted_skills=3),
        current_stage="elder",
        override="seedling",
    )
    assert decision.stage == "seedling"
    assert decision.advanced_from == "elder"
    assert decision.reason == "override"


def test_override_advance_ignores_thresholds() -> None:
    decision = compute_growth_stage(
        signals=GrowthSignals(),
        current_stage="seedling",
        override="bloom",
    )
    assert decision.stage == "bloom"
    assert decision.advanced_from == "seedling"


# ---------------------------------------------------------------------------
# DEFAULT_THRESHOLDS regression
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,expected",
    [
        ("sapling_stars", 10),
        ("sapling_reflections", 1),
        ("bloom_stars", 50),
        ("bloom_faculties", 6),
        ("bloom_skill_candidates", 5),
        ("bloom_reflections", 7),
        ("elder_stars", 200),
        ("elder_promoted_skills", 3),
        ("elder_reflections", 30),
        ("elder_brain_graph_density", 0.0),
    ],
)
def test_default_thresholds_match_plan_doc(field: str, expected: float) -> None:
    """Lock the v0 thresholds — change requires updating the plan-doc
    decision section in ``plans/seedling-and-feed/plan.md`` to match."""
    assert getattr(DEFAULT_THRESHOLDS, field) == expected
