# P2-14: Multi-Agent Coordination Engine — Architecture

## Problem Statement

Omni-LLM currently decomposes tasks into a `TaskGraph` (P2-08) and analyzes their complexity (P2-09), but has no mechanism to **assign subtasks to specialized agents** based on their characteristics. Every task goes through the same execution path regardless of whether it needs a cheap fast model for formatting or a powerful reasoning model for architecture decisions.

We need a coordination layer that:
1. Models specialized agents with distinct capabilities, costs, and strengths
2. Matches subtasks to the best agent using complexity, type, and required capabilities
3. Handles inter-agent handoffs (sequential, parallel, review workflows)
4. Integrates with the existing `TaskGraph`, `ComplexityEstimate`, and `ModelRouter`
5. Emits events for observability (P2-13) and drives the parallel execution engine (P2-11)

## Design Goals

| Goal | Rationale |
|------|-----------|
| **Declarative agent registry** | Agents are data, not hardcoded — add/remove without touching engine code |
| **Capability-based routing** | Route by what an agent *can do*, not just by name |
| **Complexity-aware assignment** | Use `ComplexityEstimate.tier` and `Subtask.required_capabilities` |
| **Protocol-driven workflows** | Support sequential handoff, parallel fan-out, review chains |
| **Non-disruptive integration** | Wrap existing `ModelRouter`, don't replace it |
| **Observable** | Every coordination decision emits an event for P2-13 |
| **Testable** | Pure-Python data models, mock-friendly interfaces |

## Existing Components (Integration Points)

```
┌─────────────────────────────────────────────────────────────────┐
│                      Omni-LLM Architecture                      │
│                                                                  │
│  ┌──────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │ P2-08: Task  │───▶│ P2-09: Complexity │───▶│ P2-10: Graph  │  │
│  │ Decomposition│    │ Analyzer          │    │ Visualizer    │  │
│  └──────┬───────┘    └────────┬──────────┘    └───────────────┘  │
│         │                     │                                   │
│         ▼                     ▼                                   │
│  ┌──────────────────────────────────────┐                        │
│  │          TaskGraph + Subtask          │                        │
│  │  ┌─────────────────────────────────┐ │                        │
│  │  │ Subtask.required_capabilities   │ │                        │
│  │  │ ComplexityEstimate.tier         │ │◀── KEY INPUTS         │
│  │  │ Subtask.subtask_type            │ │                        │
│  │  │ Subtask.effort_score            │ │                        │
│  │  └─────────────────────────────────┘ │                        │
│  └──────────────────┬───────────────────┘                        │
│                     │                                             │
│                     ▼                                             │
│  ┌──────────────────────────────────────┐                        │
│  │    ★ P2-14: Coordination Engine ★    │ ◀── NEW                │
│  │                                      │                        │
│  │  ┌────────┐  ┌────────┐  ┌────────┐ │                        │
│  │  │ Agent  │  │ Task   │  │Workflow│ │                        │
│  │  │Registry│  │Matcher │  │Orchestr│ │                        │
│  │  └────┬───┘  └───┬────┘  └───┬────┘ │                        │
│  │       │          │           │       │                        │
│  │       ▼          ▼           ▼       │                        │
│  │  ┌─────────────────────────────────┐ │                        │
│  │  │      CoordinationContext        │ │                        │
│  │  └─────────────────────────────────┘ │                        │
│  └──────────────────┬───────────────────┘                        │
│                     │                                             │
│         ┌───────────┼───────────┐                                │
│         ▼           ▼           ▼                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                         │
│  │ P2-11:   │ │ P2-12:   │ │ P2-13:   │                         │
│  │ Parallel │ │ Model    │ │ Observ-  │                         │
│  │ Execution│ │ Router   │ │ ability  │                         │
│  └──────────┘ └──────────┘ └──────────┘                         │
└─────────────────────────────────────────────────────────────────┘
```

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                    Multi-Agent Coordination Engine                   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     AgentRegistry                             │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ ┌─────┐ │   │
│  │  │  Intern   │ │  Coder   │ │  Reader  │ │ Visual │ │Think│ │   │
│  │  │  (T1)     │ │  (T2)    │ │  (T3)    │ │  (T4)  │ │(T5) │ │   │
│  │  │ mimo-flash│ │deepseek  │ │ kimi-k2.5│ │mimo-omni│ │mimo │ │   │
│  │  │ trivial   │ │ coding   │ │ long-ctx │ │ vision │ │reason│ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └────────┘ └─────┘ │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                              │                                       │
│  ┌──────────────────────────▼───────────────────────────────────┐   │
│  │                     TaskMatcher                               │   │
│  │                                                               │   │
│  │  Input: Subtask + ComplexityEstimate + required_capabilities │   │
│  │  Output: AgentAssignment (agent_id + confidence + reasoning) │   │
│  │                                                               │   │
│  │  Rules:                                                       │   │
│  │  1. Capability match (required_capabilities ⊆ agent.caps)    │   │
│  │  2. Tier match (complexity.tier → agent.tier)                │   │
│  │  3. Subtask type affinity (implementation→coder, etc.)        │   │
│  │  4. Cost optimization (cheapest capable agent wins)           │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                              │                                       │
│  ┌──────────────────────────▼───────────────────────────────────┐   │
│  │                   WorkflowOrchestrator                         │   │
│  │                                                               │   │
│  │  ┌─────────────────┐  ┌──────────────────┐  ┌────────────┐  │   │
│  │  │ SequentialStep  │  │ ParallelFanOut   │  │ReviewChain │  │   │
│  │  │ A → B → C       │  │ [A, B, C] → join │  │ Impl→Review│  │   │
│  │  └─────────────────┘  └──────────────────┘  └────────────┘  │   │
│  │                                                               │   │
│  │  Composes TaskGraph edges into executable workflows           │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                              │                                       │
│  ┌──────────────────────────▼───────────────────────────────────┐   │
│  │                  CoordinationContext                           │   │
│  │                                                               │   │
│  │  • agent_assignments: dict[task_id → AgentAssignment]         │   │
│  │  • workflow_plan: list[WorkflowStep]                          │   │
│  │  • shared_state: dict (inter-agent result passing)            │   │
│  │  • event_bus: → emits to P2-13 observability                  │   │
│  └──────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

