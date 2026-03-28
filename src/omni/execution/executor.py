"""
Task executor protocol and implementations.
"""

import asyncio
import random
from typing import Protocol

from ..task.models import Task, TaskResult, TaskStatus
from .config import ExecutionContext
from .models import TaskExecutionError, TaskFatalError


class TaskExecutor(Protocol):
    """Pluggable task execution backend."""

    async def execute(
        self,
        task: Task,
        context: ExecutionContext,
    ) -> TaskResult:
        """Execute a task and return its result.

        Args:
            task: The task to execute (includes description, type, complexity).
            context: Accumulated results from dependency tasks.

        Returns:
            TaskResult with status, outputs, tokens_used, cost.

        Raises:
            TaskExecutionError: On recoverable failures (triggers retry).
            TaskFatalError: On non-recoverable failures (no retry).
        """
        ...


class MockTaskExecutor:
    """Mock executor for testing without real LLM calls."""

    def __init__(
        self,
        success_rate: float = 0.8,
        avg_delay: float = 0.5,
        delay_variance: float = 0.3,
        token_cost_per_task: int = 100,
        cost_per_token: float = 0.00002,
    ) -> None:
        """
        Args:
            success_rate: Probability of task success (0.0 to 1.0)
            avg_delay: Average execution delay in seconds
            delay_variance: Variance in delay (uniform distribution)
            token_cost_per_task: Mock tokens used per task
            cost_per_token: Mock cost per token
        """
        self.success_rate = success_rate
        self.avg_delay = avg_delay
        self.delay_variance = delay_variance
        self.token_cost_per_task = token_cost_per_task
        self.cost_per_token = cost_per_token

    async def execute(
        self,
        task: Task,
        context: ExecutionContext,
    ) -> TaskResult:
        """Execute a task with configurable mock behavior."""
        
        # Simulate execution delay
        delay = self.avg_delay + random.uniform(
            -self.delay_variance, self.delay_variance
        )
        delay = max(0.1, delay)  # Minimum delay
        await asyncio.sleep(delay)

        # Determine success/failure
        if random.random() < self.success_rate:
            # Success case
            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.COMPLETED,
                outputs={
                    "result": f"Mock result for task {task.task_id}",
                    "context_size": len(context.dependency_results),
                    "execution_id": context.execution_id,
                },
                tokens_used=self.token_cost_per_task,
                cost=self.token_cost_per_task * self.cost_per_token,
                metadata={
                    "mock_executor": True,
                    "delay_seconds": delay,
                    "success_rate": self.success_rate,
                },
            )
        else:
            # Failure case - simulate different error types
            error_type = random.choice(["recoverable", "fatal", "transient"])
            
            if error_type == "fatal":
                raise TaskFatalError(f"Mock fatal error for task {task.task_id}")
            elif error_type == "transient":
                # Transient error that should trigger retry
                raise TaskExecutionError(f"Mock transient error for task {task.task_id}")
            else:
                # Recoverable error but task completes with errors
                return TaskResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    errors=[f"Mock recoverable error for task {task.task_id}"],
                    tokens_used=self.token_cost_per_task // 2,  # Partial tokens used
                    cost=(self.token_cost_per_task // 2) * self.cost_per_token,
                    metadata={
                        "mock_executor": True,
                        "delay_seconds": delay,
                        "error_type": "recoverable",
                    },
                )