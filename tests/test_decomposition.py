"""
Comprehensive tests for the Task Decomposition Engine.

Covers Subtask, DecompositionResult, decomposition strategies,
and the main TaskDecompositionEngine facade.
"""

from __future__ import annotations

import pytest

from omni.decomposition.engine import EngineConfig, TaskDecompositionEngine
from omni.decomposition.models import DecompositionResult, Subtask, SubtaskType
from omni.decomposition.strategies import (
    DecompositionContext,
    DependencyAnalyzer,
    ParallelDecomposer,
    RecursiveDecomposer,
)
from omni.task.models import ComplexityEstimate, Task, TaskGraph, TaskType

# ── SubtaskType ─────────────────────────────────────────────────────


class TestSubtaskType:
    """Tests for SubtaskType enum."""

    def test_values(self) -> None:
        assert SubtaskType.PREPARATION == "preparation"
        assert SubtaskType.ANALYSIS == "analysis"
        assert SubtaskType.IMPLEMENTATION == "implementation"
        assert SubtaskType.VALIDATION == "validation"
        assert SubtaskType.INTEGRATION == "integration"
        assert SubtaskType.CLEANUP == "cleanup"
        assert SubtaskType.UNKNOWN == "unknown"

    def test_str(self) -> None:
        assert str(SubtaskType.PREPARATION) == "preparation"
        assert str(SubtaskType.IMPLEMENTATION) == "implementation"

    def test_from_string(self) -> None:
        assert SubtaskType("analysis") == SubtaskType.ANALYSIS
        assert SubtaskType("validation") == SubtaskType.VALIDATION


# ── Subtask ─────────────────────────────────────────────────────────


class TestSubtask:
    """Tests for Subtask dataclass."""

    def test_minimal(self) -> None:
        s = Subtask(description="Test subtask")
        assert s.subtask_type == SubtaskType.UNKNOWN
        assert s.depth == 0
        assert s.parent_id is None
        assert s.effort_score == 1.0
        assert s.required_capabilities == []

    def test_full_initialization(self) -> None:
        s = Subtask(
            description="Full subtask",
            task_type=TaskType.CODE_GENERATION,
            subtask_type=SubtaskType.IMPLEMENTATION,
            depth=2,
            parent_id="parent-123",
            effort_score=2.5,
            required_capabilities=["coding", "testing"],
            priority=5,
            tags=["urgent"],
        )
        assert s.subtask_type == SubtaskType.IMPLEMENTATION
        assert s.depth == 2
        assert s.parent_id == "parent-123"
        assert s.effort_score == 2.5
        assert "coding" in s.required_capabilities
        assert s.priority == 5

    def test_negative_depth_rejected(self) -> None:
        with pytest.raises(ValueError, match="depth must be non-negative"):
            Subtask(description="Test", depth=-1)

    def test_negative_effort_rejected(self) -> None:
        with pytest.raises(ValueError, match="effort_score must be non-negative"):
            Subtask(description="Test", effort_score=-0.5)

    def test_from_task(self) -> None:
        task = Task(
            description="Original task",
            task_type=TaskType.TESTING,
            priority=3,
            tags=["important"],
            context={"key": "value"},
        )
        subtask = Subtask.from_task(
            task,
            subtask_type=SubtaskType.VALIDATION,
            depth=1,
            parent_id="parent-456",
            effort_score=1.5,
            required_capabilities=["testing"],
        )
        assert subtask.description == "Original task"
        assert subtask.task_type == TaskType.TESTING
        assert subtask.subtask_type == SubtaskType.VALIDATION
        assert subtask.depth == 1
        assert subtask.parent_id == "parent-456"
        assert subtask.effort_score == 1.5
        assert "testing" in subtask.required_capabilities
        assert "important" in subtask.tags
        assert subtask.context["key"] == "value"

    def test_from_task_preserves_dependencies(self) -> None:
        task = Task(description="Test", dependencies=["dep1", "dep2"])
        subtask = Subtask.from_task(task)
        assert subtask.dependencies == ["dep1", "dep2"]
        # Ensure it's a copy, not reference
        subtask.dependencies.append("dep3")
        assert "dep3" not in task.dependencies


# ── DecompositionResult ─────────────────────────────────────────────


