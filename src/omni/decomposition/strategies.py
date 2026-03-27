"""
Decomposition strategies for breaking tasks into subtasks.

Implements recursive decomposition and dependency analysis algorithms
for the Task Decomposition Engine.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from omni.task.models import ComplexityEstimate, Task, TaskType

from .models import Subtask, SubtaskType

logger = logging.getLogger(__name__)


@dataclass
class DecompositionContext:
    """Context for decomposition decisions.

    Provides configuration and constraints for how tasks
    should be decomposed.
    """

    # Maximum recursion depth
    max_depth: int = 5

    # Maximum number of subtasks per decomposition
    max_subtasks: int = 20

    # Minimum complexity score to continue decomposing
    min_complexity_threshold: float = 3.0

    # Target complexity for leaf tasks
    target_leaf_complexity: float = 2.0

    # Whether to merge small adjacent tasks
    enable_task_merging: bool = True

    # Minimum subtask count (avoid trivial decompositions)
    min_subtasks: int = 2

    # Custom decomposition rules
    rules: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate decomposition context."""
        if self.max_depth < 1:
            raise ValueError(f"max_depth must be >= 1, got {self.max_depth}")
        if self.max_subtasks < 1:
            raise ValueError(f"max_subtasks must be >= 1, got {self.max_subtasks}")
        if self.min_subtasks < 1:
            raise ValueError(f"min_subtasks must be >= 1, got {self.min_subtasks}")
        if self.min_subtasks > self.max_subtasks:
            raise ValueError(
                f"min_subtasks ({self.min_subtasks}) cannot exceed "
                f"max_subtasks ({self.max_subtasks})"
            )