## Component Design

### 1. AgentRegistry

The central registry of available agents. Each agent is a declarative data model — no logic, just metadata.

```python
# src/omni/coordination/agents.py

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AgentTier(StrEnum):
    """Agent capability tiers, mapped from ComplexityEstimate.tier."""
    INTERN = "intern"      # T1: trivial work
    CODER = "coder"        # T2: standard coding
    READER = "reader"      # T3: long-context specialist
    VISUAL = "visual"      # T4: multimodal specialist
    THINKER = "thinker"    # T5: complex reasoning


class AgentCapability(StrEnum):
    """Capabilities that agents may possess."""
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    TESTING = "testing"
    FORMATTING = "formatting"
    EXTRACTION = "extraction"
    LONG_CONTEXT = "long_context"
    VISION = "vision"
    IMAGE_ANALYSIS = "image_analysis"
    ARCHITECTURE = "architecture"
    REASONING = "reasoning"
    DEBUGGING = "debugging"
    DOCUMENTATION = "documentation"
    REFACTORING = "refactoring"


@dataclass
class AgentProfile:
    """
    Declarative description of a specialized agent.

    This is pure data — no behavior. The coordination engine uses
    these profiles to match tasks to agents.
    """
    agent_id: str                          # e.g., "intern", "coder"
    tier: AgentTier                        # Capability tier
    model_id: str                          # e.g., "mimo/mimo-v2-flash"
    display_name: str                      # Human-readable name
    capabilities: set[AgentCapability]     # What this agent can do
    max_complexity: float = 5.0            # Max ComplexityEstimate.overall_score
    max_context_tokens: int = 8000         # Max input tokens
    cost_per_million_tokens: float = 0.0   # Relative cost indicator
    priority: int = 0                      # Tiebreaker (higher wins)
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.max_complexity <= 10.0:
            raise ValueError(f"max_complexity must be 0-10, got {self.max_complexity}")
        if self.max_context_tokens < 0:
            raise ValueError("max_context_tokens must be non-negative")

    def can_handle(self, capability: AgentCapability) -> bool:
        """Check if this agent has a specific capability."""
        return capability in self.capabilities

    def can_handle_complexity(self, score: float) -> bool:
        """Check if this agent can handle a given complexity score."""
        return score <= self.max_complexity


# ── Default Agent Definitions (from AGENTS.md) ──────────────────

DEFAULT_AGENTS: dict[str, AgentProfile] = {
    "intern": AgentProfile(
        agent_id="intern",
        tier=AgentTier.INTERN,
        model_id="mimo/mimo-v2-flash",
        display_name="Intern (T1)",
        capabilities={
            AgentCapability.FORMATTING,
            AgentCapability.EXTRACTION,
            AgentCapability.DOCUMENTATION,
        },
        max_complexity=3.0,
        max_context_tokens=8000,
        cost_per_million_tokens=0.0,
        priority=1,
        description="Trivial work: formatting, extraction, boilerplate",
    ),
    "coder": AgentProfile(
        agent_id="coder",
        tier=AgentTier.CODER,
        model_id="deepseek/deepseek-chat",
        display_name="Coder (T2)",
        capabilities={
            AgentCapability.CODE_GENERATION,
            AgentCapability.CODE_REVIEW,
            AgentCapability.TESTING,
            AgentCapability.DEBUGGING,
            AgentCapability.REFACTORING,
            AgentCapability.FORMATTING,
        },
        max_complexity=5.5,
        max_context_tokens=32000,
        cost_per_million_tokens=0.14,
        priority=5,
        description="Coding, debugging, scripts, tests",
    ),
    "reader": AgentProfile(
        agent_id="reader",
        tier=AgentTier.READER,
        model_id="moonshot/kimi-k2.5",
        display_name="Reader (T3)",
        capabilities={
            AgentCapability.LONG_CONTEXT,
            AgentCapability.CODE_REVIEW,
            AgentCapability.DOCUMENTATION,
            AgentCapability.EXTRACTION,
            AgentCapability.ANALYSIS if hasattr(AgentCapability, 'ANALYSIS') else AgentCapability.CODE_REVIEW,
        },
        max_complexity=7.5,
        max_context_tokens=200000,
        cost_per_million_tokens=0.55,
        priority=3,
        description="Long-context reading, codebase exploration, large document analysis",
    ),
    "visual": AgentProfile(
        agent_id="visual",
        tier=AgentTier.VISUAL,
        model_id="mimo/mimo-v2-omni",
        display_name="Visual (T4)",
        capabilities={
            AgentCapability.VISION,
            AgentCapability.IMAGE_ANALYSIS,
            AgentCapability.CODE_REVIEW,
        },
        max_complexity=5.0,
        max_context_tokens=32000,
        cost_per_million_tokens=0.0,
        priority=4,
        description="Screenshots, images, multimodal input",
    ),
    "thinker": AgentProfile(
        agent_id="thinker",
        tier=AgentTier.THINKER,
        model_id="mimo/mimo-v2-pro",
        display_name="Thinker (T5)",
        capabilities={
            AgentCapability.ARCHITECTURE,
            AgentCapability.REASONING,
            AgentCapability.CODE_REVIEW,
            AgentCapability.REFACTORING,
            AgentCapability.DEBUGGING,
        },
        max_complexity=10.0,
        max_context_tokens=64000,
        cost_per_million_tokens=1.0,
        priority=10,
        description="Architecture, complex reasoning, ambiguous problems, escalation target",
    ),
}


@dataclass
class AgentRegistry:
    """
    Registry of available agents for task coordination.

    Supports registration, lookup by capability/tier, and filtering
    by complexity limits.
    """
    agents: dict[str, AgentProfile] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.agents:
            self.agents = DEFAULT_AGENTS.copy()

    def register(self, agent: AgentProfile) -> None:
        """Register an agent profile."""
        if agent.agent_id in self.agents:
            raise ValueError(f"Agent '{agent.agent_id}' already registered")
        self.agents[agent.agent_id] = agent

    def unregister(self, agent_id: str) -> AgentProfile:
        """Unregister an agent."""
        if agent_id not in self.agents:
            raise KeyError(f"Agent '{agent_id}' not found")
        return self.agents.pop(agent_id)

    def get(self, agent_id: str) -> AgentProfile:
        """Get an agent by ID."""
        if agent_id not in self.agents:
            raise KeyError(f"Agent '{agent_id}' not found")
        return self.agents[agent_id]

    def get_by_tier(self, tier: AgentTier) -> list[AgentProfile]:
        """Get all agents at a given tier."""
        return [a for a in self.agents.values() if a.tier == tier]

    def get_by_capability(
        self,
        capability: AgentCapability,
        max_complexity: float | None = None,
    ) -> list[AgentProfile]:
        """Get agents with a specific capability, optionally filtered by complexity."""
        results = [
            a for a in self.agents.values()
            if a.can_handle(capability)
        ]
        if max_complexity is not None:
            results = [a for a in results if a.can_handle_complexity(max_complexity)]
        # Sort by priority (higher first), then cost (lower first)
        results.sort(key=lambda a: (-a.priority, a.cost_per_million_tokens))
        return results

    def get_escalation_target(self, current_agent_id: str) -> AgentProfile | None:
        """
        Get the next-tier agent for escalation.

        Escalation chain: intern → coder → reader → thinker
        (Visual is a specialist, not in escalation chain)
        """
        escalation_order = ["intern", "coder", "reader", "thinker"]
        try:
            current_idx = escalation_order.index(current_agent_id)
        except ValueError:
            # Specialist or unknown — escalate to thinker
            return self.agents.get("thinker")

        if current_idx + 1 < len(escalation_order):
            next_id = escalation_order[current_idx + 1]
            return self.agents.get(next_id)
        return None  # Already at top

    def summary(self) -> dict[str, Any]:
        """Get a summary of registered agents."""
        return {
            agent_id: {
                "tier": agent.tier.value,
                "model": agent.model_id,
                "capabilities": [c.value for c in agent.capabilities],
                "max_complexity": agent.max_complexity,
            }
            for agent_id, agent in self.agents.items()
        }
```

