"""
Tests for workflow nodes module.
"""

import pytest

from src.omni.workflow.nodes import (
    Condition,
    ConditionEvaluationError,
    EdgeType,
    NodeEdge,
    NodeType,
    ResourceConstraint,
    WorkflowNode,
)


class TestCondition:
    """Tests for Condition class."""

    def test_condition_creation(self):
        """Test creating a condition."""
        condition = Condition(
            expression="result.success",
            description="Check if result was successful",
        )
        assert condition.expression == "result.success"
        assert condition.description == "Check if result was successful"

    def test_condition_evaluation_success(self):
        """Test evaluating a condition successfully."""
        condition = Condition("variables['score'] > 0.8")
        context = {
            "variables": {"score": 0.9},
            "node_results": {},
            "iteration": 0,
            "resource": {},
        }
        assert condition.evaluate(context) is True

    def test_condition_evaluation_failure(self):
        """Test evaluating a condition that returns False."""
        condition = Condition("variables['score'] > 0.8")
        context = {
            "variables": {"score": 0.7},
            "node_results": {},
            "iteration": 0,
            "resource": {},
        }
        assert condition.evaluate(context) is False

    def test_condition_evaluation_error(self):
        """Test condition evaluation error."""
        condition = Condition("variables.missing > 0.8")
        context = {
            "variables": {"score": 0.9},
            "node_results": {},
            "iteration": 0,
            "resource": {},
        }
        with pytest.raises(ConditionEvaluationError):
            condition.evaluate(context)

    def test_condition_safe_builtins(self):
        """Test that condition evaluation has safe builtins."""
        condition = Condition("len(variables['items']) > 2")
        context = {
            "variables": {"items": [1, 2, 3, 4]},
            "node_results": {},
            "iteration": 0,
            "resource": {},
        }
        assert condition.evaluate(context) is True


class TestNodeEdge:
    """Tests for NodeEdge class."""

    def test_node_edge_creation(self):
        """Test creating a node edge."""
        edge = NodeEdge(
            target_node_id="next_node",
            edge_type=EdgeType.UNCONDITIONAL,
        )
        assert edge.target_node_id == "next_node"
        assert edge.edge_type == EdgeType.UNCONDITIONAL
        assert edge.condition is None
        assert edge.priority == 0

    def test_conditional_edge_creation(self):
        """Test creating a conditional edge."""
        condition = Condition("result.success")
        edge = NodeEdge(
            target_node_id="next_node",
            edge_type=EdgeType.CONDITIONAL,
            condition=condition,
            priority=1,
        )
        assert edge.edge_type == EdgeType.CONDITIONAL
        assert edge.condition == condition
        assert edge.priority == 1

    def test_conditional_edge_validation(self):
        """Test that conditional edges require a condition."""
        with pytest.raises(ValueError, match="Conditional edges require a Condition"):
            NodeEdge(
                target_node_id="next_node",
                edge_type=EdgeType.CONDITIONAL,
                condition=None,
            )


class TestResourceConstraint:
    """Tests for ResourceConstraint class."""

    def test_resource_constraint_creation(self):
        """Test creating a resource constraint."""
        constraint = ResourceConstraint(
            max_concurrent_tasks=3,
            max_tokens=5000,
            max_cost=1.5,
            timeout_seconds=300,
            priority=2,
        )
        assert constraint.max_concurrent_tasks == 3
        assert constraint.max_tokens == 5000
        assert constraint.max_cost == 1.5
        assert constraint.timeout_seconds == 300
        assert constraint.priority == 2

    def test_resource_constraint_defaults(self):
        """Test resource constraint with defaults."""
        constraint = ResourceConstraint()
        assert constraint.max_concurrent_tasks is None
        assert constraint.max_tokens is None
        assert constraint.max_cost is None
        assert constraint.timeout_seconds is None
        assert constraint.priority == 0