class TestDecompositionResult:
    """Tests for DecompositionResult dataclass."""

    def _make_result(
        self,
        task: Task | None = None,
        subtasks: list[Subtask] | None = None,
    ) -> DecompositionResult:
        """Create a DecompositionResult for testing."""
        if task is None:
            task = Task(description="Test task", task_id="test-123")
        if subtasks is None:
            subtasks = [
                Subtask(description="Subtask 1", task_id="st-1", parent_id=task.task_id),
                Subtask(description="Subtask 2", task_id="st-2", parent_id=task.task_id),
            ]

        graph = TaskGraph(name="test-graph")
        for st in subtasks:
            graph.add_task(st)

        return DecompositionResult(
            original_task=task,
            task_graph=graph,
            strategy_used="test",
            confidence=0.8,
            reasoning="Test decomposition",
        )

    def test_basic_result(self) -> None:
        result = self._make_result()
        assert result.total_subtasks == 2
        assert result.strategy_used == "test"
        assert result.confidence == 0.8

    def test_invalid_confidence_rejected(self) -> None:
        task = Task(description="Test", task_id="t1")
        graph = TaskGraph(name="g1")
        graph.add_task(Subtask(description="S1", task_id="s1"))

        with pytest.raises(ValueError, match="confidence"):
            DecompositionResult(
                original_task=task,
                task_graph=graph,
                confidence=1.5,
            )

    def test_is_atomic(self) -> None:
        result = self._make_result()
        # With subtasks having UNKNOWN type, should not be atomic
        assert result.is_atomic is False

        # Make subtasks have specific types
        for task in result.task_graph.tasks.values():
            if isinstance(task, Subtask):
                task.subtask_type = SubtaskType.IMPLEMENTATION
        assert result.is_atomic is True

    def test_subtasks_by_type(self) -> None:
        subtasks = [
            Subtask(description="Prep", task_id="s1", subtask_type=SubtaskType.PREPARATION),
            Subtask(description="Impl 1", task_id="s2", subtask_type=SubtaskType.IMPLEMENTATION),
            Subtask(description="Impl 2", task_id="s3", subtask_type=SubtaskType.IMPLEMENTATION),
            Subtask(description="Valid", task_id="s4", subtask_type=SubtaskType.VALIDATION),
        ]
        result = self._make_result(subtasks=subtasks)
        by_type = result.subtasks_by_type
        assert len(by_type[SubtaskType.PREPARATION]) == 1
        assert len(by_type[SubtaskType.IMPLEMENTATION]) == 2
        assert len(by_type[SubtaskType.VALIDATION]) == 1

    def test_leaf_subtasks(self) -> None:
        graph = TaskGraph(name="leaves")
        a = Subtask(description="A", task_id="a")
        b = Subtask(description="B", task_id="b", dependencies=["a"])
        graph.add_task(a)
        graph.add_task(b)

        task = Task(description="Root", task_id="root")
        result = DecompositionResult(
            original_task=task,
            task_graph=graph,
            confidence=0.9,
        )

        leaves = result.leaf_subtasks
        assert len(leaves) == 1
        assert leaves[0].task_id == "b"

    def test_root_subtasks(self) -> None:
        graph = TaskGraph(name="roots")
        a = Subtask(description="A", task_id="a")
        b = Subtask(description="B", task_id="b", dependencies=["a"])
        graph.add_task(a)
        graph.add_task(b)

        task = Task(description="Root", task_id="root")
        result = DecompositionResult(
            original_task=task,
            task_graph=graph,
            confidence=0.9,
        )

        roots = result.root_subtasks
        assert len(roots) == 1
        assert roots[0].task_id == "a"

    def test_summary(self) -> None:
        result = self._make_result()
        summary = result.summary()
        assert summary["original_task_id"] == "test-123"
        assert summary["strategy"] == "test"
        assert summary["total_subtasks"] == 2
        assert summary["confidence"] == 0.8


# ── DecompositionContext ────────────────────────────────────────────


class TestDecompositionContext:
    """Tests for DecompositionContext dataclass."""

    def test_defaults(self) -> None:
        ctx = DecompositionContext()
        assert ctx.max_depth == 5
        assert ctx.max_subtasks == 20
        assert ctx.min_complexity_threshold == 3.0
        assert ctx.enable_task_merging is True

    def test_invalid_max_depth(self) -> None:
        with pytest.raises(ValueError, match="max_depth"):
            DecompositionContext(max_depth=0)

    def test_invalid_max_subtasks(self) -> None:
        with pytest.raises(ValueError, match="max_subtasks"):
            DecompositionContext(max_subtasks=0)

    def test_min_exceeds_max(self) -> None:
        with pytest.raises(ValueError, match="min_subtasks.*cannot exceed"):
            DecompositionContext(min_subtasks=10, max_subtasks=5)


