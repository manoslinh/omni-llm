"""
Shared data models for the edit loop.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Edit:
    """A single edit to apply to a file."""
    file_path: str
    old_text: str
    new_text: str
    search_context: Optional[str] = None


@dataclass
class ApplyResult:
    """Result of applying edits."""
    files_modified: List[str]
    files_created: List[str]
    files_deleted: List[str]
    errors: List[str]


from .verifier import VerificationResult


@dataclass
class CycleResult:
    """Result of a complete edit cycle."""
    edits: List[Edit]
    verification: VerificationResult
    cost: float
    reflections: int
    success: bool