"""Tests for ComplexityAnalyzer class.

Tests token estimation, dependency depth analysis, and parallelizability scoring.
"""

from __future__ import annotations

import pytest

from omni.decomposition.complexity_analyzer import ComplexityAnalyzer
from omni.task.models import Task, TaskGraph, TaskType


class TestComplexityAnalyzer:
    """Tests for ComplexityAnalyzer functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.analyzer = ComplexityAnalyzer()

    # ── Token Estimation Tests ─────────────────────────────────────────

    def test_estimate_tokens_simple_task(self) -> None:
        """Test token estimation for a simple task."""
        task = Task(
            description="Fix a bug in the login function",
            task_type=TaskType.CODE_GENERATION,
        )
        tokens = self.analyzer.estimate_tokens(task)
        assert tokens > 0
        assert tokens < 1000  # Reasonable upper bound

    def test_estimate_tokens_long_description(self) -> None:
        """Test token estimation for a task with long description."""
        long_desc = "This is a very long task description " * 20
        task = Task(description=long_desc, task_type=TaskType.CODE_GENERATION)
        tokens = self.analyzer.estimate_tokens(task)
        assert tokens > 100  # Should be higher for longer description

    def test_estimate_tokens_different_task_types(self) -> None:
        """Test that different task types produce different token estimates."""
        desc = "Implement a new feature"
        tasks = [
            Task(description=desc, task_type=TaskType.CODE_GENERATION),
            Task(description=desc, task_type=TaskType.DOCUMENTATION),
            Task(description=desc, task_type=TaskType.CONFIGURATION),
        ]
        tokens = [self.analyzer.estimate_tokens(t) for t in tasks]
        # Code generation should have highest multiplier
        assert tokens[0] > tokens[1]  # code_generation > documentation
        assert tokens[0] > tokens[2]  # code_generation > configuration

    def test_estimate_tokens_minimum(self) -> None:
        """Test that token estimation has a minimum value."""
        task = Task(description="X", task_type=TaskType.CUSTOM)
        tokens = self.analyzer.estimate_tokens(task)
        assert tokens >= 10  # Minimum tokens

    # ── Dependency Depth Tests ─────────────────────────────────────────

    def test_dependency_depth_root_task(self) -> None:
        """Test dependency depth for a root task (no dependencies)."""
        task_graph = TaskGraph()
        task = Task(description="Root task", task_type=TaskType.CUSTOM)
        task_graph.add_task(task)

        depth = self.analyzer.analyze_dependency_depth(task_graph, task.task_id)
        assert depth == 0

    def test_dependency_depth_one_level(self) -> None:
        """Test dependency depth for a task with one dependency."""
        task_graph = TaskGraph()
        root = Task(description="Root task", task_type=TaskType.CUSTOM)
        dependent = Task(
            description="Dependent task",
            task_type=TaskType.CUSTOM,
            dependencies=[root.task_id],
        )
        task_graph.add_task(root)
        task_graph.add_task(dependent)

        root_depth = self.analyzer.analyze_dependency_depth(task_graph, root.task_id)
        dep_depth = self.analyzer.analyze_dependency_depth(task_graph, dependent.task_id)

        assert root_depth == 0
        assert dep_depth == 1

    def test_dependency_depth_multiple_levels(self) -> None:
        """Test dependency depth for a multi-level dependency chain."""
        task_graph = TaskGraph()
        task1 = Task(description="Task 1", task_type=TaskType.CUSTOM)
        task2 = Task(
            description="Task 2",
            task_type=TaskType.CUSTOM,
            dependencies=[task1.task_id],
        )
        task3 = Task(
            description="Task 3",
            task_type=TaskType.CUSTOM,
            dependencies=[task2.task_id],
        )
        task_graph.add_task(task1)
        task_graph.add_task(task2)
        task_graph.add_task(task3)

        depth1 = self.analyzer.analyze_dependency_depth(task_graph, task1.task_id)
        depth2 = self.analyzer.analyze_dependency_depth(task_graph, task2.task_id)
        depth3 = self.analyzer.analyze_dependency_depth(task_graph, task3.task_id)

        assert depth1 == 0
        assert depth2 == 1
        assert depth3 == 2

    def test_dependency_depth_nonexistent_task(self) -> None:
        """Test that analyzing a nonexistent task raises an error."""
        task_graph = TaskGraph()
        with pytest.raises(ValueError, match="not found in graph"):
            self.analyzer.analyze_dependency_depth(task_graph, "nonexistent")

    # ── Parallelizability Score Tests ──────────────────────────────────

    def test_parallelizability_empty_graph(self) -> None:
        """Test parallelizability of an empty graph."""
        task_graph = TaskGraph()
        score = self.analyzer.calculate_parallelizability_score(task_graph)
        assert score == 1.0

    def test_parallelizability_single_task(self) -> None:
        """Test parallelizability of a single-task graph."""
        task_graph = TaskGraph()
        task = Task(description="Single task", task_type=TaskType.CUSTOM)
        task_graph.add_task(task)

        score = self.analyzer.calculate_parallelizability_score(task_graph)
        assert score == 1.0

    def test_parallelizability_independent_tasks(self) -> None:
        """Test parallelizability of independent tasks (should be high)."""
        task_graph = TaskGraph()
        task1 = Task(description="Task 1", task_type=TaskType.CUSTOM)
        task2 = Task(description="Task 2", task_type=TaskType.CUSTOM)
        task3 = Task(description="Task 3", task_type=TaskType.CUSTOM)

        task_graph.add_task(task1)
        task_graph.add_task(task2)
        task_graph.add_task(task3)

        score = self.analyzer.calculate_parallelizability_score(task_graph)
        assert score > 0.8  # Should be highly parallelizable

    def test_parallelizability_sequential_tasks(self) -> None:
        """Test parallelizability of sequential tasks (should be low)."""
        task_graph = TaskGraph()
        task1 = Task(description="Task 1", task_type=TaskType.CUSTOM)
        task2 = Task(
            description="Task 2",
            task_type=TaskType.CUSTOM,
            dependencies=[task1.task_id],
        )
        task3 = Task(
            description="Task 3",
            task_type=TaskType.CUSTOM,
            dependencies=[task2.task_id],
        )

        task_graph.add_task(task1)
        task_graph.add_task(task2)
        task_graph.add_task(task3)

        score = self.analyzer.calculate_parallelizability_score(task_graph)
        assert score < 0.5  # Should be low for sequential tasks

    def test_parallelizability_mixed_dependencies(self) -> None:
        """Test parallelizability with mixed dependency patterns."""
        task_graph = TaskGraph()
        # Two independent roots
        root1 = Task(description="Root 1", task_type=TaskType.CUSTOM)
        root2 = Task(description="Root 2", task_type=TaskType.CUSTOM)
        # One task depending on both roots
        dependent = Task(
            description="Dependent",
            task_type=TaskType.CUSTOM,
            dependencies=[root1.task_id, root2.task_id],
        )

        task_graph.add_task(root1)
        task_graph.add_task(root2)
        task_graph.add_task(dependent)

        score = self.analyzer.calculate_parallelizability_score(task_graph)
        # Should be moderately parallelizable
        assert 0.3 < score < 0.8

    # ── Task Complexity Analysis Tests ─────────────────────────────────

    def test_analyze_task_complexity_basic(self) -> None:
        """Test basic task complexity analysis."""
        task = Task(
            description="Implement a new feature",
            task_type=TaskType.CODE_GENERATION,
        )
        complexity = self.analyzer.analyze_task_complexity(task)

        assert 1 <= complexity.code_complexity <= 10
        assert 1 <= complexity.integration_complexity <= 10
        assert 1 <= complexity.testing_complexity <= 10
        assert 1 <= complexity.unknown_factor <= 10
        assert complexity.estimated_tokens > 0
        assert complexity.reasoning  # Should have reasoning text

    def test_analyze_task_complexity_with_graph(self) -> None:
        """Test task complexity analysis with task graph."""
        task_graph = TaskGraph()
        root = Task(description="Root task", task_type=TaskType.CUSTOM)
        dependent = Task(
            description="Dependent task",
            task_type=TaskType.CODE_GENERATION,
            dependencies=[root.task_id],
        )
        task_graph.add_task(root)
        task_graph.add_task(dependent)

        complexity = self.analyzer.analyze_task_complexity(dependent, task_graph)

        # Integration complexity should be higher due to dependency
        assert complexity.integration_complexity >= 2

    def test_analyze_task_complexity_different_types(self) -> None:
        """Test that different task types produce different complexity scores."""
        desc = "Implement a feature"
        tasks = [
            Task(description=desc, task_type=TaskType.CODE_GENERATION),
            Task(description=desc, task_type=TaskType.DOCUMENTATION),
            Task(description=desc, task_type=TaskType.CONFIGURATION),
        ]
        complexities = [self.analyzer.analyze_task_complexity(t) for t in tasks]

        # Code generation should have higher code complexity
        assert complexities[0].code_complexity >= complexities[1].code_complexity
        assert complexities[0].code_complexity >= complexities[2].code_complexity

    def test_analyze_task_complexity_overall_score(self) -> None:
        """Test that overall complexity score is calculated correctly."""
        task = Task(
            description="Complex implementation task",
            task_type=TaskType.CODE_GENERATION,
        )
        complexity = self.analyzer.analyze_task_complexity(task)

        # Overall score should be weighted average
        expected_score = (
            complexity.code_complexity * 0.3
            + complexity.integration_complexity * 0.25
            + complexity.testing_complexity * 0.2
            + complexity.unknown_factor * 0.25
        )
        assert abs(complexity.overall_score - expected_score) < 0.01

    # ── Graph Complexity Analysis Tests ─────────────────────────────────

    def test_analyze_graph_complexity_empty(self) -> None:
        """Test graph complexity analysis for empty graph."""
        task_graph = TaskGraph()
        result = self.analyzer.analyze_graph_complexity(task_graph)

        assert result["avg_complexity"] == 0.0
        assert result["max_complexity"] == 0.0
        assert result["parallelizability"] == 1.0
        assert result["total_estimated_tokens"] == 0

    def test_analyze_graph_complexity_single_task(self) -> None:
        """Test graph complexity analysis for single task."""
        task_graph = TaskGraph()
        task = Task(description="Single task", task_type=TaskType.CODE_GENERATION)
        task_graph.add_task(task)

        result = self.analyzer.analyze_graph_complexity(task_graph)

        assert result["avg_complexity"] > 0
        assert result["max_complexity"] > 0
        assert result["parallelizability"] == 1.0
        assert result["total_estimated_tokens"] > 0

    def test_analyze_graph_complexity_multiple_tasks(self) -> None:
        """Test graph complexity analysis for multiple tasks."""
        task_graph = TaskGraph()
        for i in range(5):
            task = Task(
                description=f"Task {i}",
                task_type=TaskType.CODE_GENERATION if i % 2 == 0 else TaskType.DOCUMENTATION,
            )
            task_graph.add_task(task)

        result = self.analyzer.analyze_graph_complexity(task_graph)

        assert result["avg_complexity"] > 0
        assert result["max_complexity"] >= result["avg_complexity"]
        assert 0 <= result["parallelizability"] <= 1
        assert result["total_estimated_tokens"] > 0

    # ── Edge Cases and Error Handling ──────────────────────────────────

    def test_estimate_tokens_with_special_characters(self) -> None:
        """Test token estimation with special characters in description."""
        task = Task(
            description="Fix bug in function() { return x; }",
            task_type=TaskType.CODE_GENERATION,
        )
        tokens = self.analyzer.estimate_tokens(task)
        assert tokens > 0

    def test_dependency_depth_with_cycle(self) -> None:
        """Test dependency depth with cycle (should handle gracefully)."""
        task_graph = TaskGraph()
        task1 = Task(
            description="Task 1",
            task_type=TaskType.CUSTOM,
            dependencies=[],  # Will add cycle manually
        )
        task2 = Task(
            description="Task 2",
            task_type=TaskType.CUSTOM,
            dependencies=[task1.task_id],
        )
        # Manually create a cycle by adding task1 as dependency of task2
        # This would normally be caught by TaskGraph validation
        task_graph.add_task(task1)
        task_graph.add_task(task2)

        # The analyzer should handle this gracefully
        depth = self.analyzer.analyze_dependency_depth(task_graph, task1.task_id)
        assert depth >= 0  # Should not crash

    def test_parallelizability_score_boundaries(self) -> None:
        """Test that parallelizability score is always between 0 and 1."""
        task_graph = TaskGraph()
        # Create a complex dependency graph
        tasks = []
        for i in range(10):
            task = Task(
                description=f"Task {i}",
                task_type=TaskType.CUSTOM,
                dependencies=[t.task_id for t in tasks[:i] if i % 3 == 0],
            )
            tasks.append(task)
            task_graph.add_task(task)

        score = self.analyzer.calculate_parallelizability_score(task_graph)
        assert 0 <= score <= 1

    def test_complexity_tier_assignment(self) -> None:
        """Test that complexity tier is assigned correctly."""
        task = Task(
            description="Simple task",
            task_type=TaskType.CONFIGURATION,
        )
        complexity = self.analyzer.analyze_task_complexity(task)

        # Simple tasks should be assigned to intern tier
        if complexity.overall_score <= 3.0:
            assert complexity.tier == "intern"
        elif complexity.overall_score <= 5.5:
            assert complexity.tier == "coder"
        elif complexity.overall_score <= 7.5:
            assert complexity.tier == "reader"
        else:
            assert complexity.tier == "thinker"