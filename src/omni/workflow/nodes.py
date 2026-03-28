"""
Workflow node definitions for P2-15: Workflow Orchestration.

Defines the node types, edges, conditions, and resource constraints
for the workflow definition language.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar


class NodeType(StrEnum):
    """Types of workflow nodes."""

    TASK = "task"  # Execute a single task (atomic work unit)
    PARALLEL = "parallel"  # Execute children concurrently
    SEQUENCE = "sequence"  # Execute children in order
    IF = "if"  # Conditional branch
    WHILE = "while"  # Loop while condition is true
    FOR_EACH = "for_each"  # Iterate over a collection
    TRY_CATCH = "try_catch"  # Error handling zone
    COMPENSATE = "compensate"  # Undo/rollback action
    SUB_WORKFLOW = "sub_workflow"  # Reference to another workflow template


class EdgeType(StrEnum):
    """Types of edges between nodes."""

    UNCONDITIONAL = "unconditional"  # Always follow this edge
    CONDITIONAL = "conditional"  # Follow if expression evaluates True
    ERROR = "error"  # Follow on exception
    COMPENSATION = "compensation"  # Follow for rollback


class ConditionEvaluationError(Exception):
    """Raised when a condition expression fails to evaluate."""

    pass


@dataclass
class Condition:
    """A condition expression evaluated at runtime.

    Conditions are Python expressions evaluated against a WorkflowContext.
    The expression must return a truthy value.

    Examples:
        Condition("result.success")
        Condition("result.outputs['score'] > 0.8")
        Condition("variables['attempt'] < 3")
        Condition("'error' not in result.outputs")
    """

    expression: str
    description: str = ""

    # Safe builtins for expression evaluation
    SAFE_BUILTINS: ClassVar[dict[str, Any]] = {
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "sorted": sorted,
        "sum": sum,
        "isinstance": isinstance,
        "True": True,
        "False": False,
        "None": None,
        "dict": dict,
        "list": list,
        "tuple": tuple,
        "set": set,
        "enumerate": enumerate,
        "zip": zip,
    }

    def evaluate(self, context: dict[str, Any]) -> bool:
        """Evaluate the condition against a context dict.

        Safety: Uses a restricted eval with no builtins except safe ones.
        Available variables: result, variables, node_results, iteration
        """
        try:
            return bool(
                eval(self.expression, {"__builtins__": self.SAFE_BUILTINS}, context)
            )
        except Exception as e:
            raise ConditionEvaluationError(
                f"Failed to evaluate condition '{self.expression}': {e}"
            ) from e


@dataclass
class NodeEdge:
    """An edge connecting two workflow nodes."""

    target_node_id: str
    edge_type: EdgeType = EdgeType.UNCONDITIONAL
    condition: Condition | None = None  # Required if edge_type == CONDITIONAL
    priority: int = 0  # Higher = checked first (for multiple conditional edges)

    def __post_init__(self) -> None:
        if self.edge_type == EdgeType.CONDITIONAL and self.condition is None:
            raise ValueError("Conditional edges require a Condition")


@dataclass
class ResourceConstraint:
    """Resource limits for a workflow node's execution."""

    max_concurrent_tasks: int | None = None  # Override global concurrency for this node
    max_tokens: int | None = None  # Token budget for this node (and children)
    max_cost: float | None = None  # Cost budget in USD
    timeout_seconds: float | None = None  # Per-node timeout (overrides global)
    priority: int = 0  # Scheduling priority (higher first)


@dataclass
class CompensationAction:
    """An action to execute when a preceding node fails."""

    action_node_id: str  # The task node to execute as compensation
    trigger_on: list[str] = field(default_factory=lambda: ["failed"])
    description: str = ""


@dataclass
class WorkflowNode:
    """A node in the workflow definition graph.

    Nodes are the building blocks of conditional workflows. Each node
    has a type that determines its control-flow behavior.

    Backward compatibility: A simple `NodeType.TASK` node maps directly
    to a P2-14 `WorkflowStep` with a single task.
    """

    node_id: str
    node_type: NodeType
    label: str = ""

    # For TASK nodes: the task to execute
    task_id: str | None = None
    agent_id: str | None = None  # Override P2-14 assignment

    # For PARALLEL/SEQUENCE nodes: child node IDs
    children: list[str] = field(default_factory=list)

    # For IF nodes: condition + branch targets
    condition: Condition | None = None
    true_branch: list[str] = field(default_factory=list)  # Nodes to execute if True
    false_branch: list[str] = field(default_factory=list)  # Nodes to execute if False

    # For WHILE nodes: loop condition + body
    loop_condition: Condition | None = None
    loop_body: list[str] = field(default_factory=list)
    max_iterations: int = 10  # Safety limit
    iteration_variable: str = "iteration"  # Exposed in context

    # For FOR_EACH: collection expression + body
    collection_expression: str = ""  # Evaluated to get iterable
    element_variable: str = "element"  # Current element variable
    index_variable: str = "index"  # Current index variable

    # For TRY_CATCH: try body + catch handlers
    try_body: list[str] = field(default_factory=list)
    catch_handlers: list[NodeEdge] = field(default_factory=list)  # Error-type → node
    finally_body: list[str] = field(default_factory=list)

    # Edges to successor nodes (after this node completes)
    edges: list[NodeEdge] = field(default_factory=list)

    # Resource constraints
    resource: ResourceConstraint = field(default_factory=ResourceConstraint)

    # Compensation actions (run on failure of this node)
    compensations: list[CompensationAction] = field(default_factory=list)

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── Convenience properties ──────────────────────────────────

    @property
    def is_control_flow(self) -> bool:
        """Whether this node is a control-flow node (not a task)."""
        return self.node_type in (
            NodeType.IF,
            NodeType.WHILE,
            NodeType.FOR_EACH,
            NodeType.TRY_CATCH,
            NodeType.PARALLEL,
            NodeType.SEQUENCE,
            NodeType.SUB_WORKFLOW,
        )

    @property
    def is_task(self) -> bool:
        """Whether this node executes an actual task."""
        return self.node_type == NodeType.TASK

    def validate(self) -> list[str]:
        """Validate node configuration. Returns list of issues."""
        issues: list[str] = []

        if self.node_type == NodeType.TASK and self.task_id is None:
            issues.append(f"Node '{self.node_id}': TASK type requires task_id")

        if self.node_type == NodeType.IF:
            if self.condition is None:
                issues.append(f"Node '{self.node_id}': IF type requires condition")
            if not self.true_branch:
                issues.append(
                    f"Node '{self.node_id}': IF type needs at least true_branch"
                )

        if self.node_type == NodeType.WHILE:
            if self.loop_condition is None:
                issues.append(f"Node '{self.node_id}': WHILE requires loop_condition")
            if not self.loop_body:
                issues.append(f"Node '{self.node_id}': WHILE requires loop_body")

        if self.node_type == NodeType.FOR_EACH:
            if not self.collection_expression:
                issues.append(
                    f"Node '{self.node_id}': FOR_EACH requires collection_expression"
                )
            if not self.loop_body:
                issues.append(f"Node '{self.node_id}': FOR_EACH requires loop_body")

        if self.node_type == NodeType.TRY_CATCH:
            if not self.try_body:
                issues.append(f"Node '{self.node_id}': TRY_CATCH requires try_body")

        for edge in self.edges:
            if edge.edge_type == EdgeType.CONDITIONAL and edge.condition is None:
                issues.append(
                    f"Node '{self.node_id}': conditional edge missing condition"
                )

        return issues
