#!/usr/bin/env python3
"""
Example demonstrating the ResourcePool component for P2-16.

This shows how the Global Resource Manager enables:
1. Cross-workflow capacity tracking
2. Priority-based allocation
3. Resource contention resolution
4. Integration with P2-15 ResourceManager
"""

import asyncio
import logging
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from omni.scheduling.resource_pool import ResourcePool

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def demo_basic_allocation():
    """Demonstrate basic resource allocation."""
    print("\n=== Demo 1: Basic Resource Allocation ===")

    # Create a resource pool with 10 concurrent slots
    pool = ResourcePool(max_total_concurrent=10)

    print(f"Initial pool: {pool.utilization}")

    # Workflow A requests 4 slots
    success_a = pool.allocate(
        execution_id="workflow-a",
        concurrent=4
    )
    print(f"Workflow A allocated 4 slots: {success_a}")
    print(f"Pool after A: {pool.utilization}")

    # Workflow B requests 5 slots
    success_b = pool.allocate(
        execution_id="workflow-b",
        concurrent=5
    )
    print(f"Workflow B allocated 5 slots: {success_b}")
    print(f"Pool after B: {pool.utilization}")

    # Workflow C requests 3 slots - should fail
    success_c = pool.allocate(
        execution_id="workflow-c",
        concurrent=3
    )
    print(f"Workflow C allocated 3 slots: {success_c}")
    print(f"Pool after C: {pool.utilization}")

    # Workflow A completes, releases resources
    pool.release(
        execution_id="workflow-a",
        concurrent=4
    )
    print("Workflow A released 4 slots")
    print(f"Pool after A release: {pool.utilization}")

    # Now Workflow C can get resources
    success_c = pool.allocate(
        execution_id="workflow-c",
        concurrent=3
    )
    print(f"Workflow C allocated 3 slots: {success_c}")
    print(f"Final pool: {pool.utilization}")


def demo_priority_preemption():
    """Demonstrate priority-based preemption."""
    print("\n=== Demo 2: Priority-Based Preemption ===")

    pool = ResourcePool(max_total_concurrent=8)

    # Fill pool with workflows
    pool.allocate(execution_id="wf-1", concurrent=4)
    pool.allocate(execution_id="wf-2", concurrent=4)

    print(f"Pool filled with workflows: {pool.utilization}")
    print(f"Available capacity: {pool.available_concurrent}")

    # New workflow needs resources
    print("\nNew workflow needs 2 slots...")

    # Check if we can allocate
    can_allocate = pool.can_allocate(requested_concurrent=2)
    print(f"Can allocate 2 slots directly: {can_allocate}")

    # Note: Priority-based preemption is handled by GlobalResourceManager
    # ResourcePool itself doesn't have preemption logic
    print("\nNote: Priority-based preemption is handled by GlobalResourceManager")
    print("ResourcePool provides basic capacity tracking only")


def demo_resource_usage_tracking():
    """Demonstrate resource usage tracking for rate limiting."""
    print("\n=== Demo 3: Resource Usage Tracking ===")

    # Create pool with rate limits
    pool = ResourcePool(
        max_total_concurrent=10,
        max_total_tokens_per_minute=10000,
        max_total_cost_per_hour=5.0
    )

    print(f"Pool with rate limits: {pool.utilization}")

    # Allocate for a workflow
    pool.allocate(
        execution_id="wf-data-intensive",
        concurrent=3
    )

    # Simulate task execution
    print("\nSimulating task execution...")

    tasks = [
        {"tokens": 1500, "cost": 0.15},
        {"tokens": 2200, "cost": 0.22},
        {"tokens": 800, "cost": 0.08},
        {"tokens": 3000, "cost": 0.30},
    ]

    for i, task in enumerate(tasks, 1):
        pool.record_usage(tokens=task["tokens"], cost=task["cost"])
        print(f"Task {i}: Used {task['tokens']} tokens, ${task['cost']:.2f}")

        # Check available capacity
        print(f"  Available: {pool.available_concurrent} slots, "
              f"{pool.tokens_used_this_minute} tokens used this minute, "
              f"${pool.cost_used_this_hour:.2f} used this hour")

    print(f"\nFinal usage: {pool.tokens_used_this_minute} tokens this minute, "
          f"${pool.cost_used_this_hour:.2f} this hour")