### 2. TaskMatcher

Matches subtasks to the best agent based on multiple signals.

```python
# src/omni/coordination/matcher.py

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from omni.task.models import ComplexityEstimate, Task
from omni.decomposition.models import Subtask

from .agents import AgentCapability, AgentProfile, AgentRegistry, AgentTier


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
                reasons.append(f"Has all required capabilities")
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
```

### 3. WorkflowOrchestrator

Converts `TaskGraph` dependency edges into executable workflow patterns.

```python
# src/omni/coordination/workflow.py

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from omni.task.models import Task, TaskGraph, TaskStatus


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
```

### 4. CoordinationEngine (Main Facade)

The top-level engine that ties everything together.

```python
# src/omni/coordination/engine.py

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from omni.task.models import Task, TaskGraph

from .agents import AgentRegistry
from .matcher import AgentAssignment, MatcherConfig, TaskMatcher
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
            confidence="fallback",
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
```

## Integration Plan

### With P2-08 (Task Decomposition Engine)

```
DecompositionResult.task_graph
        │
        ▼
CoordinationEngine.coordinate(task_graph)
```

The `CoordinationEngine` takes a `TaskGraph` directly from `TaskDecompositionEngine.decompose()`. No adapter needed — the `Subtask` model already has `required_capabilities` and `effort_score`.

