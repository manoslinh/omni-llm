"""
Execution configuration and callbacks.
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from ..task.models import Task, TaskResult
from .models import ExecutionResult, ExecutionMetrics


@dataclass(frozen=True)
class ExecutionConfig:
    """Configuration for parallel execution."""

    max_concurrent: int = 5  # Max tasks running simultaneously
    retry_enabled: bool = True  # Whether to retry failed tasks
    backoff_base: float = 2.0  # Base seconds for exponential backoff
    backoff_max: float = 60.0  # Maximum backoff delay
    timeout_per_task: float = 300.0  # Per-task timeout in seconds
    fail_fast: bool = False  # Abort on first non-retryable failure
    skip_on_dep_failure: bool = True  # Skip tasks whose deps failed
    checkpoint_interval: int = 1  # Save to DB every N state changes

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        if self.backoff_base <= 0:
            raise ValueError("backoff_base must be positive")
        if self.backoff_max < self.backoff_base:
            raise ValueError("backoff_max must be >= backoff_base")
        if self.timeout_per_task <= 0:
            raise ValueError("timeout_per_task must be positive")
        if self.checkpoint_interval < 1:
            raise ValueError("checkpoint_interval must be at least 1")


@dataclass
class ExecutionContext:
    """Context passed to task executors."""

    dependency_results: dict[str, TaskResult]  # Results from completed deps
    execution_id: str
    task_index: int  # Position in execution
    total_tasks: int


@dataclass
class ExecutionCallbacks:
    """Optional callbacks for execution events."""

    on_task_start: Callable[[str, Task], None] | None = None
    on_task_complete: Callable[[str, TaskResult], None] | None = None
    on_task_fail: Callable[[str, Task, Exception], None] | None = None
    on_progress: Callable[[ExecutionMetrics], None] | None = None
    on_execution_complete: Callable[[ExecutionResult], None] | None = None

    def _safe_call(self, callback: Callable | None, *args: Any) -> None:
        """Safely call a callback, swallowing any exceptions."""
        if callback is not None:
            try:
                callback(*args)
            except Exception:
                # Log but don't crash execution
                pass