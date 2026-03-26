"""
Comprehensive tests for task decomposition models.

Covers Task, TaskGraph, TaskStatus, TaskResult, ComplexityEstimate
and all edge cases for Phase 2.2 foundation.
"""

from __future__ import annotations

import pytest

from omni.task.models import (
    ComplexityEstimate,
    CycleError,
    Task,
    TaskGraph,
    TaskResult,
    TaskStatus,
    TaskType,
)

# ── TaskStatus ──────────────────────────────────────────────────────


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_values(self) -> None:
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"

    def test_str(self) -> None:
        assert str(TaskStatus.PENDING) == "pending"
        assert str(TaskStatus.COMPLETED) == "completed"

    def test_from_string(self) -> None:
        assert TaskStatus("pending") == TaskStatus.PENDING
        assert TaskStatus("failed") == TaskStatus.FAILED

    def test_invalid_value(self) -> None:
        with pytest.raises(ValueError):
            TaskStatus("invalid")


# ── TaskType ────────────────────────────────────────────────────────


class TestTaskType:
    """Tests for TaskType enum."""

    def test_all_types_exist(self) -> None:
        expected = {
            "code_generation", "code_review", "testing",
            "refactoring", "documentation", "analysis",
            "configuration", "deployment", "custom",
        }
        actual = {t.value for t in TaskType}
        assert actual == expected

    def test_str(self) -> None:
        assert str(TaskType.TESTING) == "testing"
        assert str(TaskType.CUSTOM) == "custom"


# ── ComplexityEstimate ──────────────────────────────────────────────


class TestComplexityEstimate:
    """Tests for ComplexityEstimate dataclass."""

    def test_defaults(self) -> None:
        ce = ComplexityEstimate()
        assert ce.code_complexity == 1
        assert ce.integration_complexity == 1
        assert ce.testing_complexity == 1
        assert ce.unknown_factor == 1
        assert ce.estimated_tokens == 0
        assert ce.reasoning == ""

    def test_custom_values(self) -> None:
        ce = ComplexityEstimate(
            code_complexity=5,
            integration_complexity=3,
            testing_complexity=4,
            unknown_factor=2,
            estimated_tokens=5000,
            reasoning="Moderate complexity",
        )
        assert ce.code_complexity == 5
        assert ce.estimated_tokens == 5000

    def test_validation_low(self) -> None:
        with pytest.raises(ValueError, match="code_complexity"):
            ComplexityEstimate(code_complexity=0)

    def test_validation_high(self) -> None:
        with pytest.raises(ValueError, match="integration_complexity"):
            ComplexityEstimate(integration_complexity=11)

    def test_validation_negative_tokens(self) -> None:
        with pytest.raises(ValueError, match="estimated_tokens"):
            ComplexityEstimate(estimated_tokens=-1)

    def test_overall_score(self) -> None:
        ce = ComplexityEstimate(
            code_complexity=10,
            integration_complexity=10,
            testing_complexity=10,
            unknown_factor=10,
        )
        assert ce.overall_score == 10.0

    def test_overall_score_min(self) -> None:
        ce = ComplexityEstimate(
            code_complexity=1,
            integration_complexity=1,
            testing_complexity=1,
            unknown_factor=1,
        )
        assert ce.overall_score == 1.0

    def test_overall_score_weighted(self) -> None:
        ce = ComplexityEstimate(
            code_complexity=8,
            integration_complexity=4,
            testing_complexity=4,
            unknown_factor=6,
        )
        # 8*0.3 + 4*0.25 + 4*0.2 + 6*0.25 = 2.4 + 1.0 + 0.8 + 1.5 = 5.7
        assert ce.overall_score == pytest.approx(5.7)

    def test_tier_intern(self) -> None:
        ce = ComplexityEstimate(
            code_complexity=1, integration_complexity=1,
            testing_complexity=1, unknown_factor=1,
        )
        assert ce.tier == "intern"

    def test_tier_coder(self) -> None:
        ce = ComplexityEstimate(
            code_complexity=5, integration_complexity=5,
            testing_complexity=5, unknown_factor=5,
        )
        assert ce.tier == "coder"

    def test_tier_reader(self) -> None:
        ce = ComplexityEstimate(
            code_complexity=7, integration_complexity=7,
            testing_complexity=7, unknown_factor=7,
        )
        assert ce.tier == "reader"

    def test_tier_thinker(self) -> None:
        ce = ComplexityEstimate(
            code_complexity=9, integration_complexity=9,
            testing_complexity=9, unknown_factor=9,
        )
        assert ce.tier == "thinker"