### With P2-09 (Complexity Analyzer)

```
ComplexityEstimate.overall_score → TaskMatcher scoring
ComplexityEstimate.tier → AgentTier matching
```

The `ComplexityEstimate.tier` property already returns `"intern"`, `"coder"`, `"reader"`, or `"thinker"` — directly maps to `AgentTier`.

### With P2-11 (Parallel Execution Engine)

```
WorkflowPlan.get_execution_waves()
        │
        ▼
ParallelExecutionEngine.schedule(wave)
```

The `WorkflowPlan` produces execution waves (`list[list[step_id]]`) — each wave is a batch of parallelizable steps. The parallel execution engine consumes these waves.

### With P2-12 (LLM Integration / Model Router)

```
AgentAssignment.agent_profile.model_id
        │
        ▼
ModelRouter.complete(messages, model=agent.model_id)
```

Each agent profile has a `model_id` that maps directly to the router's model selection. The coordination engine doesn't call models itself — it produces assignments that the execution layer uses to configure the router.

### With P2-13 (Observability)

```
CoordinationObserver protocol
        │
        ▼
EventBus → metrics, logs, live visualization
```

The `CoordinationObserver` protocol emits events at every decision point. P2-13 implements this protocol to provide real-time visibility.

## API Design

### Public Interface Summary

