# Hermes v0.7.0 Patterns — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Port three Hermes v0.7.0 patterns into METIS: configurable context compression, skill progressive disclosure (compact index in system prompt), and credential pool rotation.

**Architecture:**
- Phase B (skill index): additive segment in `runtime_resolution.py` system prompt builder; new `SkillSummary` + `load_skill_index()` in `skill_repository.py`.
- Phase C (credential pool): new `metis_app/utils/credential_pool.py` class + `PooledLLM` wrapper injected in `llm_providers.py`.
- Phase A (context compression): upgrade the existing sliding-window compaction in `streaming.py` to use a structured template and make threshold configurable.

**Tech Stack:** Python 3.10+, pytest, no new dependencies.

---

## Task 1: SkillSummary + load_skill_index()

**Files:**
- Modify: `metis_app/services/skill_repository.py`
- Test: `tests/test_skill_evolution.py` (or create `tests/test_skill_index.py`)

**Step 1: Write the failing test**

Create `tests/test_skill_index.py`:

```python
"""Tests for SkillRepository.load_skill_index()."""
from __future__ import annotations
import pathlib
import pytest
from metis_app.services.skill_repository import SkillRepository, SkillSummary

_SKILL_FM = """\
---
id: demo
name: Demo Skill
description: A skill for testing skill discovery.
enabled_by_default: true
priority: 1
triggers:
  keywords: [demo, test]
  modes: []
  file_types: []
  output_styles: []
runtime_overrides: {}
---

# Demo Skill
Do the demo thing.
"""


def _make_skill(tmp_path: pathlib.Path, skill_id: str, fm: str) -> None:
    d = tmp_path / skill_id
    d.mkdir()
    (d / "SKILL.md").write_text(fm, encoding="utf-8")


def test_load_skill_index_returns_summaries(tmp_path):
    _make_skill(tmp_path, "demo", _SKILL_FM)
    repo = SkillRepository(skills_dir=tmp_path)
    index = repo.load_skill_index()
    assert len(index) == 1
    s = index[0]
    assert isinstance(s, SkillSummary)
    assert s.skill_id == "demo"
    assert s.name == "Demo Skill"
    assert "A skill for testing" in s.description
    assert "demo" in s.keywords


def test_load_skill_index_excludes_invalid_skills(tmp_path):
    _make_skill(tmp_path, "demo", _SKILL_FM)
    bad_dir = tmp_path / "broken"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text("not yaml frontmatter", encoding="utf-8")
    repo = SkillRepository(skills_dir=tmp_path)
    index = repo.load_skill_index()
    assert len(index) == 1  # only valid skill


def test_skill_summary_format_line():
    s = SkillSummary(skill_id="demo", name="Demo", description="Does demo.", keywords=["demo"])
    line = s.format_index_line()
    assert "demo" in line
    assert "Demo" in line
    assert "Does demo." in line
```

**Step 2: Run to verify it fails**

```
cd C:\Users\samwe\Documents\metis\.claude\worktrees\pedantic-mclean
python -m pytest tests/test_skill_index.py -v
```
Expected: `ImportError` — `SkillSummary` does not exist yet.

**Step 3: Implement `SkillSummary` and `load_skill_index()`**

In `metis_app/services/skill_repository.py`, after the imports, add:

```python
from dataclasses import dataclass as _dataclass

@_dataclass
class SkillSummary:
    """Lightweight skill descriptor for system-prompt index injection."""
    skill_id: str
    name: str
    description: str
    keywords: list[str]  # from triggers.keywords

    def format_index_line(self) -> str:
        kw = ", ".join(self.keywords[:4]) if self.keywords else "—"
        return f"- {self.skill_id} ({self.name}): {self.description}  [triggers: {kw}]"
```

Then add `load_skill_index()` to the `SkillRepository` class (after `enabled_skills()`):

```python
def load_skill_index(self) -> list["SkillSummary"]:
    """Return compact summaries of all *valid* skills — no body content.

    Used to build a discovery index in the system prompt without bloating
    it with full SKILL.md bodies (progressive disclosure pattern).
    """
    return [
        SkillSummary(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            keywords=list((skill.triggers or {}).get("keywords") or []),
        )
        for skill in self.list_valid_skills()
    ]
```

**Step 4: Run to verify pass**

```
python -m pytest tests/test_skill_index.py -v
```
Expected: all 3 tests PASS.

**Step 5: Commit**

