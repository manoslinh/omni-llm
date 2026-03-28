"""
Workflow definition for P2-15: Workflow Orchestration.

Defines the complete workflow graph with conditional control flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .nodes import EdgeType, NodeEdge, NodeType, WorkflowNode


@dataclass
class WorkflowDefinition:
    """
    Complete workflow definition with conditional control flow.

    This is the P2-15 equivalent of P2-14's WorkflowPlan. It adds
    support for conditional branches, loops, error handling, and
    compensation actions.

    Backward compatibility: Can be constructed from a P2-14 WorkflowPlan
    (all steps become TASK nodes with UNCONDITIONAL edges).
    """

    workflow_id: str
    name: str
    nodes: dict[str, WorkflowNode] = field(default_factory=dict)
    entry_node_id: str = ""  # First node to execute
    exit_node_ids: list[str] = field(default_factory=list)  # Terminal nodes
    variables: dict[str, Any] = field(
        default_factory=dict
    )  # Initial workflow variables
    description: str = ""
    version: str = "1.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── P2-14 backward compatibility ──────────────────────────

    @classmethod
    def from_plan(cls, plan: Any) -> WorkflowDefinition:
        """
        Convert a P2-14 WorkflowPlan to a P2-15 WorkflowDefinition.

        Each WorkflowStep becomes a TASK node. Dependencies become edges.
        Steps with no dependencies form the entry points.
        """
        from .nodes import EdgeType, NodeEdge, ResourceConstraint

        workflow_id = getattr(plan, "plan_id", "converted-plan")
        name = getattr(plan, "task_graph_name", "Converted Workflow")
        steps = getattr(plan, "steps", [])

        if not steps:
            return cls(workflow_id=workflow_id, name=name, nodes={})

        nodes: dict[str, WorkflowNode] = {}
        step_map: dict[str, Any] = {}

        # Index steps
        for step in steps:
            sid = getattr(step, "step_id", getattr(step, "task_id", f"step_{len(step_map)}"))
            step_map[sid] = step

        # Create TASK nodes
        for sid, step in step_map.items():
            task_id = getattr(step, "task_id", sid)
            description = getattr(step, "description", "")
            agent_id = getattr(step, "agent_id", None)
            priority = getattr(step, "priority", 0)
            metadata = getattr(step, "metadata", {})

            nodes[sid] = WorkflowNode(
                node_id=sid,
                node_type=NodeType.TASK,
                label=description or sid,
                task_id=task_id,
                agent_id=agent_id,
                resource=ResourceConstraint(priority=priority),
                metadata=metadata,
            )

        # Build edges from dependencies
        for sid, step in step_map.items():
            deps = getattr(step, "dependencies", [])
            for dep_id in deps:
                if dep_id in nodes:
                    nodes[dep_id].edges.append(
                        NodeEdge(target_node_id=sid, edge_type=EdgeType.UNCONDITIONAL)
                    )

        # Entry/exit detection
        all_targets: set[str] = set()
        for node in nodes.values():
            for edge in node.edges:
                all_targets.add(edge.target_node_id)

        entry_nodes = [nid for nid in nodes if nid not in all_targets]
        exit_nodes = [nid for nid in nodes if not nodes[nid].edges]

        if len(entry_nodes) == 1:
            entry_node_id = entry_nodes[0]
        elif len(entry_nodes) > 1:
            entry_node_id = "_entry"
            nodes[entry_node_id] = WorkflowNode(
                node_id="_entry",
                node_type=NodeType.PARALLEL,
                label="Entry (fan-out)",
                children=entry_nodes,
            )
            for eid in entry_nodes:
                nodes[entry_node_id].edges.append(
                    NodeEdge(target_node_id=eid, edge_type=EdgeType.UNCONDITIONAL)
                )
        else:
            entry_node_id = ""

        return cls(
            workflow_id=workflow_id,
            name=name,
            nodes=nodes,
            entry_node_id=entry_node_id,
            exit_node_ids=exit_nodes,
            description=getattr(plan, "description", f"Converted from P2-14 plan '{workflow_id}'"),
            metadata=getattr(plan, "metadata", {}),
        )

    # ── Navigation ─────────────────────────────────────────────

    def get_node(self, node_id: str) -> WorkflowNode:
        """Get a node by ID."""
        if node_id not in self.nodes:
            raise KeyError(f"Node '{node_id}' not found in workflow '{self.name}'")
        return self.nodes[node_id]

    def get_successors(self, node_id: str) -> list[str]:
        """Get all successor node IDs for a given node."""
        node = self.get_node(node_id)
        return [edge.target_node_id for edge in node.edges]

    def get_predecessors(self, node_id: str) -> list[str]:
        """Get all predecessor node IDs for a given node."""
        predecessors: list[str] = []
        for pred_id, pred_node in self.nodes.items():
            for edge in pred_node.edges:
                if edge.target_node_id == node_id:
                    predecessors.append(pred_id)
        return predecessors

    # ── Validation ─────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Validate the workflow definition. Returns list of issues."""
        issues: list[str] = []

        # Check entry node exists
        if self.entry_node_id and self.entry_node_id not in self.nodes:
            issues.append(f"Entry node '{self.entry_node_id}' not found in nodes")

        # Check exit nodes exist
        for exit_id in self.exit_node_ids:
            if exit_id not in self.nodes:
                issues.append(f"Exit node '{exit_id}' not found in nodes")

        # Validate each node
        for node_id, node in self.nodes.items():
            issues.extend(node.validate())

            # Check that edges point to valid nodes
            for edge in node.edges:
                if edge.target_node_id not in self.nodes:
                    issues.append(
                        f"Node '{node_id}': edge points to non-existent node '{edge.target_node_id}'"
                    )

            # Check that child nodes exist
            for child_id in node.children:
                if child_id not in self.nodes:
                    issues.append(
                        f"Node '{node_id}': child '{child_id}' not found in nodes"
                    )

            # Check that branch nodes exist
            for branch_id in node.true_branch + node.false_branch:
                if branch_id not in self.nodes:
                    issues.append(
                        f"Node '{node_id}': branch node '{branch_id}' not found in nodes"
                    )

            # Check that loop body nodes exist
            for body_id in node.loop_body:
                if body_id not in self.nodes:
                    issues.append(
                        f"Node '{node_id}': loop body node '{body_id}' not found in nodes"
                    )

            # Check that try/catch/finally nodes exist
            for try_id in node.try_body:
                if try_id not in self.nodes:
                    issues.append(
                        f"Node '{node_id}': try body node '{try_id}' not found in nodes"
                    )
            for finally_id in node.finally_body:
                if finally_id not in self.nodes:
                    issues.append(
                        f"Node '{node_id}': finally body node '{finally_id}' not found in nodes"
                    )
            for edge in node.catch_handlers:
                if edge.target_node_id not in self.nodes:
                    issues.append(
                        f"Node '{node_id}': catch handler node '{edge.target_node_id}' not found in nodes"
                    )

        # Check for cycles (basic check)
        visited: set[str] = set()
        stack: set[str] = set()

        def dfs(current: str) -> bool:
            if current in stack:
                return True  # Cycle detected
            if current in visited:
                return False

            # Check if node exists
            if current not in self.nodes:
                return False  # Already reported as issue, skip traversal

            visited.add(current)
            stack.add(current)

            node = self.get_node(current)
            for edge in node.edges:
                if dfs(edge.target_node_id):
                    return True
            for child_id in node.children:
                if dfs(child_id):
                    return True
            for branch_id in node.true_branch + node.false_branch:
                if dfs(branch_id):
                    return True
            for body_id in node.loop_body:
                if dfs(body_id):
                    return True
            for try_id in node.try_body:
                if dfs(try_id):
                    return True
            for finally_id in node.finally_body:
                if dfs(finally_id):
                    return True
            for edge in node.catch_handlers:
                if dfs(edge.target_node_id):
                    return True

            stack.remove(current)
            return False

        for node_id in self.nodes:
            if node_id not in visited:
                if dfs(node_id):
                    issues.append("Cycle detected in workflow graph")

        return issues

    # ── Serialization ──────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Convert workflow definition to dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "nodes": {
                node_id: self._node_to_dict(node)
                for node_id, node in self.nodes.items()
            },
            "entry_node_id": self.entry_node_id,
            "exit_node_ids": self.exit_node_ids,
            "variables": self.variables,
            "description": self.description,
            "version": self.version,
            "metadata": self.metadata,
        }

    def _node_to_dict(self, node: WorkflowNode) -> dict[str, Any]:
        """Convert a node to dictionary."""
        return {
            "node_id": node.node_id,
            "node_type": node.node_type.value,
            "label": node.label,
            "task_id": node.task_id,
            "agent_id": node.agent_id,
            "children": node.children,
            "condition": {
                "expression": node.condition.expression,
                "description": node.condition.description,
            }
            if node.condition
            else None,
            "true_branch": node.true_branch,
            "false_branch": node.false_branch,
            "loop_condition": {
                "expression": node.loop_condition.expression,
                "description": node.loop_condition.description,
            }
            if node.loop_condition
            else None,
            "loop_body": node.loop_body,
            "max_iterations": node.max_iterations,
            "iteration_variable": node.iteration_variable,
            "collection_expression": node.collection_expression,
            "element_variable": node.element_variable,
            "index_variable": node.index_variable,
            "try_body": node.try_body,
            "catch_handlers": [
                {
                    "target_node_id": edge.target_node_id,
                    "edge_type": edge.edge_type.value,
                    "condition": {
                        "expression": edge.condition.expression,
                        "description": edge.condition.description,
                    }
                    if edge.condition
                    else None,
                    "priority": edge.priority,
                }
                for edge in node.catch_handlers
            ],
            "finally_body": node.finally_body,
            "edges": [
                {
                    "target_node_id": edge.target_node_id,
                    "edge_type": edge.edge_type.value,
                    "condition": {
                        "expression": edge.condition.expression,
                        "description": edge.condition.description,
                    }
                    if edge.condition
                    else None,
                    "priority": edge.priority,
                }
                for edge in node.edges
            ],
            "resource": {
                "max_concurrent_tasks": node.resource.max_concurrent_tasks,
                "max_tokens": node.resource.max_tokens,
                "max_cost": node.resource.max_cost,
                "timeout_seconds": node.resource.timeout_seconds,
                "priority": node.resource.priority,
            },
            "compensations": [
                {
                    "action_node_id": comp.action_node_id,
                    "trigger_on": comp.trigger_on,
                    "description": comp.description,
                }
                for comp in node.compensations
            ],
            "metadata": node.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowDefinition:
        """Create workflow definition from dictionary."""
        nodes: dict[str, WorkflowNode] = {}

        # First create all nodes without complex references
        for node_id, node_data in data.get("nodes", {}).items():
            nodes[node_id] = cls._node_from_dict(node_data)

        return cls(
            workflow_id=data["workflow_id"],
            name=data["name"],
            nodes=nodes,
            entry_node_id=data.get("entry_node_id", ""),
            exit_node_ids=data.get("exit_node_ids", []),
            variables=data.get("variables", {}),
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def _node_from_dict(cls, data: dict[str, Any]) -> WorkflowNode:
        """Create a node from dictionary."""
        from .nodes import CompensationAction, Condition, ResourceConstraint

        # Extract condition if present
        condition_data = data.get("condition")
        condition = None
        if condition_data:
            condition = Condition(
                expression=condition_data["expression"],
                description=condition_data.get("description", ""),
            )

        # Extract loop condition if present
        loop_condition_data = data.get("loop_condition")
        loop_condition = None
        if loop_condition_data:
            loop_condition = Condition(
                expression=loop_condition_data["expression"],
                description=loop_condition_data.get("description", ""),
            )

        # Extract edges
        edges = []
        for edge_data in data.get("edges", []):
            condition_data = edge_data.get("condition")
            condition = None
            if condition_data:
                condition = Condition(
                    expression=condition_data["expression"],
                    description=condition_data.get("description", ""),
                )
            edges.append(
                NodeEdge(
                    target_node_id=edge_data["target_node_id"],
                    edge_type=EdgeType(edge_data["edge_type"]),
                    condition=condition,
                    priority=edge_data.get("priority", 0),
                )
            )

        # Extract catch handlers
        catch_handlers = []
        for handler_data in data.get("catch_handlers", []):
            condition_data = handler_data.get("condition")
            condition = None
            if condition_data:
                condition = Condition(
                    expression=condition_data["expression"],
                    description=condition_data.get("description", ""),
                )
            catch_handlers.append(
                NodeEdge(
                    target_node_id=handler_data["target_node_id"],
                    edge_type=EdgeType(handler_data["edge_type"]),
                    condition=condition,
                    priority=handler_data.get("priority", 0),
                )
            )

        # Extract resource constraint
        resource_data = data.get("resource", {})
        resource = ResourceConstraint(
            max_concurrent_tasks=resource_data.get("max_concurrent_tasks"),
            max_tokens=resource_data.get("max_tokens"),
            max_cost=resource_data.get("max_cost"),
            timeout_seconds=resource_data.get("timeout_seconds"),
            priority=resource_data.get("priority", 0),
        )

        # Extract compensations
        compensations = []
        for comp_data in data.get("compensations", []):
            compensations.append(
                CompensationAction(
                    action_node_id=comp_data["action_node_id"],
                    trigger_on=comp_data.get("trigger_on", ["FAILED"]),
                    description=comp_data.get("description", ""),
                )
            )

        return WorkflowNode(
            node_id=data["node_id"],
            node_type=NodeType(data["node_type"]),
            label=data.get("label", ""),
            task_id=data.get("task_id"),
            agent_id=data.get("agent_id"),
            children=data.get("children", []),
            condition=condition,
            true_branch=data.get("true_branch", []),
            false_branch=data.get("false_branch", []),
            loop_condition=loop_condition,
            loop_body=data.get("loop_body", []),
            max_iterations=data.get("max_iterations", 10),
            iteration_variable=data.get("iteration_variable", "iteration"),
            collection_expression=data.get("collection_expression", ""),
            element_variable=data.get("element_variable", "element"),
            index_variable=data.get("index_variable", "index"),
            try_body=data.get("try_body", []),
            catch_handlers=catch_handlers,
            finally_body=data.get("finally_body", []),
            edges=edges,
            resource=resource,
            compensations=compensations,
            metadata=data.get("metadata", {}),
        )
