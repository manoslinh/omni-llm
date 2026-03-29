# P2-16: Advanced Scheduling & Resource Management — Architecture

**Author:** Thinker (mimo-v2-pro)
**Date:** 2026-03-28
**Phase:** 2.4 — Advanced Orchestration & Multi-Agent Coordination
**Sprint:** P2-16
**Status:** Architecture Design
**PR:** (pending)

---

## 1. Problem Statement

P2-15 introduced conditional workflow execution with per-workflow resource budgets. P2-11's `Scheduler` runs tasks in parallel using a simple semaphore. P2-14's `CoordinationEngine` matches tasks to agents by capability. But the scheduling layer has clear gaps:

**What exists today:**
- Tasks are scheduled FIFO (first ready, first dispatched) with a flat concurrency limit
- Per-workflow `ResourceBudget` tracks tokens/cost/concurrency in isolation
- Agent matching is static (assigned once at coordination time, never revisited)
- No awareness of deadlines, priorities beyond `Task.priority`, or cost budgets at scheduling time
- No cross-workflow resource visibility — each workflow has its own isolated budget
- No predictive capacity — we react to demand but never anticipate it
- Failure recovery re-tries the same agent; there's no intelligent rescheduling

**What we need:**
1. **Intelligent scheduling** — priority, deadline, and cost awareness when choosing what runs next
2. **Global resource management** — see and manage resources across all active workflows
3. **Real-time adjustments** — reschedule, reassign agents, and reallocate resources at runtime
4. **Predictive capacity** — learn from execution patterns to forecast demand and prevent bottlenecks

### Design Principles (Non-Negotiable)

| Principle | Meaning |
|-----------|---------|
| **Efficiency over complexity** | Simple algorithms that work > sophisticated ones that don't |
| **Incremental improvement** | Extend existing `Scheduler`, `ResourceManager`, `TaskMatcher` — don't replace them |
| **Practical implementation** | No ML pipelines, no distributed consensus — heuristic + statistical methods |
| **Integration-first** | Every new component plugs into an existing P2-11/14/15 interface |
| **Observable** | All scheduling decisions are logged and emitted as P2-13 events |
| **Testable** | Each component has clear success metrics and deterministic test inputs |

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    P2-16: Advanced Scheduling & Resource Management      │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                     SchedulingEngine                              │   │
│  │  Extends P2-11 Scheduler with pluggable policies                  │   │
│  │                                                                   │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐    │   │
│  │  │ PriorityQueue│  │  Policy      │  │  ScheduleAdjuster   │    │   │
│  │  │ (priority +  │  │  Selector    │  │  (reschedule,       │    │   │
│  │  │  deadline +  │  │  (pick next  │  │   reassign,         │    │   │
│  │  │  cost sort)  │  │   task)      │  │   escalate at       │    │   │
│  │  │              │  │              │  │   runtime)          │    │   │
│  │  └──────────────┘  └──────────────┘  └─────────────────────┘    │   │
│  └──────────────────────────────┬───────────────────────────────────┘   │
│                                  │                                       │
│  ┌──────────────────────────────▼───────────────────────────────────┐   │
│  │                     GlobalResourceManager                         │   │
│  │  Extends P2-15 ResourceManager with cross-workflow visibility     │   │
│  │                                                                   │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐    │   │
│  │  │ ResourcePool │  │ LoadBalancer │  │ ContentionResolver  │    │   │
│  │  │ (global      │  │ (distribute  │  │ (arbitrate when     │    │   │
│  │  │  capacity    │  │  across      │  │  workflows compete) │    │   │
│  │  │  tracking)   │  │  agents)     │  │                     │    │   │
│  │  └──────────────┘  └──────────────┘  └─────────────────────┘    │   │
│  └──────────────────────────────┬───────────────────────────────────┘   │
│                                  │                                       │
│  ┌──────────────────────────────▼───────────────────────────────────┐   │
│  │                     PredictiveModule                              │   │
│  │  Lightweight statistical forecasting                              │   │
│  │                                                                   │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐    │   │
│  │  │ Workload     │  │ Demand       │  │ Bottleneck          │    │   │
│  │  │ Pattern      │  │ Forecaster   │  │ Detector            │    │   │
│  │  │ Tracker      │  │              │  │                     │    │   │
│  │  └──────────────┘  └──────────────┘  └─────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ─── Integration Layer (read-only, no changes to existing code) ────    │
│                                                                          │
│  P2-11 Scheduler ←── SchedulingEngine replaces it                       │
│  P2-14 TaskMatcher ←── ScheduleAdjuster can re-match at runtime         │
│  P2-15 ResourceManager ←── GlobalResourceManager wraps it               │
│  P2-13 Observability ←── All decisions emit events                      │
│  P2-12 CostTracker ←── Cost data feeds scheduling decisions             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Design

### 3.1 Scheduling Engine

The `SchedulingEngine` replaces the simple FIFO dispatch in P2-11's `Scheduler` with a pluggable policy system. The existing `Scheduler` loop stays — we change only *which task runs next*.

#### 3.1.1 Scheduling Policies

