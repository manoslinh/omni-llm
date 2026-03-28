"""
Tests for workflow state machine — the core execution engine.

Tests cover: sequential execution, control flow, loops (WHILE/FOR_EACH),
TRY_CATCH error handling, compensation, and edge cases.
"""


from src.omni.workflow.context import NodeStatus, WorkflowContext
from src.omni.workflow.definition import WorkflowDefinition
from src.omni.workflow.nodes import (
    CompensationAction,
    Condition,
    EdgeType,
    NodeEdge,
    NodeType,
    WorkflowNode,
)
from src.omni.workflow.state_machine import (
    ExecutionEventType,
    WorkflowStateMachine,
)


def _make_context(**kwargs) -> WorkflowContext:
    """Create a workflow context with defaults."""
    return WorkflowContext(
        workflow_id=kwargs.get("workflow_id", "test_wf"),
        execution_id=kwargs.get("execution_id", "test_exec"),
        variables=kwargs.get("variables", {}),
    )


def _make_definition(nodes: dict[str, WorkflowNode], entry: str = "", exits: list[str] | None = None) -> WorkflowDefinition:
    """Create a workflow definition."""
    return WorkflowDefinition(
        workflow_id="test_wf",
        name="Test Workflow",
        nodes=nodes,
        entry_node_id=entry,
        exit_node_ids=exits or [],
    )


def _simple_task(task_id: str, label: str = "") -> WorkflowNode:
    """Create a simple TASK node."""
    return WorkflowNode(
        node_id=task_id,
        node_type=NodeType.TASK,
        label=label or task_id,
        task_id=task_id,
    )


class TestSingleTaskExecution:
    """Test executing a single task node."""

    def test_single_task_completes(self):
        nodes = {"task1": _simple_task("task1")}
        wf = _make_definition(nodes, entry="task1", exits=["task1"])
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert result.success
        assert ctx.get_node_result("task1").status == NodeStatus.SUCCESS

    def test_single_task_node_type_unknown_raises(self):
        node = WorkflowNode(
            node_id="bad",
            node_type="unknown_type",
            label="Bad",
        )
        wf = _make_definition({"bad": node}, entry="bad")
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert not result.success


class TestSequentialTasks:
    """Test executing tasks in sequence via edges."""

    def test_two_tasks_in_order(self):
        nodes = {
            "task_a": _simple_task("task_a"),
            "task_b": _simple_task("task_b"),
        }
        nodes["task_a"].edges = [NodeEdge(target_node_id="task_b")]
        wf = _make_definition(nodes, entry="task_a", exits=["task_b"])
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert result.success
        assert ctx.get_node_result("task_a").status == NodeStatus.SUCCESS
        assert ctx.get_node_result("task_b").status == NodeStatus.SUCCESS

    def test_three_tasks_chain(self):
        nodes = {
            "a": _simple_task("a"),
            "b": _simple_task("b"),
            "c": _simple_task("c"),
        }
        nodes["a"].edges = [NodeEdge(target_node_id="b")]
        nodes["b"].edges = [NodeEdge(target_node_id="c")]
        wf = _make_definition(nodes, entry="a", exits=["c"])
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert result.success
        for nid in ("a", "b", "c"):
            assert ctx.get_node_result(nid).status == NodeStatus.SUCCESS


class TestParallelSequenceNodes:
    """Test PARALLEL and SEQUENCE node scheduling."""

    def test_parallel_schedules_children(self):
        nodes = {
            "par": WorkflowNode(
                node_id="par",
                node_type=NodeType.PARALLEL,
                label="Parallel",
                children=["t1", "t2"],
            ),
            "t1": _simple_task("t1"),
            "t2": _simple_task("t2"),
        }
        wf = _make_definition(nodes, entry="par", exits=["t1", "t2"])
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert result.success
        assert ctx.get_node_result("t1").status == NodeStatus.SUCCESS
        assert ctx.get_node_result("t2").status == NodeStatus.SUCCESS

    def test_sequence_schedules_children_in_order(self):
        nodes = {
            "seq": WorkflowNode(
                node_id="seq",
                node_type=NodeType.SEQUENCE,
                label="Sequence",
                children=["s1", "s2", "s3"],
            ),
            "s1": _simple_task("s1"),
            "s2": _simple_task("s2"),
            "s3": _simple_task("s3"),
        }
        wf = _make_definition(nodes, entry="seq", exits=["s1", "s2", "s3"])
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert result.success
        for nid in ("s1", "s2", "s3"):
            assert ctx.get_node_result(nid).status == NodeStatus.SUCCESS


