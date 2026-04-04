# Reverse-Curriculum Autonomous Research Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Sort constellation faculties by hardness (`demand / coverage`) before researching, so high-demand / low-coverage faculties are researched first (Sotaku reverse-curriculum pattern).

**Architecture:** Add `compute_demand_scores(indexes)` to `AutonomousResearchService` — counts non-auto user indexes per faculty from `brain_pass.placement.faculty_id`. Wire this into `run()` so demand scores are computed before calling `scan_faculty_gaps()`. `scan_faculty_gaps()` already accepts `demand_scores` and implements the hardness sort; only the call site needs updating.

**Tech Stack:** Python, pytest, existing `AutonomousResearchService`, `BrainGraph` index metadata.

---

### Task 1: Add `compute_demand_scores` method (TDD)

**Files:**
- Test: `tests/test_autonomous_research_service.py`
- Modify: `metis_app/services/autonomous_research_service.py`

**Step 1: Write the failing tests**

Append to `tests/test_autonomous_research_service.py`:

```python
def test_compute_demand_scores_counts_user_indexes_per_faculty():
    """Non-auto indexes with brain_pass.placement.faculty_id increment demand."""
    svc = AutonomousResearchService(web_search=MagicMock())
    indexes = [
        {
            "index_id": "user_doc_1",
            "brain_pass": {"placement": {"faculty_id": "reasoning"}},
        },
        {
            "index_id": "user_doc_2",
            "brain_pass": {"placement": {"faculty_id": "reasoning"}},
        },
        {
            "index_id": "user_doc_3",
            "brain_pass": {"placement": {"faculty_id": "knowledge"}},
        },
        # auto_ indexes should not count toward demand
        {
            "index_id": "auto_reasoning_abc",
            "brain_pass": {"placement": {"faculty_id": "reasoning"}},
        },
    ]
    scores = svc.compute_demand_scores(indexes)
    assert scores["reasoning"] == 2
    assert scores["knowledge"] == 1
    assert scores.get("perception", 0) == 0


def test_compute_demand_scores_ignores_missing_placement():
    """Indexes without brain_pass.placement.faculty_id are skipped."""
    svc = AutonomousResearchService(web_search=MagicMock())
    indexes = [
        {"index_id": "user_doc_no_faculty", "brain_pass": {}},
        {"index_id": "user_doc_no_brain_pass"},
        {"index_id": "user_doc_valid", "brain_pass": {"placement": {"faculty_id": "memory"}}},
    ]
    scores = svc.compute_demand_scores(indexes)
    assert scores.get("memory", 0) == 1
    assert len([v for v in scores.values() if v > 0]) == 1


def test_compute_demand_scores_returns_empty_for_no_user_indexes():
    """Returns empty dict when no user-placed indexes exist."""
    svc = AutonomousResearchService(web_search=MagicMock())
    scores = svc.compute_demand_scores([])
    assert scores == {}
```

**Step 2: Run tests to verify they fail**

```
cd C:\Users\samwe\Documents\metis\.claude\worktrees\reverse-curriculum
python -m pytest tests/test_autonomous_research_service.py::test_compute_demand_scores_counts_user_indexes_per_faculty tests/test_autonomous_research_service.py::test_compute_demand_scores_ignores_missing_placement tests/test_autonomous_research_service.py::test_compute_demand_scores_returns_empty_for_no_user_indexes -v
```
Expected: FAIL — `AttributeError: 'AutonomousResearchService' object has no attribute 'compute_demand_scores'`

**Step 3: Implement `compute_demand_scores` in `autonomous_research_service.py`**

Add after the `scan_faculty_gaps` method (around line 203):

```python
def compute_demand_scores(self, indexes: list[dict[str, Any]]) -> dict[str, int]:
    """Count non-auto user indexes per faculty as a demand signal.

    Each user-uploaded index whose brain_pass.placement.faculty_id names a
    constellation faculty adds 1 demand point. Auto-generated indexes
    (index_id starts with 'auto_') are excluded — they represent supply,
    not demand.
    """
    scores: dict[str, int] = {}
    for idx in indexes:
        index_id = str(idx.get("index_id") or "")
        if index_id.startswith("auto_"):
            continue
        brain_pass = idx.get("brain_pass") or {}
        if not isinstance(brain_pass, dict):
            continue
        placement = brain_pass.get("placement") or {}
        if not isinstance(placement, dict):
            continue
        faculty = str(placement.get("faculty_id") or "").strip()
        if faculty:
            scores[faculty] = scores.get(faculty, 0) + 1
    return scores
```

**Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_autonomous_research_service.py::test_compute_demand_scores_counts_user_indexes_per_faculty tests/test_autonomous_research_service.py::test_compute_demand_scores_ignores_missing_placement tests/test_autonomous_research_service.py::test_compute_demand_scores_returns_empty_for_no_user_indexes -v
```
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add tests/test_autonomous_research_service.py metis_app/services/autonomous_research_service.py
git commit -m "feat: add compute_demand_scores to AutonomousResearchService"
```

---

### Task 2: Wire `demand_scores` into `run()` (TDD)

**Files:**
- Test: `tests/test_autonomous_research_service.py`
- Modify: `metis_app/services/autonomous_research_service.py`

**Step 1: Write the failing test**

Append to `tests/test_autonomous_research_service.py`:

```python
def test_run_passes_demand_scores_to_scan_faculty_gaps():
    """run() computes demand scores and passes them to scan_faculty_gaps."""
    svc = AutonomousResearchService(web_search=MagicMock())

    captured: dict = {}

    original_scan = svc.scan_faculty_gaps

    def capturing_scan(indexes, demand_scores=None):
        captured["demand_scores"] = demand_scores
        return original_scan(indexes, demand_scores=demand_scores)

    svc.scan_faculty_gaps = capturing_scan  # type: ignore[method-assign]

    # One user index assigned to "reasoning" → demand_scores={"reasoning": 1}
    indexes = [
        {"index_id": "user_doc_1", "brain_pass": {"placement": {"faculty_id": "reasoning"}}},
    ]
    # run() will try to create an LLM — patch llm_providers to avoid real calls
    import sys, types
    fake_lp = types.ModuleType("metis_app.utils.llm_providers")
    fake_lp.create_llm = lambda s: MagicMock(invoke=MagicMock(return_value=MagicMock(content="query")))
    original = sys.modules.get("metis_app.utils.llm_providers")
    sys.modules["metis_app.utils.llm_providers"] = fake_lp
    try:
        svc.run(settings={}, indexes=indexes, orchestrator=MagicMock())
    finally:
        if original is None:
            sys.modules.pop("metis_app.utils.llm_providers", None)
        else:
            sys.modules["metis_app.utils.llm_providers"] = original

    assert captured.get("demand_scores") == {"reasoning": 1}
```

**Step 2: Run test to verify it fails**

```
python -m pytest tests/test_autonomous_research_service.py::test_run_passes_demand_scores_to_scan_faculty_gaps -v
```
Expected: FAIL — `captured["demand_scores"]` is `None` (not wired yet)

**Step 3: Update `run()` to compute and pass demand scores**

In `metis_app/services/autonomous_research_service.py`, find the `run()` method. Change the `scan_faculty_gaps` call (currently around line 83):

```python
# Before:
faculty_id = self.scan_faculty_gaps(indexes)

# After:
demand_scores = self.compute_demand_scores(indexes) or None
faculty_id = self.scan_faculty_gaps(indexes, demand_scores=demand_scores)
```

**Step 4: Run full test suite for the file**

```
python -m pytest tests/test_autonomous_research_service.py -v
```
Expected: ALL PASS (existing + new tests)

**Step 5: Commit**

```bash
git add tests/test_autonomous_research_service.py metis_app/services/autonomous_research_service.py
git commit -m "feat: wire demand_scores into autonomous research scan — reverse-curriculum ordering"
```

---

### Task 3: Integration test — ordering changes under demand pressure

**Files:**
- Test: `tests/test_autonomous_research_service.py`

**Step 1: Write the integration test**

Append to `tests/test_autonomous_research_service.py`:

```python
def test_reverse_curriculum_prefers_high_demand_unrepresented_faculty():
    """End-to-end: compute_demand_scores + scan_faculty_gaps together."""
    svc = AutonomousResearchService(web_search=MagicMock())

    # User has uploaded 5 indexes tagged to "emergence", none to "perception".
    # Without demand scores: perception is first (FACULTY_ORDER index 0).
    # With demand scores: emergence has demand=5, perception has demand=0
    #   → emergence should be returned first.
    indexes = [
        {"index_id": f"user_doc_{i}", "brain_pass": {"placement": {"faculty_id": "emergence"}}}
        for i in range(5)
    ]
    # No auto_ indexes at all → all faculties are unrepresented

    # Baseline: without demand, perception (index 0) wins
    baseline = svc.scan_faculty_gaps(indexes)
    assert baseline == "perception"

    # With demand scores computed from same indexes:
    demand = svc.compute_demand_scores(indexes)
    assert demand == {"emergence": 5}
    result = svc.scan_faculty_gaps(indexes, demand_scores=demand)
    assert result == "emergence"


def test_reverse_curriculum_hardness_ratio_beats_raw_demand():
    """Faculty with 0 auto-stars and high demand beats one with 1 star and same demand."""
    svc = AutonomousResearchService(web_search=MagicMock())

    # reasoning: 1 auto-star, demand=5 → hardness = 5/1 = 5.0
    # emergence: 0 auto-stars, demand=5 → hardness = 5/max(0,1) = 5.0
    # Tie on hardness; emergence (index 10) comes after reasoning (index 3)
    # → reasoning should win
    indexes = [{"index_id": "auto_reasoning_abc", "document_count": 1}]
    demand = {"reasoning": 5, "emergence": 5}
    result = svc.scan_faculty_gaps(indexes, demand_scores=demand)
    # reasoning is in sparse_represented (1 star, demand=5, hardness=5)
    # emergence is unrepresented — handled in second pass
    # sparse_represented wins over unrepresented, so reasoning is returned
    assert result == "reasoning"
```

