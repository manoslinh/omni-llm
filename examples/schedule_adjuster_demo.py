#!/usr/bin/env python3
"""
Example demonstrating Schedule Adjuster usage.

Shows how to:
1. Handle task failures with automatic reassignment
2. Escalate tasks approaching deadlines
3. Request capacity bursts for workload surges
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from omni.execution.adjuster import ScheduleAdjuster
from omni.task.models import Task, TaskType


class DemoTaskMatcher:
    """Simple demo task matcher for the example."""

    async def match(self, task):
        """Match task to an agent (demo implementation)."""
        # In a real implementation, this would use P2-14 agent matcher
        return {
            "agent_id": "thinker",
            "confidence": 0.85,
            "model": "mimo-v2-pro",
            "reason": "Escalated for deadline pressure",
        }


async def demo_failure_recovery():
    """Demonstrate failure recovery."""
    print("\n=== Failure Recovery Demo ===")

    # Create adjuster with matcher
    matcher = DemoTaskMatcher()
    adjuster = ScheduleAdjuster(matcher=matcher)

    # Create a sample task
    task = Task(
        description="Generate API client for weather service",
        task_type=TaskType.CODE_GENERATION,
        task_id="task-weather-api-001",
        priority=3,
        context={"assigned_agent": "coder"},
    )

    # Simulate different types of failures
    failure_scenarios = [
        ("Rate limit exceeded - retry in 5s", "transient"),
        ("Authentication failed - invalid API key", "permanent"),
        ("Timeout after 30 seconds", "transient"),
        ("Invalid input format - cannot parse", "permanent"),
    ]

    for failure_reason, expected_type in failure_scenarios:
        print(f"\nTask failure: {failure_reason}")
        result = await adjuster.adjust_for_failure(task, failure_reason)

        print(f"  Adjustment: {result.adjustment.adjustment_type.value}")
        print(f"  Reason: {result.adjustment.reason}")
        print(f"  Details: {result.adjustment.details}")

        if expected_type == "transient":
            assert result.adjustment.details["failure_type"] == "transient"
        else:
            assert result.adjustment.details["failure_type"] == "permanent"

    # Show adjustment summary
    summary = adjuster.get_adjustment_summary()
    print(f"\nAdjustment summary: {summary}")


async def demo_deadline_pressure():
    """Demonstrate deadline pressure handling."""
    print("\n=== Deadline Pressure Demo ===")

    # Create adjuster with matcher
    matcher = DemoTaskMatcher()
    adjuster = ScheduleAdjuster(matcher=matcher)

    # Create a sample task
    task = Task(
        description="Process quarterly financial report",
        task_type=TaskType.ANALYSIS,
        task_id="task-finance-q1-2024",
        priority=5,
        context={"assigned_agent": "analyst"},
    )

    # Simulate different deadline scenarios
    deadline_scenarios = [
        (-60.0, "overdue", "1 minute overdue"),
        (30.0, "critical", "30 seconds remaining"),
        (150.0, "high", "2.5 minutes remaining"),
        (600.0, "normal", "10 minutes remaining"),
    ]

    for time_remaining, expected_urgency, description in deadline_scenarios:
        print(f"\nDeadline: {description}")
        result = await adjuster.adjust_for_deadline_pressure(task, time_remaining)

        print(f"  Adjustment: {result.adjustment.adjustment_type.value}")
        print(f"  Urgency: {result.adjustment.details['urgency']}")
        print(f"  Priority boost: {result.adjustment.details['priority_boost']}")

        assert result.adjustment.details["urgency"] == expected_urgency

    # Show adjustment summary
    summary = adjuster.get_adjustment_summary()
    print(f"\nAdjustment summary: {summary}")


async def demo_capacity_bursting():
    """Demonstrate capacity bursting."""
    print("\n=== Capacity Bursting Demo ===")

    # Create adjuster
    adjuster = ScheduleAdjuster()

    # Request capacity bursts for different workflows
    burst_requests = [
        {
            "workflow_id": "workflow-data-import",
            "resources": {"concurrent": 3, "duration_seconds": 300, "reason": "Data import backlog"},
        },
        {
            "workflow_id": "workflow-report-generation",
            "resources": {"concurrent": 2, "duration_seconds": 180, "reason": "End-of-month reporting"},
        },
        {
            "workflow_id": "workflow-api-sync",
            "resources": {"concurrent": 1, "duration_seconds": 60, "reason": "API rate limit reset"},
        },
    ]

    for request in burst_requests:
        print(f"\nRequesting capacity burst for {request['workflow_id']}")
        result = await adjuster.adjust_for_capacity_needs(
            request["workflow_id"],
            request["resources"],
        )

        print(f"  Adjustment: {result.adjustment.adjustment_type.value}")
        print(f"  Additional concurrent: {result.adjustment.details['additional_concurrent']}")
        print(f"  Duration: {result.adjustment.details['duration_seconds']}s")
        print(f"  Reason: {result.adjustment.reason}")

    # Show active bursts
    active_bursts = adjuster.get_active_bursts()
    print(f"\nActive bursts: {len(active_bursts)}")
    for burst_id, info in active_bursts.items():
        print(f"  {burst_id}: +{info['concurrent']} for {info['workflow_id']} "
              f"({info['remaining_seconds']:.0f}s remaining)")

    # Wait a moment and check again
    print("\nWaiting 0.2 seconds...")
    await asyncio.sleep(0.2)

    active_bursts = adjuster.get_active_bursts()
    print(f"Active bursts after wait: {len(active_bursts)}")

    # Show adjustment summary
    summary = adjuster.get_adjustment_summary()
    print(f"\nAdjustment summary: {summary}")


async def demo_integration():
    """Demonstrate integrated adjustment flow."""
    print("\n=== Integrated Adjustment Flow Demo ===")

    # Create adjuster with matcher
    matcher = DemoTaskMatcher()
    adjuster = ScheduleAdjuster(matcher=matcher)

    # Create a critical task
    task = Task(
        description="Emergency security patch deployment",
        task_type=TaskType.DEPLOYMENT,
        task_id="task-security-patch-001",
        priority=10,
        context={"assigned_agent": "security-engineer"},
    )

    print("Simulating emergency scenario:")
    print("1. Task fails due to deployment timeout")
    print("2. Deadline is approaching (45 seconds remaining)")
    print("3. Need capacity burst for parallel deployment")

    # 1. Handle failure
    print("\n1. Handling task failure...")
    failure_result = await adjuster.adjust_for_failure(
        task=task,
        failure_reason="Deployment timeout - infrastructure issue",
    )
    print(f"   Result: {failure_result.adjustment.adjustment_type.value}")

    # 2. Handle deadline pressure
    print("\n2. Handling deadline pressure...")
    deadline_result = await adjuster.adjust_for_deadline_pressure(
        task=task,
        time_remaining=45.0,
    )
    print(f"   Result: {deadline_result.adjustment.adjustment_type.value}")
    print(f"   Urgency: {deadline_result.adjustment.details['urgency']}")

    # 3. Request capacity burst
    print("\n3. Requesting capacity burst...")
    burst_result = await adjuster.adjust_for_capacity_needs(
        workflow_id="workflow-emergency-deploy",
        additional_resources={
            "concurrent": 5,
            "duration_seconds": 600,
            "reason": "Emergency security patch deployment",
        },
    )
    print(f"   Result: {burst_result.adjustment.adjustment_type.value}")
    print(f"   Additional capacity: +{burst_result.adjustment.details['additional_concurrent']}")

    # Show complete history
    print("\n=== Complete Adjustment History ===")
    history = adjuster.get_adjustment_history()
    for i, result in enumerate(history, 1):
        print(f"{i}. {result.adjustment.adjustment_type.value}: {result.adjustment.reason}")

    # Show summary
    summary = adjuster.get_adjustment_summary()
    print("\n=== Final Summary ===")
    print(f"Total adjustments: {summary['total_adjustments']}")
    print(f"By type: {summary['by_type']}")
    print(f"Active bursts: {summary['active_bursts']}")


async def main():
    """Run all demos."""
    print("Schedule Adjuster Demo")
    print("=" * 50)

    # Configure logging
    logging.basicConfig(level=logging.WARNING)  # Reduce noise

    # Run demos
    await demo_failure_recovery()
    await demo_deadline_pressure()
    await demo_capacity_bursting()
    await demo_integration()

    print("\n" + "=" * 50)
    print("All demos completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
