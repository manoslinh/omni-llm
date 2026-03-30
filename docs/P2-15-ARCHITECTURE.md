# P2-15: Workflow Orchestration — Architecture

**Date:** 2026-03-28
**Phase:** 2.4 — Advanced Orchestration & Multi-Agent Coordination
**Sprint:** P2-15

---

## 1. Problem Statement

P2-14 introduced the Multi-Agent Coordination Engine with agent matching, workflow planning, and parallel execution waves. However, its `WorkflowPlan` model is limited to **linear DAG execution** — sequential steps, parallel fan-out, and review chains. Real-world orchestration demands more:

- **Conditional branching:** "If the test task fails, run the debug task; otherwise, deploy."
- **Loops:** "Retry code generation until the linter passes, up to 5 iterations."
- **Iteration:** "For each file in the changeset, run a review task."
- **Error handling zones:** "Try the risky deployment, catch failures, run rollback."
- **Dynamic modification:** "Based on intermediate analysis, add new tasks mid-workflow."
- **Resource constraints:** "Don't run more than 2 LLM-heavy tasks simultaneously."
- **Reusable patterns:** "The analyze→implement→test→review pattern appears everywhere."

P2-15 extends the coordination engine with a **conditional workflow definition language** and a **state-machine execution engine** that supports complex control flow while maintaining backward compatibility with P2-14's simple workflows.

### Current Gap

```
P2-14 WorkflowPlan:  step-001 (parallel) → step-002 (review) → step-003
                     ↓                     ↓                  ↓
                     [task-A, task-B]      [review-A, review-B]  [task-C]

P2-15 Needs:        step-001 → IF(result.success) → step-002a (deploy)
                                           └─ELSE → step-002b (debug)
                                                           ↓
                                                    WHILE(lint_fails) → step-fix
                                                           ↓
                                                    TRY → step-deploy
                                                          CATCH → step-rollback
```

---

## 2. Design Goals

| Goal | Rationale |
|------|-----------|
| **Backward compatible** | P2-14 `WorkflowPlan` must work unmodified inside P2-15 |
| **Composable control flow** | IF/ELSE, WHILE, FOR_EACH, TRY/CATCH compose with existing parallel/sequential steps |
| **Python expressions** | Conditions are evaluated Python expressions, not a custom DSL |
| **Type-safe state passing** | Step outputs carry typed metadata accessible to downstream conditions |
| **Dynamic modification** | Workflows can insert/remove/reorder steps at runtime based on results |
| **Resource-aware** | Per-workflow quotas prevent runaway parallelism and API exhaustion |
| **Observable** | Every control-flow decision is logged and visible in P2-13 dashboards |
| **Template-based** | Common patterns are reusable, parameterized building blocks |

---

## 3. Existing Components (Integration Points)

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Omni-LLM Architecture                         │
│                                                                       │
│  ┌───────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
│  │ P2-08: Task   │───▶│ P2-09: Complexity│───▶│ P2-14: Coordina- │   │
│  │ Decomposition │    │ Analyzer         │    │ tion Engine      │   │
│  └───────────────┘    └──────────────────┘    └────────┬─────────┘   │
│                                                         │              │
│  ┌──────────────────────────────────────────────────────▼──────────┐  │
│  │              ★ P2-15: Workflow Orchestration ★                  │  │
│  │                                                                  │  │
│  │  ┌────────────┐  ┌─────────────┐  ┌──────────┐  ┌───────────┐ │  │
│  │  │ Workflow   │  │ Expression  │  │ Resource │  │ Workflow  │ │  │
│  │  │ Definition │  │ Evaluator   │  │ Manager  │  │ Templates │ │  │
│  │  │ Language   │  │             │  │          │  │           │ │  │
│  │  └────────────┘  └─────────────┘  └──────────┘  └───────────┘ │  │
│  │                                                                  │  │
│  │  ┌──────────────────────────────────────────────────────────┐   │  │
│  │  │              Execution State Machine                      │   │  │
│  │  │  (drives node transitions with full control flow)         │   │  │
│  │  └──────────────────────────────────────────────────────────┘   │  │
│  └──────────────────────────┬──────────────────────────────────────┘  │
│                              │                                        │
│         ┌────────────────────┼────────────────────┐                  │
│         ▼                    ▼                    ▼                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐           │
│  │ P2-11:       │    │ P2-12: Model │    │ P2-13:       │           │
│  │ Parallel     │    │ Router +     │    │ Observability│           │
│  │ Execution    │    │ LLM Executor │    │ + Dashboard  │           │
│  └──────────────┘    └──────────────┘    └──────────────┘           │
└──────────────────────────────────────────────────────────────────────┘
```

### Integration contracts (unchanged from P2-14):

| Component | Integration | What changes for P2-15 |
|-----------|-------------|----------------------|
| P2-08 TaskGraph | Input: `TaskGraph` → `WorkflowDefinition` | New: conditional edges added to `TaskGraph` |
| P2-09 ComplexityAnalyzer | Pre-execution: populates `Task.complexity` | No change |
| P2-11 ParallelEngine | Execution: consumes execution waves | New: executor receives per-node resource constraints |
| P2-12 LLM Executor | Task execution: `LLMTaskExecutor.execute()` | New: executor returns typed metadata for condition evaluation |
| P2-13 Observability | Events: `CoordinationObserver` protocol | New: workflow-level events (branch taken, loop iteration, retry) |
| P2-14 Coordination | Agent matching: `TaskMatcher` | No change — P2-15 reuses P2-14 assignments |

---

## 4. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Workflow Orchestration Engine                       │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │                    WorkflowDefinition                           │   │
│  │                                                                │   │
│  │   ┌─────────┐   ┌─────────┐   ┌──────────┐   ┌────────────┐  │   │
│  │   │  Task   │   │   If    │   │  While   │   │ TryCatch   │  │   │
│  │   │  Node   │   │  Node   │   │  Node    │   │  Node      │  │   │
│  │   └─────────┘   └─────────┘   └──────────┘   └────────────┘  │   │
│  │   ┌─────────┐   ┌─────────┐   ┌──────────┐                   │   │
│  │   │ForEach  │   │ Parallel│   │ Compensa-│                   │   │
│  │   │  Node   │   │  Node   │   │ tion Node│                   │   │
│  │   └─────────┘   └─────────┘   └──────────┘                   │   │
│  │                                                                │   │
│  │   Edges: unconditional, conditional, error, compensation       │   │
│  └────────────────────────────┬───────────────────────────────────┘   │
│                               │                                       │
│  ┌────────────────────────────▼───────────────────────────────────┐   │
│  │                   Execution State Machine                       │   │
│  │                                                                │   │
│  │   ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐ │   │
│  │   │ Evaluator│──▶│ Scheduler│──▶│ Executor │──▶│Post-proc│ │   │
│  │   │(conditions│   │(resource │    │ (P2-11   │    │(state   │ │   │
│  │   │ + routing)│   │ aware)   │    │  bridge) │    │ update) │ │   │
│  │   └─────────┘    └──────────┘    └──────────┘    └─────────┘ │   │
│  │                                                                │   │
│  │   ┌──────────────────────────────────────────────────────────┐ │   │
│  │   │              WorkflowContext (shared state)               │ │   │
│  │   │  • node_results: dict[node_id → NodeResult]              │ │   │
│  │   │  • variables: dict[str → Any] (user-defined state)       │ │   │
│  │   │  • iteration_counters: dict[node_id → int]               │ │   │
│  │   │  • resource_usage: ResourceSnapshot                      │ │   │
│  │   └──────────────────────────────────────────────────────────┘ │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │                    Resource Manager                             │   │
│  │  • Per-workflow concurrency quotas                             │   │
│  │  • API rate limit tracking                                     │   │
│  │  • Memory budget enforcement                                   │   │
│  │  • Priority-based scheduling                                   │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │                    Workflow Template Library                    │   │
│  │  • analyze-implement-test-review (default pipeline)            │   │
│  │  • parallel-review (fan-out review chain)                      │   │
│  │  • explore-plan-implement (codebase workflow)                  │   │
│  │  • User-defined templates                                      │   │
│  └────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 5. Component Design

### 5.1 Workflow Definition Language

The core abstraction extends P2-14's `WorkflowStep` with a node-based graph that supports control flow.

#### 5.1.1 Node Types

```python
# src/omni/workflow/nodes.py

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class NodeType(StrEnum):
    """Types of workflow nodes."""
    TASK = "task"              # Execute a single task (atomic work unit)
    PARALLEL = "parallel"      # Execute children concurrently
    SEQUENCE = "sequence"      # Execute children in order
    IF = "if"                  # Conditional branch
    WHILE = "while"            # Loop while condition is true
    FOR_EACH = "for_each"      # Iterate over a collection
    TRY_CATCH = "try_catch"    # Error handling zone
    COMPENSATE = "compensate"  # Undo/rollback action
    SUB_WORKFLOW = "sub_workflow"  # Reference to another workflow template


