"""
Normalized trace event schema and vocabulary for METIS.

Inspired by AG-UI event taxonomy, this module defines:
- EventType enum: Standard event categories (STAGE, TOOL, CHECKPOINT, CONTENT, ITERATION)
- EventStatus enum: Standard status values (success, pending, error, skipped)
- Helper functions: categorization and lifecycle inquiry
- TypedDict schemas: Standardized payload structures

No breaking changes to existing trace events; schema is purely documentary and additive.

Example payloads:

1. Tool invocation (LLM call):
   {
       "event_type": "tool_invoke",
       "status": "pending",
       "message": "Calling Claude API",
       "context": {
           "tool_name": "llm_request",
           "provider": "anthropic",
           "model": "claude-3-5-sonnet"
       }
   }

2. Validation checkpoint:
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

3. Stage transition:
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
"""

from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict


class EventType(Enum):
    """Normalized event type enumeration with category groupings."""

    # STAGE events: pipeline phase transitions
    STAGE_START = "stage_start"
    STAGE_END = "stage_end"

    # TOOL events: model/service invocations
    TOOL_INVOKE = "tool_invoke"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    TOOL_SKIP = "tool_skip"

    # CHECKPOINT events: validation and decision points
    CHECKPOINT = "checkpoint"
    VALIDATION_PASS = "validation_pass"
    VALIDATION_FAIL = "validation_fail"

    # CONTENT events: document and output transformations
    CONTENT_ADDED = "content_added"
    CONTENT_REVISED = "content_revised"

    # ITERATION events: agentic loop milestones
    ITERATION_START = "iteration_start"
    ITERATION_END = "iteration_end"

    def __str__(self) -> str:
        return self.value


class EventStatus(Enum):
    """Standard event status enumeration."""

    SUCCESS = "success"
    PENDING = "pending"
    ERROR = "error"
    SKIPPED = "skipped"

    def __str__(self) -> str:
        return self.value


class BaseEventPayload(TypedDict, total=False):
    """Standard structure for normalized trace event payloads."""

    status: str  # EventStatus value: "success", "pending", "error", "skipped"
    message: str  # Human-readable summary (max ~200 chars)
    duration_ms: int  # Elapsed milliseconds (if applicable)
    context: dict[str, Any]  # Event-specific metadata (tool type, stage name, etc.)


class ToolEventContext(TypedDict, total=False):
    """Context dict for TOOL category events."""

    tool_name: str  # e.g., "llm_request", "retrieval", "validation"
    provider: str  # e.g., "anthropic", "weaviate"
    model: str  # e.g., "claude-3-5-sonnet"
    tool_version: str  # Optional version identifier


class StageEventContext(TypedDict, total=False):
    """Context dict for STAGE category events."""

    stage_name: str  # e.g., "synthesis", "retrieval", "skills"
    output_length: int  # Size of output (tokens, characters, etc.)
    metadata: dict[str, Any]  # Additional stage-specific data


class CheckpointEventContext(TypedDict, total=False):
    """Context dict for CHECKPOINT category events."""

    validator_type: str  # e.g., "claim_grounding", "schema_validation"
    note_count: int  # Number of validation notes
    failure_reason: str  # If validation failed


class ContentEventContext(TypedDict, total=False):
    """Context dict for CONTENT category events."""

    content_type: str  # e.g., "html", "json", "markdown"
    artifact_path: str  # Where artifact is persisted
    size_bytes: int  # Artifact size


class IterationEventContext(TypedDict, total=False):
    """Context dict for ITERATION category events."""

    iteration_number: int
    gap_count: int  # Identified gaps in current iteration
    refined_queries: list[str]  # Sub-queries generated


# CATEGORY_MAP: Maps EventType to its category string
_CATEGORY_MAP: dict[str, str] = {
    EventType.STAGE_START.value: "STAGE",
    EventType.STAGE_END.value: "STAGE",
    EventType.TOOL_INVOKE.value: "TOOL",
    EventType.TOOL_RESULT.value: "TOOL",
    EventType.TOOL_ERROR.value: "TOOL",
    EventType.TOOL_SKIP.value: "TOOL",
    EventType.CHECKPOINT.value: "CHECKPOINT",
    EventType.VALIDATION_PASS.value: "CHECKPOINT",
    EventType.VALIDATION_FAIL.value: "CHECKPOINT",
    EventType.CONTENT_ADDED.value: "CONTENT",
    EventType.CONTENT_REVISED.value: "CONTENT",
    EventType.ITERATION_START.value: "ITERATION",
    EventType.ITERATION_END.value: "ITERATION",
}

# LIFECYCLE_MAP: Maps EventType to its lifecycle phase
_LIFECYCLE_MAP: dict[str, str] = {
    EventType.STAGE_START.value: "start",
    EventType.STAGE_END.value: "end",
    EventType.TOOL_INVOKE.value: "start",
    EventType.TOOL_RESULT.value: "end",
    EventType.TOOL_ERROR.value: "end",
    EventType.TOOL_SKIP.value: "atomic",
    EventType.CHECKPOINT.value: "atomic",
    EventType.VALIDATION_PASS.value: "end",
    EventType.VALIDATION_FAIL.value: "end",
    EventType.CONTENT_ADDED.value: "atomic",
    EventType.CONTENT_REVISED.value: "atomic",
    EventType.ITERATION_START.value: "start",
    EventType.ITERATION_END.value: "end",
}


def get_event_category(event_type: str) -> str:
    """
    Return the category (STAGE, TOOL, CHECKPOINT, CONTENT, ITERATION) for an event type.

    Args:
        event_type: EventType value (e.g., "tool_invoke", "stage_end")

    Returns:
        Category string or "UNKNOWN" if not found.
    """
    return _CATEGORY_MAP.get(event_type, "UNKNOWN")


def is_valid_event_type(event_type: str) -> bool:
    """
    Check if an event_type is defined in the EventType enum.

    Args:
        event_type: String to validate

    Returns:
        True if event_type is valid, False otherwise.
    """
    return event_type in _CATEGORY_MAP


def get_event_lifecycle(event_type: str) -> str:
    """
    Return the lifecycle phase (start, end, ongoing, atomic) for an event type.

    Args:
        event_type: EventType value

    Returns:
        Lifecycle phase ("start", "end", "ongoing", "atomic") or "unknown".
    """
    return _LIFECYCLE_MAP.get(event_type, "unknown")
