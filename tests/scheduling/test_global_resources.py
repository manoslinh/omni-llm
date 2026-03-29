"""
Tests for global resource management.
"""

import asyncio

import pytest

from omni.scheduling.resource_pool import (
    GlobalResourceManager,
    ResourcePool,
    WorkflowQuota,
)


class TestResourcePool:
    """Tests for ResourcePool class."""

    def test_default_initialization(self):
        pool = ResourcePool()
        assert pool.max_total_concurrent == 20
        assert pool.allocated_concurrent == 0
        assert pool.available_concurrent == 20

    def test_custom_initialization(self):
        pool = ResourcePool(max_total_concurrent=10, max_total_cost_per_hour=5.0)
        assert pool.max_total_concurrent == 10
        assert pool.max_total_cost_per_hour == 5.0

    def test_can_allocate(self):
        pool = ResourcePool(max_total_concurrent=5)
        assert pool.can_allocate(3) is True
        assert pool.can_allocate(5) is True
        assert pool.can_allocate(6) is False

    def test_allocate_and_release(self):
        pool = ResourcePool(max_total_concurrent=5)

        # Allocate 3 slots
        assert pool.allocate("exec1", 3) is True
        assert pool.allocated_concurrent == 3
        assert pool.available_concurrent == 2

        # Try to allocate 3 more (only 2 available)
        assert pool.allocate("exec2", 3) is False
        assert pool.allocated_concurrent == 3  # Unchanged

        # Allocate 2 more
        assert pool.allocate("exec2", 2) is True
        assert pool.allocated_concurrent == 5
        assert pool.available_concurrent == 0

        # Release some slots
        pool.release("exec1", 2)
        assert pool.allocated_concurrent == 3
        assert pool.available_concurrent == 2

    def test_utilization_property(self):
        pool = ResourcePool(max_total_concurrent=10)
        pool.allocate("exec1", 4)

        util = pool.utilization
        assert util["total_concurrent"] == 10
        assert util["allocated"] == 4
        assert util["available"] == 6
        assert util["utilization_pct"] == 40.0
        assert util["active_workflows"] == 1

    def test_record_usage(self):
        pool = ResourcePool()

        # Record some usage
        pool.record_usage(tokens=1000, cost=0.01)
        assert pool.tokens_used_this_minute == 1000
        assert pool.cost_used_this_hour == 0.01

        # Record more usage
        pool.record_usage(tokens=500, cost=0.005)
        assert pool.tokens_used_this_minute == 1500
        assert pool.cost_used_this_hour == 0.015


class TestWorkflowQuota:
    """Tests for WorkflowQuota class."""

    def test_initialization(self):
        quota = WorkflowQuota(
            execution_id="exec1",
            max_concurrent=5,
            max_cost=10.0,
            max_tokens=100000,
            priority=7,
            guaranteed_share=0.2,
        )
        assert quota.execution_id == "exec1"
        assert quota.max_concurrent == 5
        assert quota.max_cost == 10.0
        assert quota.max_tokens == 100000
        assert quota.priority == 7
        assert quota.guaranteed_share == 0.2


