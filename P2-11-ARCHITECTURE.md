# P2-11 Parallel Execution Engine — Architecture Design

**Author:** Thinker (mimo-v2-pro)
**Date:** 2026-03-27
**Phase:** 2.2 — Task Decomposition & Parallelism
**Sprint:** P2-11, P2-12, P2-13

---

## 1. Problem Statement

Phase 2.2 established the *planning* layer: decompose complex work into dependency-ordered tasks (P2-08), analyze their complexity (P2-09), and visualize the task graph (P2-10). What's missing is the *execution* layer — actually running those task graphs in parallel, respecting dependencies, handling failures, and exposing real-time state.

We need a `ParallelExecutionEngine` that:
- Takes a `TaskGraph` and executes it, respecting dependency edges
- Runs independent tasks concurrently, maximizing throughput
- Integrates complexity scores to route tasks to appropriate agent tiers
- Feeds live state back to the visualizer
- Persists execution history for auditing and resumption

---

## 2. Architecture Decisions

### 2.1 Concurrency Model: `asyncio` (primary) + `ThreadPoolExecutor` (escape hatch)

**Decision:** Pure `asyncio` with `asyncio.TaskGroup` for structured concurrency. `ThreadPoolExecutor` reserved for CPU-bound or blocking I/O.

**Rationale:**
- The entire provider layer (`ModelProvider`) is already async. Running tasks means calling `chat_completion()` — an `await` call, not CPU work.
- `asyncio.TaskGroup` (Python 3.11+) gives structured concurrency: if the engine is cancelled, all in-flight tasks are cancelled cleanly. No orphaned coroutines.
- `ThreadPoolExecutor` is an escape hatch for blocking operations (file I/O, `subprocess`, `git` commands) that some tasks may need. The engine wraps these via `loop.run_in_executor()`.
- `ProcessPoolExecutor` is **rejected**: tasks are LLM-bound (network latency), not CPU-bound. The overhead of pickling data across process boundaries and losing in-memory state (task graph, results dict) outweighs any benefit. LLM API calls release the GIL naturally.

**Trade-off:** Single-process means a crash kills all tasks. Acceptable for an orchestration tool (not a distributed system). Mitigated by checkpointing (§2.2).

### 2.2 State Persistence: SQLite (via `sqlite-utils`)

**Decision:** SQLite database for execution state. In-memory dict as write-through cache.

**Rationale:**
- `sqlite-utils` is already a dependency. No new packages needed.
- Execution state (which task is running, results, retry counts) must survive process restarts for long-running graphs.
- JSON files are fragile (no concurrent access, no queries, corruption risk on crash).
- In-memory only means any crash loses all progress — unacceptable for graphs with 20+ tasks.
- SQLite gives us: ACID transactions, query capability (find failed tasks, compute aggregates), single-file portability.

**Schema:**
```sql
CREATE TABLE executions (
    execution_id TEXT PRIMARY KEY,
    graph_name   TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    completed_at TEXT,
    status       TEXT NOT NULL DEFAULT 'running',  -- running | completed | failed | cancelled
    config_json  TEXT NOT NULL                      -- serialized ExecutionConfig
);

CREATE TABLE task_states (
    execution_id TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    status       TEXT NOT NULL,
    started_at   TEXT,
    completed_at TEXT,
    retry_count  INTEGER NOT NULL DEFAULT 0,
    result_json  TEXT,                              -- serialized TaskResult
    error_msg    TEXT,
    PRIMARY KEY (execution_id, task_id),
    FOREIGN KEY (execution_id) REFERENCES executions(execution_id)
);

CREATE INDEX idx_task_states_status ON task_states(execution_id, status);
```

### 2.3 Error Handling: Exponential Backoff + Dead Letter Queue

**Decision:** Per-task retry with exponential backoff. Failed tasks that exhaust retries go to a "dead letter" list for manual review. No circuit breaker (premature for this abstraction level).

