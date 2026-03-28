"""
Global resource management for cross-workflow scheduling.

Provides ResourcePool for global capacity tracking and GlobalResourceManager
for priority-based resource allocation and preemption.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from .models import ResourceBudget

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

    # Thread safety lock (created in __post_init__ to avoid dataclass field issues)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @property
    def available_concurrent(self) -> int:
        return max(0, self.max_total_concurrent - self.allocated_concurrent)

    @property
    def utilization(self) -> dict[str, Any]:
        with self._lock:
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
        with self._lock:
            return self.available_concurrent >= requested_concurrent

    def allocate(self, execution_id: str, concurrent: int = 1) -> bool:
        """Reserve capacity from the global pool."""
        with self._lock:
            if not self.can_allocate(concurrent):
                return False
            self.allocated_concurrent += concurrent
            # Track in active_budgets for utilization reporting
            if execution_id not in self.active_budgets:
                self.active_budgets[execution_id] = ResourceBudget(
                    execution_id=execution_id,
                    max_concurrent=concurrent,
                )
            else:
                # Update existing budget
                self.active_budgets[execution_id].max_concurrent += concurrent
            return True

    def release(self, execution_id: str, concurrent: int = 1) -> None:
        """Return capacity to the global pool."""
        with self._lock:
            self.allocated_concurrent = max(0, self.allocated_concurrent - concurrent)
            # Update or remove budget
            if execution_id in self.active_budgets:
                budget = self.active_budgets[execution_id]
                budget.max_concurrent = max(0, budget.max_concurrent - concurrent)
                if budget.max_concurrent == 0:
                    # Remove budget if no slots left
                    del self.active_budgets[execution_id]

    def record_usage(self, tokens: int, cost: float) -> None:
        """Record token/cost usage for rate limiting."""
        with self._lock:
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
        can_run = await global_mgr.check_capacity("wf-001", task_concurrent=1)

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
            self.pool.active_budgets.pop(execution_id, None)

            if quota:
                self.pool.release(execution_id, quota.max_concurrent)
                logger.info(f"Workflow {execution_id}: released {quota.max_concurrent} slots")

    async def check_capacity(self, execution_id: str, task_concurrent: int = 1) -> bool:
        """
        Check if a workflow can schedule another task.

        Both global pool and workflow quota must have capacity.
        """
        async with self._lock:
            quota = self._quotas.get(execution_id)
            if quota is None:
                return self.pool.can_allocate(task_concurrent)

            # Access pool state under lock
            with self.pool._lock:
                budget = self.pool.active_budgets.get(execution_id)
                if budget and budget.active_tasks + task_concurrent > quota.max_concurrent:
                    return False

                return self.pool.available_concurrent >= task_concurrent

    def get_load_balancing_hint(self) -> dict[str, Any]:
        """
        Provide load balancing recommendations to the scheduler.

        Returns per-agent availability and suggested workflow distribution.
        """
        total = self.pool.max_total_concurrent
        # Get utilization first (it has its own lock)
        utilization = self.pool.utilization

        # Access pool state under lock
        with self.pool._lock:
            active = len(self.pool.active_budgets)
            if active == 0:
                return {
                    "suggested_per_workflow": total,
                    "global_utilization": utilization,
                    "agent_hints": {},
                }

            # Fair share
            fair_share = max(1, total // active)

            # Per-agent limits (copy to avoid holding lock while building dict)
            agent_max_concurrent = self.pool.agent_max_concurrent.copy()

        # Build agent hints outside of lock
        agent_hints = {}
        for agent_id, max_conc in agent_max_concurrent.items():
            agent_hints[agent_id] = {
                "max_concurrent": max_conc,
                "available": max_conc,  # TODO: track actual agent-level usage
            }

        return {
            "suggested_per_workflow": fair_share,
            "global_utilization": utilization,
            "agent_hints": agent_hints,
        }

    async def get_status(self) -> dict[str, Any]:
        """Full status for observability."""
        async with self._lock:
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
            # Take up to needed - freed, but leave at least 1 slot
            take = min(needed - freed, quota.max_concurrent - 1)
            if take > 0:
                # Update quota max_concurrent
                quota.max_concurrent -= take
                # Release slots from pool (which will update the budget)
                self.pool.release(eid, take)
                freed += take
                logger.info(
                    f"Preempted {take} slot(s) from {eid} (pri={quota.priority}) "
                    f"for {new_execution_id} (pri={priority})"
                )

        return available + freed
