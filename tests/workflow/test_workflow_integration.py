"""
Integration tests for workflow orchestration — end-to-end scenarios.
"""


from src.omni.workflow.context import NodeStatus, WorkflowContext
from src.omni.workflow.definition import WorkflowDefinition
from src.omni.workflow.nodes import (
    Condition,
    EdgeType,
    NodeEdge,
    NodeType,
    WorkflowNode,
)
from src.omni.workflow.state_machine import WorkflowStateMachine


class TestEndToEndWorkflows:
    """End-to-end tests for complex workflow patterns."""

    def test_loop_with_conditional(self):
        """WHILE loop body contains an IF node."""
        nodes = {
            "loop": WorkflowNode(
                node_id="loop",
                node_type=NodeType.WHILE,
                label="Retry loop",
                loop_condition=Condition("iteration < 3"),
                loop_body=["check", "maybe_stop"],
                max_iterations=10,
                edges=[NodeEdge(target_node_id="done")],
            ),
            "check": WorkflowNode(
                node_id="check",
                node_type=NodeType.IF,
                label="Check iteration",
                condition=Condition("iteration >= 2"),
                true_branch=["stop_flag"],
                false_branch=[],
            ),
            "stop_flag": WorkflowNode(
                node_id="stop_flag",
                node_type=NodeType.TASK,
                label="Set stop flag",
                task_id="stop_flag",
            ),
            "maybe_stop": WorkflowNode(
                node_id="maybe_stop",
                node_type=NodeType.TASK,
                label="Continue",
                task_id="continue_task",
            ),
            "done": WorkflowNode(
                node_id="done",
                node_type=NodeType.TASK,
                label="Done",
                task_id="done_task",
            ),
        }
        wf = WorkflowDefinition(
            workflow_id="loop_conditional",
            name="Loop with Conditional",
            nodes=nodes,
            entry_node_id="loop",
            exit_node_ids=["done"],
        )
        ctx = WorkflowContext(workflow_id="loop_conditional", execution_id="exec1")
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert result.success
        assert ctx.get_node_result("loop").outputs["iterations"] == 3
        assert ctx.get_node_result("done").status == NodeStatus.SUCCESS

    def test_for_each_with_parallel(self):
        """FOR_EACH body contains a PARALLEL node."""
        nodes = {
            "foreach": WorkflowNode(
                node_id="foreach",
                node_type=NodeType.FOR_EACH,
                label="Process items",
                collection_expression="variables['items']",
                element_variable="item",
                index_variable="idx",
                loop_body=["parallel_process"],
                max_iterations=100,
            ),
            "parallel_process": WorkflowNode(
                node_id="parallel_process",
                node_type=NodeType.PARALLEL,
                label="Process element in parallel",
                children=["step_a", "step_b"],
            ),
            "step_a": WorkflowNode(
                node_id="step_a",
                node_type=NodeType.TASK,
                label="Step A",
                task_id="step_a",
            ),
            "step_b": WorkflowNode(
                node_id="step_b",
                node_type=NodeType.TASK,
                label="Step B",
                task_id="step_b",
            ),
        }
        wf = WorkflowDefinition(
            workflow_id="foreach_parallel",
            name="ForEach with Parallel",
            nodes=nodes,
            entry_node_id="foreach",
            exit_node_ids=["foreach"],
        )
        ctx = WorkflowContext(workflow_id="foreach_parallel", execution_id="exec1", variables={"items": [1, 2]})
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert result.success

    def test_nested_try_catch(self):
        """Nested TRY_CATCH — inner catches first."""
        failing = WorkflowNode(
            node_id="failing_task",
            node_type=NodeType.TASK,
            label="Failing",
            task_id=None,
        )
        nodes = {
            "outer_tc": WorkflowNode(
                node_id="outer_tc",
                node_type=NodeType.TRY_CATCH,
                label="Outer try",
                try_body=["inner_tc"],
                catch_handlers=[
                    NodeEdge(target_node_id="outer_handler", edge_type=EdgeType.UNCONDITIONAL)
                ],
                edges=[NodeEdge(target_node_id="after")],
            ),
            "inner_tc": WorkflowNode(
                node_id="inner_tc",
                node_type=NodeType.TRY_CATCH,
                label="Inner try",
                try_body=["failing_task"],
                catch_handlers=[
                    NodeEdge(target_node_id="inner_handler", edge_type=EdgeType.UNCONDITIONAL)
                ],
            ),
            "failing_task": failing,
            "inner_handler": WorkflowNode(
                node_id="inner_handler",
                node_type=NodeType.TASK,
                label="Inner handler",
                task_id="inner_handler",
            ),
            "outer_handler": WorkflowNode(
                node_id="outer_handler",
                node_type=NodeType.TASK,
                label="Outer handler",
                task_id="outer_handler",
            ),
            "after": WorkflowNode(
                node_id="after",
                node_type=NodeType.TASK,
                label="After",
                task_id="after",
            ),
        }
        wf = WorkflowDefinition(
            workflow_id="nested_tc",
            name="Nested TRY_CATCH",
            nodes=nodes,
            entry_node_id="outer_tc",
            exit_node_ids=["after"],
        )
        ctx = WorkflowContext(workflow_id="nested_tc", execution_id="exec1")
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        # Inner handler should catch, not outer
        assert result.success
        assert ctx.get_node_result("inner_handler") is not None

    def test_if_else_both_sides_connected(self):
        """IF with both branches converging to a final node."""
        nodes = {
            "if1": WorkflowNode(
                node_id="if1",
                node_type=NodeType.IF,
                label="Branch",
                condition=Condition("variables.get('path') == 'yes'"),
                true_branch=["yes_task"],
                false_branch=["no_task"],
            ),
            "yes_task": WorkflowNode(
                node_id="yes_task",
                node_type=NodeType.TASK,
                label="Yes",
                task_id="yes",
                edges=[NodeEdge(target_node_id="final")],
            ),
            "no_task": WorkflowNode(
                node_id="no_task",
                node_type=NodeType.TASK,
                label="No",
                task_id="no",
                edges=[NodeEdge(target_node_id="final")],
            ),
            "final": WorkflowNode(
                node_id="final",
                node_type=NodeType.TASK,
                label="Final",
                task_id="final",
            ),
        }
        wf = WorkflowDefinition(
            workflow_id="if_else_converge",
            name="IF/Else Converge",
            nodes=nodes,
            entry_node_id="if1",
            exit_node_ids=["final"],
        )

        # Test true path
        ctx = WorkflowContext(workflow_id="if_else_converge", execution_id="yes", variables={"path": "yes"})
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()
        assert result.success
        assert ctx.get_node_result("yes_task").status == NodeStatus.SUCCESS
        assert ctx.get_node_result("final").status == NodeStatus.SUCCESS

        # Test false path
        ctx = WorkflowContext(workflow_id="if_else_converge", execution_id="no", variables={"path": "no"})
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()
        assert result.success
        assert ctx.get_node_result("no_task").status == NodeStatus.SUCCESS
        assert ctx.get_node_result("final").status == NodeStatus.SUCCESS


