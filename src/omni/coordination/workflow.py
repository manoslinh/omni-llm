"""Workflow orchestration for multi-agent coordination.

This module converts TaskGraphs into WorkflowPlans with parallel
execution waves and review steps.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from omni.decomposition.models import Subtask
from omni.task.models import Task, TaskGraph


class WorkflowStepType(StrEnum):
    """Types of workflow execution steps."""
    SEQUENTIAL = "sequential"    # Execute tasks in dependency order
    PARALLEL = "parallel"        # Execute independent tasks concurrently
    HANDOFF = "handoff"          # Agent A passes result to Agent B
    REVIEW = "review"            # Implementer → Reviewer (one tier above)
    SPECIALIST = "specialist"    # Route to specialist for specific content
    ESCALATION = "escalation"    # Failed task → higher-tier agent


@dataclass
class WorkflowStep:
    """A single step in a workflow execution plan."""
    step_id: str
    step_type: WorkflowStepType
    task_ids: list[str]                    # Tasks in this step
    agent_assignments: dict[str, str]      # task_id → agent_id
    depends_on: list[str] = field(default_factory=list)  # Previous step IDs
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_parallel(self) -> bool:
        return self.step_type == WorkflowStepType.PARALLEL or len(self.task_ids) > 1


@dataclass
class WorkflowPlan:
    """
    Complete execution plan derived from a TaskGraph.

    A WorkflowPlan is a list of WorkflowSteps that respects
    the dependency graph while maximizing parallelism.
    """
    plan_id: str
    steps: list[WorkflowStep]
    task_graph_name: str
    total_steps: int = 0
    parallel_steps: int = 0
    review_steps: int = 0

    def __post_init__(self) -> None:
        self.total_steps = len(self.steps)
        self.parallel_steps = sum(1 for s in self.steps if s.is_parallel)
        self.review_steps = sum(
            1 for s in self.steps if s.step_type == WorkflowStepType.REVIEW
        )

    def get_step(self, step_id: str) -> WorkflowStep:
        """Get a step by ID."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        raise KeyError(f"Step '{step_id}' not found")

    def get_execution_order(self) -> list[list[str]]:
        """
        Get steps grouped by execution wave (for parallel scheduling).

        Returns:
            List of lists — each inner list contains step IDs
            that can execute in parallel.
        """
        waves: list[list[str]] = []
        completed: set[str] = set()

        remaining = {s.step_id for s in self.steps}
        step_map = {s.step_id: s for s in self.steps}

        while remaining:
            # Find steps whose dependencies are all completed
            ready = [
                sid for sid in remaining
                if all(dep in completed for dep in step_map[sid].depends_on)
            ]
            if not ready:
                # Should not happen in a valid plan
                break
            waves.append(ready)
            completed.update(ready)
            remaining -= set(ready)

        return waves

    def summary(self) -> dict[str, Any]:
        """Get a plan summary."""
        return {
            "plan_id": self.plan_id,
            "total_steps": self.total_steps,
            "parallel_steps": self.parallel_steps,
            "review_steps": self.review_steps,
            "execution_waves": len(self.get_execution_order()),
        }