def demo_agent_capacity_management():
    """Demonstrate agent-specific capacity limits."""
    print("\n=== Demo 4: Agent Capacity Management ===")

    pool = ResourcePool(max_total_concurrent=12)

    # Set agent capacities via direct dict access
    pool.agent_max_concurrent["coder"] = 4
    pool.agent_max_concurrent["reviewer"] = 3
    pool.agent_max_concurrent["tester"] = 2

    print("Agent capacities set:")
    agents = ["coder", "reviewer", "tester", "deployer"]
    for agent in agents:
        capacity = pool.agent_max_concurrent.get(agent)
        if capacity is not None:
            print(f"  {agent}: {capacity} concurrent tasks")
        else:
            print(f"  {agent}: No limit set")

    # Allocate workflows
    print("\nAllocating workflows...")

    # Workflow 1: Coding tasks
    success1 = pool.allocate(
        execution_id="wf-coding",
        concurrent=3
    )
    print(f"Workflow 'wf-coding' (coder agent) allocated 3 slots: {success1}")

    # Workflow 2: Review tasks
    success2 = pool.allocate(
        execution_id="wf-review",
        concurrent=2
    )
    print(f"Workflow 'wf-review' (reviewer agent) allocated 2 slots: {success2}")

    # Workflow 3: Mixed tasks
    success3 = pool.allocate(
        execution_id="wf-mixed",
        concurrent=4
    )
    print(f"Workflow 'wf-mixed' (multiple agents) allocated 4 slots: {success3}")

    print(f"\nFinal pool utilization: {pool.utilization}")


def demo_concurrent_workflows():
    """Demonstrate handling multiple concurrent workflows."""
    print("\n=== Demo 5: Concurrent Workflow Management ===")

    pool = ResourcePool(max_total_concurrent=15)

    # Simulate multiple workflows starting
    def start_workflow(wf_id: str, slots: int):
        """Simulate a workflow starting."""
        can_allocate = pool.can_allocate(requested_concurrent=slots)
        if can_allocate:
            success = pool.allocate(
                execution_id=wf_id,
                concurrent=slots
            )
            return success, f"Workflow {wf_id} started with {slots} slots"
        else:
            return False, f"Workflow {wf_id} failed: insufficient capacity"

    # Define workflows
    workflows = [
        ("wf-1", 6),    # Needs 6 slots
        ("wf-2", 5),    # Needs 5 slots
        ("wf-3", 4),    # Needs 4 slots
        ("wf-4", 3),    # Needs 3 slots
    ]

    print("Starting workflows...")

    # Start workflows sequentially (for demo simplicity)
    results = []
    for wf_id, slots in workflows:
        success, message = start_workflow(wf_id, slots)
        results.append((success, message))
        status = "✓" if success else "✗"
        print(f"{status} {message}")

    print(f"\nFinal pool state: {pool.utilization}")

    # Show which workflows got resources
    print("\nWorkflow allocation summary:")
    for (wf_id, slots), (success, _) in zip(workflows, results, strict=True):
        status = "allocated" if success else "failed"
        print(f"  {wf_id}: Requested {slots} slots - {status}")


def main():
    """Run all demos."""
    print("=" * 60)
    print("P2-16 Global Resource Manager - ResourcePool Demo")
    print("=" * 60)

    demo_basic_allocation()
    demo_priority_preemption()
    demo_resource_usage_tracking()
    demo_agent_capacity_management()
    demo_concurrent_workflows()

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
