"""
Omni-LLM Model Router — cost-aware model selection and routing.

This package provides:
- ModelRouter: Main facade for unified model routing with fallback chains
- RoutingStrategy: Abstract interface for pluggable routing strategies
- Data models: TaskType, ModelSelection, CostEstimate, etc.
- Errors: Router-specific exceptions for budget and eligibility failures
- Budget: Budget tracking and enforcement system
- Health: Health monitoring and circuit breaker for provider resilience
"""

from .budget import BudgetConfig, BudgetTracker
from .cost_optimized import CostOptimizedStrategy
from .errors import (
    AllModelsFailedError,
    BudgetExceededError,
    NoEligibleModelError,
    RouterError,
)
from .health import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    HealthConfig,
    HealthManager,
    HealthMetrics,
    HealthMonitor,
    ResilientProvider,
)
from .models import (
    CostEstimate,
    FallbackConfig,
    ModelSelection,
    RankedModel,
    RoutingContext,
    TaskType,
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
    # Budget
    "BudgetConfig",
    "BudgetTracker",
    # Health monitoring & circuit breaker
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "HealthConfig",
    "HealthManager",
    "HealthMetrics",
    "HealthMonitor",
    "ResilientProvider",
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