# ── RecursiveDecomposer ─────────────────────────────────────────────


class TestRecursiveDecomposer:
    """Tests for RecursiveDecomposer strategy."""

    def test_name(self) -> None:
        decomposer = RecursiveDecomposer()
        assert decomposer.name == "recursive"

    def test_can_decompose_high_complexity(self) -> None:
        decomposer = RecursiveDecomposer()
        task = Task(
            description="Complex task",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=7,
                integration_complexity=6,
                testing_complexity=5,
                unknown_factor=4,
            ),
        )
        ctx = DecompositionContext()
        assert decomposer.can_decompose(task, ctx) is True

    def test_can_decompose_low_complexity(self) -> None:
        decomposer = RecursiveDecomposer()
        task = Task(
            description="Simple task",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=1,
                integration_complexity=1,
                testing_complexity=1,
                unknown_factor=1,
            ),
        )
        ctx = DecompositionContext()
        assert decomposer.can_decompose(task, ctx) is False

    def test_decompose_code_generation(self) -> None:
        decomposer = RecursiveDecomposer()
        task = Task(
            description="Build REST API",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=7,
                integration_complexity=6,
                testing_complexity=5,
                unknown_factor=4,
                estimated_tokens=5000,
            ),
        )
        ctx = DecompositionContext()
        subtasks = decomposer.decompose(task, ctx)

        assert len(subtasks) > 0
        assert all(isinstance(st, Subtask) for st in subtasks)
        assert all(st.parent_id == task.task_id for st in subtasks)

        # Check that phases are present
        types = {st.subtask_type for st in subtasks}
        assert SubtaskType.PREPARATION in types or SubtaskType.ANALYSIS in types
        assert SubtaskType.IMPLEMENTATION in types

    def test_decompose_testing(self) -> None:
        decomposer = RecursiveDecomposer()
        task = Task(
            description="Test the system",
            task_type=TaskType.TESTING,
            complexity=ComplexityEstimate(
                code_complexity=5,
                testing_complexity=7,
                estimated_tokens=3000,
            ),
        )
        ctx = DecompositionContext()
        subtasks = decomposer.decompose(task, ctx)

        assert len(subtasks) >= 2
        # Testing should have preparation and validation
        types = {st.subtask_type for st in subtasks}
        assert SubtaskType.VALIDATION in types

    def test_decompose_respects_max_depth(self) -> None:
        decomposer = RecursiveDecomposer()
        task = Task(
            description="Complex task",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(code_complexity=8),
        )
        ctx = DecompositionContext(max_depth=1)
        subtasks = decomposer.decompose(task, ctx, depth=1)
        assert len(subtasks) == 0  # Max depth reached immediately

    def test_decompose_dependencies_sequential(self) -> None:
        decomposer = RecursiveDecomposer()
        task = Task(
            description="Sequential task",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(code_complexity=7),
        )
        ctx = DecompositionContext()
        subtasks = decomposer.decompose(task, ctx)

        # Check that subtasks have sequential dependencies
        if len(subtasks) >= 2:
            # Second subtask should depend on first
            assert subtasks[0].task_id in subtasks[1].dependencies

    def test_custom_task_type_fallback(self) -> None:
        decomposer = RecursiveDecomposer()
        task = Task(
            description="Custom task",
            task_type=TaskType.CUSTOM,
            complexity=ComplexityEstimate(code_complexity=7),
        )
        ctx = DecompositionContext()
        subtasks = decomposer.decompose(task, ctx)
        # Should fall back to generic phases
        assert len(subtasks) >= 2


# ── DependencyAnalyzer ──────────────────────────────────────────────