class TestWorkflowNode:
    """Tests for WorkflowNode class."""

    def test_task_node_creation(self):
        """Test creating a task node."""
        node = WorkflowNode(
            node_id="task_1",
            node_type=NodeType.TASK,
            label="Execute Task 1",
            task_id="task_001",
            agent_id="coder",
        )
        assert node.node_id == "task_1"
        assert node.node_type == NodeType.TASK
        assert node.label == "Execute Task 1"
        assert node.task_id == "task_001"
        assert node.agent_id == "coder"
        assert node.is_task is True
        assert node.is_control_flow is False

    def test_parallel_node_creation(self):
        """Test creating a parallel node."""
        node = WorkflowNode(
            node_id="parallel_1",
            node_type=NodeType.PARALLEL,
            label="Parallel Execution",
            children=["task_1", "task_2", "task_3"],
        )
        assert node.node_type == NodeType.PARALLEL
        assert node.children == ["task_1", "task_2", "task_3"]
        assert node.is_task is False
        assert node.is_control_flow is True

    def test_if_node_creation(self):
        """Test creating an IF node."""
        condition = Condition("variables['decision'] == 'yes'")
        node = WorkflowNode(
            node_id="decision_point",
            node_type=NodeType.IF,
            label="Make Decision",
            condition=condition,
            true_branch=["path_yes"],
            false_branch=["path_no"],
        )
        assert node.node_type == NodeType.IF
        assert node.condition == condition
        assert node.true_branch == ["path_yes"]
        assert node.false_branch == ["path_no"]

    def test_while_node_creation(self):
        """Test creating a WHILE node."""
        condition = Condition("iteration < 5")
        node = WorkflowNode(
            node_id="retry_loop",
            node_type=NodeType.WHILE,
            label="Retry Loop",
            loop_condition=condition,
            loop_body=["retry_task"],
            max_iterations=10,
            iteration_variable="attempt",
        )
        assert node.node_type == NodeType.WHILE
        assert node.loop_condition == condition
        assert node.loop_body == ["retry_task"]
        assert node.max_iterations == 10
        assert node.iteration_variable == "attempt"

    def test_for_each_node_creation(self):
        """Test creating a FOR_EACH node."""
        node = WorkflowNode(
            node_id="process_items",
            node_type=NodeType.FOR_EACH,
            label="Process Items",
            collection_expression="variables['items']",
            element_variable="item",
            index_variable="idx",
            loop_body=["process_item"],
        )
        assert node.node_type == NodeType.FOR_EACH
        assert node.collection_expression == "variables['items']"
        assert node.element_variable == "item"
        assert node.index_variable == "idx"
        assert node.loop_body == ["process_item"]

    def test_try_catch_node_creation(self):
        """Test creating a TRY_CATCH node."""
        node = WorkflowNode(
            node_id="safe_execution",
            node_type=NodeType.TRY_CATCH,
            label="Safe Execution",
            try_body=["risky_task"],
            catch_handlers=[
                NodeEdge(target_node_id="error_handler", edge_type=EdgeType.ERROR)
            ],
            finally_body=["cleanup"],
        )
        assert node.node_type == NodeType.TRY_CATCH
        assert node.try_body == ["risky_task"]
        assert len(node.catch_handlers) == 1
        assert node.catch_handlers[0].target_node_id == "error_handler"
        assert node.finally_body == ["cleanup"]

    def test_node_validation_task(self):
        """Test node validation for task nodes."""
        # Task node without task_id should fail validation
        node = WorkflowNode(
            node_id="invalid_task",
            node_type=NodeType.TASK,
        )
        issues = node.validate()
        assert "requires task_id" in issues[0]

        # Task node with task_id should pass validation
        node.task_id = "valid_task"
        issues = node.validate()
        assert len(issues) == 0

    def test_node_validation_if(self):
        """Test node validation for IF nodes."""
        # IF node without condition should fail validation
        node = WorkflowNode(
            node_id="invalid_if",
            node_type=NodeType.IF,
        )
        issues = node.validate()
        assert "requires condition" in issues[0]

        # IF node without true_branch should fail validation
        node.condition = Condition("True")
        issues = node.validate()
        assert "needs at least true_branch" in issues[0]

        # Valid IF node should pass validation
        node.true_branch = ["branch_task"]
        issues = node.validate()
        assert len(issues) == 0

    def test_node_validation_while(self):
        """Test node validation for WHILE nodes."""
        # WHILE node without loop_condition should fail validation
        node = WorkflowNode(
            node_id="invalid_while",
            node_type=NodeType.WHILE,
        )
        issues = node.validate()
        assert "requires loop_condition" in issues[0]

        # WHILE node without loop_body should fail validation
        node.loop_condition = Condition("True")
        issues = node.validate()
        assert "requires loop_body" in issues[0]

        # Valid WHILE node should pass validation
        node.loop_body = ["loop_task"]
        issues = node.validate()
        assert len(issues) == 0

    def test_node_validation_for_each(self):
        """Test node validation for FOR_EACH nodes."""
        # FOR_EACH node without collection_expression should fail validation
        node = WorkflowNode(
            node_id="invalid_for_each",
            node_type=NodeType.FOR_EACH,
        )
        issues = node.validate()
        assert "requires collection_expression" in issues[0]

        # FOR_EACH node without loop_body should fail validation
        node.collection_expression = "variables['items']"
        issues = node.validate()
        assert "requires loop_body" in issues[0]

        # Valid FOR_EACH node should pass validation
        node.loop_body = ["process_item"]
        issues = node.validate()
        assert len(issues) == 0

    def test_node_validation_try_catch(self):
        """Test node validation for TRY_CATCH nodes."""
        # TRY_CATCH node without try_body should fail validation
        node = WorkflowNode(
            node_id="invalid_try_catch",
            node_type=NodeType.TRY_CATCH,
        )
        issues = node.validate()
        assert "requires try_body" in issues[0]

        # Valid TRY_CATCH node should pass validation
        node.try_body = ["try_task"]
        issues = node.validate()
        assert len(issues) == 0

    def test_node_validation_conditional_edge(self):
        """Test node validation for conditional edges."""
        node = WorkflowNode(
            node_id="test_node",
            node_type=NodeType.TASK,
            task_id="test_task",
        )

        # We can't create a conditional edge without a condition due to validation in __post_init__
        # So we test that the edge creation itself validates
        with pytest.raises(ValueError, match="Conditional edges require a Condition"):
            NodeEdge(
                target_node_id="next_node",
                edge_type=EdgeType.CONDITIONAL,
                condition=None,
            )

        # Conditional edge with condition should pass validation
        condition = Condition("True")
        node.edges = [
            NodeEdge(
                target_node_id="next_node",
                edge_type=EdgeType.CONDITIONAL,
                condition=condition,
            )
        ]
        issues = node.validate()
        assert len(issues) == 0
