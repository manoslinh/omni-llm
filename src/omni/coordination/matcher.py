"""Task matching for multi-agent coordination.

This module implements the TaskMatcher that matches tasks/subtasks
to the best available agent based on capabilities, complexity, cost,
and priority.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from omni.decomposition.models import Subtask
from omni.task.models import Task

from .agents import AgentCapability, AgentProfile, AgentRegistry


class MatchConfidence(StrEnum):
    """Confidence level of an agent match."""
    EXACT = "exact"          # Perfect capability + tier match
    STRONG = "strong"        # Capability match, tier mismatch within 1
    WEAK = "weak"            # Partial capability match
    FALLBACK = "fallback"    # No good match, using fallback


@dataclass
class AgentAssignment:
    """Result of matching a task to an agent."""
    agent_id: str
    agent_profile: AgentProfile
    confidence: MatchConfidence
    reasoning: str
    score: float = 0.0  # 0.0 to 1.0, higher is better
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatcherConfig:
    """Configuration for the task matcher."""
    # Weight for each scoring factor (must sum to 1.0)
    capability_weight: float = 0.40
    complexity_weight: float = 0.25
    cost_weight: float = 0.20
    priority_weight: float = 0.15

    # Whether to prefer cheaper agents when scores are close
    cost_optimization: bool = True

    # Threshold below which we escalate rather than assign
    min_acceptable_score: float = 0.3

    def __post_init__(self) -> None:
        total = (self.capability_weight + self.complexity_weight +
                 self.cost_weight + self.priority_weight)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total:.3f}")


class TaskMatcher:
    """
    Matches tasks/subtasks to the best available agent.

    Scoring algorithm:
    1. Capability match  (40%) — does the agent have required capabilities?
    2. Complexity fit    (25%) — is the agent's tier appropriate for the complexity?
    3. Cost efficiency   (20%) — is this the cheapest capable agent?
    4. Priority/seniority(15%) — agent priority for tiebreaking
    """

    def __init__(
        self,
        registry: AgentRegistry,
        config: MatcherConfig | None = None,
    ) -> None:
        self.registry = registry
        self.config = config or MatcherConfig()

    def match(
        self,
        task: Task,
        required_capabilities: set[AgentCapability] | None = None,
    ) -> AgentAssignment:
        """
        Find the best agent for a task.

        Args:
            task: The task to assign (may be a Subtask)
            required_capabilities: Override for required capabilities
                (if None, extracted from Subtask.required_capabilities)

        Returns:
            AgentAssignment with the best agent and reasoning
        """
        # Extract required capabilities
        caps = required_capabilities or self._extract_capabilities(task)

        # Get complexity score
        complexity = task.effective_complexity
        complexity_score = complexity.overall_score

        # Score all agents
        scored_agents: list[tuple[AgentProfile, float, str]] = []
        for agent in self.registry.agents.values():
            score, reasoning = self._score_agent(agent, caps, complexity_score, task)
            scored_agents.append((agent, score, reasoning))

        # Sort by score descending
        scored_agents.sort(key=lambda x: x[1], reverse=True)

        if not scored_agents:
            # No agents registered — should not happen with defaults
            return self._fallback_assignment(task)

        best_agent, best_score, best_reasoning = scored_agents[0]

        # Determine confidence
        if best_score >= 0.8:
            confidence = MatchConfidence.EXACT
        elif best_score >= 0.6:
            confidence = MatchConfidence.STRONG
        elif best_score >= self.config.min_acceptable_score:
            confidence = MatchConfidence.WEAK
        else:
            # Score too low — consider escalation
            escalation = self.registry.get_escalation_target(best_agent.agent_id)
            if escalation and escalation.agent_id != best_agent.agent_id:
                esc_score, esc_reasoning = self._score_agent(
                    escalation, caps, complexity_score, task
                )
                if esc_score > best_score:
                    return AgentAssignment(
                        agent_id=escalation.agent_id,
                        agent_profile=escalation,
                        confidence=MatchConfidence.FALLBACK,
                        reasoning=f"Escalated from {best_agent.agent_id}: {esc_reasoning}",
                        score=esc_score,
                    )
            confidence = MatchConfidence.FALLBACK

        return AgentAssignment(
            agent_id=best_agent.agent_id,
            agent_profile=best_agent,
            confidence=confidence,
            reasoning=best_reasoning,
            score=best_score,
            metadata={
                "complexity_score": complexity_score,
                "required_capabilities": [c.value for c in caps],
                "alternatives": [
                    {"agent_id": a.agent_id, "score": s}
                    for a, s, _ in scored_agents[1:3]  # Top 3 alternatives
                ],
            },
        )

    def match_batch(
        self,
        tasks: list[Task],
    ) -> dict[str, AgentAssignment]:
        """
        Match multiple tasks to agents in one call.

        Returns:
            Dict mapping task_id → AgentAssignment
        """
        return {task.task_id: self.match(task) for task in tasks}

    def _score_agent(
        self,
        agent: AgentProfile,
        required_caps: set[AgentCapability],
        complexity_score: float,
        task: Task,
    ) -> tuple[float, str]:
        """
        Score an agent for a task. Returns (score, reasoning).

        Score is 0.0 to 1.0, higher is better.
        """
        reasons: list[str] = []

        # 1. Capability score (0 or 1, with partial credit)
        if required_caps:
            matched = required_caps & agent.capabilities
            cap_score = len(matched) / len(required_caps)
            if cap_score == 1.0:
                reasons.append("Has all required capabilities")
            elif cap_score > 0:
                reasons.append(f"Has {len(matched)}/{len(required_caps)} required capabilities")
            else:
                reasons.append("Missing required capabilities")
        else:
            cap_score = 1.0  # No specific requirements

        # 2. Complexity fit score
        if agent.can_handle_complexity(complexity_score):
            # Prefer agents whose max is closest to the complexity
            # (not overqualified = cheaper)
            if agent.max_complexity > 0:
                fit_ratio = complexity_score / agent.max_complexity
                # Sweet spot: 0.3 to 0.9 of max capacity
                if 0.3 <= fit_ratio <= 0.9:
                    complexity_fit = 1.0
                elif fit_ratio < 0.3:
                    complexity_fit = 0.7  # Overqualified
                else:
                    complexity_fit = 0.8  # Near capacity
            else:
                complexity_fit = 0.5
            reasons.append(f"Can handle complexity {complexity_score:.1f} (max: {agent.max_complexity})")
        else:
            complexity_fit = 0.0
            reasons.append(f"Cannot handle complexity {complexity_score:.1f} (max: {agent.max_complexity})")

        # 3. Cost efficiency (normalize to 0-1, lower cost = higher score)
        max_cost = max(
            (a.cost_per_million_tokens for a in self.registry.agents.values()),
            default=1.0
        )
        if max_cost > 0:
            cost_score = 1.0 - (agent.cost_per_million_tokens / max_cost)
        else:
            cost_score = 1.0

        # 4. Priority score (normalize to 0-1)
        max_priority = max(
            (a.priority for a in self.registry.agents.values()),
            default=1
        )
        priority_score = agent.priority / max_priority if max_priority > 0 else 1.0

        # Weighted total
        total = (
            cap_score * self.config.capability_weight
            + complexity_fit * self.config.complexity_weight
            + cost_score * self.config.cost_weight
            + priority_score * self.config.priority_weight
        )

        # Penalty for capability mismatch
        if cap_score < 0.5:
            total *= 0.5  # Heavy penalty

        reasoning = f"[{agent.display_name}] score={total:.2f}: {'; '.join(reasons)}"
        return round(total, 4), reasoning

    def _extract_capabilities(self, task: Task) -> set[AgentCapability]:
        """
        Extract required capabilities from a task.

        Uses Subtask.required_capabilities if available, otherwise
        infers from task type and context.
        """
        caps: set[AgentCapability] = set()

        # If it's a Subtask with explicit capabilities, use those
        if isinstance(task, Subtask) and task.required_capabilities:
            for cap_str in task.required_capabilities:
                try:
                    caps.add(AgentCapability(cap_str))
                except ValueError:
                    pass  # Unknown capability string

        if caps:
            return caps

        # Infer from task type
        task_type_str = str(task.task_type)
        type_to_caps: dict[str, set[AgentCapability]] = {
            "code_generation": {AgentCapability.CODE_GENERATION},
            "code_review": {AgentCapability.CODE_REVIEW},
            "testing": {AgentCapability.TESTING},
            "refactoring": {AgentCapability.REFACTORING},
            "documentation": {AgentCapability.DOCUMENTATION},
            "analysis": {AgentCapability.CODE_REVIEW},
            "configuration": {AgentCapability.FORMATTING},
        }
        caps = type_to_caps.get(task_type_str, set())

        # Check context for image references
        if task.context:
            context_str = str(task.context).lower()
            if any(kw in context_str for kw in ["screenshot", "image", "png", "jpg", "visual"]):
                caps.add(AgentCapability.VISION)
            if any(kw in context_str for kw in ["long", "large", "explore", "codebase"]):
                caps.add(AgentCapability.LONG_CONTEXT)

        return caps

    def _fallback_assignment(self, task: Task) -> AgentAssignment:
        """Create a fallback assignment when no good match is found."""
        # Default to Coder as the safest fallback
        fallback = self.registry.agents.get("coder")
        if not fallback:
            # Should never happen with default agents
            fallback = list(self.registry.agents.values())[0]

        return AgentAssignment(
            agent_id=fallback.agent_id,
            agent_profile=fallback,
            confidence=MatchConfidence.FALLBACK,
            reasoning="No strong match found, using fallback agent",
            score=0.1,
        )