class TestDependencyAnalyzer:
    """Tests for DependencyAnalyzer strategy."""

    def test_name(self) -> None:
        analyzer = DependencyAnalyzer()
        assert analyzer.name == "dependency"

    def test_can_decompose_with_dependencies(self) -> None:
        analyzer = DependencyAnalyzer()
        task = Task(
            description="Task with deps",
            dependencies=["other-task"],
        )
        ctx = DecompositionContext()
        assert analyzer.can_decompose(task, ctx) is True

    def test_can_decompose_code_generation(self) -> None:
        analyzer = DependencyAnalyzer()
        task = Task(
            description="Code gen",
            task_type=TaskType.CODE_GENERATION,
        )
        ctx = DecompositionContext()
        assert analyzer.can_decompose(task, ctx) is True

    def test_decompose(self) -> None:
        analyzer = DependencyAnalyzer()
        task = Task(
            description="Build feature",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(code_complexity=7),
        )
        ctx = DecompositionContext()
        subtasks = analyzer.decompose(task, ctx)

        # Should produce preparation, implementation, validation
        assert len(subtasks) == 3
        types = {st.subtask_type for st in subtasks}
        assert SubtaskType.PREPARATION in types
        assert SubtaskType.IMPLEMENTATION in types
        assert SubtaskType.VALIDATION in types

    def test_decompose_dependencies(self) -> None:
        analyzer = DependencyAnalyzer()
        task = Task(
            description="Build feature",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(code_complexity=7),
        )
        ctx = DecompositionContext()
        subtasks = analyzer.decompose(task, ctx)

        # Preparation -> Implementation -> Validation
        prep = next(st for st in subtasks if st.subtask_type == SubtaskType.PREPARATION)
        impl = next(st for st in subtasks if st.subtask_type == SubtaskType.IMPLEMENTATION)
        valid = next(st for st in subtasks if st.subtask_type == SubtaskType.VALIDATION)

        assert prep.task_id in impl.dependencies
        assert impl.task_id in valid.dependencies


# ── ParallelDecomposer ──────────────────────────────────────────────


class TestParallelDecomposer:
    """Tests for ParallelDecomposer strategy."""

    def test_name(self) -> None:
        decomposer = ParallelDecomposer()
        assert decomposer.name == "parallel"

    def test_can_decompose_testing(self) -> None:
        decomposer = ParallelDecomposer()
        task = Task(description="Test", task_type=TaskType.TESTING)
        ctx = DecompositionContext()
        assert decomposer.can_decompose(task, ctx) is True

    def test_can_decompose_documentation(self) -> None:
        decomposer = ParallelDecomposer()
        task = Task(description="Docs", task_type=TaskType.DOCUMENTATION)
        ctx = DecompositionContext()
        assert decomposer.can_decompose(task, ctx) is True

    def test_cannot_decompose_config(self) -> None:
        decomposer = ParallelDecomposer()
        task = Task(description="Config", task_type=TaskType.CONFIGURATION)
        ctx = DecompositionContext()
        assert decomposer.can_decompose(task, ctx) is False

    def test_decompose_testing(self) -> None:
        decomposer = ParallelDecomposer()
        task = Task(
            description="Test everything",
            task_type=TaskType.TESTING,
            complexity=ComplexityEstimate(testing_complexity=7),
        )
        ctx = DecompositionContext()
        subtasks = decomposer.decompose(task, ctx)

        # Should produce unit, integration, edge case tests
        assert len(subtasks) == 3
        tags = {tag for st in subtasks for tag in st.tags}
        assert "unit" in tags
        assert "integration" in tags
        assert "edge-cases" in tags

    def test_decompose_no_dependencies(self) -> None:
        """Parallel subtasks should have no inter-dependencies."""
        decomposer = ParallelDecomposer()
        task = Task(
            description="Test everything",
            task_type=TaskType.TESTING,
            complexity=ComplexityEstimate(testing_complexity=7),
        )
        ctx = DecompositionContext()
        subtasks = decomposer.decompose(task, ctx)

        # All subtasks should be independent
        subtask_ids = {st.task_id for st in subtasks}
        for st in subtasks:
            for dep in st.dependencies:
                assert dep not in subtask_ids, "Parallel subtasks should not depend on each other"


# ── EngineConfig ────────────────────────────────────────────────────


class TestEngineConfig:
    """Tests for EngineConfig dataclass."""

    def test_defaults(self) -> None:
        config = EngineConfig()
        assert len(config.strategies) == 3
        assert "recursive" in config.strategies
        assert "dependency" in config.strategies
        assert "parallel" in config.strategies
        assert config.enable_recursion is True
        assert config.enable_validation is True

    def test_invalid_min_confidence(self) -> None:
        with pytest.raises(ValueError, match="min_confidence"):
            EngineConfig(min_confidence=1.5)


# ── TaskDecompositionEngine ─────────────────────────────────────────


