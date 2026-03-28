"""
Parallel execution engine for task graphs.

Provides ParallelExecutionEngine for executing TaskGraph objects in parallel
with dependency resolution, retry logic, and persistence.
"""

from .config import ExecutionCallbacks, ExecutionConfig, ExecutionContext
from .db import ExecutionDB
from .engine import ParallelExecutionEngine
from .executor import MockTaskExecutor, TaskExecutor
from .models import (
    ExecutionAbortedError,
    ExecutionMetrics,
    ExecutionResult,
    ExecutionStatus,
    TaskExecutionError,
    TaskFatalError,
)
from .scheduler import Scheduler

__all__ = [
    # Main engine
    "ParallelExecutionEngine",

    # Configuration
    "ExecutionConfig",
    "ExecutionCallbacks",
    "ExecutionContext",

    # Executors
    "TaskExecutor",
    "MockTaskExecutor",

    # Models
    "ExecutionResult",
    "ExecutionMetrics",
    "ExecutionStatus",
    "TaskExecutionError",
    "TaskFatalError",
    "ExecutionAbortedError",

    # Persistence
    "ExecutionDB",

    # Scheduler (mostly internal)
    "Scheduler",
]