```python
# src/omni/execution/policies.py

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..task.models import Task, TaskStatus


class SchedulingPolicy(StrEnum):
    """Available scheduling strategies."""
    FIFO = "fifo"                  # First ready, first run (P2-11 default)
    PRIORITY = "priority"          # Highest priority first
    DEADLINE = "deadline"          # Earliest deadline first
    COST_AWARE = "cost_aware"      # Minimize total cost within constraints
    FAIR = "fair"                  # Fair distribution across workflows
    BALANCED = "balanced"          # Weighted combination of all factors


@dataclass
class SchedulingScore:
    """Score for a task in the scheduling queue."""
    task_id: str
    composite_score: float  # Higher = more urgent to schedule
    priority_score: float = 0.0
    deadline_score: float = 0.0
    cost_score: float = 0.0
    fairness_score: float = 0.0
    agent_availability_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SchedulingContext:
    """Context available to scheduling policies at decision time."""
    ready_tasks: list[Task]
    running_tasks: dict[str, Any]  # task_id → execution info
    workflow_id: str
    resource_snapshot: dict[str, Any]  # Current resource utilization
    agent_availability: dict[str, bool]  # agent_id → available
    deadline_info: dict[str, float | None] = field(default_factory=dict)  # task_id → deadline timestamp
    cost_budget_remaining: float | None = None
    execution_history: list[dict[str, Any]] = field(default_factory=list)


class SchedulingPolicyBase(ABC):
    """Base class for scheduling policies."""

    @abstractmethod
    def rank_tasks(self, context: SchedulingContext) -> list[SchedulingScore]:
        """
        Rank ready tasks by scheduling urgency.

        Returns:
            List of SchedulingScore sorted by composite_score descending.
            The scheduler dispatches tasks in this order.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Policy name for logging/observability."""


class FIFOPolicy(SchedulingPolicyBase):
    """First In, First Out — P2-11 default behavior."""

    @property
    def name(self) -> str:
        return "fifo"

    def rank_tasks(self, context: SchedulingContext) -> list[SchedulingScore]:
        return [
            SchedulingScore(task_id=t.task_id, composite_score=float(i))
            for i, t in enumerate(context.ready_tasks)
        ]


class PriorityPolicy(SchedulingPolicyBase):
    """Highest priority tasks first."""

    @property
    def name(self) -> str:
        return "priority"

    def rank_tasks(self, context: SchedulingContext) -> list[SchedulingScore]:
        scores = []
        for task in context.ready_tasks:
            # Normalize priority: CRITICAL=100, HIGH=75, MEDIUM=50, LOW=25
            priority_map = {"critical": 100, "high": 75, "medium": 50, "low": 25}
            p_score = priority_map.get(str(task.priority).lower(), 50)
            scores.append(SchedulingScore(
                task_id=task.task_id,
                composite_score=p_score,
                priority_score=p_score,
            ))
        scores.sort(key=lambda s: -s.composite_score)
        return scores


class DeadlinePolicy(SchedulingPolicyBase):
    """Earliest deadline first. Tasks without deadlines are lowest priority."""

    @property
    def name(self) -> str:
        return "deadline"

    def rank_tasks(self, context: SchedulingContext) -> list[SchedulingScore]:
        import time
        now = time.time()
        scores = []
        for task in context.ready_tasks:
            deadline = context.deadline_info.get(task.task_id)
            if deadline is not None:
                remaining = deadline - now
                # Urgency: higher when closer to deadline (negative = overdue = max urgency)
                urgency = max(0, 1000 - remaining) if remaining > 0 else 10000
            else:
                urgency = 0  # No deadline → lowest priority
            scores.append(SchedulingScore(
                task_id=task.task_id,
                composite_score=urgency,
                deadline_score=urgency,
            ))
        scores.sort(key=lambda s: -s.composite_score)
        return scores


class CostAwarePolicy(SchedulingPolicyBase):
    """
    Minimize total cost by preferring cheaper tasks when budget is tight.

    When budget is plentiful, behaves like FIFO.
    When budget is tight, schedules cheap tasks first to maximize throughput.
    """

    @property
    def name(self) -> str:
        return "cost_aware"

    def rank_tasks(self, context: SchedulingContext) -> list[SchedulingScore]:
        budget_remaining = context.cost_budget_remaining
        scores = []

        for task in context.ready_tasks:
            est_cost = task.estimated_cost.total_cost_usd if task.estimated_cost else 0.01

            if budget_remaining is not None and budget_remaining > 0:
                # Cost efficiency: tasks that use less of remaining budget rank higher
                cost_ratio = est_cost / budget_remaining
                cost_score = max(0, 100 - (cost_ratio * 1000))
            else:
                cost_score = 50  # Neutral

            scores.append(SchedulingScore(
                task_id=task.task_id,
                composite_score=cost_score,
                cost_score=cost_score,
            ))
        scores.sort(key=lambda s: -s.composite_score)
        return scores


class FairPolicy(SchedulingPolicyBase):
    """
    Fair distribution: prevent one workflow from monopolizing resources.

    Tracks tasks dispatched per workflow and penalizes overrepresented ones.
    """

    @property
    def name(self) -> str:
        return "fair"

    def rank_tasks(self, context: SchedulingContext) -> list[SchedulingScore]:
        # Count running tasks per workflow
        workflow_counts: dict[str, int] = {}
        for info in context.running_tasks.values():
            wfid = info.get("workflow_id", "unknown")
            workflow_counts[wfid] = workflow_counts.get(wfid, 0) + 1

        max_running = max(workflow_counts.values()) if workflow_counts else 1
        my_running = workflow_counts.get(context.workflow_id, 0)

        scores = []
        for i, task in enumerate(context.ready_tasks):
            # Fairness: penalize if this workflow already has many running tasks
            fairness = max(0, 100 - (my_running * 20))
            scores.append(SchedulingScore(
                task_id=task.task_id,
                composite_score=fairness + (10 - i),  # Small FIFO tiebreaker
                fairness_score=fairness,
            ))
        scores.sort(key=lambda s: -s.composite_score)
        return scores


class BalancedPolicy(SchedulingPolicyBase):
    """
    Weighted combination: priority + deadline + cost + fairness + agent availability.

    Default weights tuned for typical workloads.
    """

    def __init__(
        self,
        priority_weight: float = 0.30,
        deadline_weight: float = 0.25,
        cost_weight: float = 0.20,
        fairness_weight: float = 0.10,
        agent_weight: float = 0.15,
    ) -> None:
        total = priority_weight + deadline_weight + cost_weight + fairness_weight + agent_weight
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total:.3f}")
        self.w_priority = priority_weight
        self.w_deadline = deadline_weight
        self.w_cost = cost_weight
        self.w_fair = fairness_weight
        self.w_agent = agent_weight

    @property
    def name(self) -> str:
        return "balanced"

    def rank_tasks(self, context: SchedulingContext) -> list[SchedulingScore]:
        import time
        now = time.time()

        # Pre-compute agent availability scores
        agent_scores: dict[str, float] = {}
        for task in context.ready_tasks:
            # Check if a preferred agent is available
            preferred = getattr(task, 'preferred_agent', None)
            if preferred and context.agent_availability.get(preferred, False):
                agent_scores[task.task_id] = 100.0
            elif any(context.agent_availability.values()):
                agent_scores[task.task_id] = 50.0
            else:
                agent_scores[task.task_id] = 0.0

        # Pre-compute deadline scores
        deadline_scores: dict[str, float] = {}
        for task in context.ready_tasks:
            deadline = context.deadline_info.get(task.task_id)
            if deadline is not None:
                remaining = deadline - now
                deadline_scores[task.task_id] = max(0, 1000 - remaining) if remaining > 0 else 10000
            else:
                deadline_scores[task.task_id] = 0.0

        # Pre-compute priority scores
        priority_map = {"critical": 100, "high": 75, "medium": 50, "low": 25}

        # Pre-compute fairness scores
        workflow_counts: dict[str, int] = {}
        for info in context.running_tasks.values():
            wfid = info.get("workflow_id", "unknown")
            workflow_counts[wfid] = workflow_counts.get(wfid, 0) + 1
        my_running = workflow_counts.get(context.workflow_id, 0)
        fairness_base = max(0, 100 - (my_running * 20))

        scores = []
        for task in context.ready_tasks:
            p = priority_map.get(str(task.priority).lower(), 50)
            d = deadline_scores.get(task.task_id, 0.0)
            a = agent_scores.get(task.task_id, 0.0)

            est_cost = task.estimated_cost.total_cost_usd if task.estimated_cost else 0.01
            budget = context.cost_budget_remaining
            if budget and budget > 0:
                c = max(0, 100 - (est_cost / budget * 1000))
            else:
                c = 50.0

            composite = (
                p * self.w_priority +
                d * self.w_deadline +
                c * self.w_cost +
                fairness_base * self.w_fair +
                a * self.w_agent
            )

            scores.append(SchedulingScore(
                task_id=task.task_id,
                composite_score=round(composite, 4),
                priority_score=p,
                deadline_score=d,
                cost_score=c,
                fairness_score=fairness_base,
                agent_availability_score=a,
            ))

        scores.sort(key=lambda s: -s.composite_score)
        return scores


# ── Policy Registry ──────────────────────────────────────

POLICY_REGISTRY: dict[str, type[SchedulingPolicyBase]] = {
    SchedulingPolicy.FIFO: FIFOPolicy,
    SchedulingPolicy.PRIORITY: PriorityPolicy,
    SchedulingPolicy.DEADLINE: DeadlinePolicy,
    SchedulingPolicy.COST_AWARE: CostAwarePolicy,
    SchedulingPolicy.FAIR: FairPolicy,
    SchedulingPolicy.BALANCED: BalancedPolicy,
}

def get_policy(name: str, **kwargs: Any) -> SchedulingPolicyBase:
    """Get a scheduling policy by name."""
    if name not in POLICY_REGISTRY:
        raise ValueError(f"Unknown policy '{name}'. Available: {list(POLICY_REGISTRY.keys())}")
    return POLICY_REGISTRY[name](**kwargs)
```