class TestTaskDecompositionEngine:
    """Tests for TaskDecompositionEngine facade."""

    def _make_engine(self) -> TaskDecompositionEngine:
        """Create an engine for testing."""
        return TaskDecompositionEngine()

    def test_initialization(self) -> None:
        engine = self._make_engine()
        assert engine.config is not None
        assert len(engine.config.strategies) == 3

    def test_decompose_simple_task(self) -> None:
        engine = self._make_engine()
        task = Task(
            description="Build REST API",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=7,
                integration_complexity=6,
                testing_complexity=5,
                unknown_factor=4,
                estimated_tokens=5000,
            ),
        )

        result = engine.decompose(task)
        assert isinstance(result, DecompositionResult)
        assert result.total_subtasks >= 2
        assert result.is_valid is True
        assert result.confidence > 0.0

    def test_decompose_low_complexity_trivial(self) -> None:
        engine = self._make_engine()
        task = Task(
            description="Simple task",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=1,
                integration_complexity=1,
                testing_complexity=1,
                unknown_factor=1,
            ),
        )

        result = engine.decompose(task)
        assert result.strategy_used == "trivial"
        assert result.total_subtasks == 1
        assert result.confidence == 1.0

    def test_decompose_with_specific_strategy(self) -> None:
        engine = self._make_engine()
        task = Task(
            description="Test task",
            task_type=TaskType.TESTING,
            complexity=ComplexityEstimate(
                testing_complexity=7,
                code_complexity=6,
                integration_complexity=5,
                unknown_factor=4,
            ),
        )

        result = engine.decompose(task, strategy_name="parallel")
        assert result.strategy_used == "parallel"
        assert result.total_subtasks >= 2

    def test_decompose_invalid_strategy(self) -> None:
        engine = self._make_engine()
        task = Task(
            description="Test",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=7,
                integration_complexity=6,
                testing_complexity=5,
                unknown_factor=4,
            ),
        )

        with pytest.raises(ValueError, match="Strategy.*not found"):
            engine.decompose(task, strategy_name="nonexistent")

    def test_validate_result(self) -> None:
        engine = self._make_engine()
        task = Task(
            description="Validate me",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(code_complexity=7),
        )
        result = engine.decompose(task)

        issues = engine.validate(result)
        assert isinstance(issues, list)
        # Valid decomposition should have no issues
        assert len(issues) == 0

    def test_optimize_result(self) -> None:
        engine = self._make_engine()
        task = Task(
            description="Optimize me",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=7,
                integration_complexity=6,
                testing_complexity=5,
                unknown_factor=4,
                estimated_tokens=5000,
            ),
        )
        result = engine.decompose(task)
        optimized = engine.optimize(result)

        assert optimized.strategy_used.endswith("+optimized")
        assert optimized.total_subtasks == result.total_subtasks

    def test_optimize_priorities(self) -> None:
        engine = self._make_engine()
        task = Task(
            description="Priority test",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(code_complexity=7),
        )
        result = engine.decompose(task)
        optimized = engine.optimize(result)

        # Earlier tasks in topological order should have higher priority
        order = optimized.task_graph.topological_order()
        if len(order) >= 2:
            first_task = optimized.task_graph.get_task(order[0])
            last_task = optimized.task_graph.get_task(order[-1])
            assert first_task.priority >= last_task.priority

    def test_decomposition_history(self) -> None:
        engine = self._make_engine()
        task = Task(
            description="History test",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=7,
                integration_complexity=6,
                testing_complexity=5,
                unknown_factor=4,
            ),
        )

        assert len(engine.get_decomposition_history()) == 0
        engine.decompose(task)
        assert len(engine.get_decomposition_history()) == 1
        engine.decompose(task)
        assert len(engine.get_decomposition_history()) == 2

        engine.clear_history()
        assert len(engine.get_decomposition_history()) == 0

    def test_custom_context(self) -> None:
        engine = self._make_engine()
        task = Task(
            description="Custom context test",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(code_complexity=7),
        )
        ctx = DecompositionContext(max_depth=2, max_subtasks=5)
        result = engine.decompose(task, context=ctx)

        assert result.total_subtasks <= 5

    def test_result_is_stored_in_history(self) -> None:
        engine = self._make_engine()
        task = Task(
            description="History storage",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=7,
                integration_complexity=6,
                testing_complexity=5,
                unknown_factor=4,
            ),
        )
        result = engine.decompose(task)

        history = engine.get_decomposition_history()
        assert len(history) == 1
        assert history[0] is result


# ── Integration Tests ───────────────────────────────────────────────


