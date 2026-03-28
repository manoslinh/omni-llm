"""
Tests for execution scheduler.
"""

import asyncio
import pytest

from src.omni.task.models import Task, TaskGraph, TaskStatus
from src.omni.execution.config import ExecutionConfig
from src.omni.execution.scheduler import Scheduler
from src.omni.execution.models import TaskExecutionError, TaskFatalError


@pytest.mark.asyncio
async def test_scheduler_linear_chain() -> None:
    """Test scheduler with linear chain of tasks."""
    # Create a linear chain: A -> B -> C
    graph = TaskGraph(name="linear_chain")
    
    task_a = Task(description="Task A", task_id="A")
    task_b = Task(description="Task B", task_id="B", dependencies=["A"])
    task_c = Task(description="Task C", task_id="C", dependencies=["B"])
    
    graph.add_task(task_a)
    graph.add_task(task_b)
    graph.add_task(task_c)
    
    # Track execution order
    execution_order = []
    completed_tasks = []
    
    async def mock_executor(task: Task) -> dict:
        """Mock executor that records order and succeeds."""
        execution_order.append(task.task_id)
        await asyncio.sleep(0.01)  # Small delay
        return {"outputs": {f"result_{task.task_id}": "success"}}
    
    def on_task_complete(task_id: str, status: TaskStatus, result: dict | None, error: str | None) -> None:
        if status == TaskStatus.COMPLETED:
            completed_tasks.append(task_id)
    
    def on_propagate_skip(failed_task_id: str) -> None:
        pass  # Not needed for this test
    
    config = ExecutionConfig(max_concurrent=1)  # Force sequential execution
    scheduler = Scheduler(
        graph=graph,
        config=config,
        task_executor=mock_executor,
        on_task_complete=on_task_complete,
        on_propagate_skip=on_propagate_skip,
    )
    
    await scheduler.run()
    
    # Should execute in dependency order
    assert execution_order == ["A", "B", "C"]
    assert completed_tasks == ["A", "B", "C"]
    assert all(t.status == TaskStatus.COMPLETED for t in graph.tasks.values())


@pytest.mark.asyncio
async def test_scheduler_parallel_diamond() -> None:
    """Test scheduler with diamond graph for parallelism."""
    # Create diamond: A -> B, A -> C, B -> D, C -> D
    graph = TaskGraph(name="diamond")
    
    task_a = Task(description="Task A", task_id="A")
    task_b = Task(description="Task B", task_id="B", dependencies=["A"])
    task_c = Task(description="Task C", task_id="C", dependencies=["A"])
    task_d = Task(description="Task D", task_id="D", dependencies=["B", "C"])
    
    graph.add_task(task_a)
    graph.add_task(task_b)
    graph.add_task(task_c)
    graph.add_task(task_d)
    
    # Track start times to verify parallelism
    start_times = {}
    
    async def mock_executor(task: Task) -> dict:
        """Mock executor that records start time."""
        start_times[task.task_id] = asyncio.get_event_loop().time()
        await asyncio.sleep(0.1)  # Simulate work
        return {"outputs": {f"result_{task.task_id}": "success"}}
    
    completed_tasks = []
    
    def on_task_complete(task_id: str, status: TaskStatus, result: dict | None, error: str | None) -> None:
        if status == TaskStatus.COMPLETED:
            completed_tasks.append(task_id)
    
    def on_propagate_skip(failed_task_id: str) -> None:
        pass
    
    config = ExecutionConfig(max_concurrent=2)  # Allow parallelism
    scheduler = Scheduler(
        graph=graph,
        config=config,
        task_executor=mock_executor,
        on_task_complete=on_task_complete,
        on_propagate_skip=on_propagate_skip,
    )
    
    await scheduler.run()
    
    # All tasks should complete
    assert set(completed_tasks) == {"A", "B", "C", "D"}
    
    # B and C should run in parallel (after A completes)
    # Their start times should be close to each other
    if "B" in start_times and "C" in start_times:
        time_diff = abs(start_times["B"] - start_times["C"])
        assert time_diff < 0.05  # Should start within 50ms of each other


@pytest.mark.asyncio
async def test_scheduler_skip_propagation() -> None:
    """Test that failed tasks cause downstream skips."""
    # Create chain: A -> B -> C
    graph = TaskGraph(name="skip_chain")
    
    task_a = Task(description="Task A", task_id="A")
    task_b = Task(description="Task B", task_id="B", dependencies=["A"])
    task_c = Task(description="Task C", task_id="C", dependencies=["B"])
    
    graph.add_task(task_a)
    graph.add_task(task_b)
    graph.add_task(task_c)
    
    completed_tasks = []
    failed_tasks = []
    skipped_tasks = []
    
    async def mock_executor(task: Task) -> dict:
        """Mock executor that fails task A."""
        if task.task_id == "A":
            raise TaskFatalError("Task A failed")
        return {"outputs": {f"result_{task.task_id}": "success"}}
    
    def on_task_complete(task_id: str, status: TaskStatus, result: dict | None, error: str | None) -> None:
        if status == TaskStatus.COMPLETED:
            completed_tasks.append(task_id)
        elif status == TaskStatus.FAILED:
            failed_tasks.append(task_id)
        elif status == TaskStatus.SKIPPED:
            skipped_tasks.append(task_id)
    
    skipped_propagations = []
    
    def on_propagate_skip(failed_task_id: str) -> None:
        skipped_propagations.append(failed_task_id)
    
    config = ExecutionConfig(skip_on_dep_failure=True)
    scheduler = Scheduler(
        graph=graph,
        config=config,
        task_executor=mock_executor,
        on_task_complete=on_task_complete,
        on_propagate_skip=on_propagate_skip,
    )
    
    await scheduler.run()
    
    # A should fail, B should be skipped (direct dependent)
    # C won't be skipped in this test because scheduler only skips direct dependents
    # when checking ready tasks. Full propagation would be done by the engine.
    assert failed_tasks == ["A"]
    assert skipped_tasks == ["B"]  # Only direct dependent
    assert completed_tasks == []
    assert skipped_propagations == ["A"]  # Skip propagated from A (failed task)