class EdgeType(StrEnum):
    """Types of edges between nodes."""
    UNCONDITIONAL = "unconditional"  # Always follow this edge
    CONDITIONAL = "conditional"      # Follow if expression evaluates True
    ERROR = "error"                  # Follow on exception
    COMPENSATION = "compensation"    # Follow for rollback


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

    def evaluate(self, context: dict[str, Any]) -> bool:
        """Evaluate the condition against a context dict.

        Safety: Uses a restricted eval with no builtins except safe ones.
        Available variables: result, variables, node_results, iteration
        """
        safe_builtins = {
            "len": len, "str": str, "int": int, "float": float,
            "bool": bool, "abs": abs, "min": min, "max": max,
            "round": round, "sorted": sorted, "sum": sum,
            "isinstance": isinstance, "True": True, "False": False,
            "None": None, "dict": dict, "list": list, "tuple": tuple,
            "set": set, "enumerate": enumerate, "zip": zip,
        }
        try:
            return bool(
                eval(self.expression, {"__builtins__": safe_builtins}, context)
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
    max_tokens: int | None = None            # Token budget for this node (and children)
    max_cost: float | None = None            # Cost budget in USD
    timeout_seconds: float | None = None     # Per-node timeout (overrides global)
    priority: int = 0                        # Scheduling priority (higher first)


@dataclass
class CompensationAction:
    """An action to execute when a preceding node fails."""
    action_node_id: str   # The task node to execute as compensation
    trigger_on: list[str] = field(default_factory=lambda: ["FAILED"])
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
    true_branch: list[str] = field(default_factory=list)   # Nodes to execute if True
    false_branch: list[str] = field(default_factory=list)  # Nodes to execute if False

    # For WHILE nodes: loop condition + body
    loop_condition: Condition | None = None
    loop_body: list[str] = field(default_factory=list)
    max_iterations: int = 10  # Safety limit
    iteration_variable: str = "iteration"  # Exposed in context

    # For FOR_EACH: collection expression + body
    collection_expression: str = ""  # Evaluated to get iterable
    element_variable: str = "element"  # Current element variable
    index_variable: str = "index"      # Current index variable

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
            NodeType.IF, NodeType.WHILE, NodeType.FOR_EACH,
            NodeType.TRY_CATCH, NodeType.PARALLEL, NodeType.SEQUENCE,
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
                issues.append(f"Node '{self.node_id}': IF type needs at least true_branch")

        if self.node_type == NodeType.WHILE:
            if self.loop_condition is None:
                issues.append(f"Node '{self.node_id}': WHILE requires loop_condition")
            if not self.loop_body:
                issues.append(f"Node '{self.node_id}': WHILE requires loop_body")

        if self.node_type == NodeType.FOR_EACH:
            if not self.collection_expression:
                issues.append(f"Node '{self.node_id}': FOR_EACH requires collection_expression")
            if not self.loop_body:
                issues.append(f"Node '{self.node_id}': FOR_EACH requires loop_body")

        if self.node_type == NodeType.TRY_CATCH:
            if not self.try_body:
                issues.append(f"Node '{self.node_id}': TRY_CATCH requires try_body")

        for edge in self.edges:
            if edge.edge_type == EdgeType.CONDITIONAL and edge.condition is None:
                issues.append(f"Node '{self.node_id}': conditional edge missing condition")

        return issues
```

#### 5.1.2 Workflow Definition

```python
# src/omni/workflow/definition.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..coordination.workflow import WorkflowPlan, WorkflowStep  # P2-14 compat
from .nodes import EdgeType, NodeType, WorkflowNode


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
    variables: dict[str, Any] = field(default_factory=dict)  # Initial workflow variables
    description: str = ""
    version: str = "1.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── P2-14 backward compatibility ──────────────────────────

    @classmethod
    def from_plan(cls, plan: WorkflowPlan) -> WorkflowDefinition:
        """
        Convert a P2-14 WorkflowPlan to a P2-15 WorkflowDefinition.

        Every WorkflowStep becomes a Task node (or Sequence of Task nodes).
        Step dependencies become unconditional edges.

        This ensures P2-14 workflows continue to work unchanged.
        """
        nodes: dict[str, WorkflowNode] = {}
        prev_step_node_id: str | None = None

        for step in plan.steps:
            if step.is_parallel and len(step.task_ids) > 1:
                # Parallel step → PARALLEL node with child TASK nodes
                child_ids: list[str] = []
                for task_id in step.task_ids:
                    child_node_id = f"{step.step_id}:{task_id}"
                    child_ids.append(child_node_id)
                    nodes[child_node_id] = WorkflowNode(
                        node_id=child_node_id,
                        node_type=NodeType.TASK,
                        label=f"Execute {task_id}",
                        task_id=task_id,
                        agent_id=step.agent_assignments.get(task_id),
                    )

                nodes[step.step_id] = WorkflowNode(
                    node_id=step.step_id,
                    node_type=NodeType.PARALLEL,
                    label=f"Parallel: {step.step_type.value}",
                    children=child_ids,
                )
            else:
                # Single task step → TASK node
                task_id = step.task_ids[0] if step.task_ids else step.step_id
                nodes[step.step_id] = WorkflowNode(
                    node_id=step.step_id,
                    node_type=NodeType.TASK,
                    label=f"Execute {task_id}",
                    task_id=task_id,
                    agent_id=step.agent_assignments.get(task_id),
                )

            # Wire edges from previous step
            if prev_step_node_id is not None:
                nodes[prev_step_node_id].edges.append(
                    nodes[step.step_id].node_id
                    if isinstance(nodes[step.step_id], str)
                    else __import__('dataclasses', fromlist=['']).asdict
                        if False else None  # placeholder
                )
                # Proper edge wiring
                from .nodes import NodeEdge
                nodes[prev_step_node_id].edges = [
                    NodeEdge(target_node_id=step.step_id)
                ]

            prev_step_node_id = step.step_id

        # Determine entry and exit
        entry = plan.steps[0].step_id if plan.steps else ""
        exit_nodes = [plan.steps[-1].step_id] if plan.steps else []

        return cls(
            workflow_id=plan.plan_id,
            name=plan.task_graph_name,
            nodes=nodes,
            entry_node_id=entry,
            exit_node_ids=exit_nodes,
        )

    # ── Navigation ─────────────────────────────────────────────

    def get_node(self, node_id: str) -> WorkflowNode:
        """Get a node by ID."""
        if node_id not in self.nodes:
            raise KeyError(f"Node '{node_id}' not found in workflow '{self.name}'")
        return self.nodes[node_id]

    def get_successors(self, node_id: str) -> list[tuple[str, EdgeType]]:
        """Get successor node IDs with their edge types."""
        node = self.get_node(node_id)
        return [(e.target_node_id, e.edge_type) for e in node.edges]

    def get_all_task_node_ids(self) -> list[str]:
        """Get all nodes that execute actual tasks."""
        return [nid for nid, n in self.nodes.items() if n.is_task]

    def get_reachable_nodes(self, start_node_id: str) -> set[str]:
        """Get all nodes reachable from a starting node (BFS)."""
        visited: set[str] = set()
        queue = [start_node_id]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            node = self.nodes.get(current)
            if node is None:
                continue
            # Collect all possible targets
            targets: list[str] = []
            for edge in node.edges:
                targets.append(edge.target_node_id)
            # Include branch targets for IF
            if node.node_type == NodeType.IF:
                targets.extend(node.true_branch)
                targets.extend(node.false_branch)
            # Include loop body for WHILE/FOR_EACH
            if node.node_type in (NodeType.WHILE, NodeType.FOR_EACH):
                targets.extend(node.loop_body)
            # Include TRY_CATCH bodies
            if node.node_type == NodeType.TRY_CATCH:
                targets.extend(node.try_body)
                for handler in node.catch_handlers:
                    targets.append(handler.target_node_id)
                targets.extend(node.finally_body)
            queue.extend(t for t in targets if t not in visited)
        return visited

    # ── Validation ─────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Validate the workflow definition. Returns list of issues."""
        issues: list[str] = []

        if not self.entry_node_id:
            issues.append("Workflow has no entry_node_id")
        elif self.entry_node_id not in self.nodes:
            issues.append(f"Entry node '{self.entry_node_id}' not in nodes")

        if not self.exit_node_ids:
            issues.append("Workflow has no exit_node_ids")

        for node_id, node in self.nodes.items():
            issues.extend(node.validate())

            # Check that all edge targets exist
            for edge in node.edges:
                if edge.target_node_id not in self.nodes:
                    issues.append(
                        f"Node '{node_id}' edge targets missing node '{edge.target_node_id}'"
                    )

            # Check IF branches
            if node.node_type == NodeType.IF:
                for branch_id in node.true_branch + node.false_branch:
                    if branch_id not in self.nodes:
                        issues.append(
                            f"IF node '{node_id}' references missing branch '{branch_id}'"
                        )

            # Check WHILE/FOR_EACH body
            if node.node_type in (NodeType.WHILE, NodeType.FOR_EACH):
                for body_id in node.loop_body:
                    if body_id not in self.nodes:
                        issues.append(
                            f"{node.node_type.value} node '{node_id}' references missing body '{body_id}'"
                        )

            # Check TRY_CATCH bodies
            if node.node_type == NodeType.TRY_CATCH:
                for body_id in node.try_body + node.finally_body:
                    if body_id not in self.nodes:
                        issues.append(
                            f"TRY_CATCH node '{node_id}' references missing body '{body_id}'"
                        )

        # Check reachability from entry
        if self.entry_node_id:
            reachable = self.get_reachable_nodes(self.entry_node_id)
            unreachable = set(self.nodes.keys()) - reachable
            if unreachable:
                issues.append(f"Unreachable nodes: {unreachable}")

        return issues

    @property
    def is_valid(self) -> bool:
        return len(self.validate()) == 0

    @property
    def size(self) -> int:
        return len(self.nodes)

    def summary(self) -> dict[str, Any]:
        """Get workflow summary."""
        type_counts: dict[str, int] = {}
        for node in self.nodes.values():
            key = node.node_type.value
            type_counts[key] = type_counts.get(key, 0) + 1

        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "total_nodes": self.size,
            "node_types": type_counts,
            "task_nodes": len(self.get_all_task_node_ids()),
            "has_loops": any(
                n.node_type in (NodeType.WHILE, NodeType.FOR_EACH)
                for n in self.nodes.values()
            ),
            "has_conditionals": any(
                n.node_type == NodeType.IF for n in self.nodes.values()
            ),
            "has_error_handling": any(
                n.node_type == NodeType.TRY_CATCH for n in self.nodes.values()
            ),
        }
```

#### 5.1.3 Expression Evaluator

```python
# src/omni/workflow/expressions.py

"""
Safe expression evaluation for workflow conditions.

Conditions are Python expressions evaluated against a restricted context.
No arbitrary code execution is permitted — only whitelisted builtins
and workflow-scoped variables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..task.models import TaskResult


class ConditionEvaluationError(Exception):
    """Raised when a condition expression fails to evaluate."""
    pass


# Whitelisted builtins for safe eval
_SAFE_BUILTINS = {
    # Type constructors
    "str": str, "int": int, "float": float, "bool": bool,
    "dict": dict, "list": list, "tuple": tuple, "set": set,

    # Math
    "abs": abs, "min": min, "max": max, "round": round, "sum": sum,
    "len": len,

    # Iteration
    "sorted": sorted, "reversed": reversed,
    "enumerate": enumerate, "zip": zip, "range": range,

    # Type checking
    "isinstance": isinstance, "type": type,

    # Constants
    "True": True, "False": False, "None": None,
}


@dataclass
class ExpressionContext:
    """
    Context available to expressions during evaluation.

    Populated by the execution state machine before evaluating conditions.
    """
    # Current task result (available after a TASK node completes)
    result: TaskResult | None = None

    # All completed node results
    node_results: dict[str, TaskResult] | None = None

    # Workflow-level variables (user-defined)
    variables: dict[str, Any] | None = None

    # Current iteration count (inside WHILE/FOR_EACH)
    iteration: int = 0

    # Current element (inside FOR_EACH)
    element: Any = None

    # Current index (inside FOR_EACH)
    index: int = 0

    # Collection being iterated (FOR_EACH)
    collection: list[Any] | None = None

    # Error that triggered a catch (inside TRY_CATCH catch blocks)
    error: Exception | None = None

    def to_eval_dict(self) -> dict[str, Any]:
        """Convert to a dict for eval() namespace."""
        d: dict[str, Any] = {
            "iteration": self.iteration,
            "index": self.index,
            "element": self.element,
        }

        if self.result is not None:
            d["result"] = self.result

        if self.node_results is not None:
            d["node_results"] = self.node_results
            # Also expose individual results by node ID
            for nid, r in self.node_results.items():
                d[f"result_{nid}"] = r

        if self.variables is not None:
            d["variables"] = self.variables

        if self.collection is not None:
            d["collection"] = self.collection

        if self.error is not None:
            d["error"] = self.error

        return d


class ExpressionEvaluator:
    """
    Evaluates condition expressions against a WorkflowContext.

    Thread safety: Each evaluation is independent — safe for concurrent use.
    """

    def evaluate(
        self,
        expression: str,
        context: ExpressionContext,
    ) -> bool:
        """
        Evaluate an expression and return boolean result.

        Args:
            expression: Python expression string
            context: Available variables and state

        Returns:
            Boolean result of the expression

        Raises:
            ConditionEvaluationError: If expression is invalid or unsafe
        """
        eval_dict = context.to_eval_dict()

        try:
            result = eval(expression, {"__builtins__": _SAFE_BUILTINS}, eval_dict)
            return bool(result)
        except Exception as e:
            raise ConditionEvaluationError(
                f"Failed to evaluate '{expression}': {type(e).__name__}: {e}"
            ) from e

    def evaluate_collection(
        self,
        expression: str,
        context: ExpressionContext,
    ) -> list[Any]:
        """
        Evaluate an expression that returns a collection (for FOR_EACH).

        Args:
            expression: Python expression returning an iterable
            context: Available variables and state

        Returns:
            List of elements to iterate over
        """
        eval_dict = context.to_eval_dict()

        try:
            result = eval(expression, {"__builtins__": _SAFE_BUILTINS}, eval_dict)
            return list(result)
        except Exception as e:
            raise ConditionEvaluationError(
                f"Failed to evaluate collection '{expression}': {e}"
            ) from e

    def evaluate_assignment(
        self,
        expression: str,
        context: ExpressionContext,
    ) -> Any:
        """
        Evaluate an expression and return its value (for variable assignment).

        Used by workflow nodes that set variables based on results.
        """
        eval_dict = context.to_eval_dict()

        try:
            return eval(expression, {"__builtins__": _SAFE_BUILTINS}, eval_dict)
        except Exception as e:
            raise ConditionEvaluationError(
                f"Failed to evaluate assignment '{expression}': {e}"
            ) from e
```

### 5.2 Execution State Machine

The state machine drives workflow execution, handling all control-flow transitions.

```python
# src/omni/workflow/state_machine.py

"""
Workflow execution state machine.

