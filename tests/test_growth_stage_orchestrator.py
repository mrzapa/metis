"""Integration tests for ``WorkspaceOrchestrator.recompute_growth_stage``.

The pure compute is exercised in ``test_seedling_growth.py``. These
tests exercise the integration: pulling counts from the assistant
service + skill repo, persisting the new stage on advance, and
emitting a single stage_transition activity event.
"""

from __future__ import annotations

import pathlib

import pytest

from metis_app.models.assistant_types import (
    AssistantMemoryEntry,
    AssistantStatus,
)
from metis_app.seedling.activity import (
    clear_seedling_activity_events,
    list_seedling_activity_events,
)


# ---------------------------------------------------------------------------
# Helpers — build a fully-stubbed orchestrator with controllable counts.
# ---------------------------------------------------------------------------


class _FakeAssistantRepo:
    def __init__(self) -> None:
        self._status = AssistantStatus()
        self._memory: list[AssistantMemoryEntry] = []

    def get_status(self) -> AssistantStatus:
        return self._status

    def update_status(self, status: AssistantStatus) -> None:
        self._status = status

    def list_memory(self, limit: int = 1000) -> list[AssistantMemoryEntry]:
        return list(self._memory[:limit])


class _FakeAssistantService:
    def __init__(self) -> None:
        self.repository = _FakeAssistantRepo()


class _FakeSkillRepo:
    def __init__(self, *, total: int, promoted: int) -> None:
        self._counts = {
            "total": total,
            "promoted": promoted,
            "unpromoted": max(0, total - promoted),
        }

    def count_candidates(self, *, db_path: pathlib.Path) -> dict[str, int]:
        return dict(self._counts)


class _StubOrchestrator:
    """A minimal stand-in for ``WorkspaceOrchestrator`` that provides
    only what ``recompute_growth_stage`` reaches for. We bind the real
    method onto it so the production code path runs verbatim."""

    def __init__(
        self,
        *,
        indexes: list[dict],
        memory: list[AssistantMemoryEntry],
        skill_total: int,
        skill_promoted: int,
        settings: dict | None = None,
        brain_graph_density: float = 0.0,
    ) -> None:
        self._indexes = indexes
        self._assistant_service = _FakeAssistantService()
        self._assistant_service.repository._memory = memory
        self._skill_repo = _FakeSkillRepo(
            total=skill_total, promoted=skill_promoted
        )
        self._settings = dict(settings or {})
        self._brain_graph_density = float(brain_graph_density)

    def list_indexes(self) -> list[dict]:
        return list(self._indexes)

    def get_workspace_graph(self, *, skip_layout: bool = False):  # noqa: ARG002
        """Stub the BrainGraph build so density tests don't depend on
        the full assistant subgraph construction. Returns an object
        whose ``compute_assistant_density`` returns the configured
        value — Phase 6 ``_collect_growth_counts`` only calls that
        method on the result."""
        density_value = self._brain_graph_density

        class _DensityStub:
            def compute_assistant_density(self) -> float:
                return density_value

        return _DensityStub()

    def _resolve_query_settings(self, override: dict) -> dict:
        merged = dict(self._settings)
        merged.update(override or {})
        return merged

    # Bind the production methods.
    from metis_app.services.workspace_orchestrator import (
        WorkspaceOrchestrator as _W,
    )

    recompute_growth_stage = _W.recompute_growth_stage  # type: ignore[assignment]
    _collect_growth_counts = _W._collect_growth_counts  # type: ignore[assignment]


def _memory_entries(reflection_kinds: dict[str, int]) -> list[AssistantMemoryEntry]:
    """Build a memory list with N entries of each kind."""
    entries: list[AssistantMemoryEntry] = []
    for kind, count in reflection_kinds.items():
        for i in range(count):
            entries.append(
                AssistantMemoryEntry.create(
                    kind=kind,
                    title=f"{kind} entry {i}",
                    summary="x",
                )
            )
    return entries


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_activity():
    clear_seedling_activity_events()
    yield
    clear_seedling_activity_events()


def test_recompute_growth_stage_holds_seedling_when_under_threshold() -> None:
    orch = _StubOrchestrator(
        indexes=[{"index_id": "i1", "faculty_id": "ml"}] * 5,
        memory=_memory_entries({"reflection": 0}),
        skill_total=0,
        skill_promoted=0,
    )
    result = orch.recompute_growth_stage()
    assert result["stage"] == "seedling"
    assert result["advanced_from"] is None
    assert "transition_event" not in result
    # No activity event fired.
    assert list_seedling_activity_events() == []


def test_recompute_growth_stage_advances_to_sapling_with_bonsai_reflection() -> None:
    """ADR 0013 nit 3 resolution: a Bonsai while-you-work reflection
    counts toward the Seedling → Sapling threshold even when the
    backend GGUF is not configured."""
    orch = _StubOrchestrator(
        indexes=[
            {"index_id": f"idx-{i}", "faculty_id": "ml" if i % 2 else "systems"}
            for i in range(10)
        ],
        memory=_memory_entries({"bonsai_reflection": 1}),
        skill_total=0,
        skill_promoted=0,
    )
    result = orch.recompute_growth_stage()
    assert result["stage"] == "sapling"
    assert result["advanced_from"] == "seedling"

    # Assistant status persisted.
    status = orch._assistant_service.repository.get_status()
    assert status.growth_stage == "sapling"
    assert status.growth_stage_changed_at  # ISO timestamp set

    # One stage_transition activity event fired.
    events = list_seedling_activity_events()
    transition_events = [e for e in events if e.get("kind") == "stage_transition"]
    assert len(transition_events) == 1
    assert transition_events[0]["payload"]["status"]["growth_stage"] == "sapling"
    assert transition_events[0]["payload"]["status"]["advanced_from"] == "seedling"


