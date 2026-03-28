"""Main coordination engine for multi-agent task execution.

This module provides the CoordinationEngine facade that ties together
agent matching, workflow planning, and observability integration.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from omni.task.models import TaskGraph

from .agents import AgentRegistry
from .matcher import AgentAssignment, MatchConfidence, MatcherConfig, TaskMatcher
from .workflow import WorkflowOrchestrator, WorkflowPlan

logger = logging.getLogger(__name__)


class CoordinationObserver(Protocol):
    """Protocol for observing coordination events (integrates with P2-13)."""
    def on_agent_assigned(self, task_id: str, assignment: AgentAssignment) -> None: ...
    def on_workflow_planned(self, plan: WorkflowPlan) -> None: ...
    def on_step_started(self, step_id: str, task_ids: list[str]) -> None: ...
    def on_step_completed(self, step_id: str, results: dict[str, Any]) -> None: ...
    def on_escalation(self, task_id: str, from_agent: str, to_agent: str, reason: str) -> None: ...


@dataclass
class CoordinationResult:
    """Result of coordinating a TaskGraph for execution."""
    plan: WorkflowPlan
    assignments: dict[str, AgentAssignment]  # task_id → assignment
    task_graph: TaskGraph
    total_agents_used: int = 0
    estimated_total_cost: float = 0.0

    def __post_init__(self) -> None:
        agents_used = {a.agent_id for a in self.assignments.values()}
        self.total_agents_used = len(agents_used)


@dataclass
class CoordinationConfig:
    """Configuration for the coordination engine."""
    matcher_config: MatcherConfig = field(default_factory=MatcherConfig)
    enable_reviews: bool = True
    enable_specialist_routing: bool = True
    max_parallel_per_step: int = 5
    auto_escalate_on_failure: bool = True


class CoordinationEngine:
    """
    Main facade for multi-agent coordination.

    Usage:
        engine = CoordinationEngine()
        result = engine.coordinate(task_graph)
        # result.plan has the execution steps
        # result.assignments maps each task to an agent
    """

    def __init__(
        self,
        config: CoordinationConfig | None = None,
        registry: AgentRegistry | None = None,
        observers: list[CoordinationObserver] | None = None,
    ) -> None:
        self.config = config or CoordinationConfig()
        self.registry = registry or AgentRegistry()
        self.matcher = TaskMatcher(self.registry, self.config.matcher_config)
        self.orchestrator = WorkflowOrchestrator(
            enable_reviews=self.config.enable_reviews,
            enable_specialist_routing=self.config.enable_specialist_routing,
            max_parallel_per_step=self.config.max_parallel_per_step,
        )
        self._observers = observers or []

    def coordinate(
        self,
        task_graph: TaskGraph,
        plan_id: str | None = None,
    ) -> CoordinationResult:
        """
        Coordinate a TaskGraph for multi-agent execution.

        This is the main entry point:
        1. Matches each task to the best agent
        2. Creates a workflow plan with parallel/review steps
        3. Returns the plan + assignments for execution

        Args:
            task_graph: The decomposed task graph
            plan_id: Optional plan identifier

        Returns:
            CoordinationResult with plan and assignments
        """
        logger.info(
            f"Coordinating task graph '{task_graph.name}' "
            f"({task_graph.size} tasks, {task_graph.edge_count} edges)"
        )

        # 1. Match each task to an agent
        assignments: dict[str, AgentAssignment] = {}
        for task_id, task in task_graph.tasks.items():
            assignment = self.matcher.match(task)
            assignments[task_id] = assignment

            # Notify observers
            for obs in self._observers:
                obs.on_agent_assigned(task_id, assignment)

            logger.debug(
                f"Task '{task_id}' → {assignment.agent_id} "
                f"(confidence: {assignment.confidence.value}, "
                f"score: {assignment.score:.2f})"
            )

        # 2. Create workflow plan
        agent_id_map = {
            tid: a.agent_id for tid, a in assignments.items()
        }
        plan = self.orchestrator.create_plan(
            task_graph, agent_id_map, plan_id
        )

        # Notify observers
        for obs in self._observers:
            obs.on_workflow_planned(plan)

        # 3. Estimate total cost
        estimated_cost = sum(
            a.agent_profile.cost_per_million_tokens
            for a in assignments.values()
        )

        result = CoordinationResult(
            plan=plan,
            assignments=assignments,
            task_graph=task_graph,
            estimated_total_cost=estimated_cost,
        )

        logger.info(
            f"Coordination complete: {plan.total_steps} steps, "
            f"{result.total_agents_used} agents, "
            f"estimated cost: {estimated_cost:.2f}"
        )

        return result

    def handle_failure(
        self,
        task_id: str,
        current_agent_id: str,
        error: str,
    ) -> AgentAssignment | None:
        """
        Handle a task failure by escalating to a higher-tier agent.

        Returns a new assignment if escalation is possible, None if not.
        """
        if not self.config.auto_escalate_on_failure:
            return None

        escalation_target = self.registry.get_escalation_target(current_agent_id)
        if escalation_target is None:
            logger.warning(
                f"Task '{task_id}' failed on {current_agent_id}, "
                f"no escalation target available"
            )
            return None

        # Notify observers
        for obs in self._observers:
            obs.on_escalation(
                task_id, current_agent_id,
                escalation_target.agent_id, error
            )

        logger.info(
            f"Escalating task '{task_id}' from {current_agent_id} "
            f"to {escalation_target.agent_id}: {error}"
        )

        return AgentAssignment(
            agent_id=escalation_target.agent_id,
            agent_profile=escalation_target,
            confidence=MatchConfidence.FALLBACK,
            reasoning=f"Escalated from {current_agent_id} after failure: {error}",
            score=0.5,
            metadata={"escalation": True, "original_agent": current_agent_id, "error": error},
        )

    def register_observer(self, observer: CoordinationObserver) -> None:
        """Register an observer for coordination events."""
        self._observers.append(observer)

    def unregister_observer(self, observer: CoordinationObserver) -> None:
        """Unregister an observer."""
        self._observers = [o for o in self._observers if o is not observer]
