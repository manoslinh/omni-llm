"""
Tests for the ResourcePool component of P2-16 Global Resource Manager.
"""

import pytest

from src.omni.scheduling.resource_pool import ResourcePool


class TestResourcePool:
    """Test suite for ResourcePool class."""

    @pytest.fixture
    def pool(self):
        """Create a fresh ResourcePool for each test."""
        return ResourcePool(max_total_concurrent=10)

    def test_initial_state(self, pool):
        """Test initial state of ResourcePool."""
        assert pool.max_total_concurrent == 10
        assert pool.allocated_concurrent == 0
        assert pool.available_concurrent == 10

        utilization = pool.utilization
        assert utilization["total_concurrent"] == 10
        assert utilization["allocated"] == 0
        assert utilization["available"] == 10
        assert utilization["utilization_pct"] == 0.0

    def test_can_allocate(self, pool):
        """Test can_allocate method."""
        # Should be able to allocate when pool has capacity
        assert pool.can_allocate(5) is True
        assert pool.can_allocate(10) is True
        assert pool.can_allocate(11) is False

    def test_allocate_success(self, pool):
        """Test successful allocation."""
        # Allocate 3 slots
        success = pool.allocate(
            execution_id="wf-001",
            concurrent=3
        )
        assert success is True
        assert pool.allocated_concurrent == 3
        assert pool.available_concurrent == 7

        # Allocate 4 more slots
        success = pool.allocate(
            execution_id="wf-002",
            concurrent=4
        )
        assert success is True
        assert pool.allocated_concurrent == 7
        assert pool.available_concurrent == 3

    def test_allocate_failure(self, pool):
        """Test allocation failure when insufficient capacity."""
        # Allocate 8 slots
        success = pool.allocate(
            execution_id="wf-001",
            concurrent=8
        )
        assert success is True

        # Try to allocate 3 more (only 2 available)
        success = pool.allocate(
            execution_id="wf-002",
            concurrent=3
        )
        assert success is False
        assert pool.allocated_concurrent == 8
        assert pool.available_concurrent == 2

    def test_release(self, pool):
        """Test release of resources."""
        # Allocate resources
        pool.allocate(
            execution_id="wf-001",
            concurrent=5
        )
        assert pool.allocated_concurrent == 5

        # Release 3 slots
        pool.release(
            execution_id="wf-001",
            concurrent=3
        )
        assert pool.allocated_concurrent == 2
        assert pool.available_concurrent == 8

        # Release more than allocated (should not go negative)
        pool.release(
            execution_id="wf-001",
            concurrent=5
        )
        assert pool.allocated_concurrent == 0
        assert pool.available_concurrent == 10



    def test_get_available_capacity(self, pool):
        """Test get_available_capacity method."""
        # Note: There's no get_available_capacity method in ResourcePool
        # The integration test shows we should use pool.available_concurrent
        # and pool.utilization for capacity information
        assert pool.available_concurrent == 10
        
        # Set rate limits
        pool.max_total_tokens_per_minute = 10000
        pool.max_total_cost_per_hour = 10.0

        # Check utilization includes rate limits
        utilization = pool.utilization
        assert utilization["total_concurrent"] == 10
        assert pool.tokens_used_this_minute == 0
        assert pool.cost_used_this_hour == 0.0

    def test_record_usage(self, pool):
        """Test record_usage method."""
        # Set rate limits
        pool.max_total_tokens_per_minute = 10000
        pool.max_total_cost_per_hour = 10.0

        # Record some usage
        pool.record_usage(tokens=1000, cost=0.5)
        assert pool.tokens_used_this_minute == 1000
        assert pool.cost_used_this_hour == 0.5

        # Record more usage
        pool.record_usage(tokens=2000, cost=1.0)
        assert pool.tokens_used_this_minute == 3000
        assert pool.cost_used_this_hour == 1.5

    def test_agent_capacity(self, pool):
        """Test agent capacity management."""
        # Set agent capacity via direct dict access
        pool.agent_max_concurrent["coder"] = 3
        pool.agent_max_concurrent["reviewer"] = 2

        # Get agent capacity via direct dict access
        coder_cap = pool.agent_max_concurrent.get("coder")
        reviewer_cap = pool.agent_max_concurrent.get("reviewer")
        unknown_cap = pool.agent_max_concurrent.get("unknown")

        assert coder_cap == 3
        assert reviewer_cap == 2
        assert unknown_cap is None

    def test_concurrent_access(self, pool):
        """Test thread-safe concurrent access."""
        import threading
        
        results = []
        lock = threading.Lock()
        
        def allocate_workflow(wf_id: str):
            success = pool.allocate(execution_id=wf_id, concurrent=1)
            with lock:
                results.append(success)
        
        # Create multiple threads that allocate concurrently
        threads = [
            threading.Thread(target=allocate_workflow, args=(f"wf-{i}",))
            for i in range(15)  # More than capacity
        ]
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for all threads to complete
        for t in threads:
            t.join()
        
        # Should have exactly 10 successful allocations (pool capacity)
        successful = sum(1 for r in results if r)
        assert successful == 10
        assert pool.allocated_concurrent == 10
        assert pool.available_concurrent == 0

    def test_allocation_scenario(self, pool):
        """Test a realistic allocation scenario."""
        # First workflow gets resources
        success1 = pool.allocate(
            execution_id="wf-1",
            concurrent=4
        )
        assert success1 is True

        # Second workflow gets some resources
        success2 = pool.allocate(
            execution_id="wf-2",
            concurrent=4
        )
        assert success2 is True

        # Third workflow tries to get resources (only 2 left)
        success3 = pool.allocate(
            execution_id="wf-3",
            concurrent=3  # Only 2 available
        )
        assert success3 is False  # Should fail

        # But should succeed with 2 slots
        success4 = pool.allocate(
            execution_id="wf-3",
            concurrent=2
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
