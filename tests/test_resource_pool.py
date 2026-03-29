"""
Tests for the ResourcePool component of P2-16 Global Resource Manager.
"""

import asyncio

import pytest

from src.omni.scheduling.resource_pool import ResourcePool


class TestResourcePool:
    """Test suite for ResourcePool class."""

    @pytest.fixture
    def pool(self):
        """Create a fresh ResourcePool for each test."""
        return ResourcePool(resource_manager=None, max_total_concurrent=10)

    @pytest.mark.asyncio
    async def test_initial_state(self, pool):
        """Test initial state of ResourcePool."""
        assert pool.max_total_concurrent == 10
        assert pool.allocated_concurrent == 0
        assert pool.available_concurrent == 10

        utilization = pool.utilization
        assert utilization["total_concurrent"] == 10
        assert utilization["allocated"] == 0
        assert utilization["available"] == 10
        assert utilization["utilization_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_can_allocate(self, pool):
        """Test can_allocate method."""
        # Should be able to allocate when pool has capacity
        assert await pool.can_allocate(5) is True
        assert await pool.can_allocate(10) is True
        assert await pool.can_allocate(11) is False

    @pytest.mark.asyncio
    async def test_allocate_success(self, pool):
        """Test successful allocation."""
        # Allocate 3 slots
        success = await pool.allocate(
            workflow_id="wf-001",
            resources={"concurrent": 3},
            priority=5
        )
        assert success is True
        assert pool.allocated_concurrent == 3
        assert pool.available_concurrent == 7

        # Allocate 4 more slots
        success = await pool.allocate(
            workflow_id="wf-002",
            resources={"concurrent": 4},
            priority=3
        )
        assert success is True
        assert pool.allocated_concurrent == 7
        assert pool.available_concurrent == 3

    @pytest.mark.asyncio
    async def test_allocate_failure(self, pool):
        """Test allocation failure when insufficient capacity."""
        # Allocate 8 slots
        success = await pool.allocate(
            workflow_id="wf-001",
            resources={"concurrent": 8},
            priority=5
        )
        assert success is True

        # Try to allocate 3 more (only 2 available)
        success = await pool.allocate(
            workflow_id="wf-002",
            resources={"concurrent": 3},
            priority=3
        )
        assert success is False
        assert pool.allocated_concurrent == 8
        assert pool.available_concurrent == 2

    @pytest.mark.asyncio
    async def test_deallocate(self, pool):
        """Test deallocation of resources."""
        # Allocate resources
        await pool.allocate(
            workflow_id="wf-001",
            resources={"concurrent": 5},
            priority=5
        )
        assert pool.allocated_concurrent == 5

        # Deallocate 3 slots
        await pool.deallocate(
            workflow_id="wf-001",
            resources={"concurrent": 3}
        )
        assert pool.allocated_concurrent == 2
        assert pool.available_concurrent == 8

        # Deallocate more than allocated (should not go negative)
        await pool.deallocate(
            workflow_id="wf-001",
            resources={"concurrent": 5}
        )
        assert pool.allocated_concurrent == 0
        assert pool.available_concurrent == 10

    @pytest.mark.asyncio
    async def test_steal_slot_no_need(self, pool):
        """Test steal_slot when capacity is available."""
        # Pool has capacity, no need to steal
        success, message = await pool.steal_slot(
            from_workflow_id="wf-001",
            to_workflow_id="wf-002"
        )
        assert success is False
        assert "No need to steal" in message

    @pytest.mark.asyncio
    async def test_steal_slot_full_pool(self, pool):
        """Test steal_slot when pool is full."""
        # Fill the pool
        await pool.allocate(
            workflow_id="wf-001",
            resources={"concurrent": 10},
            priority=5
        )
        assert pool.available_concurrent == 0

        # Try to steal (simulated success for now)
        success, message = await pool.steal_slot(
            from_workflow_id="wf-001",
            to_workflow_id="wf-002"
        )
        # Note: Current implementation returns True for simulation
        # In real implementation, this would check priorities
        assert success is True
        assert "stole 1 slot" in message

    @pytest.mark.asyncio
    async def test_get_available_capacity(self, pool):
        """Test get_available_capacity method."""
        capacity = pool.get_available_capacity()
        assert capacity["concurrent"] == 10
        assert capacity["tokens_per_minute"] is None  # Not set
        assert capacity["cost_per_hour"] is None  # Not set

        # Set rate limits
        pool.max_total_tokens_per_minute = 10000
        pool.max_total_cost_per_hour = 10.0

        capacity = pool.get_available_capacity()
        assert capacity["concurrent"] == 10
        assert capacity["tokens_per_minute"] == 10000
        assert capacity["cost_per_hour"] == 10.0

    @pytest.mark.asyncio
    async def test_record_usage(self, pool):
        """Test record_usage method."""
        # Set rate limits
        pool.max_total_tokens_per_minute = 10000
        pool.max_total_cost_per_hour = 10.0

        # Record some usage
        await pool.record_usage(tokens=1000, cost=0.5)
        assert pool.tokens_used_this_minute == 1000
        assert pool.cost_used_this_hour == 0.5

        # Record more usage
        await pool.record_usage(tokens=2000, cost=1.0)
        assert pool.tokens_used_this_minute == 3000
        assert pool.cost_used_this_hour == 1.5

    @pytest.mark.asyncio
    async def test_agent_capacity(self, pool):
        """Test agent capacity management."""
        # Set agent capacity
        await pool.set_agent_capacity("coder", 3)
        await pool.set_agent_capacity("reviewer", 2)

        # Get agent capacity
        coder_cap = await pool.get_agent_capacity("coder")
        reviewer_cap = await pool.get_agent_capacity("reviewer")
        unknown_cap = await pool.get_agent_capacity("unknown")

        assert coder_cap == 3
        assert reviewer_cap == 2
        assert unknown_cap is None

    @pytest.mark.asyncio
    async def test_concurrent_access(self, pool):
        """Test thread-safe concurrent access."""
        # Create multiple coroutines that allocate concurrently
        async def allocate_workflow(wf_id: str):
            return await pool.allocate(
                workflow_id=wf_id,
                resources={"concurrent": 1},
                priority=1
            )

        # Run multiple allocations concurrently
        tasks = [
            allocate_workflow(f"wf-{i}") for i in range(15)  # More than capacity
        ]
        results = await asyncio.gather(*tasks)

        # Should have exactly 10 successful allocations (pool capacity)
        successful = sum(1 for r in results if r)
        assert successful == 10
        assert pool.allocated_concurrent == 10
        assert pool.available_concurrent == 0

    @pytest.mark.asyncio
    async def test_priority_allocation_scenario(self, pool):
        """Test a realistic priority-based allocation scenario."""
        # High priority workflow gets resources first
        success1 = await pool.allocate(
            workflow_id="wf-high",
            resources={"concurrent": 4},
            priority=9  # High priority
        )
        assert success1 is True

        # Medium priority workflow gets some resources
        success2 = await pool.allocate(
            workflow_id="wf-medium",
            resources={"concurrent": 4},
            priority=5  # Medium priority
        )
        assert success2 is True

        # Low priority workflow tries to get resources (only 2 left)
        success3 = await pool.allocate(
            workflow_id="wf-low",
            resources={"concurrent": 3},  # Only 2 available
            priority=1  # Low priority
        )
        assert success3 is False  # Should fail

        # But should succeed with 2 slots
        success4 = await pool.allocate(
            workflow_id="wf-low",
            resources={"concurrent": 2},
            priority=1
        )
        assert success4 is True

        # Verify final state
        assert pool.allocated_concurrent == 10
        assert pool.available_concurrent == 0

        utilization = pool.utilization
        assert utilization["allocated"] == 10
        assert utilization["available"] == 0
        assert utilization["utilization_pct"] == 100.0
        assert utilization["active_workflows"] == 3  # 3 workflows have budgets
