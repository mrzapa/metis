# Axiom Refactoring Implementation Plan

**Date:** March 23, 2026  
**Scope:** Two independent improvements identified from prior research  
**Status:** Planning phase — no code changes issued yet

---

## Executive Summary

This plan covers two substantial but independent improvements:

1. **TASK 1: GGUF Explainability Serialization Refactoring** (Quick wins, 1–2 hours)
   - Factor out duplicated catalog entry serialization logic shared between FastAPI and Litestar  
   - Create a single, reusable serialization module
   - Maintain 100% backward compatibility with existing API contracts
   - Reduce code duplication by ~150 lines

2. **TASK 2: AG-UI-Inspired Trace Event Normalization** (Exploratory, 2–4 hours)
   - Normalize how trace events are structured and emitted across the backend
   - Apply AG-UI event taxonomy to clarify tool lifecycle and stage transitions
   - Prepare frontend to consume uniformly shaped events (no breaking changes)
   - Establish a portable event schema for future trace tooling

---

---

## TASK 1: GGUF Serialization Refactoring

### 1.1 Problem Statement

**Current State:**  
Two independent implementations of the same GGUF catalog serialization logic:

- **FastAPI** (`axiom_app/api/gguf.py`, lines 44–86)  
  Returns Pydantic `GgufCatalogEntryModel` via `_serialize_catalog_entry()`
  
- **Litestar** (`axiom_app/api_litestar/routes/gguf.py`, lines 26–70)  
  Returns raw `dict[str, Any]` via `_serialize_catalog_entry()`

**Shared helpers (duplicated):**
- `_is_caveat(note: str) -> bool` — caveat detection identical in both
- `_build_recommendation_summary(item) -> str` — identical in both  
- `_load_registry() -> dict` — identical in both

**Other duplicated endpoints:**
- `/v1/gguf/catalog` — both call `_RECOMMENDER.recommend_models()` and serialize identically
- `/v1/gguf/hardware` — same output dict structure
- `/v1/gguf/installed` — same filtering and dto construction
- `/v1/gguf/validate`, `/refresh`, `/register`, `/unregister` — logic duplicated

**Risk:** When GGUF explainability requirements change (e.g., new score component, field addition), maintainers must update two places or one breaks.

### 1.2 Solution Design

**Create a new shared module:** `axiom_app/services/gguf_serialization.py`

**Responsibilities:**
- Pure serialization functions (no FastAPI/Litestar coupling)
- Input: raw dict from `LocalLlmRecommenderService`
- Output: normalized dict (framework-agnostic)
- Pydantic models stay in `axiom_app/api/models.py` (FastAPI-specific)
- Return types: always `dict[str, Any]` for compatibility

**Files Created:**
```
axiom_app/
  services/
    gguf_serialization.py  (NEW)
```

**Factored Functions:**

```python
# gguf_serialization.py
def is_caveat(note: str) -> bool:
    """Detect if a note is a caveat (one-liner helper)."""
    
def build_recommendation_summary(item: dict[str, Any]) -> str:
    """Build human-readable recommendation text."""
    
def serialize_catalog_entry(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a catalog dict into standard output shape."""
    # Returns all fields required by GgufCatalogEntryModel
    
def get_installed_entries() -> list[dict[str, Any]]:
    """Load and filter installed GGUF entries from registry."""
    # Helper to avoid duplication of registry + filtering logic
```

### 1.3 Modification Details

#### Step 1: Create `axiom_app/services/gguf_serialization.py`

