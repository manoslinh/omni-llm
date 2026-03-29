# Omni-LLM Phase 2: Orchestration Layer Implementation Plan

**Author:** Athena (Senior Project Manager)
**Date:** March 26, 2026
**Status:** Active — Ready for Execution
**Branch:** `main` (commit `51bc53b`)

---

## Executive Summary

Phase 2 transforms Omni-LLM from a single-agent edit loop into a **multi-agent orchestration OS**. This plan decomposes Phase 2 into **22 tickets** across **5 sub-phases**, sequenced by dependencies.

**Current Foundation (Phase 0-1 Complete):**
- ✅ ModelProvider interface + LiteLLM adapter
- ✅ EditLoop service (send → parse → apply → verify → reflect)
- ✅ EditBlock parser
- ✅ Git integration (dirty commits, attribution, undo)
- ✅ Verification pipeline (lint + test verifiers)
- ✅ Provider configuration system (YAML-based)
- ✅ Cost tracking per request
- ✅ CI/CD (ruff + mypy + pytest on Python 3.12)
- ✅ CLI entry point (`omni`)

**Phase 2 Deliverables:**
1. **Model Router** (cost-aware routing, fallback chains, strategies)
2. **Task Decomposition** (LLM-powered task breakdown into DAG)
3. **Multi-Agent Coordination** (message bus, agent registry, supervisor pattern)
4. **Parallel Execution** (git worktree isolation, result integration)
5. **Workflow Templates** (YAML-defined multi-step workflows)

---

## Phase 2 Breakdown

### Phase 2.1: Model Router Implementation (Tickets P2-01 to P2-06)

The Model Router is the backbone. It must exist before any multi-agent work because every agent needs cost-aware model selection.

### Phase 2.2: Task Decomposition Engine (Tickets P2-07 to P2-10)

Task decomposition requires the router (to estimate costs per subtask) and provides the input for multi-agent execution.

### Phase 2.3: Multi-Agent Coordination (Tickets P2-11 to P2-15)

Message bus, agent registry, and supervisor pattern. Depends on task decomposition for task graph input.

### Phase 2.4: Parallel Execution (Tickets P2-16 to P2-19)

Git worktree isolation, concurrent execution engine, conflict resolution. Depends on coordination layer.

### Phase 2.5: Workflow Templates & Integration (Tickets P2-20 to P2-22)

YAML workflow definitions, end-to-end integration testing, documentation.

---

## Dependency Graph

```
P2-01 (RoutingStrategy ABC)
  ├─→ P2-02 (CostOptimizedStrategy)
  │     ├─→ P2-03 (Model Router Service)
  │     │     ├─→ P2-04 (Fallback Chain)
  │     │     │     ├─→ P2-05 (Router + EditLoop Integration)
  │     │     │     └─→ P2-07 (Task Model)
  │     │     └─→ P2-06 (Budget Enforcement)
  │     │           └─→ P2-07 (Task Model)
  │     └─→ P2-07 (Task Model)
  └─→ P2-02 (CostOptimizedStrategy)

P2-07 (Task Model)
  └─→ P2-08 (Task Decomposer)
        └─→ P2-09 (Dependency Graph)
              └─→ P2-10 (Complexity Estimator)

P2-10 (Complexity Estimator)
  └─→ P2-11 (Message Bus)
        └─→ P2-12 (Agent Registry)
              └─→ P2-13 (Agent Base Class)
                    └─→ P2-14 (Supervisor Agent)
                          └─→ P2-15 (Worker Agent)

P2-13 (Agent Base Class)
  └─→ P2-16 (Worktree Manager)
        └─→ P2-17 (Parallel Executor)
              └─→ P2-18 (Conflict Resolver)
                    └─→ P2-19 (Result Integrator)

P2-19 (Result Integrator)
  └─→ P2-20 (Workflow Template Engine)
        └─→ P2-21 (End-to-End Integration)
              └─→ P2-22 (Documentation + Examples)
```

---

## Tickets

---

### P2-01: Routing Strategy Interface (ABC)

**TICKET ID:** P2-01
**TITLE:** Define RoutingStrategy Abstract Base Class and Data Models
**AGENT TYPE:** Thinker (complex architecture — defining the core abstraction)
**PRIORITY:** P0 (blocks everything)
**DEPENDENCIES:** None
**DELIVERABLES:**
- `src/omni/router/__init__.py` — package init
- `src/omni/router/strategy.py` — `RoutingStrategy` ABC with methods:
  - `select_model(task_type, context, budget_remaining) -> ModelSelection`
  - `estimate_cost(task, model) -> CostEstimate`
  - `rank_models(task_type, context) -> list[RankedModel]`
- `src/omni/router/models.py` — Data models:
  - `TaskType` enum (ARCHITECTURE, CODING, CODE_REVIEW, TESTING, DOCUMENTATION, SIMPLE_QUERY)
  - `ModelSelection` dataclass (model_id, reason, estimated_cost, confidence)
  - `CostEstimate` dataclass (input_tokens, output_tokens, total_cost_usd)
  - `RankedModel` dataclass (model_id, score, cost_estimate, quality_estimate)
  - `RoutingContext` dataclass (task_type, file_count, complexity, budget_remaining, history)
  - `FallbackConfig` dataclass (chain, max_retries, backoff_seconds)
- `tests/test_routing_strategy.py` — Tests for ABC contract and data models
**DEFINITION OF DONE:**
- [ ] `RoutingStrategy` ABC is defined with all abstract methods
- [ ] All data models are dataclasses with proper type annotations
- [ ] `TaskType` enum covers all required task types
- [ ] Tests pass: ABC cannot be instantiated, all methods raise `NotImplementedError`
- [ ] `ruff check .` passes
- [ ] `mypy src/omni --ignore-missing-imports` passes
- [ ] `pytest tests/ -v` passes
**ESTIMATED EFFORT:** S (2-3 hours)
**NOTES:** This is pure architecture — no external dependencies needed. Thinker should design the cleanest possible interface before Coder implements strategies on top. Study the existing `providers/base.py` pattern for consistency.