def test_recompute_growth_stage_idempotent_on_second_call() -> None:
    orch = _StubOrchestrator(
        indexes=[
            {"index_id": f"idx-{i}", "faculty_id": "ml"}
            for i in range(10)
        ],
        memory=_memory_entries({"overnight_reflection": 1}),
        skill_total=0,
        skill_promoted=0,
    )
    first = orch.recompute_growth_stage()
    assert first["advanced_from"] == "seedling"
    assert len(list_seedling_activity_events()) == 1

    # Second call with the same signals — no new event, status unchanged.
    second = orch.recompute_growth_stage()
    assert second["advanced_from"] is None
    assert second["stage"] == "sapling"
    assert len(list_seedling_activity_events()) == 1


def test_recompute_growth_stage_advances_through_bloom() -> None:
    orch = _StubOrchestrator(
        indexes=[
            {"index_id": f"idx-{i}", "faculty_id": f"f{i % 6}"}
            for i in range(60)
        ],
        memory=_memory_entries({
            "reflection": 4,
            "bonsai_reflection": 2,
            "overnight_reflection": 2,
        }),
        skill_total=5,
        skill_promoted=0,
    )
    result = orch.recompute_growth_stage()
    assert result["stage"] == "bloom"
    assert result["advanced_from"] == "seedling"
    # Single transition event covers the multi-stage jump (we only
    # emit one event per recompute, which is the right behaviour —
    # the user sees one "Companion advanced to Bloom" toast, not two).
    transitions = [
        e for e in list_seedling_activity_events()
        if e.get("kind") == "stage_transition"
    ]
    assert len(transitions) == 1


def test_override_setting_demotes_for_testing() -> None:
    orch = _StubOrchestrator(
        indexes=[
            {"index_id": f"idx-{i}", "faculty_id": "ml"}
            for i in range(10)
        ],
        memory=_memory_entries({"reflection": 1}),
        skill_total=0,
        skill_promoted=0,
        settings={"seedling_growth_stage_override": "elder"},
    )
    result = orch.recompute_growth_stage()
    assert result["stage"] == "elder"
    assert result["reason"] == "override"

    # Demote via override.
    orch._settings["seedling_growth_stage_override"] = "seedling"
    demote = orch.recompute_growth_stage()
    assert demote["stage"] == "seedling"
    assert demote["reason"] == "override"


def test_count_growth_signals_includes_all_reflection_kinds() -> None:
    """Verifies the reflection counter sums across the three kinds —
    the load-bearing fact behind ADR 0013 nit 3 resolution."""
    orch = _StubOrchestrator(
        indexes=[],
        memory=_memory_entries({
            "reflection": 3,
            "bonsai_reflection": 4,
            "overnight_reflection": 2,
            "autonomous_research": 5,  # must NOT count
            "skill_candidate_audit": 1,  # must NOT count
        }),
        skill_total=0,
        skill_promoted=0,
    )
    counts = orch._collect_growth_counts()
    assert counts["reflections_total"] == 9  # 3 + 4 + 2
    assert counts["overnight_reflections"] == 2


# ---------------------------------------------------------------------------
# M13 Phase 6 — brain-graph density signal + Elder gate
# ---------------------------------------------------------------------------


def test_collect_growth_counts_pulls_density_from_brain_graph() -> None:
    """Phase 6 integration: the orchestrator's ``_collect_growth_counts``
    forwards ``BrainGraph.compute_assistant_density`` into the signal
    payload."""
    orch = _StubOrchestrator(
        indexes=[],
        memory=_memory_entries({"reflection": 5}),
        skill_total=0,
        skill_promoted=0,
        brain_graph_density=0.42,
    )
    counts = orch._collect_growth_counts()
    assert counts["brain_graph_density"] == 0.42


def test_recompute_growth_stage_blocks_elder_when_density_low(tmp_path) -> None:
    """Phase 6 regression: structural Elder counts met but density
    below 0.5 → held at Bloom. The user has all the right counters
    but the brain graph hasn't fattened enough."""
    indexes = [
        {"index_id": f"idx-{i}", "faculty_id": f"f{i % 8}"} for i in range(220)
    ]
    orch = _StubOrchestrator(
        indexes=indexes,
        memory=_memory_entries({"reflection": 35}),
        skill_total=10,
        skill_promoted=4,
        brain_graph_density=0.30,  # below 0.5 default
    )
    # Set current_stage to bloom so we're testing the bloom→elder gate.
    orch._assistant_service.repository.get_status().growth_stage = "bloom"
    result = orch.recompute_growth_stage()
    assert result["stage"] == "bloom"
    assert result["advanced_from"] is None  # held — density gate blocks


def test_recompute_growth_stage_advances_to_elder_when_density_high(tmp_path) -> None:
    """Phase 6 happy-path: structural counts AND density both above
    threshold → Elder advance."""
    indexes = [
        {"index_id": f"idx-{i}", "faculty_id": f"f{i % 8}"} for i in range(220)
    ]
    orch = _StubOrchestrator(
        indexes=indexes,
        memory=_memory_entries({"reflection": 35}),
        skill_total=10,
        skill_promoted=4,
        brain_graph_density=0.85,
    )
    orch._assistant_service.repository.get_status().growth_stage = "bloom"
    result = orch.recompute_growth_stage()
    assert result["stage"] == "elder"
    assert result["advanced_from"] == "bloom"
    assert result["signals"]["brain_graph_density"] == 0.85
