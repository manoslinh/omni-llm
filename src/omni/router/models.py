"""
Data models for the Omni-LLM Model Router.

Defines the core types used for routing decisions, cost estimation,
and model ranking across the orchestration layer.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskType(StrEnum):
    """Classification of tasks for routing decisions."""

    ARCHITECTURE = "architecture"
    CODING = "coding"
    CODE_REVIEW = "code_review"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    SIMPLE_QUERY = "simple_query"


@dataclass
class CostEstimate:
    """Estimated cost for a model invocation."""

    input_tokens: int
    output_tokens: int
    total_cost_usd: float

    def __post_init__(self) -> None:
        """Validate cost estimate fields."""
        if self.input_tokens < 0:
            raise ValueError(f"input_tokens must be >= 0, got {self.input_tokens}")
        if self.output_tokens < 0:
            raise ValueError(f"output_tokens must be >= 0, got {self.output_tokens}")
        if self.total_cost_usd < 0:
            raise ValueError(f"total_cost_usd must be >= 0, got {self.total_cost_usd}")


@dataclass
class ModelSelection:
    """Result of a routing decision — which model to use and why."""

    model_id: str
    reason: str
    estimated_cost: CostEstimate
    confidence: float  # 0.0 to 1.0

    def __post_init__(self) -> None:
        """Validate model selection fields."""
        if not self.model_id:
            raise ValueError("model_id cannot be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}"
            )


@dataclass
class RankedModel:
    """A model with its ranking score for a given task."""

    model_id: str
    score: float  # 0.0 to 1.0, higher is better
    cost_estimate: CostEstimate
    quality_estimate: float  # 0.0 to 1.0

    def __post_init__(self) -> None:
        """Validate ranked model fields."""
        if not self.model_id:
            raise ValueError("model_id cannot be empty")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be between 0.0 and 1.0, got {self.score}")
        if not 0.0 <= self.quality_estimate <= 1.0:
            raise ValueError(
                f"quality_estimate must be between 0.0 and 1.0, "
                f"got {self.quality_estimate}"
            )


@dataclass
class RoutingContext:
    """Context information for a routing decision."""

    task_type: TaskType
    file_count: int = 0
    complexity: float = 0.5  # 0.0 (trivial) to 1.0 (extremely complex)
    budget_remaining: float | None = None  # USD, None = unlimited
    history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate routing context fields."""
        if self.file_count < 0:
            raise ValueError(f"file_count must be >= 0, got {self.file_count}")
        if not 0.0 <= self.complexity <= 1.0:
            raise ValueError(
                f"complexity must be between 0.0 and 1.0, got {self.complexity}"
            )
        if self.budget_remaining is not None and self.budget_remaining < 0:
            raise ValueError(
                f"budget_remaining must be >= 0 or None, got {self.budget_remaining}"
            )


@dataclass
class FallbackConfig:
    """Configuration for model fallback chains."""

    chain: list[str] = field(default_factory=list)
    max_retries: int = 3
    backoff_seconds: float = 1.0

    def __post_init__(self) -> None:
        """Validate fallback config fields."""
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {self.max_retries}")
        if self.backoff_seconds < 0:
            raise ValueError(
                f"backoff_seconds must be >= 0, got {self.backoff_seconds}"
            )