#### 3.1.2 Enhanced Scheduler

The enhanced `Scheduler` in P2-11's dispatch loop gets one change: instead of `ready.sort(key=lambda t: t.priority, reverse=True)`, it delegates to the policy.

```python
# Changes to src/omni/execution/scheduler.py (minimal diff)

# BEFORE (P2-11):
#   ready.sort(key=lambda t: t.priority, reverse=True)

# AFTER (P2-16):
#   scored = self.policy.rank_tasks(self._build_scheduling_context(ready))
#   task_order = [self.graph.tasks[s.task_id] for s in scored]
```

The `Scheduler.__init__` gains one parameter:

```python
# In Scheduler.__init__, add:
#   self.policy: SchedulingPolicyBase = policy or FIFOPolicy()
#   self.scheduling_decisions: list[SchedulingScore] = []  # for observability
```

**Integration impact:** ~15 lines changed in `scheduler.py`. No changes to the scheduling loop structure, retry logic, or cancellation.

---

### 3.2 Global Resource Manager

The `GlobalResourceManager` wraps P2-15's `ResourceManager` and adds cross-workflow visibility, load balancing, and contention resolution.

```python
# src/omni/execution/global_resources.py

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..workflow.resources import ResourceBudget, ResourceManager

logger = logging.getLogger(__name__)


@dataclass
class ResourcePool:
    """
    Global resource pool shared across all workflows.

    Tracks aggregate capacity and allocation so the scheduler
    can make cross-workflow decisions.
    """
    # Total system capacity
    max_total_concurrent: int = 20
    max_total_tokens_per_minute: int | None = None
    max_total_cost_per_hour: float | None = None

    # Current allocation
    allocated_concurrent: int = 0
    tokens_used_this_minute: int = 0
    cost_used_this_hour: float = 0.0

    # Per-agent capacity limits
    agent_max_concurrent: dict[str, int] = field(default_factory=dict)

    # Active allocations: execution_id → ResourceBudget
    active_budgets: dict[str, ResourceBudget] = field(default_factory=dict)

    # Timestamps for rate window resets
    _token_window_start: float = field(default_factory=time.time)
    _cost_window_start: float = field(default_factory=time.time)

    @property
    def available_concurrent(self) -> int:
        return max(0, self.max_total_concurrent - self.allocated_concurrent)

    @property
    def utilization(self) -> dict[str, Any]:
        return {
            "total_concurrent": self.max_total_concurrent,
            "allocated": self.allocated_concurrent,
            "available": self.available_concurrent,
            "utilization_pct": round(self.allocated_concurrent / max(1, self.max_total_concurrent) * 100, 1),
            "active_workflows": len(self.active_budgets),
            "tokens_per_minute": self.tokens_used_this_minute,
            "cost_per_hour": round(self.cost_used_this_hour, 4),
        }

    def can_allocate(self, requested_concurrent: int = 1) -> bool:
        """Check if global pool can satisfy a request."""
        return self.available_concurrent >= requested_concurrent

    def allocate(self, execution_id: str, concurrent: int = 1) -> bool:
        """Reserve capacity from the global pool."""
        if not self.can_allocate(concurrent):
            return False
        self.allocated_concurrent += concurrent
        return True

    def release(self, execution_id: str, concurrent: int = 1) -> None:
        """Return capacity to the global pool."""
        self.allocated_concurrent = max(0, self.allocated_concurrent - concurrent)

    def record_usage(self, tokens: int, cost: float) -> None:
        """Record token/cost usage for rate limiting."""
        now = time.time()

        # Reset token window if >60s
        if now - self._token_window_start > 60:
            self.tokens_used_this_minute = 0
            self._token_window_start = now

        # Reset cost window if >3600s
        if now - self._cost_window_start > 3600:
            self.cost_used_this_hour = 0.0
            self._cost_window_start = now

        self.tokens_used_this_minute += tokens
        self.cost_used_this_hour += cost


@dataclass
class WorkflowQuota:
    """Quota assigned to a workflow from the global pool."""
    execution_id: str
    max_concurrent: int
    max_cost: float | None
    max_tokens: int | None
    priority: int = 0  # Higher = more share during contention
    guaranteed_share: float = 0.0  # 0.0 to 1.0 — fraction of global capacity guaranteed


class GlobalResourceManager:
    """
    Manages resources across all active workflows.

    Wraps P2-15's ResourceManager to provide:
    - Cross-workflow resource visibility
    - Fair allocation with priority-based sharing
    - Contention resolution when demand exceeds capacity
    - Load balancing recommendations

    Usage:
        global_mgr = GlobalResourceManager(pool=ResourcePool(max_total_concurrent=20))

        # When starting a workflow:
        budget = global_mgr.create_workflow_budget(
            execution_id="wf-001",
            requested_concurrent=5,
            priority=7,
        )

        # During scheduling:
        can_run = global_mgr.check_capacity("wf-001", task_concurrent=1)

        # When workflow completes:
        global_mgr.release_workflow_budget("wf-001")
    """

    def __init__(self, pool: ResourcePool | None = None) -> None:
        self.pool = pool or ResourcePool()
        self._quotas: dict[str, WorkflowQuota] = {}
        self._lock = asyncio.Lock()

    async def create_workflow_budget(
        self,
        execution_id: str,
        requested_concurrent: int = 5,
        priority: int = 0,
        guaranteed_share: float = 0.0,
        max_cost: float | None = None,
        max_tokens: int | None = None,
    ) -> ResourceBudget:
        """
        Create a resource budget for a workflow, drawing from the global pool.

        If the pool can't fully satisfy the request, allocates what's available.
        High-priority workflows can preempt low-priority allocations.
        """
        async with self._lock:
            actual_concurrent = min(requested_concurrent, self.pool.available_concurrent)

            if actual_concurrent < requested_concurrent:
                # Try preemption: steal from lower-priority workflows
                actual_concurrent = await self._try_preempt(
                    execution_id, requested_concurrent, priority
                )

            if actual_concurrent == 0:
                logger.warning(
                    f"Cannot allocate any concurrency for {execution_id}, "
                    f"pool full ({self.pool.utilization})"
                )
                # Still create budget with 0 — workflow will queue
                actual_concurrent = 0

            # Register in global pool
            if actual_concurrent > 0:
                self.pool.allocate(execution_id, actual_concurrent)

            # Create quota
            quota = WorkflowQuota(
                execution_id=execution_id,
                max_concurrent=actual_concurrent,
                max_cost=max_cost,
                max_tokens=max_tokens,
                priority=priority,
                guaranteed_share=guaranteed_share,
            )
            self._quotas[execution_id] = quota

            # Create the underlying P2-15 budget
            budget = ResourceBudget(
                execution_id=execution_id,
                max_concurrent=actual_concurrent,
                max_tokens=max_tokens,
                max_cost=max_cost,
            )
            self.pool.active_budgets[execution_id] = budget

            logger.info(
                f"Workflow {execution_id}: allocated {actual_concurrent}/{requested_concurrent} "
                f"concurrent slots (priority={priority})"
            )
            return budget

    async def release_workflow_budget(self, execution_id: str) -> None:
        """Release a workflow's resources back to the global pool."""
        async with self._lock:
            quota = self._quotas.pop(execution_id, None)
            budget = self.pool.active_budgets.pop(execution_id, None)

            if quota:
                self.pool.release(execution_id, quota.max_concurrent)
                logger.info(f"Workflow {execution_id}: released {quota.max_concurrent} slots")

    def check_capacity(self, execution_id: str, task_concurrent: int = 1) -> bool:
        """
        Check if a workflow can schedule another task.

        Both global pool and workflow quota must have capacity.
        """
        quota = self._quotas.get(execution_id)
        if quota is None:
            return self.pool.can_allocate(task_concurrent)

        budget = self.pool.active_budgets.get(execution_id)
        if budget and budget.active_tasks >= quota.max_concurrent:
            return False

        return self.pool.can_allocate(task_concurrent)

    def get_load_balancing_hint(self) -> dict[str, Any]:
        """
        Provide load balancing recommendations to the scheduler.

        Returns per-agent availability and suggested workflow distribution.
        """
        total = self.pool.max_total_concurrent
        active = len(self.pool.active_budgets)
        if active == 0:
            return {"suggested_per_workflow": total, "agent_hints": {}}

        # Fair share
        fair_share = max(1, total // active)

        # Per-agent limits
        agent_hints = {}
        for agent_id, max_conc in self.pool.agent_max_concurrent.items():
            agent_hints[agent_id] = {
                "max_concurrent": max_conc,
                "available": max_conc,  # TODO: track actual agent-level usage
            }

        return {
            "suggested_per_workflow": fair_share,
            "global_utilization": self.pool.utilization,
            "agent_hints": agent_hints,
        }

    def get_status(self) -> dict[str, Any]:
        """Full status for observability."""
        return {
            "pool": self.pool.utilization,
            "workflows": {
                eid: {
                    "concurrent": q.max_concurrent,
                    "priority": q.priority,
                    "guaranteed_share": q.guaranteed_share,
                }
                for eid, q in self._quotas.items()
            },
        }

    async def _try_preempt(
        self,
        new_execution_id: str,
        requested: int,
        priority: int,
    ) -> int:
        """
        Try to preempt lower-priority workflows to free capacity.

        Returns actual concurrent slots available after preemption.
        """
        available = self.pool.available_concurrent
        if available >= requested:
            return requested

        needed = requested - available

        # Find lower-priority workflows to preempt from
        preemptable = [
            (eid, q) for eid, q in self._quotas.items()
            if q.priority < priority and q.max_concurrent > 1
        ]
        preemptable.sort(key=lambda x: x[1].priority)  # Lowest priority first

        freed = 0
        for eid, quota in preemptable:
            if freed >= needed:
                break
            # Take 1 slot from this workflow
            take = min(1, needed - freed, quota.max_concurrent - 1)  # Leave at least 1
            if take > 0:
                quota.max_concurrent -= take
                budget = self.pool.active_budgets.get(eid)
                if budget:
                    budget.max_concurrent = quota.max_concurrent
                freed += take
                logger.info(
                    f"Preempted {take} slot(s) from {eid} (pri={quota.priority}) "
                    f"for {new_execution_id} (pri={priority})"
                )

        return available + freed
```

