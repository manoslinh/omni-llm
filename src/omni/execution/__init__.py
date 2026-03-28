"""
Parallel execution engine for task graphs.

Provides ParallelExecutionEngine for executing TaskGraph objects in parallel
with dependency resolution, retry logic, and persistence.
"""

from .engine import ParallelExecutionEngine
from .config import ExecutionConfig, ExecutionCallbacks, ExecutionContext
from .executor import TaskExecutor, MockTaskExecutor
from .models import (
    ExecutionResult,
    ExecutionMetrics,
    ExecutionStatus,
    TaskExecutionError,
    TaskFatalError,
    ExecutionAbortedError,
)
from .db import ExecutionDB
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