"""
Orchestration layer for multi-agent workflow execution.

This module provides:
1. Workflow template engine (YAML-based reusable workflows)
2. Result integration (combining parallel task results)
3. Conflict resolution (handling file merge conflicts)
"""

from .conflicts import (
    ConflictResolver,
    ConflictType,
    FileConflict,
    Resolution,
    ResolutionStrategy,
)
from .integrator import OrchestrationResult, ResultIntegrator
from .workflow import WorkflowEngine
from .workflow_models import TaskType, VariableDef, WorkflowStep, WorkflowTemplate

__all__ = [
    # Workflow template engine
    "WorkflowEngine",
    "TaskType",
    "VariableDef",
    "WorkflowStep",
    "WorkflowTemplate",
    # Result integration
    "OrchestrationResult",
    "ResultIntegrator",
    # Conflict resolution
    "ConflictResolver",
    "ConflictType",
    "FileConflict",
    "Resolution",
    "ResolutionStrategy",
]
