"""
Tests for task executors.
"""

import asyncio
import pytest

from src.omni.execution.executor import MockTaskExecutor
from src.omni.execution.config import ExecutionContext
from src.omni.task.models import Task, TaskType, TaskStatus
from src.omni.execution.models import TaskExecutionError, TaskFatalError


@pytest.mark.asyncio
async def test_mock_executor_success() -> None:
    """Test MockTaskExecutor with high success rate."""
    executor = MockTaskExecutor(
        success_rate=1.0,  # Always succeed
        avg_delay=0.01,    # Fast execution for tests
        delay_variance=0.0,
    )
    
    task = Task(description="Test task")
    context = ExecutionContext(
        dependency_results={},
        execution_id="test123",
        task_index=1,
        total_tasks=5,
    )
    
    result = await executor.execute(task, context)
    
    assert result.task_id == task.task_id
    assert result.status == TaskStatus.COMPLETED
    assert "result" in result.outputs
    assert "Mock result for task" in result.outputs["result"]
    assert result.tokens_used > 0
    assert result.cost > 0
    assert result.metadata["mock_executor"] is True


@pytest.mark.asyncio
async def test_mock_executor_failure() -> None:
    """Test MockTaskExecutor with low success rate."""
    executor = MockTaskExecutor(
        success_rate=0.0,  # Always fail
        avg_delay=0.01,
        delay_variance=0.0,
    )
    
    task = Task(description="Test task")
    context = ExecutionContext(
        dependency_results={},
        execution_id="test123",
        task_index=1,
        total_tasks=5,
    )
    
    # Run multiple times to test different failure modes
    fatal_error_count = 0
    execution_error_count = 0
    failed_result_count = 0
    
    for _ in range(30):  # Run enough times to likely hit all failure modes
        try:
            result = await executor.execute(task, context)
            # If we get here, it's a failed result (not an exception)
            assert result.status == TaskStatus.FAILED
            failed_result_count += 1
        except TaskFatalError:
            fatal_error_count += 1
        except TaskExecutionError:
            execution_error_count += 1
    
    # We should have seen all failure modes
    assert fatal_error_count + execution_error_count + failed_result_count == 30
    # Each should have occurred at least once
    assert fatal_error_count > 0
    assert execution_error_count > 0
    assert failed_result_count > 0


@pytest.mark.asyncio
async def test_mock_executor_delay() -> None:
    """Test MockTaskExecutor delay simulation."""
    executor = MockTaskExecutor(
        success_rate=1.0,
        avg_delay=0.1,
        delay_variance=0.05,
    )
    
    task = Task(description="Test task")
    context = ExecutionContext(
        dependency_results={},
        execution_id="test123",
        task_index=1,
        total_tasks=5,
    )
    
    # Measure execution time
    import time
    start_time = time.time()
    result = await executor.execute(task, context)
    end_time = time.time()
    
    elapsed = end_time - start_time
    
    # Should take roughly 0.1 seconds +/- variance
    assert 0.05 <= elapsed <= 0.15  # Allow some tolerance
    assert result.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_mock_executor_context() -> None:
    """Test MockTaskExecutor with dependency context."""
    executor = MockTaskExecutor(success_rate=1.0, avg_delay=0.01)
    
    # Create a task with mock dependency results
    from src.omni.task.models import TaskResult
    
    dependency_results = {
        "dep1": TaskResult(task_id="dep1", status=TaskStatus.COMPLETED),
        "dep2": TaskResult(task_id="dep2", status=TaskStatus.COMPLETED),
    }
    
    task = Task(description="Test task with dependencies")
    context = ExecutionContext(
        dependency_results=dependency_results,
        execution_id="test123",
        task_index=3,
        total_tasks=10,
    )
    
    result = await executor.execute(task, context)
    
    assert result.status == TaskStatus.COMPLETED
    assert result.outputs["context_size"] == 2
    assert result.outputs["execution_id"] == "test123"


def test_mock_executor_configuration() -> None:
    """Test MockTaskExecutor configuration."""
    executor = MockTaskExecutor(
        success_rate=0.7,
        avg_delay=2.0,
        delay_variance=1.0,
        token_cost_per_task=500,
        cost_per_token=0.00001,
    )
    
    # Test with success
    # Note: We can't easily test the exact configuration without running many times
    # But we can verify the executor was created with these values
    assert executor.success_rate == 0.7
    assert executor.avg_delay == 2.0
    assert executor.delay_variance == 1.0
    assert executor.token_cost_per_task == 500
    assert executor.cost_per_token == 0.00001


@pytest.mark.asyncio
async def test_mock_executor_cancellation() -> None:
    """Test that MockTaskExecutor respects cancellation."""
    executor = MockTaskExecutor(
        success_rate=1.0,
        avg_delay=1.0,  # Long delay to allow cancellation
        delay_variance=0.0,
    )
    
    task = Task(description="Test task")
    context = ExecutionContext(
        dependency_results={},
        execution_id="test123",
        task_index=1,
        total_tasks=5,
    )
    
    # Create a task and cancel it
    task_future = asyncio.create_task(executor.execute(task, context))
    
    # Cancel immediately
    task_future.cancel()
    
    # Should raise CancelledError
    with pytest.raises(asyncio.CancelledError):
        await task_future