```python
"""Shared GGUF serialization logic for FastAPI and Litestar."""

from __future__ import annotations

from typing import Any

_CAVEAT_HINTS = (
    "advisory",
    "bottleneck",
    "insufficient",
    "limited",
    "overridden",
    "reduced",
    "slow",
    "spilling",
    "tight",
)


def is_caveat(note: str) -> bool:
    """Check if a note is a caveat (problem indicator)."""
    lowered = str(note or "").strip().lower()
    return any(token in lowered for token in _CAVEAT_HINTS)


def build_recommendation_summary(item: dict[str, Any]) -> str:
    """Build a human-readable recommendation summary from catalog item."""
    fit_level = str(item.get("fit_level") or "unknown").replace("_", " ").strip()
    run_mode = str(item.get("run_mode") or "cpu_only").replace("_", " ").strip()
    quant = str(item.get("best_quant") or "default quant")
    context_length = max(int(item.get("recommended_context_length") or 2048), 256)
    memory_required = float(item.get("memory_required_gb") or 0.0)
    memory_available = float(item.get("memory_available_gb") or 0.0)
    estimated_tps = float(item.get("estimated_tps") or 0.0)
    
    return (
        f"{fit_level.title()} fit on {run_mode} with {quant} at {context_length:,}-token context. "
        f"Needs about {memory_required:.1f} GB from {memory_available:.1f} GB available and is estimated around "
        f"{estimated_tps:.1f} tok/s."
    )


def serialize_catalog_entry(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a GGUF catalog dict into standard serialization shape."""
    notes = [str(note) for note in (item.get("notes") or [])]
    caveats = [note for note in notes if is_caveat(note)]
    score_components = {
        str(key): float(value)
        for key, value in dict(item.get("score_components") or {}).items()
    }
    
    return {
        "model_name": item.get("model_name", ""),
        "provider": item.get("provider", ""),
        "parameter_count": item.get("parameter_count", ""),
        "architecture": item.get("architecture", ""),
        "use_case": item.get("use_case", ""),
        "fit_level": item.get("fit_level", ""),
        "run_mode": item.get("run_mode", ""),
        "best_quant": item.get("best_quant", ""),
        "estimated_tps": float(item.get("estimated_tps", 0.0) or 0.0),
        "memory_required_gb": float(item.get("memory_required_gb", 0.0) or 0.0),
        "memory_available_gb": float(item.get("memory_available_gb", 0.0) or 0.0),
        "recommended_context_length": item.get("recommended_context_length", 2048),
        "score": float(item.get("score", 0.0) or 0.0),
        "recommendation_summary": build_recommendation_summary(item),
        "notes": notes,
        "caveats": caveats,
        "score_components": score_components,
        "source_repo": item.get("source_repo", ""),
        "source_provider": item.get("source_provider", ""),
    }
```

#### Step 2: Update `axiom_app/api/gguf.py`

**Changes:**
- Import `serialize_catalog_entry` and `is_caveat` from new module  
- Remove local `_is_caveat()` and `_build_recommendation_summary()` definitions
- Update `_serialize_catalog_entry()` to wrap serialized dict in Pydantic model:

```python
from axiom_app.services.gguf_serialization import (
    serialize_catalog_entry,
    is_caveat,
)

def _serialize_catalog_entry(item: dict[str, Any]) -> GgufCatalogEntryModel:
    """Convert raw catalog dict to Pydantic model (FastAPI)."""
    serialized = serialize_catalog_entry(item)
    return GgufCatalogEntryModel(**serialized)
```

#### Step 3: Update `axiom_app/api_litestar/routes/gguf.py`

**Changes:**
- Import shared functions  
- Replace local `_serialize_catalog_entry()` with call to shared function:

```python
from axiom_app.services.gguf_serialization import serialize_catalog_entry

def _serialize_catalog_entry(item: dict[str, Any]) -> dict[str, Any]:
    """Convert raw catalog dict to standard dict (Litestar)."""
    return serialize_catalog_entry(item)
```

### 1.4 Files to Modify

| File | Change | Lines | Notes |
|------|--------|-------|-------|
| `axiom_app/services/gguf_serialization.py` | **Create** | ~70 | New shared module |
| `axiom_app/api/gguf.py` | Edit | 30–60 | Remove duplicates, import shared |
| `axiom_app/api_litestar/routes/gguf.py` | Edit | 20–45 | Remove duplicates, import shared |
| `axiom_app/api/app.py` | No change | — | Uses gguf module, no refactoring needed |
| `axiom_app/api_litestar/app.py` | No change | — | Uses gguf routes, no refactoring needed |