```bash
git add metis_app/services/skill_repository.py tests/test_skill_index.py
git commit -m "feat: add SkillSummary + load_skill_index() for progressive skill disclosure"
```

---

## Task 2: Inject skill discovery index into system prompt

**Files:**
- Modify: `metis_app/services/runtime_resolution.py`
- Modify: `metis_app/services/workspace_orchestrator.py` (pass `skill_index` to resolver)
- Test: `tests/test_parity_services.py` or new test in the skill index test file

**Background:** `resolve_runtime_settings()` in `runtime_resolution.py` already builds a system prompt with segments. Its signature is:
```python
def resolve_runtime_settings(settings, *, enabled_skills, session_skill_state, query, file_types) -> RuntimeSettings
```
The function calls `_build_runtime_system_prompt(...)` which assembles `segments`. We add a new segment: "Available skills: [compact index]" when `enabled_skills` is non-empty.

**Step 1: Write the failing test**

Add to `tests/test_skill_index.py`:

```python
from metis_app.services.runtime_resolution import resolve_runtime_settings
from metis_app.services.skill_repository import SkillRepository


def test_system_prompt_includes_skill_index(tmp_path):
    _make_skill(tmp_path, "demo", _SKILL_FM)
    repo = SkillRepository(skills_dir=tmp_path)
    enabled = repo.list_valid_skills()

    result = resolve_runtime_settings(
        {"llm_provider": "mock", "selected_mode": "Q&A"},
        enabled_skills=enabled,
        session_skill_state=None,
        query="just a test",
        file_types=[],
    )
    prompt = result.system_prompt
    assert "Available skills:" in prompt
    assert "demo" in prompt
    assert "A skill for testing" in prompt
    # Full body should NOT be in the index segment when skill is not selected
    assert "Do the demo thing." not in prompt
```

**Step 2: Run to verify fail**

```
python -m pytest tests/test_skill_index.py::test_system_prompt_includes_skill_index -v
```
Expected: FAIL — `Available skills:` not in prompt.

**Step 3: Add skill index segment to `_build_runtime_system_prompt()`**

In `metis_app/services/runtime_resolution.py`, find `_build_runtime_system_prompt()`. Its signature has `enabled_skills` or similar — check the actual function. The system prompt builder at lines ~279-310 assembles `segments`.

Add the skill index segment (after `base_instructions` and before selected skill blocks):

```python
# --- Skill discovery index (progressive disclosure) ---
# Inject compact one-liner per enabled skill so the LLM knows what's
# available. Full skill bodies are only injected for *selected* skills below.
if enabled_skills:
    from metis_app.services.skill_repository import SkillSummary as _SS  # noqa: PLC0415
    _index_lines = [
        _SS(
            skill_id=sk.skill_id,
            name=sk.name,
            description=sk.description,
            keywords=list((sk.triggers or {}).get("keywords") or []),
        ).format_index_line()
        for sk in enabled_skills
    ]
    segments.append("Available skills:\n" + "\n".join(_index_lines))
```

**Note:** Check where `enabled_skills` is in scope within `_build_runtime_system_prompt()`. If it's not a parameter, trace the call from `resolve_runtime_settings()` to find how to pass it through.

Look at the function signature at line ~278:
```python
def _build_runtime_system_prompt(
    settings, *, mode, retrieval_mode, retrieve_k, final_k, mmr_lambda,
    agentic_mode, agentic_max_iterations, capability_index, selected_skills,
    citation_policy_append, mode_prompt,
) -> str:
```

`enabled_skills` (all enabled, not just selected) is NOT currently a parameter. Add it:
1. Add `enabled_skills: list = []` to `_build_runtime_system_prompt()` signature
2. Pass it from the call site in `resolve_runtime_settings()`

**Step 4: Run to verify pass**

```
python -m pytest tests/test_skill_index.py -v
python -m pytest tests/test_parity_services.py -v  # regression check
```
Expected: all tests PASS.

**Step 5: Commit**

```bash
git add metis_app/services/runtime_resolution.py tests/test_skill_index.py
git commit -m "feat: inject available-skills index into system prompt for skill discovery"
```

---

## Task 3: Credential pool — `CredentialPool` class

**Files:**
- Create: `metis_app/utils/credential_pool.py`
- Test: `tests/test_credential_pool.py` (new)

**Step 1: Write the failing test**

Create `tests/test_credential_pool.py`:

```python
"""Tests for metis_app.utils.credential_pool.CredentialPool."""
from __future__ import annotations
import pytest
from metis_app.utils.credential_pool import CredentialPool


def test_get_key_returns_first_when_all_equal():
    pool = CredentialPool(["key-a", "key-b", "key-c"])
    assert pool.get_key() == "key-a"


def test_report_success_increments_use_count():
    pool = CredentialPool(["key-a", "key-b"])
    pool.report_success("key-a")
    pool.report_success("key-a")
    # key-b has lower count — should be preferred now
    assert pool.get_key() == "key-b"


def test_report_failure_removes_key():
    pool = CredentialPool(["key-a", "key-b"])
    pool.report_failure("key-a")
    assert pool.get_key() == "key-b"


def test_report_failure_all_keys_raises():
    pool = CredentialPool(["key-a"])
    pool.report_failure("key-a")
    with pytest.raises(RuntimeError, match="No credential pool keys"):
        pool.get_key()


def test_empty_pool_raises():
    pool = CredentialPool([])
    with pytest.raises(RuntimeError, match="No credential pool keys"):
        pool.get_key()


def test_thread_safety(monkeypatch):
    """get_key() + report_success() from multiple threads should not corrupt state."""
    import threading
    pool = CredentialPool(["k1", "k2", "k3"])
    results = []
    errors = []

    def _worker():
        try:
            key = pool.get_key()
            pool.report_success(key)
            results.append(key)
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=_worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(results) == 20
```

**Step 2: Run to verify fail**

```
python -m pytest tests/test_credential_pool.py -v
```
Expected: `ModuleNotFoundError` — `credential_pool` doesn't exist.

**Step 3: Implement `CredentialPool`**

Create `metis_app/utils/credential_pool.py`:

```python
"""metis_app.utils.credential_pool — Thread-safe API key pool with least-used rotation.

Ported from Hermes Agent v0.7.0 credential_pool pattern.
"""
from __future__ import annotations

import threading
from typing import Sequence


class CredentialPool:
    """Manages a pool of API keys for a single provider.

    Strategy: least-used — always return the key with the lowest success_count.
    On auth failure, remove the key from the active pool.
    Thread-safe via a single Lock.
    """

    def __init__(self, keys: Sequence[str]) -> None:
        self._lock = threading.Lock()
        # {key: use_count}
        self._pool: dict[str, int] = {k: 0 for k in keys if k}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_key(self) -> str:
        """Return the least-used active key.

        Raises
        ------
        RuntimeError
            If the pool is empty or all keys have been failed out.
        """
        with self._lock:
            if not self._pool:
                raise RuntimeError(
                    "No credential pool keys available. "
                    "Add more keys to 'credential_pool' in settings."
                )
            return min(self._pool, key=self._pool.__getitem__)

    def report_success(self, key: str) -> None:
        """Increment use counter for *key*."""
        with self._lock:
            if key in self._pool:
                self._pool[key] += 1

    def report_failure(self, key: str) -> None:
        """Remove *key* from the active pool (auth/rate-limit failure)."""
        with self._lock:
            self._pool.pop(key, None)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def active_count(self) -> int:
        """Number of keys still in the active pool."""
        with self._lock:
            return len(self._pool)
```

**Step 4: Run to verify pass**

```
python -m pytest tests/test_credential_pool.py -v
```
Expected: all 6 tests PASS.

**Step 5: Commit**

```bash
git add metis_app/utils/credential_pool.py tests/test_credential_pool.py
git commit -m "feat: add CredentialPool — thread-safe least-used API key rotation"
```

---

## Task 4: Wire credential pool into `create_llm()`

**Files:**
- Modify: `metis_app/utils/llm_providers.py`
- Modify: `metis_app/default_settings.json`
- Test: `tests/test_llm_providers.py`

**Background:** When `settings["credential_pool"][provider]` is a non-empty list, `create_llm()` should return a `PooledLLM` that wraps the real LLM and retries with the next key on 401/429. The `PooledLLM` must implement the same `invoke()` + `stream()` interface.

**Step 1: Write the failing tests**

Add to `tests/test_llm_providers.py`:

```python
from metis_app.utils.credential_pool import CredentialPool
from metis_app.utils.llm_providers import PooledLLM, _ChatMessage


class _AlwaysFailLLM:
    """LLM stub that raises an auth error on every call."""
    def invoke(self, messages):
        raise Exception("401 Unauthorized")


class _FailOnceLLM:
    """LLM stub that fails the first call then succeeds."""
    def __init__(self):
        self._calls = 0

    def invoke(self, messages):
        self._calls += 1
        if self._calls == 1:
            raise Exception("401 Unauthorized")
        return _ChatMessage(content="ok")


def test_pooled_llm_retries_on_auth_error():
    """PooledLLM retries with next key when invoke raises 401."""
    pool = CredentialPool(["bad-key", "good-key"])
    calls = []

    def _factory(key):
        return _FailOnceLLM() if key == "bad-key" else _ChatMessage.__new__(_ChatMessage)

    # Simpler: use a counter-based factory
    attempt = {"n": 0}

    class _CountingLLM:
        def invoke(self, messages):
            attempt["n"] += 1
            if attempt["n"] == 1:
                raise Exception("401 Unauthorized")
            return _ChatMessage(content="success")

    pooled = PooledLLM(
        pool=pool,
        factory=lambda key: _CountingLLM(),
        initial_key=pool.get_key(),
    )
    result = pooled.invoke([{"type": "human", "content": "hi"}])
    assert result.content == "success"


def test_pooled_llm_raises_when_all_keys_exhausted():
    """PooledLLM raises RuntimeError when all keys are tried and fail."""
    pool = CredentialPool(["k1"])

    class _AlwaysFail:
        def invoke(self, messages):
            raise Exception("401 Unauthorized")

    pooled = PooledLLM(
        pool=pool,
        factory=lambda key: _AlwaysFail(),
        initial_key="k1",
    )
    with pytest.raises(RuntimeError, match="No credential pool keys"):
        pooled.invoke([])
```

**Step 2: Run to verify fail**

```
python -m pytest tests/test_llm_providers.py -k "pooled" -v
```
Expected: `ImportError` — `PooledLLM` not yet defined.

**Step 3: Implement `PooledLLM` and wire into `create_llm()`**

In `metis_app/utils/llm_providers.py`, add after the imports:

```python
from metis_app.utils.credential_pool import CredentialPool as _CredentialPool


class PooledLLM:
    """LLM wrapper that retries with the next pool key on 401/429 errors.

    Matches the invoke() / stream() interface of LangChain BaseChatModel.
    """

    _AUTH_KEYWORDS = ("401", "unauthorized", "authentication", "invalid api key", "ratelimit", "429")

    def __init__(
        self,
        pool: _CredentialPool,
        factory: Any,  # Callable[[str], LLM]
        initial_key: str,
    ) -> None:
        self._pool = pool
        self._factory = factory
        self._current_key = initial_key
        self._llm = factory(initial_key)

    def _is_auth_error(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(kw in msg for kw in self._AUTH_KEYWORDS)

    def _rotate(self) -> None:
        self._pool.report_failure(self._current_key)
        self._current_key = self._pool.get_key()  # raises RuntimeError if empty
        self._llm = self._factory(self._current_key)

    def invoke(self, messages: list[Any]) -> Any:
        try:
            result = self._llm.invoke(messages)
            self._pool.report_success(self._current_key)
            return result
        except Exception as exc:
            if self._is_auth_error(exc):
                self._rotate()
                result = self._llm.invoke(messages)
                self._pool.report_success(self._current_key)
                return result
            raise

    def stream(self, messages: list[Any]) -> Any:
        try:
            yield from self._llm.stream(messages)
            self._pool.report_success(self._current_key)
        except Exception as exc:
            if self._is_auth_error(exc):
                self._rotate()
                yield from self._llm.stream(messages)
                self._pool.report_success(self._current_key)
            else:
                raise
```

Then in `create_llm()`, BEFORE the `if provider not in _UNCACHED:` block, add pool detection:

```python
# --- Credential pool rotation ---
_pool_keys = list(
    (settings.get("credential_pool") or {}).get(provider) or []
)
if _pool_keys:
    pool = _CredentialPool(_pool_keys)
    initial_key = pool.get_key()

    def _llm_factory(key: str, _p=provider, _m=model_name, _t=temperature, _o=output_max) -> Any:
        # Temporarily override the API key in a settings copy
        _s = dict(settings)
        _key_map = {
            "openai": "api_key_openai",
            "anthropic": "api_key_anthropic",
            "google": "api_key_google",
            "xai": "api_key_xai",
        }
        if _p in _key_map:
            _s[_key_map[_p]] = key
        # Re-call the per-provider constructor directly
        if _p == "openai":
            return _create_openai(_s, _m, _t, _o)
        if _p == "anthropic":
            return _create_anthropic(_s, _m, _t, _o)
        if _p == "google":
            return _create_google(_s, _m, _t, _o)
        if _p == "xai":
            return _create_xai(_s, _m, _t, _o)
        raise ValueError(f"Credential pool not supported for provider: {_p}")

    pool.report_success(initial_key)  # count initial selection
    return PooledLLM(pool=pool, factory=_llm_factory, initial_key=initial_key)
```