---

### 3.3 Predictive Module

Lightweight statistical forecasting — no ML pipelines, just sliding-window averages and trend detection.

```python
# src/omni/execution/predictive.py

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExecutionRecord:
    """Record of a completed task execution for pattern analysis."""
    task_id: str
    agent_id: str
    task_type: str
    complexity: float
    duration_seconds: float
    tokens_used: int
    cost: float
    success: bool
    completed_at: float = field(default_factory=time.time)
    workflow_id: str = ""


@dataclass
class WorkloadForecast:
    """Forecast of expected resource demand."""
    forecast_window_seconds: float
    estimated_tasks: int
    estimated_concurrent_peak: int
    estimated_total_tokens: int
    estimated_total_cost: float
    estimated_duration_seconds: float
    bottleneck_agents: list[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0 to 1.0 — higher with more history
    details: dict[str, Any] = field(default_factory=dict)


class WorkloadTracker:
    """
    Tracks execution history for pattern analysis.

    Maintains a sliding window of recent executions to compute
    statistics for scheduling decisions and forecasting.
    """

    def __init__(self, window_size: int = 500) -> None:
        self._history: deque[ExecutionRecord] = deque(maxlen=window_size)
        # Per-agent stats
        self._agent_durations: dict[str, deque[float]] = {}
        self._agent_success_rates: dict[str, deque[bool]] = {}
        # Per-task-type stats
        self._type_durations: dict[str, deque[float]] = {}

    def record(self, record: ExecutionRecord) -> None:
        """Record a completed task execution."""
        self._history.append(record)

        # Per-agent tracking
        if record.agent_id not in self._agent_durations:
            self._agent_durations[record.agent_id] = deque(maxlen=100)
            self._agent_success_rates[record.agent_id] = deque(maxlen=100)
        self._agent_durations[record.agent_id].append(record.duration_seconds)
        self._agent_success_rates[record.agent_id].append(record.success)

        # Per-type tracking
        if record.task_type not in self._type_durations:
            self._type_durations[record.task_type] = deque(maxlen=100)
        self._type_durations[record.task_type].append(record.duration_seconds)

    def get_agent_avg_duration(self, agent_id: str) -> float | None:
        """Get average execution duration for an agent."""
        durations = self._agent_durations.get(agent_id)
        if not durations:
            return None
        return sum(durations) / len(durations)

    def get_agent_success_rate(self, agent_id: str) -> float | None:
        """Get success rate for an agent (0.0 to 1.0)."""
        successes = self._agent_success_rates.get(agent_id)
        if not successes:
            return None
        return sum(successes) / len(successes)

    def get_type_avg_duration(self, task_type: str) -> float | None:
        """Get average duration for a task type."""
        durations = self._type_durations.get(task_type)
        if not durations:
            return None
        return sum(durations) / len(durations)

    def get_avg_cost(self) -> float | None:
        """Get average task cost across all history."""
        if not self._history:
            return None
        return sum(r.cost for r in self._history) / len(self._history)

    def get_throughput(self, window_seconds: float = 300) -> float:
        """Get tasks completed per second over the recent window."""
        now = time.time()
        recent = [r for r in self._history if now - r.completed_at <= window_seconds]
        if not recent or window_seconds <= 0:
            return 0.0
        return len(recent) / window_seconds


class DemandForecaster:
    """
    Forecasts resource demand based on workload patterns.

    Uses moving averages and trend detection — no ML required.
    """

    def __init__(self, tracker: WorkloadTracker) -> None:
        self.tracker = tracker

    def forecast(
        self,
        pending_tasks: list[dict[str, Any]],
        time_horizon_seconds: float = 300,
    ) -> WorkloadForecast:
        """
        Forecast resource demand for pending tasks.

        Args:
            pending_tasks: List of task descriptors with 'agent_id', 'task_type', 'complexity'
            time_horizon_seconds: How far ahead to forecast

        Returns:
            WorkloadForecast with estimates
        """
        if not pending_tasks:
            return WorkloadForecast(
                forecast_window_seconds=time_horizon_seconds,
                estimated_tasks=0,
                estimated_concurrent_peak=0,
                estimated_total_tokens=0,
                estimated_total_cost=0.0,
                estimated_duration_seconds=0.0,
                confidence=0.0,
            )

        total_duration = 0.0
        total_cost = 0.0
        total_tokens = 0
        agent_loads: dict[str, int] = {}

        for task_desc in pending_tasks:
            agent_id = task_desc.get("agent_id", "coder")
            task_type = task_desc.get("task_type", "coding")

            # Estimate duration from history
            agent_dur = self.tracker.get_agent_avg_duration(agent_id)
            type_dur = self.tracker.get_type_avg_duration(task_type)
            if agent_dur is not None:
                est_duration = agent_dur
            elif type_dur is not None:
                est_duration = type_dur
            else:
                est_duration = 30.0  # Default estimate

            total_duration += est_duration

            # Estimate cost
            avg_cost = self.tracker.get_avg_cost()
            total_cost += avg_cost if avg_cost else 0.01

            # Estimate tokens (rough: $0.14/1M → 1000 tokens/$0.00014)
            total_tokens += int(total_cost / 0.00014 * 1000) if total_cost > 0 else 1000

            # Track agent load
            agent_loads[agent_id] = agent_loads.get(agent_id, 0) + 1

        # Peak concurrent estimate: min of task count and typical concurrency
        peak_concurrent = min(len(pending_tasks), 5)

        # Bottleneck agents: those with the most tasks
        sorted_agents = sorted(agent_loads.items(), key=lambda x: -x[1])
        bottlenecks = [a for a, count in sorted_agents if count > 1]

        # Confidence based on history size
        history_size = len(self.tracker._history)
        confidence = min(1.0, history_size / 100)

        return WorkloadForecast(
            forecast_window_seconds=time_horizon_seconds,
            estimated_tasks=len(pending_tasks),
            estimated_concurrent_peak=peak_concurrent,
            estimated_total_tokens=total_tokens,
            estimated_total_cost=round(total_cost, 4),
            estimated_duration_seconds=round(total_duration / peak_concurrent, 1),
            bottleneck_agents=bottlenecks,
            confidence=round(confidence, 2),
            details={
                "agent_loads": agent_loads,
                "avg_task_duration": round(total_duration / len(pending_tasks), 1),
            },
        )


class BottleneckDetector:
    """
    Detects resource bottlenecks in real-time.

    Monitors queue depth, agent utilization, and throughput
    to identify when the system is constrained.
    """

    def __init__(self, tracker: WorkloadTracker) -> None:
        self.tracker = tracker
        self._queue_depths: deque[int] = deque(maxlen=60)  # Last 60 samples

    def sample_queue_depth(self, depth: int) -> None:
        """Record a queue depth sample."""
        self._queue_depths.append(depth)

    def detect(self) -> dict[str, Any]:
        """
        Detect current bottlenecks.

        Returns a report with bottleneck type, severity, and suggestions.
        """
        report: dict[str, Any] = {
            "has_bottleneck": False,
            "bottlenecks": [],
            "suggestions": [],
        }

        # 1. Queue depth growing = scheduling bottleneck
        if len(self._queue_depths) >= 5:
            recent = list(self._queue_depths)[-5:]
            if all(recent[i] <= recent[i + 1] for i in range(len(recent) - 1)):
                report["has_bottleneck"] = True
                report["bottlenecks"].append({
                    "type": "growing_queue",
                    "severity": "high" if recent[-1] > 10 else "medium",
                    "detail": f"Queue depth grew from {recent[0]} to {recent[-1]} over last 5 samples",
                })
                report["suggestions"].append("Increase max_concurrent or add more agents")

        # 2. Agent success rates dropping
        for agent_id in list(self.tracker._agent_success_rates.keys())[-5:]:
            rate = self.tracker.get_agent_success_rate(agent_id)
            if rate is not None and rate < 0.5:
                report["has_bottleneck"] = True
                report["bottlenecks"].append({
                    "type": "low_success_rate",
                    "severity": "high",
                    "agent_id": agent_id,
                    "detail": f"Agent {agent_id} success rate: {rate:.0%}",
                })
                report["suggestions"].append(f"Consider escalating tasks from {agent_id}")

        # 3. Throughput declining
        throughput_5m = self.tracker.get_throughput(300)
        throughput_1m = self.tracker.get_throughput(60)
        if throughput_5m > 0 and throughput_1m < throughput_5m * 0.5:
            report["has_bottleneck"] = True
            report["bottlenecks"].append({
                "type": "declining_throughput",
                "severity": "medium",
                "detail": f"Throughput dropped from {throughput_5m:.2f}/s to {throughput_1m:.2f}/s",
            })
            report["suggestions"].append("Check for agent failures or API rate limiting")

        return report
```

