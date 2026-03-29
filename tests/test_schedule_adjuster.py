"""
Tests for Schedule Adjuster component.

Tests failure recovery, deadline pressure handling, and capacity bursting.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.omni.execution.adjuster import (
    AdjustmentType,
    ScheduleAdjuster,
)
from src.omni.task.models import Task, TaskType


class MockTaskMatcher:
    """Mock implementation of TaskMatcherProtocol for testing."""

    def __init__(self, agent_id: str = "coder", confidence: float = 0.8):
        self.agent_id = agent_id
        self.confidence = confidence
        self.match_called = False

    async def match(self, task):
        self.match_called = True
        return {
            "agent_id": self.agent_id,
            "confidence": self.confidence,
            "model": "deepseek-chat",
        }


class MockResourcePool:
    """Mock implementation of ResourcePoolProtocol for testing."""

    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self.allocated = 0
        self.allocations = {}

    def can_allocate(self, requested_concurrent: int = 1) -> bool:
        return self.allocated + requested_concurrent <= self.max_concurrent

    def allocate(self, execution_id: str, concurrent: int = 1) -> bool:
        if not self.can_allocate(concurrent):
            return False
        self.allocated += concurrent
        self.allocations[execution_id] = self.allocations.get(execution_id, 0) + concurrent
        return True

    def release(self, execution_id: str, concurrent: int = 1) -> None:
        if execution_id in self.allocations:
            self.allocated = max(0, self.allocated - concurrent)
            self.allocations[execution_id] = max(0, self.allocations[execution_id] - concurrent)
            if self.allocations[execution_id] == 0:
                del self.allocations[execution_id]

    @property
    def available_concurrent(self) -> int:
        return max(0, self.max_concurrent - self.allocated)

    @property
    def utilization(self) -> dict[str, Any]:
        return {
            "max_concurrent": self.max_concurrent,
            "allocated": self.allocated,
            "available": self.available_concurrent,
            "utilization_pct": round(self.allocated / max(1, self.max_concurrent) * 100, 1),
        }


class MockWorkloadTracker:
    """Mock implementation of WorkloadTrackerProtocol for testing."""

    def __init__(self):
        self.agent_durations = {}
        self.agent_success_rates = {}
        self.throughput = 1.0

    def get_agent_avg_duration(self, agent_id: str) -> float | None:
        return self.agent_durations.get(agent_id)

    def get_agent_success_rate(self, agent_id: str) -> float | None:
        return self.agent_success_rates.get(agent_id)

    def get_throughput(self, window_seconds: float = 300) -> float:
        return self.throughput


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        description="Test task",
        task_type=TaskType.CODE_GENERATION,
        task_id="test-task-123",
        priority=5,
        context={"assigned_agent": "coder"},
    )


@pytest.fixture
def adjuster_without_matcher():
    """Create ScheduleAdjuster without matcher."""
    return ScheduleAdjuster()


@pytest.fixture
def adjuster_with_matcher():
    """Create ScheduleAdjuster with mock matcher."""
    matcher = MockTaskMatcher(agent_id="thinker", confidence=0.9)
    return ScheduleAdjuster(matcher=matcher)


class TestFailureRecovery:
    """Tests for adjust_for_failure method."""

    @pytest.mark.asyncio
    async def test_transient_failure_reschedule(self, adjuster_without_matcher, sample_task):
        """Test that transient failures trigger reschedule."""
        result = await adjuster_without_matcher.adjust_for_failure(
            task=sample_task,
            failure_reason="Rate limit exceeded, please retry",
        )

        assert result.applied
        assert result.adjustment.adjustment_type == AdjustmentType.RESCHEDULE
        assert "transient" in result.adjustment.reason.lower()
        assert result.adjustment.details["failure_type"] == "transient"
        assert result.adjustment.details["backoff_seconds"] == 5.0

    @pytest.mark.asyncio
    async def test_permanent_failure_reassign_with_matcher(self, adjuster_with_matcher, sample_task):
        """Test that permanent failures trigger reassignment when matcher is available."""
        result = await adjuster_with_matcher.adjust_for_failure(
            task=sample_task,
            failure_reason="Authentication failed: invalid API key",
        )

        assert result.applied
        assert result.adjustment.adjustment_type == AdjustmentType.REASSIGN
        assert "permanent" in result.adjustment.reason.lower()
        assert result.adjustment.details["failure_type"] == "permanent"
        assert result.adjustment.details["new_agent"] == "thinker"

        # Verify matcher was called
        assert adjuster_with_matcher.matcher.match_called

    @pytest.mark.asyncio
    async def test_permanent_failure_reschedule_without_matcher(self, adjuster_without_matcher, sample_task):
        """Test that permanent failures trigger reschedule when no matcher is available."""
        result = await adjuster_without_matcher.adjust_for_failure(
            task=sample_task,
            failure_reason="Invalid input format: cannot parse",
        )

        assert result.applied
        assert result.adjustment.adjustment_type == AdjustmentType.RESCHEDULE
        assert "no matcher" in result.adjustment.reason.lower()
        assert result.adjustment.details["failure_type"] == "permanent"

    @pytest.mark.asyncio
    async def test_matcher_error_falls_back_to_reschedule(self, sample_task):
        """Test that matcher errors fall back to reschedule."""
        matcher = MockTaskMatcher()
        matcher.match = AsyncMock(side_effect=Exception("Matcher unavailable"))
        adjuster = ScheduleAdjuster(matcher=matcher)

        result = await adjuster.adjust_for_failure(
            task=sample_task,
            failure_reason="Some failure",
        )

        assert result.applied
        assert result.adjustment.adjustment_type == AdjustmentType.RESCHEDULE
        assert "matcher error" in result.adjustment.reason.lower()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("failure_reason,expected_transient", [
        ("Rate limit exceeded", True),
        ("Timeout after 30 seconds", True),
        ("HTTP 429 Too Many Requests", True),
        ("HTTP 503 Service Unavailable", True),
        ("Authentication failed", False),
        ("Invalid input format", False),
        ("Permission denied", False),
        ("Syntax error in code", False),
    ])
    async def test_transient_failure_detection(self, adjuster_without_matcher, sample_task,
                                               failure_reason, expected_transient):
        """Test that transient failures are correctly identified."""
        result = await adjuster_without_matcher.adjust_for_failure(
            task=sample_task,
            failure_reason=failure_reason,
        )

        if expected_transient:
            assert result.adjustment.details["failure_type"] == "transient"
        else:
            assert result.adjustment.details["failure_type"] == "permanent"


class TestDeadlinePressure:
    """Tests for adjust_for_deadline_pressure method."""

    @pytest.mark.asyncio
    async def test_overdue_deadline(self, adjuster_with_matcher, sample_task):
        """Test handling of overdue deadlines."""
        result = await adjuster_with_matcher.adjust_for_deadline_pressure(
            task=sample_task,
            time_remaining=-10.0,  # Overdue by 10 seconds
        )

        assert result.applied
        assert result.adjustment.adjustment_type == AdjustmentType.REASSIGN
        assert "overdue" in result.adjustment.reason.lower()
        assert result.adjustment.details["urgency"] == "overdue"
        assert result.adjustment.details["priority_boost"] is True

    @pytest.mark.asyncio
    async def test_critical_deadline(self, adjuster_with_matcher, sample_task):
        """Test handling of critical deadlines (<60 seconds)."""
        result = await adjuster_with_matcher.adjust_for_deadline_pressure(
            task=sample_task,
            time_remaining=30.0,  # 30 seconds remaining
        )

        assert result.applied
        assert result.adjustment.adjustment_type == AdjustmentType.REASSIGN
        assert "critical" in result.adjustment.reason.lower()
        assert result.adjustment.details["urgency"] == "critical"
        assert result.adjustment.details["priority_boost"] is True

    @pytest.mark.asyncio
    async def test_high_deadline(self, adjuster_with_matcher, sample_task):
        """Test handling of high urgency deadlines (60-300 seconds)."""
        result = await adjuster_with_matcher.adjust_for_deadline_pressure(
            task=sample_task,
            time_remaining=150.0,  # 2.5 minutes remaining
        )

        assert result.applied
        assert result.adjustment.adjustment_type == AdjustmentType.RESCHEDULE
        assert "high" in result.adjustment.reason.lower()
        assert result.adjustment.details["urgency"] == "high"
        assert result.adjustment.details["priority_boost"] is False

    @pytest.mark.asyncio
    async def test_normal_deadline(self, adjuster_with_matcher, sample_task):
        """Test handling of normal deadlines (>300 seconds)."""
        result = await adjuster_with_matcher.adjust_for_deadline_pressure(
            task=sample_task,
            time_remaining=600.0,  # 10 minutes remaining
        )

        assert result.applied
        assert result.adjustment.adjustment_type == AdjustmentType.RESCHEDULE
        assert "normal" in result.adjustment.reason.lower()
        assert result.adjustment.details["urgency"] == "normal"
        assert result.adjustment.details["priority_boost"] is False

    @pytest.mark.asyncio
    async def test_deadline_without_matcher(self, adjuster_without_matcher, sample_task):
        """Test deadline handling when no matcher is available."""
        result = await adjuster_without_matcher.adjust_for_deadline_pressure(
            task=sample_task,
            time_remaining=30.0,  # Critical deadline
        )

        assert result.applied
        # Without matcher, should reschedule even for critical deadlines
        assert result.adjustment.adjustment_type == AdjustmentType.RESCHEDULE
        assert result.adjustment.details["urgency"] == "critical"


class TestCapacityBursting:
    """Tests for adjust_for_capacity_needs method."""

    @pytest.mark.asyncio
    async def test_capacity_burst(self, adjuster_without_matcher):
        """Test requesting a capacity burst."""
        result = await adjuster_without_matcher.burst_capacity(
            workflow_id="test-workflow-123",
            additional_concurrent=3,
            duration_seconds=180.0,
            reason="Workload surge detected",
        )

        assert result.applied
        assert result.adjustment.adjustment_type == AdjustmentType.BURST
        assert "burst" in result.message.lower()
        assert result.adjustment.details["additional_concurrent"] == 3
        assert result.adjustment.details["duration_seconds"] == 180.0
        assert result.adjustment.details["workflow_id"] == "test-workflow-123"

    @pytest.mark.asyncio
    async def test_capacity_burst_defaults(self, adjuster_without_matcher):
        """Test capacity burst with default values using legacy method."""
        result = await adjuster_without_matcher.adjust_for_capacity_needs(
            workflow_id="test-workflow-456",
            additional_resources={},  # Empty dict should use defaults
        )

        assert result.applied
        assert result.adjustment.details["additional_concurrent"] == 1  # Default
        assert result.adjustment.details["duration_seconds"] == 300.0  # Default

    @pytest.mark.asyncio
    async def test_active_bursts_tracking(self, adjuster_without_matcher):
        """Test that active bursts are tracked correctly."""
        # Request a burst
        await adjuster_without_matcher.adjust_for_capacity_needs(
            workflow_id="test-workflow-123",
            additional_resources={
                "concurrent": 2,
                "duration_seconds": 0.1,  # Short duration for testing
            },
        )

        # Check active bursts
        active_bursts = adjuster_without_matcher.get_active_bursts()
        assert len(active_bursts) == 1

        burst_id = list(active_bursts.keys())[0]
        burst_info = active_bursts[burst_id]
        assert burst_info["workflow_id"] == "test-workflow-123"
        assert burst_info["concurrent"] == 2
        assert burst_info["remaining_seconds"] <= 0.1

        # Wait for burst to expire
        await asyncio.sleep(0.15)

        # Check that burst was cleaned up
        active_bursts = adjuster_without_matcher.get_active_bursts()
        assert len(active_bursts) == 0


class TestAdjustmentHistory:
    """Tests for adjustment history and summary."""

    @pytest.mark.asyncio
    async def test_adjustment_history(self, adjuster_without_matcher, sample_task):
        """Test that adjustments are logged in history."""
        # Make some adjustments
        await adjuster_without_matcher.adjust_for_failure(
            task=sample_task,
            failure_reason="Test failure 1",
        )

        await adjuster_without_matcher.adjust_for_deadline_pressure(
            task=sample_task,
            time_remaining=45.0,
        )

        # Check history
        history = adjuster_without_matcher.get_adjustment_history()
        assert len(history) == 2
        assert history[0].adjustment.task_id == sample_task.task_id
        assert history[1].adjustment.task_id == sample_task.task_id

    @pytest.mark.asyncio
    async def test_adjustment_summary(self, adjuster_without_matcher, sample_task):
        """Test adjustment summary statistics."""
        # Make adjustments of different types
        await adjuster_without_matcher.adjust_for_failure(
            task=sample_task,
            failure_reason="Failure 1",
        )

        await adjuster_without_matcher.adjust_for_failure(
            task=sample_task,
            failure_reason="Failure 2",
        )

        await adjuster_without_matcher.adjust_for_deadline_pressure(
            task=sample_task,
            time_remaining=100.0,
        )

        await adjuster_without_matcher.adjust_for_capacity_needs(
            workflow_id="test-workflow",
            additional_resources={"concurrent": 1},
        )

        # Check summary
        summary = adjuster_without_matcher.get_adjustment_summary()
        assert summary["total_adjustments"] == 4
        # 2 failures (transient detection) + 1 deadline pressure (high urgency) = 3 reschedules
        assert summary["by_type"]["reschedule"] == 3
        assert summary["by_type"]["burst"] == 1

    @pytest.mark.asyncio
    async def test_concurrent_adjustments(self, adjuster_without_matcher):
        """Test that adjustments can be made concurrently."""
        tasks = [
            Task(
                description=f"Task {i}",
                task_type=TaskType.CODE_GENERATION,
                task_id=f"task-{i}",
                priority=i,
            )
            for i in range(10)
        ]

        # Make adjustments concurrently
        adjustments = await asyncio.gather(*[
            adjuster_without_matcher.adjust_for_failure(
                task=task,
                failure_reason=f"Failure {i}",
            )
            for i, task in enumerate(tasks)
        ])

        # Verify all adjustments were made
        assert len(adjustments) == 10
        for result in adjustments:
            assert result.applied

        # Verify history contains all adjustments
        history = adjuster_without_matcher.get_adjustment_history()
        assert len(history) == 10


class TestIntegration:
    """Integration tests for ScheduleAdjuster."""

    @pytest.mark.asyncio
    async def test_full_adjustment_flow(self, adjuster_with_matcher, sample_task):
        """Test a complete adjustment flow with all adjustment types."""
        # 1. Handle a failure
        failure_result = await adjuster_with_matcher.adjust_for_failure(
            task=sample_task,
            failure_reason="Rate limit exceeded",
        )
        assert failure_result.applied

        # 2. Handle deadline pressure
        deadline_result = await adjuster_with_matcher.adjust_for_deadline_pressure(
            task=sample_task,
            time_remaining=25.0,  # Critical
        )
        assert deadline_result.applied

        # 3. Request capacity burst
        burst_result = await adjuster_with_matcher.adjust_for_capacity_needs(
            workflow_id=sample_task.task_id[:8],  # Use part of task ID as workflow ID
            additional_resources={
                "concurrent": 2,
                "duration_seconds": 60.0,
                "reason": "Critical deadline approaching",
            },
        )
        assert burst_result.applied

        # 4. Verify summary
        summary = adjuster_with_matcher.get_adjustment_summary()
        assert summary["total_adjustments"] == 3
        assert summary["active_bursts"] == 1

        # 5. Verify history
        history = adjuster_with_matcher.get_adjustment_history()
        assert len(history) == 3
        assert history[0].adjustment.adjustment_type == AdjustmentType.RESCHEDULE
        assert history[1].adjustment.adjustment_type == AdjustmentType.REASSIGN
        assert history[2].adjustment.adjustment_type == AdjustmentType.BURST


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