**Policy tiers (configurable):**
| Scenario | Strategy |
|---|---|
| Transient LLM error (rate limit, 500, timeout) | Retry with exponential backoff (base=2s, max=60s) |
| Permanent LLM error (auth, model not found) | Fail immediately, no retry |
| Task execution raises unexpected exception | Retry up to `max_retries`, then dead-letter |
| Dependency failed | Skip task, mark as `SKIPPED` |
| All root tasks failed | Abort execution |

**New `TaskStatus` value needed:** `SKIPPED` (when a dependency fails, downstream tasks are skipped rather than left PENDING).

**Error propagation model:**
```
root_task FAILS
  └── dependent_task → SKIPPED (immediate, no retry)
        └── its_dependent → SKIPPED
```

This is a decision the engine makes at scheduling time: before dispatching a ready task, check that all deps are COMPLETED (not just not-PENDING).

### 2.4 Integration Points: Loose Coupling via Protocols

**Decision:** The engine depends on `TaskGraph`, `Task`, `ComplexityEstimate`, and `TaskResult` data models (from `omni.task.models`) — these are stable data classes. Integration with `ComplexityAnalyzer` and `TaskGraphVisualizer` is through **optional callbacks**, not hard imports.

**Why:** The engine should be usable without the analyzer or visualizer. Tight coupling would mean changing the visualizer forces engine changes. Instead:

```python
# Engine accepts optional callbacks
@dataclass
class ExecutionCallbacks:
    on_task_start: Callable[[str, Task], None] | None = None
    on_task_complete: Callable[[str, TaskResult], None] | None = None
    on_task_fail: Callable[[str, Task, Exception], None] | None = None
    on_progress: Callable[[float], None] | None = None  # 0.0 to 1.0
    on_execution_complete: Callable[[ExecutionResult], None] | None = None
```

The visualizer hooks into these callbacks to update its display. The complexity analyzer is used *before* execution to configure routing — the engine reads pre-computed `ComplexityEstimate` from `Task.complexity`, it doesn't call the analyzer itself.

**Model routing integration:** The engine uses `ComplexityEstimate.tier` to select which agent/model executes a task. It delegates to a `TaskExecutor` protocol:

```python
class TaskExecutor(Protocol):
    """Executes a single task. The engine calls this for each ready task."""
    async def execute(self, task: Task, context: ExecutionContext) -> TaskResult: ...
```

A concrete `LLMTaskExecutor` would use the provider/router layer. A `MockTaskExecutor` enables testing without API calls.

### 2.5 Observability: Structured Logging + Metrics Emission

**Decision:** Python `logging` with structured fields + lightweight metrics via callbacks.

**Logging strategy:**
- `INFO`: Task start/complete/fail, execution start/complete, retry events
- `DEBUG`: Scheduling decisions, ready-task evaluations, dependency checks
- `WARNING`: Retry attempts, slow tasks (configurable threshold)
- `ERROR`: Task failures, execution aborts

**Metrics emitted via callbacks (not Prometheus — keep it dependency-free):**
```python
@dataclass
class ExecutionMetrics:
    execution_id: str
    total_tasks: int
    completed: int
    failed: int
    skipped: int
    running: int
    pending: int
    total_tokens_used: int
    total_cost: float
    wall_clock_seconds: float
    parallel_efficiency: float  # actual_speedup / theoretical_max_speedup
```

The `on_progress` callback fires after every state change, carrying `ExecutionMetrics`. Any consumer (visualizer, CLI, dashboard) can use this.

---

## 3. Class Diagram