```python
# ── Quick Start ─────────────────────────────────────────────────

from omni.coordination import (
    CoordinationEngine,
    CoordinationConfig,
    AgentRegistry,
    AgentProfile,
)

# Use defaults
engine = CoordinationEngine()
result = engine.coordinate(task_graph)

# Access results
for step in result.plan.steps:
    print(f"{step.step_id}: {step.step_type.value} "
          f"({len(step.task_ids)} tasks)")
    for task_id in step.task_ids:
        agent = result.assignments[task_id]
        print(f"  {task_id} → {agent.agent_id} ({agent.confidence.value})")

# ── Custom Configuration ────────────────────────────────────────

config = CoordinationConfig(
    enable_reviews=True,
    max_parallel_per_step=3,
    matcher_config=MatcherConfig(
        cost_optimization=True,
        min_acceptable_score=0.4,
    ),
)

engine = CoordinationEngine(config=config)

# ── Custom Agents ───────────────────────────────────────────────

registry = AgentRegistry()
registry.register(AgentProfile(
    agent_id="data-specialist",
    tier=AgentTier.READER,
    model_id="moonshot/kimi-k2.5",
    display_name="Data Specialist",
    capabilities={AgentCapability.LONG_CONTEXT, AgentCapability.EXTRACTION},
    max_complexity=6.0,
))

engine = CoordinationEngine(registry=registry)

# ── Observability Integration ───────────────────────────────────

class MyObserver:
    def on_agent_assigned(self, task_id, assignment):
        print(f"Assigned {task_id} to {assignment.agent_id}")

    def on_workflow_planned(self, plan):
        print(f"Plan ready: {plan.total_steps} steps")

    # ... implement other protocol methods

engine = CoordinationEngine(observers=[MyObserver()])
```

## File Structure

```
src/omni/coordination/
├── __init__.py          # Public API exports
├── agents.py            # AgentProfile, AgentRegistry, DEFAULT_AGENTS
├── matcher.py           # TaskMatcher, AgentAssignment, MatcherConfig
├── workflow.py          # WorkflowOrchestrator, WorkflowPlan, WorkflowStep
└── engine.py            # CoordinationEngine, CoordinationResult, CoordinationConfig

tests/
├── test_agents.py       # AgentProfile validation, Registry operations
├── test_matcher.py      # Matching algorithm, scoring, edge cases
├── test_workflow.py     # Plan generation, wave computation, review insertion
└── test_coordination_engine.py  # End-to-end coordination

docs/
└── P2-14-ARCHITECTURE.md  # This document
```