---

### P2-02: CostOptimizedStrategy Implementation

**TICKET ID:** P2-02
**TITLE:** Implement CostOptimizedStrategy — cheapest model that meets quality threshold
**AGENT TYPE:** Coder (standard implementation over defined interface)
**PRIORITY:** P0
**DEPENDENCIES:** P2-01
**DELIVERABLES:**
- `src/omni/router/cost_optimized.py` — `CostOptimizedStrategy` class:
  - Loads model costs from `configs/providers.yaml` `cost_config.rates`
  - Loads model capabilities (strengths, weaknesses, max_context_tokens) from `configs/models.yaml`
  - `select_model()`: filters models by task_type match, sorts by cost ascending, picks first that meets `min_quality` threshold
  - `estimate_cost()`: uses token estimation heuristic (input ≈ prompt tokens, output ≈ 2x input for edit tasks)
  - `rank_models()`: returns all qualifying models sorted by cost
  - Respects budget constraints from `RoutingContext.budget_remaining`
- `tests/test_cost_optimized.py` — Unit tests:
  - Test: architecture task → picks Claude/GPT-4 tier (not cheapest)
  - Test: coding task → picks DeepSeek/GPT-3.5 tier (cheapest)
  - Test: budget exhausted → returns `None` or raises `BudgetExceededError`
  - Test: model config loading from YAML
