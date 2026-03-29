"""
Integration tests for scheduling policies with scheduler.
"""

import asyncio

import pytest

from src.omni.execution.config import ExecutionConfig
from src.omni.execution.scheduler import Scheduler
from src.omni.scheduling.policies import (
    PriorityPolicy,
    get_policy,
)
from src.omni.task.models import Task, TaskGraph, TaskStatus


def create_test_graph_with_priorities() -> TaskGraph:
    """Create a test graph with tasks of different priorities."""
    graph = TaskGraph(name="priority_test")

    # Independent tasks with different priorities
    tasks = [
        Task(description="Low priority task", task_id="low", priority=1),
        Task(description="Medium priority task", task_id="medium", priority=5),
        Task(description="High priority task", task_id="high", priority=10),
    ]

    for task in tasks:
        graph.add_task(task)

    return graph


def create_test_graph_with_deadlines() -> TaskGraph:
    """Create a test graph with tasks with deadlines in context."""
    graph = TaskGraph(name="deadline_test")

    # Independent tasks with deadlines in context
    import time
    now = time.time()
    tasks = [
        Task(
            description="Task with far deadline",
            task_id="far",
            priority=5,
            context={"deadline": now + 300},  # 5 minutes
        ),
        Task(
            description="Task with near deadline",
            task_id="near",
            priority=5,
            context={"deadline": now + 60},  # 1 minute
        ),
        Task(
            description="Task with no deadline",
            task_id="none",
            priority=5,
        ),
    ]

    for task in tasks:
        graph.add_task(task)

    return graph


async def run_scheduler_with_policy(graph: TaskGraph, policy_name: str = "fifo", **policy_kwargs) -> list[str]:
    """Run scheduler with specified policy and return execution order."""
    execution_order = []
    completed_tasks = []

    async def mock_executor(task: Task) -> dict:
        """Mock executor that records order."""
        execution_order.append(task.task_id)
        await asyncio.sleep(0.01)  # Small delay
        return {"outputs": {f"result_{task.task_id}": "success"}}

    def on_task_complete(task_id: str, status: TaskStatus, result: dict | None, error: str | None) -> None:
        if status == TaskStatus.COMPLETED:
            completed_tasks.append(task_id)

    def on_propagate_skip(failed_task_id: str) -> None:
        pass  # Not needed

    config = ExecutionConfig(max_concurrent=3)  # Allow all to run in parallel
    policy = get_policy(policy_name, **policy_kwargs)

    scheduler = Scheduler(
        graph=graph,
        config=config,
        task_executor=mock_executor,
        on_task_complete=on_task_complete,
        on_propagate_skip=on_propagate_skip,
        policy=policy,
    )

    await scheduler.run()
    return execution_order


@pytest.mark.asyncio
async def test_fifo_policy_integration() -> None:
    """Test FIFO policy integration with scheduler."""
    graph = create_test_graph_with_priorities()
    execution_order = await run_scheduler_with_policy(graph, "fifo")

    # FIFO should execute in the order tasks were added to graph
    # Since we add low, medium, high in that order
    assert execution_order == ["low", "medium", "high"]


@pytest.mark.asyncio
async def test_priority_policy_integration() -> None:
    """Test priority policy integration with scheduler."""
    graph = create_test_graph_with_priorities()
    execution_order = await run_scheduler_with_policy(graph, "priority")

    # Priority policy should execute highest priority first
    assert execution_order == ["high", "medium", "low"]


@pytest.mark.asyncio
async def test_deadline_policy_integration() -> None:
    """Test deadline policy integration with scheduler."""
    graph = create_test_graph_with_deadlines()
    execution_order = await run_scheduler_with_policy(graph, "deadline")

    # Deadline policy should execute nearest deadline first
    # near (60s), far (300s), none (no deadline = lowest priority)
    assert execution_order == ["near", "far", "none"]


@pytest.mark.asyncio
async def test_balanced_policy_integration() -> None:
    """Test balanced policy integration with scheduler."""
    graph = create_test_graph_with_priorities()

    # Use balanced policy with high priority weight
    execution_order = await run_scheduler_with_policy(
        graph,
        "balanced",
        priority_weight=0.8,
        deadline_weight=0.1,
        cost_weight=0.05,
        fairness_weight=0.025,
        agent_weight=0.025,
    )

    # With high priority weight, should execute high priority first
    assert execution_order == ["high", "medium", "low"]


@pytest.mark.asyncio
async def test_scheduler_backward_compatibility() -> None:
    """Test scheduler backward compatibility (defaults to FIFO)."""
    graph = create_test_graph_with_priorities()

    execution_order = []
    completed_tasks = []

    async def mock_executor(task: Task) -> dict:
        execution_order.append(task.task_id)
        await asyncio.sleep(0.01)
        return {"outputs": {f"result_{task.task_id}": "success"}}

    def on_task_complete(task_id: str, status: TaskStatus, result: dict | None, error: str | None) -> None:
        if status == TaskStatus.COMPLETED:
            completed_tasks.append(task_id)

    def on_propagate_skip(failed_task_id: str) -> None:
        pass

    config = ExecutionConfig(max_concurrent=3)

    # Create scheduler without specifying policy (should default to FIFO)
    scheduler = Scheduler(
        graph=graph,
        config=config,
        task_executor=mock_executor,
        on_task_complete=on_task_complete,
        on_propagate_skip=on_propagate_skip,
        # policy parameter omitted
    )

    await scheduler.run()

    # Should use FIFO as default
    assert execution_order == ["low", "medium", "high"]


@pytest.mark.asyncio
async def test_scheduler_with_custom_policy_instance() -> None:
    """Test scheduler with custom policy instance."""
    graph = create_test_graph_with_priorities()

    execution_order = []
    completed_tasks = []

    async def mock_executor(task: Task) -> dict:
        execution_order.append(task.task_id)
        await asyncio.sleep(0.01)
        return {"outputs": {f"result_{task.task_id}": "success"}}

    def on_task_complete(task_id: str, status: TaskStatus, result: dict | None, error: str | None) -> None:
        if status == TaskStatus.COMPLETED:
            completed_tasks.append(task_id)

    def on_propagate_skip(failed_task_id: str) -> None:
        pass

    config = ExecutionConfig(max_concurrent=3)

    # Create custom priority policy instance
    custom_policy = PriorityPolicy()

    scheduler = Scheduler(
        graph=graph,
        config=config,
        task_executor=mock_executor,
        on_task_complete=on_task_complete,
        on_propagate_skip=on_propagate_skip,
        policy=custom_policy,
    )

    await scheduler.run()

    # Should use priority policy
    assert execution_order == ["high", "medium", "low"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