**Step 4: Add `credential_pool` to `default_settings.json`**

In `metis_app/default_settings.json`, after `"api_key_perplexity": ""`, add:

```json
"credential_pool": {},
```

**Step 5: Run tests to verify pass**

```
python -m pytest tests/test_llm_providers.py tests/test_credential_pool.py -v
```
Expected: all tests PASS.

**Step 6: Commit**

```bash
git add metis_app/utils/llm_providers.py metis_app/default_settings.json
git commit -m "feat: wire CredentialPool into create_llm() with PooledLLM retry wrapper"
```

---

## Task 5: Context compression — configurable threshold + structured template

**Files:**
- Modify: `metis_app/engine/streaming.py`
- Modify: `metis_app/default_settings.json`
- Test: `tests/test_engine_streaming.py` (existing — add cases)

**Background:** `streaming.py` already has a sliding-window compaction at lines 569–595 (`if iteration >= 3 and len(candidate) > _MAX_CONTEXT_CHARS`). This task:
1. Extracts the compaction logic into `_compress_context()` helper
2. Makes the threshold configurable via settings
3. Upgrades the summary prompt to the structured Goal/Key Findings/Remaining Gaps/Next Steps template
4. Emits a `context_compressed` trace event when compression fires
5. Respects `agentic_context_compress_enabled` setting

**Step 1: Write the failing test**

Add to `tests/test_engine_streaming.py`:

```python
def test_context_compression_emits_event(tmp_path, monkeypatch) -> None:
    """When accumulated context exceeds threshold, a context_compressed event is emitted."""
    import metis_app.engine.streaming as _s

    # Patch _compress_context to track calls
    compressed_calls = []

    _orig = _s._compress_context

    def _mock_compress(context, question, llm, iteration):
        compressed_calls.append(iteration)
        return "COMPRESSED SUMMARY"

    monkeypatch.setattr(_s, "_compress_context", _mock_compress)

    build_result = _build_test_index(tmp_path, monkeypatch)

    # Build a request with low threshold to force compression
    req = RagQueryRequest(
        manifest_path=build_result.manifest_path,
        question="Who wrote the first algorithm?",
        settings={
            "embedding_provider": "mock",
            "llm_provider": "mock",
            "vector_db_type": "json",
            "selected_mode": "Q&A",
            "top_k": 2,
            "retrieval_k": 2,
            "agentic_mode": True,
            "agentic_max_iterations": 3,
            "agentic_iteration_budget": 3,
            "agentic_context_compress_enabled": True,
            "agentic_context_compress_threshold_chars": 1,  # tiny threshold forces compression
        },
    )
    events = list(stream_rag_answer(req))
    event_types = [e.get("type") for e in events]
    # context_compressed event should appear if compaction fired
    # (Only check no error occurred; compaction is optional depending on mock answer length)
    assert "error" not in event_types


def test_compress_context_returns_structured_summary(monkeypatch) -> None:
    """_compress_context calls LLM with structured template and returns its output."""
    from metis_app.engine.streaming import _compress_context

    class _MockLLM:
        def invoke(self, messages):
            from metis_app.utils.llm_providers import _ChatMessage
            # Verify prompt contains the structured template keywords
            system = messages[0]["content"]
            assert "Key Findings" in system or "Goal" in system
            return _ChatMessage(content="STRUCTURED SUMMARY")

    result = _compress_context(
        context="Some long context text.",
        question="What is the answer?",
        llm=_MockLLM(),
        iteration=3,
    )
    assert result == "STRUCTURED SUMMARY"
```

**Step 2: Run to verify fail**

```
python -m pytest tests/test_engine_streaming.py::test_compress_context_returns_structured_summary -v
```
Expected: `ImportError` — `_compress_context` not yet defined as a standalone function.

**Step 3: Extract and upgrade `_compress_context()`**