class TestIfNode:
    """Test IF node conditional branching."""

    def test_if_true_branch(self):
        nodes = {
            "if1": WorkflowNode(
                node_id="if1",
                node_type=NodeType.IF,
                label="Decision",
                condition=Condition("variables.get('go', False)"),
                true_branch=["yes_task"],
                false_branch=["no_task"],
            ),
            "yes_task": _simple_task("yes_task"),
            "no_task": _simple_task("no_task"),
        }
        wf = _make_definition(nodes, entry="if1", exits=["yes_task", "no_task"])
        ctx = _make_context(variables={"go": True})
        sm = WorkflowStateMachine(wf, ctx)
        sm.execute()

        # IF node itself succeeds (schedules its branch)
        assert ctx.get_node_result("if1").status == NodeStatus.SUCCESS
        assert ctx.get_node_result("yes_task").status == NodeStatus.SUCCESS
        # no_task should NOT be in node_results (never scheduled)
        assert ctx.get_node_result("no_task") is None

    def test_if_false_branch(self):
        nodes = {
            "if1": WorkflowNode(
                node_id="if1",
                node_type=NodeType.IF,
                label="Decision",
                condition=Condition("variables.get('go', False)"),
                true_branch=["yes_task"],
                false_branch=["no_task"],
            ),
            "yes_task": _simple_task("yes_task"),
            "no_task": _simple_task("no_task"),
        }
        wf = _make_definition(nodes, entry="if1", exits=["yes_task", "no_task"])
        ctx = _make_context(variables={"go": False})
        sm = WorkflowStateMachine(wf, ctx)
        sm.execute()

        # IF node itself succeeds
        assert ctx.get_node_result("if1").status == NodeStatus.SUCCESS
        assert ctx.get_node_result("no_task").status == NodeStatus.SUCCESS
        assert ctx.get_node_result("yes_task") is None

    def test_if_no_condition_raises(self):
        nodes = {
            "if1": WorkflowNode(
                node_id="if1",
                node_type=NodeType.IF,
                label="Bad IF",
                true_branch=["t1"],
            ),
            "t1": _simple_task("t1"),
        }
        wf = _make_definition(nodes, entry="if1")
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert not result.success


class TestWhileLoop:
    """Test WHILE loop execution with continuation-based looping."""

    def test_while_loop_multiple_iterations(self):
        """WHILE loop should iterate multiple times."""
        nodes = {
            "loop": WorkflowNode(
                node_id="loop",
                node_type=NodeType.WHILE,
                label="Count to 3",
                loop_condition=Condition("iteration < 3"),
                loop_body=["counter"],
                max_iterations=10,
            ),
            "counter": _simple_task("counter"),
        }
        wf = _make_definition(nodes, entry="loop", exits=["loop"])
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert result.success
        loop_result = ctx.get_node_result("loop")
        assert loop_result.status == NodeStatus.SUCCESS
        assert loop_result.outputs["iterations"] == 3
        assert loop_result.outputs["completed"] is True

    def test_while_loop_max_iterations_safety(self):
        """WHILE loop should stop at max_iterations."""
        nodes = {
            "loop": WorkflowNode(
                node_id="loop",
                node_type=NodeType.WHILE,
                label="Infinite-ish",
                loop_condition=Condition("True"),  # Always true
                loop_body=["body"],
                max_iterations=3,
            ),
            "body": _simple_task("body"),
        }
        wf = _make_definition(nodes, entry="loop", exits=["loop"])
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert result.success  # max_iterations is a safety, not failure
        loop_result = ctx.get_node_result("loop")
        assert loop_result.outputs["iterations"] == 3
        assert loop_result.outputs["completed"] is False

    def test_while_loop_zero_iterations(self):
        """WHILE loop with false condition from start — body never executes."""
        nodes = {
            "loop": WorkflowNode(
                node_id="loop",
                node_type=NodeType.WHILE,
                label="Never loops",
                loop_condition=Condition("variables.get('should_loop', False)"),
                loop_body=["body"],
                max_iterations=10,
            ),
            "body": _simple_task("body"),
        }
        wf = _make_definition(nodes, entry="loop", exits=["loop"])
        ctx = _make_context(variables={"should_loop": False})
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert result.success
        loop_result = ctx.get_node_result("loop")
        assert loop_result.outputs["iterations"] == 0
        assert loop_result.outputs["completed"] is True
        # Body should never have executed
        assert ctx.get_node_result("body") is None

    def test_while_loop_with_successor(self):
        """WHILE loop followed by another task."""
        nodes = {
            "loop": WorkflowNode(
                node_id="loop",
                node_type=NodeType.WHILE,
                label="Count",
                loop_condition=Condition("iteration < 2"),
                loop_body=["body"],
                max_iterations=10,
                edges=[NodeEdge(target_node_id="after")],
            ),
            "body": _simple_task("body"),
            "after": _simple_task("after"),
        }
        wf = _make_definition(nodes, entry="loop", exits=["after"])
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert result.success
        assert ctx.get_node_result("loop").outputs["iterations"] == 2
        assert ctx.get_node_result("after").status == NodeStatus.SUCCESS