**DEFINITION OF DONE:**
- [ ] Strategy loads model costs from existing YAML config
- [ ] `select_model()` returns cheapest model whose strengths include the task type
- [ ] Budget enforcement: refuses selection if `estimated_cost > budget_remaining`
- [ ] Handles missing model configs gracefully (skips model, doesn't crash)
- [ ] All unit tests pass
- [ ] `ruff check .` passes
- [ ] `mypy src/omni --ignore-missing-imports` passes
**ESTIMATED EFFORT:** M (4-6 hours)
**NOTES:** Reuse existing `configs/providers.yaml` cost_config.rates and `configs/models.yaml` routing.task_types. Don't create new config files. The `ProviderConfiguration` loader in `providers/config.py` can be imported.

---

### P2-03: Model Router Service

**TICKET ID:** P2-03
**TITLE:** Model Router Service — unified routing facade
**AGENT TYPE:** Coder
**PRIORITY:** P0
**DEPENDENCIES:** P2-02
**DELIVERABLES:**
- `src/omni/router/router.py` — `ModelRouter` class:
  - Constructor: takes `ModelProvider`, `RoutingStrategy`, `CostTracker`
  - `route(task_type, context) -> ModelSelection`: delegates to strategy
  - `complete(messages, task_type, **kwargs) -> ChatCompletion`: routes then calls provider
  - `stream(messages, task_type, **kwargs) -> AsyncGenerator`: routes then streams
  - `get_cost_summary() -> dict`: delegates to CostTracker
  - `set_strategy(strategy)`: hot-swap routing strategy
- `src/omni/router/__init__.py` — exports `ModelRouter`, `CostOptimizedStrategy`
- Integration with existing `EditLoop`: show how `ModelRouter` can replace direct `model_provider.complete()` calls
- `tests/test_model_router.py` — Integration tests with MockProvider
**DEFINITION OF DONE:**
- [ ] `ModelRouter` wraps `ModelProvider` transparently
- [ ] `complete()` routes to cheapest capable model automatically
- [ ] Strategy can be swapped at runtime
- [ ] Cost tracking is automatic (every `complete()` call is tracked)
- [ ] Works with `MockProvider` for testing
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** M (4-6 hours)
**NOTES:** The router is a decorator/wrapper around `ModelProvider`. It should NOT modify the `ModelProvider` interface — it implements the same interface but adds routing logic on top.

---

### P2-04: Fallback Chain with Retry Logic

**TICKET ID:** P2-04
**TITLE:** Fallback chain — automatic model failover with exponential backoff
**AGENT TYPE:** Coder
**PRIORITY:** P0
**DEPENDENCIES:** P2-03
**DELIVERABLES:**
- `src/omni/router/fallback.py` — `FallbackChain` class:
  - Constructor: takes list of `ModelProvider` instances (or model IDs to resolve)
  - `execute(messages, **kwargs) -> ChatCompletion`: tries primary, falls back on failure
  - Handles `ProviderError`, `RateLimitError`, `AuthenticationError`, `ModelNotFoundError`
  - Exponential backoff: 1s → 2s → 4s → 8s (configurable max)
  - Respects `Retry-After` header from `RateLimitError`
  - `execute_with_fallback_chain(chain: list[str], messages, **kwargs)`: explicit chain
- `src/omni/router/errors.py` — Router-specific errors:
  - `AllModelsFailedError` (all models in chain failed)
  - `BudgetExceededError` (no budget remaining)
  - `NoEligibleModelError` (no model matches task requirements)
- `tests/test_fallback.py` — Tests:
  - Primary fails → secondary succeeds
  - All fail → `AllModelsFailedError`
  - Rate limit → respects `Retry-After`
  - Budget exceeded → `BudgetExceededError`
**DEFINITION OF DONE:**
- [ ] Fallback chain tries models in order until one succeeds
- [ ] Exponential backoff between retries
- [ ] `RateLimitError` with `retry_after` is respected
- [ ] `AllModelsFailedError` raised when chain is exhausted
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** M (4-6 hours)
**NOTES:** Reuse error classes from `providers/base.py`. The fallback chain should log each attempt for observability. Consider using `tenacity` library if available, otherwise implement backoff manually.

---

### P2-05: EditLoop + Router Integration

**TICKET ID:** P2-05
**TITLE:** Integrate ModelRouter into EditLoop — automatic model selection per cycle
**AGENT TYPE:** Coder
**PRIORITY:** P1
**DEPENDENCIES:** P2-03, P2-04
**DELIVERABLES:**
- Modify `src/omni/core/edit_loop.py`:
  - Add `model_router: ModelRouter | None` parameter to `__init__`
  - In `run_cycle()`: if `model_router` is set, use `model_router.complete()` instead of `model_provider.complete()`
  - Detect task type from user input (simple heuristic or explicit `task_type` parameter)
  - Pass `task_type` to router for model selection
  - Track routed model in `CycleResult` (add `model_used: str` field)
- Update `src/omni/core/models.py`:
  - Add `model_used: str` to `CycleResult`
  - Add `routing_reason: str | None` to `CycleResult`
- Update CLI (`src/omni/cli/main.py`):
  - Add `--strategy` flag (cost_optimized, quality_first, balanced)
  - Add `--model` override flag (bypass router, use specific model)
- `tests/test_edit_loop_routing.py` — Integration tests
**DEFINITION OF DONE:**
- [ ] EditLoop uses ModelRouter when provided
- [ ] `CycleResult` includes which model was used and why
- [ ] CLI `--strategy` flag works
- [ ] CLI `--model` flag bypasses router
- [ ] Existing EditLoop tests still pass (backward compatible)
- [ ] New integration tests pass
- [ ] CI green
**ESTIMATED EFFORT:** M (4-6 hours)
**NOTES:** This is the integration point that makes routing real. Keep backward compatibility — if no router is provided, EditLoop works exactly as before. Task type detection can be a simple keyword heuristic for now; Phase 2.2 will add proper decomposition.

---

### P2-06: Budget Enforcement in Router

**TICKET ID:** P2-06
**TITLE:** Budget enforcement — per-session and per-task cost limits
**AGENT TYPE:** Intern (extends existing cost tracking — mostly data plumbing)
**PRIORITY:** P1
**DEPENDENCIES:** P2-03
**DELIVERABLES:**
- Modify `src/omni/router/router.py`:
  - Add `session_budget: float` and `task_budget: float` parameters
  - Before each `complete()`, check if `cost_estimate > remaining_budget`
  - Raise `BudgetExceededError` or auto-downgrade to cheaper model
  - Track cumulative session cost
- Modify `src/omni/providers/cost_tracker.py`:
  - Add `get_remaining_budget(budget_limit) -> float` method
  - Add `get_session_cost() -> float` method (alias for `get_total()["total_cost"]`)
- Update `configs/providers.yaml`:
  - Ensure `budget` section is loaded and used
- `tests/test_budget_enforcement.py` — Tests:
  - Budget enforcement blocks expensive model
  - Auto-downgrade to cheaper model when budget low
  - Budget reset between sessions
**DEFINITION OF DONE:**
- [ ] Router refuses models that exceed remaining budget
- [ ] Auto-downgrade to cheaper model when budget is tight
- [ ] `BudgetExceededError` raised when budget is exhausted
- [ ] Budget loads from existing YAML config
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** S (2-3 hours)
**NOTES:** This extends the existing `CostTracker` and `BudgetConfig`. Don't reinvent — wire the existing pieces together.

---

### P2-07: Task Model and Task Types

**TICKET ID:** P2-07
**TITLE:** Define Task data model — the unit of work for orchestration
**AGENT TYPE:** Thinker (design the core data model)
**PRIORITY:** P0
**DEPENDENCIES:** P2-05, P2-06
**DELIVERABLES:**
- `src/omni/orchestration/__init__.py` — package init
- `src/omni/orchestration/task.py` — Core data models:
  - `TaskStatus` enum (PENDING, IN_PROGRESS, COMPLETED, FAILED, CANCELLED)
  - `TaskPriority` enum (CRITICAL, HIGH, MEDIUM, LOW)
  - `Task` dataclass:
    - `id: str` (UUID)
    - `title: str`
    - `description: str`
    - `task_type: TaskType` (from router)
    - `status: TaskStatus`
    - `priority: TaskPriority`
    - `dependencies: list[str]` (task IDs)
    - `files: list[str]` (files involved)
    - `estimated_cost: CostEstimate | None`
    - `actual_cost: float | None`
    - `assigned_agent: str | None`
    - `result: TaskResult | None`
    - `created_at: datetime`
    - `started_at: datetime | None`
    - `completed_at: datetime | None`
    - `metadata: dict[str, Any]`
  - `TaskResult` dataclass:
    - `success: bool`
    - `files_modified: list[str]`
    - `output: str`
    - `cost: float`
    - `model_used: str`
    - `error: str | None`
  - `TaskGraph` dataclass:
    - `tasks: dict[str, Task]`
    - `adjacency: dict[str, list[str]]` (task_id → list of dependent task_ids)
    - `root_tasks: list[str]` (no dependencies)
    - `leaf_tasks: list[str]` (no dependents)
    - `get_ready_tasks() -> list[Task]` (tasks whose deps are all COMPLETED)
    - `get_execution_order() -> list[list[Task]]` (topological sort, grouped by parallelizable batches)
- `tests/test_task_model.py` — Tests for Task, TaskGraph, topological sort
**DEFINITION OF DONE:**
- [ ] `Task` dataclass covers all required fields
- [ ] `TaskGraph` supports DAG operations (topological sort, ready tasks)
- [ ] `get_execution_order()` returns parallelizable batches
- [ ] Cycle detection in dependency graph raises error
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** S (2-3 hours)
**NOTES:** This is foundational — every orchestration component uses these models. Keep it simple; we can extend later. Import `TaskType` and `CostEstimate` from the router package.

---

### P2-08: Task Decomposer

**TICKET ID:** P2-08
**TITLE:** LLM-powered task decomposition engine
**AGENT TYPE:** Coder
**PRIORITY:** P1
**DEPENDENCIES:** P2-07, P2-03
**DELIVERABLES:**
- `src/omni/orchestration/decomposer.py` — `TaskDecomposer` class:
  - Constructor: takes `ModelRouter` (uses cheap model for decomposition)
  - `decompose(goal: str, context: DecompositionContext, max_depth: int = 3) -> TaskGraph`:
    - Sends goal to LLM with structured prompt asking for subtask breakdown
    - Prompt includes: repo structure (from RepoMap if available), file list, user request
    - LLM returns JSON with subtasks, dependencies, task types, affected files
    - Validates JSON, builds `TaskGraph`
    - Recursive: if a subtask is still complex, decompose further (up to `max_depth`)
  - `validate_decomposition(graph: TaskGraph) -> list[str]`: returns list of issues
    - Circular dependencies
    - Orphaned tasks
    - Missing file references
  - Prompt template in `src/omni/orchestration/prompts.py`:
    - `DECOMPOSITION_SYSTEM_PROMPT`
    - `DECOMPOSITION_USER_PROMPT` (with `{goal}`, `{context}`, `{files}`)
- `tests/test_decomposer.py` — Tests with MockProvider:
  - Simple goal → 2-3 subtasks
  - Complex goal → 5-10 subtasks with dependencies
  - Invalid JSON from LLM → graceful error handling
**DEFINITION OF DONE:**
- [ ] `TaskDecomposer` produces valid `TaskGraph` from a natural language goal
- [ ] Uses cheap model (GPT-3.5/DeepSeek) for decomposition (not expensive model)
- [ ] Dependency graph is a valid DAG (no cycles)
- [ ] Handles LLM returning invalid JSON gracefully
- [ ] Recursive decomposition works up to `max_depth`
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** L (8-10 hours)
**NOTES:** This is the most complex single ticket. The prompt engineering matters — the LLM must return structured JSON reliably. Use JSON mode / structured output if the provider supports it. Fallback: parse from markdown code blocks.

---

### P2-09: Dependency Graph and Execution Planner

**TICKET ID:** P2-09
**TITLE:** Execution planner — topological scheduling with parallelism detection
**AGENT TYPE:** Coder
**PRIORITY:** P1
**DEPENDENCIES:** P2-07
**DELIVERABLES:**
- `src/omni/orchestration/planner.py` — `ExecutionPlanner` class:
  - `plan(graph: TaskGraph) -> ExecutionPlan`:
    - Topological sort into parallelizable batches
    - Each batch = list of tasks with no inter-dependencies
    - Estimate total cost across all tasks
    - Estimate total time (based on task complexity + model speed)
    - Detect file conflicts (two tasks in same batch touching same file → split into sequential)
  - `ExecutionPlan` dataclass:
    - `batches: list[TaskBatch]`
    - `estimated_total_cost: float`
    - `estimated_duration: float`
    - `max_parallelism: int`
  - `TaskBatch` dataclass:
    - `tasks: list[Task]`
    - `can_parallelize: bool`
    - `estimated_cost: float`
- `tests/test_planner.py` — Tests:
  - Linear chain → 1 task per batch
  - Diamond dependency → 3 batches (root, parallel pair, leaf)
  - File conflict detection
**DEFINITION OF DONE:**
- [ ] Topological sort produces valid execution order
- [ ] Parallelizable batches are correctly identified
- [ ] File conflicts force sequential execution
- [ ] Cost estimation is aggregate across batches
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** M (4-6 hours)
**NOTES:** This is graph algorithm work — no LLM involved. Pure deterministic logic. Can be developed and tested independently of decomposer.

---

### P2-10: Complexity Estimator

**TICKET ID:** P2-10
**TITLE:** Task complexity estimation for model routing
**AGENT TYPE:** Intern (heuristic-based, straightforward)
**PRIORITY:** P2
**DEPENDENCIES:** P2-07
**DELIVERABLES:**
- `src/omni/orchestration/complexity.py` — `ComplexityEstimator` class:
  - `estimate(task: Task, repo_context: RepoContext | None) -> ComplexityScore`
  - Factors:
    - Number of files affected
    - Lines of code in affected files
    - Language complexity (Python > JSON, etc.)
    - Test coverage requirements
    - Task type (ARCHITECTURE > CODING > TESTING)
  - `ComplexityScore` dataclass:
    - `score: float` (0.0 to 1.0)
    - `level: str` (TRIVIAL, SIMPLE, MODERATE, COMPLEX, EXPERT)
    - `recommended_model_tier: int` (1-5)
    - `factors: dict[str, float]`
- `tests/test_complexity.py` — Tests with mock file contexts
**DEFINITION OF DONE:**
- [ ] Complexity score is a float between 0.0 and 1.0
- [ ] Level classification matches score ranges
- [ ] Recommended model tier aligns with complexity
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** S (2-3 hours)
**NOTES:** This is a heuristic estimator, not an LLM call. Keep it fast and deterministic. We can add LLM-based estimation later as an alternative strategy.

---

### P2-11: Message Bus

**TICKET ID:** P2-11
**TITLE:** Async message bus for agent communication
**AGENT TYPE:** Coder
**PRIORITY:** P1
**DEPENDENCIES:** P2-10
**DELIVERABLES:**
- `src/omni/orchestration/bus.py` — `MessageBus` class:
  - Async pub/sub using `asyncio.Queue` per agent
  - `send(message: AgentMessage)`: deliver to specific agent or broadcast
  - `receive(agent_id: str, timeout: float | None) -> AgentMessage`: blocking receive
  - `subscribe(agent_id: str, message_type: MessageType)`: filter by type
  - `broadcast(message: AgentMessage)`: send to all registered agents
  - `register_agent(agent_id: str)`: create queue for agent
  - `unregister_agent(agent_id: str)`: cleanup queue
- `src/omni/orchestration/messages.py` — Message models:
  - `MessageType` enum (TASK_ASSIGN, TASK_RESULT, TASK_QUERY, ERROR, HANDOFF, STATUS_UPDATE, BROADCAST)
  - `AgentMessage` dataclass:
    - `id: str` (UUID)
    - `sender: str` (agent_id)
    - `recipient: str` (agent_id or "broadcast")
    - `type: MessageType`
    - `payload: dict[str, Any]`
    - `timestamp: float`
    - `correlation_id: str` (for tracing multi-step workflows)
    - `reply_to: str | None` (message ID being replied to)
- `tests/test_message_bus.py` — Tests:
  - Send/receive between two agents
  - Broadcast reaches all agents
  - Timeout on receive
  - Message ordering preserved
**DEFINITION OF DONE:**
- [ ] Message bus supports send/receive/broadcast
- [ ] Per-agent queues with subscribe filtering
- [ ] Timeout on receive works
- [ ] Message ordering is FIFO per agent
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** M (4-6 hours)
**NOTES:** Pure asyncio — no external dependencies. The message bus is in-memory only for Phase 2. Persistent messaging (Redis/NATS) is Phase 3.

---

### P2-12: Agent Registry

**TICKET ID:** P2-12
**TITLE:** Agent registry — dynamic registration and capability discovery
**AGENT TYPE:** Coder
**PRIORITY:** P1
**DEPENDENCIES:** P2-11
**DELIVERABLES:**
- `src/omni/orchestration/registry.py` — `AgentRegistry` class:
  - `register(agent: AgentInfo) -> str`: register agent, return agent_id
  - `unregister(agent_id: str)`: remove agent
  - `get(agent_id: str) -> AgentInfo | None`: get agent by ID
  - `find_by_capability(capability: str) -> list[AgentInfo]`: find agents with capability
  - `find_available(task_type: TaskType) -> list[AgentInfo]`: find idle agents matching task type
  - `list_all() -> list[AgentInfo]`: list all registered agents
  - `update_status(agent_id: str, status: AgentStatus)`: update agent status
- `src/omni/orchestration/agents.py` — Agent models:
  - `AgentStatus` enum (IDLE, BUSY, ERROR, OFFLINE)
  - `AgentRole` enum (SUPERVISOR, WORKER, SPECIALIST)
  - `AgentInfo` dataclass:
    - `id: str`
    - `name: str`
    - `role: AgentRole`
    - `capabilities: list[str]` (e.g., "coding", "testing", "architecture")
    - `status: AgentStatus`
    - `current_task: str | None`
    - `model: str | None`
    - `max_concurrent_tasks: int`
    - `metadata: dict[str, Any]`
- `tests/test_agent_registry.py` — Tests
**DEFINITION OF DONE:**
- [ ] Agents can register and unregister
- [ ] Capability-based discovery works
- [ ] Status tracking (IDLE, BUSY, etc.) works
- [ ] Thread-safe (async-safe) operations
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** S (2-3 hours)
**NOTES:** The registry is an in-memory data structure. For Phase 2, no persistence needed. Keep it simple.

---

### P2-13: Base Agent Class

**TICKET ID:** P2-13
**TITLE:** Abstract base class for all agents (Supervisor, Worker, Specialist)
**AGENT TYPE:** Thinker (design the agent abstraction)
**PRIORITY:** P1
**DEPENDENCIES:** P2-11, P2-12
**DELIVERABLES:**
- `src/omni/orchestration/agent_base.py` — `BaseAgent` ABC:
  - Constructor: takes `agent_id`, `ModelRouter`, `MessageBus`, `AgentRegistry`
  - `start()`: begin agent lifecycle (register, start message loop)
  - `stop()`: graceful shutdown (unregister, drain messages)
  - `handle_message(message: AgentMessage)`: process incoming message (abstract)
  - `send_message(recipient, type, payload)`: send via bus
  - `report_status()`: publish status to registry
  - Properties: `id`, `status`, `current_task`
  - Internal message loop: `async def _message_loop()`
- `src/omni/orchestration/exceptions.py` — Agent-specific errors:
  - `AgentError` (base)
  - `AgentNotReadyError`
  - `TaskExecutionError`
  - `MessageDeliveryError`
- `tests/test_agent_base.py` — Tests with concrete mock agent
**DEFINITION OF DONE:**
- [ ] `BaseAgent` ABC defines complete lifecycle (start → run → stop)
- [ ] Message handling is pluggable via `handle_message()`
- [ ] Status is published to registry automatically
- [ ] Graceful shutdown drains message queue
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** M (4-6 hours)
**NOTES:** This is the base class that Supervisor and Worker inherit from. Design it carefully — every agent type must be implementable on top of this interface.

---

### P2-14: Supervisor Agent

**TICKET ID:** P2-14
**TITLE:** Supervisor agent — coordinates workers, integrates results
**AGENT TYPE:** Coder
**PRIORITY:** P1
**DEPENDENCIES:** P2-13, P2-08, P2-09
**DELIVERABLES:**
- `src/omni/orchestration/supervisor.py` — `SupervisorAgent(BaseAgent)`:
  - `orchestrate(goal: str, context: OrchContext) -> OrchestrationResult`:
    1. Decompose goal into TaskGraph (via TaskDecomposer)
    2. Create ExecutionPlan (via ExecutionPlanner)
    3. For each batch in plan:
       a. Assign tasks to available workers
       b. Wait for all workers in batch to complete
       c. Collect results
    4. Integrate results (via ResultIntegrator — P2-19)
    5. Return final result
  - `handle_message()`: handles TASK_RESULT, ERROR, STATUS_UPDATE
  - Worker management: spawn workers on-demand or use pre-registered workers
  - Budget allocation: distribute budget across workers based on task cost estimates
- `src/omni/orchestration/models.py` — Orchestration models:
  - `OrchestrationResult` dataclass (success, total_cost, tasks_completed, tasks_failed, output)
  - `OrchContext` dataclass (project_path, budget, available_models, config)
- `tests/test_supervisor.py` — Integration tests with MockProvider and mock workers
**DEFINITION OF DONE:**
- [ ] Supervisor decomposes goal and executes via workers
- [ ] Tasks are assigned to available workers
- [ ] Results from all workers are collected
- [ ] Budget is respected across all workers
- [ ] Failure in one worker doesn't crash supervisor
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** L (8-10 hours)
**NOTES:** This is the central orchestration component. It ties together decomposer, planner, message bus, registry, and workers. Integration testing is critical.

---

### P2-15: Worker Agent

**TICKET ID:** P2-15
**TITLE:** Worker agent — executes individual tasks in isolation
**AGENT TYPE:** Coder
**PRIORITY:** P1
**DEPENDENCIES:** P2-13, P2-16
**DELIVERABLES:**
- `src/omni/orchestration/worker.py` — `WorkerAgent(BaseAgent)`:
  - `handle_message(TASK_ASSIGN)`:
    1. Parse task from message payload
    2. Set up worktree (via WorktreeManager)
    3. Create EditLoop for the worktree
    4. Execute task via EditLoop
    5. Collect results
    6. Send TASK_RESULT back to supervisor
    7. Clean up worktree
  - `execute_task(task: Task) -> TaskResult`:
    - Wraps EditLoop.run_cycle() with task-specific context
    - Handles errors, retries, budget checks
    - Reports progress via STATUS_UPDATE messages
  - Supports task cancellation via CANCEL message
- `tests/test_worker.py` — Tests with MockProvider and temporary git repos
**DEFINITION OF DONE:**
- [ ] Worker executes tasks via EditLoop
- [ ] Results are sent back to supervisor
- [ ] Errors are caught and reported (worker doesn't crash)
- [ ] Task cancellation works
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** M (4-6 hours)
**NOTES:** Worker is essentially an EditLoop wrapper with message bus integration. The worktree isolation (P2-16) must be ready before this ticket can fully function. For initial testing, can use the main repo without worktrees.

---

### P2-16: Git Worktree Manager

**TICKET ID:** P2-16
**TITLE:** Git worktree manager — filesystem isolation for parallel agents
**AGENT TYPE:** Coder
**PRIORITY:** P1
**DEPENDENCIES:** P2-13
**DELIVERABLES:**
- `src/omni/git/worktree.py` — `WorktreeManager` class:
  - `create(task_id: str, base_branch: str = "main") -> WorktreeInfo`:
    - Creates git worktree at `omni-llm-worktrees/<task_id>/`
    - Creates branch `omni/task/<task_id>` in worktree
    - Returns `WorktreeInfo` (path, branch, task_id)
  - `remove(task_id: str)`: clean up worktree and branch
  - `get(task_id: str) -> WorktreeInfo | None`: get worktree info
  - `list_active() -> list[WorktreeInfo]`: list all active worktrees
  - `merge_to_main(task_id: str) -> bool`: merge worktree branch to main
  - `cleanup_stale(max_age_hours: int = 24)`: remove old worktrees
- `WorktreeInfo` dataclass:
  - `task_id: str`
  - `path: Path`
  - `branch: str`
  - `created_at: datetime`
  - `base_branch: str`
- Integration with existing `GitRepository.create_worktree()` method
- `tests/test_worktree.py` — Tests with real git repos (using `tmp_path` fixture)
**DEFINITION OF DONE:**
- [ ] Worktrees can be created and removed
- [ ] Each worktree has its own branch
- [ ] Worktree branches can be merged back to main
- [ ] Stale worktree cleanup works
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** M (4-6 hours)
**NOTES:** Reuse the existing `GitRepository.create_worktree()` method. The worktree path convention should match what's already in `omni-llm-worktrees/`. Handle edge cases: worktree already exists, branch already exists, git worktree command unavailable.

---

### P2-17: Parallel Execution Engine

**TICKET ID:** P2-17
**TITLE:** Parallel execution engine — run multiple workers concurrently
**AGENT TYPE:** Coder
**PRIORITY:** P1
**DEPENDENCIES:** P2-14, P2-15, P2-16
**DELIVERABLES:**
- `src/omni/orchestration/executor.py` — `ParallelExecutor` class:
  - `execute_batch(batch: TaskBatch, workers: list[WorkerAgent]) -> list[TaskResult]`:
    - Assigns tasks to available workers
    - Runs tasks in parallel using `asyncio.gather()`
    - Collects results, handles partial failures
    - Respects max parallelism limit
  - `execute_plan(plan: ExecutionPlan, supervisor: SupervisorAgent) -> list[list[TaskResult]]`:
    - Iterates through batches sequentially
    - Each batch runs in parallel
    - Stops on critical failure (configurable)
  - Configuration:
    - `max_parallel_workers: int` (default: 4)
    - `stop_on_critical_failure: bool` (default: True)
    - `timeout_per_task: float` (default: 300s)
- `tests/test_executor.py` — Tests:
  - Parallel batch execution
  - Partial failure handling
  - Timeout handling
  - Max parallelism enforcement
**DEFINITION OF DONE:**
- [ ] Tasks in same batch run in parallel
- [ ] Batches run sequentially (respecting dependencies)
- [ ] Partial failures don't crash the executor
- [ ] Timeout per task works
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** M (4-6 hours)
**NOTES:** Pure asyncio orchestration. Use `asyncio.gather(return_exceptions=True)` for partial failure handling. The executor doesn't know about git or files — it just coordinates worker lifecycle.

---

### P2-18: Conflict Resolver

**TICKET ID:** P2-18
**TITLE:** Conflict resolution — handle file conflicts from parallel workers
**AGENT TYPE:** Coder
**PRIORITY:** P2
**DEPENDENCIES:** P2-17
**DELIVERABLES:**
- `src/omni/orchestration/conflicts.py` — `ConflictResolver` class:
  - `detect_conflicts(results: list[TaskResult]) -> list[FileConflict]`:
    - Find files modified by multiple tasks
    - Classify conflicts: content overlap, adjacent changes, independent sections
  - `resolve(conflict: FileConflict) -> Resolution`:
    - Strategy 1: Auto-merge (if changes don't overlap)
    - Strategy 2: Sequential re-execution (run conflicting tasks sequentially)
    - Strategy 3: LLM-assisted merge (ask model to merge, last resort)
  - `FileConflict` dataclass:
    - `file_path: str`
    - `task_ids: list[str]`
    - `conflict_type: str` (OVERLAP, ADJACENT, INDEPENDENT)
    - `resolution: str | None`
  - `Resolution` dataclass:
    - `strategy: str` (AUTO_MERGE, SEQUENTIAL, LLM_MERGE)
    - `success: bool`
    - `merged_content: str | None`
- `tests/test_conflicts.py` — Tests:
  - No overlap → auto-merge succeeds
  - Overlapping changes → sequential re-execution
  - Independent sections → auto-merge succeeds
**DEFINITION OF DONE:**
- [ ] File conflicts are detected from parallel task results
- [ ] Auto-merge works for non-overlapping changes
- [ ] Sequential re-execution is triggered for conflicts
- [ ] LLM-assisted merge fallback works
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** M (4-6 hours)
**NOTES:** For Phase 2, the planner (P2-09) already prevents most conflicts by splitting conflicting tasks into separate batches. The conflict resolver handles edge cases where conflicts slip through. Don't over-engineer — a simple diff-based approach is fine for now.

---

### P2-19: Result Integrator

**TICKET ID:** P2-19
**TITLE:** Result integrator — combine worker outputs into unified result
**AGENT TYPE:** Coder
**PRIORITY:** P1
**DEPENDENCIES:** P2-17, P2-18
**DELIVERABLES:**
- `src/omni/orchestration/integrator.py` — `ResultIntegrator` class:
  - `integrate(results: list[TaskResult], original_goal: str) -> OrchestrationResult`:
    - Merge file changes across all successful tasks
    - Aggregate costs
    - Generate unified commit message
    - Run verification pipeline on final result
    - Create final commit (or branch with changes for review)
  - `generate_summary(results: list[TaskResult]) -> str`:
    - LLM-powered summary of what was accomplished
    - Uses cheap model
  - Handles partial success (some tasks failed, others succeeded)
- Integration with `VerificationPipeline` from `core/verifier.py`
- `tests/test_integrator.py` — Tests
**DEFINITION OF DONE:**
- [ ] Worker results are merged into single output
- [ ] Final verification runs on merged result
- [ ] Partial success is handled (doesn't discard successful tasks)
- [ ] Cost is aggregated across all tasks
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** M (4-6 hours)
**NOTES:** The integrator is the "last mile" of orchestration. It produces the final commit/branch that the user sees. Verification must pass before the result is marked as successful.

---

### P2-20: Workflow Template Engine

**TICKET ID:** P2-20
**TITLE:** YAML workflow templates — reusable multi-step orchestration patterns
**AGENT TYPE:** Coder
**PRIORITY:** P2
**DEPENDENCIES:** P2-14
**DELIVERABLES:**
- `src/omni/orchestration/workflow.py` — `WorkflowEngine` class:
  - `load_template(path: str) -> WorkflowTemplate`: load from YAML
  - `execute(template: WorkflowTemplate, variables: dict) -> OrchestrationResult`:
    - Substitute variables in template
    - Create TaskGraph from template steps
    - Execute via Supervisor
  - `validate_template(template: WorkflowTemplate) -> list[str]`: validate structure
- `src/omni/orchestration/workflow_models.py` — Workflow models:
  - `WorkflowTemplate` dataclass:
    - `name: str`
    - `description: str`
    - `version: str`
    - `variables: dict[str, VariableDef]`
    - `steps: list[WorkflowStep]`
  - `WorkflowStep` dataclass:
    - `name: str`
    - `task_type: TaskType`
    - `description_template: str` (supports `{variable}` substitution)
    - `files: list[str]` (file patterns)
    - `depends_on: list[str]`
    - `model_override: str | None`
    - `condition: str | None` (skip step if condition not met)
  - `VariableDef` dataclass:
    - `name: str`
    - `type: str` (str, int, float, bool, list)
    - `default: Any`
    - `required: bool`
    - `description: str`
- `configs/workflows/` — Example workflow templates:
  - `configs/workflows/feature-implementation.yaml` — Implement a feature end-to-end
  - `configs/workflows/code-review.yaml` — Review code with multiple perspectives
  - `configs/workflows/refactor.yaml` — Refactor with test verification
- `tests/test_workflow.py` — Tests with example templates
**DEFINITION OF DONE:**
- [ ] YAML templates can be loaded and validated
- [ ] Variable substitution works in step descriptions
- [ ] Workflow execution creates correct TaskGraph
- [ ] At least 3 example templates work end-to-end
- [ ] All tests pass + CI green
**ESTIMATED EFFORT:** L (8-10 hours)
**NOTES:** Workflow templates are the "user-facing" abstraction for multi-agent orchestration. They should be simple YAML that non-developers can understand and modify.

---

### P2-21: End-to-End Integration Tests

**TICKET ID:** P2-21
**TITLE:** End-to-end integration tests — full orchestration pipeline
**AGENT TYPE:** Coder
**PRIORITY:** P1
**DEPENDENCIES:** P2-20, P2-19
**DELIVERABLES:**
- `tests/integration/` — Integration test suite:
  - `test_single_agent_routing.py` — Single agent with model routing
  - `test_task_decomposition.py` — Decompose → plan → execute
  - `test_parallel_execution.py` — Multiple workers in parallel worktrees
  - `test_workflow_template.py` — Execute workflow template end-to-end
  - `test_budget_enforcement.py` — Budget limits across orchestration
  - `test_conflict_resolution.py` — Parallel workers with file conflicts
- `tests/integration/conftest.py` — Shared fixtures:
  - `mock_project_repo` — Temporary git repo with sample files
  - `mock_router` — ModelRouter with MockProvider
  - `mock_supervisor` — Pre-configured supervisor
- `scripts/run_integration_tests.sh` — Script to run integration tests
**DEFINITION OF DONE:**
- [ ] All integration tests pass
- [ ] Tests cover: routing, decomposition, parallel execution, workflows, budget, conflicts
- [ ] Tests use MockProvider (no real API calls)
- [ ] Tests run in < 60 seconds
- [ ] CI green
**ESTIMATED EFFORT:** L (8-10 hours)
**NOTES:** Integration tests are critical for confidence. Use `MockProvider` extensively. Each test should be self-contained with its own temp git repo. Don't share state between tests.

---

### P2-22: Documentation and Examples

**TICKET ID:** P2-22
**TITLE:** Phase 2 documentation, examples, and CLI integration
**AGENT TYPE:** Coder
**PRIORITY:** P2
**DEPENDENCIES:** P2-21
**DELIVERABLES:**
- Update `README.md`:
  - Update project status (mark Phase 2 items complete)
  - Add orchestration section with examples
  - Add workflow template documentation
- `docs/orchestration.md` — Orchestration architecture guide:
  - Model Router explained
  - Task decomposition flow
  - Multi-agent coordination
  - Workflow templates
- `docs/workflow-templates.md` — Template authoring guide
- `examples/` — Example scripts:
  - `examples/single_agent_with_routing.py`
  - `examples/multi_agent_parallel.py`
  - `examples/workflow_from_template.py`
- Update CLI (`src/omni/cli/main.py`):
  - `omni orchestrate "goal"` — run multi-agent orchestration
  - `omni workflow run <template.yaml>` — execute workflow template
  - `omni router status` — show current routing strategy and costs
- `CHANGELOG.md` — Phase 2 changelog
**DEFINITION OF DONE:**
- [ ] README reflects Phase 2 completion
- [ ] Architecture documentation is clear and accurate
- [ ] At least 3 working examples
- [ ] CLI orchestration commands work
- [ ] All existing tests still pass
- [ ] CI green
**ESTIMATED EFFORT:** L (8-10 hours)
**NOTES:** Documentation is not optional. If it's not documented, it doesn't exist. Examples should be runnable with `MockProvider` (no API keys needed).

---

## Effort Summary

| Phase | Tickets | Effort (hours) | Agent Types |
|-------|---------|----------------|-------------|
| 2.1 Model Router | P2-01 to P2-06 | 20-30h | Thinker, Coder, Intern |
| 2.2 Task Decomposition | P2-07 to P2-10 | 16-22h | Thinker, Coder, Intern |
| 2.3 Multi-Agent Coordination | P2-11 to P2-15 | 24-34h | Thinker, Coder |
| 2.4 Parallel Execution | P2-16 to P2-19 | 22-30h | Coder |
| 2.5 Workflow & Integration | P2-20 to P2-22 | 24-30h | Coder |
| **TOTAL** | **22 tickets** | **106-146h** | |

---

## Execution Sequence (Recommended)

### Sprint 1: Model Router (Week 1-2)
1. P2-01 (Thinker: RoutingStrategy ABC) — Day 1
2. P2-02 (Coder: CostOptimizedStrategy) — Day 1-2
3. P2-03 (Coder: ModelRouter Service) — Day 2-3
4. P2-04 (Coder: Fallback Chain) — Day 3-4
5. P2-06 (Intern: Budget Enforcement) — Day 4
6. P2-05 (Coder: EditLoop Integration) — Day 4-5

### Sprint 2: Task Decomposition (Week 2-3)
7. P2-07 (Thinker: Task Model) — Day 1
8. P2-10 (Intern: Complexity Estimator) — Day 1-2
9. P2-09 (Coder: Execution Planner) — Day 2-3
10. P2-08 (Coder: Task Decomposer) — Day 3-5

### Sprint 3: Multi-Agent Coordination (Week 3-5)
11. P2-11 (Coder: Message Bus) — Day 1-2
12. P2-12 (Coder: Agent Registry) — Day 2-3
13. P2-13 (Thinker: Base Agent) — Day 3-4
14. P2-16 (Coder: Worktree Manager) — Day 4-5
15. P2-15 (Coder: Worker Agent) — Day 5-6
16. P2-14 (Coder: Supervisor Agent) — Day 6-8

### Sprint 4: Parallel Execution (Week 5-6)
17. P2-17 (Coder: Parallel Executor) — Day 1-2
18. P2-18 (Coder: Conflict Resolver) — Day 3-4
19. P2-19 (Coder: Result Integrator) — Day 4-5

### Sprint 5: Workflows & Integration (Week 6-8)
20. P2-20 (Coder: Workflow Templates) — Day 1-3
21. P2-21 (Coder: Integration Tests) — Day 3-5
22. P2-22 (Coder: Documentation) — Day 5-7

---

## Agent Spawn Instructions

For each ticket, when spawning an agent, follow this template:

```
TASK: [TICKET ID] — [TITLE]

You are working on the Omni-LLM project.
Repository: /home/openclaw/.openclaw/workspace/omni-llm

PROTOCOL:
1. Create a worktree: ./scripts/create-worktree.sh branches/YYYYMMDD_<role>-<ticket-id>
2. Work ONLY in the worktree
3. Branch from origin/main
4. Follow branch naming: branches/YYYYMMDD_<role>_<ticket-id>
5. Before opening PR, run:
   - ruff check .
   -mypy src/omni --ignore-missing-imports
   - pytest tests/ -v
6. All must pass (CI Gate)

DELIVERABLES:
[bulleted list from ticket]

DEFINITION OF DONE:
[checklist from ticket]

DEPENDENCIES:
[ticket IDs — ensure these are merged before starting]

NOTES:
[special considerations]
```

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| LLM decomposition produces invalid JSON | High | Medium | Use JSON mode, validate schema, retry with corrected prompt |
| Worktree conflicts with existing branches | Medium | Low | Use unique task_id-based naming, cleanup script |
| Message bus deadlock | Low | High | Timeouts on all receives, deadlock detection in tests |
| Budget enforcement too aggressive | Medium | Medium | Configurable thresholds, warning before hard stop |
| Parallel workers corrupt shared state | Medium | High | Worktree isolation ensures filesystem separation |
| Integration tests flaky due to timing | Medium | Medium | Use asyncio test patterns, generous timeouts |

---

*Athena — Senior Project Manager for Omni-LLM Phase 2*
*March 26, 2026*
