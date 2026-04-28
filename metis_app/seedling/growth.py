"""Phase 5 — visible growth stages (M13).

Pure functions for computing the Seedling → Sapling → Bloom → Elder
stage from a snapshot of the user's activity counters. Kept separate
from the orchestrator so the thresholds can be unit-tested without
touching the database, and so the same function powers the dock badge
and a future "what does it take to grow?" UI.

The thresholds are currently locked in
``plans/seedling-and-feed/plan.md`` *Phase 5 thresholds — v0 decision*
section rather than a full ADR, because they will tune rapidly during
the first few weeks of real usage. Changing them is a one-line edit
to ``DEFAULT_THRESHOLDS`` plus the matching plan-doc update.

Design notes:

- The stage **only advances**; it never regresses. A user who deletes
  stars to clean up should not lose their growth stage. Regression is
  available only via the manual override
  (``seedling_growth_stage_override`` setting) for testing.
- A reflection of *any* kind counts (Phase 4a Bonsai, Phase 4b
  overnight backend, Phase 4 manual). This is the explicit answer to
  the open question in ADR 0013 §Open Questions: users without
  WebGPU and without a backend GGUF can still advance.
- Brain-graph density is part of the published Bloom → Elder
  threshold but is **not** wired up in this v0 — Phase 6 will add it
  once the M10 brain graph integration lands. Until then Elder is
  reachable on the structural counts alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from metis_app.models.assistant_types import GrowthStage

# Stage ordering — used for the "no regression" rule.
_STAGE_ORDER: list[GrowthStage] = ["seedling", "sapling", "bloom", "elder"]


@dataclass(frozen=True, slots=True)
class GrowthSignals:
    """Snapshot of the structural counters the stage machine reads.

    Each counter has an integer floor of zero. Negative or non-integer
    inputs are coerced to zero in :func:`compute_growth_stage`.
    """

    indexed_stars: int = 0
    indexed_faculties: int = 0
    reflections_total: int = 0
    overnight_reflections: int = 0
    skill_candidates: int = 0
    promoted_skills: int = 0
    brain_graph_density: float = 0.0  # Phase 6 fills this in; 0.0 means "unknown"


@dataclass(frozen=True, slots=True)
class StageThresholds:
    """Counters required to enter each stage.

    Each named counter is the **minimum** count required. Boolean AND
    across the named counters; missing counters are treated as zero.

    **Tuning checklist (M13 retro, 2026-04-26).** These are v0
    estimates locked at Phase 5 / 6 ship time. Tuning them is
    deliberately data-gated — picking new numbers without
    stage-distribution telemetry would be theatre. When real-user
    data accumulates (M16 personal evals will surface this), tune
    in this order:

    1. **Measure stage distribution.** Pull
       ``AssistantStatus.growth_stage`` for every active workspace
       across a representative window (≥30 days, ≥50 users). The
       healthy shape is roughly:

       - ~40% Seedling (first-week users)
       - ~35% Sapling (engaged but exploring)
       - ~20% Bloom (settled, productive)
       - ~5% Elder (deep-investment power users)

       If the mass is stuck at Seedling (e.g., 80%+), thresholds
       are too aggressive — drop ``sapling_stars`` toward 5-7. If
       Elder is empty after months of use, the Elder gate is too
       tight — relax ``elder_brain_graph_density`` to 0.4 first
       (cheapest knob), then ``elder_promoted_skills`` to 2.

    2. **Validate the density-gate calibration.** With Phase 6
       live, ``elder_brain_graph_density=0.5`` is the load-bearing
       gate. Pull ``BrainGraph.compute_assistant_density`` per
       workspace and look at the distribution among workspaces that
       hit the structural Elder counts (≥200 stars + ≥3 promoted
       skills + ≥30 reflections). Healthy: median density ≥ 0.6,
       p10 ≥ 0.4. Unhealthy: density bunched at 0.3-0.4 means the
       ``_TARGET_EDGES_PER_ARTEFACT=2`` constant is wrong for real
       reflection cadence — drop it to 1 (rationale: half of
       reflections get cross-linked, not all).

    3. **Validate threshold + density together.** Don't tune
       structural counts and density in the same release —
       distributions become uninterpretable. One change per
       release; observe for 2+ weeks.

    Code-side knobs (when ready to tune):
    - ``sapling_stars`` / ``sapling_reflections`` (lines below).
    - ``bloom_stars`` / ``bloom_faculties`` /
      ``bloom_skill_candidates`` / ``bloom_reflections``.
    - ``elder_stars`` / ``elder_promoted_skills`` /
      ``elder_reflections`` / ``elder_brain_graph_density``.
    - ``_TARGET_EDGES_PER_ARTEFACT`` in
      :mod:`metis_app.models.brain_graph` (calibrates density
      saturation; tune alongside ``elder_brain_graph_density``).

    Plan-doc cross-reference: keep
    ``plans/seedling-and-feed/plan.md`` *Phase 5 thresholds — v0
    decision* and *Phase 6 brain-graph density — v0 decision*
    sections in sync with any changes here. Any tuning PR should
    link the telemetry that motivated it.
    """

    sapling_stars: int = 10
    sapling_reflections: int = 1

    bloom_stars: int = 50
    bloom_faculties: int = 6
    bloom_skill_candidates: int = 5
    bloom_reflections: int = 7

    elder_stars: int = 200
    elder_promoted_skills: int = 3
    elder_reflections: int = 30
    # Phase 6 activates this gate. Values are normalised to [0.0,
    # 1.0] by ``BrainGraph.compute_assistant_density``. The 0.5
    # threshold is a v0 estimate calibrated against the doc-locked
    # Elder counts: 30 reflections + 3 promoted skills + 200
    # indexed stars typically produce ~3 edges per assistant-scope
    # node (i.e., density ≈ 0.75) in real workspaces, so 0.5 is a
    # comfortable but non-trivial gate. See the *Tuning checklist*
    # above + ``plans/seedling-and-feed/plan.md`` *Phase 6
    # brain-graph density — v0 decision* for the calibration math.
    elder_brain_graph_density: float = 0.5


DEFAULT_THRESHOLDS = StageThresholds()


@dataclass(frozen=True, slots=True)
class GrowthDecision:
    """Outcome of a stage recompute.

    ``stage`` is the new stage (or the unchanged current stage if no
    advance was warranted). ``advanced_from`` is non-None only when
    the stage moved up; the orchestrator uses that to decide whether
    to emit the one-time stage-transition activity event.
    """

    stage: GrowthStage
    advanced_from: GrowthStage | None = None
    reason: str = ""


def _meets_sapling(signals: GrowthSignals, t: StageThresholds) -> bool:
    return (
        signals.indexed_stars >= t.sapling_stars
        and signals.reflections_total >= t.sapling_reflections
    )


def _meets_bloom(signals: GrowthSignals, t: StageThresholds) -> bool:
    return (
        signals.indexed_stars >= t.bloom_stars
        and signals.indexed_faculties >= t.bloom_faculties
        and signals.skill_candidates >= t.bloom_skill_candidates
        and signals.reflections_total >= t.bloom_reflections
    )


def _meets_elder(signals: GrowthSignals, t: StageThresholds) -> bool:
    if signals.indexed_stars < t.elder_stars:
        return False
    if signals.promoted_skills < t.elder_promoted_skills:
        return False
    if signals.reflections_total < t.elder_reflections:
        return False
    if t.elder_brain_graph_density > 0.0 and (
        signals.brain_graph_density < t.elder_brain_graph_density
    ):
        return False
    return True


def compute_growth_stage(
    *,
    signals: GrowthSignals,
    current_stage: GrowthStage = "seedling",
    thresholds: StageThresholds | None = None,
    override: GrowthStage | None = None,
) -> GrowthDecision:
    """Return the appropriate stage given the current counters.

    The function is monotonic: it never returns a stage *below*
    ``current_stage`` unless ``override`` is supplied (used by the
    settings-driven manual override path). When the stage advances,
    ``GrowthDecision.advanced_from`` records the prior stage so the
    caller can fire the one-time transition event.

    *Brain-graph density* is consulted only if the threshold is
    positive — Phase 6 will set
    ``StageThresholds.elder_brain_graph_density`` to the chosen value
    when M10 wires the signal in.
    """
    t = thresholds or DEFAULT_THRESHOLDS

    # Manual override (test/debug). Bypass the monotonicity rule too —
    # demoting on purpose is the point.
    if override is not None and override in _STAGE_ORDER:
        return GrowthDecision(
            stage=override,
            advanced_from=current_stage if override != current_stage else None,
            reason="override",
        )

    if _meets_elder(signals, t):
        target: GrowthStage = "elder"
    elif _meets_bloom(signals, t):
        target = "bloom"
    elif _meets_sapling(signals, t):
        target = "sapling"
    else:
        target = "seedling"

    # No regression — the stage only advances. A user who cleaned up
    # their atlas after reaching Sapling shouldn't drop back to
    # Seedling.
    current_idx = _STAGE_ORDER.index(current_stage)
    target_idx = _STAGE_ORDER.index(target)
    if target_idx <= current_idx:
        return GrowthDecision(stage=current_stage, advanced_from=None, reason="held")

    return GrowthDecision(
        stage=target,
        advanced_from=current_stage,
        reason="advanced",
    )


def signals_from_counts(payload: dict[str, Any]) -> GrowthSignals:
    """Build :class:`GrowthSignals` from a dict, coercing types defensively.

    The orchestrator collects counts from several repos and feeds the
    raw payload here — coercion lives in one place so the compute
    function doesn't have to defend against ``None`` / non-integer
    inputs from each caller.
    """
    def _int(key: str, default: int = 0) -> int:
        try:
            return max(0, int(payload.get(key, default) or 0))
        except (TypeError, ValueError):
            return default

    def _float(key: str, default: float = 0.0) -> float:
        try:
            return max(0.0, float(payload.get(key, default) or 0.0))
        except (TypeError, ValueError):
            return default

    return GrowthSignals(
        indexed_stars=_int("indexed_stars"),
        indexed_faculties=_int("indexed_faculties"),
        reflections_total=_int("reflections_total"),
        overnight_reflections=_int("overnight_reflections"),
        skill_candidates=_int("skill_candidates"),
        promoted_skills=_int("promoted_skills"),
        brain_graph_density=_float("brain_graph_density"),
    )
