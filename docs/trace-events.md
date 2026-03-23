# Trace Event Normalization

## Overview

Trace events are structured records emitted throughout Axiom's query and indexing pipelines. They capture:

- **Stage transitions**: When a pipeline phase (retrieval, synthesis, validation) starts or completes
- **Tool invocations**: When an external service (LLM, vector DB, validator) is called
- **Checkpoints**: Validation results and decision points
- **Content transformations**: When artifacts or outputs are created or revised
- **Iteration milestones**: In agentic loops (gap identification, sub-query generation, refinement)

Trace events are persisted as JSON lines in the trace store and streamed to the frontend via SSE for real-time visualization. This normalized schema ensures consistent structure across all backend event emitters and enables portable trace tooling.

## Event Type Taxonomy

| Category | Event Type | Lifecycle | Description |
|----------|-----------|-----------|-------------|
| **STAGE** | `stage_start` | start | Pipeline phase begins (e.g., retrieval, synthesis) |
| | `stage_end` | end | Pipeline phase completes successfully |
| **TOOL** | `tool_invoke` | start | External service call initiated (LLM, retrieval, etc.) |
| | `tool_result` | end | Tool call completed with result |
| | `tool_error` | end | Tool call failed with error |
| | `tool_skip` | atomic | Tool was skipped (e.g., disabled feature) |
| **CHECKPOINT** | `checkpoint` | atomic | Generic checkpoint or decision point |
| | `validation_pass` | end | Validation rule passed |
| | `validation_fail` | end | Validation rule failed |
| **CONTENT** | `content_added` | atomic | New artifact or content chunk created |
| | `content_revised` | atomic | Existing artifact or content modified |
| **ITERATION** | `iteration_start` | start | Agentic iteration begins |
| | `iteration_end` | end | Agentic iteration completes |

## Payload Structure

All trace events follow a standardized payload structure inspired by AG-UI protocols:

```python
{
    "status": "success" | "pending" | "error" | "skipped",
    "message": str,               # Human-readable summary (~200 chars max)
    "duration_ms": int | None,    # Elapsed time (if applicable)
    "context": dict               # Event-specific metadata (see examples)
}
```

- **status**: One of `success`, `pending`, `error`, or `skipped`
- **message**: Descriptive text explaining what happened
- **duration_ms**: Optional elapsed time in milliseconds
- **context**: Event-specific dict keyed by event type (e.g., `tool_name`, `stage_name`, `validator_type`)

## Examples

### Example 1: Tool Invocation (LLM Call)

```json
{
  "event_type": "tool_invoke",
  "status": "pending",
  "message": "Calling Claude API for synthesis",
  "context": {
    "tool_name": "llm_request",
    "provider": "anthropic",
    "model": "claude-3-5-sonnet"
  }
}
```

### Example 2: Validation Checkpoint

```json
{
  "event_type": "validation_pass",
  "status": "success",
  "message": "Claim grounding validation passed (3 notes)",
  "duration_ms": 245,
  "context": {
    "validator_type": "claim_grounding",
    "note_count": 3
  }
}
```

### Example 3: Stage Completion

```json
{
  "event_type": "stage_end",
  "status": "success",
  "message": "Synthesis stage completed",
  "duration_ms": 1850,
  "context": {
    "stage_name": "synthesis",
    "output_length": 1200
  }
}
```

## Backward Compatibility

**No breaking changes.** Existing trace events remain unmodified in structure and persist as-is. The schema definitions in `axiom_app/models/trace_event_schema.py` are:

- **Purely documentary**: Define constants and types for new event emission
- **Additive only**: Do not alter the serialization of existing `TraceEvent` objects
- **Optional guidance**: New code should follow the normalized structure; legacy events are tolerated
- **Frontend-agnostic**: The `TraceEvent` TypeScript interface remains unchanged; consumers read the same JSON structure

## Integration Guide

### For Backend Contributors

When emitting a new trace event, import from the schema module:

```python
from axiom_app.models.trace_event_schema import EventType, EventStatus

# Emit a tool invocation
self.trace_store.append_event(
    run_id=run_id,
    stage="synthesis",
    event_type=EventType.TOOL_INVOKE.value,  # "tool_invoke"
    payload={
        "status": EventStatus.PENDING.value,
        "message": "Calling LLM for synthesis",
        "context": {
            "tool_name": "llm_request",
            "provider": "anthropic"
        }
    }
)
```

### For Frontend Consumers

The normalized payload structure is consistent across all new events:

```typescript
// In React, filter by lifecycle phase to render UI regions
const isStartEvent = (event: TraceEvent) => {
  const lifecycle = getEventLifecycle(event.event_type);
  return lifecycle === "start";
};

// Access standard fields
const status = event.payload?.status;      // "success" | "pending" | "error" | "skipped"
const duration = event.payload?.duration_ms;
const context = event.payload?.context;
```

### For Trace Tooling

The schema is portable and consumed by:

- **Audit logs**: Persist trace events for post-run analysis
- **Visualization**: Render event timelines and tool dependency graphs
- **Metrics**: Calculate stage duration, tool latency percentiles, error rates
- **Debugging**: Reconstruct run history and identify failure points

---

**Last Updated**: 2026-03-23  
**Schema Version**: 1.0 (initial)
