"""Backward-compatible re-exports from the canonical provider interface.

The single source of truth for the ModelProvider ABC and related types
now lives in ``omni.providers.base``.  This module re-exports every
public name so that existing ``from omni.models.provider import …``
statements continue to work without changes.
"""

from ..providers.base import (
    AuthenticationError,
    ChatCompletion,
    ContextLengthExceededError,
    CostRate,
    Message,
    MessageRole,
    ModelCapabilities,
    ModelNotFoundError,
    ModelProvider,
    ProviderError,
    RateLimitError,
    TokenUsage,
)
from ..providers.base import (
    ChatCompletion as CompletionResult,
)

__all__ = [
    "AuthenticationError",
    "ChatCompletion",
    "CompletionResult",
    "ContextLengthExceededError",
    "CostRate",
    "Message",
    "MessageRole",
    "ModelCapabilities",
    "ModelNotFoundError",
    "ModelProvider",
    "ProviderError",
    "RateLimitError",
    "TokenUsage",
]
