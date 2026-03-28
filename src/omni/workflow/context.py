"""
Workflow context for P2-15: Workflow Orchestration.

Defines the runtime context that tracks workflow execution state,
node results, variables, and resource usage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class NodeStatus(StrEnum):
    """Status of a workflow node during execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ExecutionError(Exception):
    """Base exception for workflow execution errors."""

    pass


@dataclass
class NodeResult:
    """Result of executing a workflow node."""

    node_id: str
    status: NodeStatus
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    error_type: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Whether the node execution was successful."""
        return self.status == NodeStatus.SUCCESS

    @property
    def failed(self) -> bool:
        """Whether the node execution failed."""
        return self.status == NodeStatus.FAILED

    @property
    def duration(self) -> float | None:
        """Duration in seconds, if both timestamps are available."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class ResourceSnapshot:
    """Snapshot of resource usage at a point in time."""

    tokens_used: int = 0
    cost_incurred: float = 0.0
    active_tasks: int = 0
    max_concurrent_tasks: int = 0
    start_time: datetime | None = None
    current_time: datetime | None = None

    @property
    def duration(self) -> float | None:
        """Duration in seconds since start, if start_time is available."""
        if self.start_time and self.current_time:
            return (self.current_time - self.start_time).total_seconds()
        return None


@dataclass
class WorkflowContext:
    """
    Runtime context for workflow execution.

    This is the single source of truth for workflow state during execution.
    It tracks node results, user-defined variables, iteration counters,
    and resource usage.
    """

    workflow_id: str
    execution_id: str
    node_results: dict[str, NodeResult] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)  # User-defined state
    iteration_counters: dict[str, int] = field(
        default_factory=dict
    )  # node_id → iteration count
    resource_usage: ResourceSnapshot = field(default_factory=ResourceSnapshot)
    execution_stack: list[str] = field(
        default_factory=list
    )  # Stack of active control nodes
    error_stack: list[tuple[str, str]] = field(
        default_factory=list
    )  # (node_id, error) for TRY_CATCH
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    # ── Node result management ─────────────────────────────────

    def get_node_result(self, node_id: str) -> NodeResult | None:
        """Get the result for a node, if it exists."""
        return self.node_results.get(node_id)

    def set_node_result(self, node_id: str, result: NodeResult) -> None:
        """Set the result for a node."""
        self.node_results[node_id] = result

    def mark_node_started(self, node_id: str) -> None:
        """Mark a node as started."""
        if node_id not in self.node_results:
            self.node_results[node_id] = NodeResult(
                node_id=node_id,
                status=NodeStatus.RUNNING,
                started_at=datetime.now(),
            )
        else:
            self.node_results[node_id].status = NodeStatus.RUNNING
            self.node_results[node_id].started_at = datetime.now()

    def mark_node_success(
        self, node_id: str, outputs: dict[str, Any] | None = None
    ) -> None:
        """Mark a node as successfully completed."""
        if node_id not in self.node_results:
            self.node_results[node_id] = NodeResult(
                node_id=node_id,
                status=NodeStatus.SUCCESS,
                outputs=outputs or {},
                completed_at=datetime.now(),
            )
        else:
            self.node_results[node_id].status = NodeStatus.SUCCESS
            self.node_results[node_id].outputs = outputs or {}
            self.node_results[node_id].completed_at = datetime.now()

    def mark_node_failed(
        self, node_id: str, error: str, error_type: str | None = None
    ) -> None:
        """Mark a node as failed."""
        if node_id not in self.node_results:
            self.node_results[node_id] = NodeResult(
                node_id=node_id,
                status=NodeStatus.FAILED,
                error=error,
                error_type=error_type,
                completed_at=datetime.now(),
            )
        else:
            self.node_results[node_id].status = NodeStatus.FAILED
            self.node_results[node_id].error = error
            self.node_results[node_id].error_type = error_type
            self.node_results[node_id].completed_at = datetime.now()

    def mark_node_skipped(self, node_id: str) -> None:
        """Mark a node as skipped."""
        if node_id not in self.node_results:
            self.node_results[node_id] = NodeResult(
                node_id=node_id,
                status=NodeStatus.SKIPPED,
                completed_at=datetime.now(),
            )
        else:
            self.node_results[node_id].status = NodeStatus.SKIPPED
            self.node_results[node_id].completed_at = datetime.now()

    # ── Variable management ────────────────────────────────────

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get a workflow variable."""
        return self.variables.get(name, default)

    def set_variable(self, name: str, value: Any) -> None:
        """Set a workflow variable."""
        self.variables[name] = value

    def update_variables(self, updates: dict[str, Any]) -> None:
        """Update multiple workflow variables."""
        self.variables.update(updates)

    # ── Iteration management ───────────────────────────────────

    def get_iteration_count(self, node_id: str) -> int:
        """Get the iteration count for a loop node."""
        return self.iteration_counters.get(node_id, 0)

    def increment_iteration(self, node_id: str) -> int:
        """Increment and return the iteration count for a loop node."""
        current = self.iteration_counters.get(node_id, 0)
        self.iteration_counters[node_id] = current + 1
        return current + 1

    def reset_iteration(self, node_id: str) -> None:
        """Reset the iteration count for a loop node."""
        self.iteration_counters[node_id] = 0

    # ── Execution stack management ─────────────────────────────

    def push_to_stack(self, node_id: str) -> None:
        """Push a node onto the execution stack."""
        self.execution_stack.append(node_id)

    def pop_from_stack(self) -> str | None:
        """Pop a node from the execution stack."""
        if self.execution_stack:
            return self.execution_stack.pop()
        return None

    def peek_stack(self) -> str | None:
        """Peek at the top of the execution stack."""
        if self.execution_stack:
            return self.execution_stack[-1]
        return None

    def is_in_stack(self, node_id: str) -> bool:
        """Check if a node is in the execution stack."""
        return node_id in self.execution_stack

    # ── Error stack management ─────────────────────────────────

    def push_error(self, node_id: str, error: str) -> None:
        """Push an error onto the error stack."""
        self.error_stack.append((node_id, error))

    def pop_error(self) -> tuple[str, str] | None:
        """Pop an error from the error stack."""
        if self.error_stack:
            return self.error_stack.pop()
        return None

    def peek_error(self) -> tuple[str, str] | None:
        """Peek at the top of the error stack."""
        if self.error_stack:
            return self.error_stack[-1]
        return None

    def clear_errors(self) -> None:
        """Clear all errors from the error stack."""
        self.error_stack.clear()

    # ── Resource tracking ──────────────────────────────────────

    def update_resource_usage(
        self,
        tokens_used: int = 0,
        cost_incurred: float = 0.0,
        active_tasks: int = 0,
        max_concurrent_tasks: int = 0,
    ) -> None:
        """Update resource usage metrics."""
        self.resource_usage.tokens_used += tokens_used
        self.resource_usage.cost_incurred += cost_incurred
        self.resource_usage.active_tasks = active_tasks
        self.resource_usage.max_concurrent_tasks = max(
            self.resource_usage.max_concurrent_tasks, max_concurrent_tasks
        )
        self.resource_usage.current_time = datetime.now()

        if not self.resource_usage.start_time:
            self.resource_usage.start_time = datetime.now()

    # ── Context for expression evaluation ──────────────────────

    def get_evaluation_context(
        self, current_node_id: str | None = None
    ) -> dict[str, Any]:
        """
        Get a context dictionary for evaluating expressions.

        This context is passed to Condition.evaluate() and other
        expression evaluators.
        """
        context: dict[str, Any] = {
            "variables": self.variables,
            "node_results": self.node_results,
            "iteration": self.get_iteration_count(current_node_id)
            if current_node_id
            else 0,
            "resource": self.resource_usage,
        }

        # Add current node result if available
        if current_node_id and current_node_id in self.node_results:
            context["result"] = self.node_results[current_node_id]

        return context

    # ── Serialization ──────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "node_results": {
                node_id: {
                    "node_id": result.node_id,
                    "status": result.status.value,
                    "outputs": result.outputs,
                    "error": result.error,
                    "error_type": result.error_type,
                    "started_at": result.started_at.isoformat()
                    if result.started_at
                    else None,
                    "completed_at": result.completed_at.isoformat()
                    if result.completed_at
                    else None,
                    "metadata": result.metadata,
                }
                for node_id, result in self.node_results.items()
            },
            "variables": self.variables,
            "iteration_counters": self.iteration_counters,
            "resource_usage": {
                "tokens_used": self.resource_usage.tokens_used,
                "cost_incurred": self.resource_usage.cost_incurred,
                "active_tasks": self.resource_usage.active_tasks,
                "max_concurrent_tasks": self.resource_usage.max_concurrent_tasks,
                "start_time": self.resource_usage.start_time.isoformat()
                if self.resource_usage.start_time
                else None,
                "current_time": self.resource_usage.current_time.isoformat()
                if self.resource_usage.current_time
                else None,
            },
            "execution_stack": self.execution_stack,
            "error_stack": self.error_stack,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowContext:
        """Create context from dictionary."""
        from datetime import datetime

        # Parse node results
        node_results: dict[str, NodeResult] = {}
        for node_id, result_data in data.get("node_results", {}).items():
            started_at = None
            if result_data.get("started_at"):
                started_at = datetime.fromisoformat(result_data["started_at"])

            completed_at = None
            if result_data.get("completed_at"):
                completed_at = datetime.fromisoformat(result_data["completed_at"])

            node_results[node_id] = NodeResult(
                node_id=result_data["node_id"],
                status=NodeStatus(result_data["status"]),
                outputs=result_data.get("outputs", {}),
                error=result_data.get("error"),
                error_type=result_data.get("error_type"),
                started_at=started_at,
                completed_at=completed_at,
                metadata=result_data.get("metadata", {}),
            )

        # Parse resource usage
        resource_data = data.get("resource_usage", {})
        start_time = None
        if resource_data.get("start_time"):
            start_time = datetime.fromisoformat(resource_data["start_time"])

        current_time = None
        if resource_data.get("current_time"):
            current_time = datetime.fromisoformat(resource_data["current_time"])

        resource_usage = ResourceSnapshot(
            tokens_used=resource_data.get("tokens_used", 0),
            cost_incurred=resource_data.get("cost_incurred", 0.0),
            active_tasks=resource_data.get("active_tasks", 0),
            max_concurrent_tasks=resource_data.get("max_concurrent_tasks", 0),
            start_time=start_time,
            current_time=current_time,
        )

        # Parse created_at
        created_at = datetime.now()
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        return cls(
            workflow_id=data["workflow_id"],
            execution_id=data["execution_id"],
            node_results=node_results,
            variables=data.get("variables", {}),
            iteration_counters=data.get("iteration_counters", {}),
            resource_usage=resource_usage,
            execution_stack=data.get("execution_stack", []),
            error_stack=data.get("error_stack", []),
            metadata=data.get("metadata", {}),
            created_at=created_at,
        )
