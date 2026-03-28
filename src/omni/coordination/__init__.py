"""Multi-agent coordination engine for Omni-LLM.

This module provides the coordination layer that matches tasks to
specialized agents based on capabilities, complexity, and cost.

Main components:
- AgentRegistry: Registry of available agents with capabilities
- TaskMatcher: Matches tasks to the best agent using weighted scoring
- WorkflowOrchestrator: Converts TaskGraphs into parallel execution plans
- CoordinationEngine: Main facade that ties everything together
"""

from .agents import (
    DEFAULT_AGENTS,
    AgentCapability,
    AgentProfile,
    AgentRegistry,
    AgentTier,
)
from .engine import (
    CoordinationConfig,
    CoordinationEngine,
    CoordinationObserver,
    CoordinationResult,
)
from .matcher import (
    AgentAssignment,
    MatchConfidence,
    MatcherConfig,
    TaskMatcher,
)
from .workflow import (
    WorkflowOrchestrator,
    WorkflowPlan,
    WorkflowStep,
    WorkflowStepType,
)

__all__ = [
    # Agents
    "AgentCapability",
    "AgentProfile",
    "AgentRegistry",
    "AgentTier",
    "DEFAULT_AGENTS",
    # Engine
    "CoordinationConfig",
    "CoordinationEngine",
    "CoordinationObserver",
    "CoordinationResult",
    # Matcher
    "AgentAssignment",
    "MatchConfidence",
    "MatcherConfig",
    "TaskMatcher",
    # Workflow
    "WorkflowOrchestrator",
    "WorkflowPlan",
    "WorkflowStep",
    "WorkflowStepType",
]
