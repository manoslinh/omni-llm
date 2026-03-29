"""
Data models for scheduling module.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ResourceBudget:
    """Resource budget for a workflow execution."""
    execution_id: str
    max_concurrent: int
    max_tokens: int | None = None
    max_cost: float | None = None
    metadata: dict[str, Any] | None = None
    active_tasks: int = 0