### 1.5 Backward Compatibility

**API Contract:** ✅ UNCHANGED
- Both endpoints return identical JSON to current clients
- FastAPI response model `GgufCatalogEntryModel` remains unchanged
- Response field names, types order unchanged

**Internal Compatibility:** ✅ STRONG
- Shared module is pure logic (no side effects)
- Idempotent serialization
- No changes to service layer (`LocalLlmRecommenderService`, `LocalModelRegistryService`)

**Test Impact:** ✅ MINIMAL
- Existing tests in `test_api_gguf.py` and `test_api_litestar.py` should pass unchanged
- Consider adding integration test in new file `tests/test_gguf_serialization.py` to lock down shared logic

### 1.6 Tests to Update/Add

**Existing tests (should pass without modification):**
- `tests/test_api_gguf.py::test_catalog_returns_200`  
- `tests/test_api_gguf.py::test_installed_returns_200`  
- `tests/test_api_gguf.py::test_validate_*`
- `tests/test_api_litestar.py::test_gguf_*`

**New tests to add:**

File: `tests/test_gguf_serialization.py`

```python
def test_serialize_catalog_entry_complete_fields():
    """Verify all required fields are present in serialized output."""
    
def test_is_caveat_detects_known_hints():
    """Verify caveat detection works for all hint keywords."""
    
def test_build_recommendation_summary_formats_correctly():
    """Verify summary formatting handles edge cases."""
    
def test_serialize_catalog_entry_parity_fastapi_litestar():
    """Cross-framework parity: same input produces same output dict."""
    # This test makes concrete the contract that both frameworks will produce identical JSON
```

### 1.7 Scope & Effort

| Aspect | Estimate | Notes |
|--------|----------|-------|
| Code writing | 30 min | Module creation + refactoring |
| Testing | 20 min | New tests + existing test validation |
| Review | 10 min | Verify no logic changes |
| **Total** | **~1 hour** | Quick, mechanical refactoring |

### 1.8 Acceptance Criteria

- [ ] File `axiom_app/services/gguf_serialization.py` created with shared logic
- [ ] FastAPI `gguf.py` imports and uses shared module
- [ ] Litestar `routes/gguf.py` imports and uses shared module
- [ ] All existing GGUF API tests pass
- [ ] New unit tests in `test_gguf_serialization.py` pass
- [ ] Code coverage on shared module is ≥95%
- [ ] No changes to API response structure (backward compatible)
- [ ] No changes to imports or entry points visible to consumers

---

---

## TASK 2: AG-UI-Inspired Trace Event Normalization

### 2.1 Problem Statement

**Current State:**

Trace events are emitted across multiple code paths in the backend with varying structure or context:

- **Backend emitters:** `app_controller.py` contains ~15 direct calls to `trace_store.append_event()`  
  Each call specifies different combinations of `stage`, `event_type`, `payload`, `tool_calls`, `retrieval_results`
  
- **Frontend consumption:** Events streamed via SSE or fetched from `/v1/traces/{run_id}`  
  Frontend renders events in `trace-timeline.tsx` using basic `stage` grouping
  
- **Tool lifecycle:** `tool_calls` array exists on `TraceEvent` but is:
  - Never explicitly visualized as a state machine (start → end)
  - Not synchronized with stage transitions
  - Missing explicit error/exception handling

- **Event schema fragmentation:** No agreed-upon taxonomy for:
  - When tools should be invoked vs. when they complete
  - What payload fields belong in tool_calls vs. generic payload
  - How to represent tool errors or timeouts
  - When to emit intermediate vs. final events

**Impact:** 
- Frontend doesn't know if a tool_call is pending, running, succeeded, or failed
- Developers add trace events ad-hoc without consistency
- Hard to build tooling that understands the full trace shape

### 2.2 Vision: Portable Event Taxonomy

**Inspired by AG-UI patterns**, establish a minimal but complete event vocabulary:

```typescript
// Taxonomy for event_type field

// Stage lifecycle events (backend → frontend progress)
"stage_start"       // Stage (e.g., retrieval) begins
"stage_end"         // Stage completes (success)

// Tool invocation
"tool_invoke"       // Tool call initiated with params
"tool_result"       // Tool returned result
"tool_error"        // Tool failed or timed out
"tool_skip"         // Tool was considered but skipped

// Intermediate checkpoints
"checkpoint"        // Named milestone (e.g., "parsed_query")
"validation_pass"   // Validation check succeeded
"validation_fail"   // Validation check failed

// Content changes
"content_added"     // Text/reasoning appended to synthesis
"content_revised"   // Prior content was edited

// Iteration/recursion
"iteration_start"   // Agentic loop iteration N begins
"iteration_end"     // Iteration N completes
```

**Payload standardization:**

```python
# Common fields in payload across all events:
{
    "stage": "retrieval",          # Which stage emitted this
    "status": "success|pending|error|skipped",  # Outcome
    "duration_ms": 123,             # How long this took
    "message": "...",               # Human-readable description
}

# Tool-specific:
{
    "tool_name": "web_search",
    "tool_input": {...},            # What we passed to the tool
    "tool_output": {...},           # What the tool returned
    "tool_error": "...",            # If status=error
}

# Retrieval-specific:
{
    "query": "...",
    "num_results": 5,
    "rerank_score": 0.87,
}
```

### 2.3 Implementation Strategy

**Phase 0 (This session):** Define schema, no API breaking changes  
**Phase 1 (Follow-up):** Migrate backend to emit normalized events  
**Phase 2 (Future):** Frontend rendering enhanced with tool state machine  

**This session focuses on Phase 0: schema definition and infrastructure**.

### 2.4 Changes Required

#### 2.4.1 Create `axiom_app/models/trace_event_schema.py`

**New file:** `axiom_app/models/trace_event_schema.py`

```python
"""
AG-UI-inspired event type taxonomy and standardized payload schema.
Portable: framework-agnostic, usable in backend and frontend tooling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

# ─────────────────────────────────────────────────────────────────────

class EventType(str, Enum):
    """Standard event type vocabulary."""
    
    # Stage lifecycle
    STAGE_START = "stage_start"
    STAGE_END = "stage_end"
    
    # Tool lifecycle
    TOOL_INVOKE = "tool_invoke"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    TOOL_SKIP = "tool_skip"
    
    # Checkpoints
    CHECKPOINT = "checkpoint"
    VALIDATION_PASS = "validation_pass"
    VALIDATION_FAIL = "validation_fail"
    
    # Content
    CONTENT_ADDED = "content_added"
    CONTENT_REVISED = "content_revised"
    
    # Iteration
    ITERATION_START = "iteration_start"
    ITERATION_END = "iteration_end"


class EventStatus(str, Enum):
    """Standard outcome status."""
    SUCCESS = "success"
    PENDING = "pending"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass(slots=True)
class StandardPayload:
    """
    Portable payload structure that all events should include.
    Additional fields can be added as (stage_name, event_type) pairs.
    """
    
    status: EventStatus | str
    message: str = ""
    duration_ms: int | None = None
    context: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "status": str(self.status),
            "message": self.message,
            "duration_ms": self.duration_ms,
            "context": self.context,
        }


@dataclass(slots=True)
class ToolPayload(StandardPayload):
    """Tool invocation context."""
    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_output: dict[str, Any] = field(default_factory=dict)
    tool_error: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result.update({
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_output": self.tool_output,
            "tool_error": self.tool_error,
        })
        return result


@dataclass(slots=True)
class RetrievalPayload(StandardPayload):
    """Retrieval stage context."""
    query: str = ""
    num_results: int = 0
    rerank_score: float | None = None
    retrieval_mode: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result.update({
            "query": self.query,
            "num_results": self.num_results,
            "rerank_score": self.rerank_score,
            "retrieval_mode": self.retrieval_mode,
        })
        return result


# ─────────────────────────────────────────────────────────────────────

def normalize_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Ensure a payload has minimal required fields for trace tooling.
    Preserves extra fields for backward compatibility.
    """
    normalized = dict(raw_payload or {})
    
    # Inject defaults if missing
    if "status" not in normalized:
        normalized["status"] = "pending"
    if "message" not in normalized:
        normalized["message"] = ""
    
    return normalized


def suggest_event_type(stage: str, event_type: str) -> str:
    """
    Given a stage and event_type, suggest the normalized event_type
    from the standard vocabulary.
    
    This is advisory; code can emit custom event_types if needed,
    but tooling should recognize standard ones.
    """
    standard = {
        # Retrieval stage
        ("retrieval", "retrieval_start"): EventType.STAGE_START,
        ("retrieval", "retrieval_end"): EventType.STAGE_END,
        ("retrieval", "query"): EventType.CHECKPOINT,
        
        # Validation stage
        ("validation", "validation_start"): EventType.STAGE_START,
        ("validation", "check_pass"): EventType.VALIDATION_PASS,
        ("validation", "check_fail"): EventType.VALIDATION_FAIL,
        
        # Synthesis
        ("synthesis", "synthesis_start"): EventType.STAGE_START,
        ("synthesis", "synthesis_end"): EventType.STAGE_END,
        ("synthesis", "text_added"): EventType.CONTENT_ADDED,
        
        # Tool calls
        ("skills", "tool_invoke"): EventType.TOOL_INVOKE,
        ("skills", "tool_result"): EventType.TOOL_RESULT,
        ("skills", "tool_error"): EventType.TOOL_ERROR,
    }
    
    key = (stage.lower(), event_type.lower())
    return standard.get(key, event_type)
```