# ── TaskResult ──────────────────────────────────────────────────────


class TestTaskResult:
    """Tests for TaskResult dataclass."""

    def test_basic_result(self) -> None:
        r = TaskResult(
            task_id="abc123",
            status=TaskStatus.COMPLETED,
            outputs={"file": "main.py"},
        )
        assert r.success is True
        assert r.has_errors is False
        assert r.tokens_used == 0

    def test_failed_result(self) -> None:
        r = TaskResult(
            task_id="abc123",
            status=TaskStatus.FAILED,
            errors=["Syntax error on line 42"],
        )
        assert r.success is False
        assert r.has_errors is True
        assert len(r.errors) == 1

    def test_rejects_pending(self) -> None:
        with pytest.raises(ValueError, match="PENDING"):
            TaskResult(task_id="x", status=TaskStatus.PENDING)

    def test_rejects_running(self) -> None:
        with pytest.raises(ValueError, match="RUNNING"):
            TaskResult(task_id="x", status=TaskStatus.RUNNING)

    def test_rejects_negative_tokens(self) -> None:
        with pytest.raises(ValueError, match="tokens_used"):
            TaskResult(
                task_id="x",
                status=TaskStatus.COMPLETED,
                tokens_used=-1,
            )

    def test_rejects_negative_cost(self) -> None:
        with pytest.raises(ValueError, match="cost"):
            TaskResult(
                task_id="x",
                status=TaskStatus.COMPLETED,
                cost=-0.01,
            )

    def test_metadata_and_cost(self) -> None:
        r = TaskResult(
            task_id="x",
            status=TaskStatus.COMPLETED,
            metadata={"model": "gpt-4", "duration_ms": 1234},
            tokens_used=500,
            cost=0.02,
        )
        assert r.metadata["model"] == "gpt-4"
        assert r.tokens_used == 500
        assert r.cost == pytest.approx(0.02)


# ── Task ────────────────────────────────────────────────────────────


class TestTask:
    """Tests for Task dataclass."""

    def test_minimal(self) -> None:
        t = Task(description="Do something")
        assert t.status == TaskStatus.PENDING
        assert t.task_type == TaskType.CUSTOM
        assert len(t.task_id) == 12
        assert t.dependencies == []
        assert t.priority == 0

    def test_explicit_id(self) -> None:
        t = Task(description="Test", task_id="my-task-1")
        assert t.task_id == "my-task-1"

    def test_empty_description_rejected(self) -> None:
        with pytest.raises(ValueError, match="description"):
            Task(description="")
        with pytest.raises(ValueError, match="description"):
            Task(description="   ")

    def test_negative_priority_rejected(self) -> None:
        with pytest.raises(ValueError, match="priority"):
            Task(description="Test", priority=-1)

    def test_is_terminal(self) -> None:
        t = Task(description="Test")
        assert t.is_terminal is False
        t.mark_running()
        assert t.is_terminal is False
        t.mark_completed()
        assert t.is_terminal is True

    def test_is_terminal_failed(self) -> None:
        t = Task(description="Test")
        t.mark_running()
        t.mark_failed()
        assert t.is_terminal is True

    def test_state_transitions(self) -> None:
        t = Task(description="Test")
        assert t.status == TaskStatus.PENDING

        t.mark_running()
        assert t.status == TaskStatus.RUNNING

        t.mark_completed()
        assert t.status == TaskStatus.COMPLETED

    def test_mark_completed_from_non_running(self) -> None:
        t = Task(description="Test")
        with pytest.raises(ValueError, match="must be RUNNING"):
            t.mark_completed()

    def test_mark_failed_from_non_running(self) -> None:
        t = Task(description="Test")
        with pytest.raises(ValueError, match="must be RUNNING"):
            t.mark_failed()

    def test_mark_running_twice(self) -> None:
        t = Task(description="Test")
        t.mark_running()
        with pytest.raises(ValueError, match="must be PENDING"):
            t.mark_running()

    def test_can_retry(self) -> None:
        t = Task(description="Test")
        assert t.can_retry is False

        t.mark_running()
        t.mark_failed()
        assert t.can_retry is True

    def test_retry(self) -> None:
        t = Task(description="Test")
        t.mark_running()
        t.mark_failed()

        t.retry()
        assert t.status == TaskStatus.PENDING
        assert t.retry_count == 1

    def test_retry_exhausted(self) -> None:
        t = Task(description="Test", max_retries=1)
        t.mark_running()
        t.mark_failed()
        t.retry()
        t.mark_running()
        t.mark_failed()

        with pytest.raises(ValueError, match="Cannot retry"):
            t.retry()

    def test_retry_from_non_failed(self) -> None:
        t = Task(description="Test")
        with pytest.raises(ValueError, match="Cannot retry"):
            t.retry()

    def test_retry_respects_max(self) -> None:
        t = Task(description="Test", max_retries=0)
        t.mark_running()
        t.mark_failed()
        assert t.can_retry is False

    def test_effective_complexity_explicit(self) -> None:
        ce = ComplexityEstimate(code_complexity=7, reasoning="Hard")
        t = Task(description="Test", complexity=ce)
        assert t.effective_complexity.code_complexity == 7

    def test_effective_complexity_default(self) -> None:
        t = Task(description="Test")
        ec = t.effective_complexity
        assert ec.code_complexity == 1
        assert "defaults" in ec.reasoning

    def test_dependencies(self) -> None:
        t = Task(description="Test", dependencies=["task-a", "task-b"])
        assert t.dependencies == ["task-a", "task-b"]

    def test_tags(self) -> None:
        t = Task(description="Test", tags=["urgent", "backend"])
        assert "urgent" in t.tags

    def test_context(self) -> None:
        t = Task(
            description="Test",
            context={"target_file": "main.py", "language": "python"},
        )
        assert t.context["language"] == "python"