```
                    ┌─────────────────────┐
                    │    TaskGraph        │  (existing, omni.task.models)
                    │─────────────────────│
                    │ tasks: dict         │
                    │ get_ready_tasks()   │
                    │ topological_order() │
                    └──────────┬──────────┘
                               │ contains
                               │
┌──────────────────────────────────────────────────────────────┐
│                  ParallelExecutionEngine                      │
│──────────────────────────────────────────────────────────────│
│ - _graph: TaskGraph                                          │
│ - _executor: TaskExecutor                                    │
│ - _config: ExecutionConfig                                   │
│ - _callbacks: ExecutionCallbacks                             │
│ - _db: ExecutionDB                                           │
│ - _metrics: ExecutionMetrics                                 │
│ - _results: dict[str, TaskResult]                            │
│ - _semaphore: asyncio.Semaphore                              │
│──────────────────────────────────────────────────────────────│
│ + async execute() -> ExecutionResult                         │
│ + async cancel() -> None                                     │
│ + get_status() -> ExecutionMetrics                           │
│ + get_result(task_id) -> TaskResult | None                   │
│ + resume(execution_id) -> ExecutionResult                    │
│──────────────────────────────────────────────────────────────│
│ - _schedule_loop()                                           │
│ - _execute_task(task) -> TaskResult                          │
│ - _handle_failure(task, error) -> None                       │
│ - _propagate_skips(failed_task_id) -> None                   │
│ - _should_retry(task, error) -> bool                         │
│ - _backoff_delay(retry_count) -> float                       │
│ + static from_checkpoint(execution_id, db_path) -> Engine    │
└───────┬──────────────────┬───────────────────┬───────────────┘
        │ uses              │ uses              │ uses
        ▼                   ▼                   ▼
┌───────────────┐  ┌─────────────────┐  ┌──────────────────┐
│ TaskExecutor  │  │  ExecutionDB    │  │ ExecutionConfig  │
│   (Protocol)  │  │─────────────────│  │──────────────────│
│───────────────│  │ - _db: Database  │  │ max_concurrent:  │
│ async execute │  │─────────────────│  │   int = 5        │
│   (task, ctx) │  │ save_execution()│  │ retry_enabled:   │
│   -> TaskResult│  │ save_task_state()│  │   bool = True    │
└───────┬───────┘  │ load_execution()│  │ backoff_base:    │
        │          │ load_task_states()│  │   float = 2.0    │
   ┌────┴────┐     └─────────────────┘  │ backoff_max:     │
   │         │                          │   float = 60.0   │
   ▼         ▼                          │ timeout_per_task:│
┌──────┐ ┌──────────┐                   │   float = 300.0  │
│LLM   │ │Mock      │                   │ fail_fast:       │
│Task  │ │Task      │                   │   bool = False   │
│Exec  │ │Executor  │                   │ skip_on_dep_fail:│
└──────┘ └──────────┘                   │   bool = True    │
                                        └──────────────────┘

┌─────────────────────┐     ┌─────────────────────┐
│ ExecutionResult     │     │ ExecutionCallbacks  │
│─────────────────────│     │─────────────────────│
│ execution_id: str   │     │ on_task_start       │
│ graph_name: str     │     │ on_task_complete    │
│ status: str         │     │ on_task_fail        │
│ results: dict       │     │ on_progress         │
│ metrics: Metrics    │     │ on_execution_complete│
│ started_at: datetime│     └─────────────────────┘
│ completed_at: dt    │
│ dead_letter: list   │
└─────────────────────┘
```

---

## 4. API Design

### 4.1 Core Engine

```python
class ParallelExecutionEngine:
    """Execute a TaskGraph in parallel, respecting dependencies."""

    def __init__(
        self,
        graph: TaskGraph,
        executor: TaskExecutor,
        config: ExecutionConfig | None = None,
        callbacks: ExecutionCallbacks | None = None,
        db_path: str | Path = "omni_executions.db",
    ) -> None: ...

    async def execute(self) -> ExecutionResult:
        """Run the entire task graph to completion or failure.

        Returns:
            ExecutionResult with all task outcomes and aggregate metrics.

        Raises:
            ExecutionAbortedError: If fail_fast=True and a non-retryable
                task fails.
        """

    async def cancel(self) -> None:
        """Gracefully cancel execution.

        In-flight tasks will complete their current iteration.
        Tasks not yet started will be marked CANCELLED.
        """

    def get_status(self) -> ExecutionMetrics:
        """Snapshot of current execution metrics."""

    def get_result(self, task_id: str) -> TaskResult | None:
        """Get result for a specific task (None if not yet completed)."""

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
```

### 4.2 Configuration

