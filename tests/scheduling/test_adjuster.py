"""
Tests for schedule adjuster.
"""

from unittest.mock import Mock

import pytest

from omni.execution.adjuster import (
    Adjustment,
    AdjustmentResult,
    AdjustmentType,
    ScheduleAdjuster,
)
from omni.task.models import Task


class TestAdjustment:
    """Tests for Adjustment class."""

    def test_initialization(self):
        adjustment = Adjustment(
            adjustment_type=AdjustmentType.RESCHEDULE,
            task_id="task1",
            reason="Test adjustment",
            details={"key": "value"},
        )

        assert adjustment.adjustment_type == AdjustmentType.RESCHEDULE
        assert adjustment.task_id == "task1"
        assert adjustment.reason == "Test adjustment"
        assert adjustment.details == {"key": "value"}

    def test_default_details(self):
        adjustment = Adjustment(
            adjustment_type=AdjustmentType.REASSIGN,
            task_id="task1",
            reason="Test",
        )

        assert adjustment.details == {}


class TestAdjustmentResult:
    """Tests for AdjustmentResult class."""

    def test_initialization(self):
        adjustment = Adjustment(
            adjustment_type=AdjustmentType.RESCHEDULE,
            task_id="task1",
            reason="Test",
        )

        result = AdjustmentResult(
            adjustment=adjustment,
            applied=True,
            previous_value="old",
            new_value="new",
            message="Adjustment applied",
        )

        assert result.adjustment == adjustment
        assert result.applied is True
        assert result.previous_value == "old"
        assert result.new_value == "new"
        assert result.message == "Adjustment applied"

    def test_default_values(self):
        adjustment = Adjustment(
            adjustment_type=AdjustmentType.RESCHEDULE,
            task_id="task1",
            reason="Test",
        )

        result = AdjustmentResult(
            adjustment=adjustment,
            applied=False,
        )

        assert result.previous_value is None
        assert result.new_value is None
        assert result.message == ""