Drives node transitions for complex control flow: conditionals, loops,
error handling, compensation. This replaces the simple wave-based
scheduling of P2-14's WorkflowOrchestrator.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Awaitable, Callable

from ..coordination.matcher import AgentAssignment
from ..coordination.agents import AgentRegistry
from ..execution.config import ExecutionCallbacks, ExecutionConfig, ExecutionContext
from ..execution.executor import TaskExecutor
from ..task.models import Task, TaskGraph, TaskResult, TaskStatus
from .definition import WorkflowDefinition
from .expressions import ExpressionContext, ExpressionEvaluator
from .nodes import EdgeType, NodeType, ResourceConstraint, WorkflowNode
from .resources import ResourceBudget, ResourceManager

logger = logging.getLogger(__name__)


class NodeState(StrEnum):
    """Execution state of a workflow node."""
    PENDING = "pending"
    EVALUATING = "evaluating"  # Evaluating conditions (IF/WHILE/FOR_EACH)
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    COMPENSATING = "compensating"  # Running compensation actions
    COMPENSATED = "compensated"    # Compensation completed


@dataclass
class NodeExecution:
    """Runtime state of a single node execution."""
    node_id: str
    state: NodeState = NodeState.PENDING
    result: TaskResult | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    iteration: int = 0
    error: Exception | None = None
    compensation_results: list[TaskResult] = field(default_factory=list)


@dataclass
class WorkflowContext:
    """
    Shared state accessible throughout workflow execution.

    This is the execution-time equivalent of ExpressionContext,
    containing all runtime state needed by the state machine.
    """
    workflow_id: str
    execution_id: str
    definition: WorkflowDefinition

    # Node execution states
    node_executions: dict[str, NodeExecution] = field(default_factory=dict)

    # Workflow variables (persist across nodes)
    variables: dict[str, Any] = field(default_factory=dict)

    # Task graph for resolving task definitions
    task_graph: TaskGraph | None = None

    # Agent assignments from P2-14
    agent_assignments: dict[str, AgentAssignment] = field(default_factory=dict)

    # Iteration tracking per loop node
    iteration_counters: dict[str, int] = field(default_factory=dict)

    # FOR_EACH collection snapshots
    collection_snapshots: dict[str, list[Any]] = field(default_factory=dict)

    # Stack of TRY_CATCH node IDs for error routing
    try_catch_stack: list[str] = field(default_factory=list)

    def get_node_execution(self, node_id: str) -> NodeExecution:
        """Get or create node execution state."""
        if node_id not in self.node_executions:
            self.node_executions[node_id] = NodeExecution(node_id=node_id)
        return self.node_executions[node_id]

    def get_expression_context(
        self,
        current_node_id: str | None = None,
    ) -> ExpressionContext:
        """Build an ExpressionContext for condition evaluation."""
        result = None
        if current_node_id and current_node_id in self.node_executions:
            result = self.node_executions[current_node_id].result

        node_results = {
            nid: ex.result
            for nid, ex in self.node_executions.items()
            if ex.result is not None
        }

        iteration = 0
        element = None
        index = 0

        if current_node_id:
            iteration = self.iteration_counters.get(current_node_id, 0)
            if current_node_id in self.collection_snapshots:
                coll = self.collection_snapshots[current_node_id]
                if iteration < len(coll):
                    element = coll[iteration]
                    index = iteration

        return ExpressionContext(
            result=result,
            node_results=node_results,
            variables=self.variables,
            iteration=iteration,
            element=element,
            index=index,
        )


