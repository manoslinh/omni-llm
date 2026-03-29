"""
Integration tests for ResourcePool with P2-15 ResourceManager.
"""

import pytest

from src.omni.scheduling.resource_pool import ResourcePool


# Mock P2-15 ResourceManager for integration testing
class MockResourceManager:
    """Mock implementation of P2-15 ResourceManager for testing."""

    def __init__(self, global_max_concurrent: int = 20):
        self.global_max_concurrent = global_max_concurrent
        self._budgets = {}

    def create_budget(self, execution_id: str, max_concurrent: int = 5, **kwargs):
        """Create a resource budget for a workflow execution."""
        budget = {
            "execution_id": execution_id,
            "max_concurrent": max_concurrent,
            "active_tasks": 0,
            "tokens_used": 0,
            "cost_used": 0.0,
            **kwargs
        }
        self._budgets[execution_id] = budget
        return budget

    def get_budget(self, execution_id: str):
        """Get budget for an execution."""
        return self._budgets.get(execution_id)

    def remove_budget(self, execution_id: str):
        """Clean up budget after execution completes."""
        self._budgets.pop(execution_id, None)

    def global_status(self):
        """Global resource status across all workflows."""
        total_active = sum(b.get("active_tasks", 0) for b in self._budgets.values())
        total_tokens = sum(b.get("tokens_used", 0) for b in self._budgets.values())
        total_cost = sum(b.get("cost_used", 0.0) for b in self._budgets.values())

        return {
            "active_workflows": len(self._budgets),
            "total_active_tasks": total_active,
            "global_max_concurrent": self.global_max_concurrent,
            "total_tokens_used": total_tokens,
            "total_cost_used": round(total_cost, 4),
            "per_execution": {
                eid: {
                    "max_concurrent": b.get("max_concurrent", 0),
                    "active_tasks": b.get("active_tasks", 0),
                    "utilization": f"{b.get('active_tasks', 0)}/{b.get('max_concurrent', 1)}"
                }
                for eid, b in self._budgets.items()
            }
        }


