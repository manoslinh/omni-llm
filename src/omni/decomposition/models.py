"""
Extended data models for task decomposition.

Provides Subtask, SubtaskType, and DecompositionResult for the
Task Decomposition Engine, building on the base Task model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from omni.task.models import Task, TaskGraph


class SubtaskType(StrEnum):
    """Classification of subtask kinds within a decomposition."""

    PREPARATION = "preparation"
    ANALYSIS = "analysis"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    INTEGRATION = "integration"
    CLEANUP = "cleanup"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value


@dataclass
class Subtask(Task):
    """A subtask within a decomposition.

    Extends Task with decomposition-specific fields like subtask_type,
    depth level, parent reference, and estimated effort.
    """

    subtask_type: SubtaskType = SubtaskType.UNKNOWN
    depth: int = 0
    parent_id: str | None = None
    effort_score: float = 1.0  # Relative effort (1.0 = baseline)
    required_capabilities: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate subtask fields after initialization."""
        super().__post_init__()
        if self.depth < 0:
            raise ValueError(f"depth must be non-negative, got {self.depth}")
        if self.effort_score < 0:
            raise ValueError(
                f"effort_score must be non-negative, got {self.effort_score}"
            )

    @classmethod
    def from_task(
        cls,
        task: Task,
        subtask_type: SubtaskType = SubtaskType.UNKNOWN,
        depth: int = 0,
        parent_id: str | None = None,
        effort_score: float = 1.0,
        required_capabilities: list[str] | None = None,
    ) -> Subtask:
        """Create a Subtask from an existing Task.

        Args:
            task: Base task to convert
            subtask_type: Type classification for the subtask
            depth: Nesting depth in decomposition tree
            parent_id: ID of parent task (None for top-level)
            effort_score: Relative effort estimate
            required_capabilities: List of required capabilities

        Returns:
            New Subtask instance
        """
        return cls(
            description=task.description,
            task_type=task.task_type,
            task_id=task.task_id,
            status=task.status,
            dependencies=task.dependencies.copy(),
            complexity=task.complexity,
            context=task.context.copy(),
            tags=task.tags.copy(),
            priority=task.priority,
            max_retries=task.max_retries,
            retry_count=task.retry_count,
            subtask_type=subtask_type,
            depth=depth,
            parent_id=parent_id,
            effort_score=effort_score,
            required_capabilities=required_capabilities or [],
        )


@dataclass
class DecompositionResult:
    """Result of decomposing a task into subtasks.

    Contains the decomposition tree (as a TaskGraph), metadata about
    the decomposition process, and validation results.
    """

    # The original task that was decomposed
    original_task: Task

    # The resulting task graph with subtasks
    task_graph: TaskGraph

    # Decomposition metadata
    strategy_used: str = "unknown"
    total_subtasks: int = 0
    max_depth: int = 0
    estimated_total_tokens: int = 0
    estimated_total_effort: float = 0.0

    # Validation results
    is_valid: bool = True
    validation_issues: list[str] = field(default_factory=list)

    # Decomposition reasoning
    reasoning: str = ""
    confidence: float = 0.0  # 0.0 to 1.0

    def __post_init__(self) -> None:
        """Validate and compute derived fields."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}"
            )

        # Auto-compute derived fields
        self.total_subtasks = self.task_graph.size
        self.estimated_total_tokens = self.task_graph.total_estimated_tokens

        # Compute max depth from subtasks
        subtasks = [
            t for t in self.task_graph.tasks.values() if isinstance(t, Subtask)
        ]
        if subtasks:
            self.max_depth = max(st.depth for st in subtasks)
            self.estimated_total_effort = sum(st.effort_score for st in subtasks)

        # Run validation
        issues = self.task_graph.validate()
        if issues:
            self.is_valid = False
            self.validation_issues.extend(issues)

    @property
    def is_atomic(self) -> bool:
        """Whether the decomposition resulted in atomic (leaf) tasks only."""
        return all(
            isinstance(t, Subtask) and t.subtask_type != SubtaskType.UNKNOWN
            for t in self.task_graph.tasks.values()
        )

    @property
    def subtasks_by_type(self) -> dict[SubtaskType, list[Subtask]]:
        """Group subtasks by their type."""
        result: dict[SubtaskType, list[Subtask]] = {}
        for task in self.task_graph.tasks.values():
            if isinstance(task, Subtask):
                result.setdefault(task.subtask_type, []).append(task)
        return result

    @property
    def leaf_subtasks(self) -> list[Subtask]:
        """Get leaf subtasks (no dependents)."""
        leaves = self.task_graph.leaves
        return [t for t in leaves if isinstance(t, Subtask)]

    @property
    def root_subtasks(self) -> list[Subtask]:
        """Get root subtasks (no dependencies)."""
        roots = self.task_graph.roots
        return [t for t in roots if isinstance(t, Subtask)]

    def summary(self) -> dict[str, Any]:
        """Get a summary of the decomposition result."""
        type_counts: dict[str, int] = {}
        for task in self.task_graph.tasks.values():
            if isinstance(task, Subtask):
                key = str(task.subtask_type)
                type_counts[key] = type_counts.get(key, 0) + 1

        return {
            "original_task_id": self.original_task.task_id,
            "strategy": self.strategy_used,
            "total_subtasks": self.total_subtasks,
            "max_depth": self.max_depth,
            "estimated_tokens": self.estimated_total_tokens,
            "estimated_effort": round(self.estimated_total_effort, 2),
            "is_valid": self.is_valid,
            "confidence": round(self.confidence, 2),
            "type_distribution": type_counts,
            "validation_issues": self.validation_issues[:5],  # First 5 issues
        }