---

### 3.4 Schedule Adjuster

Real-time adjustments: reschedule tasks, reassign agents, escalate priorities, handle deadline renegotiation.

```python
# src/omni/execution/adjuster.py

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from ..coordination.matcher import AgentAssignment, TaskMatcher
from ..task.models import Task, TaskStatus
from .predictive import ExecutionRecord, WorkloadTracker

logger = logging.getLogger(__name__)


class AdjustmentType(StrEnum):
    """Types of runtime schedule adjustments."""
    RESCHEDULE = "reschedule"           # Re-prioritize a task
    REASSIGN = "reassign"               # Change agent assignment
    ESCALATE = "escalate"               # Escalate to higher-tier agent
    RENEGOTIATE_DEADLINE = "renegotiate" # Extend a deadline
    BURST = "burst"                     # Temporarily increase concurrency


@dataclass
class Adjustment:
    """A runtime schedule adjustment."""
    adjustment_type: AdjustmentType
    task_id: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdjustmentResult:
    """Result of applying an adjustment."""
    adjustment: Adjustment
    applied: bool
    previous_value: Any = None
    new_value: Any = None
    message: str = ""


class ScheduleAdjuster:
    """
    Applies runtime adjustments to the schedule.

    Integrates with:
    - P2-14 TaskMatcher for agent reassignment
    - P2-15 WorkflowContext for workflow-level state
    - WorkloadTracker for data-driven decisions

    Usage:
        adjuster = ScheduleAdjuster(matcher=task_matcher, tracker=tracker)

        # React to a failure
        result = await adjuster.handle_task_failure(
            task=failed_task,
            current_agent="coder",
            error="Rate limit exceeded",
        )

        # React to a deadline approaching
        result = await adjuster.escalate_for_deadline(
            task=urgent_task,
            seconds_remaining=30,
        )
    """

    def __init__(
        self,
        matcher: TaskMatcher | None = None,
        tracker: WorkloadTracker | None = None,
    ) -> None:
        self.matcher = matcher
        self.tracker = tracker
        self._adjustment_log: list[AdjustmentResult] = []

    async def handle_task_failure(
        self,
        task: Task,
        current_agent: str,
        error: str,
    ) -> AdjustmentResult:
        """
        React to a task failure by reassigning or rescheduling.

        Strategy:
        1. If error is transient (rate limit, timeout) → reschedule with backoff
        2. If error is permanent (auth, bad input) → reassign to higher-tier agent
        3. If no higher-tier available → reschedule with lower priority
        """
        is_transient = any(kw in error.lower() for kw in [
            "rate limit", "timeout", "429", "500", "502", "503", "temporary",
        ])

        if is_transient:
            adjustment = Adjustment(
                adjustment_type=AdjustmentType.RESCHEDULE,
                task_id=task.task_id,
                reason=f"Transient failure on {current_agent}: {error}",
                details={"backoff_seconds": 5.0},
            )
        elif self.matcher:
            # Permanent failure → try reassigning
            new_assignment = self.matcher.match(task)
            if new_assignment.agent_id != current_agent:
                adjustment = Adjustment(
                    adjustment_type=AdjustmentType.REASSIGN,
                    task_id=task.task_id,
                    reason=f"Permanent failure on {current_agent}: {error}",
                    details={
                        "previous_agent": current_agent,
                        "new_agent": new_assignment.agent_id,
                        "confidence": new_assignment.confidence.value,
                    },
                )
            else:
                adjustment = Adjustment(
                    adjustment_type=AdjustmentType.ESCALATE,
                    task_id=task.task_id,
                    reason=f"Reassignment unavailable, escalating: {error}",
                    details={"escalate_from": current_agent},
                )
        else:
            adjustment = Adjustment(
                adjustment_type=AdjustmentType.RESCHEDULE,
                task_id=task.task_id,
                reason=f"No matcher available, rescheduling: {error}",
                details={"retry": True},
            )

        result = AdjustmentResult(
            adjustment=adjustment,
            applied=True,
            message=f"Applied {adjustment.adjustment_type.value} for {task.task_id}",
        )
        self._adjustment_log.append(result)

        logger.info(
            f"Schedule adjustment: {adjustment.adjustment_type.value} "
            f"for {task.task_id} — {adjustment.reason}"
        )
        return result

    async def escalate_for_deadline(
        self,
        task: Task,
        seconds_remaining: float,
    ) -> AdjustmentResult:
        """
        Escalate a task that's approaching its deadline.

        Actions:
        1. If matcher available → reassign to faster/cheaper agent
        2. Flag for priority boost in scheduling queue
        """
        if seconds_remaining <= 0:
            # Already overdue — maximum urgency
            urgency = "overdue"
        elif seconds_remaining < 60:
            urgency = "critical"
        elif seconds_remaining < 300:
            urgency = "high"
        else:
            urgency = "normal"

        adjustment = Adjustment(
            adjustment_type=AdjustmentType.REASSIGN if urgency in ("critical", "overdue") else AdjustmentType.RESCHEDULE,
            task_id=task.task_id,
            reason=f"Deadline {urgency}: {seconds_remaining:.0f}s remaining",
            details={
                "urgency": urgency,
                "seconds_remaining": seconds_remaining,
                "priority_boost": urgency in ("critical", "overdue"),
            },
        )

        result = AdjustmentResult(
            adjustment=adjustment,
            applied=True,
            message=f"Deadline escalation ({urgency}) for {task.task_id}",
        )
        self._adjustment_log.append(result)
        return result

    async def burst_capacity(
        self,
        workflow_id: str,
        additional_concurrent: int,
        duration_seconds: float,
        reason: str,
    ) -> AdjustmentResult:
        """
        Temporarily increase concurrency for a workflow.

        Used when a workflow is falling behind and needs a burst.
        The burst is time-limited — capacity is returned after duration.
        """
        adjustment = Adjustment(
            adjustment_type=AdjustmentType.BURST,
            task_id="",  # Workflow-level, not task-level
            reason=reason,
            details={
                "workflow_id": workflow_id,
                "additional_concurrent": additional_concurrent,
                "duration_seconds": duration_seconds,
            },
        )

        result = AdjustmentResult(
            adjustment=adjustment,
            applied=True,
            message=f"Burst +{additional_concurrent} concurrent for {workflow_id} "
                    f"for {duration_seconds:.0f}s: {reason}",
        )
        self._adjustment_log.append(result)
        return result

    def get_adjustment_history(self) -> list[AdjustmentResult]:
        """Get all adjustments made this session."""
        return self._adjustment_log.copy()

    def get_adjustment_summary(self) -> dict[str, Any]:
        """Summary of adjustments by type."""
        summary: dict[str, int] = {}
        for r in self._adjustment_log:
            t = r.adjustment.adjustment_type.value
            summary[t] = summary.get(t, 0) + 1
        return {
            "total_adjustments": len(self._adjustment_log),
            "by_type": summary,
        }
```