class TestResourcePoolIntegration:
    """Integration tests for ResourcePool with P2-15 components."""

    @pytest.fixture
    def mock_resource_manager(self):
        """Create a mock P2-15 ResourceManager."""
        return MockResourceManager(global_max_concurrent=20)

    @pytest.fixture
    def resource_pool(self):
        """Create a ResourcePool."""
        return ResourcePool(resource_manager=None, max_total_concurrent=10)

    @pytest.mark.asyncio
    async def test_integration_workflow(self, mock_resource_manager, resource_pool):
        """
        Test a complete workflow showing ResourcePool integration with P2-15.

        Scenario:
        1. Workflow A starts with high priority
        2. Workflow B starts with medium priority
        3. Workflow C tries to start with low priority (should fail initially)
        4. Workflow A completes, freeing resources
        5. Workflow C can now start
        """

        # Step 1: Workflow A starts (high priority)
        # First check global capacity via ResourcePool
        can_allocate = await resource_pool.can_allocate(concurrent=5)
        assert can_allocate is True

        # Allocate via ResourcePool
        success_a = await resource_pool.allocate(
            workflow_id="workflow-a",
            resources={"concurrent": 5},
            priority=9  # High priority
        )
        assert success_a is True

        # Create P2-15 budget for workflow A
        mock_resource_manager.create_budget(
            execution_id="workflow-a",
            max_concurrent=5,
            max_tokens=10000,
            max_cost=5.0
        )

        # Step 2: Workflow B starts (medium priority)
        # Check capacity (10 total - 5 allocated = 5 available)
        can_allocate = await resource_pool.can_allocate(concurrent=3)
        assert can_allocate is True

        success_b = await resource_pool.allocate(
            workflow_id="workflow-b",
            resources={"concurrent": 3},
            priority=5  # Medium priority
        )
        assert success_b is True

        mock_resource_manager.create_budget(
            execution_id="workflow-b",
            max_concurrent=3,
            max_tokens=5000,
            max_cost=2.5
        )

        # Verify ResourcePool state
        assert resource_pool.allocated_concurrent == 8
        assert resource_pool.available_concurrent == 2

        # Step 3: Workflow C tries to start (low priority, needs 3 slots)
        # Only 2 available, so should fail
        can_allocate = await resource_pool.can_allocate(concurrent=3)
        assert can_allocate is False

        success_c = await resource_pool.allocate(
            workflow_id="workflow-c",
            resources={"concurrent": 3},
            priority=1  # Low priority
        )
        assert success_c is False

        # Step 4: Workflow A completes
        # Deallocate resources via ResourcePool
        await resource_pool.deallocate(
            workflow_id="workflow-a",
            resources={"concurrent": 5}
        )

        # Remove P2-15 budget
        mock_resource_manager.remove_budget("workflow-a")

        # Verify ResourcePool state after deallocation
        assert resource_pool.allocated_concurrent == 3
        assert resource_pool.available_concurrent == 7

        # Step 5: Workflow C can now start
        can_allocate = await resource_pool.can_allocate(concurrent=3)
        assert can_allocate is True

        success_c = await resource_pool.allocate(
            workflow_id="workflow-c",
            resources={"concurrent": 3},
            priority=1
        )
        assert success_c is True

        mock_resource_manager.create_budget(
            execution_id="workflow-c",
            max_concurrent=3,
            max_tokens=3000,
            max_cost=1.5
        )

        # Final verification
        assert resource_pool.allocated_concurrent == 6
        assert resource_pool.available_concurrent == 4

        # Check P2-15 global status
        status = mock_resource_manager.global_status()
        assert status["active_workflows"] == 2  # B and C
        assert status["total_active_tasks"] == 0  # No tasks running yet
        assert status["global_max_concurrent"] == 20

        # Verify per-workflow budgets
        assert "workflow-b" in status["per_execution"]
        assert "workflow-c" in status["per_execution"]
        assert "workflow-a" not in status["per_execution"]  # Removed

    @pytest.mark.asyncio
    async def test_priority_preemption_scenario(self, resource_pool):
        """
        Test priority-based preemption scenario.

        Scenario:
        1. Low priority workflow gets resources
        2. High priority workflow needs resources but pool is full
        3. ResourcePool should enable stealing from low priority workflow
        """
        # Fill the pool with low priority workflows
        success1 = await resource_pool.allocate(
            workflow_id="wf-low-1",
            resources={"concurrent": 5},
            priority=1  # Low priority
        )
        assert success1 is True

        success2 = await resource_pool.allocate(
            workflow_id="wf-low-2",
            resources={"concurrent": 5},
            priority=2  # Low priority
        )
        assert success2 is True

        # Pool is now full (10/10)
        assert resource_pool.available_concurrent == 0

        # High priority workflow needs resources
        # In a real implementation, this would trigger preemption
        # For now, we test the steal_slot interface
        success, message = await resource_pool.steal_slot(
            from_workflow_id="wf-low-1",  # Take from low priority
            to_workflow_id="wf-high"      # Give to high priority
        )

        # Current implementation simulates successful steal
        assert success is True
        assert "stole 1 slot" in message
        assert "wf-low-1" in message
        assert "wf-high" in message

    @pytest.mark.asyncio
    async def test_resource_usage_tracking(self, resource_pool):
        """Test integration of resource usage tracking."""
        # Set up rate limits
        resource_pool.max_total_tokens_per_minute = 50000
        resource_pool.max_total_cost_per_hour = 20.0

        # Allocate for a workflow
        await resource_pool.allocate(
            workflow_id="wf-usage-test",
            resources={"concurrent": 3},
            priority=5
        )

        # Simulate task execution and record usage
        # Task 1: 1000 tokens, $0.10
        await resource_pool.record_usage(tokens=1000, cost=0.10)

        # Task 2: 2500 tokens, $0.25
        await resource_pool.record_usage(tokens=2500, cost=0.25)

        # Task 3: 1500 tokens, $0.15
        await resource_pool.record_usage(tokens=1500, cost=0.15)

        # Verify usage tracking
        assert resource_pool.tokens_used_this_minute == 5000
        assert resource_pool.cost_used_this_hour == 0.5

        # Check available capacity
        capacity = resource_pool.get_available_capacity()
        assert capacity["concurrent"] == 7  # 10 total - 3 allocated
        assert capacity["tokens_per_minute"] == 45000  # 50000 - 5000
        assert capacity["cost_per_hour"] == 19.5  # 20.0 - 0.5

        # Deallocate
        await resource_pool.deallocate(
            workflow_id="wf-usage-test",
            resources={"concurrent": 3}
        )

        # Capacity should be restored for concurrent slots
        capacity = resource_pool.get_available_capacity()
        assert capacity["concurrent"] == 10

    @pytest.mark.asyncio
    async def test_agent_capacity_integration(self, resource_pool):
        """Test agent capacity limits integration."""
        # Set up agent capacities
        await resource_pool.set_agent_capacity("coder", 3)
        await resource_pool.set_agent_capacity("reviewer", 2)
        await resource_pool.set_agent_capacity("tester", 1)

        # Allocate workflows that use different agents
        # Workflow 1: Uses coder agent (3 slots)
        success1 = await resource_pool.allocate(
            workflow_id="wf-coder-heavy",
            resources={"concurrent": 3},
            priority=5
        )
        assert success1 is True

        # Workflow 2: Uses reviewer agent (2 slots)
        success2 = await resource_pool.allocate(
            workflow_id="wf-review-heavy",
            resources={"concurrent": 2},
            priority=5
        )
        assert success2 is True

        # Workflow 3: Uses tester agent (1 slot)
        success3 = await resource_pool.allocate(
            workflow_id="wf-test-heavy",
            resources={"concurrent": 1},
            priority=5
        )
        assert success3 is True

        # Total allocated: 6 slots, pool has 10 total
        assert resource_pool.allocated_concurrent == 6
        assert resource_pool.available_concurrent == 4

        # Try to allocate another workflow that needs coder agent
        # Coder agent already at capacity (3/3), but pool has capacity
        # This tests that agent-level limits are tracked separately
        # (Implementation would need to track per-agent usage)

        # For now, just verify the agent capacity settings
        coder_cap = await resource_pool.get_agent_capacity("coder")
        reviewer_cap = await resource_pool.get_agent_capacity("reviewer")
        tester_cap = await resource_pool.get_agent_capacity("tester")

        assert coder_cap == 3
        assert reviewer_cap == 2
        assert tester_cap == 1
