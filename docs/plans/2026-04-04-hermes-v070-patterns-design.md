# Design: Hermes v0.7.0 Patterns for METIS

**Date:** 2026-04-04
**Constraints:** Local-first (GGUF + cloud APIs), no new infrastructure (SQLite + JSON vector store)
**Additive to:** `2026-04-01-hermes-sotaku-roadmap-design.md` (Phases 1–4) — this doc covers only new v0.7.0 patterns

---

## Context

Hermes Agent v0.7.0 (April 2026) shipped three patterns not covered in METIS's existing Hermes roadmap design:

1. **Context Window Compression** — auto-triggered structured summarization of long agentic sessions
2. **Skill Progressive Disclosure** — inject only skill metadata into system prompt; load full SKILL.md on demand
3. **Credential Pool Rotation** — multiple API keys per provider, thread-safe least-used rotation with 401 retry

METIS currently: has no context compression (agentic iterations accumulate unbounded synthesis history), injects full SKILL.md content into every system prompt, and supports only one API key per provider.

---

## Phase A: Context Window Compression

**Problem:** `agentic_mode` appends each synthesis pass to context for the next iteration. At 3–4 iterations this causes silent truncation or context-overflow errors for larger documents.

**Design:**

In `metis_app/engine/streaming.py`, after each agentic synthesis pass, check accumulated context size. If `sum(len(s) for s in prior_syntheses) > agentic_context_compress_threshold_chars` (default: 6000), compress before next iteration.

**Compression algorithm:**
1. Collect all prior-pass syntheses + sub-queries
2. Build compression prompt: "Summarize these research passes into: Goal, Key Findings, Remaining Gaps, Next Steps"
3. Call same LLM instance (no new client) — `llm.invoke(compression_prompt)`
4. Replace accumulated synthesis history with structured summary block
5. Continue iteration with compressed context

**Summary block template:**
```
## Compression Summary (pass {N})
**Goal:** {original query}
**Key Findings:**
- ...
**Remaining Gaps:** ...
**Next Steps:** ...
```

**New settings:**
```json
"agentic_context_compress_threshold_chars": 6000,
"agentic_context_compress_enabled": true
```

**Files to change:**
- `metis_app/engine/streaming.py` — add `_compress_agentic_context(syntheses, query, llm) -> str` + call in iteration loop
- `metis_app/default_settings.json` — two new keys
- `metis_app/api/models.py` — add `context_compressed: bool` to agentic trace (optional)

---

## Phase B: Skill Progressive Disclosure

**Problem:** Full SKILL.md content injected into every system prompt. Scales poorly as skill library grows (20+ skills = significant fixed token cost per request).

**Design:**

`SkillRepository` gains two access modes:
- `load_skill_index()` → `list[SkillSummary]` — frontmatter-only: `{name, trigger, description}`. Used for system prompt assembly.
- `load_skill_full(name: str)` → full SKILL.md content. Used at skill execution time.

`SkillSummary` dataclass:
```python
@dataclass
class SkillSummary:
    name: str
    description: str
    trigger: str  # comma-separated trigger phrases from frontmatter
```

**Frontmatter parsing:** Skills must have `description` and `trigger` in YAML frontmatter. Missing fields: use filename as name, first non-blank content line as description, name as trigger — graceful degradation, no breaking change for existing skills.

**System prompt injection** (replaces full skill bodies):
```
# Available Skills
- commit: Create a git commit with conventional message (trigger: "commit", "save changes")
- debug: Systematic debugging workflow (trigger: "debug", "fix bug")
```

**On-demand load:** When companion AI or agentic loop selects a skill, call `load_skill_full(name)` and prepend content to the skill execution context.

**Files to change:**
- `metis_app/services/skill_repository.py` — add `SkillSummary` dataclass + `load_skill_index()` method; rename existing `load_skill()` to `load_skill_full()`
- Wherever system prompt injects skills (likely `metis_app/services/workspace_orchestrator.py` or `assistant_companion.py`) — swap to `load_skill_index()`
- `metis_app/services/assistant_companion.py` — call `load_skill_full()` at skill execution time

---

## Phase C: Credential Pool Rotation

**Problem:** METIS supports one API key per provider. Rate limit hits on a single key block all requests; multi-account setups require manual rotation.

**Design:**

New `credential_pool` key in `settings.json`:
```json
"credential_pool": {
  "openai": ["sk-key1", "sk-key2", "sk-key3"],
  "anthropic": ["sk-ant-key1", "sk-ant-key2"]
}
```
Backward compatible: if absent or empty for a provider, falls back to existing `openai_api_key` / `anthropic_api_key` single keys.

**`CredentialPool` class** (new file: `metis_app/utils/credential_pool.py`):
```python
@dataclass
class CredentialPool:
    def __init__(self, keys: list[str]): ...
    def get_key(self) -> str:           # least-used: key with lowest use_count
    def report_success(self, key: str): # increment use_count
    def report_failure(self, key: str): # mark failed, remove from active rotation
```
Thread-safe via single `threading.Lock`. Global singleton per provider, instantiated at startup from settings.

**Integration in `llm_providers.py`:**
- `create_llm(settings)` checks `credential_pool[provider]` first; if non-empty, creates `CredentialPool` singleton
- LLM call wrapper: on `AuthenticationError` (401) or `RateLimitError` (429), call `pool.report_failure(key)` + recreate client with `pool.get_key()` + retry once
- On success: call `pool.report_success(key)`

**Files to change:**
- `metis_app/utils/credential_pool.py` — new `CredentialPool` class
- `metis_app/utils/llm_providers.py` — integrate `CredentialPool`; add retry wrapper around LLM calls
- `metis_app/default_settings.json` — add `"credential_pool": {}` placeholder
- `metis_app/config.py` — add `credential_pool: dict[str, list[str]] = {}` to Settings schema

---

## Implementation Order

| Order | Phase | Reason |
|-------|-------|--------|
| 1 | Phase B (Skill Progressive Disclosure) | Pure refactor, no new behavior, immediate prompt size benefit |
| 2 | Phase C (Credential Pool) | Self-contained new utility class, no dependencies |
| 3 | Phase A (Context Compression) | Most impactful but most invasive; depends on familiarity with agentic loop |

---

## Verification

- **Phase A:** Run agentic query with `agentic_max_iterations: 5` on a large document; assert `context_compressed: true` in trace; verify answer quality is not degraded vs uncompressed baseline.
- **Phase B:** Check system prompt length before/after with 5+ skills loaded; assert each skill appears as a one-liner; assert full skill content is injected when skill is executed.
- **Phase C:** Configure `credential_pool.openai: ["valid-key", "invalid-key"]`; force 401 on first key (revoke or use invalid); assert second key is used on retry and success is logged.
