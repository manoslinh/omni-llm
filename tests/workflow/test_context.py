"""
Tests for workflow context.
"""

import pytest

from src.omni.workflow.context import NodeStatus, NodeResult, ResourceSnapshot, WorkflowContext


class TestWorkflowContext:
    """Tests for WorkflowContext."""

    def test_node_lifecycle(self):
        ctx = WorkflowContext(workflow_id="wf", execution_id="exec")
        ctx.mark_node_started("n1")
        r = ctx.get_node_result("n1")
        assert r.status == NodeStatus.RUNNING
        assert r.started_at is not None

        ctx.mark_node_success("n1", {"output": 42})
        r = ctx.get_node_result("n1")
        assert r.status == NodeStatus.SUCCESS
        assert r.outputs["output"] == 42
        assert r.success is True

    def test_node_failure_tracking(self):
        ctx = WorkflowContext(workflow_id="wf", execution_id="exec")
        ctx.mark_node_failed("n1", "Something broke", "RuntimeError")
        r = ctx.get_node_result("n1")
        assert r.status == NodeStatus.FAILED
        assert r.error == "Something broke"
        assert r.error_type == "RuntimeError"
        assert r.failed is True

    def test_node_skipped(self):
        ctx = WorkflowContext(workflow_id="wf", execution_id="exec")
        ctx.mark_node_skipped("n1")
        r = ctx.get_node_result("n1")
        assert r.status == NodeStatus.SKIPPED

    def test_variable_management(self):
        ctx = WorkflowContext(workflow_id="wf", execution_id="exec")
        ctx.set_variable("x", 10)
        assert ctx.get_variable("x") == 10
        assert ctx.get_variable("missing", "default") == "default"

        ctx.update_variables({"a": 1, "b": 2})
        assert ctx.get_variable("a") == 1
        assert ctx.get_variable("b") == 2

    def test_iteration_counter(self):
        ctx = WorkflowContext(workflow_id="wf", execution_id="exec")
        assert ctx.get_iteration_count("loop") == 0
        assert ctx.increment_iteration("loop") == 1
        assert ctx.increment_iteration("loop") == 2
        assert ctx.get_iteration_count("loop") == 2
        ctx.reset_iteration("loop")
        assert ctx.get_iteration_count("loop") == 0

    def test_execution_stack(self):
        ctx = WorkflowContext(workflow_id="wf", execution_id="exec")
        ctx.push_to_stack("a")
        ctx.push_to_stack("b")
        assert ctx.peek_stack() == "b"
        assert ctx.is_in_stack("a")
        assert ctx.pop_from_stack() == "b"
        assert ctx.pop_from_stack() == "a"
        assert ctx.pop_from_stack() is None
        assert ctx.peek_stack() is None

    def test_error_stack(self):
        ctx = WorkflowContext(workflow_id="wf", execution_id="exec")
        ctx.push_error("n1", "err1")
        ctx.push_error("n2", "err2")
        assert ctx.peek_error() == ("n2", "err2")
        assert ctx.pop_error() == ("n2", "err2")
        ctx.clear_errors()
        assert ctx.peek_error() is None
        assert ctx.pop_error() is None

    def test_evaluation_context_generation(self):
        ctx = WorkflowContext(
            workflow_id="wf",
            execution_id="exec",
            variables={"x": 5},
        )
        ctx.increment_iteration("loop1")
        ec = ctx.get_evaluation_context("loop1")
        assert "variables" in ec
        assert ec["variables"]["x"] == 5
        assert ec["iteration"] == 1

    def test_serialization_roundtrip(self):
        ctx = WorkflowContext(
            workflow_id="wf",
            execution_id="exec",
            variables={"key": "value"},
        )
        ctx.mark_node_started("n1")
        ctx.mark_node_success("n1", {"out": 1})
        ctx.increment_iteration("loop1")
        ctx.push_to_stack("tc1")
        ctx.push_error("n1", "oops")

        d = ctx.to_dict()
        restored = WorkflowContext.from_dict(d)

        assert restored.workflow_id == "wf"
        assert restored.execution_id == "exec"
        assert restored.variables == {"key": "value"}
        assert restored.get_node_result("n1").status == NodeStatus.SUCCESS
        assert restored.get_iteration_count("loop1") == 1
        assert restored.execution_stack == ["tc1"]
        assert restored.error_stack == [("n1", "oops")]

    def test_resource_usage_tracking(self):
        ctx = WorkflowContext(workflow_id="wf", execution_id="exec")
        ctx.update_resource_usage(tokens_used=100, cost_incurred=0.5, active_tasks=2)
        assert ctx.resource_usage.tokens_used == 100
        assert ctx.resource_usage.cost_incurred == 0.5
        assert ctx.resource_usage.active_tasks == 2

        ctx.update_resource_usage(tokens_used=50)
        assert ctx.resource_usage.tokens_used == 150


class TestNodeResult:
    """Tests for NodeResult."""

    def test_duration(self):
        from datetime import datetime, timedelta
        now = datetime.now()
        r = NodeResult(
            node_id="n",
            status=NodeStatus.SUCCESS,
            started_at=now,
            completed_at=now + timedelta(seconds=5),
        )
        assert r.duration == 5.0

    def test_no_duration_without_timestamps(self):
        r = NodeResult(node_id="n", status=NodeStatus.SUCCESS)
        assert r.duration is None


class TestResourceSnapshot:
    """Tests for ResourceSnapshot."""

    def test_duration(self):
        from datetime import datetime, timedelta
        now = datetime.now()
        snap = ResourceSnapshot(start_time=now, current_time=now + timedelta(seconds=10))
        assert snap.duration == 10.0

    def test_no_duration(self):
        snap = ResourceSnapshot()
        assert snap.duration is None
