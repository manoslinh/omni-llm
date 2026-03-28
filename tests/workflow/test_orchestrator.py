"""
Tests for workflow orchestrator.
"""

import pytest

from src.omni.workflow.context import NodeStatus
from src.omni.workflow.definition import WorkflowDefinition
from src.omni.workflow.nodes import NodeEdge, NodeType, WorkflowNode
from src.omni.workflow.orchestrator import (
    OrchestratorConfig,
    WorkflowExecution,
    WorkflowOrchestrator,
    execute_workflow,
    get_orchestrator,
)


def _simple_workflow() -> WorkflowDefinition:
    nodes = {
        "t1": WorkflowNode(
            node_id="t1",
            node_type=NodeType.TASK,
            label="Task 1",
            task_id="task_001",
            edges=[NodeEdge(target_node_id="t2")],
        ),
        "t2": WorkflowNode(
            node_id="t2",
            node_type=NodeType.TASK,
            label="Task 2",
            task_id="task_002",
        ),
    }
    return WorkflowDefinition(
        workflow_id="test_wf",
        name="Test Workflow",
        nodes=nodes,
        entry_node_id="t1",
        exit_node_ids=["t2"],
    )


class TestWorkflowOrchestrator:
    """Tests for WorkflowOrchestrator."""

    def test_execute_simple_workflow(self):
        orch = WorkflowOrchestrator()
        wf = _simple_workflow()
        execution = orch.execute_workflow(wf)

        assert execution.status == "completed"
        assert execution.result is not None
        assert execution.result.success
        assert execution.context.get_node_result("t1").status == NodeStatus.SUCCESS
        assert execution.context.get_node_result("t2").status == NodeStatus.SUCCESS

    def test_execute_template(self):
        orch = WorkflowOrchestrator()
        execution = orch.execute_template(
            "retry_until_success",
            parameters={"task_id": "test_retry"},
        )
        assert execution.status == "completed"
        assert execution.result.success

    def test_execution_management(self):
        orch = WorkflowOrchestrator()
        wf = _simple_workflow()
        execution = orch.execute_workflow(wf, execution_id="my_exec")

        assert orch.get_execution("my_exec") is execution
        executions = orch.list_executions()
        assert len(executions) >= 1

    def test_cancel_execution(self):
        orch = WorkflowOrchestrator()
        wf = _simple_workflow()
        execution = orch.execute_workflow(wf, execution_id="cancel_test")
        # Already completed, so cancel returns False
        assert not orch.cancel_execution("cancel_test")
        assert orch.cancel_execution("nonexistent") is False

    def test_observer_notifications(self):
        events_received = []

        def observer(event):
            events_received.append(event)

        orch = WorkflowOrchestrator()
        orch.add_observer(observer)
        wf = _simple_workflow()
        orch.execute_workflow(wf)

        assert len(events_received) > 0
        orch.remove_observer(observer)

    def test_validation_before_execution(self):
        orch = WorkflowOrchestrator(config=OrchestratorConfig(validate_before_execution=True))
        # Invalid workflow: entry node doesn't exist
        wf = WorkflowDefinition(
            workflow_id="bad",
            name="Bad",
            nodes={},
            entry_node_id="nonexistent",
        )
        with pytest.raises(ValueError, match="validation failed"):
            orch.execute_workflow(wf)

    def test_validation_disabled(self):
        orch = WorkflowOrchestrator(config=OrchestratorConfig(validate_before_execution=False))
        wf = WorkflowDefinition(
            workflow_id="bad",
            name="Bad",
            nodes={},
            entry_node_id="nonexistent",
        )
        # Should not raise, just produce empty result
        execution = orch.execute_workflow(wf)
        assert execution.result is not None

    def test_list_executions_filtered(self):
        orch = WorkflowOrchestrator()
        wf1 = _simple_workflow()
        wf2 = _simple_workflow()
        wf2.workflow_id = "other_wf"
        orch.execute_workflow(wf1, execution_id="e1")
        orch.execute_workflow(wf2, execution_id="e2")

        all_execs = orch.list_executions()
        wf1_execs = orch.list_executions(workflow_id="test_wf")
        assert len(wf1_execs) >= 1

    def test_create_workflow_from_plan(self):
        orch = WorkflowOrchestrator()

        # Mock plan object
        class MockPlan:
            plan_id = "plan_001"
            task_graph_name = "Mock Plan"
            steps = []

        plan = MockPlan()
        wf = orch.create_workflow_from_plan(plan)
        assert wf.workflow_id == "plan_001"
        assert wf.name == "Mock Plan"

    def test_get_available_templates(self):
        orch = WorkflowOrchestrator()
        templates = orch.get_available_templates()
        assert len(templates) >= 5
        for t in templates:
            assert "template_id" in t
            assert "name" in t

    def test_emit_custom_event(self):
        orch = WorkflowOrchestrator()
        wf = _simple_workflow()
        execution = orch.execute_workflow(wf, execution_id="custom_event_test")

        events = []
        orch.add_observer(lambda e: events.append(e))
        assert orch.emit_custom_event("custom_event_test", "node_started", {"test": True})
        assert orch.emit_custom_event("nonexistent", "node_started") is False

    def test_validate_workflow(self):
        orch = WorkflowOrchestrator()
        wf = _simple_workflow()
        issues = orch.validate_workflow(wf)
        assert issues == []


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_execute_workflow(self):
        wf = _simple_workflow()
        execution = execute_workflow(wf)
        assert execution.result.success

    def test_get_orchestrator(self):
        orch = get_orchestrator()
        assert orch is not None
