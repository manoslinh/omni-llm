"""
Orchestration layer for multi-agent coordination.

Includes conflict resolution, result integration, and workflow management.
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