class WorkflowStateMachine:
    """
    Drives workflow execution by transitioning through nodes.

    Unlike P2-14's wave-based scheduler, this state machine handles
    arbitrary control flow: conditionals, loops, error handling.

    The state machine executes nodes one at a time (or in parallel
    when inside a PARALLEL node), but the scheduling of actual tasks
    is delegated to the P2-11 parallel execution engine.
    """

    def __init__(
        self,
        definition: WorkflowDefinition,
        task_executor: TaskExecutor,
        task_graph: TaskGraph,
        agent_assignments: dict[str, AgentAssignment],
        config: ExecutionConfig | None = None,
        resource_manager: ResourceManager | None = None,
        callbacks: ExecutionCallbacks | None = None,
    ) -> None:
        self.definition = definition
        self.task_executor = task_executor
        self.config = config or ExecutionConfig()
        self.resource_manager = resource_manager or ResourceManager()
        self.callbacks = callbacks
        self.evaluator = ExpressionEvaluator()

        # Initialize context
        self.context = WorkflowContext(
            workflow_id=definition.workflow_id,
            execution_id=uuid.uuid4().hex[:16],
            definition=definition,
            task_graph=task_graph,
            agent_assignments=agent_assignments,
            variables=definition.variables.copy(),
        )

        self._started = False
        self._completed = False

    async def execute(self) -> WorkflowResult:
        """
        Execute the workflow from entry to exit.

        Returns:
            WorkflowResult with all node outcomes
        """
        self._started = True
        start_time = datetime.now()
        logger.info(
            f"Starting workflow '{self.definition.name}' "
            f"(id={self.context.execution_id})"
        )

        try:
            await self._execute_node(self.definition.entry_node_id)
        except WorkflowAbort as abort:
            logger.warning(f"Workflow aborted: {abort.reason}")
        except Exception as e:
            logger.error(f"Workflow failed with unexpected error: {e}")
            raise

        self._completed = True
        end_time = datetime.now()

        return self._build_result(start_time, end_time)

    async def _execute_node(self, node_id: str) -> None:
        """
        Execute a single node by type.

        This is the core dispatch method — routes to the appropriate
        handler based on node type.
        """
        node = self.definition.get_node(node_id)
        exec_state = self.context.get_node_execution(node_id)

        logger.debug(f"Executing node '{node_id}' (type={node.node_type.value})")

        try:
            match node.node_type:
                case NodeType.TASK:
                    await self._execute_task_node(node, exec_state)
                case NodeType.PARALLEL:
                    await self._execute_parallel_node(node, exec_state)
                case NodeType.SEQUENCE:
                    await self._execute_sequence_node(node, exec_state)
                case NodeType.IF:
                    await self._execute_if_node(node, exec_state)
                case NodeType.WHILE:
                    await self._execute_while_node(node, exec_state)
                case NodeType.FOR_EACH:
                    await self._execute_for_each_node(node, exec_state)
                case NodeType.TRY_CATCH:
                    await self._execute_try_catch_node(node, exec_state)
                case NodeType.SUB_WORKFLOW:
                    await self._execute_sub_workflow_node(node, exec_state)
                case NodeType.COMPENSATE:
                    await self._execute_compensate_node(node, exec_state)

            # After successful execution, follow edges
            if exec_state.state == NodeState.COMPLETED:
                await self._follow_edges(node, exec_state)

        except Exception as e:
            await self._handle_node_failure(node, exec_state, e)

    async def _execute_task_node(
        self,
        node: WorkflowNode,
        exec_state: NodeExecution,
    ) -> None:
        """Execute a TASK node — delegates to the task executor."""
        assert node.task_id is not None

        # Get the task from the graph
        task = self.context.task_graph.get_task(node.task_id)

        # Check resource constraints
        budget = self.resource_manager.get_budget(self.context.execution_id)
        if not budget.can_allocate(node.resource):
            logger.warning(
                f"Resource limit hit for node '{node.node_id}', waiting..."
            )
            await budget.wait_for_capacity(node.resource)

        exec_state.state = NodeState.RUNNING
        exec_state.started_at = datetime.now()

        # Build execution context
        dep_results = {}
        for dep_id in task.dependencies:
            if dep_id in self.context.node_executions:
                dep_exec = self.context.node_executions[dep_id]
                if dep_exec.result:
                    dep_results[dep_id] = dep_exec.result

        exec_ctx = ExecutionContext(
            dependency_results=dep_results,
            execution_id=self.context.execution_id,
            task_index=len([
                e for e in self.context.node_executions.values()
                if e.state == NodeState.COMPLETED
            ]) + 1,
            total_tasks=len(self.definition.get_all_task_node_ids()),
        )

        # Execute with retry
        retries = 0
        max_retries = task.max_retries if self.config.retry_enabled else 0

        while True:
            try:
                result = await asyncio.wait_for(
                    self.task_executor.execute(task, exec_ctx),
                    timeout=node.resource.timeout_seconds or self.config.timeout_per_task,
                )

                exec_state.result = result
                exec_state.state = (
                    NodeState.COMPLETED if result.success
                    else NodeState.FAILED
                )
                exec_state.completed_at = datetime.now()
                break

            except Exception as e:
                retries += 1
                if retries > max_retries:
                    exec_state.error = e
                    exec_state.state = NodeState.FAILED
                    exec_state.completed_at = datetime.now()
                    raise

                # Exponential backoff
                delay = min(
                    self.config.backoff_base ** retries,
                    self.config.backoff_max,
                )
                logger.warning(
                    f"Task '{node.task_id}' failed (attempt {retries}/{max_retries}), "
                    f"retrying in {delay:.1f}s: {e}"
                )
                await asyncio.sleep(delay)

    async def _execute_parallel_node(
        self,
        node: WorkflowNode,
        exec_state: NodeExecution,
    ) -> None:
        """Execute children concurrently."""
        exec_state.state = NodeState.RUNNING
        exec_state.started_at = datetime.now()

        # Enforce resource constraints
        max_concurrent = node.resource.max_concurrent_tasks or self.config.max_concurrent
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_child(child_id: str) -> None:
            async with semaphore:
                await self._execute_node(child_id)

        tasks = [run_child(child_id) for child_id in node.children]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures
        failed = [
            r for r in results if isinstance(r, Exception)
        ]
        if failed:
            exec_state.state = NodeState.FAILED
            exec_state.error = failed[0]
        else:
            exec_state.state = NodeState.COMPLETED

        exec_state.completed_at = datetime.now()

    async def _execute_sequence_node(
        self,
        node: WorkflowNode,
        exec_state: NodeExecution,
    ) -> None:
        """Execute children in order."""
        exec_state.state = NodeState.RUNNING
        exec_state.started_at = datetime.now()

        for child_id in node.children:
            await self._execute_node(child_id)

            # Check if child failed
            child_exec = self.context.get_node_execution(child_id)
            if child_exec.state == NodeState.FAILED:
                exec_state.state = NodeState.FAILED
                exec_state.error = child_exec.error
                exec_state.completed_at = datetime.now()
                return

        exec_state.state = NodeState.COMPLETED
        exec_state.completed_at = datetime.now()

    async def _execute_if_node(
        self,
        node: WorkflowNode,
        exec_state: NodeExecution,
    ) -> None:
        """Evaluate condition and follow the matching branch."""
        exec_state.state = NodeState.EVALUATING
        exec_state.started_at = datetime.now()

        assert node.condition is not None
        expr_context = self.context.get_expression_context(node.node_id)

        try:
            condition_result = self.evaluator.evaluate(
                node.condition.expression, expr_context
            )
        except Exception as e:
            logger.error(f"Condition evaluation failed in IF node '{node.node_id}': {e}")
            exec_state.state = NodeState.FAILED
            exec_state.error = e
            exec_state.completed_at = datetime.now()
            raise

        branch = node.true_branch if condition_result else node.false_branch
        logger.info(
            f"IF node '{node.node_id}': condition={condition_result}, "
            f"branch={'true' if condition_result else 'false'}"
        )

        exec_state.state = NodeState.RUNNING

        for branch_node_id in branch:
            await self._execute_node(branch_node_id)

            # Check for failure
            branch_exec = self.context.get_node_execution(branch_node_id)
            if branch_exec.state == NodeState.FAILED:
                exec_state.state = NodeState.FAILED
                exec_state.error = branch_exec.error
                exec_state.completed_at = datetime.now()
                return

        exec_state.state = NodeState.COMPLETED
        exec_state.completed_at = datetime.now()

    async def _execute_while_node(
        self,
        node: WorkflowNode,
        exec_state: NodeExecution,
    ) -> None:
        """Loop while condition is true, executing body each iteration."""
        exec_state.state = NodeState.RUNNING
        exec_state.started_at = datetime.now()

        assert node.loop_condition is not None
        iteration = 0

        while iteration < node.max_iterations:
            self.context.iteration_counters[node.node_id] = iteration

            expr_context = self.context.get_expression_context(node.node_id)

            try:
                should_continue = self.evaluator.evaluate(
                    node.loop_condition.expression, expr_context
                )
            except Exception as e:
                logger.error(f"Loop condition failed in WHILE node '{node.node_id}': {e}")
                exec_state.state = NodeState.FAILED
                exec_state.error = e
                exec_state.completed_at = datetime.now()
                raise

            if not should_continue:
                logger.info(
                    f"WHILE node '{node.node_id}': condition false after "
                    f"{iteration} iterations"
                )
                break

            logger.debug(
                f"WHILE node '{node.node_id}': iteration {iteration}"
            )

            # Execute loop body
            for body_node_id in node.loop_body:
                await self._execute_node(body_node_id)

                body_exec = self.context.get_node_execution(body_node_id)
                if body_exec.state == NodeState.FAILED:
                    exec_state.state = NodeState.FAILED
                    exec_state.error = body_exec.error
                    exec_state.completed_at = datetime.now()
                    return

            # Clear body node states for next iteration
            for body_node_id in node.loop_body:
                if body_node_id in self.context.node_executions:
                    del self.context.node_executions[body_node_id]

            iteration += 1

        if iteration >= node.max_iterations:
            logger.warning(
                f"WHILE node '{node.node_id}' hit max_iterations ({node.max_iterations})"
            )

        exec_state.iteration = iteration
        exec_state.state = NodeState.COMPLETED
        exec_state.completed_at = datetime.now()

    async def _execute_for_each_node(
        self,
        node: WorkflowNode,
        exec_state: NodeExecution,
    ) -> None:
        """Iterate over collection, executing body for each element."""
        exec_state.state = NodeState.EVALUATING
        exec_state.started_at = datetime.now()

        expr_context = self.context.get_expression_context(node.node_id)

        try:
            collection = self.evaluator.evaluate_collection(
                node.collection_expression, expr_context
            )
        except Exception as e:
            logger.error(f"Collection evaluation failed in FOR_EACH node '{node.node_id}': {e}")
            exec_state.state = NodeState.FAILED
            exec_state.error = e
            exec_state.completed_at = datetime.now()
            raise

        self.context.collection_snapshots[node.node_id] = collection
        exec_state.state = NodeState.RUNNING

        for idx, element in enumerate(collection):
            self.context.iteration_counters[node.node_id] = idx
            # Expose element and index in variables
            self.context.variables[node.element_variable] = element
            self.context.variables[node.index_variable] = idx

            logger.debug(
                f"FOR_EACH node '{node.node_id}': element {idx}/{len(collection)}"
            )

            for body_node_id in node.loop_body:
                await self._execute_node(body_node_id)

                body_exec = self.context.get_node_execution(body_node_id)
                if body_exec.state == NodeState.FAILED:
                    exec_state.state = NodeState.FAILED
                    exec_state.error = body_exec.error
                    exec_state.completed_at = datetime.now()
                    return

            # Clear body node states for next iteration
            for body_node_id in node.loop_body:
                if body_node_id in self.context.node_executions:
                    del self.context.node_executions[body_node_id]

        exec_state.iteration = len(collection)
        exec_state.state = NodeState.COMPLETED
        exec_state.completed_at = datetime.now()

    async def _execute_try_catch_node(
        self,
        node: WorkflowNode,
        exec_state: NodeExecution,
    ) -> None:
        """Execute try body with error handling."""
        exec_state.state = NodeState.RUNNING
        exec_state.started_at = datetime.now()

        # Push onto try_catch stack for error routing
        self.context.try_catch_stack.append(node.node_id)
        caught_error: Exception | None = None

        try:
            # Execute try body
            for try_node_id in node.try_body:
                await self._execute_node(try_node_id)

                try_exec = self.context.get_node_execution(try_node_id)
                if try_exec.state == NodeState.FAILED:
                    caught_error = try_exec.error
                    break
        except Exception as e:
            caught_error = e

        finally:
            # Pop from stack
            if self.context.try_catch_stack and self.context.try_catch_stack[-1] == node.node_id:
                self.context.try_catch_stack.pop()

        if caught_error is not None:
            # Execute catch handlers
            for handler in node.catch_handlers:
                if handler.condition:
                    expr_context = self.context.get_expression_context(node.node_id)
                    expr_context.error = caught_error
                    try:
                        matches = self.evaluator.evaluate(
                            handler.condition.expression, expr_context
                        )
                    except Exception:
                        matches = False  # Condition error → skip handler
                    if not matches:
                        continue

                # Execute handler
                await self._execute_node(handler.target_node_id)

        # Execute finally body (always runs)
        for finally_node_id in node.finally_body:
            await self._execute_node(finally_node_id)

        exec_state.state = NodeState.COMPLETED if caught_error is None else NodeState.COMPLETED
        exec_state.completed_at = datetime.now()

    async def _execute_sub_workflow_node(
        self,
        node: WorkflowNode,
        exec_state: NodeExecution,
    ) -> None:
        """Execute a referenced sub-workflow template."""
        # Resolved by the orchestrator — delegate to template expansion
        # For now, placeholder
        exec_state.state = NodeState.COMPLETED
        exec_state.completed_at = datetime.now()

    async def _execute_compensate_node(
        self,
        node: WorkflowNode,
        exec_state: NodeExecution,
    ) -> None:
        """Execute a compensation action (rollback)."""
        exec_state.state = NodeState.COMPENSATING
        exec_state.started_at = datetime.now()

        if node.task_id:
            task = self.context.task_graph.get_task(node.task_id)
            exec_ctx = ExecutionContext(
                dependency_results={},
                execution_id=self.context.execution_id,
                task_index=0,
                total_tasks=0,
            )
            try:
                result = await self.task_executor.execute(task, exec_ctx)
                exec_state.result = result
                exec_state.state = NodeState.COMPENSATED
            except Exception as e:
                exec_state.error = e
                exec_state.state = NodeState.FAILED
        else:
            exec_state.state = NodeState.COMPENSATED

        exec_state.completed_at = datetime.now()

    async def _follow_edges(
        self,
        node: WorkflowNode,
        exec_state: NodeExecution,
    ) -> None:
        """Follow outgoing edges after a node completes successfully."""
        for edge in sorted(node.edges, key=lambda e: -e.priority):
            if edge.edge_type == EdgeType.UNCONDITIONAL:
                await self._execute_node(edge.target_node_id)
                return  # Follow first unconditional edge only

            elif edge.edge_type == EdgeType.CONDITIONAL:
                assert edge.condition is not None
                expr_context = self.context.get_expression_context(node.node_id)
                try:
                    if self.evaluator.evaluate(edge.condition.expression, expr_context):
                        await self._execute_node(edge.target_node_id)
                        return
                except Exception:
                    continue  # Condition failed → try next edge

        # No edges matched — check if this is an exit node
        if node.node_id not in self.definition.exit_node_ids:
            logger.debug(
                f"Node '{node.node_id}' completed with no matching edges, "
                f"treating as terminal"
            )

    async def _handle_node_failure(
        self,
        node: WorkflowNode,
        exec_state: NodeExecution,
        error: Exception,
    ) -> None:
        """Handle node failure: try compensation, route to error edges."""
        exec_state.state = NodeState.FAILED
        exec_state.error = error
        exec_state.completed_at = datetime.now()

        # Run compensation actions
        for comp in node.compensations:
            if "FAILED" in comp.trigger_on:
                comp_node = self.definition.get_node(comp.action_node_id)
                comp_exec = self.context.get_node_execution(comp.action_node_id)
                comp_exec.state = NodeState.COMPENSATING
                await self._execute_compensate_node(comp_node, comp_exec)

        # Try error edges
        for edge in node.edges:
            if edge.edge_type == EdgeType.ERROR:
                logger.info(
                    f"Routing failure of '{node.node_id}' to "
                    f"error handler '{edge.target_node_id}'"
                )
                await self._execute_node(edge.target_node_id)
                return

        # Check if there's a TRY_CATCH on the stack that can catch this
        if self.context.try_catch_stack:
            try_node_id = self.context.try_catch_stack[-1]
            try_node = self.definition.get_node(try_node_id)
            for handler in try_node.catch_handlers:
                if handler.condition is None:
                    # Unconditional catch
                    logger.info(
                        f"TRY_CATCH '{try_node_id}' catching error from '{node.node_id}'"
                    )
                    await self._execute_node(handler.target_node_id)
                    return
                else:
                    expr_context = self.context.get_expression_context(try_node_id)
                    expr_context.error = error
                    try:
                        if self.evaluator.evaluate(
                            handler.condition.expression, expr_context
                        ):
                            await self._execute_node(handler.target_node_id)
                            return
                    except Exception:
                        continue

        # No handler found — propagate error
        logger.error(
            f"Unhandled failure in node '{node.node_id}': {error}"
        )
        raise WorkflowAbort(
            reason=f"Unhandled failure in '{node.node_id}': {error}",
            failed_node_id=node.node_id,
        ) from error

    def _build_result(self, start_time: datetime, end_time: datetime) -> WorkflowResult:
        """Build the final workflow execution result."""
        node_states = {
            nid: ex.state.value
            for nid, ex in self.context.node_executions.items()
        }

        failed_nodes = [
            nid for nid, ex in self.context.node_executions.items()
            if ex.state == NodeState.FAILED
        ]

        completed_nodes = [
            nid for nid, ex in self.context.node_executions.items()
            if ex.state in (NodeState.COMPLETED, NodeState.COMPENSATED)
        ]

        total_cost = sum(
            ex.result.cost
            for ex in self.context.node_executions.values()
            if ex.result
        )

        total_tokens = sum(
            ex.result.tokens_used
            for ex in self.context.node_executions.values()
            if ex.result
        )

        return WorkflowResult(
            workflow_id=self.context.workflow_id,
            execution_id=self.context.execution_id,
            name=self.definition.name,
            status="completed" if not failed_nodes else "failed",
            node_states=node_states,
            node_results={
                nid: ex.result
                for nid, ex in self.context.node_executions.items()
                if ex.result
            },
            variables=self.context.variables.copy(),
            total_cost=total_cost,
            total_tokens=total_tokens,
            started_at=start_time,
            completed_at=end_time,
            failed_nodes=failed_nodes,
            iteration_counts=dict(self.context.iteration_counters),
        )