# ── TaskGraph ───────────────────────────────────────────────────────


class TestTaskGraph:
    """Tests for TaskGraph dataclass."""

    def _make_simple_graph(self) -> TaskGraph:
        """Create a simple 3-task graph: A -> B -> C."""
        g = TaskGraph(name="test")
        a = Task(description="Task A", task_id="a")
        b = Task(description="Task B", task_id="b", dependencies=["a"])
        c = Task(description="Task C", task_id="c", dependencies=["b"])
        g.add_task(a)
        g.add_task(b)
        g.add_task(c)
        return g

    def test_empty_graph(self) -> None:
        g = TaskGraph()
        assert g.size == 0
        assert g.edge_count == 0
        assert g.is_valid is True

    def test_add_task(self) -> None:
        g = TaskGraph()
        t = Task(description="Test", task_id="t1")
        g.add_task(t)
        assert g.size == 1
        assert g.get_task("t1") is t

    def test_add_duplicate_task(self) -> None:
        g = TaskGraph()
        t = Task(description="Test", task_id="t1")
        g.add_task(t)
        with pytest.raises(ValueError, match="already exists"):
            g.add_task(Task(description="Dup", task_id="t1"))

    def test_add_task_with_missing_dependency(self) -> None:
        g = TaskGraph()
        t = Task(description="Test", task_id="t1", dependencies=["missing"])
        with pytest.raises(ValueError, match="Dependency.*not found"):
            g.add_task(t)

    def test_remove_task(self) -> None:
        g = TaskGraph()
        t = Task(description="Test", task_id="t1")
        g.add_task(t)
        removed = g.remove_task("t1")
        assert removed is t
        assert g.size == 0

    def test_remove_task_with_dependents(self) -> None:
        g = self._make_simple_graph()
        with pytest.raises(ValueError, match="Cannot remove"):
            g.remove_task("a")

    def test_remove_nonexistent(self) -> None:
        g = TaskGraph()
        with pytest.raises(KeyError):
            g.remove_task("nope")

    def test_get_task_missing(self) -> None:
        g = TaskGraph()
        with pytest.raises(KeyError):
            g.get_task("nope")

    def test_get_dependencies(self) -> None:
        g = self._make_simple_graph()
        deps = g.get_dependencies("b")
        assert len(deps) == 1
        assert deps[0].task_id == "a"

    def test_get_dependencies_no_deps(self) -> None:
        g = self._make_simple_graph()
        deps = g.get_dependencies("a")
        assert deps == []

    def test_get_dependents(self) -> None:
        g = self._make_simple_graph()
        dependents = g.get_dependents("a")
        assert len(dependents) == 1
        assert dependents[0].task_id == "b"

    def test_get_dependents_leaf(self) -> None:
        g = self._make_simple_graph()
        dependents = g.get_dependents("c")
        assert dependents == []

    def test_topological_order(self) -> None:
        g = self._make_simple_graph()
        order = g.topological_order()
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_topological_order_cycle(self) -> None:
        g = TaskGraph(name="cycle")
        g._graph.add_node("x")
        g._graph.add_node("y")
        g.tasks["x"] = Task(description="X", task_id="x")
        g.tasks["y"] = Task(description="Y", task_id="y")
        # Manually create a cycle (bypass add_task validation)
        g._graph.add_edge("x", "y")
        g._graph.add_edge("y", "x")
        with pytest.raises(CycleError):
            g.topological_order()

    def test_validate_no_issues(self) -> None:
        g = self._make_simple_graph()
        assert g.validate() == []
        assert g.is_valid is True

    def test_validate_self_dependency(self) -> None:
        g = TaskGraph()
        t = Task(description="Self", task_id="self", dependencies=["self"])
        # Bypass add_task validation for dependency check
        g.tasks["self"] = t
        g._graph.add_node("self")
        g._graph.add_edge("self", "self")
        issues = g.validate()
        assert any("depends on itself" in i for i in issues)
        assert g.is_valid is False

    def test_roots(self) -> None:
        g = self._make_simple_graph()
        roots = g.roots
        assert len(roots) == 1
        assert roots[0].task_id == "a"

    def test_leaves(self) -> None:
        g = self._make_simple_graph()
        leaves = g.leaves
        assert len(leaves) == 1
        assert leaves[0].task_id == "c"

    def test_get_ready_tasks_initial(self) -> None:
        g = self._make_simple_graph()
        ready = g.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == "a"

    def test_get_ready_tasks_after_completion(self) -> None:
        g = self._make_simple_graph()
        g.get_task("a").mark_running()
        g.get_task("a").mark_completed()

        ready = g.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == "b"

    def test_get_ready_tasks_priority_order(self) -> None:
        g = TaskGraph(name="priority")
        low = Task(description="Low", task_id="low", priority=1)
        high = Task(description="High", task_id="high", priority=10)
        g.add_task(low)
        g.add_task(high)

        ready = g.get_ready_tasks()
        assert ready[0].task_id == "high"
        assert ready[1].task_id == "low"

    def test_completed_fraction(self) -> None:
        g = self._make_simple_graph()
        assert g.completed_fraction == 0.0

        g.get_task("a").mark_running()
        g.get_task("a").mark_completed()
        assert g.completed_fraction == pytest.approx(1 / 3)

    def test_completed_fraction_empty(self) -> None:
        g = TaskGraph()
        assert g.completed_fraction == 0.0

    def test_is_complete(self) -> None:
        g = self._make_simple_graph()
        assert g.is_complete is False

        for tid in ["a", "b", "c"]:
            g.get_task(tid).mark_running()
            g.get_task(tid).mark_completed()

        assert g.is_complete is True

    def test_has_failures(self) -> None:
        g = self._make_simple_graph()
        assert g.has_failures is False

        g.get_task("a").mark_running()
        g.get_task("a").mark_failed()
        assert g.has_failures is True

    def test_failed_tasks(self) -> None:
        g = self._make_simple_graph()
        g.get_task("a").mark_running()
        g.get_task("a").mark_failed()
        failed = g.failed_tasks
        assert len(failed) == 1
        assert failed[0].task_id == "a"

    def test_total_estimated_tokens(self) -> None:
        g = TaskGraph(name="tokens")
        t1 = Task(
            description="A", task_id="a",
            complexity=ComplexityEstimate(estimated_tokens=1000),
        )
        t2 = Task(
            description="B", task_id="b",
            complexity=ComplexityEstimate(estimated_tokens=2000),
        )
        g.add_task(t1)
        g.add_task(t2)
        assert g.total_estimated_tokens == 3000

    def test_summary(self) -> None:
        g = self._make_simple_graph()
        s = g.summary()
        assert s["name"] == "test"
        assert s["total_tasks"] == 3
        assert s["edges"] == 2
        assert s["status_counts"]["pending"] == 3
        assert s["is_complete"] is False
        assert s["has_failures"] is False

    def test_remove_cleans_dependencies(self) -> None:
        g = TaskGraph(name="clean")
        a = Task(description="A", task_id="a")
        b = Task(description="B", task_id="b", dependencies=["a"])
        g.add_task(a)
        g.add_task(b)

        # Complete b so it has no dependents
        b.mark_running()
        b.mark_completed()
        # Remove a is now allowed since b is completed (b still depends on a)
        # Actually we need to check: b depends on a, so a can't be removed
        with pytest.raises(ValueError, match="Cannot remove"):
            g.remove_task("a")

    def test_diamond_dependency(self) -> None:
        """Test diamond shape: A -> B, A -> C, B -> D, C -> D."""
        g = TaskGraph(name="diamond")
        a = Task(description="A", task_id="a")
        b = Task(description="B", task_id="b", dependencies=["a"])
        c = Task(description="C", task_id="c", dependencies=["a"])
        d = Task(description="D", task_id="d", dependencies=["b", "c"])
        g.add_task(a)
        g.add_task(b)
        g.add_task(c)
        g.add_task(d)

        assert g.is_valid is True
        assert g.size == 4
        assert g.edge_count == 4
        order = g.topological_order()
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_independent_tasks(self) -> None:
        """Multiple tasks with no dependencies run in parallel."""
        g = TaskGraph(name="parallel")
        for i in range(5):
            g.add_task(Task(description=f"Task {i}", task_id=f"t{i}"))

        ready = g.get_ready_tasks()
        assert len(ready) == 5

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name"):
            TaskGraph(name="")
        with pytest.raises(ValueError, match="name"):
            TaskGraph(name="   ")


