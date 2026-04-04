# Parallel Research Subagents Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the parallel research pipeline so concurrent faculty research actually targets distinct faculties instead of all rescanning and picking the same gap.

**Architecture:** Three small surgical fixes. `run_batch` already exists but has two bugs: its lambda ignores the `faculty_id` parameter and passes `indexes=[]`. Fix by adding `target_faculty_id: str | None = None` to `run()` — when set, the scan phase is skipped and that faculty is researched directly. `run_batch` then passes `target_faculty_id=faculty_id`. Also replace the deprecated `asyncio.get_event_loop()` with `asyncio.get_running_loop()`. The orchestrator's gap-collection loop and settings wiring already work correctly.

**Tech Stack:** Python, asyncio, pytest, existing `AutonomousResearchService`, `WorkspaceOrchestrator`.

**Worktree:** `C:\Users\samwe\Documents\metis\.claude\worktrees\parallel-research`

---

### Task 1: Add `target_faculty_id` to `run()` (TDD)

**Files:**
- Test: `tests/test_autonomous_research_service.py`
- Modify: `metis_app/services/autonomous_research_service.py`

**Step 1: Write the failing test**

Append to `tests/test_autonomous_research_service.py`:

```python
def test_run_with_target_faculty_id_skips_scan():
    """run() with target_faculty_id bypasses scan_faculty_gaps and uses the supplied faculty."""
    svc = AutonomousResearchService(web_search=MagicMock())

    scan_called = []
    original_scan = svc.scan_faculty_gaps
    def capturing_scan(*args, **kwargs):
        scan_called.append(True)
        return original_scan(*args, **kwargs)
    svc.scan_faculty_gaps = capturing_scan  # type: ignore[method-assign]

    # All faculties fully covered → normally scan returns None and run() exits early.
    # With target_faculty_id, run() should skip the scan entirely and proceed to query.
    fully_covered = [
        {"index_id": f"auto_{fac}_{i}", "document_count": 1}
        for fac in ["perception", "knowledge", "memory", "reasoning", "skills",
                    "strategy", "personality", "values", "synthesis", "autonomy", "emergence"]
        for i in range(3)
    ]

    events: list[dict] = []
    # run() will try to create LLM — patch it to bail at formulation
    import sys, types
    fake_lp = types.ModuleType("metis_app.utils.llm_providers")
    fake_lp.create_llm = lambda s: MagicMock(invoke=MagicMock(return_value=MagicMock(content="")))
    original = sys.modules.get("metis_app.utils.llm_providers")
    sys.modules["metis_app.utils.llm_providers"] = fake_lp
    try:
        svc.run(
            settings={},
            indexes=fully_covered,
            orchestrator=MagicMock(),
            target_faculty_id="reasoning",
            progress_cb=events.append,
        )
    finally:
        if original is None:
            sys.modules.pop("metis_app.utils.llm_providers", None)
        else:
            sys.modules["metis_app.utils.llm_providers"] = original

    # Scan was NOT called
    assert not scan_called, "scan_faculty_gaps should be skipped when target_faculty_id is set"
    # The formulating event should mention "reasoning"
    formulating = [e for e in events if e["phase"] == "formulating"]
    assert formulating, "Expected a formulating event"
    assert formulating[0]["faculty_id"] == "reasoning"
```

**Step 2: Run test to confirm it fails**

```
cd C:\Users\samwe\Documents\metis\.claude\worktrees\parallel-research
python -m pytest tests/test_autonomous_research_service.py::test_run_with_target_faculty_id_skips_scan -v
```
Expected: FAIL — `TypeError: run() got an unexpected keyword argument 'target_faculty_id'`

**Step 3: Implement `target_faculty_id` in `run()`**

In `metis_app/services/autonomous_research_service.py`, update the `run()` signature and body:

```python
def run(
    self,
    *,
    settings: dict[str, Any],
    indexes: list[dict[str, Any]],
    orchestrator: Any,
    progress_cb: Callable[[ProgressEvent], None] | None = None,
    target_faculty_id: str | None = None,
) -> dict[str, Any] | None:
```

Then in the body, replace the scan block:

```python
# Before (lines 82-88):
_emit("scanning", None, "Scanning constellation for faculty gaps…")
demand_scores = self.compute_demand_scores(indexes) or None  # {} → None so scan uses FACULTY_ORDER fallback
faculty_id = self.scan_faculty_gaps(indexes, demand_scores=demand_scores)
if faculty_id is None:
    _log.debug("autonomous_research: no faculty gaps found, skipping")
    _emit("skipped", None, "Constellation fully covered, skipping")
    return None

# After:
if target_faculty_id is not None:
    faculty_id = target_faculty_id
    _emit("targeted", faculty_id, f"Targeting faculty '{faculty_id}' directly…")
else:
    _emit("scanning", None, "Scanning constellation for faculty gaps…")
    demand_scores = self.compute_demand_scores(indexes) or None  # {} → None so scan uses FACULTY_ORDER fallback
    faculty_id = self.scan_faculty_gaps(indexes, demand_scores=demand_scores)
    if faculty_id is None:
        _log.debug("autonomous_research: no faculty gaps found, skipping")
        _emit("skipped", None, "Constellation fully covered, skipping")
        return None
```

