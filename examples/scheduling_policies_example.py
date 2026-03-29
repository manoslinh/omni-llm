#!/usr/bin/env python3
"""
Example demonstrating scheduling policies.

This example shows how to use different scheduling policies with the scheduler.
"""

import asyncio
import sys
import time

# Add project root to path
sys.path.insert(0, '.')

from src.omni.execution.config import ExecutionConfig
from src.omni.execution.scheduler import Scheduler
from src.omni.scheduling.policies import (
    get_policy,
)
from src.omni.task.models import Task, TaskGraph, TaskStatus


async def run_example_with_policy(policy_name: str, policy_kwargs: dict = None) -> None:
    """Run example with specified scheduling policy."""
    if policy_kwargs is None:
        policy_kwargs = {}

    print(f"\n{'='*60}")
    print(f"Running with {policy_name} policy")
    print(f"{'='*60}")

    # Create a task graph with various characteristics
    graph = TaskGraph(name=f"example_{policy_name}")

    now = time.time()

    # Create tasks with different properties
    tasks = [
        Task(
            description="High priority, near deadline",
            task_id="task1",
            priority=10,
            context={"deadline": now + 30},  # 30 seconds
        ),
        Task(
            description="Medium priority, far deadline",
            task_id="task2",
            priority=5,
            context={"deadline": now + 300},  # 5 minutes
        ),
        Task(
            description="Low priority, no deadline",
            task_id="task3",
            priority=1,
        ),
        Task(
            description="Medium priority, very near deadline",
            task_id="task4",
            priority=5,
            context={"deadline": now + 10},  # 10 seconds
        ),
    ]

    for task in tasks:
        graph.add_task(task)

    # Track execution
    execution_order = []
    start_times = {}

    async def mock_executor(task: Task) -> dict:
        """Mock executor that simulates work."""
        start_times[task.task_id] = time.time()
        execution_order.append(task.task_id)

        # Simulate different execution times
        if task.task_id == "task1":
            await asyncio.sleep(0.2)
        elif task.task_id == "task2":
            await asyncio.sleep(0.1)
        elif task.task_id == "task3":
            await asyncio.sleep(0.15)
        else:  # task4
            await asyncio.sleep(0.05)

        return {
            "outputs": {"result": "success"},
            "duration": time.time() - start_times[task.task_id],
        }

    def on_task_complete(task_id: str, status: TaskStatus, result: dict | None, error: str | None) -> None:
        if status == TaskStatus.COMPLETED:
            duration = result.get("duration", 0) if result else 0
            print(f"  ✓ Completed {task_id} in {duration:.2f}s")
        elif status == TaskStatus.FAILED:
            print(f"  ✗ Failed {task_id}: {error}")

    def on_propagate_skip(failed_task_id: str) -> None:
        print(f"  ⚠ Skipping dependents of {failed_task_id}")

    # Create policy
    policy = get_policy(policy_name, **policy_kwargs)

    # Configure scheduler
    config = ExecutionConfig(max_concurrent=2)  # Allow 2 tasks in parallel

    scheduler = Scheduler(
        graph=graph,
        config=config,
        task_executor=mock_executor,
        on_task_complete=on_task_complete,
        on_propagate_skip=on_propagate_skip,
        policy=policy,
    )

    print("Tasks to schedule:")
    for task in tasks:
        deadline = task.context.get('deadline') if hasattr(task, 'context') and task.context else None
        deadline_str = f", deadline: {deadline - now:.0f}s" if deadline else ""
        print(f"  - {task.task_id}: priority={task.priority}{deadline_str}")

    print(f"\nStarting execution (max {config.max_concurrent} concurrent)...")
    start_time = time.time()

    await scheduler.run()

    total_time = time.time() - start_time
    print(f"\nExecution completed in {total_time:.2f}s")
    print(f"Execution order: {execution_order}")

    # Show scheduling decisions if available
    if hasattr(scheduler, 'scheduling_decisions') and scheduler.scheduling_decisions:
        print("\nScheduling decisions:")
        for decision in scheduler.scheduling_decisions:
            print(f"  - {decision.task_id}: score={decision.composite_score:.2f}")


async def main() -> None:
    """Run examples with different scheduling policies."""
    print("Scheduling Policies Example")
    print("="*60)
    print("\nThis example demonstrates different scheduling policies:")
    print("1. FIFO: First In, First Out (default)")
    print("2. Priority: Highest priority first")
    print("3. Deadline: Earliest deadline first")
    print("4. Balanced: Weighted combination of factors")

    # Run with different policies
    await run_example_with_policy("fifo")

    await run_example_with_policy("priority")

    await run_example_with_policy("deadline")

    # Balanced policy with custom weights
    await run_example_with_policy("balanced", {
        "priority_weight": 0.4,
        "deadline_weight": 0.4,
        "cost_weight": 0.1,
        "fairness_weight": 0.05,
        "agent_weight": 0.05,
    })

    print(f"\n{'='*60}")
    print("Summary:")
    print("- FIFO executes tasks in the order they were ready")
    print("- Priority executes highest priority tasks first")
    print("- Deadline executes tasks with nearest deadlines first")
    print("- Balanced considers multiple factors (priority, deadline, etc.)")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