class DecompositionStrategy(ABC):
    """Abstract base class for decomposition strategies.

    Each strategy implements a different approach to breaking
    down complex tasks into manageable subtasks.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the decomposition strategy."""
        ...

    @abstractmethod
    def can_decompose(self, task: Task, context: DecompositionContext) -> bool:
        """Check if this strategy can decompose the given task.

        Args:
            task: Task to potentially decompose
            context: Decomposition context

        Returns:
            True if decomposition is possible and beneficial
        """
        ...

    @abstractmethod
    def decompose(
        self,
        task: Task,
        context: DecompositionContext,
        depth: int = 0,
    ) -> list[Subtask]:
        """Decompose a task into subtasks.

        Args:
            task: Task to decompose
            context: Decomposition context
            depth: Current recursion depth

        Returns:
            List of subtasks with dependencies set up
        """
        ...

    def _create_subtask(
        self,
        description: str,
        task_type: TaskType,
        subtask_type: SubtaskType,
        parent: Task,
        depth: int,
        dependencies: list[str] | None = None,
        complexity: ComplexityEstimate | None = None,
        effort_score: float = 1.0,
        required_capabilities: list[str] | None = None,
        priority: int = 0,
        tags: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> Subtask:
        """Helper to create a Subtask with common fields.

        Args:
            description: Task description
            task_type: Type of task
            subtask_type: Type of subtask
            parent: Parent task
            depth: Current depth
            dependencies: List of dependency task IDs
            complexity: Complexity estimate
            effort_score: Relative effort
            required_capabilities: Required capabilities
            priority: Task priority
            tags: Task tags
            context: Additional context

        Returns:
            New Subtask instance
        """
        return Subtask(
            description=description,
            task_type=task_type,
            subtask_type=subtask_type,
            depth=depth,
            parent_id=parent.task_id,
            dependencies=dependencies or [],
            complexity=complexity,
            effort_score=effort_score,
            required_capabilities=required_capabilities or [],
            priority=priority,
            tags=tags or [],
            context=context or {},
        )


class RecursiveDecomposer(DecompositionStrategy):
    """Recursive decomposition strategy.

    Breaks tasks down by identifying logical phases and
    decomposing each phase until reaching atomic tasks.
    """

    # Task type to subtask phase mapping
    PHASE_PATTERNS: dict[TaskType, list[tuple[SubtaskType, str]]] = {
        TaskType.CODE_GENERATION: [
            (SubtaskType.PREPARATION, "Analyze requirements"),
            (SubtaskType.ANALYSIS, "Design solution"),
            (SubtaskType.IMPLEMENTATION, "Implement core logic"),
            (SubtaskType.VALIDATION, "Test implementation"),
            (SubtaskType.CLEANUP, "Clean up and refactor"),
        ],
        TaskType.CODE_REVIEW: [
            (SubtaskType.ANALYSIS, "Analyze code structure"),
            (SubtaskType.ANALYSIS, "Check for issues"),
            (SubtaskType.VALIDATION, "Validate findings"),
            (SubtaskType.IMPLEMENTATION, "Document recommendations"),
        ],
        TaskType.TESTING: [
            (SubtaskType.PREPARATION, "Setup test environment"),
            (SubtaskType.ANALYSIS, "Identify test cases"),
            (SubtaskType.IMPLEMENTATION, "Write test code"),
            (SubtaskType.VALIDATION, "Run and verify tests"),
        ],
        TaskType.REFACTORING: [
            (SubtaskType.ANALYSIS, "Analyze current structure"),
            (SubtaskType.PREPARATION, "Plan refactoring"),
            (SubtaskType.IMPLEMENTATION, "Apply changes"),
            (SubtaskType.VALIDATION, "Verify behavior preserved"),
            (SubtaskType.CLEANUP, "Clean up artifacts"),
        ],
        TaskType.DOCUMENTATION: [
            (SubtaskType.ANALYSIS, "Gather information"),
            (SubtaskType.IMPLEMENTATION, "Write documentation"),
            (SubtaskType.VALIDATION, "Review and edit"),
        ],
        TaskType.ANALYSIS: [
            (SubtaskType.PREPARATION, "Gather data"),
            (SubtaskType.ANALYSIS, "Analyze findings"),
            (SubtaskType.IMPLEMENTATION, "Synthesize results"),
        ],
        TaskType.CONFIGURATION: [
            (SubtaskType.ANALYSIS, "Understand requirements"),
            (SubtaskType.IMPLEMENTATION, "Apply configuration"),
            (SubtaskType.VALIDATION, "Verify configuration"),
        ],
        TaskType.DEPLOYMENT: [
            (SubtaskType.PREPARATION, "Prepare deployment"),
            (SubtaskType.IMPLEMENTATION, "Execute deployment"),
            (SubtaskType.VALIDATION, "Verify deployment"),
            (SubtaskType.CLEANUP, "Post-deployment cleanup"),
        ],
    }

    @property
    def name(self) -> str:
        return "recursive"

    def can_decompose(self, task: Task, context: DecompositionContext) -> bool:
        """Check if recursive decomposition is applicable."""
        # Check complexity threshold
        complexity = task.effective_complexity
        if complexity.overall_score < context.min_complexity_threshold:
            logger.debug(
                f"Task complexity {complexity.overall_score} below threshold "
                f"{context.min_complexity_threshold}"
            )
            return False

        # Check if we have a pattern for this task type
        if task.task_type not in self.PHASE_PATTERNS:
            # Use CUSTOM pattern as fallback
            if task.task_type != TaskType.CUSTOM:
                return False

        return True

    def decompose(
        self,
        task: Task,
        context: DecompositionContext,
        depth: int = 0,
    ) -> list[Subtask]:
        """Recursively decompose a task into phases."""
        if depth >= context.max_depth:
            logger.warning(f"Max depth {context.max_depth} reached, stopping")
            return []

        # Get phase pattern for this task type
        phases = self.PHASE_PATTERNS.get(task.task_type, self._get_custom_phases(task))

        # Limit to max subtasks
        phases = phases[: context.max_subtasks]

        subtasks: list[Subtask] = []
        prev_task_id: str | None = None

        for i, (subtask_type, description_template) in enumerate(phases):
            # Generate description
            description = self._generate_description(task, description_template, i + 1)

            # Estimate complexity for this phase
            complexity = self._estimate_phase_complexity(task, subtask_type, i, len(phases))

            # Build dependencies (sequential by default)
            dependencies: list[str] = []
            if prev_task_id is not None and i > 0:
                dependencies.append(prev_task_id)

            # Create subtask
            subtask = self._create_subtask(
                description=description,
                task_type=task.task_type,
                subtask_type=subtask_type,
                parent=task,
                depth=depth,
                dependencies=dependencies,
                complexity=complexity,
                effort_score=self._estimate_effort(subtask_type, complexity),
                required_capabilities=self._infer_capabilities(task, subtask_type),
                priority=task.priority,
                tags=task.tags + [f"phase-{i + 1}", str(subtask_type)],
                context={
                    **task.context,
                    "phase_index": i,
                    "total_phases": len(phases),
                    "parent_description": task.description,
                },
            )

            subtasks.append(subtask)
            prev_task_id = subtask.task_id

        return subtasks

    def _get_custom_phases(self, task: Task) -> list[tuple[SubtaskType, str]]:
        """Generate generic phases for custom task types."""
        return [
            (SubtaskType.ANALYSIS, "Analyze the task"),
            (SubtaskType.IMPLEMENTATION, "Execute the task"),
            (SubtaskType.VALIDATION, "Verify the result"),
        ]

    def _generate_description(
        self, parent: Task, template: str, phase_num: int
    ) -> str:
        """Generate a subtask description from template."""
        return f"{template} (for: {parent.description[:50]}...)"

    def _estimate_phase_complexity(
        self,
        parent: Task,
        subtask_type: SubtaskType,
        phase_index: int,
        total_phases: int,
    ) -> ComplexityEstimate:
        """Estimate complexity for a specific phase."""
        base = parent.effective_complexity

        # Reduce complexity per phase (division of work).
        # Use 0.8/total_phases so that IMPLEMENTATION subtasks from
        # high-complexity parents stay above the recursion threshold,
        # enabling genuine recursive decomposition at depth > 0.
        reduction_factor = 0.8 / total_phases

        # Different phases have different complexity profiles
        type_multipliers = {
            SubtaskType.PREPARATION: 0.5,
            SubtaskType.ANALYSIS: 0.8,
            SubtaskType.IMPLEMENTATION: 1.2,
            SubtaskType.VALIDATION: 0.6,
            SubtaskType.INTEGRATION: 0.9,
            SubtaskType.CLEANUP: 0.3,
        }
        multiplier = type_multipliers.get(subtask_type, 0.7)

        return ComplexityEstimate(
            code_complexity=max(1, int(base.code_complexity * reduction_factor * multiplier)),
            integration_complexity=max(1, int(base.integration_complexity * reduction_factor * multiplier)),
            testing_complexity=max(1, int(base.testing_complexity * reduction_factor * multiplier)),
            unknown_factor=max(1, int(base.unknown_factor * reduction_factor * multiplier)),
            estimated_tokens=max(100, int(base.estimated_tokens * reduction_factor)),
            reasoning=f"Phase {phase_index + 1}/{total_phases} decomposition of parent task",
        )

    def _estimate_effort(
        self, subtask_type: SubtaskType, complexity: ComplexityEstimate
    ) -> float:
        """Estimate relative effort for a subtask."""
        type_effort = {
            SubtaskType.PREPARATION: 0.5,
            SubtaskType.ANALYSIS: 0.8,
            SubtaskType.IMPLEMENTATION: 1.5,
            SubtaskType.VALIDATION: 0.7,
            SubtaskType.INTEGRATION: 1.0,
            SubtaskType.CLEANUP: 0.3,
        }
        base_effort = type_effort.get(subtask_type, 1.0)
        complexity_factor = complexity.overall_score / 5.0
        return base_effort * complexity_factor

    def _infer_capabilities(
        self, parent: Task, subtask_type: SubtaskType
    ) -> list[str]:
        """Infer required capabilities for a subtask."""
        capabilities: list[str] = []

        # Add capabilities based on task type
        type_capabilities = {
            TaskType.CODE_GENERATION: ["coding", "testing"],
            TaskType.CODE_REVIEW: ["analysis", "coding"],
            TaskType.TESTING: ["testing", "analysis"],
            TaskType.REFACTORING: ["coding", "analysis"],
            TaskType.DOCUMENTATION: ["writing", "analysis"],
            TaskType.ANALYSIS: ["analysis"],
            TaskType.CONFIGURATION: ["configuration"],
            TaskType.DEPLOYMENT: ["deployment", "configuration"],
        }
        capabilities.extend(type_capabilities.get(parent.task_type, []))

        # Add capabilities based on subtask type
        if subtask_type == SubtaskType.VALIDATION:
            capabilities.append("testing")
        elif subtask_type == SubtaskType.ANALYSIS:
            capabilities.append("analysis")

        return list(set(capabilities))


class DependencyAnalyzer(DecompositionStrategy):
    """Dependency-based decomposition strategy.

    Analyzes task dependencies and breaks down tasks based on
    their dependency relationships and execution order.
    """

    @property
    def name(self) -> str:
        return "dependency"

    def can_decompose(self, task: Task, context: DecompositionContext) -> bool:
        """Check if dependency analysis can decompose the task."""
        # Dependency analysis works best for tasks with existing dependencies
        # or for tasks that can be parallelized
        return len(task.dependencies) > 0 or task.task_type in (
            TaskType.CODE_GENERATION,
            TaskType.TESTING,
            TaskType.DEPLOYMENT,
        )

    def decompose(
        self,
        task: Task,
        context: DecompositionContext,
        depth: int = 0,
    ) -> list[Subtask]:
        """Decompose based on dependency analysis."""
        if depth >= context.max_depth:
            return []

        subtasks: list[Subtask] = []

        # Create preparation phase
        prep = self._create_subtask(
            description=f"Prepare resources for: {task.description}",
            task_type=task.task_type,
            subtask_type=SubtaskType.PREPARATION,
            parent=task,
            depth=depth,
            complexity=ComplexityEstimate(
                code_complexity=1,
                integration_complexity=2,
                testing_complexity=1,
                unknown_factor=1,
                estimated_tokens=200,
                reasoning="Preparation phase",
            ),
            effort_score=0.5,
            required_capabilities=["setup"],
            tags=task.tags + ["prep"],
        )
        subtasks.append(prep)

        # Create parallel execution phases
        execution = self._create_subtask(
            description=f"Execute core work: {task.description}",
            task_type=task.task_type,
            subtask_type=SubtaskType.IMPLEMENTATION,
            parent=task,
            depth=depth,
            dependencies=[prep.task_id],
            complexity=task.effective_complexity,
            effort_score=1.5,
            required_capabilities=self._get_execution_capabilities(task),
            priority=task.priority,
            tags=task.tags + ["execution"],
            context={
                **task.context,
                "parallelizable": True,
                "parent_description": task.description,
            },
        )
        subtasks.append(execution)

        # Create validation phase
        validation = self._create_subtask(
            description=f"Validate results: {task.description}",
            task_type=task.task_type,
            subtask_type=SubtaskType.VALIDATION,
            parent=task,
            depth=depth,
            dependencies=[execution.task_id],
            complexity=ComplexityEstimate(
                code_complexity=2,
                integration_complexity=1,
                testing_complexity=3,
                unknown_factor=1,
                estimated_tokens=300,
                reasoning="Validation phase",
            ),
            effort_score=0.7,
            required_capabilities=["testing", "verification"],
            tags=task.tags + ["validation"],
        )
        subtasks.append(validation)

        return subtasks

    def _get_execution_capabilities(self, task: Task) -> list[str]:
        """Get required capabilities for execution phase."""
        capabilities = ["implementation"]

        if task.task_type == TaskType.CODE_GENERATION:
            capabilities.extend(["coding", "debugging"])
        elif task.task_type == TaskType.TESTING:
            capabilities.extend(["testing", "analysis"])
        elif task.task_type == TaskType.DEPLOYMENT:
            capabilities.extend(["deployment", "configuration"])

        return capabilities


class ParallelDecomposer(DecompositionStrategy):
    """Parallel decomposition strategy.

    Identifies independent subtasks that can run concurrently
    and structures them for parallel execution.
    """

    @property
    def name(self) -> str:
        return "parallel"

    def can_decompose(self, task: Task, context: DecompositionContext) -> bool:
        """Check if parallel decomposition is applicable."""
        # Best for tasks that can be naturally parallelized
        return task.task_type in (
            TaskType.TESTING,
            TaskType.DOCUMENTATION,
            TaskType.ANALYSIS,
            TaskType.CODE_REVIEW,
        )

    def decompose(
        self,
        task: Task,
        context: DecompositionContext,
        depth: int = 0,
    ) -> list[Subtask]:
        """Decompose into parallel independent subtasks."""
        if depth >= context.max_depth:
            return []

        subtasks: list[Subtask] = []

        # Create independent subtasks based on task type
        if task.task_type == TaskType.TESTING:
            subtasks = self._decompose_testing(task, depth)
        elif task.task_type == TaskType.DOCUMENTATION:
            subtasks = self._decompose_documentation(task, depth)
        elif task.task_type == TaskType.ANALYSIS:
            subtasks = self._decompose_analysis(task, depth)
        elif task.task_type == TaskType.CODE_REVIEW:
            subtasks = self._decompose_code_review(task, depth)

        # Limit to max subtasks
        return subtasks[: context.max_subtasks]

    def _decompose_testing(self, task: Task, depth: int) -> list[Subtask]:
        """Decompose testing task into parallel test suites."""
        return [
            self._create_subtask(
                description="Unit tests",
                task_type=TaskType.TESTING,
                subtask_type=SubtaskType.IMPLEMENTATION,
                parent=task,
                depth=depth,
                effort_score=1.0,
                required_capabilities=["testing", "unit-testing"],
                tags=task.tags + ["unit"],
            ),
            self._create_subtask(
                description="Integration tests",
                task_type=TaskType.TESTING,
                subtask_type=SubtaskType.IMPLEMENTATION,
                parent=task,
                depth=depth,
                effort_score=1.5,
                required_capabilities=["testing", "integration-testing"],
                tags=task.tags + ["integration"],
            ),
            self._create_subtask(
                description="Edge case tests",
                task_type=TaskType.TESTING,
                subtask_type=SubtaskType.IMPLEMENTATION,
                parent=task,
                depth=depth,
                effort_score=0.8,
                required_capabilities=["testing", "edge-cases"],
                tags=task.tags + ["edge-cases"],
            ),
        ]

    def _decompose_documentation(self, task: Task, depth: int) -> list[Subtask]:
        """Decompose documentation task into parallel sections."""
        return [
            self._create_subtask(
                description="API documentation",
                task_type=TaskType.DOCUMENTATION,
                subtask_type=SubtaskType.IMPLEMENTATION,
                parent=task,
                depth=depth,
                effort_score=1.2,
                required_capabilities=["writing", "api-docs"],
                tags=task.tags + ["api"],
            ),
            self._create_subtask(
                description="Usage examples",
                task_type=TaskType.DOCUMENTATION,
                subtask_type=SubtaskType.IMPLEMENTATION,
                parent=task,
                depth=depth,
                effort_score=1.0,
                required_capabilities=["writing", "examples"],
                tags=task.tags + ["examples"],
            ),
            self._create_subtask(
                description="Architecture overview",
                task_type=TaskType.DOCUMENTATION,
                subtask_type=SubtaskType.IMPLEMENTATION,
                parent=task,
                depth=depth,
                effort_score=1.5,
                required_capabilities=["writing", "architecture"],
                tags=task.tags + ["architecture"],
            ),
        ]

    def _decompose_analysis(self, task: Task, depth: int) -> list[Subtask]:
        """Decompose analysis task into parallel analyses."""
        return [
            self._create_subtask(
                description="Static analysis",
                task_type=TaskType.ANALYSIS,
                subtask_type=SubtaskType.ANALYSIS,
                parent=task,
                depth=depth,
                effort_score=1.0,
                required_capabilities=["analysis", "static-analysis"],
                tags=task.tags + ["static"],
            ),
            self._create_subtask(
                description="Dynamic analysis",
                task_type=TaskType.ANALYSIS,
                subtask_type=SubtaskType.ANALYSIS,
                parent=task,
                depth=depth,
                effort_score=1.3,
                required_capabilities=["analysis", "dynamic-analysis"],
                tags=task.tags + ["dynamic"],
            ),
            self._create_subtask(
                description="Performance analysis",
                task_type=TaskType.ANALYSIS,
                subtask_type=SubtaskType.ANALYSIS,
                parent=task,
                depth=depth,
                effort_score=1.1,
                required_capabilities=["analysis", "performance"],
                tags=task.tags + ["performance"],
            ),
        ]

    def _decompose_code_review(self, task: Task, depth: int) -> list[Subtask]:
        """Decompose code review into parallel review aspects."""
        return [
            self._create_subtask(
                description="Logic and correctness review",
                task_type=TaskType.CODE_REVIEW,
                subtask_type=SubtaskType.ANALYSIS,
                parent=task,
                depth=depth,
                effort_score=1.2,
                required_capabilities=["review", "logic"],
                tags=task.tags + ["logic"],
            ),
            self._create_subtask(
                description="Style and conventions review",
                task_type=TaskType.CODE_REVIEW,
                subtask_type=SubtaskType.ANALYSIS,
                parent=task,
                depth=depth,
                effort_score=0.8,
                required_capabilities=["review", "style"],
                tags=task.tags + ["style"],
            ),
            self._create_subtask(
                description="Security review",
                task_type=TaskType.CODE_REVIEW,
                subtask_type=SubtaskType.ANALYSIS,
                parent=task,
                depth=depth,
                effort_score=1.5,
                required_capabilities=["review", "security"],
                tags=task.tags + ["security"],
            ),
        ]
