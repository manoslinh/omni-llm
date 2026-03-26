"""
Core data models for task decomposition.

Provides Task, TaskGraph, TaskStatus, TaskResult, and ComplexityEstimate
for breaking down complex work into manageable, dependency-ordered units.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import networkx as nx


class TaskStatus(StrEnum):
    """Lifecycle status of a task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    def __str__(self) -> str:
        return self.value


class TaskType(StrEnum):
    """Classification of task kinds."""

    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    TESTING = "testing"
    REFACTORING = "refactoring"
    DOCUMENTATION = "documentation"
    ANALYSIS = "analysis"
    CONFIGURATION = "configuration"
    DEPLOYMENT = "deployment"
    CUSTOM = "custom"

    def __str__(self) -> str:
        return self.value


@dataclass
class ComplexityEstimate:
    """Heuristic complexity scoring for a task.

    Scores are on a 1-10 scale where:
    - 1-3: Simple (well-understood, few decisions)
    - 4-6: Moderate (some ambiguity, multiple steps)
    - 7-9: Complex (significant unknowns, high coupling)
    - 10:  Extreme (research-level, novel problem)
    """

    code_complexity: int = 1
    integration_complexity: int = 1
    testing_complexity: int = 1
    unknown_factor: int = 1
    estimated_tokens: int = 0
    reasoning: str = ""

    def __post_init__(self) -> None:
        for name, value in [
            ("code_complexity", self.code_complexity),
            ("integration_complexity", self.integration_complexity),
            ("testing_complexity", self.testing_complexity),
            ("unknown_factor", self.unknown_factor),
        ]:
            if not 1 <= value <= 10:
                raise ValueError(
                    f"{name} must be between 1 and 10, got {value}"
                )
        if self.estimated_tokens < 0:
            raise ValueError(
                f"estimated_tokens must be non-negative, got {self.estimated_tokens}"
            )

    @property
    def overall_score(self) -> float:
        """Weighted average complexity score (1-10).

        Weights: code=0.3, integration=0.25, testing=0.2, unknown=0.25
        Unknown factor gets high weight because surprises dominate.
        """
        return (
            self.code_complexity * 0.3
            + self.integration_complexity * 0.25
            + self.testing_complexity * 0.2
            + self.unknown_factor * 0.25
        )

    @property
    def tier(self) -> str:
        """Recommended agent tier based on overall score."""
        score = self.overall_score
        if score <= 3.0:
            return "intern"
        elif score <= 5.5:
            return "coder"
        elif score <= 7.5:
            return "reader"
        else:
            return "thinker"


@dataclass
class TaskResult:
    """Result data from executing a task."""

    task_id: str
    status: TaskStatus
    outputs: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    cost: float = 0.0

    def __post_init__(self) -> None:
        if self.status == TaskStatus.PENDING:
            raise ValueError(
                "TaskResult cannot have PENDING status; "
                "result is only created after execution"
            )
        if self.status == TaskStatus.RUNNING:
            raise ValueError(
                "TaskResult cannot have RUNNING status; "
                "result is only created after execution"
            )
        if self.tokens_used < 0:
            raise ValueError(
                f"tokens_used must be non-negative, got {self.tokens_used}"
            )
        if self.cost < 0.0:
            raise ValueError(f"cost must be non-negative, got {self.cost}")

    @property
    def success(self) -> bool:
        """Whether the task completed successfully."""
        return self.status == TaskStatus.COMPLETED

    @property
    def has_errors(self) -> bool:
        """Whether the result contains any errors."""
        return len(self.errors) > 0


