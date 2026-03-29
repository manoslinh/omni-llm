"""
Core scheduling algorithm for parallel execution.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from ..scheduling.policies import (
    FIFOPolicy,
    SchedulingContext,
    SchedulingPolicyBase,
    SchedulingScore,
)
from ..task.models import Task, TaskGraph, TaskStatus
from .config import ExecutionConfig
from .models import ExecutionAbortedError, TaskExecutionError, TaskFatalError

logger = logging.getLogger(__name__)


class Scheduler:
    """Core scheduling logic for parallel task execution."""

    def __init__(
        self,
        graph: TaskGraph,
        config: ExecutionConfig,
        task_executor: Callable[[Task], Awaitable[Any]],
        on_task_complete: Callable[[str, TaskStatus, dict | None, str | None], None],
        on_propagate_skip: Callable[[str], None],
        policy: SchedulingPolicyBase | None = None,
    ) -> None:
        """
        Args:
            graph: TaskGraph to execute
            config: Execution configuration
            task_executor: Function that takes a Task and returns an asyncio.Task
            on_task_complete: Callback when task completes (task_id, status, result, error)
            on_propagate_skip: Callback to propagate skip to downstream tasks
            policy: Scheduling policy to use (defaults to FIFO for backward compatibility)
        """
        self.graph = graph
        self.config = config
        self.task_executor = task_executor
        self.on_task_complete = on_task_complete
        self.on_propagate_skip = on_propagate_skip
        self.policy = policy or FIFOPolicy()

        self.running_tasks: dict[str, asyncio.Task] = {}
        self.completed_results: dict[str, dict] = {}
        self.failed_tasks: set[str] = set()
        self.skipped_tasks: set[str] = set()
        self.cancelled_tasks: set[str] = set()

        self.semaphore = asyncio.Semaphore(config.max_concurrent)
        self.should_cancel = False
        self.execution_started = False
        self.scheduling_decisions: list[SchedulingScore] = []  # for observability

    async def run(self) -> None:
        """Main scheduling loop."""
        self.execution_started = True

        # Validate graph
        issues = self.graph.validate()
        if issues:
            raise ValueError(f"Invalid task graph: {issues}")

        logger.info(f"Starting execution of graph '{self.graph.name}' with {self.graph.size} tasks")

        while not self._is_execution_complete() and not self.should_cancel:
            # Get ready tasks (pending with all deps completed)
            ready_tasks = self._get_ready_tasks()

            if not ready_tasks and not self.running_tasks:
                # No ready tasks and nothing running - check for deadlock
                if self._has_deadlock():
                    logger.warning("Deadlock detected - no tasks can progress")
                    break
                # Might be waiting for running tasks to complete
                await asyncio.sleep(0.1)
                continue

            # Schedule as many tasks as concurrency allows
            scheduled = await self._schedule_tasks(ready_tasks)

            if scheduled == 0 and self.running_tasks:
                # No tasks could be scheduled, wait for some to complete
                await self._wait_for_completion()

        # Wait for any remaining running tasks to complete
        if self.running_tasks:
            logger.info(f"Waiting for {len(self.running_tasks)} running tasks to complete")
            await asyncio.wait(self.running_tasks.values())

        logger.info(f"Execution complete. Completed: {len(self.completed_results)}, "
                   f"Failed: {len(self.failed_tasks)}, Skipped: {len(self.skipped_tasks)}")

    async def cancel(self) -> None:
        """Cancel execution gracefully."""
        self.should_cancel = True
        logger.info("Cancellation requested")

        # Cancel all running tasks
        for task_id, task_future in self.running_tasks.items():
            task_future.cancel()
            self.cancelled_tasks.add(task_id)

        # Wait for cancellations to complete
        if self.running_tasks:
            await asyncio.wait(self.running_tasks.values())

        # Mark pending tasks as cancelled
        for task in self.graph.tasks.values():
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                self.cancelled_tasks.add(task.task_id)
                self.on_task_complete(task.task_id, TaskStatus.CANCELLED, None, "Cancelled by user")

    def _is_execution_complete(self) -> bool:
        """Check if execution is complete."""
        if self.should_cancel:
            return True

        # All tasks are in terminal states
        for task in self.graph.tasks.values():
            if not task.is_terminal:
                return False
        return True

    def _get_ready_tasks(self) -> list[Task]:
        """Get tasks that are ready to execute."""
        ready = []

        for task in self.graph.tasks.values():
            if task.status != TaskStatus.PENDING:
                continue

            # Check if all dependencies are completed
            deps_completed = True
            for dep_id in task.dependencies:
                dep_task = self.graph.tasks[dep_id]
                if dep_task.status != TaskStatus.COMPLETED:
                    deps_completed = False
                    # If dependency failed and we should skip, mark this task as skipped
                    if (dep_task.status == TaskStatus.FAILED and
                        self.config.skip_on_dep_failure and
                        task.task_id not in self.skipped_tasks):
                        self._mark_task_skipped(task.task_id, dep_task.task_id)
                    break

            if deps_completed and task.task_id not in self.skipped_tasks:
                ready.append(task)

        # Apply scheduling policy if we have ready tasks
        if ready:
            context = self._build_scheduling_context(ready)
            scores = self.policy.rank_tasks(context)
            self.scheduling_decisions.extend(scores)

            # Sort tasks by composite score (higher first)
            score_map = {s.task_id: s.composite_score for s in scores}
            ready.sort(key=lambda t: score_map.get(t.task_id, 0.0), reverse=True)

        return ready

    def _build_scheduling_context(self, ready_tasks: list[Task]) -> SchedulingContext:
        """Build scheduling context for policy decisions."""
        # Extract execution info from running tasks
        running_info = {}
        for task_id, task_future in self.running_tasks.items():
            # Get task start time if available from the future
            started_at = getattr(task_future, '_started_at', None)

            running_info[task_id] = {
                "workflow_id": self.graph.name,
                "started_at": started_at,
            }

        # Build deadline info (extract from task metadata if available)
        deadline_info = {}
        for task in ready_tasks:
            # Check for deadline in task metadata
            deadline = getattr(task, 'deadline', None)
            if deadline:
                deadline_info[task.task_id] = deadline
            else:
                # Also check task context for deadline (backward compatibility)
                if hasattr(task, 'context') and isinstance(task.context, dict):
                    deadline_val = task.context.get('deadline')
                    if deadline_val:
                        deadline_info[task.task_id] = float(deadline_val)

        # Get resource snapshot
        resource_snapshot = {
            "concurrent_used": len(self.running_tasks),
            "concurrent_available": self.config.max_concurrent - len(self.running_tasks),
            "total_tasks": self.graph.size,
        }

        # Default agent availability (all available)
        # In a real implementation, this would come from coordination engine
        agent_availability = {
            "intern": True,
            "coder": True,
            "reader": True,
            "thinker": True,
        }

        # Get cost budget remaining if cost tracker is available
        cost_budget_remaining = None
        if hasattr(self, 'cost_tracker'):
            # This would query the cost tracker for remaining budget
            # For now, return None as placeholder
            pass

        # Get execution history if workload tracker is available
        execution_history: list[Any] = []
        if hasattr(self, 'workload_tracker'):
            # This would get recent execution records
            # For now, return empty list as placeholder
            pass

        return SchedulingContext(
            ready_tasks=ready_tasks,
            running_tasks=running_info,
            workflow_id=self.graph.name,
            resource_snapshot=resource_snapshot,
            agent_availability=agent_availability,
            deadline_info=deadline_info,
            cost_budget_remaining=cost_budget_remaining,
            execution_history=execution_history,
        )

    def _mark_task_skipped(self, task_id: str, failed_task_id: str | None = None) -> None:
        """Mark a task as skipped and propagate to its dependents."""
        if task_id in self.skipped_tasks:
            return

        task = self.graph.tasks[task_id]
        task.status = TaskStatus.SKIPPED
        self.skipped_tasks.add(task_id)

        # Call completion callback
        self.on_task_complete(task_id, TaskStatus.SKIPPED, None, "Skipped due to dependency failure")

        # Propagate to dependents (pass the original failed task ID if available)
        propagate_from = failed_task_id or task_id
        self.on_propagate_skip(propagate_from)

    async def _schedule_tasks(self, ready_tasks: list[Task]) -> int:
        """Schedule tasks up to concurrency limit."""
        scheduled = 0

        for task in ready_tasks:
            if self.semaphore.locked():
                break

            async with self.semaphore:
                # Create and track the task
                coro = self._execute_task_with_retry(task)
                task_future = asyncio.create_task(coro)
                # Add start time for scheduling context
                task_future._started_at = time.time()  # type: ignore
                self.running_tasks[task.task_id] = task_future
                scheduled += 1

                # Mark task as running
                task.mark_running()
                logger.debug(f"Started task {task.task_id}: {task.description[:50]}...")

        return scheduled

    async def _execute_task_with_retry(self, task: Task) -> None:
        """Execute a task with retry logic."""
        retry_count = 0
        last_error = None

        while retry_count <= task.max_retries and not self.should_cancel:
            try:
                # Execute the task
                task_future = self.task_executor(task)
                result = await task_future

                # Task completed successfully
                task.mark_completed()
                self.completed_results[task.task_id] = result
                self.on_task_complete(task.task_id, TaskStatus.COMPLETED, result, None)
                return

            except TaskFatalError as e:
                # Fatal error - no retry
                last_error = str(e)
                task.mark_failed()
                self.failed_tasks.add(task.task_id)
                self.on_task_complete(task.task_id, TaskStatus.FAILED, None, last_error)
                break

            except TaskExecutionError as e:
                # Recoverable error - retry if allowed
                last_error = str(e)
                retry_count += 1

                if retry_count <= task.max_retries and self.config.retry_enabled:
                    # Calculate backoff delay
                    delay = self._calculate_backoff(retry_count)
                    logger.warning(f"Task {task.task_id} failed, retry {retry_count}/{task.max_retries} after {delay:.1f}s: {e}")

                    # Increment retry count but keep task running
                    task.retry_count += 1
                    await asyncio.sleep(delay)
                else:
                    # No more retries
                    task.mark_failed()
                    self.failed_tasks.add(task.task_id)
                    self.on_task_complete(task.task_id, TaskStatus.FAILED, None, last_error)
                    break

            except ExecutionAbortedError:
                # Fail-fast triggered - re-raise immediately
                raise

            except asyncio.CancelledError:
                # Task was cancelled
                task.status = TaskStatus.CANCELLED
                self.cancelled_tasks.add(task.task_id)
                self.on_task_complete(task.task_id, TaskStatus.CANCELLED, None, "Cancelled")
                raise

            except Exception as e:
                # Unexpected error
                last_error = f"Unexpected error: {e}"
                logger.exception(f"Unexpected error executing task {task.task_id}")
                task.mark_failed()
                self.failed_tasks.add(task.task_id)
                self.on_task_complete(task.task_id, TaskStatus.FAILED, None, last_error)
                break

        # If we get here and task is still running, mark it as failed
        if task.status == TaskStatus.RUNNING:
            task.mark_failed()
            self.failed_tasks.add(task.task_id)
            error_msg = last_error or "Unknown error after retries exhausted"
            self.on_task_complete(task.task_id, TaskStatus.FAILED, None, error_msg)

    def _calculate_backoff(self, retry_count: int) -> float:
        """Calculate exponential backoff delay."""
        delay = self.config.backoff_base * (2 ** (retry_count - 1))
        return float(min(delay, self.config.backoff_max))

    async def _wait_for_completion(self) -> None:
        """Wait for any running task to complete."""
        if not self.running_tasks:
            return

        done, _ = await asyncio.wait(
            self.running_tasks.values(),
            return_when=asyncio.FIRST_COMPLETED
        )

        # Clean up completed tasks
        for task_future in done:
            # Find which task this future corresponds to
            task_id = None
            for tid, future in self.running_tasks.items():
                if future is task_future:
                    task_id = tid
                    break

            if task_id:
                del self.running_tasks[task_id]

                # Check for exception
                try:
                    task_future.result()
                except ExecutionAbortedError:
                    raise  # Re-raise immediately for fail-fast
                except asyncio.CancelledError:
                    pass  # Expected for cancelled tasks
                except Exception as e:
                    logger.debug(f"Task {task_id} future raised: {e}")

    def _has_deadlock(self) -> bool:
        """Check if there's a deadlock (no tasks can progress)."""
        # If there are running tasks, not a deadlock yet
        if self.running_tasks:
            return False

        # Check if any task is pending with all dependencies met
        for task in self.graph.tasks.values():
            if task.status == TaskStatus.PENDING:
                deps_met = True
                for dep_id in task.dependencies:
                    dep_task = self.graph.tasks[dep_id]
                    if dep_task.status != TaskStatus.COMPLETED:
                        deps_met = False
                        break
                if deps_met:
                    return False  # At least one task can run

        # No tasks can run
        return True

    def get_progress_stats(self) -> dict[str, int]:
        """Get current progress statistics."""
        return {
            "total": self.graph.size,
            "completed": len(self.completed_results),
            "failed": len(self.failed_tasks),
            "skipped": len(self.skipped_tasks),
            "cancelled": len(self.cancelled_tasks),
            "running": len(self.running_tasks),
            "pending": self.graph.size - (
                len(self.completed_results) +
                len(self.failed_tasks) +
                len(self.skipped_tasks) +
                len(self.cancelled_tasks) +
                len(self.running_tasks)
            ),
        }