---

## 4. Integration Plan

### 4.1 Integration with P2-11 (Scheduler)

**What changes:** `Scheduler.__init__` gains an optional `policy` parameter. The `_get_ready_tasks` sort is delegated to the policy.

**Diff scope:** ~15 lines in `scheduler.py`, ~5 lines in `engine.py` to pass policy through.

```python
# In P2-11 engine.py, when creating Scheduler:
scheduler = Scheduler(
    graph=graph,
    config=config,
    task_executor=executor.execute,
    on_task_complete=...,
    on_propagate_skip=...,
    policy=policy,  # NEW: defaults to FIFOPolicy for backward compat
)
```

### 4.2 Integration with P2-14 (Coordination Engine)

**What changes:** `ScheduleAdjuster` uses `TaskMatcher` for runtime reassignment. No changes to `CoordinationEngine` itself.

**New wiring:** The `ScheduleAdjuster` takes an optional `TaskMatcher` reference. When a task fails and needs reassignment, it calls `matcher.match(task)` to find a new agent.

### 4.3 Integration with P2-15 (Workflow Orchestration)

**What changes:** `WorkflowOrchestrator._run_definition()` creates workflow budgets via `GlobalResourceManager` instead of directly creating `ResourceBudget`.

**Diff scope:** ~10 lines in `orchestrator.py` — replace `ResourceManager.create_budget()` call with `GlobalResourceManager.create_workflow_budget()`.

