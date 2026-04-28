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

    def _compute_assistant_density(self) -> float:
        """Stub the Phase 6 P1 density helper. ``_collect_growth_counts``
        calls this directly (rather than going through the UI's
        capped ``get_workspace_graph``), so the integration tests
        exercise the orchestrator's wiring without hydrating a real
        ``BrainGraph`` from an uncapped repository."""
        return self._brain_graph_density

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


# ---------------------------------------------------------------------------
# Phase 6 P1 regression (Codex review on PR #558) — density must use the
# *full* assistant repository, not the UI-capped snapshot.
# ---------------------------------------------------------------------------


def test_compute_assistant_density_reads_uncapped_repository(tmp_path) -> None:
    """P1 regression (Codex review on PR #558):
    ``_compute_assistant_density`` must NOT route through
    ``AssistantCompanionService.get_snapshot`` (which caps memory at
    8 / playbooks at 6 for the UI brain canvas). A long-running
    companion's Elder advance must reflect *all* accumulated memories.

    Distinguishing setup: 12 memories, but the cross-links are
    anchored on the OLDEST 4 (the ones the snapshot would drop).

    - Uncapped (correct): 4 learned edges / (2 × 12 artefacts) =
      ``0.166...``
    - Capped (buggy): the 8 newest memories are visible but they
      have no learned edges; the 4 edges reference ``memory:*`` IDs
      that aren't in the graph, so ``_add_assistant_subgraph``'s
      existence guard drops them. Density = ``0.0``.

    A non-zero density therefore proves the helper is reading the
    full repository, not the capped snapshot."""
    from metis_app.models.assistant_types import (
        AssistantBrainLink,
        AssistantMemoryEntry,
    )
    from metis_app.services.assistant_companion import (
        AssistantCompanionService,
    )
    from metis_app.services.assistant_repository import AssistantRepository

    repo = AssistantRepository(tmp_path / "assistant_state.json")

    # 12 memories with explicit, monotonically-increasing created_at
    # so list_memory(limit=8) returns the *newer* 8 (m04..m11) and
    # drops the 4 oldest (m00..m03).
    for i in range(12):
        ts = f"2026-01-{i + 1:02d}T00:00:00Z"
        repo.add_memory_entry(
            AssistantMemoryEntry.from_payload(
                {
                    "entry_id": f"m{i:02d}",
                    "created_at": ts,
                    "kind": "reflection",
                    "title": f"Reflection {i}",
                    "summary": "x",
                }
            ),
            max_entries=64,
        )

    # Anchor 4 ``assistant_learned`` cross-links on the OLDEST 4
    # memories only. Capped snapshot (8 newest visible) wouldn't see
    # these as ``memory:*`` nodes, so the edges would be dropped by
    # the ``_add_assistant_subgraph`` existence guard.
    learned_links = [
        AssistantBrainLink.create(
            source_node_id=f"memory:m{i:02d}",
            target_node_id="assistant:metis",
            relation="learned_from_session",
            label="Learned",
            summary="cross-link",
            metadata={"scope": "assistant_learned"},
        )
        for i in range(4)  # m00..m03 — the OLDEST four
    ]
    repo.add_brain_links(learned_links, max_items=128)

    service = AssistantCompanionService(repository=repo)

    # Sanity: prove the snapshot path is genuinely capping at 8 and
    # that the 4 oldest memories are the ones being dropped.
    snapshot = service.get_snapshot({})
    assert len(snapshot["memory"]) == 8
    snapshot_ids = {item["entry_id"] for item in snapshot["memory"]}
    assert "m00" not in snapshot_ids
    assert "m11" in snapshot_ids

    class _Stub:
        def __init__(self) -> None:
            self._assistant_service = service

            class _Sessions:
                def list_sessions(self_inner) -> list:  # noqa: ARG002
                    return []

            self._session_repo = _Sessions()

        def list_indexes(self) -> list[dict]:
            return []

        from metis_app.services.workspace_orchestrator import (
            WorkspaceOrchestrator as _W,
        )

        _compute_assistant_density = _W._compute_assistant_density  # type: ignore[assignment]

    density = _Stub()._compute_assistant_density()

    # Uncapped: 4 / (2 × 12) = 1/6.
    assert density == pytest.approx(4.0 / 24.0)
    # Buggy capped path would yield 0.0 (edges dropped by guard) —
    # explicitly assert we're well clear.
    assert density > 0.0
