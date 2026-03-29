"""
Parallel execution engine for task graphs.

Provides ParallelExecutionEngine for executing TaskGraph objects in parallel
with dependency resolution, retry logic, and persistence.
"""

from .config import ExecutionCallbacks, ExecutionConfig, ExecutionContext
from .db import ExecutionDB
from .engine import ParallelExecutionEngine
from .executor import LLMTaskExecutor, MockTaskExecutor, TaskExecutor
from .models import (
    ExecutionAbortedError,
    ExecutionMetrics,
    ExecutionResult,
    ExecutionStatus,
    TaskExecutionError,
    TaskFatalError,
)
from .policies import (
    BalancedPolicy,
    CostAwarePolicy,
    DeadlinePolicy,
    FairPolicy,
    FIFOPolicy,
    PriorityPolicy,
    SchedulingContext,
    SchedulingPolicy,
    SchedulingPolicyBase,
    SchedulingScore,
    get_policy,
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
    "LLMTaskExecutor",

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

    # Scheduling policies (P2-16)
    "SchedulingPolicy",
    "SchedulingPolicyBase",
    "SchedulingScore",
    "SchedulingContext",
    "FIFOPolicy",
    "PriorityPolicy",
    "DeadlinePolicy",
    "CostAwarePolicy",
    "FairPolicy",
    "BalancedPolicy",
    "get_policy",
]
