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

__all__ = [
    "ConflictResolver",
    "ConflictType",
    "FileConflict",
    "Resolution",
    "ResolutionStrategy",
]
