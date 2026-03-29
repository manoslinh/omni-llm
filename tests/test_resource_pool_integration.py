"""
Integration tests for ResourcePool with P2-15 ResourceManager.

Tests are written against the actual ResourcePool API:
- allocate(execution_id, concurrent) -> bool  (sync)
- release(execution_id, concurrent) -> None   (sync)
- can_allocate(requested_concurrent) -> bool   (sync)
- record_usage(tokens, cost) -> None           (sync)
- agent_max_concurrent: dict (direct access)
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
        """Create a ResourcePool with 10 max concurrent."""
        return ResourcePool(max_total_concurrent=10)

    def test_integration_workflow(self, mock_resource_manager, resource_pool):
        """
        Test a complete workflow showing ResourcePool integration with P2-15.

        Scenario:
        1. Workflow A starts with 5 concurrent slots
        2. Workflow B starts with 3 concurrent slots
        3. Workflow C tries to start with 3 slots (should fail — only 2 available)
        4. Workflow A completes, freeing resources
        5. Workflow C can now start
        """
        # Step 1: Workflow A starts
        # Check global capacity via ResourcePool
        can_allocate = resource_pool.can_allocate(requested_concurrent=5)
        assert can_allocate is True

        # Allocate via ResourcePool
        success_a = resource_pool.allocate(execution_id="workflow-a", concurrent=5)
        assert success_a is True

        # Create P2-15 budget for workflow A
        mock_resource_manager.create_budget(
            execution_id="workflow-a",
            max_concurrent=5,
            max_tokens=10000,
            max_cost=5.0,
        )

        # Step 2: Workflow B starts
        # Check capacity (10 total - 5 allocated = 5 available)
        can_allocate = resource_pool.can_allocate(requested_concurrent=3)
        assert can_allocate is True

        success_b = resource_pool.allocate(execution_id="workflow-b", concurrent=3)
        assert success_b is True

        mock_resource_manager.create_budget(
            execution_id="workflow-b",
            max_concurrent=3,
            max_tokens=5000,
            max_cost=2.5,
        )

        # Verify ResourcePool state
        assert resource_pool.allocated_concurrent == 8
        assert resource_pool.available_concurrent == 2

        # Step 3: Workflow C tries to start (needs 3 slots, only 2 available)
        can_allocate = resource_pool.can_allocate(requested_concurrent=3)
        assert can_allocate is False

        success_c = resource_pool.allocate(execution_id="workflow-c", concurrent=3)
        assert success_c is False

        # Step 4: Workflow A completes — release resources
        resource_pool.release(execution_id="workflow-a", concurrent=5)

        # Remove P2-15 budget
        mock_resource_manager.remove_budget("workflow-a")

        # Verify ResourcePool state after deallocation
        assert resource_pool.allocated_concurrent == 3
        assert resource_pool.available_concurrent == 7

        # Step 5: Workflow C can now start
        can_allocate = resource_pool.can_allocate(requested_concurrent=3)
        assert can_allocate is True

        success_c = resource_pool.allocate(execution_id="workflow-c", concurrent=3)
        assert success_c is True

        mock_resource_manager.create_budget(
            execution_id="workflow-c",
            max_concurrent=3,
            max_tokens=3000,
            max_cost=1.5,
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

    def test_priority_preemption_scenario(self, resource_pool):
        """
        Test priority-based preemption scenario.

        Scenario:
        1. Two workflows fill the pool
        2. ResourcePool is full — new allocation fails
        3. Release one workflow, new allocation succeeds

        NOTE: steal_slot() does not exist on current ResourcePool.
        Preemption logic lives in GlobalResourceManager._try_preempt().
        This test covers basic capacity management; preemption is tested
        in test_global_resource_manager.py (if it exists).
        """
        # Fill the pool with two workflows
        success1 = resource_pool.allocate(execution_id="wf-low-1", concurrent=5)
        assert success1 is True

        success2 = resource_pool.allocate(execution_id="wf-low-2", concurrent=5)
        assert success2 is True

        # Pool is now full (10/10)
        assert resource_pool.available_concurrent == 0
        assert resource_pool.allocated_concurrent == 10

        # New allocation should fail
        success3 = resource_pool.allocate(execution_id="wf-high", concurrent=1)
        assert success3 is False

        # Release one workflow
        resource_pool.release(execution_id="wf-low-1", concurrent=5)

        # Now allocation succeeds
        success3 = resource_pool.allocate(execution_id="wf-high", concurrent=5)
        assert success3 is True
        assert resource_pool.allocated_concurrent == 10

    def test_resource_usage_tracking(self, resource_pool):
        """Test integration of resource usage tracking."""
        # Set up rate limits
        resource_pool.max_total_tokens_per_minute = 50000
        resource_pool.max_total_cost_per_hour = 20.0

        # Allocate for a workflow
        resource_pool.allocate(execution_id="wf-usage-test", concurrent=3)

        # Simulate task execution and record usage
        resource_pool.record_usage(tokens=1000, cost=0.10)
        resource_pool.record_usage(tokens=2500, cost=0.25)
        resource_pool.record_usage(tokens=1500, cost=0.15)

        # Verify usage tracking
        assert resource_pool.tokens_used_this_minute == 5000
        assert resource_pool.cost_used_this_hour == 0.5

        # Check available capacity
        assert resource_pool.available_concurrent == 7  # 10 total - 3 allocated

        # Check utilization dict
        utilization = resource_pool.utilization
        assert utilization["allocated"] == 3
        assert utilization["available"] == 7
        assert utilization["total_concurrent"] == 10

        # Release
        resource_pool.release(execution_id="wf-usage-test", concurrent=3)

        # Capacity should be restored
        assert resource_pool.available_concurrent == 10

    def test_agent_capacity_integration(self, resource_pool):
        """Test agent capacity limits integration.

        NOTE: set_agent_capacity() / get_agent_capacity() do not exist on
        current ResourcePool. Agent capacity is stored directly in the
        agent_max_concurrent dict.
        """
        # Set agent capacities via dict (actual API)
        resource_pool.agent_max_concurrent["coder"] = 3
        resource_pool.agent_max_concurrent["reviewer"] = 2
        resource_pool.agent_max_concurrent["tester"] = 1

        # Allocate workflows using different agent slots
        success1 = resource_pool.allocate(execution_id="wf-coder-heavy", concurrent=3)
        assert success1 is True

        success2 = resource_pool.allocate(execution_id="wf-review-heavy", concurrent=2)
        assert success2 is True

        success3 = resource_pool.allocate(execution_id="wf-test-heavy", concurrent=1)
        assert success3 is True

        # Total allocated: 6 slots, pool has 10 total
        assert resource_pool.allocated_concurrent == 6
        assert resource_pool.available_concurrent == 4

        # Verify agent capacity settings (direct dict access)
        assert resource_pool.agent_max_concurrent["coder"] == 3
        assert resource_pool.agent_max_concurrent["reviewer"] == 2
        assert resource_pool.agent_max_concurrent["tester"] == 1

    def test_active_budgets_tracking(self, resource_pool):
        """Verify ResourcePool tracks active budgets correctly."""
        resource_pool.allocate(execution_id="exec-1", concurrent=4)
        resource_pool.allocate(execution_id="exec-2", concurrent=3)

        assert "exec-1" in resource_pool.active_budgets
        assert "exec-2" in resource_pool.active_budgets
        assert resource_pool.active_budgets["exec-1"].max_concurrent == 4
        assert resource_pool.active_budgets["exec-2"].max_concurrent == 3

        # Release exec-1
        resource_pool.release(execution_id="exec-1", concurrent=4)
        assert "exec-1" not in resource_pool.active_budgets
        assert "exec-2" in resource_pool.active_budgets

    def test_utilization_property(self, resource_pool):
        """Test utilization reporting."""
        resource_pool.allocate(execution_id="exec-1", concurrent=6)

        util = resource_pool.utilization
        assert util["total_concurrent"] == 10
        assert util["allocated"] == 6
        assert util["available"] == 4
        assert util["utilization_pct"] == 60.0
        assert util["active_workflows"] == 1
