"""
Provider module for Omni-LLM.

Contains provider abstractions and implementations.
"""

from .base import (
    AuthenticationError,
    ChatCompletion,
    ContextLengthExceededError,
    CostRate,
    Message,
    MessageRole,
    ModelNotFoundError,
    ModelProvider,
    ProviderError,
    RateLimitError,
    TokenUsage,
)
from .config import (
    APIKeyConfig,
    BudgetConfig,
    ConfigLoader,
    ModelCostConfig,
    ProviderConfig,
    ProviderConfiguration,
    ProviderFactory,
    RateLimitConfig,
    get_default_providers_config,
    get_providers_config_from_env,
)
from .cost_tracker import CostRecord, CostTracker
from .litellm_adapter import LiteLLMAdapter
from .mock_provider import MockProvider

__all__ = [
    # Base classes
    "MessageRole",
    "Message",
    "ChatCompletion",
    "TokenUsage",
    "CostRate",
    "ModelProvider",

    # Exceptions
    "ProviderError",
    "RateLimitError",
    "AuthenticationError",
    "ModelNotFoundError",
    "ContextLengthExceededError",

    # Cost tracking
    "CostTracker",
    "CostRecord",

    # Configuration
    "ProviderConfig",
    "APIKeyConfig",
    "ModelCostConfig",
    "BudgetConfig",
    "RateLimitConfig",
    "ProviderConfiguration",
    "ConfigLoader",
    "ProviderFactory",
    "get_default_providers_config",
    "get_providers_config_from_env",

    # Implementations
    "LiteLLMAdapter",
    "MockProvider",
]
