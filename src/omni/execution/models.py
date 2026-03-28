"""
Execution result and metrics models for parallel execution engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from ..task.models import TaskResult


class ExecutionStatus(StrEnum):
    """Overall status of an execution."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"

    def __str__(self) -> str:
        return self.value


@dataclass
class ExecutionMetrics:
    """Metrics collected during execution."""

    execution_id: str
    total_tasks: int
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    cancelled: int = 0
    running: int = 0
    pending: int = 0
    total_tokens_used: int = 0
    total_cost: float = 0.0
    wall_clock_seconds: float = 0.0
    parallel_efficiency: float = 0.0  # actual_speedup / theoretical_max_speedup

    def update_from_results(self, results: dict[str, TaskResult]) -> None:
        """Update counts based on task results."""
        self.completed = sum(1 for r in results.values() if r.status == "completed")
        self.failed = sum(1 for r in results.values() if r.status == "failed")
        self.skipped = sum(1 for r in results.values() if r.status == "skipped")
        self.cancelled = sum(1 for r in results.values() if r.status == "cancelled")
        self.running = 0  # Will be updated by engine
        self.pending = self.total_tasks - (self.completed + self.failed + self.skipped + self.cancelled + self.running)
        
        # Update token and cost totals
        self.total_tokens_used = sum(r.tokens_used for r in results.values())
        self.total_cost = sum(r.cost for r in results.values())


@dataclass
class ExecutionResult:
    """Aggregate result of a full graph execution."""

    execution_id: str
    graph_name: str
    status: ExecutionStatus
    results: dict[str, TaskResult]  # task_id → result
    metrics: ExecutionMetrics
    started_at: datetime
    completed_at: datetime | None = None
    dead_letter: list[str] = field(default_factory=list)  # task_ids that exhausted retries
    config: dict[str, Any] = field(default_factory=dict)  # Execution config used

    @property
    def success(self) -> bool:
        """Whether execution completed successfully."""
        return self.status == ExecutionStatus.COMPLETED

    @property
    def duration_seconds(self) -> float | None:
        """Duration in seconds if completed, else None."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class TaskExecutionError(Exception):
    """Recoverable task failure (triggers retry)."""
    pass


class TaskFatalError(Exception):
    """Non-recoverable task failure (no retry)."""
    pass


class ExecutionAbortedError(Exception):
    """Execution aborted due to fail_fast."""
    
    def __init__(self, failed_task_id: str, result: ExecutionResult) -> None:
        self.failed_task_id = failed_task_id
        self.result = result
        super().__init__(f"Execution aborted due to failure of task {failed_task_id}")