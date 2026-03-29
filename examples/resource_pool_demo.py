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

from src.omni.scheduling.resource_pool import ResourcePool

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def demo_basic_allocation():
    """Demonstrate basic resource allocation."""
    print("\n=== Demo 1: Basic Resource Allocation ===")

    # Create a resource pool with 10 concurrent slots
    pool = ResourcePool(resource_manager=None, max_total_concurrent=10)

    print(f"Initial pool: {pool.utilization}")

    # Workflow A requests 4 slots (high priority)
    success_a = await pool.allocate(
        workflow_id="workflow-a",
        resources={"concurrent": 4},
        priority=9
    )
    print(f"Workflow A (priority=9) allocated 4 slots: {success_a}")
    print(f"Pool after A: {pool.utilization}")

    # Workflow B requests 5 slots (medium priority)
    success_b = await pool.allocate(
        workflow_id="workflow-b",
        resources={"concurrent": 5},
        priority=5
    )
    print(f"Workflow B (priority=5) allocated 5 slots: {success_b}")
    print(f"Pool after B: {pool.utilization}")

    # Workflow C requests 3 slots (low priority) - should fail
    success_c = await pool.allocate(
        workflow_id="workflow-c",
        resources={"concurrent": 3},
        priority=1
    )
    print(f"Workflow C (priority=1) allocated 3 slots: {success_c}")
    print(f"Pool after C: {pool.utilization}")

    # Workflow A completes, releases resources
    await pool.deallocate(
        workflow_id="workflow-a",
        resources={"concurrent": 4}
    )
    print("Workflow A released 4 slots")
    print(f"Pool after A release: {pool.utilization}")

    # Now Workflow C can get resources
    success_c = await pool.allocate(
        workflow_id="workflow-c",
        resources={"concurrent": 3},
        priority=1
    )
    print(f"Workflow C (priority=1) allocated 3 slots: {success_c}")
    print(f"Final pool: {pool.utilization}")


async def demo_priority_preemption():
    """Demonstrate priority-based preemption."""
    print("\n=== Demo 2: Priority-Based Preemption ===")

    pool = ResourcePool(resource_manager=None, max_total_concurrent=8)

    # Fill pool with low priority workflows
    await pool.allocate(workflow_id="wf-low-1", resources={"concurrent": 4}, priority=2)
    await pool.allocate(workflow_id="wf-low-2", resources={"concurrent": 4}, priority=1)

    print(f"Pool filled with low-priority workflows: {pool.utilization}")
    print(f"Available capacity: {pool.available_concurrent}")

    # High priority workflow needs resources
    print("\nHigh priority workflow needs 2 slots...")

    # Check if we can allocate
    can_allocate = await pool.can_allocate(concurrent=2)
    print(f"Can allocate 2 slots directly: {can_allocate}")

    # Try to steal slots from lower priority workflows
    print("\nAttempting priority-based preemption...")
    success, message = await pool.steal_slot(
        from_workflow_id="wf-low-1",
        to_workflow_id="wf-high"
    )
    print(f"Preemption result: {message}")

    # In a real implementation, this would actually transfer capacity
    # For now, we just show the interface


