"""
Shared data models for the edit loop.
"""

from dataclasses import dataclass

from .verifier import VerificationResult


@dataclass
class Edit:
    """A single edit to apply to a file."""
    file_path: str
    old_text: str
    new_text: str
    search_context: str | None = None


@dataclass
class ApplyResult:
    """Result of applying edits."""
    files_modified: list[str]
    files_created: list[str]
    files_deleted: list[str]
    errors: list[str]


@dataclass
class CycleResult:
    """Result of a complete edit cycle."""
    edits: list[Edit]
    verification: VerificationResult
    cost: float
    reflections: int
    success: bool