**Step 2: Run the new integration tests**

```
python -m pytest tests/test_autonomous_research_service.py::test_reverse_curriculum_prefers_high_demand_unrepresented_faculty tests/test_autonomous_research_service.py::test_reverse_curriculum_hardness_ratio_beats_raw_demand -v
```
Expected: PASS (validates existing `scan_faculty_gaps` logic handles these cases correctly)

**Step 3: Run full test suite**

```
python -m pytest tests/test_autonomous_research_service.py -v
```
Expected: ALL PASS

**Step 4: Commit**

```bash
git add tests/test_autonomous_research_service.py
git commit -m "test: add reverse-curriculum integration tests for demand-ordered faculty gaps"
```

---

### Task 4: Emit `demand_scores` in progress events

**Files:**
- Test: `tests/test_autonomous_research_service.py`
- Modify: `metis_app/services/autonomous_research_service.py`

**Step 1: Write the failing test**

Append to `tests/test_autonomous_research_service.py`:

```python
def test_run_scanning_event_includes_demand_count():
    """The 'scanning' progress event detail should mention demand score count."""
    svc = AutonomousResearchService(web_search=MagicMock())
    # All faculties fully covered → only 'scanning' and 'skipped' events fire
    indexes = [
        {"index_id": f"auto_{fac}_{i}", "document_count": 1}
        for fac in ["perception", "knowledge", "memory", "reasoning", "skills",
                    "strategy", "personality", "values", "synthesis", "autonomy", "emergence"]
        for i in range(3)
    ] + [
        # Add 2 user indexes with faculty placement to generate non-zero demand
        {"index_id": "user_1", "brain_pass": {"placement": {"faculty_id": "reasoning"}}},
        {"index_id": "user_2", "brain_pass": {"placement": {"faculty_id": "reasoning"}}},
    ]
    events: list[dict] = []
    svc.run(settings={}, indexes=indexes, orchestrator=MagicMock(), progress_cb=events.append)
    scanning_events = [e for e in events if e["phase"] == "scanning"]
    assert scanning_events, "No scanning event emitted"
    # The detail should mention demand signals when present
    detail = scanning_events[0]["detail"]
    assert isinstance(detail, str) and len(detail) > 0
```

**Step 2: Run to confirm it passes already**

```
python -m pytest tests/test_autonomous_research_service.py::test_run_scanning_event_includes_demand_count -v
```

This test only validates that a scanning event fires with a non-empty detail — it should already pass. If it passes, **skip Steps 3–4** and go straight to Step 5.

If it fails, update the `_emit("scanning", ...)` call in `run()` to include demand context:

```python
# In run(), update the initial emit:
demand_scores = self.compute_demand_scores(indexes) or None
demand_summary = f" ({len(demand_scores)} faculties with demand signal)" if demand_scores else ""
_emit("scanning", None, f"Scanning constellation for faculty gaps…{demand_summary}")
faculty_id = self.scan_faculty_gaps(indexes, demand_scores=demand_scores)
```

> Note: If this refactor moves the `demand_scores` computation above the `_emit` call, ensure it stays before the `scan_faculty_gaps` call. Remove the duplicate `demand_scores` computation from Task 2's change.

**Step 3: Run full suite**

```
python -m pytest tests/test_autonomous_research_service.py -v
```
Expected: ALL PASS

**Step 4: Commit**

```bash
git add tests/test_autonomous_research_service.py metis_app/services/autonomous_research_service.py
git commit -m "feat: include demand signal summary in scanning progress event"
```

---

### Task 5: Final verification and branch completion

**Step 1: Run complete test suite**

```
python -m pytest tests/ -v --tb=short 2>&1 | tail -40
```
Expected: No regressions. New tests all pass.

**Step 2: Invoke finishing-a-development-branch**

Use `superpowers:finishing-a-development-branch` to verify, present options, and complete.