class TestDecompositionIntegration:
    """Integration tests for the full decomposition pipeline."""

    def test_full_decomposition_pipeline(self) -> None:
        """Test complete decomposition from task to optimized graph."""
        engine = TaskDecompositionEngine()

        # Create a complex task
        task = Task(
            description="Build and deploy microservice with authentication",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=8,
                integration_complexity=7,
                testing_complexity=6,
                unknown_factor=5,
                estimated_tokens=10000,
            ),
            tags=["backend", "security"],
            priority=5,
        )

        # Decompose
        result = engine.decompose(task)
        assert result.is_valid
        assert result.total_subtasks >= 2

        # Validate
        issues = engine.validate(result)
        assert len(issues) == 0

        # Optimize
        optimized = engine.optimize(result)
        assert optimized.is_valid

        # Check the graph
        graph = optimized.task_graph
        order = graph.topological_order()
        assert len(order) == result.total_subtasks

        # Check execution readiness
        ready = graph.get_ready_tasks()
        assert len(ready) >= 1  # At least one task should be ready

    def test_multiple_task_types(self) -> None:
        """Test decomposition across different task types."""
        engine = TaskDecompositionEngine()

        task_types = [
            (TaskType.CODE_GENERATION, 7),
            (TaskType.TESTING, 6),
            (TaskType.DOCUMENTATION, 5),
            (TaskType.ANALYSIS, 6),
            (TaskType.REFACTORING, 7),
        ]

        for task_type, complexity in task_types:
            task = Task(
                description=f"Complex {task_type.value} task",
                task_type=task_type,
                complexity=ComplexityEstimate(
                    code_complexity=complexity,
                    testing_complexity=complexity,
                    estimated_tokens=3000,
                ),
            )

            result = engine.decompose(task)
            assert result.is_valid, f"Invalid result for {task_type}"
            assert result.total_subtasks >= 2, f"Too few subtasks for {task_type}"

    def test_nested_decomposition(self) -> None:
        """Test that recursive decomposition works."""
        config = EngineConfig(
            default_context=DecompositionContext(
                max_depth=3,
                min_complexity_threshold=3.0,
            ),
            enable_recursion=True,
        )
        engine = TaskDecompositionEngine(config=config)

        task = Task(
            description="Very complex nested task",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=9,
                integration_complexity=8,
                testing_complexity=7,
                unknown_factor=6,
                estimated_tokens=15000,
            ),
        )

        result = engine.decompose(task)
        assert result.is_valid
        # With recursion, should produce more subtasks
        assert result.total_subtasks >= 3

    def test_execution_simulation(self) -> None:
        """Simulate executing decomposed tasks in order."""
        engine = TaskDecompositionEngine()

        task = Task(
            description="Execution test",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(code_complexity=7),
        )
        result = engine.decompose(task)
        graph = result.task_graph

        # Execute tasks in topological order
        completed = 0
        while not graph.is_complete:
            ready = graph.get_ready_tasks()
            assert len(ready) > 0, "No ready tasks but graph not complete"

            for task in ready:
                task.mark_running()
                task.mark_completed()
                completed += 1

        assert graph.is_complete
        assert completed == result.total_subtasks
        assert graph.completed_fraction == 1.0

    def test_complexity_distribution(self) -> None:
        """Test that complexity is properly distributed across subtasks."""
        engine = TaskDecompositionEngine()

        task = Task(
            description="Complexity distribution test",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(
                code_complexity=8,
                integration_complexity=7,
                testing_complexity=6,
                unknown_factor=5,
                estimated_tokens=5000,
            ),
        )

        result = engine.decompose(task)

        # Each subtask should have reasonable complexity
        for subtask in result.task_graph.tasks.values():
            if isinstance(subtask, Subtask):
                complexity = subtask.effective_complexity
                assert complexity.overall_score <= 10.0
                assert complexity.overall_score >= 1.0

    def test_dependency_consistency(self) -> None:
        """Test that all dependencies are properly resolved."""
        engine = TaskDecompositionEngine()

        task = Task(
            description="Dependency test",
            task_type=TaskType.CODE_GENERATION,
            complexity=ComplexityEstimate(code_complexity=7),
        )
        result = engine.decompose(task)

        # All dependencies should exist in the graph
        for subtask in result.task_graph.tasks.values():
            for dep_id in subtask.dependencies:
                assert dep_id in result.task_graph.tasks, (
                    f"Dependency '{dep_id}' not found for task '{subtask.task_id}'"
                )
