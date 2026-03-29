"""
Git integration for Omni-LLM.

Provides git operations with AI attribution and safety features.
Based on patterns from Aider's repo.py.
"""

from .repository import GitRepository
from .worktree import (
    WorktreeCreationError,
    WorktreeEnv,
    WorktreeError,
    WorktreeExistsError,
    WorktreeInfo,
    WorktreeManager,
    WorktreeNotFoundError,
)

__all__ = [
    "GitRepository",
    "WorktreeManager",
    "WorktreeEnv",
    "WorktreeInfo",
    "WorktreeError",
    "WorktreeExistsError",
    "WorktreeNotFoundError",
    "WorktreeCreationError",
]