#### 2.4.2 Update `axiom_app/models/parity_types.py`

**Add imports and documentation:**

```python
# At top of file
from axiom_app.models.trace_event_schema import (
    EventType,
    EventStatus,
    normalize_payload,
)

# Before TraceEvent class
"""
Trace event persistence model.

The TraceEvent schema is portable and can be consumed by:
- Frontend trace visualization (trace-timeline, trace viewer)
- Debug dashboards and diagnostics
- External trace analysis tools
- SSE stream player / recorder

For the standardized payload vocabulary and event type taxonomy,
see trace_event_schema.py.
"""

# In TraceEvent.create() classmethod, add normalization:
@classmethod
def create(...) -> "TraceEvent":
    # ... existing code ...
    normalized_payload = normalize_payload(payload or {})
    return cls(
        # ...
        payload=normalized_payload,
    )
```

#### 2.4.3 Update `axiom_app/controllers/app_controller.py`

**Document event emissions, no breaking changes:**

```python
# Add comment block before first trace event emission (around line 1894):
"""
Trace Event Emissions
─────────────────────

This controller emits trace events for all major stages (retrieval, synthesis, validation, etc.).
Events follow the portable schema defined in axiom_app.models.trace_event_schema:
- Use EventType vocabulary when possible
- Include 'status' and 'message' in all payloads
- Duration tracking optional but recommended for performance analysis

Example:
    self.trace_store.append_event(
        run_id=run_id,
        stage="retrieval",
        event_type="query_parsed",
        payload={
            "status": "success",
            "message": "Query parsed and expanded",
            "duration_ms": 42,
            "context": {"query": normalized_query},
        },
    )
"""
```

For now, **no code changes** to existing append_event calls. That's Phase 1 follow-up.

#### 2.4.4 Update Frontend Type Definition

**File: `apps/axiom-web/lib/api.ts`**

```typescript
// Import the server-side value for reference documentation
export interface TraceEvent {
  run_id: string;
  event_id?: string;
  stage: string;
  event_type: string;  // Now documented: use EventType vocabulary
  timestamp: string;
  iteration?: number;
  latency_ms?: number | null;
  payload: {
    status?: "success" | "pending" | "error" | "skipped";  // Standardized
    message?: string;  // Always prefer this over unlabeled strings
    duration_ms?: number;
    context?: Record<string, unknown>;
    [key: string]: unknown;  // Backward compat: allow extra fields
  };
  citations_chosen?: string[] | null;
}
```