class TestGlobalResourceManager:
    """Tests for GlobalResourceManager class."""

    @pytest.fixture
    def manager(self):
        return GlobalResourceManager(ResourcePool(max_total_concurrent=10))

    @pytest.mark.asyncio
    async def test_create_workflow_budget_success(self, manager):
        budget = await manager.create_workflow_budget(
            execution_id="exec1",
            requested_concurrent=5,
            priority=5,
        )

        assert budget is not None
        assert budget.execution_id == "exec1"
        assert budget.max_concurrent == 5

        # Check that pool was updated
        assert manager.pool.allocated_concurrent == 5
        assert manager.pool.available_concurrent == 5
        assert "exec1" in manager._quotas
        assert "exec1" in manager.pool.active_budgets

    @pytest.mark.asyncio
    async def test_create_workflow_budget_partial_allocation(self, manager):
        # First workflow takes most capacity
        budget1 = await manager.create_workflow_budget(
            execution_id="exec1",
            requested_concurrent=8,
            priority=5,
        )
        assert budget1.max_concurrent == 8

        # Second workflow gets only what's left
        budget2 = await manager.create_workflow_budget(
            execution_id="exec2",
            requested_concurrent=5,
            priority=5,
        )
        assert budget2.max_concurrent == 2  # Only 2 slots left

        # Check pool state
        assert manager.pool.allocated_concurrent == 10
        assert manager.pool.available_concurrent == 0

    @pytest.mark.asyncio
    async def test_create_workflow_budget_zero_allocation(self, manager):
        # Fill the pool
        await manager.create_workflow_budget(
            execution_id="exec1",
            requested_concurrent=10,
            priority=5,
        )

        # Try to create another budget when pool is full
        budget = await manager.create_workflow_budget(
            execution_id="exec2",
            requested_concurrent=5,
            priority=5,
        )

        # Should still create budget but with 0 concurrent
        assert budget is not None
        assert budget.max_concurrent == 0

    @pytest.mark.asyncio
    async def test_release_workflow_budget(self, manager):
        # Create and release a budget
        await manager.create_workflow_budget(
            execution_id="exec1",
            requested_concurrent=5,
            priority=5,
        )

        assert manager.pool.allocated_concurrent == 5
        assert "exec1" in manager._quotas

        # Release the budget
        await manager.release_workflow_budget("exec1")

        # Check that resources were freed
        assert manager.pool.allocated_concurrent == 0
        assert "exec1" not in manager._quotas
        assert "exec1" not in manager.pool.active_budgets

    @pytest.mark.asyncio
    async def test_release_nonexistent_budget(self, manager):
        # Should not raise an error
        await manager.release_workflow_budget("nonexistent")

    @pytest.mark.asyncio
    async def test_check_capacity(self, manager):
        # Initially, pool has capacity
        assert await manager.check_capacity("exec1", 3) is True

        # Allocate some capacity
        manager.pool.allocate("exec1", 5)

        # Still has capacity (5 allocated, 5 available)
        assert await manager.check_capacity("exec1", 3) is True

        # Fill the pool
        manager.pool.allocate("exec2", 5)

        # No more capacity
        assert await manager.check_capacity("exec1", 1) is False

    @pytest.mark.asyncio
    async def test_check_capacity_with_quota(self):
        manager = GlobalResourceManager(ResourcePool(max_total_concurrent=10))

        # Create a quota manually for testing
        quota = WorkflowQuota(
            execution_id="exec1",
            max_concurrent=3,
            max_cost=None,
            max_tokens=None,
            priority=5,
        )
        manager._quotas["exec1"] = quota

        # Create a mock budget
        budget = type('MockBudget', (), {
            'execution_id': 'exec1',
            'active_tasks': 2,
            'max_concurrent': 3,
        })()
        manager.pool.active_budgets["exec1"] = budget

        # Has capacity (2 active, max 3)
        assert await manager.check_capacity("exec1", 1) is True

        # Would exceed quota (2 active + 2 requested = 4 > 3)
        assert await manager.check_capacity("exec1", 2) is False

    def test_get_load_balancing_hint(self, manager):
        hints = manager.get_load_balancing_hint()

        assert "suggested_per_workflow" in hints
        assert "global_utilization" in hints
        assert "agent_hints" in hints

        # With empty pool, suggested per workflow should be total
        assert hints["suggested_per_workflow"] == 10

    @pytest.mark.asyncio
    async def test_get_status(self, manager):
        status = await manager.get_status()

        assert "pool" in status
        assert "workflows" in status
        assert isinstance(status["workflows"], dict)

    @pytest.mark.asyncio
    async def test_preemption_priority_based(self, manager):
        # Create low-priority workflow
        budget1 = await manager.create_workflow_budget(
            execution_id="exec_low",
            requested_concurrent=8,
            priority=1,  # Low priority
        )
        assert budget1.max_concurrent == 8

        # Create high-priority workflow (should preempt from low-priority)
        budget2 = await manager.create_workflow_budget(
            execution_id="exec_high",
            requested_concurrent=5,
            priority=9,  # High priority
        )

        # High-priority should get full request (5)
        # Low-priority should lose 3 slots (8 → 5)
        assert budget2.max_concurrent == 5
        assert manager._quotas["exec_low"].max_concurrent == 5

        # Total allocation should be 10 (5 + 5)
        assert manager.pool.allocated_concurrent == 10

    @pytest.mark.asyncio
    async def test_preemption_leave_at_least_one(self, manager):
        # Create workflow with minimal allocation
        budget1 = await manager.create_workflow_budget(
            execution_id="exec_minimal",
            requested_concurrent=2,
            priority=1,
        )
        assert budget1.max_concurrent == 2

        # Try to preempt - should leave at least 1 slot
        budget2 = await manager.create_workflow_budget(
            execution_id="exec_high",
            requested_concurrent=10,  # Asking for more than available
            priority=9,
        )

        # Should get 9 slots (10 total - 1 left for low-priority)
        assert budget2.max_concurrent == 9
        assert manager._quotas["exec_minimal"].max_concurrent == 1

    @pytest.mark.asyncio
    async def test_concurrent_access(self, manager):
        """Test that manager handles concurrent access correctly."""
        async def create_budget(i):
            return await manager.create_workflow_budget(
                execution_id=f"exec_{i}",
                requested_concurrent=3,
                priority=i,
            )

        # Create multiple budgets concurrently
        tasks = [create_budget(i) for i in range(5)]
        budgets = await asyncio.gather(*tasks)

        # All budgets should be created
        assert len(budgets) == 5

        # Total allocation should not exceed pool capacity
        total_allocated = sum(b.max_concurrent for b in budgets)
        assert total_allocated <= manager.pool.max_total_concurrent

        # Check that all execution IDs are in quotas
        for i in range(5):
            assert f"exec_{i}" in manager._quotas