class WorkflowOrchestrator:
    """
    Converts TaskGraphs into WorkflowPlans.

    The orchestrator:
    1. Traverses the TaskGraph topologically
    2. Groups independent tasks for parallel execution
    3. Inserts review steps after implementation tasks
    4. Handles specialist routing (Visual for images, Reader for long docs)
    5. Plans escalation paths for potential failures
    """

    def __init__(
        self,
        enable_reviews: bool = True,
        enable_specialist_routing: bool = True,
        max_parallel_per_step: int = 5,
    ) -> None:
        self.enable_reviews = enable_reviews
        self.enable_specialist_routing = enable_specialist_routing
        self.max_parallel_per_step = max_parallel_per_step

    def create_plan(
        self,
        task_graph: TaskGraph,
        agent_assignments: dict[str, str],  # task_id → agent_id
        plan_id: str | None = None,
    ) -> WorkflowPlan:
        """
        Create a WorkflowPlan from a TaskGraph and agent assignments.

        Args:
            task_graph: The decomposed task graph
            agent_assignments: Pre-computed agent assignments
            plan_id: Optional plan ID (auto-generated if None)

        Returns:
            WorkflowPlan ready for execution
        """
        import uuid
        pid = plan_id or f"plan-{uuid.uuid4().hex[:8]}"

        steps: list[WorkflowStep] = []
        step_counter = 0

        # Get execution waves from the graph
        waves = self._compute_execution_waves(task_graph)

        for wave_idx, task_ids in enumerate(waves):
            # Determine step type based on wave contents
            if len(task_ids) == 1:
                task_id = task_ids[0]
                task = task_graph.get_task(task_id)
                step_type = self._classify_single_task(task, agent_assignments.get(task_id, ""))
            else:
                step_type = WorkflowStepType.PARALLEL

            # Create the execution step
            step = WorkflowStep(
                step_id=f"step-{step_counter:03d}",
                step_type=step_type,
                task_ids=task_ids,
                agent_assignments={
                    tid: agent_assignments.get(tid, "coder")
                    for tid in task_ids
                },
                depends_on=[f"step-{step_counter - 1:03d}"] if wave_idx > 0 else [],
            )
            steps.append(step)
            step_counter += 1

            # Insert review steps if enabled
            if self.enable_reviews:
                review_task_ids = self._identify_review_candidates(
                    task_ids, task_graph, agent_assignments
                )
                if review_task_ids:
                    review_step = WorkflowStep(
                        step_id=f"step-{step_counter:03d}",
                        step_type=WorkflowStepType.REVIEW,
                        task_ids=review_task_ids,
                        agent_assignments={
                            tid: self._get_reviewer_agent(tid, agent_assignments)
                            for tid in review_task_ids
                        },
                        depends_on=[step.step_id],
                    )
                    steps.append(review_step)
                    step_counter += 1

        return WorkflowPlan(
            plan_id=pid,
            steps=steps,
            task_graph_name=task_graph.name,
        )

    def _compute_execution_waves(self, task_graph: TaskGraph) -> list[list[str]]:
        """
        Compute parallel execution waves from the task graph.

        Tasks with no unresolved dependencies can execute in the same wave.
        Respects max_parallel_per_step limit.
        """
        waves: list[list[str]] = []
        completed: set[str] = set()

        remaining = set(task_graph.tasks.keys())

        while remaining:
            # Find tasks whose dependencies are all completed
            ready = [
                tid for tid in remaining
                if all(
                    dep in completed
                    for dep in task_graph.tasks[tid].dependencies
                    if dep in task_graph.tasks
                )
            ]

            if not ready:
                # Cycle or error — add remaining as individual steps
                for tid in remaining:
                    waves.append([tid])
                break

            # Respect max parallel limit
            for i in range(0, len(ready), self.max_parallel_per_step):
                waves.append(ready[i:i + self.max_parallel_per_step])

            completed.update(ready)
            remaining -= set(ready)

        return waves

    def _classify_single_task(
        self,
        task: Task,
        agent_id: str,
    ) -> WorkflowStepType:
        """Classify a single-task step."""
        if isinstance(task, Subtask):
            from omni.decomposition.models import SubtaskType
            if task.subtask_type == SubtaskType.IMPLEMENTATION:
                return WorkflowStepType.SEQUENTIAL
            elif task.subtask_type == SubtaskType.VALIDATION:
                return WorkflowStepType.REVIEW
        return WorkflowStepType.SEQUENTIAL

    def _identify_review_candidates(
        self,
        task_ids: list[str],
        task_graph: TaskGraph,
        agent_assignments: dict[str, str],
    ) -> list[str]:
        """
        Identify tasks that should have a review step.

        Review is valuable for:
        - Implementation tasks done by Intern or Coder
        - Tasks with high complexity
        """
        candidates: list[str] = []
        for tid in task_ids:
            task = task_graph.tasks.get(tid)
            if task is None:
                continue

            agent_id = agent_assignments.get(tid, "")

            # Review intern and coder work
            if agent_id in ("intern", "coder"):
                candidates.append(tid)
                continue

            # Review high-complexity tasks
            complexity = task.effective_complexity
            if complexity.overall_score >= 7.0:
                candidates.append(tid)

        return candidates

    def _get_reviewer_agent(
        self,
        task_id: str,
        agent_assignments: dict[str, str],
    ) -> str:
        """
        Get the reviewer agent for a task.

        Review rule: one tier above the implementer.
        """
        implementer = agent_assignments.get(task_id, "coder")
        escalation_map = {
            "intern": "coder",
            "coder": "reader",   # or thinker for complex tasks
            "reader": "thinker",
            "visual": "thinker",
            "thinker": "thinker",  # Self-review (no higher tier)
        }
        return escalation_map.get(implementer, "thinker")
