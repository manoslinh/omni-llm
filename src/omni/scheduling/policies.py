"""
Scheduling policies for intelligent task ordering.

Provides pluggable scheduling policies that determine which ready task
should run next. Each policy implements a different scheduling strategy:
- FIFO: First In, First Out (backward compatible with P2-11)
- Priority: Highest priority tasks first
- Deadline: Earliest deadline first
- CostAware: Cost/budget optimization
- Fair: Fair resource distribution across workflows
- Balanced: Weighted combination of all factors
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..task.models import Task


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
        # Higher score for earlier tasks (FIFO)
        return [
            SchedulingScore(task_id=t.task_id, composite_score=float(len(context.ready_tasks) - i - 1))
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
            # Normalize priority: higher number = higher priority
            # Task.priority is int, default 0
            p_score = float(task.priority) if task.priority > 0 else 0.0
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

        for i, task in enumerate(context.ready_tasks):
            # Get estimated cost from task.estimated_cost or task.context
            est_cost = 0.01  # Default estimate
            if hasattr(task, 'estimated_cost') and hasattr(task.estimated_cost, 'total_cost_usd'):
                est_cost = task.estimated_cost.total_cost_usd
            elif hasattr(task, 'context') and hasattr(task.context, 'estimated_cost_usd'):
                est_cost = task.context.estimated_cost_usd

            if budget_remaining is not None and budget_remaining > 0:
                # Cost efficiency: tasks that use less of remaining budget rank higher
                cost_ratio = est_cost / budget_remaining
                # Score from 100 (best) to 0 (worst)
                # When cost_ratio = 0 (task is free), score = 100
                # When cost_ratio = 1 (task uses all budget), score = 0
                # When cost_ratio > 1 (task exceeds budget), score = 0
                cost_score = max(0, 100 - (cost_ratio * 100))
            else:
                cost_score = 50  # Neutral

            # Add small FIFO component as tiebreaker
            fifo_component = 10 - i

            scores.append(SchedulingScore(
                task_id=task.task_id,
                composite_score=cost_score + fifo_component,
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
        now = time.time()

        # Pre-compute agent availability scores
        agent_scores: dict[str, float] = {}
        for task in context.ready_tasks:
            # Check if a preferred agent is available
            # Task doesn't have preferred_agent field, so we'll check context
            preferred = task.context.get("preferred_agent") if hasattr(task, 'context') else None
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

        # Pre-compute fairness scores
        workflow_counts: dict[str, int] = {}
        for info in context.running_tasks.values():
            wfid = info.get("workflow_id", "unknown")
            workflow_counts[wfid] = workflow_counts.get(wfid, 0) + 1
        my_running = workflow_counts.get(context.workflow_id, 0)
        fairness_base = max(0, 100 - (my_running * 20))

        scores = []
        for i, task in enumerate(context.ready_tasks):
            # Priority score: normalize task.priority (int) to 0-100 scale
            p = float(task.priority) * 10 if task.priority > 0 else 0.0
            p = min(p, 100.0)  # Cap at 100

            d = deadline_scores.get(task.task_id, 0.0)
            a = agent_scores.get(task.task_id, 0.0)

            # Cost score: default estimate
            est_cost = 0.01  # Default
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

            # Add small FIFO component as tiebreaker
            composite += (10 - i) * 0.01

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


def list_policies() -> list[str]:
    """List all available policy names."""
    return list(POLICY_REGISTRY.keys())
