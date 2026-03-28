"""
Tests for scheduling policies.
"""

import time
from unittest.mock import Mock

import pytest

from omni.execution.policies import (
    BalancedPolicy,
    CostAwarePolicy,
    DeadlinePolicy,
    FairPolicy,
    FIFOPolicy,
    PriorityPolicy,
    SchedulingContext,
    SchedulingPolicy,
    get_policy,
)
from omni.task.models import Task


def create_mock_task(task_id: str, priority: int = 50):
    """Create a mock task for testing."""
    task = Mock(spec=Task)
    task.task_id = task_id
    task.priority = priority
    task.estimated_cost = None
    return task


def create_test_context(ready_tasks=None, running_tasks=None):
    """Create a test scheduling context."""
    if ready_tasks is None:
        ready_tasks = []
    if running_tasks is None:
        running_tasks = {}

    return SchedulingContext(
        ready_tasks=ready_tasks,
        running_tasks=running_tasks,
        workflow_id="test-workflow",
        resource_snapshot={},
        agent_availability={"coder": True, "intern": True},
        deadline_info={},
        cost_budget_remaining=None,
        execution_history=[],
    )


class TestFIFOPolicy:
    """Tests for FIFO scheduling policy."""

    def test_name(self):
        policy = FIFOPolicy()
        assert policy.name == "fifo"

    def test_rank_tasks_preserves_order(self):
        policy = FIFOPolicy()
        tasks = [
            create_mock_task("task1"),
            create_mock_task("task2"),
            create_mock_task("task3"),
        ]
        context = create_test_context(ready_tasks=tasks)

        scores = policy.rank_tasks(context)

        assert len(scores) == 3
        # Should preserve order with decreasing composite scores
        assert scores[0].task_id == "task1"
        assert scores[1].task_id == "task2"
        assert scores[2].task_id == "task3"
        assert scores[0].composite_score > scores[1].composite_score > scores[2].composite_score


class TestPriorityPolicy:
    """Tests for priority scheduling policy."""

    def test_name(self):
        policy = PriorityPolicy()
        assert policy.name == "priority"

    def test_rank_tasks_by_priority(self):
        policy = PriorityPolicy()
        tasks = [
            create_mock_task("task_low", 25),      # LOW priority
            create_mock_task("task_high", 75),     # HIGH priority
            create_mock_task("task_critical", 100), # CRITICAL priority
        ]
        context = create_test_context(ready_tasks=tasks)

        scores = policy.rank_tasks(context)

        assert len(scores) == 3
        # Should sort by priority: CRITICAL (100) > HIGH (75) > LOW (25)
        assert scores[0].task_id == "task_critical"
        assert scores[1].task_id == "task_high"
        assert scores[2].task_id == "task_low"
        assert scores[0].composite_score > scores[1].composite_score > scores[2].composite_score


class TestDeadlinePolicy:
    """Tests for deadline scheduling policy."""

    def test_name(self):
        policy = DeadlinePolicy()
        assert policy.name == "deadline"

    def test_rank_tasks_by_deadline(self):
        policy = DeadlinePolicy()
        tasks = [
            create_mock_task("task1"),
            create_mock_task("task2"),
            create_mock_task("task3"),
        ]

        now = time.time()
        deadline_info = {
            "task1": now + 300,  # 5 minutes from now
            "task2": now + 60,   # 1 minute from now (most urgent)
            "task3": None,       # No deadline (least urgent)
        }

        context = create_test_context(ready_tasks=tasks)
        context.deadline_info = deadline_info

        scores = policy.rank_tasks(context)

        assert len(scores) == 3
        # Should sort by deadline urgency: task2 (1min) > task1 (5min) > task3 (no deadline)
        assert scores[0].task_id == "task2"
        assert scores[1].task_id == "task1"
        assert scores[2].task_id == "task3"
        assert scores[0].composite_score > scores[1].composite_score > scores[2].composite_score

    def test_overdue_tasks_highest_priority(self):
        policy = DeadlinePolicy()
        tasks = [
            create_mock_task("task_on_time"),
            create_mock_task("task_overdue"),
        ]

        now = time.time()
        deadline_info = {
            "task_on_time": now + 60,
            "task_overdue": now - 30,  # Overdue by 30 seconds
        }

        context = create_test_context(ready_tasks=tasks)
        context.deadline_info = deadline_info

        scores = policy.rank_tasks(context)

        assert scores[0].task_id == "task_overdue"
        assert scores[0].composite_score > 1000  # Overdue tasks get very high score