### 4.4 Integration with P2-13 (Observability)

**New events:**

| Event | Payload | Trigger |
|-------|---------|---------|
| `task_scheduled` | task_id, policy, composite_score, rank | Task dispatched by scheduler |
| `policy_applied` | policy_name, task_count, ranking_scores | Policy ranks a batch of tasks |
| `resource_allocated` | execution_id, concurrent, pool_utilization | Workflow gets resources |
| `resource_released` | execution_id, concurrent | Workflow finishes |
| `capacity_preempted` | from_execution, to_execution, slots | Preemption occurs |
| `schedule_adjusted` | adjustment_type, task_id, reason | Runtime adjustment made |
| `bottleneck_detected` | type, severity, suggestions | Bottleneck identified |
| `workload_forecasted` | estimated_tasks, estimated_cost, confidence | Forecast generated |

### 4.5 Integration with P2-12 (Cost Tracking)

**What changes:** `CostAwarePolicy` and `BalancedPolicy` read from `CostTracker` via the `SchedulingContext.cost_budget_remaining` field. No changes to P2-12 itself.

---

## 5. File Structure

```
src/omni/execution/
├── __init__.py              # Updated exports
├── config.py                # Unchanged
├── db.py                    # Unchanged
├── engine.py                # Minor: pass policy to Scheduler
├── executor.py              # Unchanged
├── models.py                # Unchanged
├── scheduler.py             # Minor: accept policy, delegate ranking
├── policies.py              # NEW: SchedulingPolicy*, BalancedPolicy, registry
├── global_resources.py      # NEW: GlobalResourceManager, ResourcePool, WorkflowQuota
├── predictive.py            # NEW: WorkloadTracker, DemandForecaster, BottleneckDetector
└── adjuster.py              # NEW: ScheduleAdjuster, Adjustment, AdjustmentResult

tests/
├── test_policies.py         # Policy ranking correctness, edge cases
├── test_global_resources.py # Pool allocation, preemption, quota management
├── test_predictive.py       # Forecasting accuracy, bottleneck detection
├── test_adjuster.py         # Failure handling, deadline escalation, burst
└── test_scheduling_integration.py  # End-to-end: policy + resources + adjustments

docs/
└── P2-16-ARCHITECTURE.md    # This document
```

---

## 6. Implementation Strategy

### Phase 1: Scheduling Policies (~3 hours)

| Step | File | Description | Est. |
|------|------|-------------|------|
| 1.1 | `policies.py` | `SchedulingPolicy` enum, `SchedulingScore`, `SchedulingContext` | 30min |
| 1.2 | `policies.py` | `FIFOPolicy`, `PriorityPolicy`, `DeadlinePolicy` | 1h |
| 1.3 | `policies.py` | `CostAwarePolicy`, `FairPolicy`, `BalancedPolicy` | 1h |
| 1.4 | `scheduler.py` | Integrate policy into `_get_ready_tasks` sort | 30min |

### Phase 2: Global Resource Manager (~3 hours)

| Step | File | Description | Est. |
|------|------|-------------|------|
| 2.1 | `global_resources.py` | `ResourcePool` — global capacity tracking | 1h |
| 2.2 | `global_resources.py` | `GlobalResourceManager` — budget creation, release | 1h |
| 2.3 | `global_resources.py` | Preemption logic, load balancing hints | 1h |

### Phase 3: Predictive Module (~2 hours)

| Step | File | Description | Est. |
|------|------|-------------|------|
| 3.1 | `predictive.py` | `WorkloadTracker` — sliding window history | 45min |
| 3.2 | `predictive.py` | `DemandForecaster` — moving average forecasts | 45min |
| 3.3 | `predictive.py` | `BottleneckDetector` — queue depth + throughput | 30min |

### Phase 4: Schedule Adjuster (~2 hours)

| Step | File | Description | Est. |
|------|------|-------------|------|
| 4.1 | `adjuster.py` | `ScheduleAdjuster` — failure handling, reassignment | 1h |
| 4.2 | `adjuster.py` | Deadline escalation, capacity bursting | 45min |
| 4.3 | `adjuster.py` | Adjustment logging and summary | 15min |

### Phase 5: Tests & Integration (~3 hours)

| Step | File | Description | Est. |
|------|------|-------------|------|
| 5.1 | `test_policies.py` | Policy ranking tests, edge cases | 1h |
| 5.2 | `test_global_resources.py` | Pool allocation, preemption tests | 45min |
| 5.3 | `test_predictive.py` | Forecast and bottleneck tests | 45min |
| 5.4 | `test_scheduling_integration.py` | End-to-end policy + resources + adjuster | 30min |

**Total estimated time: ~13 hours**

---

## 7. API Summary

### Quick Start

