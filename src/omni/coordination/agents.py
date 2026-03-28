"""Agent definitions for multi-agent coordination.

This module defines the AgentProfile dataclass, AgentRegistry,
and default agent definitions from AGENTS.md.
"""

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
