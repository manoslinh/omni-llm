"""
Tests for scheduling policies.
"""

import time

import pytest

from src.omni.scheduling.policies import (
    BalancedPolicy,
    CostAwarePolicy,
    DeadlinePolicy,
    FairPolicy,
    FIFOPolicy,
    PriorityPolicy,
    SchedulingContext,
    SchedulingScore,
    get_policy,
    list_policies,
)
from src.omni.task.models import Task, TaskType


def create_test_tasks() -> list[Task]:
    """Create test tasks with different priorities."""
    return [
        Task(
            description="Task A",
            task_id="A",
            priority=1,
            task_type=TaskType.CODE_GENERATION,
        ),
        Task(
            description="Task B",
            task_id="B",
            priority=3,
            task_type=TaskType.CODE_REVIEW,
        ),
        Task(
            description="Task C",
            task_id="C",
            priority=2,
            task_type=TaskType.TESTING,
        ),
        Task(
            description="Task D",
            task_id="D",
            priority=0,
            task_type=TaskType.DOCUMENTATION,
        ),
    ]


def create_test_context(ready_tasks: list[Task]) -> SchedulingContext:
    """Create a test scheduling context."""
    return SchedulingContext(
        ready_tasks=ready_tasks,
        running_tasks={
            "running_1": {"workflow_id": "wf1", "started_at": time.time() - 10},
            "running_2": {"workflow_id": "wf2", "started_at": time.time() - 5},
        },
        workflow_id="wf1",
        resource_snapshot={
            "concurrent_used": 2,
            "concurrent_available": 3,
            "total_tasks": 10,
        },
        agent_availability={
            "intern": True,
            "coder": True,
            "reader": False,
            "thinker": True,
        },
        deadline_info={
            "A": time.time() + 300,  # 5 minutes from now
            "B": time.time() + 60,   # 1 minute from now
            "C": time.time() + 600,  # 10 minutes from now
        },
        cost_budget_remaining=10.0,
        execution_history=[],
    )


def test_fifo_policy() -> None:
    """Test FIFO policy preserves order."""
    tasks = create_test_tasks()
    context = create_test_context(tasks)
    policy = FIFOPolicy()

    scores = policy.rank_tasks(context)

    # Should be in original order (A, B, C, D) with decreasing scores
    assert len(scores) == 4
    assert scores[0].task_id == "A"
    assert scores[1].task_id == "B"
    assert scores[2].task_id == "C"
    assert scores[3].task_id == "D"

    # Scores should be 3, 2, 1, 0 (or similar)
    assert scores[0].composite_score > scores[1].composite_score
    assert scores[1].composite_score > scores[2].composite_score
    assert scores[2].composite_score > scores[3].composite_score


def test_priority_policy() -> None:
    """Test priority policy sorts by priority."""
    tasks = create_test_tasks()
    context = create_test_context(tasks)
    policy = PriorityPolicy()

    scores = policy.rank_tasks(context)

    # Should be sorted by priority: B(3), C(2), A(1), D(0)
    assert len(scores) == 4
    assert scores[0].task_id == "B"  # Highest priority (3)
    assert scores[1].task_id == "C"  # Priority 2
    assert scores[2].task_id == "A"  # Priority 1
    assert scores[3].task_id == "D"  # Priority 0

    # Check priority scores
    assert scores[0].priority_score == 3.0
    assert scores[1].priority_score == 2.0
    assert scores[2].priority_score == 1.0
    assert scores[3].priority_score == 0.0


def test_deadline_policy() -> None:
    """Test deadline policy sorts by urgency."""
    tasks = create_test_tasks()
    context = create_test_context(tasks)
    policy = DeadlinePolicy()

    scores = policy.rank_tasks(context)

    # Should be sorted by deadline urgency: B (60s), A (300s), C (600s), D (no deadline)
    assert len(scores) == 4
    assert scores[0].task_id == "B"  # Most urgent (60s)
    assert scores[1].task_id == "A"  # 300s
    assert scores[2].task_id == "C"  # 600s
    assert scores[3].task_id == "D"  # No deadline

    # Check deadline scores
    assert scores[0].deadline_score > scores[1].deadline_score
    assert scores[1].deadline_score > scores[2].deadline_score
    assert scores[2].deadline_score > scores[3].deadline_score  # D has 0


