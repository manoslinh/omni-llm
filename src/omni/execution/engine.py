"""
Parallel execution engine for task graphs.
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from ..task.models import Task, TaskGraph, TaskResult, TaskStatus
from .config import ExecutionCallbacks, ExecutionConfig, ExecutionContext
from .db import ExecutionDB
from .executor import TaskExecutor
from .models import (
    ExecutionAbortedError,
    ExecutionMetrics,
    ExecutionResult,
    ExecutionStatus,
)
from .scheduler import Scheduler

logger = logging.getLogger(__name__)


class ParallelExecutionEngine:
    """Execute a TaskGraph in parallel, respecting dependencies."""

    def __init__(
        self,
        graph: TaskGraph,
        executor: TaskExecutor,
        config: ExecutionConfig | None = None,
        callbacks: ExecutionCallbacks | None = None,
        db_path: str | Path = "omni_executions.db",
        worktree_manager: Any | None = None,  # WorktreeManager from omni.git
    ) -> None:
        """
        Args:
            graph: TaskGraph to execute
            executor: TaskExecutor implementation
            config: Execution configuration
            callbacks: Optional callbacks for execution events
            db_path: Path to SQLite database for persistence
            worktree_manager: Optional WorktreeManager for filesystem isolation
        """
        self.graph = graph
        self.executor = executor
        self.config = config or ExecutionConfig()
        self.callbacks = callbacks or ExecutionCallbacks()
        self.db = ExecutionDB(db_path)
        self.worktree_manager = worktree_manager

        self.execution_id = uuid.uuid4().hex[:16]
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None

        self.results: dict[str, TaskResult] = {}
        self.metrics = ExecutionMetrics(
            execution_id=self.execution_id,
            total_tasks=graph.size,
        )

        self._scheduler: Scheduler | None = None
        self._cancelled = False
        self._state_change_count = 0

    async def execute(self) -> ExecutionResult:
        """Run the entire task graph to completion or failure.

        Returns:
            ExecutionResult with all task outcomes and aggregate metrics.

        Raises:
            ExecutionAbortedError: If fail_fast=True and a non-retryable
                task fails.
        """
        self.started_at = datetime.now()
        logger.info(f"Starting execution {self.execution_id} of graph '{self.graph.name}'")

        # Save initial state to DB
        self.db.save_execution(
            execution_id=self.execution_id,
            graph_name=self.graph.name,
            config=self.config,
            status=ExecutionStatus.RUNNING,
        )

        # Initialize scheduler
        self._scheduler = Scheduler(
            graph=self.graph,
            config=self.config,
            task_executor=self._create_task_executor(),
            on_task_complete=self._handle_task_complete,
            on_propagate_skip=self._propagate_skip,
        )

        # Run the scheduler
        try:
            await self._scheduler.run()
        except Exception as e:
            logger.error(f"Execution {self.execution_id} failed: {e}")
            raise

        # Determine final status
        status = self._determine_final_status()
        self.completed_at = datetime.now()

        # Update metrics
        self._update_metrics()

        # Save final state to DB
        self.db.save_execution(
            execution_id=self.execution_id,
            graph_name=self.graph.name,
            config=self.config,
            status=status,
            completed_at=self.completed_at,
        )

        # Create result
        assert self.started_at is not None, "Execution started_at should be set"
        result = ExecutionResult(
            execution_id=self.execution_id,
            graph_name=self.graph.name,
            status=status,
            results=self.results,
            metrics=self.metrics,
            started_at=self.started_at,
            completed_at=self.completed_at,
            dead_letter=[],  # TODO: Track tasks that exhausted retries
            config=self.config.__dict__,
        )

        # Fire completion callback
        if self.callbacks.on_execution_complete:
            self.callbacks._safe_call(self.callbacks.on_execution_complete, result)

        logger.info(f"Execution {self.execution_id} completed with status {status}")
        return result

    async def cancel(self) -> None:
        """Gracefully cancel execution.

        In-flight tasks will complete their current iteration.
        Tasks not yet started will be marked CANCELLED.
        """
        if self._scheduler is None:
            raise RuntimeError("Execution not started")

        self._cancelled = True
        await self._scheduler.cancel()

    def get_status(self) -> ExecutionMetrics:
        """Snapshot of current execution metrics."""
        self._update_metrics()
        return self.metrics

    def get_result(self, task_id: str) -> TaskResult | None:
        """Get result for a specific task (None if not yet completed)."""
        return self.results.get(task_id)

    @classmethod
    async def resume(
        cls,
        execution_id: str,
        executor: TaskExecutor,
        db_path: str | Path = "omni_executions.db",
        config: ExecutionConfig | None = None,
        callbacks: ExecutionCallbacks | None = None,
    ) -> ExecutionResult:
        """Resume a previously interrupted execution.

        Loads state from SQLite, skips completed tasks, re-runs
        pending/running tasks.
        """
        db = ExecutionDB(db_path)

        # Load execution state
        try:
            graph_name, started_at, completed_at, status, loaded_config = db.load_execution(
                execution_id
            )
        except KeyError:
            raise ValueError(f"Execution {execution_id} not found") from None

        if status in (ExecutionStatus.COMPLETED, ExecutionStatus.CANCELLED):
            raise ValueError(f"Cannot resume execution in terminal state: {status}")

        # Load task states (not used yet - graph reconstruction needed)
        _ = db.load_task_states(execution_id)

        # We need to reconstruct the TaskGraph
        # For now, raise NotImplementedError since we need the original graph
        # In a real implementation, we'd need to store the graph structure too
        raise NotImplementedError(
            "Graph reconstruction from checkpoint not yet implemented. "
            "Need to store graph structure in DB."
        )

    def _create_task_executor(self) -> Callable[[Task], Awaitable[Any]]:
        """Create a wrapper that calls the executor with proper context."""

        async def execute_task(task: Task) -> Any:
            """Execute a single task with context."""
            # Create execution context (without worktree_path initially)
            context = ExecutionContext(
                dependency_results={
                    dep_id: self.results[dep_id]
                    for dep_id in task.dependencies
                    if dep_id in self.results
                },
                execution_id=self.execution_id,
                task_index=len(self.results) + 1,
                total_tasks=self.graph.size,
            )

            # Fire start callback
            if self.callbacks.on_task_start:
                self.callbacks._safe_call(self.callbacks.on_task_start, task.task_id, task)

            # Execute with timeout, optionally with worktree isolation
            try:
                if self.worktree_manager:
                    # Import here to avoid circular imports
                    from ..git.worktree import WorktreeEnv
                    
                    async with WorktreeEnv(
                        manager=self.worktree_manager,
                        task_id=task.task_id,
                        base_branch="main",
                        cleanup_on_success=True,
                        cleanup_on_failure=False,
                    ) as env:
                        # Update context with worktree path if env created successfully
                        if env and env.path:
                            context.worktree_path = str(env.path)
                        result = await asyncio.wait_for(
                            self.executor.execute(task, context),
                            timeout=self.config.timeout_per_task,
                        )
                else:
                    # Execute without worktree isolation
                    result = await asyncio.wait_for(
                        self.executor.execute(task, context),
                        timeout=self.config.timeout_per_task,
                    )
                return result
            except TimeoutError:
                raise TimeoutError(f"Task {task.task_id} timed out after {self.config.timeout_per_task}s") from None

        return execute_task

    def _handle_task_complete(
        self,
        task_id: str,
        status: TaskStatus,
        result: TaskResult | dict | None,
        error_msg: str | None,
    ) -> None:
        """Handle task completion from scheduler."""
        task = self.graph.tasks[task_id]

        # Handle result (could be TaskResult or dict from tests)
        task_result = None
        if result is not None:
            if isinstance(result, TaskResult):
                task_result = result
                self.results[task_id] = task_result
            else:
                # Convert dict to TaskResult (for backward compatibility with tests)
                task_result = TaskResult(
                    task_id=task_id,
                    status=status,
                    outputs=result.get("outputs", {}),
                    errors=result.get("errors", []),
                    metadata=result.get("metadata", {}),
                    tokens_used=result.get("tokens_used", 0),
                    cost=result.get("cost", 0.0),
                )
                self.results[task_id] = task_result
        else:
            # Create TaskResult for failed/cancelled/skipped tasks
            task_result = TaskResult(
                task_id=task_id,
                status=status,
                outputs={},
                errors=[error_msg] if error_msg else [],
                metadata={"error": error_msg} if error_msg else {},
                tokens_used=0,
                cost=0.0,
            )
            self.results[task_id] = task_result

        # Update task status (already done by scheduler, but ensure consistency)
        task.status = status

        # Fire appropriate callback
        if status == TaskStatus.COMPLETED and task_result and self.callbacks.on_task_complete:
            self.callbacks._safe_call(self.callbacks.on_task_complete, task_id, task_result)
        elif status == TaskStatus.FAILED and self.callbacks.on_task_fail:
            # We need the exception - for now pass a generic one
            error = Exception(error_msg or "Task failed")
            self.callbacks._safe_call(self.callbacks.on_task_fail, task_id, task, error)

        # Checkpoint to DB
        self._state_change_count += 1
        if self._state_change_count % self.config.checkpoint_interval == 0:
            self._checkpoint_task(task_id, task_result, error_msg)

        # Update metrics and fire progress callback
        self._update_metrics()
        if self.callbacks.on_progress:
            self.callbacks._safe_call(self.callbacks.on_progress, self.metrics)

        # Check for fail-fast condition
        if (status == TaskStatus.FAILED and
            self.config.fail_fast):
            # Create partial result
            self.completed_at = datetime.now()
            # When fail-fast triggers, status is FAILED (not PARTIAL)
            self._update_metrics()

            assert self.started_at is not None, "Execution started_at should be set"
            partial_result = ExecutionResult(
                execution_id=self.execution_id,
                graph_name=self.graph.name,
                status=ExecutionStatus.FAILED,  # Fail-fast means execution failed
                results=self.results,
                metrics=self.metrics,
                started_at=self.started_at,
                completed_at=self.completed_at,
                dead_letter=[task_id],
                config=self.config.__dict__,
            )

            raise ExecutionAbortedError(task_id, partial_result)

    def _propagate_skip(self, failed_task_id: str) -> None:
        """Propagate skip to downstream tasks."""
        if not self.config.skip_on_dep_failure:
            return

        # Get all tasks that depend on the failed task
        to_skip = set()
        stack = [failed_task_id]

        while stack:
            current_id = stack.pop()
            task = self.graph.tasks[current_id]

            # Skip this task if not already terminal
            if not task.is_terminal:
                task.status = TaskStatus.SKIPPED
                to_skip.add(current_id)

                # Add its dependents to the stack
                for dependent in self.graph.get_dependents(current_id):
                    stack.append(dependent.task_id)

        # Save skipped tasks to DB
        for task_id in to_skip:
            self.db.save_task_state(
                execution_id=self.execution_id,
                task_id=task_id,
                status=TaskStatus.SKIPPED,
                error_msg="Skipped due to dependency failure",
            )

    def _checkpoint_task(
        self,
        task_id: str,
        result: TaskResult | None,
        error_msg: str | None,
    ) -> None:
        """Save task state to DB."""
        task = self.graph.tasks[task_id]

        self.db.save_task_state(
            execution_id=self.execution_id,
            task_id=task_id,
            status=task.status,
            retry_count=task.retry_count,
            result=result,
            error_msg=error_msg,
            started_at=self.started_at,  # TODO: Track actual task start time
            completed_at=datetime.now() if task.is_terminal else None,
        )

    def _determine_final_status(self) -> ExecutionStatus:
        """Determine final execution status based on task outcomes."""
        if self._cancelled:
            return ExecutionStatus.CANCELLED

        # Count task statuses
        status_counts: dict[TaskStatus, int] = defaultdict(int)
        for task in self.graph.tasks.values():
            status_counts[task.status] += 1

        completed = status_counts.get(TaskStatus.COMPLETED, 0)
        failed = status_counts.get(TaskStatus.FAILED, 0)
        skipped = status_counts.get(TaskStatus.SKIPPED, 0)
        cancelled = status_counts.get(TaskStatus.CANCELLED, 0)

        total = self.graph.size

        if completed == total:
            return ExecutionStatus.COMPLETED
        elif (completed + failed + skipped + cancelled) == total:
            # All tasks are terminal
            if failed > 0:
                return ExecutionStatus.FAILED
            else:
                # No failures, just completed/skipped/cancelled
                return ExecutionStatus.COMPLETED
        else:
            # Mixed state (shouldn't happen if execution finished)
            return ExecutionStatus.PARTIAL

    def _update_metrics(self) -> None:
        """Update execution metrics."""
        # Count task statuses
        status_counts: dict[TaskStatus, int] = defaultdict(int)
        for task in self.graph.tasks.values():
            status_counts[task.status] += 1

        # Update metrics
        self.metrics.completed = status_counts.get(TaskStatus.COMPLETED, 0)
        self.metrics.failed = status_counts.get(TaskStatus.FAILED, 0)
        self.metrics.skipped = status_counts.get(TaskStatus.SKIPPED, 0)
        self.metrics.cancelled = status_counts.get(TaskStatus.CANCELLED, 0)
        self.metrics.running = status_counts.get(TaskStatus.RUNNING, 0)
        self.metrics.pending = status_counts.get(TaskStatus.PENDING, 0)

        # Update token and cost totals
        self.metrics.total_tokens_used = sum(
            r.tokens_used for r in self.results.values()
        )
        self.metrics.total_cost = sum(
            r.cost for r in self.results.values()
        )

        # Calculate wall clock time
        if self.started_at:
            end_time = self.completed_at or datetime.now()
            self.metrics.wall_clock_seconds = (
                end_time - self.started_at
            ).total_seconds()

        # Calculate parallel efficiency (simplified)
        # TODO: Implement proper parallel efficiency calculation
        if self.metrics.wall_clock_seconds > 0 and self.metrics.total_tasks > 0:
            # Very rough estimate
            avg_task_time = self.metrics.wall_clock_seconds / max(1, self.metrics.completed)
            sequential_time = avg_task_time * self.metrics.total_tasks
            self.metrics.parallel_efficiency = min(
                1.0,
                sequential_time / max(0.1, self.metrics.wall_clock_seconds)
            )
