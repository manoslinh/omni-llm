"""
Omni-LLM Model Router — cost-aware model selection and routing.

This package provides:
- RoutingStrategy: Abstract interface for pluggable routing strategies
- Data models: TaskType, ModelSelection, CostEstimate, etc.
- Errors: Router-specific exceptions for budget and eligibility failures
"""

from .errors import (
    AllModelsFailedError,
    BudgetExceededError,
    NoEligibleModelError,
    RouterError,
)
from .models import (
    CostEstimate,
    FallbackConfig,
    ModelSelection,
    RankedModel,
    RoutingContext,
    TaskType,
)
from .strategy import RoutingStrategy

__all__ = [
    # Strategy
    "RoutingStrategy",
    # Data models
    "TaskType",
    "ModelSelection",
    "CostEstimate",
    "RankedModel",
    "RoutingContext",
    "FallbackConfig",
    # Errors
    "RouterError",
    "NoEligibleModelError",
    "BudgetExceededError",
    "AllModelsFailedError",
]