```python
@dataclass(frozen=True)
class ExecutionConfig:
    """Configuration for parallel execution."""
    max_concurrent: int = 5           # Max tasks running simultaneously
    retry_enabled: bool = True        # Whether to retry failed tasks
    backoff_base: float = 2.0         # Base seconds for exponential backoff
    backoff_max: float = 60.0         # Maximum backoff delay
    timeout_per_task: float = 300.0   # Per-task timeout in seconds
    fail_fast: bool = False           # Abort on first non-retryable failure
    skip_on_dep_failure: bool = True  # Skip tasks whose deps failed
    checkpoint_interval: int = 1      # Save to DB every N state changes
```

### 4.3 Task Executor Protocol

```python
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


@dataclass
class ExecutionContext:
    """Context passed to task executors."""
    dependency_results: dict[str, TaskResult]  # Results from completed deps
    execution_id: str
    task_index: int                            # Position in execution
    total_tasks: int
```

### 4.4 Result Types

```python
@dataclass
class ExecutionResult:
    """Aggregate result of a full graph execution."""
    execution_id: str
    graph_name: str
    status: ExecutionStatus               # COMPLETED | FAILED | CANCELLED | PARTIAL
    results: dict[str, TaskResult]        # task_id → result
    metrics: ExecutionMetrics
    started_at: datetime
    completed_at: datetime
    dead_letter: list[str]                # task_ids that exhausted retries
    config: ExecutionConfig

class ExecutionStatus(StrEnum):
    COMPLETED = "completed"       # All tasks succeeded
    FAILED = "failed"             # Fail-fast triggered or all roots failed
    CANCELLED = "cancelled"       # User-requested cancel
    PARTIAL = "partial"           # Some tasks succeeded, some skipped/failed

class TaskExecutionError(Exception):
    """Recoverable task failure (triggers retry)."""

class TaskFatalError(Exception):
    """Non-recoverable task failure (no retry)."""

class ExecutionAbortedError(Exception):
    """Execution aborted due to fail_fast."""
    def __init__(self, failed_task_id: str, result: ExecutionResult) -> None: ...
```

---

## 5. Scheduling Algorithm

The core scheduling loop is the heart of the engine. Here's the design:

```
execute(graph):
    validate graph (no cycles)
    create execution record in DB
    results = {}
    running = {}    # task_id -> asyncio.Task
    semaphore = Semaphore(config.max_concurrent)

    while not graph.is_complete and not abort_condition:
        ready = graph.get_ready_tasks()  # existing method

        # Filter: skip tasks whose deps failed (if config.skip_on_dep_failure)
        ready = [t for t in ready if all_deps_completed(t)]

        # Enforce concurrency limit
        for task in ready[:semaphore._value]:
            if semaphore.locked():
                break
            running[task.task_id] = spawn(_execute_with_semaphore(task))

        # Wait for ANY task to complete
        if running:
            done, _ = await asyncio.wait(
                running.values(),
                return_when=asyncio.FIRST_COMPLETED
            )
            for coro in done:
                task_id, result = await coro
                results[task_id] = result
                graph.tasks[task_id].status = result.status
                del running[task_id]

                if result.status == FAILED:
                    _propagate_skips(task_id)  # mark downstream as SKIPPED
                checkpoint(task_id, result)

        if not ready and not running:
            break  # deadlock or done

    return ExecutionResult(...)
```

**Key properties:**
- **Back-pressure:** `asyncio.Semaphore` caps concurrency. No unbounded spawning.
- **Eager scheduling:** As soon as a task completes and frees a slot, the next ready task is dispatched in the same loop iteration.
- **Fairness:** Ready tasks are sorted by `priority` (from `TaskGraph.get_ready_tasks()`), so high-priority tasks run first within a level.
- **Graceful shutdown:** `cancel()` sets a flag; the loop drains running tasks before exiting.

---

## 6. Integration Plan with Phase 2.2 Components

### 6.1 `TaskDecompositionEngine` (P2-08)

**Integration type:** Upstream consumer. The decomposer produces `TaskGraph` objects; the engine consumes them.

```python
# Usage pattern
decomposer = TaskDecompositionEngine()
graph = await decomposer.decompose(complex_request)

engine = ParallelExecutionEngine(
    graph=graph,
    executor=llm_executor,
)
result = await engine.execute()
```

No changes needed to the decomposer. The engine is a downstream consumer of `TaskGraph`.