class WorkflowAbort(Exception):
    """Raised to abort workflow execution."""
    def __init__(self, reason: str, failed_node_id: str) -> None:
        self.reason = reason
        self.failed_node_id = failed_node_id
        super().__init__(reason)


@dataclass
class WorkflowResult:
    """Final result of workflow execution."""
    workflow_id: str
    execution_id: str
    name: str
    status: str  # "completed" | "failed" | "cancelled"
    node_states: dict[str, str]  # node_id → state
    node_results: dict[str, TaskResult]  # task node results
    variables: dict[str, Any]  # Final workflow variables
    total_cost: float
    total_tokens: int
    started_at: datetime
    completed_at: datetime
    failed_nodes: list[str] = field(default_factory=list)
    iteration_counts: dict[str, int] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == "completed"

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()
```

### 5.3 Resource Manager

```python
# src/omni/workflow/resources.py

"""
Resource management for workflow execution.

Provides per-workflow quotas for concurrency, tokens, cost, and time.
Prevents runaway workflows from exhausting system resources.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from .nodes import ResourceConstraint

logger = logging.getLogger(__name__)


@dataclass
class ResourceBudget:
    """Tracking and enforcement of resource limits for a workflow execution."""
    execution_id: str
    max_concurrent: int = 5
    max_tokens: int | None = None
    max_cost: float | None = None
    max_wall_time: float | None = None

    # Current usage
    active_tasks: int = 0
    tokens_used: int = 0
    cost_used: float = 0.0

    # Internal
    _semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(5))
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        self._semaphore = asyncio.Semaphore(self.max_concurrent)

    def can_allocate(self, constraint: ResourceConstraint) -> bool:
        """Check if resources are available for a node with given constraints."""
        if constraint.max_tokens and self.max_tokens:
            if self.tokens_used + constraint.max_tokens > self.max_tokens:
                return False
        if constraint.max_cost and self.max_cost:
            if self.cost_used + constraint.max_cost > self.max_cost:
                return False
        return True

    async def wait_for_capacity(self, constraint: ResourceConstraint) -> None:
        """Wait until resources are available."""
        while not self.can_allocate(constraint):
            await asyncio.sleep(0.5)

    async def acquire(self) -> None:
        """Acquire a concurrency slot."""
        await self._semaphore.acquire()
        self.active_tasks += 1

    def release(self, tokens: int = 0, cost: float = 0.0) -> None:
        """Release a concurrency slot and record usage."""
        self._semaphore.release()
        self.active_tasks = max(0, self.active_tasks - 1)
        self.tokens_used += tokens
        self.cost_used += cost

    @property
    def utilization(self) -> dict[str, Any]:
        """Current resource utilization."""
        return {
            "active_tasks": self.active_tasks,
            "max_concurrent": self.max_concurrent,
            "concurrency_pct": self.active_tasks / max(1, self.max_concurrent),
            "tokens_used": self.tokens_used,
            "token_limit": self.max_tokens,
            "cost_used": round(self.cost_used, 4),
            "cost_limit": self.max_cost,
        }


class ResourceManager:
    """
    Central resource manager for all active workflows.

    Maintains per-execution budgets and provides global resource visibility.
    """

    def __init__(self, global_max_concurrent: int = 20) -> None:
        self.global_max_concurrent = global_max_concurrent
        self._budgets: dict[str, ResourceBudget] = {}
        self._global_semaphore = asyncio.Semaphore(global_max_concurrent)

    def create_budget(
        self,
        execution_id: str,
        max_concurrent: int = 5,
        max_tokens: int | None = None,
        max_cost: float | None = None,
        max_wall_time: float | None = None,
    ) -> ResourceBudget:
        """Create a resource budget for a workflow execution."""
        budget = ResourceBudget(
            execution_id=execution_id,
            max_concurrent=max_concurrent,
            max_tokens=max_tokens,
            max_cost=max_cost,
            max_wall_time=max_wall_time,
        )
        self._budgets[execution_id] = budget
        return budget

    def get_budget(self, execution_id: str) -> ResourceBudget:
        """Get budget for an execution."""
        if execution_id not in self._budgets:
            raise KeyError(f"No budget found for execution '{execution_id}'")
        return self._budgets[execution_id]

    def remove_budget(self, execution_id: str) -> None:
        """Clean up budget after execution completes."""
        self._budgets.pop(execution_id, None)

    def global_status(self) -> dict[str, Any]:
        """Global resource status across all workflows."""
        total_active = sum(b.active_tasks for b in self._budgets.values())
        total_tokens = sum(b.tokens_used for b in self._budgets.values())
        total_cost = sum(b.cost_used for b in self._budgets.values())

        return {
            "active_workflows": len(self._budgets),
            "total_active_tasks": total_active,
            "global_max_concurrent": self.global_max_concurrent,
            "total_tokens_used": total_tokens,
            "total_cost_used": round(total_cost, 4),
            "per_execution": {
                eid: b.utilization for eid, b in self._budgets.items()
            },
        }
```

### 5.4 Workflow Templates

```python
# src/omni/workflow/templates.py

"""
Reusable workflow templates.

Templates are parameterized WorkflowDefinitions that can be instantiated
with specific parameters. They capture common orchestration patterns
so users don't have to build workflows from scratch every time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .definition import WorkflowDefinition
from .nodes import (
    Condition, EdgeType, NodeType, ResourceConstraint, WorkflowNode,
)


@dataclass
class TemplateParameter:
    """A parameter for a workflow template."""
    name: str
    description: str
    default: Any = None
    required: bool = True
    param_type: str = "str"  # "str", "int", "float", "bool", "list"


@dataclass
class WorkflowTemplate:
    """
    A parameterized workflow template.

    Templates define a reusable workflow structure with named parameters
    that are substituted at instantiation time.
    """
    template_id: str
    name: str
    description: str
    parameters: list[TemplateParameter] = field(default_factory=list)
    _builder: Any = field(default=None, repr=False)  # Callable[[dict], WorkflowDefinition]

    def instantiate(
        self,
        workflow_id: str,
        **kwargs: Any,
    ) -> WorkflowDefinition:
        """
        Instantiate a template with concrete parameters.

        Args:
            workflow_id: Unique ID for the workflow instance
            **kwargs: Parameter values

        Returns:
            WorkflowDefinition ready for execution
        """
        # Validate required params
        missing = [
            p.name for p in self.parameters
            if p.required and p.name not in kwargs and p.default is None
        ]
        if missing:
            raise ValueError(
                f"Missing required parameters for template '{self.template_id}': {missing}"
            )

        # Apply defaults
        params = {p.name: p.default for p in self.parameters if p.default is not None}
        params.update(kwargs)

        if self._builder is None:
            raise RuntimeError(f"Template '{self.template_id}' has no builder")

        return self._builder(workflow_id, params)


class TemplateRegistry:
    """Registry of available workflow templates."""

    def __init__(self) -> None:
        self._templates: dict[str, WorkflowTemplate] = {}
        self._register_defaults()

    def register(self, template: WorkflowTemplate) -> None:
        self._templates[template.template_id] = template

    def get(self, template_id: str) -> WorkflowTemplate:
        if template_id not in self.templates:
            raise KeyError(f"Template '{template_id}' not found")
        return self._templates[template_id]

    def list_templates(self) -> list[dict[str, str]]:
        return [
            {"id": t.template_id, "name": t.name, "description": t.description}
            for t in self._templates.values()
        ]

    @property
    def templates(self) -> dict[str, WorkflowTemplate]:
        return self._templates

    def _register_defaults(self) -> None:
        """Register built-in workflow templates."""
        self.register(_build_analyze_implement_test_review())
        self.register(_build_explore_plan_implement())
        self.register(_build_parallel_review())
        self.register(_build_retry_until_success())
        self.register(_build_safe_deploy())