class TestForEachLoop:
    """Test FOR_EACH loop execution."""

    def test_for_each_all_elements(self):
        """FOR_EACH should iterate over all elements."""
        nodes = {
            "foreach": WorkflowNode(
                node_id="foreach",
                node_type=NodeType.FOR_EACH,
                label="Process items",
                collection_expression="variables['items']",
                element_variable="item",
                index_variable="idx",
                loop_body=["process"],
                max_iterations=100,
            ),
            "process": _simple_task("process"),
        }
        wf = _make_definition(nodes, entry="foreach", exits=["foreach"])
        ctx = _make_context(variables={"items": [10, 20, 30]})
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert result.success
        fe_result = ctx.get_node_result("foreach")
        assert fe_result.outputs["iterations"] == 3
        assert fe_result.outputs["collection_size"] == 3

    def test_for_each_empty_collection(self):
        """FOR_EACH with empty collection — body never executes."""
        nodes = {
            "foreach": WorkflowNode(
                node_id="foreach",
                node_type=NodeType.FOR_EACH,
                label="Empty",
                collection_expression="variables['items']",
                element_variable="item",
                index_variable="idx",
                loop_body=["process"],
            ),
            "process": _simple_task("process"),
        }
        wf = _make_definition(nodes, entry="foreach", exits=["foreach"])
        ctx = _make_context(variables={"items": []})
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert result.success
        fe_result = ctx.get_node_result("foreach")
        assert fe_result.outputs["iterations"] == 0
        assert ctx.get_node_result("process") is None

    def test_for_each_variables_set(self):
        """FOR_EACH should set element and index variables."""
        nodes = {
            "foreach": WorkflowNode(
                node_id="foreach",
                node_type=NodeType.FOR_EACH,
                label="Collect",
                collection_expression="variables['items']",
                element_variable="item",
                index_variable="idx",
                loop_body=["capture"],
            ),
            "capture": _simple_task("capture"),
        }
        wf = _make_definition(nodes, entry="foreach", exits=["foreach"])
        ctx = _make_context(variables={"items": ["a", "b", "c"]})
        sm = WorkflowStateMachine(wf, ctx)

        # Observe iteration starts to verify variables
        iteration_data = []
        def observer(event):
            if event.event_type == ExecutionEventType.LOOP_ITERATION_START:
                iteration_data.append(event.data)

        sm.observers.append(observer)
        result = sm.execute()

        assert result.success
        assert len(iteration_data) == 3
        assert iteration_data[0]["index"] == 0
        assert iteration_data[2]["index"] == 2

    def test_for_each_with_successor(self):
        """FOR_EACH followed by another task."""
        nodes = {
            "foreach": WorkflowNode(
                node_id="foreach",
                node_type=NodeType.FOR_EACH,
                label="Loop",
                collection_expression="variables['items']",
                element_variable="item",
                index_variable="idx",
                loop_body=["body"],
                edges=[NodeEdge(target_node_id="after")],
            ),
            "body": _simple_task("body"),
            "after": _simple_task("after"),
        }
        wf = _make_definition(nodes, entry="foreach", exits=["after"])
        ctx = _make_context(variables={"items": [1, 2]})
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert result.success
        assert ctx.get_node_result("after").status == NodeStatus.SUCCESS


