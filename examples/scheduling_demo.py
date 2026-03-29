#!/usr/bin/env python3
"""
Demonstration of P2-16 Advanced Scheduling & Resource Management.

This example shows how to use:
1. Pluggable scheduling policies
2. Global resource management
3. Predictive scheduling components
4. Real-time schedule adjustments
"""

import asyncio
import logging
from unittest.mock import Mock

from omni.execution.adjuster import ScheduleAdjuster
from omni.scheduling.predictive import (
    BottleneckDetector,
    DemandForecaster,
    WorkloadTracker,
)
from omni.scheduling.resource_pool import GlobalResourceManager, ResourcePool
from omni.scheduling.policies import (
    BalancedPolicy,
    DeadlinePolicy,
    FIFOPolicy,
    PriorityPolicy,
)
from omni.task.models import Task


def demo_scheduling_policies():
    """Demonstrate different scheduling policies."""
    print("=== Scheduling Policies Demo ===")

    # Create mock tasks
    tasks = [
        Mock(spec=Task, task_id="task1", priority=25),   # LOW priority (0-100 scale)
        Mock(spec=Task, task_id="task2", priority=75),   # HIGH priority
        Mock(spec=Task, task_id="task3", priority=100),  # CRITICAL priority
    ]

    # Test different policies
    policies = [
        ("FIFO", FIFOPolicy()),
        ("Priority", PriorityPolicy()),
        ("Deadline", DeadlinePolicy()),
        ("Balanced", BalancedPolicy()),
    ]

    for name, policy in policies:
        print(f"\n{name} Policy:")
        # Create a simple context
        context = Mock()
        context.ready_tasks = tasks
        context.running_tasks = {}
        context.workflow_id = "demo"
        context.resource_snapshot = {}
        context.agent_availability = {}
        context.deadline_info = {}
        context.cost_budget_remaining = None
        context.execution_history = []

        scores = policy.rank_tasks(context)
        for score in scores:
            print(f"  Task {score.task_id}: score={score.composite_score:.1f}")


async def demo_global_resource_manager():
    """Demonstrate global resource management."""
    print("\n=== Global Resource Manager Demo ===")

    # Create resource pool with 10 concurrent slots
    pool = ResourcePool(max_total_concurrent=10)
    manager = GlobalResourceManager(pool)

    # Create workflow budgets
    print("Creating workflow budgets...")
    budget1 = await manager.create_workflow_budget(
        execution_id="workflow1",
        requested_concurrent=5,
        priority=5,
    )
    print(f"  Workflow1: allocated {budget1.max_concurrent} slots")

    budget2 = await manager.create_workflow_budget(
        execution_id="workflow2",
        requested_concurrent=8,
        priority=8,  # Higher priority
    )
    print(f"  Workflow2: allocated {budget2.max_concurrent} slots (higher priority)")

    # Check pool status
    status = manager.get_status()
    print(f"\nPool status: {status['pool']['allocated']}/{status['pool']['total_concurrent']} slots allocated")
    print(f"Utilization: {status['pool']['utilization_pct']}%")

    # Release a budget
    await manager.release_workflow_budget("workflow1")
    print("\nReleased workflow1 budget")
    print(f"Pool status: {manager.pool.allocated_concurrent}/{manager.pool.max_total_concurrent} slots allocated")


def demo_predictive_scheduling():
    """Demonstrate predictive scheduling components."""
    print("\n=== Predictive Scheduling Demo ===")

    # Create workload tracker
    tracker = WorkloadTracker()

    # Record some execution history
    print("Recording execution history...")
    from omni.scheduling.predictive import ExecutionRecord

    for i in range(5):
        record = ExecutionRecord(
            task_id=f"task{i}",
            agent_id="coder",
            task_type="coding",
            complexity=5.0,
            duration_seconds=10.0 + i * 2,
            tokens_used=2000,
            cost=0.002 + i * 0.001,
            success=True,
        )
        tracker.record(record)

    # Create demand forecaster
    forecaster = DemandForecaster(tracker)

    # Forecast demand for pending tasks
    pending_tasks = [
        {"agent_id": "coder", "task_type": "coding", "complexity": 5.0},
        {"agent_id": "coder", "task_type": "coding", "complexity": 5.0},
        {"agent_id": "intern", "task_type": "formatting", "complexity": 2.0},
    ]

    forecast = forecaster.forecast(pending_tasks, time_horizon_seconds=300)
    print(f"\nForecast for {forecast.estimated_tasks} tasks:")
    print(f"  Peak concurrency: {forecast.estimated_concurrent_peak}")
    print(f"  Estimated duration: {forecast.estimated_duration_seconds}s")
    print(f"  Estimated cost: ${forecast.estimated_total_cost:.4f}")
    print(f"  Bottleneck agents: {forecast.bottleneck_agents}")

    # Create bottleneck detector
    detector = BottleneckDetector(tracker)

    # Sample queue depths
    for depth in [3, 5, 8, 12, 15]:
        detector.sample_queue_depth(depth)

    # Detect bottlenecks
    report = detector.detect()
    print("\nBottleneck detection:")
    print(f"  Has bottleneck: {report['has_bottleneck']}")
    if report['bottlenecks']:
        for bottleneck in report['bottlenecks']:
            print(f"  - {bottleneck['type']}: {bottleneck['detail']}")


async def demo_schedule_adjuster():
    """Demonstrate real-time schedule adjustments."""
    print("\n=== Schedule Adjuster Demo ===")

    adjuster = ScheduleAdjuster()

    # Create a mock task
    task = Mock(spec=Task, task_id="test_task", priority=50)  # MEDIUM priority (0-100 scale)

    # Handle task failure
    print("Handling task failure...")
    result = await adjuster.handle_task_failure(
        task=task,
        current_agent="coder",
        error="Rate limit exceeded",
    )
    print(f"  Adjustment: {result.adjustment.adjustment_type.value}")
    print(f"  Reason: {result.adjustment.reason}")

    # Escalate for deadline
    print("\nEscalating for deadline...")
    result = await adjuster.escalate_for_deadline(
        task=task,
        seconds_remaining=30,  # Critical deadline
    )
    print(f"  Adjustment: {result.adjustment.adjustment_type.value}")
    print(f"  Urgency: {result.adjustment.details['urgency']}")

    # Burst capacity
    print("\nBursting capacity...")
    result = await adjuster.burst_capacity(
        workflow_id="workflow1",
        additional_concurrent=3,
        duration_seconds=60.0,
        reason="Falling behind schedule",
    )
    print(f"  Adjustment: {result.adjustment.adjustment_type.value}")
    print(f"  Message: {result.message}")

    # Show adjustment history
    print(f"\nTotal adjustments made: {len(adjuster.get_adjustment_history())}")
    summary = adjuster.get_adjustment_summary()
    print(f"Adjustment summary: {summary['by_type']}")


async def main():
    """Run all demos."""
    logging.basicConfig(level=logging.INFO)

    print("P2-16: Advanced Scheduling & Resource Management Demo")
    print("=" * 60)

    # Demo 1: Scheduling policies
    demo_scheduling_policies()

    # Demo 2: Global resource manager
    await demo_global_resource_manager()

    # Demo 3: Predictive scheduling
    demo_predictive_scheduling()

    # Demo 4: Schedule adjuster
    await demo_schedule_adjuster()

    print("\n" + "=" * 60)
    print("Demo complete!")


if __name__ == "__main__":
    asyncio.run(main())