async def demo_resource_usage_tracking():
    """Demonstrate resource usage tracking for rate limiting."""
    print("\n=== Demo 3: Resource Usage Tracking ===")

    # Create pool with rate limits
    pool = ResourcePool(
        resource_manager=None,
        max_total_concurrent=10,
        max_total_tokens_per_minute=10000,
        max_total_cost_per_hour=5.0
    )

    print(f"Pool with rate limits: {pool.utilization}")

    # Allocate for a workflow
    await pool.allocate(
        workflow_id="wf-data-intensive",
        resources={"concurrent": 3},
        priority=5
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
        await pool.record_usage(tokens=task["tokens"], cost=task["cost"])
        print(f"Task {i}: Used {task['tokens']} tokens, ${task['cost']:.2f}")

        # Check available capacity
        capacity = pool.get_available_capacity()
        print(f"  Available: {capacity['concurrent']} slots, "
              f"{capacity['tokens_per_minute']} tokens/min, "
              f"${capacity['cost_per_hour']:.2f}/hour")

    print(f"\nFinal usage: {pool.tokens_used_this_minute} tokens this minute, "
          f"${pool.cost_used_this_hour:.2f} this hour")


async def demo_agent_capacity_management():
    """Demonstrate agent-specific capacity limits."""
    print("\n=== Demo 4: Agent Capacity Management ===")

    pool = ResourcePool(resource_manager=None, max_total_concurrent=12)

    # Set agent capacities
    await pool.set_agent_capacity("coder", 4)
    await pool.set_agent_capacity("reviewer", 3)
    await pool.set_agent_capacity("tester", 2)

    print("Agent capacities set:")
    agents = ["coder", "reviewer", "tester", "deployer"]
    for agent in agents:
        capacity = await pool.get_agent_capacity(agent)
        if capacity is not None:
            print(f"  {agent}: {capacity} concurrent tasks")
        else:
            print(f"  {agent}: No limit set")

    # Allocate workflows
    print("\nAllocating workflows...")

    # Workflow 1: Coding tasks
    success1 = await pool.allocate(
        workflow_id="wf-coding",
        resources={"concurrent": 3},
        priority=5
    )
    print(f"Workflow 'wf-coding' (coder agent) allocated 3 slots: {success1}")

    # Workflow 2: Review tasks
    success2 = await pool.allocate(
        workflow_id="wf-review",
        resources={"concurrent": 2},
        priority=5
    )
    print(f"Workflow 'wf-review' (reviewer agent) allocated 2 slots: {success2}")

    # Workflow 3: Mixed tasks
    success3 = await pool.allocate(
        workflow_id="wf-mixed",
        resources={"concurrent": 4},
        priority=5
    )
    print(f"Workflow 'wf-mixed' (multiple agents) allocated 4 slots: {success3}")

    print(f"\nFinal pool utilization: {pool.utilization}")


async def demo_concurrent_workflows():
    """Demonstrate handling multiple concurrent workflows."""
    print("\n=== Demo 5: Concurrent Workflow Management ===")

    pool = ResourcePool(resource_manager=None, max_total_concurrent=15)

    # Simulate multiple workflows starting concurrently
    async def start_workflow(wf_id: str, slots: int, priority: int):
        """Simulate a workflow starting."""
        can_allocate = await pool.can_allocate(concurrent=slots)
        if can_allocate:
            success = await pool.allocate(
                workflow_id=wf_id,
                resources={"concurrent": slots},
                priority=priority
            )
            return success, f"Workflow {wf_id} started with {slots} slots"
        else:
            return False, f"Workflow {wf_id} failed: insufficient capacity"

    # Define workflows
    workflows = [
        ("wf-urgent", 6, 9),    # Urgent, needs 6 slots
        ("wf-important", 5, 7), # Important, needs 5 slots
        ("wf-background", 4, 3), # Background, needs 4 slots
        ("wf-low", 3, 1),       # Low priority, needs 3 slots
    ]

    print("Starting workflows concurrently...")

    # Start workflows
    tasks = [start_workflow(wf_id, slots, pri) for wf_id, slots, pri in workflows]
    results = await asyncio.gather(*tasks)

    # Show results
    for (_wf_id, _slots, pri), (success, message) in zip(workflows, results, strict=True):
        status = "✓" if success else "✗"
        print(f"{status} {message} (priority={pri})")

    print(f"\nFinal pool state: {pool.utilization}")

    # Show which workflows got resources
    print("\nWorkflow allocation summary:")
    for wf_id, slots, pri in workflows:
        # Note: This is simplified - real implementation would track per-workflow allocation
        print(f"  {wf_id}: Requested {slots} slots at priority {pri}")


async def main():
    """Run all demos."""
    print("=" * 60)
    print("P2-16 Global Resource Manager - ResourcePool Demo")
    print("=" * 60)

    await demo_basic_allocation()
    await demo_priority_preemption()
    await demo_resource_usage_tracking()
    await demo_agent_capacity_management()
    await demo_concurrent_workflows()

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