def test_cost_aware_policy() -> None:
    """Test cost-aware policy with budget."""
    tasks = create_test_tasks()
    context = create_test_context(tasks)
    policy = CostAwarePolicy()

    scores = policy.rank_tasks(context)

    # All tasks should have cost scores
    assert len(scores) == 4
    for score in scores:
        assert score.cost_score > 0
        assert score.composite_score > 0


def test_fair_policy() -> None:
    """Test fair policy considers workflow distribution."""
    tasks = create_test_tasks()
    context = create_test_context(tasks)
    policy = FairPolicy()

    scores = policy.rank_tasks(context)

    # All tasks should have fairness scores
    assert len(scores) == 4
    for score in scores:
        assert score.fairness_score > 0
        assert score.composite_score > 0


def test_balanced_policy() -> None:
    """Test balanced policy with weighted combination."""
    tasks = create_test_tasks()
    context = create_test_context(tasks)
    policy = BalancedPolicy()

    scores = policy.rank_tasks(context)

    # All tasks should have composite scores with multiple components
    assert len(scores) == 4
    for score in scores:
        assert score.composite_score > 0
        assert score.priority_score >= 0
        assert score.deadline_score >= 0
        assert score.cost_score > 0
        assert score.fairness_score > 0
        assert score.agent_availability_score >= 0


def test_balanced_policy_custom_weights() -> None:
    """Test balanced policy with custom weights."""
    tasks = create_test_tasks()
    context = create_test_context(tasks)

    # Create policy with custom weights that sum to 1.0
    policy = BalancedPolicy(
        priority_weight=0.5,
        deadline_weight=0.3,
        cost_weight=0.1,
        fairness_weight=0.05,
        agent_weight=0.05,
    )

    scores = policy.rank_tasks(context)
    assert len(scores) == 4

    # Test invalid weights - need to provide all weights when testing invalid case
    with pytest.raises(ValueError, match="Weights must sum to 1.0"):
        BalancedPolicy(
            priority_weight=0.5,
            deadline_weight=0.5,
            cost_weight=0.2,
            fairness_weight=0.1,
            agent_weight=0.1,
        )  # Sum = 1.4


def test_policy_registry() -> None:
    """Test policy registry and factory function."""
    policies = list_policies()
    assert len(policies) == 6
    assert "fifo" in policies
    assert "priority" in policies
    assert "deadline" in policies
    assert "cost_aware" in policies
    assert "fair" in policies
    assert "balanced" in policies

    # Test getting policies
    fifo = get_policy("fifo")
    assert isinstance(fifo, FIFOPolicy)
    assert fifo.name == "fifo"

    priority = get_policy("priority")
    assert isinstance(priority, PriorityPolicy)
    assert priority.name == "priority"

    balanced = get_policy("balanced", priority_weight=0.4, deadline_weight=0.3, cost_weight=0.15, fairness_weight=0.1, agent_weight=0.05)
    assert isinstance(balanced, BalancedPolicy)
    assert balanced.name == "balanced"

    # Test invalid policy name
    with pytest.raises(ValueError, match="Unknown policy"):
        get_policy("invalid_policy")


def test_scheduling_score_metadata() -> None:
    """Test scheduling score with metadata."""
    score = SchedulingScore(
        task_id="test_task",
        composite_score=85.5,
        priority_score=75.0,
        deadline_score=90.0,
        cost_score=80.0,
        fairness_score=70.0,
        agent_availability_score=95.0,
        metadata={"reason": "urgent", "workflow": "wf1"},
    )

    assert score.task_id == "test_task"
    assert score.composite_score == 85.5
    assert score.priority_score == 75.0
    assert score.deadline_score == 90.0
    assert score.cost_score == 80.0
    assert score.fairness_score == 70.0
    assert score.agent_availability_score == 95.0
    assert score.metadata["reason"] == "urgent"
    assert score.metadata["workflow"] == "wf1"


def test_scheduling_context_validation() -> None:
    """Test scheduling context creation and validation."""
    tasks = create_test_tasks()

    context = SchedulingContext(
        ready_tasks=tasks,
        running_tasks={"task1": {"workflow_id": "wf1"}},
        workflow_id="wf1",
        resource_snapshot={"concurrent": 5},
        agent_availability={"agent1": True},
        deadline_info={"task1": time.time() + 100},
        cost_budget_remaining=50.0,
        execution_history=[{"task": "task1", "duration": 10}],
    )

    assert len(context.ready_tasks) == 4
    assert context.workflow_id == "wf1"
    assert context.cost_budget_remaining == 50.0
    assert len(context.deadline_info) == 1
    assert len(context.execution_history) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