class TestTryCatch:
    """Test TRY_CATCH error handling."""

    def test_try_catch_no_error(self):
        """TRY_CATCH with no error — catch handler skipped."""
        nodes = {
            "tc": WorkflowNode(
                node_id="tc",
                node_type=NodeType.TRY_CATCH,
                label="Safe",
                try_body=["safe_task"],
                catch_handlers=[
                    NodeEdge(target_node_id="handler", edge_type=EdgeType.UNCONDITIONAL)
                ],
            ),
            "safe_task": _simple_task("safe_task"),
            "handler": _simple_task("handler"),
        }
        wf = _make_definition(nodes, entry="tc", exits=["tc"])
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert result.success
        assert ctx.get_node_result("safe_task").status == NodeStatus.SUCCESS
        # handler should NOT run
        assert ctx.get_node_result("handler") is None
        tc_result = ctx.get_node_result("tc")
        assert tc_result.outputs.get("exception_caught") is False

    def test_try_catch_catches_error(self):
        """TRY_CATCH should catch errors from try body."""
        # Create a task node that raises
        failing_task = WorkflowNode(
            node_id="failing",
            node_type=NodeType.TASK,
            label="Failing task",
            task_id=None,  # This will cause ExecutionError
        )
        nodes = {
            "tc": WorkflowNode(
                node_id="tc",
                node_type=NodeType.TRY_CATCH,
                label="Safe",
                try_body=["failing"],
                catch_handlers=[
                    NodeEdge(target_node_id="handler", edge_type=EdgeType.UNCONDITIONAL)
                ],
            ),
            "failing": failing_task,
            "handler": _simple_task("handler"),
        }
        wf = _make_definition(nodes, entry="tc", exits=["tc"])
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        # Workflow should succeed because exception was caught
        assert result.success
        assert ctx.get_node_result("handler").status == NodeStatus.SUCCESS
        tc_result = ctx.get_node_result("tc")
        assert tc_result.outputs.get("exception_caught") is True

    def test_error_propagation_without_try_catch(self):
        """Error without TRY_CATCH should propagate and fail workflow."""
        failing = WorkflowNode(
            node_id="fail",
            node_type=NodeType.TASK,
            label="Fail",
            task_id=None,
        )
        nodes = {"fail": failing}
        wf = _make_definition(nodes, entry="fail")
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        assert not result.success
        assert result.error is not None


class TestCompensation:
    """Test compensation actions on failure."""

    def test_compensation_triggered_on_failure(self):
        """Compensation should fire when a node fails."""
        failing = WorkflowNode(
            node_id="risky",
            node_type=NodeType.TASK,
            label="Risky",
            task_id=None,  # Will fail
            compensations=[
                CompensationAction(
                    action_node_id="comp_task",
                    trigger_on=["failed"],
                )
            ],
        )
        nodes = {
            "risky": failing,
            "comp_task": _simple_task("comp_task"),
        }
        wf = _make_definition(nodes, entry="risky")
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        # Workflow fails (compensation doesn't fix the error)
        assert not result.success
        # But compensation task should have executed
        assert ctx.get_node_result("comp_task").status == NodeStatus.SUCCESS


class TestStateMachineEvents:
    """Test event emission during execution."""

    def test_workflow_started_and_completed_events(self):
        nodes = {"t": _simple_task("t")}
        wf = _make_definition(nodes, entry="t", exits=["t"])
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        event_types = [e.event_type for e in result.events]
        assert ExecutionEventType.WORKFLOW_STARTED in event_types
        assert ExecutionEventType.WORKFLOW_COMPLETED in event_types

    def test_node_started_and_completed_events(self):
        nodes = {"t": _simple_task("t")}
        wf = _make_definition(nodes, entry="t", exits=["t"])
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        event_types = [e.event_type for e in result.events]
        assert ExecutionEventType.NODE_STARTED in event_types
        assert ExecutionEventType.NODE_COMPLETED in event_types

    def test_observer_receives_events(self):
        received = []
        nodes = {"t": _simple_task("t")}
        wf = _make_definition(nodes, entry="t", exits=["t"])
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx, observers=[received.append])
        sm.execute()

        assert len(received) > 0
        assert any(e.event_type == ExecutionEventType.NODE_STARTED for e in received)

    def test_observer_error_does_not_break_execution(self):
        def bad_observer(event):
            raise RuntimeError("Observer broken!")

        nodes = {"t": _simple_task("t")}
        wf = _make_definition(nodes, entry="t", exits=["t"])
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx, observers=[bad_observer])
        result = sm.execute()

        assert result.success


class TestExecutionResult:
    """Test ExecutionResult serialization."""

    def test_to_dict(self):
        nodes = {"t": _simple_task("t")}
        wf = _make_definition(nodes, entry="t", exits=["t"])
        ctx = _make_context()
        sm = WorkflowStateMachine(wf, ctx)
        result = sm.execute()

        d = result.to_dict()
        assert d["success"] is True
        assert d["workflow_id"] == "test_wf"
        assert "context" in d
        assert "events" in d