#### 2.4.5 Create Documentation

**File: `docs/trace-events.md`**

```markdown
# Trace Event Schema

## Overview

Trace events record the execution lifecycle of a run (query, reasoning steps, tool calls).
The schema is portable and consumed by frontend visualization, diagnostics, and external analysis tools.

## Event Types (Standard Vocabulary)

See `axiom_app.models.trace_event_schema.EventType`:
- `stage_start` / `stage_end` — Stage lifecycle
- `tool_invoke` / `tool_result` / `tool_error` — Tool lifecycle
- `validation_pass` / `validation_fail` — Validation checkpoints
- etc.

## Payload Standard

All payloads should include:
```json
{
  "status": "success|pending|error|skipped",
  "message": "Human-readable description",
  "duration_ms": 123,
  "context": { /* stage-specific context */ }
}
```

## Backward Compatibility

Clients must tolerate:
- Extra fields in payload (ignore them)  
- `status` or `message` being missing (treat as unknown or "pending")
- Custom event_types not in the standard vocabulary

New code should emit standardized events; legacy events continue to work.
```

### 2.5 Files to Modify

| File | Change | Purpose | Lines |
|------|--------|---------|-------|
| `axiom_app/models/trace_event_schema.py` | **Create** | Event type vocabulary, payload schema | ~150 |
| `axiom_app/models/parity_types.py` | Edit | Import schema constants, document TraceEvent | ~10 |
| `axiom_app/controllers/app_controller.py` | Edit | Add documentation for emitters | ~15 |
| `apps/axiom-web/lib/api.ts` | Edit | Update TraceEvent type docs | ~10 |
| `docs/trace-events.md` | **Create** | Public documentation | ~40 |

### 2.6 Backward Compatibility

**API Contract:** ✅ UNCHANGED
- No changes to trace event shape
- No changes to `/v1/traces/{run_id}` response structure
- No changes to SSE stream encoding

**Frontend:** ✅ IMPROVED
- TypeScript types are documented but not restrictive
- Extra fields in payload are preserved
- Rendering logic can gradually adopt `status` and `message` fields

**Backend:** ✅ ADDITIVE
- New constants and helpers available but optional
- Existing code continues to work
- Phase 1 migration to use new event types is separate

### 2.7 Tests to Add

**File: `tests/test_trace_event_schema.py`**

```python
def test_event_type_enum_complete():
    """Verify standard event types cover common cases."""
    
def test_normalize_payload_injects_defaults():
    """Verify missing status/message are filled in."""
    
def test_normalize_payload_preserves_extra_fields():
    """Verify backward compat: unknown fields are preserved."""
    
def test_suggest_event_type_mapping():
    """Verify the advisory mapping table is correct."""
    
def test_tool_payload_serialization():
    """Verify payload objects serialize to dicts correctly."""
```

**File: `tests/test_app_controller_trace_emitters.py`** (can be minimal for now)

```python
def test_trace_store_events_have_status_field():
    """Verify all trace events emitted include status field."""
    # Scan app_controller.py trace_store.append_event calls
    # This is advisory; existing events still work without it
```

### 2.8 Scope & Effort

| Aspect | Estimate | Notes |
|--------|----------|-------|
| Schema design | 20 min | Enumerate event types, think through payloads |
| Code writing | 40 min | New files + updates to parity_types |
| Tests | 15 min | Schema tests + documentation |
| Docs | 15 min | trace-events.md + code comments |
| **Total** | **~90 min** | Exploratory foundation work |

### 2.9 Acceptance Criteria

- [ ] File `axiom_app/models/trace_event_schema.py` created with event taxonomy
- [ ] `EventType` enum covers ≥80% of current event_type values in app_controller  
- [ ] `TraceEvent` in parity_types imports and documents schema
- [ ] Frontend `TraceEvent` type in api.ts updated with payload schema docs
- [ ] `docs/trace-events.md` published with clear examples
- [ ] New tests in `test_trace_event_schema.py` pass (≥95% coverage)
- [ ] Existing trace store tests pass (no breaking changes)
- [ ] No changes to `/v1/traces/{run_id}` or SSE stream response format