### 6.2 `ComplexityAnalyzer` (P2-09)

**Integration type:** Pre-execution analysis. The analyzer runs *before* the engine, populating `Task.complexity` fields.

```python
# Pre-processing step
analyzer = ComplexityAnalyzer()
for task in graph.tasks.values():
    task.complexity = analyzer.analyze_task_complexity(task, graph)

# Engine reads complexity.tier for routing
engine = ParallelExecutionEngine(graph=graph, executor=tiered_executor)
```

The engine **reads** `task.complexity.tier` to select the appropriate model/agent tier. It does **not** call the analyzer directly. This keeps the dependency one-directional: Analyzer → Task.complexity → Engine.

**Config integration:** `ExecutionConfig` can include a `parallelizability_threshold` that uses `analyzer.calculate_parallelizability_score()` to decide whether to enable parallelism at all. Graphs with score < 0.2 are run sequentially to avoid overhead.

### 6.3 `TaskGraphVisualizer` (P2-10)

**Integration type:** Real-time state consumer via callbacks.

```python
visualizer = TaskGraphVisualizer(graph)

def on_progress(metrics: ExecutionMetrics) -> None:
    # Re-render ASCII with current status
    print(visualizer.visualize(OutputFormat.ASCII))

engine = ParallelExecutionEngine(
    graph=graph,
    executor=executor,
    callbacks=ExecutionCallbacks(on_progress=on_progress),
)
```

The visualizer **does not need changes** — it already reads `Task.status` from the graph. The engine mutates `task.status` in-place as tasks transition. The callback triggers re-rendering.

**Future enhancement (P2-13):** Add execution-specific visual elements — progress bars per task level, parallelism heatmap, timing waterfall.

---

## 7. File Structure

New files to create:

```
src/omni/execution/
├── __init__.py              # Public API exports
├── engine.py                # ParallelExecutionEngine
├── config.py                # ExecutionConfig, ExecutionCallbacks
├── executor.py              # TaskExecutor protocol, LLMTaskExecutor, MockTaskExecutor
├── db.py                    # ExecutionDB (SQLite persistence)
├── models.py                # ExecutionResult, ExecutionMetrics, ExecutionStatus, errors
└── scheduler.py             # Core scheduling loop (extracted from engine for testability)

tests/
├── test_execution_engine.py       # Integration tests for the engine
├── test_execution_scheduler.py    # Unit tests for scheduling algorithm
├── test_execution_db.py           # SQLite persistence tests
├── test_execution_executor.py     # Mock executor tests
└── test_execution_integration.py  # End-to-end with real TaskGraph
```

**Modification to existing files:**
- `src/omni/task/models.py`: Add `SKIPPED` to `TaskStatus` enum, add `CANCELLED` status
- `src/omni/decomposition/__init__.py`: No changes needed
- `pyproject.toml`: Add `pytest-asyncio` to dev deps (already there, just verify)

---

## 8. Implementation Roadmap

### P2-11: Core Engine (this sprint)

**Objective:** Working `ParallelExecutionEngine` that executes task graphs with `MockTaskExecutor`.

| Deliverable | Description | Est. Complexity |
|---|---|---|
| `execution/models.py` | `ExecutionResult`, `ExecutionMetrics`, `ExecutionStatus`, error classes | Low |
| `execution/config.py` | `ExecutionConfig` dataclass, `ExecutionCallbacks` | Low |
| `execution/db.py` | `ExecutionDB` — SQLite schema, save/load operations | Medium |
| `execution/executor.py` | `TaskExecutor` protocol, `MockTaskExecutor` | Low |
| `execution/scheduler.py` | Core scheduling loop with semaphore-based concurrency | High |
| `execution/engine.py` | `ParallelExecutionEngine` class wiring it all together | High |
| `task/models.py` changes | Add `SKIPPED`, `CANCELLED` to `TaskStatus` | Low |
| `tests/test_execution_engine.py` | Integration tests with mock executor | Medium |
| `tests/test_execution_scheduler.py` | Unit tests for scheduling edge cases | Medium |
| `tests/test_execution_db.py` | SQLite round-trip tests | Low |

