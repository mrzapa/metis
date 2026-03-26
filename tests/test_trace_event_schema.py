"""Tests for trace event schema definitions and helper functions."""

from __future__ import annotations

import pytest

from metis_app.models.trace_event_schema import (
    EventType,
    EventStatus,
    get_event_category,
    is_valid_event_type,
    get_event_lifecycle,
)


class TestEventTypeEnum:
    """Tests for EventType enum membership and values."""

    def test_all_stage_events_present(self) -> None:
        """Verify STAGE category events are defined."""
        assert EventType.STAGE_START.value == "stage_start"
        assert EventType.STAGE_END.value == "stage_end"

    def test_all_tool_events_present(self) -> None:
        """Verify TOOL category events are defined."""
        assert EventType.TOOL_INVOKE.value == "tool_invoke"
        assert EventType.TOOL_RESULT.value == "tool_result"
        assert EventType.TOOL_ERROR.value == "tool_error"
        assert EventType.TOOL_SKIP.value == "tool_skip"

    def test_all_checkpoint_events_present(self) -> None:
        """Verify CHECKPOINT category events are defined."""
        assert EventType.CHECKPOINT.value == "checkpoint"
        assert EventType.VALIDATION_PASS.value == "validation_pass"
        assert EventType.VALIDATION_FAIL.value == "validation_fail"

    def test_all_content_events_present(self) -> None:
        """Verify CONTENT category events are defined."""
        assert EventType.CONTENT_ADDED.value == "content_added"
        assert EventType.CONTENT_REVISED.value == "content_revised"

    def test_all_iteration_events_present(self) -> None:
        """Verify ITERATION category events are defined."""
        assert EventType.ITERATION_START.value == "iteration_start"
        assert EventType.ITERATION_END.value == "iteration_end"

    def test_event_type_str_representation(self) -> None:
        """Verify EventType string conversion."""
        assert str(EventType.TOOL_INVOKE) == "tool_invoke"
        assert str(EventType.VALIDATION_PASS) == "validation_pass"


class TestEventStatusEnum:
    """Tests for EventStatus enum membership and values."""

    def test_all_status_values_present(self) -> None:
        """Verify all EventStatus values are defined."""
        assert EventStatus.SUCCESS.value == "success"
        assert EventStatus.PENDING.value == "pending"
        assert EventStatus.ERROR.value == "error"
        assert EventStatus.SKIPPED.value == "skipped"

    def test_event_status_str_representation(self) -> None:
        """Verify EventStatus string conversion."""
        assert str(EventStatus.SUCCESS) == "success"
        assert str(EventStatus.ERROR) == "error"


class TestGetEventCategory:
    """Tests for get_event_category() helper function."""

    def test_stage_category(self) -> None:
        """Verify STAGE category detection."""
        assert get_event_category("stage_start") == "STAGE"
        assert get_event_category("stage_end") == "STAGE"

    def test_tool_category(self) -> None:
        """Verify TOOL category detection."""
        assert get_event_category("tool_invoke") == "TOOL"
        assert get_event_category("tool_result") == "TOOL"
        assert get_event_category("tool_error") == "TOOL"
        assert get_event_category("tool_skip") == "TOOL"

    def test_checkpoint_category(self) -> None:
        """Verify CHECKPOINT category detection."""
        assert get_event_category("checkpoint") == "CHECKPOINT"
        assert get_event_category("validation_pass") == "CHECKPOINT"
        assert get_event_category("validation_fail") == "CHECKPOINT"

    def test_content_category(self) -> None:
        """Verify CONTENT category detection."""
        assert get_event_category("content_added") == "CONTENT"
        assert get_event_category("content_revised") == "CONTENT"

    def test_iteration_category(self) -> None:
        """Verify ITERATION category detection."""
        assert get_event_category("iteration_start") == "ITERATION"
        assert get_event_category("iteration_end") == "ITERATION"

    def test_unknown_category(self) -> None:
        """Verify unknown event types return 'UNKNOWN'."""
        assert get_event_category("invalid_event") == "UNKNOWN"
        assert get_event_category("") == "UNKNOWN"
        assert get_event_category("llm_request") == "UNKNOWN"


class TestIsValidEventType:
    """Tests for is_valid_event_type() helper function."""

    def test_valid_event_types(self) -> None:
        """Verify valid event types return True."""
        valid_types = [
            "stage_start",
            "stage_end",
            "tool_invoke",
            "tool_result",
            "tool_error",
            "tool_skip",
            "checkpoint",
            "validation_pass",
            "validation_fail",
            "content_added",
            "content_revised",
            "iteration_start",
            "iteration_end",
        ]
        for event_type in valid_types:
            assert is_valid_event_type(event_type) is True, f"{event_type} should be valid"

    def test_invalid_event_types(self) -> None:
        """Verify invalid event types return False."""
        invalid_types = [
            "invalid_event",
            "llm_request",
            "blinkist_summary",
            "tutor_mode",
            "",
            "stage",
            "tool",
        ]
        for event_type in invalid_types:
            assert is_valid_event_type(event_type) is False, f"{event_type} should be invalid"


