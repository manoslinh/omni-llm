"""
Task Decomposition Engine for Omni-LLM.

Main facade for breaking complex tasks into atomic, dependency-ordered
subtasks using multiple decomposition strategies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from omni.task.models import Task, TaskGraph

from .complexity_analyzer import ComplexityAnalyzer
from .models import DecompositionResult, Subtask, SubtaskType
from .strategies import (
    DecompositionContext,
    DecompositionStrategy,
    DependencyAnalyzer,
    ParallelDecomposer,
    RecursiveDecomposer,
)

logger = logging.getLogger(__name__)


@dataclass
class EngineConfig:
    """Configuration for the Task Decomposition Engine."""

    # Default decomposition context
    default_context: DecompositionContext = field(
        default_factory=DecompositionContext
    )

    # Available strategies
    strategies: dict[str, DecompositionStrategy] = field(default_factory=dict)

    # Strategy selection order (first match wins)
    strategy_priority: list[str] = field(default_factory=list)

    # Whether to enable recursive decomposition
    enable_recursion: bool = True

    # Whether to validate results
    enable_validation: bool = True

    # Minimum confidence threshold for accepting decomposition
    min_confidence: float = 0.5

    def __post_init__(self) -> None:
        """Initialize default strategies if not provided."""
        if not self.strategies:
            self.strategies = {
                "recursive": RecursiveDecomposer(),
                "dependency": DependencyAnalyzer(),
                "parallel": ParallelDecomposer(),
            }

        if not self.strategy_priority:
            self.strategy_priority = ["recursive", "dependency", "parallel"]

        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError(
                f"min_confidence must be between 0.0 and 1.0, "
                f"got {self.min_confidence}"
            )


class TaskDecompositionEngine:
    """
    Main engine for task decomposition.

    Coordinates multiple decomposition strategies to break complex
    tasks into atomic, manageable subtasks with proper dependency
    ordering.

    The engine:
    1. Analyzes task complexity to determine if decomposition is needed
    2. Selects the best strategy based on task type and context
    3. Decomposes the task recursively until atomic subtasks are reached
    4. Validates the resulting task graph for correctness
    5. Optimizes the graph for execution efficiency

    Example:
        >>> engine = TaskDecompositionEngine()
        >>> task = Task(
        ...     description="Build REST API with auth",
        ...     task_type=TaskType.CODE_GENERATION,
        ...     complexity=ComplexityEstimate(
        ...         code_complexity=7,
        ...         integration_complexity=6,
        ...         estimated_tokens=5000,
        ...     ),
        ... )
        >>> result = engine.decompose(task)
        >>> print(result.total_subtasks)  # e.g., 5
        >>> print(result.task_graph.topological_order())  # Ordered subtask IDs
    """

    def __init__(self, config: EngineConfig | None = None) -> None:
        """
        Initialize the Task Decomposition Engine.

        Args:
            config: Engine configuration (uses defaults if not provided)
        """
        self.config = config or EngineConfig()
        self._decomposition_history: list[DecompositionResult] = []
        self._complexity_analyzer: ComplexityAnalyzer | None = None  # Lazy initialization

    def decompose(
        self,
        task: Task,
        context: DecompositionContext | None = None,
        strategy_name: str | None = None,
    ) -> DecompositionResult:
        """
        Decompose a complex task into atomic subtasks.

        This is the main entry point for the engine. It:
        1. Checks if decomposition is needed
        2. Selects the best strategy
        3. Recursively decomposes the task
        4. Builds a dependency graph
        5. Validates the result

        Args:
            task: The task to decompose
            context: Decomposition context (uses default if not provided)
            strategy_name: Specific strategy to use (None for auto-select)

        Returns:
            DecompositionResult with the task graph and metadata

        Raises:
            ValueError: If task cannot be decomposed
        """
        ctx = context or self.config.default_context

        # Check if decomposition is needed
        if not self._needs_decomposition(task, ctx):
            logger.info(
                f"Task '{task.task_id}' does not need decomposition "
                f"(complexity: {task.effective_complexity.overall_score:.1f})"
            )
            return self._create_trivial_result(task)

        # Select strategy
        strategy = self._select_strategy(task, ctx, strategy_name)
        if strategy is None:
            raise ValueError(
                f"No suitable decomposition strategy found for task type "
                f"{task.task_type}"
            )

        logger.info(
            f"Decomposing task '{task.task_id}' using '{strategy.name}' strategy"
        )

        # Perform decomposition
        subtasks = self._decompose_recursive(task, ctx, strategy, depth=0)

        if not subtasks:
            raise ValueError(
                f"Strategy '{strategy.name}' produced no subtasks for task "
                f"'{task.task_id}'"
            )

        # Build task graph
        task_graph = self._build_task_graph(task, subtasks)

        # Create result
        result = DecompositionResult(
            original_task=task,
            task_graph=task_graph,
            strategy_used=strategy.name,
            confidence=self._calculate_confidence(task, subtasks, ctx),
            reasoning=self._generate_reasoning(task, subtasks, strategy),
        )

        # Validate if enabled
        if self.config.enable_validation:
            result = self._validate_result(result, ctx)

        # Store in history
        self._decomposition_history.append(result)

        logger.info(
            f"Decomposition complete: {result.total_subtasks} subtasks, "
            f"depth {result.max_depth}, confidence {result.confidence:.2f}"
        )

        return result

    def validate(self, result: DecompositionResult) -> list[str]:
        """
        Validate a decomposition result.

        Checks for:
        - Graph validity (no cycles, proper dependencies)
        - Subtask completeness (all required fields present)
        - Dependency consistency
        - Complexity distribution

        Args:
            result: Decomposition result to validate

        Returns:
            List of validation issues (empty if valid)
        """
        issues: list[str] = []

        # Validate task graph structure
        graph_issues = result.task_graph.validate()
        issues.extend(graph_issues)

        # Validate subtask properties
        for task_id, task in result.task_graph.tasks.items():
            if isinstance(task, Subtask):
                # Check depth consistency
                if task.depth < 0:
                    issues.append(f"Subtask '{task_id}' has negative depth")

                # Check parent reference
                if task.parent_id != result.original_task.task_id:
                    # This is OK for nested decompositions, but log it
                    pass

                # Check effort score
                if task.effort_score < 0:
                    issues.append(
                        f"Subtask '{task_id}' has negative effort score"
                    )

        # Check for duplicate dependencies
        for task_id, task in result.task_graph.tasks.items():
            if len(task.dependencies) != len(set(task.dependencies)):
                issues.append(
                    f"Task '{task_id}' has duplicate dependencies"
                )

        # Validate complexity distribution
        subtasks = [
            t for t in result.task_graph.tasks.values()
            if isinstance(t, Subtask)
        ]
        if subtasks:
            avg_complexity = sum(
                t.effective_complexity.overall_score for t in subtasks
            ) / len(subtasks)
            if avg_complexity > 8.0:
                issues.append(
                    f"Average subtask complexity is high ({avg_complexity:.1f}), "
                    f"consider further decomposition"
                )

        return issues

    def optimize(self, result: DecompositionResult) -> DecompositionResult:
        """
        Optimize a decomposition result for execution efficiency.

        Applies optimizations:
        - Merges small sequential tasks
        - Identifies parallel execution opportunities
        - Adjusts priorities based on dependencies
        - Removes redundant dependencies

        Args:
            result: Decomposition result to optimize

        Returns:
            Optimized DecompositionResult
        """
        if result.total_subtasks < 2:
            return result

        logger.info(f"Optimizing decomposition with {result.total_subtasks} subtasks")

        # Create a copy of the task graph
        optimized_graph = TaskGraph(name=result.task_graph.name)

        # Copy all tasks
        for _task_id, task in result.task_graph.tasks.items():
            # Create a copy of the task
            optimized_task: Task
            if isinstance(task, Subtask):
                optimized_task = Subtask(
                    description=task.description,
                    task_type=task.task_type,
                    task_id=task.task_id,
                    status=task.status,
                    dependencies=task.dependencies.copy(),
                    complexity=task.complexity,
                    context=task.context.copy(),
                    tags=task.tags.copy(),
                    priority=task.priority,
                    max_retries=task.max_retries,
                    retry_count=task.retry_count,
                    subtask_type=task.subtask_type,
                    depth=task.depth,
                    parent_id=task.parent_id,
                    effort_score=task.effort_score,
                    required_capabilities=task.required_capabilities.copy(),
                )
            else:
                optimized_task = Task(
                    description=task.description,
                    task_type=task.task_type,
                    task_id=task.task_id,
                    status=task.status,
                    dependencies=task.dependencies.copy(),
                    complexity=task.complexity,
                    context=task.context.copy(),
                    tags=task.tags.copy(),
                    priority=task.priority,
                    max_retries=task.max_retries,
                    retry_count=task.retry_count,
                )
            optimized_graph.add_task(optimized_task)

        # Apply optimizations
        self._optimize_priorities(optimized_graph)
        self._remove_redundant_dependencies(optimized_graph)

        # Create optimized result
        optimized_result = DecompositionResult(
            original_task=result.original_task,
            task_graph=optimized_graph,
            strategy_used=result.strategy_used + "+optimized",
            confidence=result.confidence,
            reasoning=result.reasoning + " (optimized)",
        )

        return optimized_result

    def get_decomposition_history(self) -> list[DecompositionResult]:
        """Get the history of decompositions performed."""
        return self._decomposition_history.copy()

    def clear_history(self) -> None:
        """Clear the decomposition history."""
        self._decomposition_history.clear()

    # ── Private Methods ─────────────────────────────────────────────

    def _needs_decomposition(
        self, task: Task, context: DecompositionContext
    ) -> bool:
        """Check if a task needs decomposition."""
        # Check if task has explicit complexity estimate
        if task.complexity is None:
            # No explicit complexity, estimate it from description
            if self._complexity_analyzer is None:
                self._complexity_analyzer = ComplexityAnalyzer()

            estimated_complexity = self._complexity_analyzer.analyze_task_complexity(task)
            # Always update task with estimated complexity for accuracy
            task.complexity = estimated_complexity
            complexity = estimated_complexity
        else:
            complexity = task.complexity

        # Check complexity threshold
        if complexity.overall_score < context.min_complexity_threshold:
            return False

        # Check if any strategy can decompose it
        for strategy in self.config.strategies.values():
            if strategy.can_decompose(task, context):
                return True

        return False

    def _select_strategy(
        self,
        task: Task,
        context: DecompositionContext,
        strategy_name: str | None,
    ) -> DecompositionStrategy | None:
        """Select the best decomposition strategy for a task."""
        # Use specified strategy if provided
        if strategy_name is not None:
            if strategy_name not in self.config.strategies:
                raise ValueError(
                    f"Strategy '{strategy_name}' not found. "
                    f"Available: {list(self.config.strategies.keys())}"
                )
            strategy = self.config.strategies[strategy_name]
            if strategy.can_decompose(task, context):
                return strategy
            logger.warning(
                f"Strategy '{strategy_name}' cannot decompose task type "
                f"{task.task_type}, trying other strategies"
            )

        # Try strategies in priority order
        for name in self.config.strategy_priority:
            if name in self.config.strategies:
                strategy = self.config.strategies[name]
                if strategy.can_decompose(task, context):
                    return strategy

        # Try all strategies as fallback
        for strategy in self.config.strategies.values():
            if strategy.can_decompose(task, context):
                return strategy

        return None

    def _decompose_recursive(
        self,
        task: Task,
        context: DecompositionContext,
        strategy: DecompositionStrategy,
        depth: int,
    ) -> list[Subtask]:
        """Recursively decompose a task until atomic subtasks are reached."""
        if depth >= context.max_depth:
            logger.warning(f"Max depth {context.max_depth} reached")
            return []

        # Get subtasks from strategy
        subtasks = strategy.decompose(task, context, depth)

        if not subtasks:
            return []

        # Check if recursion is enabled and subtasks need further decomposition
        if self.config.enable_recursion and depth < context.max_depth - 1:
            final_subtasks: list[Subtask] = []
            for subtask in subtasks:
                # Check if this subtask needs further decomposition
                if self._needs_decomposition(subtask, context):
                    # Find a strategy for this subtask
                    sub_strategy = self._select_strategy(subtask, context, None)
                    if sub_strategy:
                        logger.debug(
                            f"Recursively decomposing subtask '{subtask.task_id}' "
                            f"at depth {depth + 1}"
                        )
                        nested = self._decompose_recursive(
                            subtask, context, sub_strategy, depth + 1
                        )
                        if nested:
                            final_subtasks.extend(nested)
                            continue

                # Keep the subtask as-is
                final_subtasks.append(subtask)

            return final_subtasks

        return subtasks

    def _build_task_graph(
        self, original_task: Task, subtasks: list[Subtask]
    ) -> TaskGraph:
        """Build a TaskGraph from the list of subtasks."""
        graph = TaskGraph(name=f"decomposition-{original_task.task_id}")

        # Add all subtasks
        for subtask in subtasks:
            try:
                graph.add_task(subtask)
            except ValueError as e:
                # Log but continue - dependency might be to original task
                logger.warning(f"Could not add subtask '{subtask.task_id}': {e}")

        return graph

    def _calculate_confidence(
        self,
        task: Task,
        subtasks: list[Subtask],
        context: DecompositionContext,
    ) -> float:
        """Calculate confidence score for the decomposition."""
        if not subtasks:
            return 0.0

        confidence = 0.5  # Base confidence

        # Boost for reasonable subtask count
        if context.min_subtasks <= len(subtasks) <= context.max_subtasks:
            confidence += 0.2

        # Boost for type coverage
        types_present = {st.subtask_type for st in subtasks}
        if SubtaskType.IMPLEMENTATION in types_present:
            confidence += 0.1
        if SubtaskType.VALIDATION in types_present:
            confidence += 0.1

        # Boost for complexity distribution
        avg_complexity = sum(
            st.effective_complexity.overall_score for st in subtasks
        ) / len(subtasks)
        if avg_complexity <= context.target_leaf_complexity * 1.5:
            confidence += 0.1

        return min(1.0, confidence)

    def _generate_reasoning(
        self,
        task: Task,
        subtasks: list[Subtask],
        strategy: DecompositionStrategy,
    ) -> str:
        """Generate human-readable reasoning for the decomposition."""
        phases: dict[str, int] = {}
        for st in subtasks:
            phase = str(st.subtask_type)
            phases[phase] = phases.get(phase, 0) + 1

        phase_summary = ", ".join(f"{count} {phase}" for phase, count in phases.items())

        return (
            f"Decomposed '{task.description[:50]}...' into {len(subtasks)} "
            f"subtasks using {strategy.name} strategy. "
            f"Phase distribution: {phase_summary}."
        )

    def _validate_result(
        self, result: DecompositionResult, context: DecompositionContext
    ) -> DecompositionResult:
        """Validate and potentially fix the decomposition result."""
        issues = self.validate(result)

        if issues:
            result.is_valid = False
            result.validation_issues = issues
            logger.warning(
                f"Decomposition validation found {len(issues)} issues: "
                f"{issues[:3]}..."
            )
        else:
            result.is_valid = True

        return result

    def _create_trivial_result(self, task: Task) -> DecompositionResult:
        """Create a trivial result for tasks that don't need decomposition."""
        graph = TaskGraph(name=f"trivial-{task.task_id}")

        # Create a single subtask that is the task itself
        subtask = Subtask.from_task(
            task,
            subtask_type=SubtaskType.IMPLEMENTATION,
            depth=0,
            parent_id=task.task_id,
        )
        graph.add_task(subtask)

        return DecompositionResult(
            original_task=task,
            task_graph=graph,
            strategy_used="trivial",
            confidence=1.0,
            reasoning="Task complexity below threshold, no decomposition needed.",
        )

    def _optimize_priorities(self, graph: TaskGraph) -> None:
        """Adjust task priorities based on dependency position."""
        try:
            order = graph.topological_order()
            # Tasks earlier in the order get higher priority
            for i, task_id in enumerate(order):
                task = graph.get_task(task_id)
                # Inverse of position (earlier = higher priority)
                task.priority = max(0, len(order) - i)
        except Exception as e:
            logger.warning(f"Could not optimize priorities: {e}")

    def _remove_redundant_dependencies(self, graph: TaskGraph) -> None:
        """Remove transitive dependencies that are redundant."""
        try:
            # Get topological order
            order = graph.topological_order()

            for task_id in order:
                task = graph.get_task(task_id)
                if not task.dependencies:
                    continue

                # Find transitive dependencies
                transitive: set[str] = set()
                for dep_id in task.dependencies:
                    dep_task = graph.get_task(dep_id)
                    transitive.update(dep_task.dependencies)

                # Remove transitive dependencies from direct dependencies
                redundant = set(task.dependencies) & transitive
                if redundant:
                    for dep_id in redundant:
                        task.dependencies.remove(dep_id)
                    logger.debug(
                        f"Removed {len(redundant)} redundant dependencies "
                        f"from task '{task_id}'"
                    )
        except Exception as e:
            logger.warning(f"Could not remove redundant dependencies: {e}")