@dataclass
class Task:
    """A single unit of work in a task decomposition.

    Tasks are the atomic building blocks of a TaskGraph. Each task
    has a type, description, and optional dependencies on other tasks.
    """

    description: str
    task_type: TaskType = TaskType.CUSTOM
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[str] = field(default_factory=list)
    complexity: ComplexityEstimate | None = None
    context: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    priority: int = 0
    max_retries: int = 3
    retry_count: int = 0

    def __post_init__(self) -> None:
        if not self.description or not self.description.strip():
            raise ValueError("Task description cannot be empty")
        if self.priority < 0:
            raise ValueError(
                f"priority must be non-negative, got {self.priority}"
            )
        if self.max_retries < 0:
            raise ValueError(
                f"max_retries must be non-negative, got {self.max_retries}"
            )
        if self.retry_count < 0:
            raise ValueError(
                f"retry_count must be non-negative, got {self.retry_count}"
            )

    @property
    def is_terminal(self) -> bool:
        """Whether the task is in a terminal state."""
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)

    @property
    def can_retry(self) -> bool:
        """Whether the task can be retried after failure."""
        return self.status == TaskStatus.FAILED and self.retry_count < self.max_retries

    @property
    def effective_complexity(self) -> ComplexityEstimate:
        """Get complexity, falling back to a default estimate."""
        if self.complexity is not None:
            return self.complexity
        return ComplexityEstimate(
            reasoning="No explicit complexity estimate; using defaults"
        )

    def mark_running(self) -> None:
        """Transition task to RUNNING state."""
        if self.status != TaskStatus.PENDING:
            raise ValueError(
                f"Cannot start task in {self.status} state; "
                f"must be PENDING"
            )
        self.status = TaskStatus.RUNNING

    def mark_completed(self) -> None:
        """Transition task to COMPLETED state."""
        if self.status != TaskStatus.RUNNING:
            raise ValueError(
                f"Cannot complete task in {self.status} state; "
                f"must be RUNNING"
            )
        self.status = TaskStatus.COMPLETED

    def mark_failed(self) -> None:
        """Transition task to FAILED state."""
        if self.status != TaskStatus.RUNNING:
            raise ValueError(
                f"Cannot fail task in {self.status} state; "
                f"must be RUNNING"
            )
        self.status = TaskStatus.FAILED

    def retry(self) -> None:
        """Reset task for retry after failure."""
        if not self.can_retry:
            raise ValueError(
                f"Cannot retry: status={self.status}, "
                f"retry_count={self.retry_count}, max_retries={self.max_retries}"
            )
        self.retry_count += 1
        self.status = TaskStatus.PENDING


