"""
Tests for workflow definition module.
"""

import pytest

from src.omni.workflow.definition import WorkflowDefinition
from src.omni.workflow.nodes import (
    Condition,
    EdgeType,
    NodeEdge,
    NodeType,
    WorkflowNode,
)


class TestWorkflowDefinition:
    """Tests for WorkflowDefinition class."""

    def test_workflow_definition_creation(self):
        """Test creating a workflow definition."""
        # Create some nodes
        nodes = {
            "start": WorkflowNode(
                node_id="start",
                node_type=NodeType.TASK,
                label="Start Task",
                task_id="task_001",
            ),
            "end": WorkflowNode(
                node_id="end",
                node_type=NodeType.TASK,
                label="End Task",
                task_id="task_002",
            ),
        }

        # Connect nodes
        nodes["start"].edges = [NodeEdge(target_node_id="end")]

        # Create workflow definition
        workflow = WorkflowDefinition(
            workflow_id="test_workflow",
            name="Test Workflow",
            nodes=nodes,
            entry_node_id="start",
            exit_node_ids=["end"],
            variables={"param": "value"},
            description="A test workflow",
            version="1.0",
            metadata={"author": "test"},
        )

        assert workflow.workflow_id == "test_workflow"
        assert workflow.name == "Test Workflow"
        assert len(workflow.nodes) == 2
        assert workflow.entry_node_id == "start"
        assert workflow.exit_node_ids == ["end"]
        assert workflow.variables == {"param": "value"}
        assert workflow.description == "A test workflow"
        assert workflow.version == "1.0"
        assert workflow.metadata == {"author": "test"}

    def test_get_node(self):
        """Test getting a node by ID."""
        nodes = {
            "task_1": WorkflowNode(
                node_id="task_1",
                node_type=NodeType.TASK,
                task_id="task_001",
            ),
        }

        workflow = WorkflowDefinition(
            workflow_id="test",
            name="Test",
            nodes=nodes,
        )

        node = workflow.get_node("task_1")
        assert node.node_id == "task_1"
        assert node.task_id == "task_001"

    def test_get_node_not_found(self):
        """Test getting a non-existent node."""
        workflow = WorkflowDefinition(
            workflow_id="test",
            name="Test",
            nodes={},
        )

        with pytest.raises(KeyError, match="not found"):
            workflow.get_node("missing")

    def test_get_successors(self):
        """Test getting successor nodes."""
        nodes = {
            "start": WorkflowNode(
                node_id="start",
                node_type=NodeType.TASK,
                task_id="task_001",
            ),
            "middle": WorkflowNode(
                node_id="middle",
                node_type=NodeType.TASK,
                task_id="task_002",
            ),
            "end": WorkflowNode(
                node_id="end",
                node_type=NodeType.TASK,
                task_id="task_003",
            ),
        }

        # Create a chain: start -> middle -> end
        nodes["start"].edges = [NodeEdge(target_node_id="middle")]
        nodes["middle"].edges = [NodeEdge(target_node_id="end")]

        workflow = WorkflowDefinition(
            workflow_id="test",
            name="Test",
            nodes=nodes,
        )

        assert workflow.get_successors("start") == ["middle"]
        assert workflow.get_successors("middle") == ["end"]
        assert workflow.get_successors("end") == []

    def test_get_predecessors(self):
        """Test getting predecessor nodes."""
        nodes = {
            "start": WorkflowNode(
                node_id="start",
                node_type=NodeType.TASK,
                task_id="task_001",
            ),
            "middle": WorkflowNode(
                node_id="middle",
                node_type=NodeType.TASK,
                task_id="task_002",
            ),
            "end": WorkflowNode(
                node_id="end",
                node_type=NodeType.TASK,
                task_id="task_003",
            ),
        }

        # Create a chain: start -> middle -> end
        nodes["start"].edges = [NodeEdge(target_node_id="middle")]
        nodes["middle"].edges = [NodeEdge(target_node_id="end")]

        workflow = WorkflowDefinition(
            workflow_id="test",
            name="Test",
            nodes=nodes,
        )

        assert workflow.get_predecessors("start") == []
        assert workflow.get_predecessors("middle") == ["start"]
        assert workflow.get_predecessors("end") == ["middle"]

    def test_validation_valid_workflow(self):
        """Test validation of a valid workflow."""
        nodes = {
            "start": WorkflowNode(
                node_id="start",
                node_type=NodeType.TASK,
                task_id="task_001",
            ),
            "end": WorkflowNode(
                node_id="end",
                node_type=NodeType.TASK,
                task_id="task_002",
            ),
        }

        nodes["start"].edges = [NodeEdge(target_node_id="end")]

        workflow = WorkflowDefinition(
            workflow_id="test",
            name="Test",
            nodes=nodes,
            entry_node_id="start",
            exit_node_ids=["end"],
        )

        issues = workflow.validate()
        assert len(issues) == 0

    def test_validation_missing_entry_node(self):
        """Test validation with missing entry node."""
        nodes = {
            "task": WorkflowNode(
                node_id="task",
                node_type=NodeType.TASK,
                task_id="task_001",
            ),
        }

        workflow = WorkflowDefinition(
            workflow_id="test",
            name="Test",
            nodes=nodes,
            entry_node_id="missing",  # Doesn't exist
        )

        issues = workflow.validate()
        assert "not found" in issues[0]

    def test_validation_missing_exit_node(self):
        """Test validation with missing exit node."""
        nodes = {
            "task": WorkflowNode(
                node_id="task",
                node_type=NodeType.TASK,
                task_id="task_001",
            ),
        }

        workflow = WorkflowDefinition(
            workflow_id="test",
            name="Test",
            nodes=nodes,
            exit_node_ids=["missing"],  # Doesn't exist
        )

        issues = workflow.validate()
        assert "not found" in issues[0]

    def test_validation_invalid_edge_target(self):
        """Test validation with edge pointing to non-existent node."""
        nodes = {
            "start": WorkflowNode(
                node_id="start",
                node_type=NodeType.TASK,
                task_id="task_001",
            ),
        }

        nodes["start"].edges = [NodeEdge(target_node_id="missing")]

        workflow = WorkflowDefinition(
            workflow_id="test",
            name="Test",
            nodes=nodes,
        )

        issues = workflow.validate()
        assert "points to non-existent node" in issues[0]

    def test_validation_invalid_child(self):
        """Test validation with non-existent child node."""
        nodes = {
            "parallel": WorkflowNode(
                node_id="parallel",
                node_type=NodeType.PARALLEL,
                children=["missing"],  # Doesn't exist
            ),
        }

        workflow = WorkflowDefinition(
            workflow_id="test",
            name="Test",
            nodes=nodes,
        )

        issues = workflow.validate()
        assert "child 'missing' not found" in issues[0]

    def test_validation_cycle_detection(self):
        """Test cycle detection in workflow graph."""
        nodes = {
            "a": WorkflowNode(
                node_id="a",
                node_type=NodeType.TASK,
                task_id="task_a",
            ),
            "b": WorkflowNode(
                node_id="b",
                node_type=NodeType.TASK,
                task_id="task_b",
            ),
        }

        # Create a cycle: a -> b -> a
        nodes["a"].edges = [NodeEdge(target_node_id="b")]
        nodes["b"].edges = [NodeEdge(target_node_id="a")]

        workflow = WorkflowDefinition(
            workflow_id="test",
            name="Test",
            nodes=nodes,
        )

        issues = workflow.validate()
        assert "Cycle detected" in issues[0]

    def test_serialization_roundtrip(self):
        """Test serialization and deserialization roundtrip."""
        # Create a workflow with various node types
        nodes = {
            "start": WorkflowNode(
                node_id="start",
                node_type=NodeType.TASK,
                label="Start Task",
                task_id="task_001",
                agent_id="coder",
                edges=[NodeEdge(target_node_id="end")],
            ),
            "if_node": WorkflowNode(
                node_id="if_node",
                node_type=NodeType.IF,
                label="Decision Point",
                condition=Condition("variables['choice'] == 'yes'"),
                true_branch=["yes_task"],
                false_branch=["no_task"],
            ),
            "end": WorkflowNode(
                node_id="end",
                node_type=NodeType.TASK,
                label="End Task",
                task_id="task_002",
            ),
        }

        original = WorkflowDefinition(
            workflow_id="test_workflow",
            name="Test Workflow",
            nodes=nodes,
            entry_node_id="start",
            exit_node_ids=["end"],
            variables={"choice": "yes"},
            description="Test workflow with serialization",
            version="1.0",
            metadata={"test": True},
        )

        # Serialize to dict
        data = original.to_dict()

        # Deserialize from dict
        restored = WorkflowDefinition.from_dict(data)

        # Check basic properties
        assert restored.workflow_id == original.workflow_id
        assert restored.name == original.name
        assert restored.entry_node_id == original.entry_node_id
        assert restored.exit_node_ids == original.exit_node_ids
        assert restored.variables == original.variables
        assert restored.description == original.description
        assert restored.version == original.version
        assert restored.metadata == original.metadata

        # Check nodes
        assert set(restored.nodes.keys()) == set(original.nodes.keys())

        # Check a specific node
        original_start = original.nodes["start"]
        restored_start = restored.nodes["start"]

        assert restored_start.node_id == original_start.node_id
        assert restored_start.node_type == original_start.node_type
        assert restored_start.label == original_start.label
        assert restored_start.task_id == original_start.task_id
        assert restored_start.agent_id == original_start.agent_id
        assert len(restored_start.edges) == len(original_start.edges)

        # Check edges
        if original_start.edges:
            assert (
                restored_start.edges[0].target_node_id
                == original_start.edges[0].target_node_id
            )

        # Check IF node condition
        original_if = original.nodes["if_node"]
        restored_if = restored.nodes["if_node"]

        assert restored_if.condition is not None
        assert original_if.condition is not None
        assert restored_if.condition.expression == original_if.condition.expression
        assert restored_if.true_branch == original_if.true_branch
        assert restored_if.false_branch == original_if.false_branch

    def test_from_dict_empty(self):
        """Test creating workflow definition from empty dictionary."""
        data = {
            "workflow_id": "test",
            "name": "Test",
            "nodes": {},
        }

        workflow = WorkflowDefinition.from_dict(data)
        assert workflow.workflow_id == "test"
        assert workflow.name == "Test"
        assert workflow.nodes == {}
        assert workflow.entry_node_id == ""
        assert workflow.exit_node_ids == []
        assert workflow.variables == {}
        assert workflow.description == ""
        assert workflow.version == "1.0"
        assert workflow.metadata == {}

    def test_from_dict_with_nodes(self):
        """Test creating workflow definition with nodes from dictionary."""
        data = {
            "workflow_id": "test",
            "name": "Test",
            "nodes": {
                "task_1": {
                    "node_id": "task_1",
                    "node_type": "task",
                    "label": "Task 1",
                    "task_id": "task_001",
                    "children": [],
                    "true_branch": [],
                    "false_branch": [],
                    "loop_body": [],
                    "try_body": [],
                    "catch_handlers": [],
                    "finally_body": [],
                    "edges": [
                        {
                            "target_node_id": "task_2",
                            "edge_type": "unconditional",
                            "priority": 0,
                        }
                    ],
                    "resource": {
                        "max_concurrent_tasks": None,
                        "max_tokens": None,
                        "max_cost": None,
                        "timeout_seconds": None,
                        "priority": 0,
                    },
                    "compensations": [],
                    "metadata": {},
                },
                "task_2": {
                    "node_id": "task_2",
                    "node_type": "task",
                    "label": "Task 2",
                    "task_id": "task_002",
                    "children": [],
                    "true_branch": [],
                    "false_branch": [],
                    "loop_body": [],
                    "try_body": [],
                    "catch_handlers": [],
                    "finally_body": [],
                    "edges": [],
                    "resource": {
                        "max_concurrent_tasks": None,
                        "max_tokens": None,
                        "max_cost": None,
                        "timeout_seconds": None,
                        "priority": 0,
                    },
                    "compensations": [],
                    "metadata": {},
                },
            },
            "entry_node_id": "task_1",
            "exit_node_ids": ["task_2"],
            "variables": {"param": "value"},
            "description": "Test workflow",
            "version": "1.0",
            "metadata": {"test": True},
        }

        workflow = WorkflowDefinition.from_dict(data)

        assert workflow.workflow_id == "test"
        assert workflow.name == "Test"
        assert len(workflow.nodes) == 2
        assert "task_1" in workflow.nodes
        assert "task_2" in workflow.nodes
        assert workflow.entry_node_id == "task_1"
        assert workflow.exit_node_ids == ["task_2"]
        assert workflow.variables == {"param": "value"}
        assert workflow.description == "Test workflow"
        assert workflow.version == "1.0"
        assert workflow.metadata == {"test": True}

        # Check node properties
        task1 = workflow.nodes["task_1"]
        assert task1.node_id == "task_1"
        assert task1.node_type == NodeType.TASK
        assert task1.label == "Task 1"
        assert task1.task_id == "task_001"
        assert len(task1.edges) == 1
        assert task1.edges[0].target_node_id == "task_2"
        assert task1.edges[0].edge_type == EdgeType.UNCONDITIONAL