**Step 4: Run tests**

```
python -m pytest tests/test_autonomous_research_service.py::test_run_with_target_faculty_id_skips_scan -v
```
Expected: PASS

```
python -m pytest tests/test_autonomous_research_service.py -v --tb=short
```
Expected: All existing tests still pass (backward compatible — `target_faculty_id` defaults to `None`).

**Step 5: Commit**

```bash
git add tests/test_autonomous_research_service.py metis_app/services/autonomous_research_service.py
git commit -m "feat: add target_faculty_id to run() to skip scan phase in batch mode"
```

---

### Task 2: Fix `run_batch` bugs (TDD)

**Files:**
- Test: `tests/test_autonomous_research_service.py`
- Modify: `metis_app/services/autonomous_research_service.py`

**Step 1: Write the failing tests**

Append to `tests/test_autonomous_research_service.py`:

```python
def test_run_batch_passes_target_faculty_id_to_each_run():
    """run_batch must pass the correct target_faculty_id to each run() call."""
    import asyncio as _asyncio
    svc = AutonomousResearchService(web_search=MagicMock())

    received_faculty_ids: list[str] = []

    def capturing_run(**kwargs):
        fid = kwargs.get("target_faculty_id")
        if fid:
            received_faculty_ids.append(fid)
        return {"faculty_id": fid, "index_id": f"auto_{fid}_x"}

    svc.run = capturing_run  # type: ignore[method-assign]

    _asyncio.run(
        svc.run_batch(
            faculty_ids=["reasoning", "memory", "emergence"],
            settings={},
            orchestrator=MagicMock(),
            concurrency=3,
            request_delay_ms=0,
        )
    )

    assert sorted(received_faculty_ids) == ["emergence", "memory", "reasoning"]


def test_run_batch_respects_semaphore_concurrency():
    """run_batch serialises tasks correctly under concurrency=1."""
    import asyncio as _asyncio
    import threading

    svc = AutonomousResearchService(web_search=MagicMock())
    concurrent_count = [0]
    max_concurrent = [0]
    lock = threading.Lock()

    def slow_run(**kwargs):
        import time
        with lock:
            concurrent_count[0] += 1
            max_concurrent[0] = max(max_concurrent[0], concurrent_count[0])
        time.sleep(0.02)
        with lock:
            concurrent_count[0] -= 1
        return {"faculty_id": kwargs.get("target_faculty_id"), "index_id": "x"}

    svc.run = slow_run  # type: ignore[method-assign]

    _asyncio.run(
        svc.run_batch(
            faculty_ids=["perception", "knowledge", "memory"],
            settings={},
            orchestrator=MagicMock(),
            concurrency=1,
            request_delay_ms=0,
        )
    )

    assert max_concurrent[0] == 1, f"Expected max 1 concurrent, got {max_concurrent[0]}"
```

**Step 2: Run tests to confirm they fail**

```
python -m pytest tests/test_autonomous_research_service.py::test_run_batch_passes_target_faculty_id_to_each_run tests/test_autonomous_research_service.py::test_run_batch_respects_semaphore_concurrency -v
```
Expected: FAIL — `received_faculty_ids` will be empty (lambda ignores faculty_id).

**Step 3: Fix `run_batch`**

In `metis_app/services/autonomous_research_service.py`, replace the `run_batch` method body:

```python
async def run_batch(
    self,
    *,
    faculty_ids: list[str],
    settings: dict[str, Any],
    orchestrator: Any,
    concurrency: int = 1,
    request_delay_ms: int = 500,
    progress_cb: Callable[[ProgressEvent], None] | None = None,
) -> list[dict[str, Any]]:
    """Run research for multiple faculty gaps concurrently.

    Uses an asyncio.Semaphore to cap concurrent tasks. Each task calls
    self.run() in a thread executor to avoid blocking the event loop.
    The target_faculty_id is passed to each run() call so the scan phase
    is bypassed and each task researches its assigned faculty directly.
    """
    import asyncio

    semaphore = asyncio.Semaphore(max(1, concurrency))
    delay_s = max(0, request_delay_ms) / 1000.0
    loop = asyncio.get_running_loop()

    async def _run_one(faculty_id: str) -> dict[str, Any] | None:
        async with semaphore:
            if delay_s > 0:
                await asyncio.sleep(delay_s)
            return await loop.run_in_executor(
                None,
                lambda: self.run(
                    settings=settings,
                    indexes=[],
                    orchestrator=orchestrator,
                    target_faculty_id=faculty_id,
                    progress_cb=progress_cb,
                ),
            )

    tasks = [_run_one(fid) for fid in faculty_ids]
    raw = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in raw if isinstance(r, dict)]
```

Key changes from original:
- `asyncio.get_event_loop()` → `asyncio.get_running_loop()` (not deprecated)
- `target_faculty_id=faculty_id` added to `self.run()` call (was completely missing)
- Comment updated to explain the design