def _build_analyze_implement_test_review() -> WorkflowTemplate:
    """
    Default development pipeline:
    1. Analyze the codebase
    2. Implement the solution
    3. Run tests
    4. IF tests pass → review, ELSE → fix and retry
    """
    def builder(workflow_id: str, params: dict[str, Any]) -> WorkflowDefinition:
        nodes = {
            "analyze": WorkflowNode(
                node_id="analyze",
                node_type=NodeType.TASK,
                label="Analyze codebase",
                task_id=params.get("analyze_task_id", "analyze"),
                agent_id=params.get("analyze_agent", "reader"),
                edges=[EdgeType.UNCONDITIONAL.__class__(
                    target_node_id="implement",
                    edge_type=EdgeType.UNCONDITIONAL,
                )],
            ),
            "implement": WorkflowNode(
                node_id="implement",
                node_type=NodeType.TASK,
                label="Implement solution",
                task_id=params.get("implement_task_id", "implement"),
                agent_id=params.get("implement_agent", "coder"),
                edges=[EdgeType.UNCONDITIONAL.__class__(
                    target_node_id="test",
                    edge_type=EdgeType.UNCONDITIONAL,
                )],
            ),
            "test": WorkflowNode(
                node_id="test",
                node_type=NodeType.TASK,
                label="Run tests",
                task_id=params.get("test_task_id", "test"),
                agent_id=params.get("test_agent", "coder"),
                edges=[],
            ),
            "check_tests": WorkflowNode(
                node_id="check_tests",
                node_type=NodeType.IF,
                label="Tests passed?",
                condition=Condition(
                    "result.success",
                    description="Check if test task completed successfully",
                ),
                true_branch=["review"],
                false_branch=["fix"],
            ),
            "review": WorkflowNode(
                node_id="review",
                node_type=NodeType.TASK,
                label="Code review",
                task_id=params.get("review_task_id", "review"),
                agent_id=params.get("review_agent", "reader"),
            ),
            "fix": WorkflowNode(
                node_id="fix",
                node_type=NodeType.TASK,
                label="Fix failing tests",
                task_id=params.get("fix_task_id", "fix"),
                agent_id=params.get("fix_agent", "coder"),
                edges=[EdgeType.UNCONDITIONAL.__class__(
                    target_node_id="test",
                    edge_type=EdgeType.UNCONDITIONAL,
                )],
            ),
        }

        # Wire: test → check_tests
        from .nodes import NodeEdge
        nodes["test"].edges = [
            NodeEdge(target_node_id="check_tests", edge_type=EdgeType.UNCONDITIONAL)
        ]

        return WorkflowDefinition(
            workflow_id=workflow_id,
            name=params.get("name", "Analyze→Implement→Test→Review"),
            nodes=nodes,
            entry_node_id="analyze",
            exit_node_ids=["review"],
            description="Standard development pipeline with test-retry loop",
        )

    return WorkflowTemplate(
        template_id="analyze-implement-test-review",
        name="Analyze → Implement → Test → Review",
        description="Standard development pipeline: analyze, implement, test, review with auto-fix loop",
        parameters=[
            TemplateParameter("name", "Workflow name", required=False),
            TemplateParameter("analyze_task_id", "Task ID for analysis step", required=False),
            TemplateParameter("analyze_agent", "Agent for analysis", default="reader", required=False),
            TemplateParameter("implement_task_id", "Task ID for implementation", required=False),
            TemplateParameter("implement_agent", "Agent for implementation", default="coder", required=False),
            TemplateParameter("test_task_id", "Task ID for testing", required=False),
            TemplateParameter("test_agent", "Agent for testing", default="coder", required=False),
            TemplateParameter("review_task_id", "Task ID for review", required=False),
            TemplateParameter("review_agent", "Agent for review", default="reader", required=False),
            TemplateParameter("fix_task_id", "Task ID for fix loop", required=False),
            TemplateParameter("fix_agent", "Agent for fixes", default="coder", required=False),
        ],
        _builder=builder,
    )


def _build_explore_plan_implement() -> WorkflowTemplate:
    """
    Codebase exploration workflow:
    1. Explore (Reader) → understand the codebase
    2. Plan (Thinker) → create implementation plan
    3. FOR_EACH plan items → implement
    4. Review
    """
    def builder(workflow_id: str, params: dict[str, Any]) -> WorkflowDefinition:
        from .nodes import NodeEdge
        nodes = {
            "explore": WorkflowNode(
                node_id="explore",
                node_type=NodeType.TASK,
                label="Explore codebase",
                task_id=params.get("explore_task_id", "explore"),
                agent_id="reader",
                edges=[NodeEdge(target_node_id="plan", edge_type=EdgeType.UNCONDITIONAL)],
            ),
            "plan": WorkflowNode(
                node_id="plan",
                node_type=NodeType.TASK,
                label="Create implementation plan",
                task_id=params.get("plan_task_id", "plan"),
                agent_id="thinker",
                edges=[NodeEdge(target_node_id="implement_each", edge_type=EdgeType.UNCONDITIONAL)],
            ),
            "implement_each": WorkflowNode(
                node_id="implement_each",
                node_type=NodeType.FOR_EACH,
                label="Implement each plan item",
                collection_expression="result.outputs.get('items', [])",
                element_variable="plan_item",
                index_variable="item_index",
                loop_body=["implement_item"],
            ),
            "implement_item": WorkflowNode(
                node_id="implement_item",
                node_type=NodeType.TASK,
                label="Implement plan item",
                task_id=params.get("implement_task_id", "implement"),
                agent_id="coder",
            ),
            "review": WorkflowNode(
                node_id="review",
                node_type=NodeType.TASK,
                label="Final review",
                task_id=params.get("review_task_id", "review"),
                agent_id="reader",
            ),
        }

        nodes["implement_each"].edges = [
            NodeEdge(target_node_id="review", edge_type=EdgeType.UNCONDITIONAL)
        ]

        return WorkflowDefinition(
            workflow_id=workflow_id,
            name=params.get("name", "Explore→Plan→Implement"),
            nodes=nodes,
            entry_node_id="explore",
            exit_node_ids=["review"],
            description="Explore codebase, plan, iterate over plan items, review",
        )

    return WorkflowTemplate(
        template_id="explore-plan-implement",
        name="Explore → Plan → Implement",
        description="Codebase exploration with iterative implementation",
        parameters=[
            TemplateParameter("name", "Workflow name", required=False),
            TemplateParameter("explore_task_id", "Task ID for exploration"),
            TemplateParameter("plan_task_id", "Task ID for planning"),
            TemplateParameter("implement_task_id", "Task ID for implementation"),
            TemplateParameter("review_task_id", "Task ID for review", required=False),
        ],
        _builder=builder,
    )


def _build_parallel_review() -> WorkflowTemplate:
    """Fan-out review: implement N items in parallel, then review all."""
    def builder(workflow_id: str, params: dict[str, Any]) -> WorkflowDefinition:
        from .nodes import NodeEdge
        nodes = {
            "implement_parallel": WorkflowNode(
                node_id="implement_parallel",
                node_type=NodeType.PARALLEL,
                label="Implement in parallel",
                children=params.get("implement_task_ids", ["implement-1", "implement-2"]),
                resource=ResourceConstraint(max_concurrent_tasks=params.get("max_concurrent", 3)),
            ),
            "review_all": WorkflowNode(
                node_id="review_all",
                node_type=NodeType.TASK,
                label="Review all implementations",
                task_id=params.get("review_task_id", "review"),
                agent_id="reader",
            ),
        }
        nodes["implement_parallel"].edges = [
            NodeEdge(target_node_id="review_all", edge_type=EdgeType.UNCONDITIONAL)
        ]

        return WorkflowDefinition(
            workflow_id=workflow_id,
            name="Parallel Review",
            nodes=nodes,
            entry_node_id="implement_parallel",
            exit_node_ids=["review_all"],
        )

    return WorkflowTemplate(
        template_id="parallel-review",
        name="Parallel Implementation + Review",
        description="Implement multiple items in parallel, then review all",
        parameters=[
            TemplateParameter("implement_task_ids", "List of implementation task IDs", param_type="list"),
            TemplateParameter("review_task_id", "Review task ID"),
            TemplateParameter("max_concurrent", "Max parallel tasks", default=3, param_type="int", required=False),
        ],
        _builder=builder,
    )


def _build_retry_until_success() -> WorkflowTemplate:
    """Retry a task until it succeeds or hits max iterations."""
    def builder(workflow_id: str, params: dict[str, Any]) -> WorkflowDefinition:
        from .nodes import NodeEdge
        max_iter = params.get("max_iterations", 5)
        task_id = params.get("task_id", "task")
        fallback_task_id = params.get("fallback_task_id")

        nodes: dict[str, WorkflowNode] = {
            "retry_loop": WorkflowNode(
                node_id="retry_loop",
                node_type=NodeType.WHILE,
                label=f"Retry until success (max {max_iter})",
                loop_condition=Condition(
                    f"iteration < {max_iter} and "
                    f"(node_results.get('execute_task') is None or "
                    f"not node_results['execute_task'].success)",
                    description="Continue while task hasn't succeeded and under max iterations",
                ),
                loop_body=["execute_task", "check_result"],
                max_iterations=max_iter,
            ),
            "execute_task": WorkflowNode(
                node_id="execute_task",
                node_type=NodeType.TASK,
                label="Execute task",
                task_id=task_id,
                agent_id=params.get("agent_id", "coder"),
            ),
            "check_result": WorkflowNode(
                node_id="check_result",
                node_type=NodeType.IF,
                label="Task succeeded?",
                condition=Condition(
                    "result.success",
                    description="Check if task completed successfully",
                ),
                true_branch=[],  # Loop condition handles exit
                false_branch=[],
            ),
        }

        if fallback_task_id:
            nodes["fallback"] = WorkflowNode(
                node_id="fallback",
                node_type=NodeType.TASK,
                label="Execute fallback",
                task_id=fallback_task_id,
                agent_id=params.get("fallback_agent", "thinker"),
            )
            nodes["retry_loop"].edges = [
                NodeEdge(
                    target_node_id="fallback",
                    edge_type=EdgeType.CONDITIONAL,
                    condition=Condition(
                        "not node_results.get('execute_task', TaskResult('', 'failed')).success",
                        description="If retry loop exhausted without success",
                    ),
                ),
            ]

        return WorkflowDefinition(
            workflow_id=workflow_id,
            name=params.get("name", "Retry Until Success"),
            nodes=nodes,
            entry_node_id="retry_loop",
            exit_node_ids=["execute_task"] if not fallback_task_id else ["fallback"],
            description=f"Retry task up to {max_iter} times with optional fallback",
        )

    return WorkflowTemplate(
        template_id="retry-until-success",
        name="Retry Until Success",
        description="Retry a task with loop until success or max iterations, with optional fallback",
        parameters=[
            TemplateParameter("task_id", "Task ID to retry"),
            TemplateParameter("agent_id", "Agent for the task", default="coder", required=False),
            TemplateParameter("max_iterations", "Max retry attempts", default=5, param_type="int", required=False),
            TemplateParameter("fallback_task_id", "Fallback task if all retries fail", required=False),
            TemplateParameter("fallback_agent", "Agent for fallback", default="thinker", required=False),
            TemplateParameter("name", "Workflow name", required=False),
        ],
        _builder=builder,
    )


def _build_safe_deploy() -> WorkflowTemplate:
    """
    Safe deployment pattern:
    TRY → deploy
    CATCH → rollback
    """
    def builder(workflow_id: str, params: dict[str, Any]) -> WorkflowDefinition:
        from .nodes import NodeEdge
        nodes = {
            "try_deploy": WorkflowNode(
                node_id="try_deploy",
                node_type=NodeType.TRY_CATCH,
                label="Safe deployment",
                try_body=["deploy"],
                catch_handlers=[
                    NodeEdge(
                        target_node_id="rollback",
                        edge_type=EdgeType.UNCONDITIONAL,
                    ),
                ],
                finally_body=["notify"],
            ),
            "deploy": WorkflowNode(
                node_id="deploy",
                node_type=NodeType.TASK,
                label="Deploy",
                task_id=params.get("deploy_task_id", "deploy"),
                agent_id=params.get("deploy_agent", "coder"),
            ),
            "rollback": WorkflowNode(
                node_id="rollback",
                node_type=NodeType.COMPENSATE,
                label="Rollback deployment",
                task_id=params.get("rollback_task_id", "rollback"),
            ),
            "notify": WorkflowNode(
                node_id="notify",
                node_type=NodeType.TASK,
                label="Send notification",
                task_id=params.get("notify_task_id", "notify"),
                agent_id="intern",
            ),
        }

        return WorkflowDefinition(
            workflow_id=workflow_id,
            name=params.get("name", "Safe Deploy"),
            nodes=nodes,
            entry_node_id="try_deploy",
            exit_node_ids=["notify"],
            description="Deploy with automatic rollback on failure",
        )

    return WorkflowTemplate(
        template_id="safe-deploy",
        name="Safe Deploy",
        description="Deploy with try/catch rollback and notification",
        parameters=[
            TemplateParameter("deploy_task_id", "Deploy task ID"),
            TemplateParameter("rollback_task_id", "Rollback task ID"),
            TemplateParameter("notify_task_id", "Notification task ID", required=False),
            TemplateParameter("deploy_agent", "Agent for deploy", default="coder", required=False),
            TemplateParameter("name", "Workflow name", required=False),
        ],
        _builder=builder,
    )