```python
from omni.execution.policies import get_policy, SchedulingPolicy
from omni.execution.global_resources import GlobalResourceManager, ResourcePool
from omni.execution.predictive import WorkloadTracker, DemandForecaster, BottleneckDetector
from omni.execution.adjuster import ScheduleAdjuster

# ── 1. Use a scheduling policy ──────────────────────────

policy = get_policy(SchedulingPolicy.BALANCED, priority_weight=0.3, deadline_weight=0.25)
# Or simply:
policy = get_policy("priority")

# ── 2. Global resource management ──────────────────────

pool = ResourcePool(max_total_concurrent=20)
global_mgr = GlobalResourceManager(pool=pool)

# Allocate to workflow
budget = await global_mgr.create_workflow_budget(
    execution_id="wf-001",
    requested_concurrent=5,
    priority=8,
    max_cost=1.00,
)

# Check status
print(global_mgr.get_status())

# Release when done
await global_mgr.release_workflow_budget("wf-001")

# ── 3. Predictive scheduling ──────────────────────────

tracker = WorkloadTracker()
forecaster = DemandForecaster(tracker)

# After tasks execute, record them:
tracker.record(ExecutionRecord(
    task_id="t1", agent_id="coder", task_type="coding",
    complexity=5.0, duration_seconds=12.3, tokens_used=2000,
    cost=0.003, success=True,
))

# Forecast pending work
forecast = forecaster.forecast(
    pending_tasks=[{"agent_id": "coder", "task_type": "coding"}],
    time_horizon_seconds=300,
)
print(f"Estimated cost: ${forecast.estimated_total_cost}")
print(f"Bottleneck agents: {forecast.bottleneck_agents}")

# ── 4. Real-time adjustments ──────────────────────────

adjuster = ScheduleAdjuster(matcher=task_matcher, tracker=tracker)

# On failure:
result = await adjuster.handle_task_failure(
    task=failed_task,
    current_agent="coder",
    error="Rate limit exceeded",
)
print(result.message)  # "Applied reschedule for t1"

# On deadline pressure:
result = await adjuster.escalate_for_deadline(task, seconds_remaining=30)
```

### With P2-11 Scheduler (drop-in)

```python
from omni.execution.scheduler import Scheduler
from omni.execution.policies import get_policy

policy = get_policy("balanced")
scheduler = Scheduler(
    graph=task_graph,
    config=ExecutionConfig(max_concurrent=5),
    task_executor=executor.execute,
    on_task_complete=...,
    on_propagate_skip=...,
    policy=policy,  # NEW — defaults to FIFO if omitted
)
await scheduler.run()
```

---

## 8. Success Metrics

| Metric | How to Measure | Target |
|--------|---------------|--------|
| **Scheduling latency** | Time from task-ready to task-dispatched | <50ms per decision |
| **Throughput improvement** | Tasks/minute with BalancedPolicy vs FIFO | ≥15% improvement on mixed workloads |
| **Cost efficiency** | Total cost for same workload, CostAware vs FIFO | ≥10% cost reduction |
| **Fairness** | Std deviation of per-workflow concurrency usage | <20% variance |
| **Forecast accuracy** | Predicted vs actual duration for 100-task workload | ±30% (with 100+ history records) |
| **Bottleneck detection time** | Seconds from bottleneck onset to detection | <30 seconds |
| **Preemption success** | % of high-priority workflows that get capacity when needed | ≥90% |
| **Reassignment success** | % of failed tasks that succeed after reassignment | ≥70% |
| **Backward compatibility** | Existing P2-11 tests still pass with no changes to callers | 100% pass rate |

---

## 9. Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Policies are classes, not functions** | Each policy encapsulates scoring logic + state. Class hierarchy makes adding policies trivial. |
| **BalancedPolicy as default** | Single-factor policies (priority-only, deadline-only) are too naive for real workloads. Balanced gives good-enough defaults. |
| **GlobalResourceManager wraps, not replaces, P2-15 ResourceManager** | Backward compatible. Existing code using `ResourceManager` directly still works. Global manager adds a layer above. |
| **Preemption takes 1 slot at a time** | Conservative — don't starve low-priority workflows. Steal gently. |
| **WorkloadTracker uses deque, not database** | In-memory sliding window is fast and simple. Persist to SQLite in Phase 2 if needed. |
| **BottleneckDetector is reactive, not predictive** | Detects problems as they emerge (queue growing, throughput dropping). Prediction would need ML — overkill for now. |
| **ScheduleAdjuster is async** | Adjustments may involve I/O (re-matching agents, logging). Async keeps the scheduler non-blocking. |
| **No distributed scheduling** | Single-process orchestration. Distributed scheduling is Phase 3+. |
| **Forecasting uses averages, not ML** | Moving averages are sufficient for "how long will these tasks take?" ML adds complexity without proportional value at this scale. |
| **~13 hours estimated** | Practical scope. Each component is <200 lines. Focus on integration, not algorithms. |

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Preemption causes workflow starvation | Medium | Limit preemption to 1 slot per operation. Starvation detection: log if a workflow is preempted >3 times. |
| BalancedPolicy weights are wrong for some workloads | Low | Expose weights as configuration. Users can tune or use single-factor policies. |
| Forecaster is inaccurate with little history | Low | Confidence score is explicit (0.0 with no history). Falls back to default estimates. |
| GlobalResourceManager adds latency to scheduling | Low | `check_capacity()` is O(1) dict lookup. Pool state is in-memory. No I/O. |
| Integration with P2-11 breaks existing behavior | Medium | FIFO policy is identical to current behavior. All existing tests must pass unchanged. |
| Over-engineering | Medium | Each component is <200 lines. No external dependencies. No ML. Phased delivery. |

---

## 11. Open Questions

1. **Should scheduling policies be configurable per-workflow or globally?**
   Proposed: Both. Global default, per-workflow override. The `SchedulingContext` carries the workflow_id so policies can be workflow-aware.

2. **Should the global resource pool support dynamic resizing?**
   Proposed: Yes — `ResourcePool.max_total_concurrent` can be changed at runtime. A pool with 20 slots can become 10 during a cost-saving mode.

3. **How does `ScheduleAdjuster` interact with P2-15's state machine?**
   Proposed: Adjustments are applied to the `WorkflowContext` before the next node dispatch. The state machine reads adjustments as hints, not commands.

4. **Should `WorkloadTracker` persist to SQLite?**
   Proposed: Phase 2 enhancement. In-memory is fine for single-session forecasting. Persist for cross-session pattern learning.

5. **Should we add a "deadline" field to the `Task` model?**
   Proposed: Yes, add `deadline: float | None` (epoch timestamp) to `Task`. Optional field — `None` means no deadline. This feeds the `DeadlinePolicy`.

---

## 12. Summary

P2-16 adds three layers of intelligence on top of existing infrastructure:

1. **Scheduling Policies** — Pluggable algorithms that decide *what runs next*. Six policies from simple FIFO to weighted balanced scoring. ~15 lines changed in P2-11.

2. **Global Resource Management** — Cross-workflow capacity tracking, fair allocation with priority-based preemption, and load balancing hints. Wraps P2-15's `ResourceManager` without replacing it.

3. **Predictive + Reactive** — `WorkloadTracker` records execution patterns, `DemandForecaster` estimates future demand, `BottleneckDetector` catches problems early, and `ScheduleAdjuster` reacts to failures and deadline pressure with intelligent reassignment.

**Total scope:** ~4 new files, ~13 hours, no new dependencies, backward compatible with all existing P2-11/14/15 code.