class TestGetEventLifecycle:
    """Tests for get_event_lifecycle() helper function."""

    def test_start_lifecycle_events(self) -> None:
        """Verify events with 'start' lifecycle."""
        assert get_event_lifecycle("stage_start") == "start"
        assert get_event_lifecycle("tool_invoke") == "start"
        assert get_event_lifecycle("iteration_start") == "start"

    def test_end_lifecycle_events(self) -> None:
        """Verify events with 'end' lifecycle."""
        assert get_event_lifecycle("stage_end") == "end"
        assert get_event_lifecycle("tool_result") == "end"
        assert get_event_lifecycle("tool_error") == "end"
        assert get_event_lifecycle("validation_pass") == "end"
        assert get_event_lifecycle("validation_fail") == "end"
        assert get_event_lifecycle("iteration_end") == "end"

    def test_atomic_lifecycle_events(self) -> None:
        """Verify events with 'atomic' lifecycle (single-point-in-time)."""
        assert get_event_lifecycle("tool_skip") == "atomic"
        assert get_event_lifecycle("checkpoint") == "atomic"
        assert get_event_lifecycle("content_added") == "atomic"
        assert get_event_lifecycle("content_revised") == "atomic"

    def test_unknown_lifecycle(self) -> None:
        """Verify unknown event types return 'unknown'."""
        assert get_event_lifecycle("invalid_event") == "unknown"
        assert get_event_lifecycle("") == "unknown"


class TestCategoryCompleteness:
    """Integration tests ensuring all events are properly categorized."""

    def test_all_event_types_have_category(self) -> None:
        """Verify every EventType enum member is categorized."""
        for member in EventType:
            category = get_event_category(member.value)
            assert category != "UNKNOWN", f"{member.value} missing from category map"
            assert category in {"STAGE", "TOOL", "CHECKPOINT", "CONTENT", "ITERATION"}

    def test_all_event_types_have_lifecycle(self) -> None:
        """Verify every EventType enum member has a lifecycle."""
        for member in EventType:
            lifecycle = get_event_lifecycle(member.value)
            assert lifecycle != "unknown", f"{member.value} missing from lifecycle map"
            assert lifecycle in {"start", "end", "ongoing", "atomic"}

    def test_all_valid_events_are_categorized(self) -> None:
        """Verify all categorized events are marked as valid."""
        valid_types = [
            "stage_start",
            "stage_end",
            "tool_invoke",
            "tool_result",
            "tool_error",
            "tool_skip",
            "checkpoint",
            "validation_pass",
            "validation_fail",
            "content_added",
            "content_revised",
            "iteration_start",
            "iteration_end",
        ]
        for event_type in valid_types:
            assert is_valid_event_type(event_type) is True
            assert get_event_category(event_type) != "UNKNOWN"


class TestCoverageCritical:
    """Tests designed to meet coverage requirements."""

    def test_baseeventpayload_import(self) -> None:
        """Ensure TypedDict imports are available."""
        from metis_app.models.trace_event_schema import BaseEventPayload
        # TypedDict is just a type hint, verify it exists
        assert BaseEventPayload is not None

    def test_context_typeddicts_import(self) -> None:
        """Ensure context TypedDict definitions are available."""
        from metis_app.models.trace_event_schema import (
            ToolEventContext,
            StageEventContext,
            CheckpointEventContext,
            ContentEventContext,
            IterationEventContext,
        )
        assert all([
            ToolEventContext is not None,
            StageEventContext is not None,
            CheckpointEventContext is not None,
            ContentEventContext is not None,
            IterationEventContext is not None,
        ])

    def test_category_and_lifecycle_consistency(self) -> None:
        """Verify no event is both atomic and paired start/end."""
        atomic_events = {
            "tool_skip",
            "checkpoint",
            "content_added",
            "content_revised",
        }
        paired_events = {
            ("stage_start", "stage_end"),
            ("tool_invoke", "tool_result"),
            ("tool_invoke", "tool_error"),
            ("iteration_start", "iteration_end"),
        }
        
        for event_type in atomic_events:
            lifecycle = get_event_lifecycle(event_type)
            assert lifecycle == "atomic", f"{event_type} should be atomic"

        # Verify paired events have complementary lifecycles
        for start_type, end_type in paired_events:
            assert get_event_lifecycle(start_type) == "start"
            assert get_event_lifecycle(end_type) == "end"