class TestCostAwarePolicy:
    """Tests for cost-aware scheduling policy."""

    def test_name(self):
        policy = CostAwarePolicy()
        assert policy.name == "cost_aware"

    def test_rank_tasks_with_budget(self):
        policy = CostAwarePolicy()

        # Create tasks with different estimated costs
        task1 = create_mock_task("task_cheap")
        task1.estimated_cost = Mock(total_cost_usd=0.01)

        task2 = create_mock_task("task_expensive")
        task2.estimated_cost = Mock(total_cost_usd=0.10)

        task3 = create_mock_task("task_medium")
        task3.estimated_cost = Mock(total_cost_usd=0.05)

        tasks = [task1, task2, task3]

        # With limited budget, cheaper tasks should rank higher
        context = create_test_context(ready_tasks=tasks)
        context.cost_budget_remaining = 0.05  # Only 5 cents left

        scores = policy.rank_tasks(context)

        assert len(scores) == 3
        # Cheapest task should rank highest when budget is tight
        assert scores[0].task_id == "task_cheap"
        assert scores[0].cost_score > scores[1].cost_score
        assert scores[0].cost_score > scores[2].cost_score


class TestFairPolicy:
    """Tests for fair scheduling policy."""

    def test_name(self):
        policy = FairPolicy()
        assert policy.name == "fair"

    def test_rank_tasks_fair_distribution(self):
        policy = FairPolicy()
        tasks = [
            create_mock_task("task1"),
            create_mock_task("task2"),
            create_mock_task("task3"),
        ]

        # Simulate that this workflow already has 3 running tasks
        running_tasks = {
            "running1": {"workflow_id": "test-workflow"},
            "running2": {"workflow_id": "test-workflow"},
            "running3": {"workflow_id": "test-workflow"},
        }

        context = create_test_context(ready_tasks=tasks, running_tasks=running_tasks)

        scores = policy.rank_tasks(context)

        # When workflow already has many running tasks, fairness score should be lower
        assert all(0 <= s.fairness_score <= 100 for s in scores)
        # With 3 running tasks, fairness should be 100 - (3 * 20) = 40
        assert scores[0].fairness_score == 40


class TestBalancedPolicy:
    """Tests for balanced scheduling policy."""

    def test_name(self):
        policy = BalancedPolicy()
        assert policy.name == "balanced"

    def test_weights_must_sum_to_one(self):
        # Valid weights
        BalancedPolicy(priority_weight=0.3, deadline_weight=0.3,
                      cost_weight=0.2, fairness_weight=0.1, agent_weight=0.1)

        # Invalid weights
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            BalancedPolicy(priority_weight=0.5, deadline_weight=0.5,
                          cost_weight=0.5, fairness_weight=0.5, agent_weight=0.5)

    def test_rank_tasks_balanced_scoring(self):
        policy = BalancedPolicy()

        # Create tasks with different characteristics
        task1 = create_mock_task("task_high_priority", 75)  # HIGH priority
        task1.estimated_cost = Mock(total_cost_usd=0.01)

        task2 = create_mock_task("task_low_priority", 25)   # LOW priority
        task2.estimated_cost = Mock(total_cost_usd=0.10)

        tasks = [task1, task2]

        now = time.time()
        deadline_info = {
            "task_high_priority": now + 300,
            "task_low_priority": now + 60,  # Sooner deadline
        }

        context = create_test_context(ready_tasks=tasks)
        context.deadline_info = deadline_info
        context.cost_budget_remaining = 0.05

        scores = policy.rank_tasks(context)

        assert len(scores) == 2
        # Each score should have all components populated
        for score in scores:
            assert score.priority_score > 0
            assert score.deadline_score >= 0
            assert score.cost_score >= 0  # Can be 0 if task cost exceeds budget
            assert score.fairness_score >= 0
            assert score.agent_availability_score >= 0
            assert score.composite_score > 0


class TestPolicyRegistry:
    """Tests for policy registry and factory function."""

    def test_get_policy_valid_names(self):
        # Test getting each policy type
        fifo = get_policy("fifo")
        assert isinstance(fifo, FIFOPolicy)

        priority = get_policy("priority")
        assert isinstance(priority, PriorityPolicy)

        deadline = get_policy("deadline")
        assert isinstance(deadline, DeadlinePolicy)

        cost_aware = get_policy("cost_aware")
        assert isinstance(cost_aware, CostAwarePolicy)

        fair = get_policy("fair")
        assert isinstance(fair, FairPolicy)

        balanced = get_policy("balanced")
        assert isinstance(balanced, BalancedPolicy)

    def test_get_policy_with_kwargs(self):
        # Test passing kwargs to policy constructor
        balanced = get_policy("balanced", priority_weight=0.4, deadline_weight=0.3,
                             cost_weight=0.1, fairness_weight=0.1, agent_weight=0.1)
        assert isinstance(balanced, BalancedPolicy)
        # Note: weights are private attributes, but we can verify the policy works
        scores = balanced.rank_tasks(create_test_context())
        assert scores == []  # No tasks in context

    def test_get_policy_invalid_name(self):
        with pytest.raises(ValueError, match="Unknown policy"):
            get_policy("invalid_policy_name")

    def test_scheduling_policy_enum(self):
        # Test that enum values match expected policy names
        assert SchedulingPolicy.FIFO == "fifo"
        assert SchedulingPolicy.PRIORITY == "priority"
        assert SchedulingPolicy.DEADLINE == "deadline"
        assert SchedulingPolicy.COST_AWARE == "cost_aware"
        assert SchedulingPolicy.FAIR == "fair"
        assert SchedulingPolicy.BALANCED == "balanced"
