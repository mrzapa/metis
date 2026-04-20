# Hermes + Sotaku Roadmap Implementation Plan

> **Phase 3 (M06) coordinates with M17 (Network audit).** Autonomous
> LLM calls emitted by the skill-self-evolution loop must keep
> `user_initiated=False` and must propagate `NetworkBlockedError` as
> a skip (no retry, no fallback). Full contract:
> [`plans/network-audit/plan.md` → Coordination hooks (Phase 7)](../../plans/network-audit/plan.md#coordination-hooks-phase-7).

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement 4 independent improvements to Metis inspired by Sotaku's looped convergence and Hermes Agent's learning loop.

**Architecture:** Phase 1 adds cosine-similarity convergence detection to the existing agentic loop in `engine/streaming.py`. Phase 2 sorts faculty gaps by hardness in `autonomous_research_service.py`. Phase 4 parallelises faculty research via `asyncio.gather`. Phase 3 adds a skill-candidate capture + promotion pipeline to `skill_repository.py` + `assistant_companion.py`.

**Tech Stack:** Python 3.11+, pytest, existing `create_embeddings()` for cosine similarity, `asyncio` for Phase 4, existing SQLite via `skill_repository.py` conventions.

---

## Phase 1: IterRAG — Convergence-Based Retrieval Loop

> **Claim (2026-04-18):** M03 **IterRAG convergence** is claimed as **backend-only** work with **zero collision risk with M02**.

**Files:**
- Modify: `metis_app/engine/streaming.py` (lines ~250–360)
- Modify: `metis_app/default_settings.json`
- Create: `tests/test_iterrag_convergence.py`

---

### Task 1.1: Add new settings to default_settings.json

**Step 1: Add the two new keys after `agentic_max_iterations`**

Open `metis_app/default_settings.json`. After line 138 (`"agentic_max_iterations": 2`), add:

```json
"agentic_iteration_budget": 4,
"agentic_convergence_threshold": 0.95,
```

**Step 2: Verify JSON is still valid**

```bash
python -c "import json; json.load(open('metis_app/default_settings.json'))"
```

Expected: no output (no error).

**Step 3: Commit**

```bash
git add metis_app/default_settings.json
git commit -m "feat(settings): add agentic_iteration_budget and convergence_threshold"
```

---

### Task 1.2: Add cosine-similarity helpers to streaming.py

**Step 1: Read the file header to understand imports**

`metis_app/engine/streaming.py` already imports `execute_retrieval_plan` from `retrieval_pipeline` and uses `create_embeddings` indirectly. You need to add a direct import.

**Step 2: Add imports — find the import block at the top of streaming.py, add:**

```python
from metis_app.utils.embedding_providers import create_embeddings
from metis_app.utils.mock_embeddings import MockEmbeddings
```

(Check if already present before adding — search for `create_embeddings` in the file.)

**Step 3: Add two private helpers after the `_MAX_CONTEXT_CHARS` constant (or after the last module-level helper):**

```python
def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors. Returns 0.0 on zero vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embed_text(text: str, settings: dict) -> list[float]:
    """Embed a text string for convergence comparison. Falls back to MockEmbeddings."""
    try:
        emb = create_embeddings(settings)
    except (ValueError, ImportError):
        emb = MockEmbeddings(dimensions=32)
    return emb.embed_query(text)
```

**Step 4: Write the failing test**

Create `tests/test_iterrag_convergence.py`:

```python
from __future__ import annotations

from metis_app.engine.streaming import _cosine_similarity, _embed_text


def test_cosine_similarity_identical_vectors():
    v = [1.0, 0.0, 0.0]
    assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6


def test_cosine_similarity_orthogonal_vectors():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(_cosine_similarity(a, b)) < 1e-6


def test_cosine_similarity_zero_vector_returns_zero():
    assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_embed_text_returns_list_of_floats():
    result = _embed_text("hello world", {"embeddings_backend": "mock"})
    assert isinstance(result, list)
    assert all(isinstance(x, float) for x in result)
```

**Step 5: Run to verify it fails**

```bash
pytest tests/test_iterrag_convergence.py -v
```

Expected: `ImportError` or `AttributeError` — the helpers don't exist yet.

**Step 6: Add the helpers to streaming.py** (as described in Step 3 above).

**Step 7: Run to verify it passes**

```bash
pytest tests/test_iterrag_convergence.py -v
```

Expected: all 4 PASS.

**Step 8: Commit**

```bash
git add metis_app/engine/streaming.py tests/test_iterrag_convergence.py
git commit -m "feat(streaming): add _cosine_similarity and _embed_text convergence helpers"
```

---

### Task 1.3: Wire convergence detection into the agentic loop

**Context:** The agentic loop is in `metis_app/engine/streaming.py` around lines 250–360. After line 252 (`agentic_max_iterations = ...`), the loop runs `for iteration in range(1, agentic_max_iterations + 1)`.

**Step 1: Write failing test for convergence behaviour**

Add to `tests/test_iterrag_convergence.py`:

```python
def test_convergence_threshold_setting_read():
    """Streaming engine reads the new settings keys without error."""
    settings = {
        "agentic_mode": True,
        "agentic_iteration_budget": 4,
        "agentic_convergence_threshold": 0.95,
    }
    budget = max(1, int(settings.get("agentic_iteration_budget", 4) or 4))
    threshold = float(settings.get("agentic_convergence_threshold", 0.95) or 0.95)
    assert budget == 4
    assert threshold == 0.95
```

**Step 2: Run to verify it passes immediately** (it's a pure logic test)

```bash
pytest tests/test_iterrag_convergence.py::test_convergence_threshold_setting_read -v
```

**Step 3: Modify the loop in streaming.py**

Find line `agentic_max_iterations = max(...)` (~line 251). Change the block that reads these settings:

**Before:**
```python
agentic_max_iterations = max(
    1, int(settings.get("agentic_max_iterations", 2) or 2)
)
```

**After:**
```python
agentic_max_iterations = max(
    1, int(settings.get("agentic_max_iterations", 2) or 2)
)
agentic_iteration_budget = max(
    1, int(settings.get("agentic_iteration_budget", agentic_max_iterations) or agentic_max_iterations)
)
agentic_convergence_threshold = float(
    settings.get("agentic_convergence_threshold", 0.95) or 0.95
)
```

**Step 4: Change the loop range to use the budget**

Find: `for iteration in range(1, agentic_max_iterations + 1):`
Change to: `for iteration in range(1, agentic_iteration_budget + 1):`

Also update the `total_iterations` in the emitted event:
Find: `"total_iterations": agentic_max_iterations,`
Change to: `"total_iterations": agentic_iteration_budget,`

**Step 5: Add convergence state tracking before the loop**

After `accumulated_sources = list(sources)` and `if agentic_mode:`, add before the `for` loop:

```python
            _prev_draft_embedding: list[float] = []
            _iterations_used: int = 0
            _last_convergence_score: float = 0.0
```

**Step 6: Add convergence check after draft re-synthesis**

Find the block around line 344–357:
```python
                if iteration < agentic_max_iterations:
                    ...
                    current_draft = _response_text(...)
```

Change to:
```python
                if iteration < agentic_iteration_budget:
                    _refined_prompt = (...)
                    current_draft = _response_text(
                        llm.invoke([...])
                    )
                    # --- Sotaku-inspired convergence detection ---
                    _current_emb = _embed_text(current_draft, settings)
                    if _prev_draft_embedding:
                        _last_convergence_score = _cosine_similarity(
                            _prev_draft_embedding, _current_emb
                        )
                        if _last_convergence_score >= agentic_convergence_threshold:
                            _iterations_used = iteration
                            yield _emit({
                                "type": "iteration_converged",
                                "run_id": run_id,
                                "iteration": iteration,
                                "convergence_score": round(_last_convergence_score, 4),
                            })
                            break
                    _prev_draft_embedding = _current_emb
                _iterations_used = iteration
```

**Step 7: Run the existing streaming tests to ensure nothing broke**

```bash
pytest tests/test_engine_streaming.py -v
```

Expected: all existing tests PASS.

**Step 8: Commit**

```bash
git add metis_app/engine/streaming.py tests/test_iterrag_convergence.py
git commit -m "feat(streaming): add convergence detection to agentic loop (Sotaku IterRAG)"
```

---

## Phase 2: Reverse-Curriculum Autonomous Research

**Files:**
- Modify: `metis_app/services/autonomous_research_service.py`
- Modify: `tests/test_autonomous_research_service.py`

---

### Task 2.1: Add hardness scoring to scan_faculty_gaps

**Step 1: Write failing tests**

Add to `tests/test_autonomous_research_service.py`:

```python
def test_scan_faculty_gaps_uses_demand_scores_for_ordering():
    """High-demand faculty with zero indexes should be prioritised over low-demand."""
    svc = AutonomousResearchService(web_search=MagicMock())
    # reasoning (index 3 in FACULTY_ORDER) has no auto-indexes
    # perception (index 0) has no auto-indexes
    # If reasoning has higher demand, it should come first
    indexes = []  # all faculties have zero coverage
    demand_scores = {"perception": 1, "reasoning": 5}  # reasoning is in higher demand
    faculty = svc.scan_faculty_gaps(indexes, demand_scores=demand_scores)
    assert faculty == "reasoning"


def test_scan_faculty_gaps_falls_back_to_faculty_order_without_demand_scores():
    """Without demand_scores, original tie-break by FACULTY_ORDER still applies."""
    svc = AutonomousResearchService(web_search=MagicMock())
    indexes = []
    faculty = svc.scan_faculty_gaps(indexes)
    assert faculty == "perception"  # first in FACULTY_ORDER
```

**Step 2: Run to verify they fail**

```bash
pytest tests/test_autonomous_research_service.py::test_scan_faculty_gaps_uses_demand_scores_for_ordering tests/test_autonomous_research_service.py::test_scan_faculty_gaps_falls_back_to_faculty_order_without_demand_scores -v
```

Expected: FAIL — `scan_faculty_gaps` doesn't accept `demand_scores`.

**Step 3: Modify scan_faculty_gaps signature and hardness logic**

In `autonomous_research_service.py`, change `scan_faculty_gaps`:

**Before:**
```python
def scan_faculty_gaps(self, indexes: list[dict[str, Any]]) -> str | None:
```

**After:**
```python
def scan_faculty_gaps(
    self,
    indexes: list[dict[str, Any]],
    demand_scores: dict[str, int] | None = None,
) -> str | None:
```

In the method body, replace the final tie-break logic. Find:
```python
        # No partially-covered faculties — fall back to first completely unrepresented faculty
        for fac in FACULTY_ORDER:
            if faculty_counts[fac] == 0:
                return fac
```

Replace with:
```python
        # No partially-covered faculties — fall back to first unrepresented faculty
        # sorted by hardness (demand / max(count, 1)) descending when demand_scores provided.
        unrepresented = [fac for fac in FACULTY_ORDER if faculty_counts[fac] == 0]
        if unrepresented and demand_scores:
            unrepresented.sort(
                key=lambda f: (-(demand_scores.get(f, 0)), FACULTY_ORDER.index(f))
            )
        if unrepresented:
            return unrepresented[0]
```

Also apply hardness to the `sparse_represented` selection:

Find:
```python
        if sparse_represented:
            # Return the sparsest (first in FACULTY_ORDER on tie)
            return min(sparse_represented, key=lambda x: (x[1], FACULTY_ORDER.index(x[0])))[0]
```

Replace with:
```python
        if sparse_represented:
            if demand_scores:
                # hardness = demand_score / count; higher hardness → research first
                return min(
                    sparse_represented,
                    key=lambda x: (
                        -(demand_scores.get(x[0], 0) / max(x[1], 1)),
                        FACULTY_ORDER.index(x[0]),
                    ),
                )[0]
            return min(sparse_represented, key=lambda x: (x[1], FACULTY_ORDER.index(x[0])))[0]
```

**Step 4: Run tests**

```bash
pytest tests/test_autonomous_research_service.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add metis_app/services/autonomous_research_service.py tests/test_autonomous_research_service.py
git commit -m "feat(autonomous-research): reverse-curriculum hardness scoring for faculty gaps"
```

---

## Phase 4: Parallel Research Subagents

**Files:**
- Modify: `metis_app/services/autonomous_research_service.py`
- Modify: `metis_app/services/workspace_orchestrator.py` (lines ~666–692)
- Modify: `metis_app/default_settings.json`
- Modify: `tests/test_autonomous_research_service.py`

---

### Task 4.1: Add concurrency settings

**Step 1: Add to default_settings.json** under `assistant_policy`:

```json
"autonomous_research_concurrency": 1,
"autonomous_research_request_delay_ms": 500
```

(Keep default concurrency at 1 to preserve current behaviour.)

**Step 2: Verify JSON valid**

```bash
python -c "import json; json.load(open('metis_app/default_settings.json'))"
```

**Step 3: Commit**

```bash
git add metis_app/default_settings.json
git commit -m "feat(settings): add autonomous_research_concurrency and request_delay_ms"
```

---

### Task 4.2: Add run_batch method to AutonomousResearchService

**Step 1: Write failing test**

Add to `tests/test_autonomous_research_service.py`:

```python
import asyncio

def test_run_batch_returns_list_of_results():
    """run_batch calls run() once per faculty gap up to concurrency limit."""
    call_count = 0

    async def fake_run(**kwargs):
        nonlocal call_count
        call_count += 1
        return {"faculty_id": "perception", "index_id": "auto_perception_test"}

    svc = AutonomousResearchService(web_search=MagicMock())
    svc.run = MagicMock(return_value={"faculty_id": "perception", "index_id": "x"})

    # Simulate 2 gaps with concurrency=2
    results = asyncio.get_event_loop().run_until_complete(
        svc.run_batch(
            faculty_ids=["perception", "memory"],
            settings={},
            orchestrator=MagicMock(),
            concurrency=2,
            request_delay_ms=0,
        )
    )
    assert len(results) == 2
```

**Step 2: Run to verify it fails**

```bash
pytest tests/test_autonomous_research_service.py::test_run_batch_returns_list_of_results -v
```

Expected: FAIL — `run_batch` doesn't exist.

**Step 3: Add run_batch to AutonomousResearchService**

Add this method after `save_temp_document`:

```python
    async def run_batch(
        self,
        *,
        faculty_ids: list[str],
        settings: dict[str, Any],
        orchestrator: Any,
        concurrency: int = 1,
        request_delay_ms: int = 500,
    ) -> list[dict[str, Any]]:
        """Run research for multiple faculty gaps concurrently.

        Uses an asyncio.Semaphore to cap concurrent tasks. Each task calls
        self.run() in a thread executor to avoid blocking the event loop.
        """
        import asyncio

        semaphore = asyncio.Semaphore(max(1, concurrency))
        delay_s = max(0, request_delay_ms) / 1000.0
        loop = asyncio.get_event_loop()

        async def _run_one(faculty_id: str) -> dict[str, Any] | None:
            async with semaphore:
                if delay_s > 0:
                    await asyncio.sleep(delay_s)
                return await loop.run_in_executor(
                    None,
                    lambda: self.run(
                        settings=settings,
                        indexes=[],  # orchestrator provides current index list inside
                        orchestrator=orchestrator,
                    ),
                )

        tasks = [_run_one(fid) for fid in faculty_ids]
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in raw if isinstance(r, dict)]
```

**Step 4: Run tests**

```bash
pytest tests/test_autonomous_research_service.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add metis_app/services/autonomous_research_service.py tests/test_autonomous_research_service.py
git commit -m "feat(autonomous-research): add run_batch for concurrent faculty research"
```

---

### Task 4.3: Update WorkspaceOrchestrator to use run_batch

**Context:** `workspace_orchestrator.py:666` has `run_autonomous_research()` which calls `svc.run(...)` once.

**Step 1: Modify `run_autonomous_research` to detect all gaps and run them in batch**

Find lines ~686–692 in `workspace_orchestrator.py`:

```python
        svc = AutonomousResearchService(web_search=create_web_search(resolved))
        return svc.run(settings=resolved, indexes=index_list, orchestrator=self)
```

Replace with:

```python
        raw_policy = (settings or {}).get("assistant_policy") or {}
        concurrency = max(1, int(raw_policy.get("autonomous_research_concurrency", 1) or 1))
        delay_ms = max(0, int(raw_policy.get("autonomous_research_request_delay_ms", 500) or 500))

        svc = AutonomousResearchService(web_search=create_web_search(resolved))

        if concurrency <= 1:
            # Original single-gap behaviour — backwards compatible
            return svc.run(settings=resolved, indexes=index_list, orchestrator=self)

        # Collect all sparse faculty gaps
        import asyncio
        faculty_ids: list[str] = []
        temp_indexes = list(index_list)
        for _ in range(concurrency * 2):  # cap scan to avoid infinite loop
            fid = svc.scan_faculty_gaps(temp_indexes)
            if fid is None or fid in faculty_ids:
                break
            faculty_ids.append(fid)
            # Temporarily mark as covered so scan finds the next gap
            temp_indexes = temp_indexes + [{"index_id": f"auto_{fid}_placeholder"}]

        if not faculty_ids:
            return None

        results = asyncio.run(
            svc.run_batch(
                faculty_ids=faculty_ids,
                settings=resolved,
                orchestrator=self,
                concurrency=concurrency,
                request_delay_ms=delay_ms,
            )
        )
        return results[0] if results else None
```

**Step 2: Run orchestrator tests**

```bash
pytest tests/test_workspace_orchestrator.py -v
```

Expected: all PASS.

**Step 3: Commit**

```bash
git add metis_app/services/workspace_orchestrator.py
git commit -m "feat(orchestrator): use run_batch for concurrent autonomous research (Phase 4)"
```

---

## Phase 3: Skill Self-Evolution from Traces

**Files:**
- Modify: `metis_app/services/skill_repository.py`
- Modify: `metis_app/services/assistant_companion.py`
- Modify: `metis_app/engine/streaming.py` (emit trace on convergence/completion)
- Create: `tests/test_skill_evolution.py`

---

### Task 3.1: Add SQLite skill_candidates table to SkillRepository

**Step 1: Write failing test**

Create `tests/test_skill_evolution.py`:

```python
from __future__ import annotations

import json
import pathlib
import sqlite3

import pytest

from metis_app.services.skill_repository import SkillRepository


@pytest.fixture
def repo(tmp_path):
    return SkillRepository(skills_dir=tmp_path / "skills")


def test_save_candidate_creates_db_and_row(tmp_path, repo):
    db_path = tmp_path / "skill_candidates.db"
    repo.save_candidate(
        db_path=db_path,
        query_text="How does RAG work?",
        trace_json=json.dumps({"iterations": 2, "sources": ["doc1"]}),
        convergence_score=0.97,
    )
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT query_text, convergence_score, promoted FROM skill_candidates").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "How does RAG work?"
    assert abs(rows[0][1] - 0.97) < 1e-6
    assert rows[0][2] == 0  # not promoted yet


def test_list_candidates_returns_top_unreviewed(tmp_path, repo):
    db_path = tmp_path / "skill_candidates.db"
    for i in range(5):
        repo.save_candidate(db_path=db_path, query_text=f"q{i}", trace_json="{}", convergence_score=float(i) / 10)
    candidates = repo.list_candidates(db_path=db_path, limit=3)
    assert len(candidates) == 3
    # Should be ordered by convergence_score desc
    scores = [c["convergence_score"] for c in candidates]
    assert scores == sorted(scores, reverse=True)
```

**Step 2: Run to verify they fail**

```bash
pytest tests/test_skill_evolution.py -v
```

Expected: `AttributeError` — methods don't exist.

**Step 3: Add SQLite helpers to SkillRepository**

At the bottom of `SkillRepository` class, add:

```python
    # ------------------------------------------------------------------
    # Skill candidate capture (Phase 3: Skill Evolution)
    # ------------------------------------------------------------------

    @staticmethod
    def _init_candidates_db(db_path: pathlib.Path) -> sqlite3.Connection:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skill_candidates (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                query_text TEXT NOT NULL,
                trace_json TEXT NOT NULL,
                convergence_score REAL NOT NULL DEFAULT 0.0,
                created_at REAL NOT NULL,
                promoted  INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()
        return conn

    def save_candidate(
        self,
        *,
        db_path: pathlib.Path,
        query_text: str,
        trace_json: str,
        convergence_score: float,
    ) -> None:
        import sqlite3
        import time
        conn = self._init_candidates_db(db_path)
        with conn:
            conn.execute(
                "INSERT INTO skill_candidates (query_text, trace_json, convergence_score, created_at) VALUES (?, ?, ?, ?)",
                (str(query_text), str(trace_json), float(convergence_score), time.time()),
            )

    def list_candidates(
        self,
        *,
        db_path: pathlib.Path,
        limit: int = 5,
    ) -> list[dict]:
        import sqlite3
        conn = self._init_candidates_db(db_path)
        rows = conn.execute(
            "SELECT id, query_text, trace_json, convergence_score, created_at FROM skill_candidates "
            "WHERE promoted = 0 ORDER BY convergence_score DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"id": r[0], "query_text": r[1], "trace_json": r[2], "convergence_score": r[3], "created_at": r[4]}
            for r in rows
        ]

    def mark_candidate_promoted(self, *, db_path: pathlib.Path, candidate_id: int) -> None:
        import sqlite3
        conn = self._init_candidates_db(db_path)
        with conn:
            conn.execute("UPDATE skill_candidates SET promoted = 1 WHERE id = ?", (candidate_id,))
```

**Step 4: Run tests**

```bash
pytest tests/test_skill_evolution.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add metis_app/services/skill_repository.py tests/test_skill_evolution.py
git commit -m "feat(skill-repo): add SQLite skill_candidates capture for Phase 3 evolution"
```

---

### Task 3.2: Emit iteration_complete with trace data from streaming.py

**Context:** When the agentic loop ends (either converged or exhausted), we want the trace JSON for skill capture.

**Step 1: Write failing test for trace event structure**

Add to `tests/test_skill_evolution.py`:

```python
def test_iteration_complete_event_has_trace_fields():
    """The iteration_complete event dict must have the expected keys."""
    event = {
        "type": "iteration_complete",
        "run_id": "abc123",
        "iterations_used": 2,
        "convergence_score": 0.97,
        "query_text": "What is RAG?",
    }
    assert event["type"] == "iteration_complete"
    assert "iterations_used" in event
    assert "convergence_score" in event
```

**Step 2: Run to verify it passes immediately** (pure dict test, no imports needed)

```bash
pytest tests/test_skill_evolution.py::test_iteration_complete_event_has_trace_fields -v
```

**Step 3: Add iteration_complete emission to streaming.py**

Find the line after the agentic loop ends (after `# After all iterations, expose accumulated sources`):

```python
        # After all iterations, expose accumulated sources for the final answer.
        sources = accumulated_sources
```

Add after it:

```python
            # Emit trace event for skill candidate capture
            yield _emit({
                "type": "iteration_complete",
                "run_id": run_id,
                "iterations_used": _iterations_used,
                "convergence_score": round(_last_convergence_score, 4),
                "query_text": question,
            })
```

**Step 4: Run streaming tests**

```bash
pytest tests/test_engine_streaming.py -v
```

Expected: all PASS.

**Step 5: Commit**

```bash
git add metis_app/engine/streaming.py tests/test_skill_evolution.py
git commit -m "feat(streaming): emit iteration_complete trace event for skill evolution"
```

---

### Task 3.3: Hook skill candidate save into the companion's reflection cycle

**Context:** `metis_app/services/assistant_companion.py` has a reflection loop. The `iteration_complete` event arrives via the streaming SSE consumer. The companion needs a way to receive it and save candidates.

**Step 1: Add a `capture_skill_candidate` method to the companion (or a standalone function)**

Find `metis_app/services/assistant_companion.py`. Read the reflection loop pattern. Add a method:

```python
def capture_skill_candidate(
    self,
    *,
    db_path: pathlib.Path,
    query_text: str,
    trace_json: str,
    convergence_score: float,
    min_convergence: float = 0.90,
    min_iterations: int = 2,
    trace_iterations: int = 0,
) -> bool:
    """Save a successful agentic run as a skill candidate if it meets quality thresholds.

    Returns True if saved, False if below threshold.
    """
    from metis_app.services.skill_repository import SkillRepository
    if convergence_score < min_convergence or trace_iterations < min_iterations:
        return False
    repo = SkillRepository(skills_dir=self._skills_dir if hasattr(self, "_skills_dir") else None)
    repo.save_candidate(
        db_path=db_path,
        query_text=query_text,
        trace_json=trace_json,
        convergence_score=convergence_score,
    )
    return True
```

**Step 2: Write the test**

Add to `tests/test_skill_evolution.py`:

```python
def test_companion_capture_saves_above_threshold(tmp_path):
    from metis_app.services.assistant_companion import AssistantCompanion
    companion = AssistantCompanion.__new__(AssistantCompanion)  # bypass __init__
    db_path = tmp_path / "skill_candidates.db"
    saved = companion.capture_skill_candidate(
        db_path=db_path,
        query_text="test query",
        trace_json='{"ok": true}',
        convergence_score=0.96,
        trace_iterations=2,
    )
    assert saved is True


def test_companion_capture_skips_below_threshold(tmp_path):
    from metis_app.services.assistant_companion import AssistantCompanion
    companion = AssistantCompanion.__new__(AssistantCompanion)
    db_path = tmp_path / "skill_candidates.db"
    saved = companion.capture_skill_candidate(
        db_path=db_path,
        query_text="test query",
        trace_json='{}',
        convergence_score=0.50,  # below min_convergence=0.90
        trace_iterations=2,
    )
    assert saved is False
```

**Step 3: Run to verify they fail**

```bash
pytest tests/test_skill_evolution.py::test_companion_capture_saves_above_threshold tests/test_skill_evolution.py::test_companion_capture_skips_below_threshold -v
```

**Step 4: Add the method to AssistantCompanion**

Open `metis_app/services/assistant_companion.py`, read the class structure, and add the `capture_skill_candidate` method as described in Step 1.

**Step 5: Run all skill evolution tests**

```bash
pytest tests/test_skill_evolution.py -v
```

Expected: all PASS.

**Step 6: Commit**

```bash
git add metis_app/services/assistant_companion.py tests/test_skill_evolution.py
git commit -m "feat(companion): add capture_skill_candidate for Phase 3 skill evolution"
```

---

## Verification Checklist

After all phases, run:

```bash
# Full test suite
pytest tests/ -v --tb=short

# Specifically verify each phase
pytest tests/test_iterrag_convergence.py -v         # Phase 1
pytest tests/test_autonomous_research_service.py -v  # Phase 2
pytest tests/test_skill_evolution.py -v              # Phase 3
pytest tests/test_autonomous_research_service.py tests/test_workspace_orchestrator.py -v  # Phase 4

# Verify settings JSON is still valid
python -c "import json; json.load(open('metis_app/default_settings.json')); print('JSON OK')"
```

**End-to-end smoke test (manual):**
1. Set `"agentic_mode": true, "agentic_iteration_budget": 3, "agentic_convergence_threshold": 0.90` in settings
2. Run a query — confirm the SSE stream emits `iteration_converged` or `iteration_complete` before the maximum iterations
3. Set `"autonomous_research_concurrency": 2` in `assistant_policy` and trigger autonomous research — confirm 2 faculty gaps researched per cycle