**Definition of done:**
- Engine executes a linear chain (A→B→C) sequentially ✓
- Engine executes a diamond graph (A→B, A→C, B→D, C→D) with 2-way parallelism ✓
- Failed task causes downstream skips ✓
- Retry with exponential backoff works ✓
- SQLite checkpoint survives restart ✓
- `ruff check . && mypy src/omni && pytest tests/` all pass ✓

### P2-12: LLM Integration & Tiered Routing

**Objective:** `LLMTaskExecutor` that calls real LLM providers, routes by complexity tier.

| Deliverable | Description |
|---|---|
| `execution/executor.py` | `LLMTaskExecutor` implementation using provider/router layer |
| Tier routing | Map `ComplexityEstimate.tier` → model selection via router |
| Context assembly | Build prompts from `Task.description` + dependency results |
| `ExecutionContext` | Pass dependency outputs as context to downstream tasks |
| Timeout handling | Per-task timeout via `asyncio.wait_for` |
| Cost tracking | Aggregate token usage and cost across execution |
| Tests | Integration tests with `MockProvider` from existing test infra |

### P2-13: Observability & Live Visualization

**Objective:** Rich real-time feedback during execution.

| Deliverable | Description |
|---|---|
| Live ASCII dashboard | Terminal-based real-time execution view |
| Mermaid live updates | Generate Mermaid snapshots at each state change |
| Execution replay | Load past execution from DB, replay state transitions |
| Parallelism metrics | Compute and display parallel efficiency |
| CLI integration | `omni execute graph.json` command |
| Performance tuning | Adaptive concurrency based on task completion rate |

---

## 9. Testing Strategy

### Unit Tests (no I/O, no async)

- `ExecutionConfig` validation
- `ExecutionResult` / `ExecutionMetrics` construction
- Error class hierarchy
- `TaskStatus` transitions (including new `SKIPPED`, `CANCELLED`)

### Async Unit Tests (`pytest-asyncio`)

- `MockTaskExecutor` — controllable delays and failure injection
- Scheduling loop: linear chain, diamond, fan-out/fan-in, cycle detection
- Retry logic: backoff calculation, max retry exhaustion
- Skip propagation: failed root → all downstream SKIPPED
- Concurrency limiting: semaphore respects `max_concurrent`
- Cancellation: mid-flight cancel drains properly

### Integration Tests

- Full `ParallelExecutionEngine.execute()` with `MockTaskExecutor`
- SQLite persistence: execute, stop, resume from checkpoint
- Callback invocation: verify `on_task_start`, `on_task_complete`, `on_progress` fire correctly
- Large graph (50+ tasks) — verify no deadlocks or resource leaks

### CI Requirements

All tests must pass:
```bash
ruff check .                           # Lint
mypy src/omni --ignore-missing-imports # Type check
pytest tests/ -v                       # Tests
```

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| SQLite write contention under high parallelism | Medium | Use WAL mode + batch writes (checkpoint_interval) |
| asyncio.TaskGroup cancels all on one failure | High | Wrap individual tasks in shield; handle cancellation per-task |
| Large graphs exhaust memory with result context | Medium | Lazy loading: only pass direct dependency results, not full graph |
| Deadlock if graph validation misses edge case | High | Timeout per task + global execution timeout as safety net |
| `TaskStatus.SKIPPED` requires modifying existing model | Low | Backwards-compatible enum addition; existing tests unchanged |

---

## 11. Design Principles Summary

1. **Async-native:** Everything is `async` from the start. No sync wrappers that block the event loop.
2. **Structured concurrency:** `asyncio.TaskGroup` for clean lifecycle. No fire-and-forget tasks.
3. **Protocol-based extensibility:** `TaskExecutor` protocol means zero coupling to any specific LLM provider.
4. **Checkpoint-first:** Every state change is persisted before the callback fires. Crash recovery is the default, not an afterthought.
5. **Minimal surface area:** The engine does scheduling and execution orchestration. It does NOT do prompt construction, model selection, or result interpretation — those are the executor's job.
6. **Observable by default:** Callbacks for every meaningful event. Structured logging. No "black box" execution.