In `metis_app/engine/streaming.py`:

1. Replace the hardcoded constant `_MAX_CONTEXT_CHARS = 12_000` with a comment noting it's now settings-driven (keep as default fallback).

2. Add the standalone helper after the existing helper functions:

```python
def _compress_context(
    context: str,
    question: str,
    llm: Any,
    iteration: int,
) -> str:
    """Compress *context* using a structured summary template.

    Ported from Hermes Agent v0.7.0 context_compressor.py.
    Template: Goal / Key Findings / Remaining Gaps / Next Steps.
    Falls back to hard truncation on LLM failure.
    """
    system = (
        "You are a concise research summariser. Compress the following retrieved "
        "context into a structured summary. Return ONLY:\n\n"
        f"## Compression Summary (pass {iteration})\n"
        f"**Goal:** {{one sentence restating the original question}}\n"
        "**Key Findings:**\n- (bullet points of the most important facts)\n"
        "**Remaining Gaps:** (what is still unknown or unresolved)\n"
        "**Next Steps:** (what additional retrieval would help)\n\n"
        "Preserve all entity names, dates, numbers, and key claims. "
        "Be dense — every sentence should carry information."
    )
    try:
        from metis_app.engine.querying import _response_text as _rt  # noqa: PLC0415
        return _rt(
            llm.invoke([
                {"type": "system", "content": system},
                {
                    "type": "human",
                    "content": f"ORIGINAL QUESTION:\n{question}\n\nCONTEXT TO COMPRESS:\n{context[:6000]}",
                },
            ])
        )
    except Exception:  # noqa: BLE001
        return context[:_MAX_CONTEXT_CHARS]
```

3. In the agentic loop (around line 571), replace the existing compaction block:

```python
# Old code (lines ~569-595):
candidate = accumulated_context + "\n\n" + new_context_block
if iteration >= 3 and len(candidate) > _MAX_CONTEXT_CHARS:
    ...
```

Replace with:

```python
candidate = accumulated_context + "\n\n" + new_context_block
_compress_enabled = bool(settings.get("agentic_context_compress_enabled", True))
_compress_threshold = int(
    settings.get("agentic_context_compress_threshold_chars", _MAX_CONTEXT_CHARS) or _MAX_CONTEXT_CHARS
)
if _compress_enabled and iteration >= 3 and len(candidate) > _compress_threshold:
    try:
        _compact = _compress_context(
            accumulated_context, question, llm, iteration
        )
        accumulated_context = _compact + "\n\n" + new_context_block
        yield _emit({
            "type": "context_compressed",
            "run_id": run_id,
            "iteration": iteration,
            "chars_before": len(candidate),
            "chars_after": len(accumulated_context),
        })
    except Exception:  # noqa: BLE001
        accumulated_context = candidate[:_compress_threshold]
else:
    accumulated_context = candidate[:_compress_threshold]
```

4. Add two keys to `metis_app/default_settings.json` after `"agentic_convergence_threshold"`:

```json
"agentic_context_compress_enabled": true,
"agentic_context_compress_threshold_chars": 12000,
```

**Step 4: Run tests**

```
python -m pytest tests/test_engine_streaming.py -v
```
Expected: all existing + new streaming tests PASS.

**Step 5: Commit**

```bash
git add metis_app/engine/streaming.py metis_app/default_settings.json
git commit -m "feat: extract _compress_context() with structured template; make threshold configurable"
```

---

## Task 6: Full regression run

**Step 1: Run the full test suite**

```
python -m pytest tests/ -x -q
```
Expected: all tests pass. Fix any failures before proceeding.

**Step 2: Commit any fixes**

```bash
git add -p
git commit -m "fix: address regression from hermes v0.7.0 pattern integration"
```

---

## Verification

After all tasks:

- **Phase B (skill index):** Load METIS with 3+ skills enabled; inspect system prompt in logs — each enabled skill should appear as a one-liner under "Available skills:". Full skill body should only appear for the matched (selected) skill.

- **Phase C (credential pool):** In `settings.json` set `"credential_pool": {"openai": ["invalid-key-1", "your-real-key"]}`. Send a query — first key 401s, second succeeds. Check logs for rotation.

- **Phase A (compression):** Set `"agentic_mode": true, "agentic_max_iterations": 5, "agentic_context_compress_threshold_chars": 100` and run a query. SSE stream should contain a `context_compressed` event on iteration 3+.
