# P2-11: Parallel Execution Engine

## Overview

The Parallel Execution Engine provides a robust framework for executing task graphs in parallel while respecting dependencies, with support for retries, skip propagation, persistence, and configurable execution policies.

## Architecture

The engine consists of several key components:

1. **ParallelExecutionEngine** - Main orchestrator
2. **Scheduler** - Core scheduling algorithm
3. **TaskExecutor** - Pluggable execution backend
4. **ExecutionDB** - SQLite persistence layer
5. **ExecutionConfig** - Configuration and callbacks

## Key Features

### Parallel Execution with Dependencies
- Execute task graphs in parallel while respecting dependencies
- Configurable concurrency limits
- Priority-based scheduling

### Fault Tolerance
- Retry with exponential backoff
- Skip propagation on dependency failure
- Fail-fast mode for critical failures
- Fatal vs. recoverable error distinction

### Persistence
- SQLite database for execution state
- Checkpointing for crash recovery
- Execution history and metrics

### Observability
- Comprehensive execution metrics
- Progress callbacks
- Task lifecycle events

## Usage

### Basic Example

```python
from src.omni.task.models import Task, TaskGraph
from src.omni.execution.engine import ParallelExecutionEngine
from src.omni.execution.executor import MockTaskExecutor
from src.omni.execution.config import ExecutionConfig

# Create a task graph
graph = TaskGraph(name="example")
task_a = Task(description="Task A", task_id="A")
task_b = Task(description="Task B", task_id="B", dependencies=["A"])
graph.add_task(task_a)
graph.add_task(task_b)

# Create engine with mock executor
executor = MockTaskExecutor(success_rate=0.9)
engine = ParallelExecutionEngine(
    graph=graph,
    executor=executor,
    config=ExecutionConfig(max_concurrent=2),
)

# Execute
result = await engine.execute()
print(f"Status: {result.status}")
print(f"Completed: {result.metrics.completed}/{result.metrics.total_tasks}")
```

### Configuration Options

```python
config = ExecutionConfig(
    max_concurrent=5,           # Maximum parallel tasks
    retry_enabled=True,         # Enable retries
    backoff_base=2.0,           # Exponential backoff base
    backoff_max=60.0,           # Maximum backoff delay
    timeout_per_task=300.0,     # Per-task timeout
    fail_fast=False,            # Abort on first non-retryable failure
    skip_on_dep_failure=True,   # Skip tasks whose dependencies failed
    checkpoint_interval=1,      # Save to DB every N state changes
)
```

### Custom Executors

Implement the `TaskExecutor` protocol:

```python
from src.omni.execution.executor import TaskExecutor
from src.omni.task.models import Task
from src.omni.execution.config import ExecutionContext

class MyExecutor(TaskExecutor):
    async def execute(self, task: Task, context: ExecutionContext) -> TaskResult:
        # Your implementation here
        pass
```

## Testing

The implementation includes comprehensive tests covering:

- Linear chain execution
- Diamond graph parallelism
- Skip propagation
- Retry with backoff
- SQLite persistence
- Concurrency limiting
- Fail-fast behavior
- Cancellation

Run tests with:
```bash
pytest tests/test_execution_*.py -v
```

## Database Schema

The SQLite database (`omni_executions.db`) contains:

### `executions` table
- `execution_id` TEXT PRIMARY KEY
- `graph_name` TEXT NOT NULL
- `started_at` TEXT NOT NULL
- `completed_at` TEXT
- `status` TEXT NOT NULL DEFAULT 'running'
- `config_json` TEXT NOT NULL

### `task_states` table
- `execution_id` TEXT NOT NULL
- `task_id` TEXT NOT NULL
- `status` TEXT NOT NULL
- `started_at` TEXT
- `completed_at` TEXT
- `retry_count` INTEGER NOT NULL DEFAULT 0
- `result_json` TEXT
- `error_msg` TEXT
- PRIMARY KEY (execution_id, task_id)
- FOREIGN KEY (execution_id) REFERENCES executions(execution_id) ON DELETE CASCADE

## Status Codes

### ExecutionStatus
- `RUNNING` - Execution in progress
- `COMPLETED` - All tasks completed successfully
- `FAILED` - Some tasks failed (all tasks terminal)
- `CANCELLED` - Execution cancelled by user
- `PARTIAL` - Mixed state (shouldn't happen if execution finished)

### TaskStatus (extended)
- `PENDING` - Task not yet started
- `RUNNING` - Task currently executing
- `COMPLETED` - Task completed successfully
- `FAILED` - Task failed
- `SKIPPED` - Task skipped due to dependency failure
- `CANCELLED` - Task cancelled

## Error Handling

### TaskExecutionError
Recoverable error that triggers retry logic.

### TaskFatalError
Non-recoverable error that doesn't trigger retries.

### ExecutionAbortedError
Raised when fail-fast is enabled and a non-retryable task fails.

## Limitations and Future Work

1. **Graph reconstruction from checkpoint** - Currently not implemented; requires storing graph structure in DB
2. **Distributed execution** - Single-process only
3. **Resource management** - No CPU/memory limits
4. **Advanced scheduling** - Simple priority-based only

## Integration with P2-12 (LLM Integration)

This engine is designed to work with P2-12 LLM integration:
- `MockTaskExecutor` for testing
- `TaskExecutor` protocol for LLM backend
- Execution context includes dependency results for LLM chaining