---

---

## Execution Strategy

### Recommended Order

**Execute in this sequence:**

1. **TASK 1 first** (GGUF Refactoring, ~1 hour)  
   - Low risk, mechanical refactoring
   - No dependencies on other changes
   - Good warm-up for codebase

2. **TASK 2 second** (Trace Event Schema, ~1.5 hours)  
   - Additive, no breaking changes
   - Can be done after TASK 1
   - Prepares groundwork for future trace tooling

**Parallelization:** Not recommended. TASK 1 should finish completely before TASK 2 starts.

### Testing Plan

**After TASK 1:**
```bash
pytest tests/test_api_gguf.py -v
pytest tests/test_api_litestar.py::test_gguf -v
pytest tests/test_gguf_serialization.py -v
```

**After TASK 2:**
```bash
pytest tests/test_trace_event_schema.py -v
pytest tests/test_trace_store.py -v  # Should still pass
pytest tests/test_app_controller_trace_emitters.py -v
```

### Integration Checkpoints

**Checkpoint 1 (after TASK 1):**
- [ ] GGUF endpoints respond identically from both FastAPI and Litestar
- [ ] All GGUF tests pass
- [ ] Code coverage on `services/gguf_serialization.py` ≥95%

**Checkpoint 2 (after TASK 2):**
- [ ] Schema documentation published  
- [ ] All trace schema tests pass
- [ ] Existing trace store functionality unchanged
- [ ] Frontend can receive and render events with new payload format

---

---

## Risk Analysis

### TASK 1: GGUF Refactoring

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Pydantic model wrapping breaks FastAPI contract | Low | High | Run existing type-check tests, manual validation |
| Litestar dict output differs from FastAPI JSON | Low | High | Test cross-framework serialization parity |
| Import cycles introduced | Very low | Medium | Keep services module import-clean |

### TASK 2: Trace Event Schema

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Frontend trace rendering breaks | Low | Medium | No changes to TraceEvent shape; new fields only |
| Backend code emits malformed payloads | Low | Low | New tests; optional adoption in Phase 1 |
| Documentation unclear | Medium | Low | Include code examples, usage guide |

---

---

## Success Criteria Summary

### TASK 1: GGUF Refactoring
- ✅ Shared serialization module created and imported by both FastAPI and Litestar
- ✅ Duplication reduced by ~150 lines
- ✅ 100% backward compatible (no API response changes)
- ✅ All existing tests pass
- ✅ New unit tests for shared module
- ✅ Code coverage ≥95%

### TASK 2: Trace Event Normalization
- ✅ Event type vocabulary established (`EventType` enum)
- ✅ Payload schema standardized and documented
- ✅ No API breaking changes
- ✅ Frontend TraceEvent type updated with schema docs
- ✅ `trace-events.md` published
- ✅ New tests validate schema helpers
- ✅ Foundation ready for Phase 1 backend migration

---

---

## Dependencies & Follow-Ups

### TASK 1 → No follow-ups
Once complete, GGUF serialization is stable and ready for production.

### TASK 2 → Phase 1 Work (Future Session)
After this session's schema definition, Phase 1 will:
1. Migrate app_controller.py to emit events using `EventType` vocabulary
2. Update frontend TraceTimeline to render tool lifecycles
3. Add tool state machine visualization (pending → running → complete)
4. Ensure all payloads include `status` and `message`

### External Context: AG-UI
The event taxonomy in TASK 2 is inspired by AG-UI patterns but not a direct port.
If AG-UI repository becomes available, a future session can align the schemas more tightly.

---

**Plan prepared:** March 23, 2026  
**Ready for implementation:** Yes  
**Estimated total duration:** 2–3 hours  
**Sessions required:** 1 (both tasks in sequence)