class TestScheduleAdjuster:
    """Tests for ScheduleAdjuster class."""

    @pytest.fixture
    def mock_task(self):
        task = Mock(spec=Task)
        task.task_id = "test_task"
        task.priority = 50  # MEDIUM priority (0-100 scale)
        task.context = {"assigned_agent": "coder"}
        task.retry_count = 0
        return task

    @pytest.fixture
    def mock_matcher(self):
        from unittest.mock import AsyncMock
        matcher = Mock()
        matcher.match = AsyncMock(return_value={
            "agent_id": "coder",
            "confidence": 0.8,
            "model": "deepseek-chat"
        })
        return matcher

    @pytest.fixture
    def mock_tracker(self):
        return Mock()

    @pytest.mark.asyncio
    async def test_initialization(self):
        adjuster = ScheduleAdjuster()
        assert adjuster.matcher is None
        assert adjuster.tracker is None
        assert adjuster._adjustment_log == []

    @pytest.mark.asyncio
    async def test_initialization_with_dependencies(self, mock_matcher, mock_tracker):
        adjuster = ScheduleAdjuster(matcher=mock_matcher, tracker=mock_tracker)
        assert adjuster.matcher == mock_matcher
        assert adjuster.tracker == mock_tracker

    @pytest.mark.asyncio
    async def test_adjust_for_failure_transient_error(self, mock_task):
        adjuster = ScheduleAdjuster()

        result = await adjuster.adjust_for_failure(
            task=mock_task,
            failure_reason="Rate limit exceeded, please try again",
        )

        assert result.applied is True
        assert result.adjustment.adjustment_type == AdjustmentType.RESCHEDULE
        assert "transient" in result.adjustment.reason.lower()
        assert result.adjustment.details.get("backoff_seconds") == 5.0

        # Should be logged
        assert len(adjuster._adjustment_log) == 1
        assert adjuster._adjustment_log[0] == result

    @pytest.mark.asyncio
    async def test_adjust_for_failure_permanent_error_with_matcher(self, mock_task, mock_matcher):
        adjuster = ScheduleAdjuster(matcher=mock_matcher)

        result = await adjuster.adjust_for_failure(
            task=mock_task,
            failure_reason="Authentication failed: invalid API key",
        )

        assert result.applied is True
        assert result.adjustment.adjustment_type == AdjustmentType.REASSIGN
        assert "permanent" in result.adjustment.reason.lower()
        assert result.adjustment.details["previous_agent"] == "coder"  # From task.context
        assert result.adjustment.details["new_agent"] == "coder"

        # Matcher should have been called
        mock_matcher.match.assert_called_once_with(mock_task)

    @pytest.mark.asyncio
    async def test_adjust_for_failure_permanent_error_same_agent(self, mock_task, mock_matcher):
        # Configure matcher to return same agent
        from unittest.mock import AsyncMock
        mock_matcher.match = AsyncMock(return_value={
            "agent_id": "coder",  # Same as current agent
            "confidence": 0.8,
            "model": "deepseek-chat"
        })

        adjuster = ScheduleAdjuster(matcher=mock_matcher)

        result = await adjuster.adjust_for_failure(
            task=mock_task,
            failure_reason="Invalid input format",
        )

        # In the new implementation, if matcher returns same agent, it should still be REASSIGN
        # (not ESCALATE) because the logic doesn't check for same agent
        assert result.adjustment.adjustment_type == AdjustmentType.REASSIGN
        assert result.adjustment.details["new_agent"] == "coder"

    @pytest.mark.asyncio
    async def test_adjust_for_failure_permanent_error_no_matcher(self, mock_task):
        adjuster = ScheduleAdjuster()  # No matcher

        result = await adjuster.adjust_for_failure(
            task=mock_task,
            failure_reason="Invalid input format",
        )

        # Should reschedule since no matcher available
        assert result.adjustment.adjustment_type == AdjustmentType.RESCHEDULE
        assert "no matcher" in result.adjustment.reason.lower()

    @pytest.mark.asyncio
    async def test_adjust_for_deadline_pressure_overdue(self, mock_task):
        adjuster = ScheduleAdjuster()

        result = await adjuster.adjust_for_deadline_pressure(
            task=mock_task,
            time_remaining=-10,  # Overdue
        )

        assert result.applied is True
        assert result.adjustment.task_id == "test_task"
        assert "overdue" in result.adjustment.reason.lower()
        assert result.adjustment.details["urgency"] == "overdue"
        assert result.adjustment.details["priority_boost"] is True

    @pytest.mark.asyncio
    async def test_adjust_for_deadline_pressure_critical(self, mock_task):
        adjuster = ScheduleAdjuster()

        result = await adjuster.adjust_for_deadline_pressure(
            task=mock_task,
            time_remaining=30,
        )
        assert result.applied is True
        assert "critical" in result.adjustment.reason.lower()
        assert result.adjustment.details["urgency"] == "critical"
        assert result.adjustment.details["priority_boost"] is True
        # Critical without matcher should trigger reschedule
        assert result.adjustment.adjustment_type == AdjustmentType.RESCHEDULE

    @pytest.mark.asyncio
    async def test_adjust_for_deadline_pressure_high(self, mock_task):
        adjuster = ScheduleAdjuster()

        result = await adjuster.adjust_for_deadline_pressure(
            task=mock_task,
            time_remaining=120,
        )
        assert result.applied is True
        assert result.adjustment.details["urgency"] == "high"
        assert result.adjustment.details["priority_boost"] is False
        # High should trigger reschedule (not reassign)
        assert result.adjustment.adjustment_type == AdjustmentType.RESCHEDULE

    @pytest.mark.asyncio
    async def test_adjust_for_deadline_pressure_normal(self, mock_task):
        adjuster = ScheduleAdjuster()

        result = await adjuster.adjust_for_deadline_pressure(
            task=mock_task,
            time_remaining=600,
        )
        assert result.applied is True
        assert result.adjustment.details["urgency"] == "normal"
        assert result.adjustment.details["priority_boost"] is False

    @pytest.mark.asyncio
    async def test_burst_capacity(self):
        adjuster = ScheduleAdjuster()

        result = await adjuster.burst_capacity(
            workflow_id="wf1",
            additional_concurrent=3,
            duration_seconds=60.0,
            reason="Falling behind schedule",
        )

        assert result.applied is True
        assert result.adjustment.adjustment_type == AdjustmentType.BURST
        assert result.adjustment.task_id == ""  # Workflow-level adjustment
        assert "burst" in result.message.lower()
        assert result.adjustment.details["workflow_id"] == "wf1"
        assert result.adjustment.details["additional_concurrent"] == 3
        assert result.adjustment.details["duration_seconds"] == 60.0

    def test_get_adjustment_history(self):
        adjuster = ScheduleAdjuster()

        # Add some adjustments
        adjustment1 = Adjustment(
            adjustment_type=AdjustmentType.RESCHEDULE,
            task_id="task1",
            reason="Test 1",
        )
        result1 = AdjustmentResult(adjustment=adjustment1, applied=True)
        adjuster._adjustment_log.append(result1)

        adjustment2 = Adjustment(
            adjustment_type=AdjustmentType.REASSIGN,
            task_id="task2",
            reason="Test 2",
        )
        result2 = AdjustmentResult(adjustment=adjustment2, applied=False)
        adjuster._adjustment_log.append(result2)

        history = adjuster.get_adjustment_history()

        assert len(history) == 2
        assert history[0] == result1
        assert history[1] == result2
        # Should return a copy, not the original list
        assert history is not adjuster._adjustment_log

    def test_get_adjustment_summary(self):
        adjuster = ScheduleAdjuster()

        # Add adjustments of different types
        adjustments = [
            (AdjustmentType.RESCHEDULE, "task1"),
            (AdjustmentType.RESCHEDULE, "task2"),
            (AdjustmentType.REASSIGN, "task3"),
            (AdjustmentType.ESCALATE, "task4"),
            (AdjustmentType.BURST, ""),
        ]

        for adj_type, task_id in adjustments:
            adjustment = Adjustment(
                adjustment_type=adj_type,
                task_id=task_id,
                reason=f"Test {adj_type.value}",
            )
            result = AdjustmentResult(adjustment=adjustment, applied=True)
            adjuster._adjustment_log.append(result)

        summary = adjuster.get_adjustment_summary()

        assert summary["total_adjustments"] == 5
        assert summary["by_type"]["reschedule"] == 2
        assert summary["by_type"]["reassign"] == 1
        assert summary["by_type"]["escalate"] == 1
        assert summary["by_type"]["burst"] == 1

    def test_get_adjustment_summary_empty(self):
        adjuster = ScheduleAdjuster()

        summary = adjuster.get_adjustment_summary()

        assert summary["total_adjustments"] == 0
        assert summary["by_type"] == {}