@pytest.mark.asyncio
async def test_scheduler_retry_logic() -> None:
    """Test scheduler retry with exponential backoff."""
    graph = TaskGraph(name="retry_test")
    task = Task(description="Task with retries", task_id="A", max_retries=2)
    graph.add_task(task)
    
    execution_count = 0
    
    async def mock_executor(task: Task) -> dict:
        """Mock executor that fails twice then succeeds."""
        nonlocal execution_count
        execution_count += 1
        
        if execution_count <= 2:
            raise TaskExecutionError(f"Transient error attempt {execution_count}")
        
        return {"outputs": {"result": "success"}}
    
    completed_tasks = []
    
    def on_task_complete(task_id: str, status: TaskStatus, result: dict | None, error: str | None) -> None:
        if status == TaskStatus.COMPLETED:
            completed_tasks.append(task_id)
    
    def on_propagate_skip(failed_task_id: str) -> None:
        pass
    
    config = ExecutionConfig(retry_enabled=True, backoff_base=0.01)  # Short backoff for test
    scheduler = Scheduler(
        graph=graph,
        config=config,
        task_executor=mock_executor,
        on_task_complete=on_task_complete,
        on_propagate_skip=on_propagate_skip,
    )
    
    await scheduler.run()
    
    # Should have executed 3 times (2 failures + 1 success)
    assert execution_count == 3
    assert completed_tasks == ["A"]
    assert task.status == TaskStatus.COMPLETED
    assert task.retry_count == 2  # Was incremented by scheduler


@pytest.mark.asyncio
async def test_scheduler_cancellation() -> None:
    """Test scheduler cancellation."""
    graph = TaskGraph(name="cancellation_test")
    
    # Create tasks that take time to execute
    tasks = []
    for i in range(5):
        task = Task(description=f"Task {i}", task_id=f"T{i}")
        graph.add_task(task)
        tasks.append(task)
    
    execution_count = 0
    
    async def mock_executor(task: Task) -> dict:
        """Mock executor that counts executions and takes time."""
        nonlocal execution_count
        execution_count += 1
        await asyncio.sleep(0.2)  # Simulate work
        return {"outputs": {"result": "success"}}
    
    completed_tasks = []
    
    def on_task_complete(task_id: str, status: TaskStatus, result: dict | None, error: str | None) -> None:
        if status == TaskStatus.COMPLETED:
            completed_tasks.append(task_id)
        elif status == TaskStatus.CANCELLED:
            completed_tasks.append(f"cancelled_{task_id}")
    
    def on_propagate_skip(failed_task_id: str) -> None:
        pass
    
    config = ExecutionConfig(max_concurrent=2)
    scheduler = Scheduler(
        graph=graph,
        config=config,
        task_executor=mock_executor,
        on_task_complete=on_task_complete,
        on_propagate_skip=on_propagate_skip,
    )
    
    # Start execution and cancel after a short delay
    scheduler_task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(0.1)  # Let some tasks start
    await scheduler.cancel()
    
    # Wait for cancellation to complete
    await scheduler_task
    
    # Some tasks may have completed, some cancelled
    assert execution_count <= 5
    assert len(completed_tasks) <= 5
    
    # Check that no tasks are still running
    stats = scheduler.get_progress_stats()
    assert stats["running"] == 0


@pytest.mark.asyncio
async def test_scheduler_progress_stats() -> None:
    """Test scheduler progress statistics during execution."""
    graph = TaskGraph(name="stats_test")
    
    # Create a simple task
    task = Task(description="Test task", task_id="T1")
    graph.add_task(task)
    
    execution_count = 0
    
    async def mock_executor(t: Task) -> dict:
        nonlocal execution_count
        execution_count += 1
        await asyncio.sleep(0.01)
        return {"outputs": {"result": "success"}}
    
    completed_count = 0
    
    def on_task_complete(task_id: str, status: TaskStatus, result: dict | None, error: str | None) -> None:
        nonlocal completed_count
        if status == TaskStatus.COMPLETED:
            completed_count += 1
    
    def on_propagate_skip(failed_task_id: str) -> None:
        pass
    
    scheduler = Scheduler(
        graph=graph,
        config=ExecutionConfig(),
        task_executor=mock_executor,
        on_task_complete=on_task_complete,
        on_propagate_skip=on_propagate_skip,
    )
    
    # Start execution in background
    scheduler_task = asyncio.create_task(scheduler.run())
    
    # Give it a moment to start
    await asyncio.sleep(0.02)
    
    # Check stats while running
    stats = scheduler.get_progress_stats()
    
    # Should have 1 task total
    assert stats["total"] == 1
    
    # Task might be running or completed by now
    # Sum of all states should equal total
    total_counted = (
        stats["completed"] + 
        stats["failed"] + 
        stats["skipped"] + 
        stats["cancelled"] + 
        stats["running"] + 
        stats["pending"]
    )
    assert total_counted == 1
    
    # Wait for completion
    await scheduler_task
    
    # Check final stats
    stats = scheduler.get_progress_stats()
    assert stats["completed"] == 1
    assert stats["running"] == 0
    assert stats["pending"] == 0
    assert completed_count == 1
    assert execution_count == 1