"""
Tests for execution models.
"""

from datetime import datetime, timedelta

from src.omni.execution.models import (
    ExecutionAbortedError,
    ExecutionMetrics,
    ExecutionResult,
    ExecutionStatus,
    TaskExecutionError,
    TaskFatalError,
)
from src.omni.task.models import TaskResult, TaskStatus


def test_execution_status() -> None:
    """Test ExecutionStatus enum."""
    assert ExecutionStatus.RUNNING.value == "running"
    assert ExecutionStatus.COMPLETED.value == "completed"
    assert ExecutionStatus.FAILED.value == "failed"
    assert ExecutionStatus.CANCELLED.value == "cancelled"
    assert ExecutionStatus.PARTIAL.value == "partial"

    # String representation
    assert str(ExecutionStatus.RUNNING) == "running"


def test_execution_metrics() -> None:
    """Test ExecutionMetrics."""
    metrics = ExecutionMetrics(
        execution_id="test123",
        total_tasks=10,
        completed=5,
        failed=1,
        skipped=2,
        cancelled=0,
        running=1,
        pending=1,
        total_tokens_used=1000,
        total_cost=0.02,
        wall_clock_seconds=10.5,
        parallel_efficiency=0.8,
    )

    assert metrics.execution_id == "test123"
    assert metrics.total_tasks == 10
    assert metrics.completed == 5
    assert metrics.failed == 1
    assert metrics.skipped == 2
    assert metrics.cancelled == 0
    assert metrics.running == 1
    assert metrics.pending == 1
    assert metrics.total_tokens_used == 1000
    assert metrics.total_cost == 0.02
    assert metrics.wall_clock_seconds == 10.5
    assert metrics.parallel_efficiency == 0.8

    # Test update_from_results
    results = {
        "task1": TaskResult(task_id="task1", status=TaskStatus.COMPLETED, tokens_used=100, cost=0.002),
        "task2": TaskResult(task_id="task2", status=TaskStatus.FAILED, tokens_used=50, cost=0.001),
        "task3": TaskResult(task_id="task3", status=TaskStatus.SKIPPED, tokens_used=0, cost=0.0),
        "task4": TaskResult(task_id="task4", status=TaskStatus.CANCELLED, tokens_used=0, cost=0.0),
    }

    metrics.update_from_results(results)
    assert metrics.completed == 1
    assert metrics.failed == 1
    assert metrics.skipped == 1
    assert metrics.cancelled == 1
    assert metrics.total_tokens_used == 150
    assert metrics.total_cost == 0.003


def test_execution_result() -> None:
    """Test ExecutionResult."""
    started_at = datetime.now()
    completed_at = started_at + timedelta(seconds=10)

    # Create some mock results
    results = {
        "task1": TaskResult(task_id="task1", status=TaskStatus.COMPLETED),
        "task2": TaskResult(task_id="task2", status=TaskStatus.FAILED),
    }

    metrics = ExecutionMetrics(
        execution_id="test123",
        total_tasks=2,
        completed=1,
        failed=1,
    )

    result = ExecutionResult(
        execution_id="test123",
        graph_name="test_graph",
        status=ExecutionStatus.PARTIAL,
        results=results,
        metrics=metrics,
        started_at=started_at,
        completed_at=completed_at,
        dead_letter=["task2"],
        config={"max_concurrent": 5},
    )

    assert result.execution_id == "test123"
    assert result.graph_name == "test_graph"
    assert result.status == ExecutionStatus.PARTIAL
    assert len(result.results) == 2
    assert result.metrics.total_tasks == 2
    assert result.started_at == started_at
    assert result.completed_at == completed_at
    assert result.dead_letter == ["task2"]
    assert result.config == {"max_concurrent": 5}

    # Test success property
    result.status = ExecutionStatus.COMPLETED
    assert result.success is True

    result.status = ExecutionStatus.FAILED
    assert result.success is False

    # Test duration_seconds
    assert result.duration_seconds == 10.0

    # Test with None completed_at
    result.completed_at = None
    assert result.duration_seconds is None


def test_execution_aborted_error() -> None:
    """Test ExecutionAbortedError."""
    result = ExecutionResult(
        execution_id="test123",
        graph_name="test_graph",
        status=ExecutionStatus.FAILED,
        results={},
        metrics=ExecutionMetrics(execution_id="test123", total_tasks=0),
        started_at=datetime.now(),
        completed_at=datetime.now(),
    )

    error = ExecutionAbortedError("task1", result)

    assert error.failed_task_id == "task1"
    assert error.result == result
    assert "task1" in str(error)


def test_task_errors() -> None:
    """Test task error classes."""
    recoverable = TaskExecutionError("Recoverable error")
    fatal = TaskFatalError("Fatal error")

    assert str(recoverable) == "Recoverable error"
    assert str(fatal) == "Fatal error"

    # They should be distinct exception types
    assert isinstance(recoverable, Exception)
    assert isinstance(fatal, Exception)