```

### 5.5 Workflow Orchestrator (P2-15 Facade)

```python
# src/omni/workflow/orchestrator.py

"""
P2-15 Workflow Orchestrator — top-level facade.

Extends P2-14's CoordinationEngine with conditional workflow support.
Maintains full backward compatibility: plain WorkflowPlans work unchanged.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..coordination.engine import CoordinationEngine, CoordinationResult
from ..coordination.matcher import AgentAssignment
from ..execution.config import ExecutionConfig
from ..execution.executor import TaskExecutor
from ..task.models import TaskGraph
from .definition import WorkflowDefinition
from .nodes import NodeType, WorkflowNode
from .resources import ResourceManager
from .state_machine import WorkflowResult, WorkflowStateMachine
from .templates import TemplateRegistry, WorkflowTemplate

logger = logging.getLogger(__name__)


@dataclass
class WorkflowOrchestrationConfig:
    """Configuration for the workflow orchestrator."""
    execution_config: ExecutionConfig = field(default_factory=ExecutionConfig)
    max_workflow_concurrent: int = 10       # Global max concurrent across all workflows
    enable_templates: bool = True           # Enable template-based workflows
    default_resource_limits: dict[str, Any] = field(default_factory=lambda: {
        "max_concurrent_tasks": 5,
        "max_tokens": None,
        "max_cost": None,
        "timeout_seconds": 600.0,
    })


class WorkflowOrchestrator:
    """
    Top-level orchestrator for P2-15 conditional workflows.

    Bridges P2-14 coordination → P2-15 state machine execution.

    Usage:
        # Simple (P2-14 compatible)
        orchestrator = WorkflowOrchestrator()
        result = await orchestrator.execute_from_plan(plan, task_graph, executor)

        # Conditional workflow
        workflow = orchestrator.build_workflow(task_graph, assignments, definition)
        result = await orchestrator.execute_workflow(workflow, executor)

        # From template
        workflow = orchestrator.instantiate_template(
            "analyze-implement-test-review",
            analyze_task_id="t1",
            implement_task_id="t2",
        )
        result = await orchestrator.execute_workflow(workflow, executor)
    """

    def __init__(
        self,
        config: WorkflowOrchestrationConfig | None = None,
        coordination_engine: CoordinationEngine | None = None,
        resource_manager: ResourceManager | None = None,
        template_registry: TemplateRegistry | None = None,
    ) -> None:
        self.config = config or WorkflowOrchestrationConfig()
        self.coordination = coordination_engine or CoordinationEngine()
        self.resources = resource_manager or ResourceManager(
            global_max_concurrent=self.config.max_workflow_concurrent,
        )
        self.templates = template_registry or TemplateRegistry()

    async def execute_from_plan(
        self,
        plan: Any,  # P2-14 WorkflowPlan
        task_graph: TaskGraph,
        executor: TaskExecutor,
    ) -> WorkflowResult:
        """
        Execute a P2-14 WorkflowPlan (backward compatible).

        Converts the plan to a WorkflowDefinition and executes via
        the state machine. Functionally identical to P2-14 execution.
        """
        from ..coordination.workflow import WorkflowPlan

        if not isinstance(plan, WorkflowPlan):
            raise TypeError(f"Expected WorkflowPlan, got {type(plan)}")

        definition = WorkflowDefinition.from_plan(plan)

        # Get agent assignments from plan
        assignments: dict[str, AgentAssignment] = {}
        for step in plan.steps:
            for task_id, agent_id in step.agent_assignments.items():
                profile = self.coordination.registry.get(agent_id)
                assignments[task_id] = AgentAssignment(
                    agent_id=agent_id,
                    agent_profile=profile,
                    confidence="exact",
                    reasoning="From P2-14 plan",
                )

        return await self._run_definition(
            definition, task_graph, executor, assignments
        )

    async def execute_workflow(
        self,
        definition: WorkflowDefinition,
        task_graph: TaskGraph,
        executor: TaskExecutor,
        assignments: dict[str, AgentAssignment] | None = None,
    ) -> WorkflowResult:
        """
        Execute a P2-15 WorkflowDefinition with full conditional support.
        """
        if assignments is None:
            assignments = self.coordination.match_batch(
                [task_graph.tasks[tid] for tid in definition.get_all_task_node_ids()
                 if tid in task_graph.tasks]
            )

        return await self._run_definition(
            definition, task_graph, executor, assignments
        )

    def instantiate_template(
        self,
        template_id: str,
        workflow_id: str | None = None,
        **kwargs: Any,
    ) -> WorkflowDefinition:
        """Instantiate a workflow template with parameters."""
        template = self.templates.get(template_id)
        wid = workflow_id or f"wf-{uuid.uuid4().hex[:8]}"
        return template.instantiate(wid, **kwargs)

    async def _run_definition(
        self,
        definition: WorkflowDefinition,
        task_graph: TaskGraph,
        executor: TaskExecutor,
        assignments: dict[str, AgentAssignment],
    ) -> WorkflowResult:
        """Run a workflow definition through the state machine."""
        # Validate
        issues = definition.validate()
        if issues:
            raise ValueError(f"Invalid workflow: {issues}")

        # Create resource budget
        budget = self.resources.create_budget(
            execution_id=definition.workflow_id,
            **self.config.default_resource_limits,
        )

        # Run state machine
        machine = WorkflowStateMachine(
            definition=definition,
            task_executor=executor,
            task_graph=task_graph,
            agent_assignments=assignments,
            config=self.config.execution_config,
            resource_manager=self.resources,
        )

        try:
            result = await machine.execute()
        finally:
            self.resources.remove_budget(definition.workflow_id)

        return result
```

---

## 6. API Specifications

### 6.1 Public Interface Summary

```python
# src/omni/workflow/__init__.py — public exports

# ── Definition Language ──────────────────────────────────
from .nodes import (
    NodeType, EdgeType, Condition, NodeEdge,
    ResourceConstraint, CompensationAction, WorkflowNode,
)
from .definition import WorkflowDefinition

# ── Execution ────────────────────────────────────────────
from .state_machine import (
    WorkflowStateMachine, WorkflowContext, WorkflowResult,
    NodeExecution, NodeState,
)

# ── Resources ────────────────────────────────────────────
from .resources import ResourceManager, ResourceBudget

# ── Templates ────────────────────────────────────────────
from .templates import (
    WorkflowTemplate, TemplateParameter, TemplateRegistry,
)

# ── Expressions ──────────────────────────────────────────
from .expressions import (
    ExpressionEvaluator, ExpressionContext, ConditionEvaluationError,
)

# ── Orchestrator ─────────────────────────────────────────
from .orchestrator import (
    WorkflowOrchestrator, WorkflowOrchestrationConfig,
)
```

### 6.2 Quick Start Examples

```python
# ── Example 1: P2-14 backward compatible ─────────────────

from omni.workflow import WorkflowOrchestrator

orchestrator = WorkflowOrchestrator()
result = await orchestrator.execute_from_plan(plan, graph, executor)

# ── Example 2: Conditional workflow ──────────────────────

from omni.workflow import (
    WorkflowDefinition, WorkflowNode, NodeType, Condition, NodeEdge, EdgeType
)

definition = WorkflowDefinition(
    workflow_id="deploy-pipeline",
    name="Deploy with Fallback",
    entry_node_id="test",
    exit_node_ids=["notify"],
    nodes={
        "test": WorkflowNode(
            node_id="test",
            node_type=NodeType.TASK,
            label="Run tests",
            task_id="test-task",
            edges=[NodeEdge("check", EdgeType.UNCONDITIONAL)],
        ),
        "check": WorkflowNode(
            node_id="check",
            node_type=NodeType.IF,
            label="Tests passed?",
            condition=Condition("result.success"),
            true_branch=["deploy"],
            false_branch=["fix"],
        ),
        "deploy": WorkflowNode(
            node_id="deploy",
            node_type=NodeType.TRY_CATCH,
            label="Deploy with rollback",
            try_body=["deploy_task"],
            catch_handlers=[NodeEdge("rollback", EdgeType.UNCONDITIONAL)],
            finally_body=["notify"],
        ),
        "deploy_task": WorkflowNode(
            node_id="deploy_task",
            node_type=NodeType.TASK,
            task_id="deploy-task",
        ),
        "rollback": WorkflowNode(
            node_id="rollback",
            node_type=NodeType.COMPENSATE,
            task_id="rollback-task",
        ),
        "fix": WorkflowNode(
            node_id="fix",
            node_type=NodeType.TASK,
            task_id="fix-task",
            edges=[NodeEdge("test", EdgeType.UNCONDITIONAL)],
        ),
        "notify": WorkflowNode(
            node_id="notify",
            node_type=NodeType.TASK,
            task_id="notify-task",
            agent_id="intern",
        ),
    },
)

result = await orchestrator.execute_workflow(definition, graph, executor)

# ── Example 3: Template instantiation ────────────────────

definition = orchestrator.instantiate_template(
    "analyze-implement-test-review",
    analyze_task_id="analyze-001",
    implement_task_id="impl-001",
    test_task_id="test-001",
)
result = await orchestrator.execute_workflow(definition, graph, executor)

# ── Example 4: Loop with retry ───────────────────────────

definition = orchestrator.instantiate_template(
    "retry-until-success",
    task_id="flaky-api-call",
    max_iterations=5,
    fallback_task_id="escalate-to-human",
)
result = await orchestrator.execute_workflow(definition, graph, executor)
```

---

## 7. File Structure

```
src/omni/workflow/
├── __init__.py           # Public API exports
├── nodes.py              # WorkflowNode, NodeType, EdgeType, Condition, etc.
├── definition.py         # WorkflowDefinition (extends WorkflowPlan)
├── expressions.py        # ExpressionEvaluator, ExpressionContext
├── state_machine.py      # WorkflowStateMachine, WorkflowContext, WorkflowResult
├── resources.py          # ResourceManager, ResourceBudget
├── templates.py          # WorkflowTemplate, TemplateRegistry, built-in templates
├── orchestrator.py       # WorkflowOrchestrator (top-level facade)
└── migration.py          # P2-14 → P2-15 migration utilities

tests/
├── test_nodes.py           # Node validation, edge wiring
├── test_definition.py      # WorkflowDefinition construction, validation
├── test_expressions.py     # Condition evaluation, safety
├── test_state_machine.py   # State machine execution paths
├── test_resources.py       # Budget tracking, concurrency limits
├── test_templates.py       # Template instantiation
├── test_orchestrator.py    # End-to-end orchestration
├── test_backward_compat.py # P2-14 plans work in P2-15
└── test_integration.py     # Full pipeline tests

docs/
└── P2-15-ARCHITECTURE.md  # This document
```

---

## 8. Implementation Roadmap

### Phase 1: Core Models & Expression Evaluator (~3 hours)

| Step | File | Description | Est. |
|------|------|-------------|------|
| 1.1 | `nodes.py` | `NodeType`, `EdgeType`, `Condition`, `NodeEdge`, `ResourceConstraint`, `CompensationAction`, `WorkflowNode` | 1h |
| 1.2 | `definition.py` | `WorkflowDefinition` with validation, navigation, `from_plan()` backward compat | 1h |
| 1.3 | `expressions.py` | `ExpressionEvaluator`, `ExpressionContext`, safe eval | 1h |

### Phase 2: State Machine (~4 hours)

| Step | File | Description | Est. |
|------|------|-------------|------|
| 2.1 | `state_machine.py` | `WorkflowContext`, `NodeExecution`, core dispatch | 1h |
| 2.2 | `state_machine.py` | `_execute_task_node`, `_execute_parallel_node`, `_execute_sequence_node` | 1h |
| 2.3 | `state_machine.py` | `_execute_if_node`, `_execute_while_node`, `_execute_for_each_node` | 1h |
| 2.4 | `state_machine.py` | `_execute_try_catch_node`, error handling, compensation | 1h |

### Phase 3: Resources & Templates (~3 hours)

| Step | File | Description | Est. |
|------|------|-------------|------|
| 3.1 | `resources.py` | `ResourceBudget`, `ResourceManager` | 1h |
| 3.2 | `templates.py` | `WorkflowTemplate`, `TemplateRegistry`, 5 built-in templates | 2h |

### Phase 4: Orchestrator Facade (~2 hours)

| Step | File | Description | Est. |
|------|------|-------------|------|
| 4.1 | `orchestrator.py` | `WorkflowOrchestrator` — bridge P2-14 → P2-15 | 1h |
| 4.2 | `migration.py` | Migration helpers for P2-14 users | 0.5h |
| 4.3 | `__init__.py` | Public exports, documentation | 0.5h |

### Phase 5: Tests (~4 hours)

| Step | File | Description | Est. |
|------|------|-------------|------|
| 5.1 | `test_nodes.py`, `test_expressions.py` | Unit tests for models and evaluator | 1h |
| 5.2 | `test_definition.py`, `test_resources.py` | Definition validation, resource tracking | 1h |
| 5.3 | `test_state_machine.py` | All control-flow paths | 1h |
| 5.4 | `test_backward_compat.py`, `test_integration.py` | P2-14 compat, end-to-end | 1h |

### Phase 6: Polish & Documentation (~1 hour)

| Step | Description | Est. |
|------|-------------|------|
| 6.1 | Integration with P2-13 observability events | 0.5h |
| 6.2 | CLI commands for workflow management | 0.5h |

**Total estimated time: ~17 hours**

---

## 9. Migration Strategy: P2-14 → P2-15

### Automatic Migration

The `WorkflowDefinition.from_plan()` class method converts P2-14 plans automatically:

```
P2-14 WorkflowPlan                    P2-15 WorkflowDefinition
─────────────────                     ────────────────────────
WorkflowStep (sequential)       →     WorkflowNode(TASK)
WorkflowStep (parallel)         →     WorkflowNode(PARALLEL) + child TASK nodes
WorkflowStep (review)           →     WorkflowNode(TASK) with reviewer agent

Step dependencies (step.depends_on) → UNCONDITIONAL edges between nodes
```

### What Changes for Users

| P2-14 Pattern | P2-15 Equivalent | Migration Effort |
|--------------|-------------------|-----------------|
| `WorkflowPlan(steps=[...])` | `WorkflowDefinition.from_plan(plan)` | Automatic |
| `CoordinationEngine.coordinate()` | `WorkflowOrchestrator.execute_from_plan()` | Drop-in replace |
| `WorkflowStep(step_type=SEQUENTIAL)` | `WorkflowNode(node_type=TASK)` | Automatic |
| Custom step types | Manual `WorkflowNode` construction | New code |

### What Doesn't Change

- `TaskGraph`, `Task`, `TaskResult` models — unchanged
- `AgentRegistry`, `TaskMatcher`, `AgentAssignment` — unchanged (P2-14)
- `TaskExecutor` protocol — unchanged
- `ExecutionConfig`, `ExecutionCallbacks` — extended, not replaced
- P2-13 observability integration — extended with workflow events

### Opt-In Features

P2-15 features are opt-in. Existing code continues to work:

```python
# Old code (still works)
engine = CoordinationEngine()
result = engine.coordinate(task_graph)
plan = result.plan
# ... execute plan

# New code (adds conditional workflows)
orchestrator = WorkflowOrchestrator()
result = await orchestrator.execute_from_plan(plan, task_graph, executor)

# New code (full P2-15 features)
definition = orchestrator.instantiate_template("retry-until-success", ...)
result = await orchestrator.execute_workflow(definition, task_graph, executor)
```

---

## 10. Design Decisions Log

| Decision | Rationale |
|----------|-----------|
| **Node graph, not DAG** | Conditional branches and loops break the DAG assumption. The state machine handles arbitrary graphs safely via max_iterations and reachability checks. |
| **Python expressions, not DSL** | Users already know Python. A custom DSL adds complexity without value. Safe eval with whitelisted builtins prevents injection. |
| **State machine, not wave scheduler** | Wave scheduling can't handle IF/WHILE. The state machine is a natural fit for sequential execution with branching. |
| **Backward compatible via `from_plan()`** | Zero-migration path. P2-14 plans become P2-15 definitions. Existing code works unchanged. |
| **Templates are code, not config** | Workflow templates are Python functions that build `WorkflowDefinition` objects. This gives full expressiveness without a serialization format. |
| **Resource budgets per execution** | Prevents one runaway workflow from starving others. Quotas are enforced at the node level via semaphores. |
| **Compensation as first-class nodes** | Rollback actions are explicit nodes in the graph, not callbacks. This makes failure recovery auditable and composable. |
| **TRY_CATCH stack for error routing** | Errors propagate up the call stack until a TRY_CATCH handler catches them. Mirrors Python's exception model. |
| **FOR_EACH iterates over expressions** | The collection is evaluated once at loop start (not re-evaluated). Prevents mid-loop mutations from causing confusion. |
| **`WorkflowContext` is the single source of truth** | All runtime state (node results, variables, iteration counters) lives in one place. Simplifies serialization and debugging. |

---

## 11. Error & Recovery Taxonomy

### Failure Classification

| Category | Examples | Strategy |
|----------|---------|----------|
| **Transient** | Rate limit (429), timeout, 500 error | Retry with exponential backoff |
| **Permanent** | Auth failure, invalid input, model not found | Fail immediately, route to error handler |
| **Resource** | Token budget exceeded, concurrency limit | Wait and retry, or escalate |
| **Logic** | Condition evaluation error, missing node | Fail workflow (configuration bug) |

### Recovery Mechanisms

```
Task fails
  ├─ Transient? → Retry (exponential backoff, max_retries)
  │               └─ Retries exhausted? → Route to error edge or TRY_CATCH
  │
  ├─ Permanent? → Run compensation actions
  │               └─ Route to error edge or TRY_CATCH
  │               └─ No handler? → WorkflowAbort
  │
  └─ Resource?  → Wait for capacity
                  └─ Timeout? → Route to error edge
```

### Compensation Chain

```
TRY_CATCH catches error
  └─ Run catch handler
       └─ Handler can access: error type, failed node's result
       └─ Handler can execute: COMPENSATE nodes (rollback tasks)
  └─ Run finally body (always executes)
```

---

## 12. Observability Integration (P2-13)

New events emitted by P2-15:

| Event | Payload | Trigger |
|-------|---------|---------|
| `workflow_started` | workflow_id, name, node_count | Workflow begins |
| `node_evaluating` | node_id, node_type, expression | IF/WHILE/FOR_EACH evaluating condition |
| `condition_result` | node_id, expression, result, context_summary | Condition evaluated |
| `branch_taken` | node_id, branch (true/false), target_node_ids | IF branch selected |
| `loop_iteration` | node_id, iteration, max_iterations | WHILE/FOR_EACH iteration |
| `loop_completed` | node_id, total_iterations | Loop finished |
| `compensation_started` | node_id, failed_node_id | Compensation action begins |
| `compensation_completed` | node_id, success | Compensation action finishes |
| `workflow_completed` | workflow_id, status, duration, cost | Workflow finishes |

These extend the existing `CoordinationObserver` protocol from P2-14.

---

## 13. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Infinite loops | High | `max_iterations` enforced on every WHILE/FOR_EACH. Global wall-clock timeout as safety net. |
| Expression injection | Medium | Safe eval with whitelisted builtins. No file I/O, no imports, no `__` attributes. |
| State machine complexity | Medium | Each node type handler is <50 lines. State transitions are explicit. Full logging. |
| Memory growth in long workflows | Medium | Loop body states are cleared each iteration. Node results are lightweight (TaskResult). |
| Backward compatibility regression | Low | Dedicated `test_backward_compat.py` suite. `from_plan()` is a thin wrapper. |
| Resource exhaustion | Medium | Per-workflow budgets with hard limits. Global semaphore for cross-workflow concurrency. |

---

## 14. Open Questions

1. **Workflow serialization:** Should workflows be serializable to JSON/YAML for storage and sharing? (Proposed: Phase 2 enhancement — first make them work as Python objects.)

2. **Nested sub-workflows:** Should `SUB_WORKFLOW` nodes be supported in the initial version? (Proposed: Stub in Phase 1, implement in Phase 2.)

3. **Dynamic agent re-assignment:** Should the state machine be able to change agent assignments mid-workflow based on results? (Proposed: Yes, via variables + condition-based agent overrides.)

4. **Workflow versioning:** How do we handle updates to workflow templates while instances are running? (Proposed: Templates are immutable once instantiated; new versions create new template IDs.)

5. **Maximum workflow complexity:** What's the practical limit on node count? (Proposed: No hard limit, but warn at 100+ nodes. Resource budgets prevent abuse.)

---

## 15. Summary

P2-15 extends the Omni-LLM orchestration layer from simple DAG execution to full conditional workflow support:

- **7 node types** (TASK, PARALLEL, SEQUENCE, IF, WHILE, FOR_EACH, TRY_CATCH, COMPENSATE, SUB_WORKFLOW) provide complete control flow
- **Python expression evaluator** for conditions with safe eval sandbox
- **State machine execution** handles arbitrary control flow including loops and error handling
- **Resource manager** enforces per-workflow budgets for concurrency, tokens, and cost
- **Template library** provides 5 built-in patterns (dev pipeline, explore-plan, parallel review, retry loop, safe deploy)
- **Full backward compatibility** with P2-14 via `WorkflowDefinition.from_plan()`
- **17-hour estimated implementation** across 6 phases

The architecture deliberately mirrors Python's own control flow constructs (if/else, while, for, try/except) to minimize the learning curve while maximizing expressiveness.