@dataclass
class TaskGraph:
    """Directed graph of tasks with dependency resolution.

    Manages a collection of tasks and their dependency relationships.
    Provides topological ordering for execution scheduling.
    """

    name: str = "task_graph"
    tasks: dict[str, Task] = field(default_factory=dict)
    _graph: nx.DiGraph = field(default_factory=nx.DiGraph, repr=False)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("TaskGraph name cannot be empty")
        # Rebuild graph from existing tasks
        for task_id in self.tasks:
            self._graph.add_node(task_id)

    def add_task(self, task: Task) -> None:
        """Add a task to the graph."""
        if task.task_id in self.tasks:
            raise ValueError(f"Task with id '{task.task_id}' already exists")
        self.tasks[task.task_id] = task
        self._graph.add_node(task.task_id)

        # Add dependency edges
        for dep_id in task.dependencies:
            if dep_id not in self.tasks:
                raise ValueError(
                    f"Dependency '{dep_id}' not found in graph "
                    f"for task '{task.task_id}'"
                )
            self._graph.add_edge(dep_id, task.task_id)

    def remove_task(self, task_id: str) -> Task:
        """Remove a task from the graph.

        Raises ValueError if other tasks depend on this one.
        """
        if task_id not in self.tasks:
            raise KeyError(f"Task '{task_id}' not found")

        # Check if other tasks depend on this one
        dependents = list(self._graph.successors(task_id))
        if dependents:
            raise ValueError(
                f"Cannot remove task '{task_id}': "
                f"tasks {dependents} depend on it"
            )

        task = self.tasks.pop(task_id)
        self._graph.remove_node(task_id)

        # Clean up dependency references in other tasks
        for other in self.tasks.values():
            if task_id in other.dependencies:
                other.dependencies.remove(task_id)

        return task

    def get_task(self, task_id: str) -> Task:
        """Get a task by ID."""
        if task_id not in self.tasks:
            raise KeyError(f"Task '{task_id}' not found")
        return self.tasks[task_id]

    def get_dependencies(self, task_id: str) -> list[Task]:
        """Get all direct dependencies of a task."""
        task = self.get_task(task_id)
        return [self.tasks[dep_id] for dep_id in task.dependencies]

    def get_dependents(self, task_id: str) -> list[Task]:
        """Get all tasks that directly depend on this task."""
        self.get_task(task_id)  # Validate exists
        return [
            self.tasks[tid]
            for tid in self._graph.successors(task_id)
        ]

    def get_ready_tasks(self) -> list[Task]:
        """Get tasks that are PENDING with all dependencies COMPLETED."""
        ready: list[Task] = []
        for task in self.tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            deps_completed = all(
                self.tasks[dep_id].status == TaskStatus.COMPLETED
                for dep_id in task.dependencies
                if dep_id in self.tasks
            )
            if deps_completed:
                ready.append(task)
        # Sort by priority (higher first)
        ready.sort(key=lambda t: t.priority, reverse=True)
        return ready

    def topological_order(self) -> list[str]:
        """Get tasks in dependency-respecting execution order.

        Raises CycleError if the graph contains cycles.
        """
        try:
            return list(nx.topological_sort(self._graph))
        except nx.NetworkXUnfeasible as exc:
            cycles = list(nx.simple_cycles(self._graph))
            raise CycleError(
                f"Dependency cycle detected: {cycles}"
            ) from exc

    def validate(self) -> list[str]:
        """Validate the graph structure. Returns list of issues found."""
        issues: list[str] = []

        # Check for cycles
        if not nx.is_directed_acyclic_graph(self._graph):
            cycles = list(nx.simple_cycles(self._graph))
            issues.append(f"Dependency cycles found: {cycles}")

        # Check for missing dependencies
        for task in self.tasks.values():
            for dep_id in task.dependencies:
                if dep_id not in self.tasks:
                    issues.append(
                        f"Task '{task.task_id}' depends on "
                        f"missing task '{dep_id}'"
                    )

        # Check for self-dependencies
        for task in self.tasks.values():
            if task.task_id in task.dependencies:
                issues.append(
                    f"Task '{task.task_id}' depends on itself"
                )

        return issues

    @property
    def is_valid(self) -> bool:
        """Whether the graph has no structural issues."""
        return len(self.validate()) == 0

    @property
    def size(self) -> int:
        """Number of tasks in the graph."""
        return len(self.tasks)

    @property
    def edge_count(self) -> int:
        """Number of dependency edges in the graph."""
        return int(self._graph.number_of_edges())

    @property
    def roots(self) -> list[Task]:
        """Tasks with no dependencies (entry points)."""
        return [
            self.tasks[tid]
            for tid in self._graph.nodes()
            if self._graph.in_degree(tid) == 0
        ]

    @property
    def leaves(self) -> list[Task]:
        """Tasks that no other task depends on (terminal tasks)."""
        return [
            self.tasks[tid]
            for tid in self._graph.nodes()
            if self._graph.out_degree(tid) == 0
        ]

    @property
    def completed_fraction(self) -> float:
        """Fraction of tasks that are COMPLETED."""
        if not self.tasks:
            return 0.0
        completed = sum(
            1 for t in self.tasks.values()
            if t.status == TaskStatus.COMPLETED
        )
        return completed / len(self.tasks)

    @property
    def is_complete(self) -> bool:
        """Whether all tasks are COMPLETED."""
        return all(
            t.status == TaskStatus.COMPLETED
            for t in self.tasks.values()
        )

    @property
    def has_failures(self) -> bool:
        """Whether any task has FAILED."""
        return any(
            t.status == TaskStatus.FAILED
            for t in self.tasks.values()
        )

    @property
    def failed_tasks(self) -> list[Task]:
        """All tasks in FAILED state."""
        return [
            t for t in self.tasks.values()
            if t.status == TaskStatus.FAILED
        ]

    @property
    def total_estimated_tokens(self) -> int:
        """Sum of estimated tokens across all tasks with estimates."""
        return sum(
            t.effective_complexity.estimated_tokens
            for t in self.tasks.values()
        )

    def summary(self) -> dict[str, Any]:
        """Get a summary of the graph state."""
        status_counts: dict[str, int] = {}
        for task in self.tasks.values():
            key = str(task.status)
            status_counts[key] = status_counts.get(key, 0) + 1

        return {
            "name": self.name,
            "total_tasks": self.size,
            "edges": self.edge_count,
            "status_counts": status_counts,
            "completed_fraction": round(self.completed_fraction, 2),
            "is_complete": self.is_complete,
            "has_failures": self.has_failures,
            "total_estimated_tokens": self.total_estimated_tokens,
        }


class CycleError(Exception):
    """Raised when a dependency cycle is detected in a TaskGraph."""