class TestFromPlanConversion:
    """Tests for P2-14 backward compatibility via from_plan()."""

    def test_from_plan_single_step(self):
        """Convert a plan with a single step."""
        class MockStep:
            step_id = "step_1"
            task_id = "task_001"
            description = "First task"
            dependencies = []
            agent_id = "coder"
            priority = 1
            metadata = {"key": "value"}

        class MockPlan:
            plan_id = "plan_001"
            task_graph_name = "Test Plan"
            steps = [MockStep()]

        wf = WorkflowDefinition.from_plan(MockPlan())
        assert wf.workflow_id == "plan_001"
        assert len(wf.nodes) == 1
        assert "step_1" in wf.nodes
        assert wf.nodes["step_1"].node_type == NodeType.TASK
        assert wf.nodes["step_1"].task_id == "task_001"
        assert wf.entry_node_id == "step_1"
        assert wf.exit_node_ids == ["step_1"]

    def test_from_plan_with_dependencies(self):
        """Convert a plan with step dependencies."""
        class MockStep1:
            step_id = "step_1"
            task_id = "task_001"
            description = "First"
            dependencies = []
            agent_id = None
            priority = 0
            metadata = {}

        class MockStep2:
            step_id = "step_2"
            task_id = "task_002"
            description = "Second"
            dependencies = ["step_1"]
            agent_id = None
            priority = 0
            metadata = {}

        class MockPlan:
            plan_id = "plan_002"
            task_graph_name = "Chain Plan"
            steps = [MockStep1(), MockStep2()]

        wf = WorkflowDefinition.from_plan(MockPlan())
        assert len(wf.nodes) == 2
        assert wf.entry_node_id == "step_1"
        assert wf.exit_node_ids == ["step_2"]
        # step_1 should have edge to step_2
        assert len(wf.nodes["step_1"].edges) == 1
        assert wf.nodes["step_1"].edges[0].target_node_id == "step_2"

    def test_from_plan_multiple_entry_points(self):
        """Convert a plan with multiple entry points (no dependencies)."""
        class MockStep1:
            step_id = "a"
            task_id = "task_a"
            description = ""
            dependencies = []
            agent_id = None
            priority = 0
            metadata = {}

        class MockStep2:
            step_id = "b"
            task_id = "task_b"
            description = ""
            dependencies = []
            agent_id = None
            priority = 0
            metadata = {}

        class MockPlan:
            plan_id = "plan_fan"
            task_graph_name = "Fan Plan"
            steps = [MockStep1(), MockStep2()]

        wf = WorkflowDefinition.from_plan(MockPlan())
        assert len(wf.nodes) == 3  # a, b, _entry
        assert "_entry" in wf.nodes
        assert wf.nodes["_entry"].node_type == NodeType.PARALLEL

    def test_from_plan_empty(self):
        """Convert an empty plan."""
        class MockPlan:
            plan_id = "empty"
            task_graph_name = "Empty"
            steps = []

        wf = WorkflowDefinition.from_plan(MockPlan())
        assert wf.workflow_id == "empty"
        assert len(wf.nodes) == 0

    def test_from_plan_no_attributes(self):
        """Convert a plan-like object with no expected attributes."""
        wf = WorkflowDefinition.from_plan("not a plan")
        assert wf.workflow_id == "converted-plan"
        assert len(wf.nodes) == 0

    def test_from_plan_uses_task_id_fallback(self):
        """Steps without step_id use task_id as fallback."""
        class MockStep:
            task_id = "fallback_task"
            description = "Fallback"
            dependencies = []
            agent_id = None
            priority = 0
            metadata = {}

        class MockPlan:
            plan_id = "fallback_plan"
            task_graph_name = "Fallback"
            steps = [MockStep()]

        wf = WorkflowDefinition.from_plan(MockPlan())
        assert "fallback_task" in wf.nodes