## Implementation Roadmap

### Phase 1: Core Models (Agent, Matcher) — ~2 hours

| Step | File | Description |
|------|------|-------------|
| 1.1 | `agents.py` | `AgentTier`, `AgentCapability`, `AgentProfile` dataclasses |
| 1.2 | `agents.py` | `AgentRegistry` with register/unregister/lookup |
| 1.3 | `agents.py` | `DEFAULT_AGENTS` from AGENTS.md |
| 1.4 | `matcher.py` | `TaskMatcher.match()` scoring algorithm |
| 1.5 | `matcher.py` | `AgentAssignment`, `MatcherConfig` |
| 1.6 | `__init__.py` | Public exports |

### Phase 2: Workflow Planning — ~2 hours

| Step | File | Description |
|------|------|-------------|
| 2.1 | `workflow.py` | `WorkflowStep`, `WorkflowPlan` dataclasses |
| 2.2 | `workflow.py` | `WorkflowOrchestrator.create_plan()` |
| 2.3 | `workflow.py` | Parallel wave computation |
| 2.4 | `workflow.py` | Review step insertion |
| 2.5 | `workflow.py` | `WorkflowPlan.get_execution_order()` |

### Phase 3: Engine Facade — ~1 hour

| Step | File | Description |
|------|------|-------------|
| 3.1 | `engine.py` | `CoordinationEngine.coordinate()` |
| 3.2 | `engine.py` | `CoordinationObserver` protocol |
| 3.3 | `engine.py` | `handle_failure()` escalation |
| 3.4 | `engine.py` | `CoordinationConfig`, `CoordinationResult` |

### Phase 4: Tests — ~2 hours

| Step | File | Description |
|------|------|-------------|
| 4.1 | `test_agents.py` | Registry CRUD, default agents validation |
| 4.2 | `test_matcher.py` | Scoring algorithm, capability matching, edge cases |
| 4.3 | `test_workflow.py` | Plan generation, wave scheduling, review chains |
| 4.4 | `test_coordination_engine.py` | End-to-end: decompose → coordinate → plan |

### Phase 5: Integration Polish — ~1 hour

| Step | Description |
|------|-------------|
| 5.1 | Wire into `TaskDecompositionEngine` output |
| 5.2 | Verify `ComplexityEstimate.tier` mapping |
| 5.3 | Add to CLI for visualization |
| 5.4 | Documentation + examples |

**Total estimated time: ~8 hours**

## Design Decisions Log

| Decision | Rationale |
|----------|-----------|
| Agents are dataclasses, not classes with behavior | Keeps coordination logic centralized in engine; agents are configuration |
| Capability set on AgentProfile, not just tier | Tier alone is too coarse — Reader can do code review, Coder can do docs |
| Separate Matcher from Orchestrator | Single responsibility; matcher does scoring, orchestrator does scheduling |
| Review insertion in Orchestrator, not Matcher | Review depends on execution order, not just agent selection |
| Observer protocol, not concrete class | Decouples from P2-13; any monitoring system can implement the protocol |
| `handle_failure()` returns new assignment | Keeps escalation logic in the engine, not scattered in execution layer |
| Default agents from AGENTS.md | Ensures protocol compliance out of the box |
| Escalation chain excludes Visual | Visual is a specialist (image tasks), not a general-purpose escalation tier |

## Open Questions

1. **Context passing between agents**: When Agent A hands off to Agent B, how much of Agent A's context does B get? (Proposed: structured handoff message with inputs/outputs/errors)

2. **Agent concurrency limits**: Should agents have max concurrent tasks? (Proposed: yes, default to 3, configurable per agent)

3. **Dynamic agent discovery**: Should agents register themselves at runtime? (Proposed: Phase 2 enhancement, not MVP)

4. **Cost budgets per coordination**: Should there be a total cost budget for a coordination run? (Proposed: integrate with P2-12 budget tracking)
