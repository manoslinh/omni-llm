"""
Tests for resource management.
"""

import pytest

from src.omni.workflow.resources import (
    ConcurrencyLimiter,
    ResourceLimit,
    ResourceManager,
    ResourceType,
    WorkflowResources,
    get_resource_manager,
)


class TestResourceLimit:
    """Tests for ResourceLimit."""

    def test_acquire_within_limit(self):
        rl = ResourceLimit(ResourceType.TOKENS, 100, 0, "tokens")
        assert rl.can_acquire(50)
        assert rl.acquire(50)
        assert rl.current == 50
        assert rl.available == 50

    def test_acquire_exceeds_limit(self):
        rl = ResourceLimit(ResourceType.TOKENS, 100, 0, "tokens")
        assert not rl.can_acquire(200)
        assert not rl.acquire(200)
        assert rl.current == 0

    def test_release(self):
        rl = ResourceLimit(ResourceType.TOKENS, 100, 0, "tokens")
        rl.acquire(80)
        rl.release(30)
        assert rl.current == 50
        assert rl.available == 50

    def test_release_clamps_at_zero(self):
        rl = ResourceLimit(ResourceType.TOKENS, 100, 0, "tokens")
        rl.acquire(20)
        rl.release(100)
        assert rl.current == 0

    def test_usage_percentage(self):
        rl = ResourceLimit(ResourceType.COST, 10.0, 0, "USD")
        rl.acquire(5.0)
        assert rl.usage_percentage == 50.0

    def test_usage_percentage_zero_limit(self):
        rl = ResourceLimit(ResourceType.COST, 0, 0, "USD")
        assert rl.usage_percentage == 0.0


class TestWorkflowResources:
    """Tests for WorkflowResources."""

    def test_default_limits_created(self):
        wr = WorkflowResources(workflow_id="wf", execution_id="exec")
        assert ResourceType.CONCURRENCY in wr.limits
        assert ResourceType.TOKENS in wr.limits
        assert ResourceType.COST in wr.limits
        assert ResourceType.TIME in wr.limits

    def test_can_acquire_and_release(self):
        wr = WorkflowResources(workflow_id="wf", execution_id="exec")
        assert wr.can_acquire(ResourceType.TOKENS, 100)
        assert wr.acquire(ResourceType.TOKENS, 100)
        assert wr.get_usage(ResourceType.TOKENS) == 100
        wr.release(ResourceType.TOKENS, 50)
        assert wr.get_usage(ResourceType.TOKENS) == 50

    def test_unknown_resource_type(self):
        wr = WorkflowResources(workflow_id="wf", execution_id="exec")
        assert wr.can_acquire(ResourceType.MEMORY)  # Not in defaults
        assert wr.acquire(ResourceType.MEMORY)
        assert wr.get_usage(ResourceType.MEMORY) == 0.0
        assert wr.get_available(ResourceType.MEMORY) == float("inf")

    def test_to_dict(self):
        wr = WorkflowResources(workflow_id="wf", execution_id="exec")
        d = wr.to_dict()
        assert d["workflow_id"] == "wf"
        assert "limits" in d


class TestConcurrencyLimiter:
    """Tests for ConcurrencyLimiter."""

    def test_acquire_release(self):
        cl = ConcurrencyLimiter(max_concurrent=2)
        assert cl.acquire("task1")
        assert cl.acquire("task2")
        assert not cl.acquire("task3")  # No slot
        assert cl.active_count == 2

        cl.release("task1")
        assert cl.acquire("task3")
        assert cl.active_count == 2

    def test_available_and_usage(self):
        cl = ConcurrencyLimiter(max_concurrent=5)
        assert cl.available == 5
        assert cl.usage_percentage == 0.0
        cl.acquire("t1")
        cl.acquire("t2")
        assert cl.available == 3
        assert cl.usage_percentage == 40.0


class TestResourceManager:
    """Tests for ResourceManager."""

    def test_register_unregister_workflow(self):
        rm = ResourceManager()
        wr = rm.register_workflow("wf1", "exec1")
        assert wr.workflow_id == "wf1"
        assert wr.execution_id == "exec1"

        # Register again returns same
        wr2 = rm.register_workflow("wf1", "exec1")
        assert wr is wr2

        rm.unregister_workflow("wf1", "exec1")
        assert rm.get_workflow_resources("wf1", "exec1") is None

    def test_acquire_release_resource(self):
        rm = ResourceManager()
        rm.register_workflow("wf1", "exec1")
        assert rm.acquire_resource("wf1", "exec1", ResourceType.TOKENS, 100)
        rm.release_resource("wf1", "exec1", ResourceType.TOKENS, 50)

    def test_global_limits_enforced(self):
        rm = ResourceManager()
        rm._global_limits[ResourceType.TOKENS] = ResourceLimit(ResourceType.TOKENS, 10, 0, "tokens")
        rm.register_workflow("wf1", "exec1")
        assert rm.acquire_resource("wf1", "exec1", ResourceType.TOKENS, 8)
        assert not rm.acquire_resource("wf1", "exec1", ResourceType.TOKENS, 5)  # Would exceed global

    def test_get_global_summary(self):
        rm = ResourceManager()
        rm.register_workflow("wf1", "exec1")
        rm.register_workflow("wf2", "exec2")
        summary = rm.get_global_summary()
        assert summary["active_workflows"] == 2
        assert "global_limits" in summary

    def test_concurrency_acquire_release(self):
        rm = ResourceManager()
        rm.register_workflow("wf1", "exec1")
        assert rm.acquire_concurrency("wf1", "exec1", "t1")
        rm.release_concurrency("wf1", "exec1", "t1")

    def test_singleton(self):
        rm1 = get_resource_manager()
        rm2 = get_resource_manager()
        assert rm1 is rm2
