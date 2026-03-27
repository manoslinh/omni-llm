"""
Omni-LLM Model Router — cost-aware model selection and routing.

This package provides:
- ModelRouter: Main facade for unified model routing with fallback chains
- RoutingStrategy: Abstract interface for pluggable routing strategies
- ProviderRegistry: Central registry for model providers with capability discovery
- Data models: TaskType, ModelSelection, CostEstimate, etc.
- Errors: Router-specific exceptions for budget and eligibility failures
- Budget: Budget tracking and enforcement system
"""

from .budget import BudgetConfig, BudgetTracker
from .cost_optimized import CostOptimizedStrategy
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
from .provider_registry import (
    Capability,
    ProviderHealthCheck,
    ProviderMetadata,
    ProviderRegistry,
    ProviderStatus,
)
from .router import ModelRouter, RouterConfig, RouterResult
from .strategy import RoutingStrategy

__all__ = [
    # Main router facade
    "ModelRouter",
    "RouterConfig",
    "RouterResult",
    # Strategies
    "RoutingStrategy",
    "CostOptimizedStrategy",
    # Provider registry
    "ProviderRegistry",
    "ProviderMetadata",
    "ProviderStatus",
    "Capability",
    "ProviderHealthCheck",
    # Budget
    "BudgetConfig",
    "BudgetTracker",
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