**Step 4: Run all tests**

```
python -m pytest tests/test_autonomous_research_service.py -v --tb=short
```
Expected: All pass. Pay special attention to the two new tests.

**Step 5: Commit**

```bash
git add tests/test_autonomous_research_service.py metis_app/services/autonomous_research_service.py
git commit -m "fix: run_batch now passes target_faculty_id and uses get_running_loop()"
```

---

### Task 3: Integration test — orchestrator concurrent dispatch

**Files:**
- Test: `tests/test_workspace_orchestrator.py`

**Step 1: Write the integration test**

Append to `tests/test_workspace_orchestrator.py` (after the last `test_run_autonomous_research_*` test):

```python
def test_run_autonomous_research_concurrent_dispatches_multiple_faculties():
    """With concurrency=2, run_autonomous_research scans multiple gaps and calls run_batch."""
    import asyncio as _asyncio
    import unittest.mock as um
    from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator

    settings = {
        "assistant_policy": {
            "autonomous_research_enabled": True,
            "autonomous_research_concurrency": 2,
            "autonomous_research_request_delay_ms": 0,
        },
        "llm_provider": "mock",
    }

    orc = WorkspaceOrchestrator()

    # No indexes → all 11 faculties are gaps; orchestrator should collect 2*2=4 at most
    # and call run_batch with multiple faculty IDs.
    run_batch_calls: list[dict] = []

    async def fake_run_batch(**kwargs):
        run_batch_calls.append(kwargs)
        return [{"faculty_id": fid, "index_id": f"auto_{fid}_x"}
                for fid in kwargs.get("faculty_ids", [])]

    mock_svc = um.MagicMock()
    mock_svc.scan_faculty_gaps.side_effect = lambda indexes, **kw: (
        "perception" if not any(i["index_id"] == "auto_perception_placeholder" for i in indexes)
        else "knowledge" if not any(i["index_id"] == "auto_knowledge_placeholder" for i in indexes)
        else None
    )
    mock_svc.run_batch = fake_run_batch

    MockSvcClass = um.MagicMock(return_value=mock_svc)

    with um.patch(
        "metis_app.services.workspace_orchestrator.AutonomousResearchService",
        MockSvcClass,
    ), um.patch(
        "metis_app.utils.web_search.create_web_search",
        return_value=um.MagicMock(),
    ), um.patch.object(orc, "list_indexes", return_value=[]):
        result = orc.run_autonomous_research(settings)

    assert run_batch_calls, "run_batch was not called"
    assert len(run_batch_calls[0]["faculty_ids"]) >= 2, (
        f"Expected ≥2 faculty IDs dispatched, got {run_batch_calls[0]['faculty_ids']}"
    )
```

**Step 2: Run the test**

```
python -m pytest tests/test_workspace_orchestrator.py::test_run_autonomous_research_concurrent_dispatches_multiple_faculties -v --tb=short
```
Expected: PASS (orchestrator already collects multiple gaps correctly).

If it fails, check the mock's `scan_faculty_gaps.side_effect` — adjust to return the right faculty names based on the placeholder logic the orchestrator uses.

**Step 3: Run the full workspace orchestrator test file**

```
python -m pytest tests/test_workspace_orchestrator.py -v --tb=short 2>&1 | tail -20
```
Expected: No regressions.

**Step 4: Commit**

```bash
git add tests/test_workspace_orchestrator.py
git commit -m "test: verify concurrent dispatch sends multiple faculty IDs to run_batch"
```

---

### Task 4: Fix DeprecationWarning in existing run_batch tests

**Files:**
- Modify: `tests/test_autonomous_research_service.py`

**Step 1: Find the deprecated calls**

```
grep -n "get_event_loop" tests/test_autonomous_research_service.py
```
Expected: Lines 166 and 235 use `asyncio.get_event_loop().run_until_complete(...)`.

**Step 2: Replace with `asyncio.run()`**

In `tests/test_autonomous_research_service.py`, update both callers from:

```python
asyncio.get_event_loop().run_until_complete(
    svc.run_batch(...)
)
```

To:

```python
asyncio.run(
    svc.run_batch(...)
)
```

**Step 3: Run the affected tests**

```
python -m pytest tests/test_autonomous_research_service.py::test_run_batch_returns_list_of_results tests/test_autonomous_research_service.py::test_run_batch_threads_progress_cb_to_run -v --tb=short
```
Expected: PASS, no DeprecationWarning.

**Step 4: Run full suite**

```
python -m pytest tests/ --tb=no -q 2>&1 | tail -5
```
Expected: 840+ passed, 12 skipped, 0 failures, DeprecationWarning count reduced.

**Step 5: Commit**

```bash
git add tests/test_autonomous_research_service.py
git commit -m "test: replace deprecated get_event_loop with asyncio.run in run_batch tests"
```

---

### Task 5: Final verification and branch completion

**Step 1: Run complete test suite**

```
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: All pass, no new failures.

**Step 2: Invoke finishing-a-development-branch**

Use `superpowers:finishing-a-development-branch` to verify, present options, and complete.
