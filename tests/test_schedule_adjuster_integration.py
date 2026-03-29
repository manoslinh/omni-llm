"""
Integration tests for Schedule Adjuster with P2-14 TaskMatcher.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.omni.execution.adjuster import (
    AdjustmentType,
    ScheduleAdjuster,
)
from src.omni.task.models import Task, TaskType


@pytest.fixture
def mock_task_matcher():
    """Create a mock P2-14 TaskMatcher."""
    matcher = AsyncMock()
    matcher.match.return_value = {
        "agent_id": "escalated-agent",
        "confidence": 0.9,
        "model": "mimo-v2-pro",
        "reason": "Task requires escalation",
    }
    return matcher


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        description="Integration test task",
        task_type=TaskType.CODE_GENERATION,
        task_id="integration-test-001",
        priority=7,
        context={"assigned_agent": "initial-agent"},
    )


@pytest.mark.asyncio
async def test_integration_with_matcher(sample_task):
    """Test ScheduleAdjuster integration with P2-14 TaskMatcher."""
    # Create mock matcher (not using fixture to avoid issues)
    mock_task_matcher = AsyncMock()
    mock_task_matcher.match.return_value = {
        "agent_id": "escalated-agent",
        "confidence": 0.9,
        "model": "mimo-v2-pro",
        "reason": "Task requires escalation",
    }

    # Create adjuster with mock matcher
    adjuster = ScheduleAdjuster(matcher=mock_task_matcher)

    # Test 1: Permanent failure triggers reassignment via matcher
    result = await adjuster.adjust_for_failure(
        task=sample_task,
        failure_reason="Authentication failed: invalid API key",
    )

    assert result.applied
    assert result.adjustment.adjustment_type == AdjustmentType.REASSIGN

    # Verify adjustment details include matcher results
    # If matcher was called, we should see its results in details
    assert result.adjustment.details["new_agent"] == "escalated-agent"
    assert result.adjustment.details["confidence"] == 0.9

    # Test 2: Critical deadline triggers reassignment via matcher
    # Reset mock and set new return value
    mock_task_matcher.reset_mock()
    mock_task_matcher.match.return_value = {
        "agent_id": "critical-agent",
        "confidence": 0.95,
        "model": "mimo-v2-pro",
        "reason": "Critical deadline",
    }

    result = await adjuster.adjust_for_deadline_pressure(
        task=sample_task,
        time_remaining=25.0,  # Critical deadline
    )

    assert result.applied
    assert result.adjustment.adjustment_type == AdjustmentType.REASSIGN

    # Test 3: Normal deadline doesn't trigger matcher
    mock_task_matcher.reset_mock()
    result = await adjuster.adjust_for_deadline_pressure(
        task=sample_task,
        time_remaining=400.0,  # Normal deadline
    )

    assert result.applied
    assert result.adjustment.adjustment_type == AdjustmentType.RESCHEDULE
    # For normal deadlines, we expect reschedule, not reassign


@pytest.mark.asyncio
async def test_matcher_error_handling(sample_task):
    """Test graceful handling of matcher errors."""
    # Create matcher that raises exception
    matcher = AsyncMock()
    matcher.match.side_effect = Exception("Matcher service unavailable")

    adjuster = ScheduleAdjuster(matcher=matcher)

    # Should fall back to reschedule when matcher fails
    result = await adjuster.adjust_for_failure(
        task=sample_task,
        failure_reason="Some failure",
    )

    assert result.applied
    assert result.adjustment.adjustment_type == AdjustmentType.RESCHEDULE
    assert "matcher error" in result.adjustment.reason.lower()


@pytest.mark.asyncio
async def test_capacity_bursting_without_matcher(sample_task):
    """Test capacity bursting works independently of matcher."""
    # Create adjuster without matcher
    adjuster = ScheduleAdjuster()

    # Capacity bursting should work without matcher
    result = await adjuster.burst_capacity(
        workflow_id="test-workflow",
        additional_concurrent=2,
        duration_seconds=60,
        reason="Test burst",
    )

    assert result.applied
    assert result.adjustment.adjustment_type == AdjustmentType.BURST
    assert result.adjustment.details["additional_concurrent"] == 2


@pytest.mark.asyncio
async def test_adjustment_history_integration(mock_task_matcher, sample_task):
    """Test adjustment history tracks all integration events."""
    adjuster = ScheduleAdjuster(matcher=mock_task_matcher)

    # Make multiple adjustments
    await adjuster.adjust_for_failure(sample_task, "Failure 1")
    await adjuster.adjust_for_deadline_pressure(sample_task, 45.0)
    await adjuster.adjust_for_capacity_needs("workflow-1", {"concurrent": 1})

    # Verify history
    history = adjuster.get_adjustment_history()
    assert len(history) == 3

    # Verify summary
    summary = adjuster.get_adjustment_summary()
    assert summary["total_adjustments"] == 3
    # Check burst count
    assert summary["by_type"].get("burst", 0) == 1
    # Check we have some adjustments
    assert sum(summary["by_type"].values()) == 3


@pytest.mark.asyncio
async def test_concurrent_adjustments_with_matcher(mock_task_matcher):
    """Test concurrent adjustments with matcher integration."""
    adjuster = ScheduleAdjuster(matcher=mock_task_matcher)

    # Create multiple tasks
    tasks = [
        Task(
            description=f"Task {i}",
            task_type=TaskType.CODE_GENERATION,
            task_id=f"task-{i}",
            priority=i,
        )
        for i in range(5)
    ]

    # Make concurrent adjustments
    adjustments = await asyncio.gather(*[
        adjuster.adjust_for_failure(task, f"Failure {i}")
        for i, task in enumerate(tasks)
    ])

    # Verify all succeeded
    assert len(adjustments) == 5
    for result in adjustments:
        assert result.applied

    # Verify matcher was called for each
    assert mock_task_matcher.match.call_count == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