# ── Integration ─────────────────────────────────────────────────────


class TestIntegration:
    """Integration tests for combined model usage."""

    def test_full_lifecycle(self) -> None:
        """Simulate a complete task lifecycle from creation to completion."""
        g = TaskGraph(name="deploy")

        # Define tasks
        lint = Task(
            description="Run linter",
            task_id="lint",
            task_type=TaskType.TESTING,
            complexity=ComplexityEstimate(
                code_complexity=2, estimated_tokens=500,
                reasoning="Simple lint check",
            ),
        )
        test = Task(
            description="Run test suite",
            task_id="test",
            task_type=TaskType.TESTING,
            dependencies=["lint"],
            complexity=ComplexityEstimate(
                code_complexity=4, testing_complexity=5,
                estimated_tokens=2000,
                reasoning="Full test suite",
            ),
        )
        deploy = Task(
            description="Deploy to production",
            task_id="deploy",
            task_type=TaskType.DEPLOYMENT,
            dependencies=["test"],
            priority=10,
            complexity=ComplexityEstimate(
                integration_complexity=8, unknown_factor=5,
                estimated_tokens=1000,
                reasoning="Production deployment",
            ),
        )

        g.add_task(lint)
        g.add_task(test)
        g.add_task(deploy)

        # Verify structure
        assert g.is_valid
        assert g.total_estimated_tokens == 3500

        # Execute in order
        ready = g.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == "lint"

        lint.mark_running()
        lint.mark_completed()
        result = TaskResult(
            task_id="lint", status=TaskStatus.COMPLETED,
            outputs={"issues": 0}, tokens_used=500, cost=0.001,
        )
        assert result.success

        ready = g.get_ready_tasks()
        assert ready[0].task_id == "test"

        test.mark_running()
        test.mark_completed()

        ready = g.get_ready_tasks()
        assert ready[0].task_id == "deploy"

        deploy.mark_running()
        deploy.mark_completed()

        assert g.is_complete
        assert g.completed_fraction == 1.0

    def test_retry_flow(self) -> None:
        """Test a task failing and being retried."""
        t = Task(description="Flaky test", task_id="flaky", max_retries=2)

        # First attempt
        t.mark_running()
        t.mark_failed()
        assert t.can_retry

        # Retry
        t.retry()
        assert t.status == TaskStatus.PENDING
        assert t.retry_count == 1

        # Second attempt succeeds
        t.mark_running()
        t.mark_completed()
        assert t.status == TaskStatus.COMPLETED
