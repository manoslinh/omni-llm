"""
Model Provider Abstraction Layer — Canonical Interface.

Defines the unified ModelProvider interface for Omni-LLM.
All providers must implement this interface.

This is the single source of truth for:
- MessageRole, Message, TokenUsage (shared data types)
- ChatCompletion / CompletionResult (response container)
- ModelCapabilities (per-model feature flags)
- CostRate (pricing metadata)
- ModelProvider ABC (the contract every backend implements)
- Provider exception hierarchy
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# ── Shared Data Types ────────────────────────────────────────────────────────


class MessageRole(StrEnum):
    """Message roles for chat completion."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

    def __str__(self) -> str:
        return self.value


@dataclass
class Message:
    """A single message in a chat conversation."""
    role: MessageRole
    content: str
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


@dataclass
class ChatCompletion:
    """Result from a chat completion."""
    content: str
    model: str
    usage: "TokenUsage"
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


# Backward-compatible alias used by omni.models.provider consumers.
CompletionResult = ChatCompletion


@dataclass
class TokenUsage:
    """Token usage statistics."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class CostRate:
    """Cost rate for a model (per million tokens)."""
    input_per_million: float  # USD per million input tokens
    output_per_million: float  # USD per million output tokens


@dataclass
class ModelCapabilities:
    """Capabilities of a specific model."""
    supports_edit_format: str = "whole"  # "whole", "diff", "editblock"
    max_context_tokens: int = 128_000
    supports_tools: bool = False
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_audio: bool = False
    temperature_range: tuple[float, float] = (0.0, 2.0)
    top_p_range: tuple[float, float] = (0.0, 1.0)


# ── ModelProvider ABC ────────────────────────────────────────────────────────


class ModelProvider(ABC):
    """Abstract base class for all model providers.

    Required methods (must override):
        chat_completion, stream_chat_completion, count_tokens,
        estimate_cost, close

    Required properties (must override):
        name, supports_streaming, cost_per_token

    Optional methods (have sensible defaults):
        complete          — delegates to chat_completion
        get_capabilities  — returns generic ModelCapabilities
        list_models       — returns empty list
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the provider (e.g., 'openai', 'anthropic', 'litellm')."""
        pass

    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Whether the provider supports streaming responses."""
        pass

    @property
    @abstractmethod
    def cost_per_token(self) -> dict[str, CostRate]:
        """
        Cost per token for each model.

        Returns:
            Dictionary mapping model names to CostRate objects
        """
        pass

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any
    ) -> ChatCompletion:
        """
        Send messages to the model and get a completion.

        Args:
            messages: List of messages in the conversation
            model: Model identifier (provider-specific)
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Returns:
            ChatCompletion with content and usage

        Raises:
            ProviderError: For general provider errors
            RateLimitError: If rate limit exceeded
            AuthenticationError: If authentication failed
            ModelNotFoundError: If model is not found
            ContextLengthExceededError: If context length exceeded
        """
        pass

    @abstractmethod
    async def stream_chat_completion(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any
    ) -> AsyncGenerator[str, None]:
        """
        Stream messages to the model and get a streaming response.

        Args:
            messages: List of messages in the conversation
            model: Model identifier (provider-specific)
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Returns:
            AsyncGenerator yielding chunks of the response

        Raises:
            ProviderError: For general provider errors
            RateLimitError: If rate limit exceeded
            AuthenticationError: If authentication failed
            ModelNotFoundError: If model is not found
            ContextLengthExceededError: If context length exceeded
        """
        pass

    @abstractmethod
    def count_tokens(self, text: str, model: str) -> int:
        """
        Count tokens in text for a specific model.

        Args:
            text: Text to count tokens for
            model: Model identifier

        Returns:
            Number of tokens
        """
        pass

    @abstractmethod
    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str
    ) -> float:
        """
        Estimate cost for a completion.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model identifier

        Returns:
            Estimated cost in USD
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up provider resources."""
        pass

    # ── Optional methods with default implementations ────────────────────

    async def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ChatCompletion:
        """Convenience wrapper that delegates to ``chat_completion``.

        Subclasses that were written against the old
        ``omni.models.provider.ModelProvider`` contract override this
        directly and never call ``chat_completion``.  The default
        implementation here bridges the two styles so that callers
        using ``complete()`` still work when the subclass only
        implements ``chat_completion()``.
        """
        return await self.chat_completion(
            messages, model, temperature=temperature,
            max_tokens=max_tokens, **kwargs,
        )

    def get_capabilities(self, model: str) -> ModelCapabilities:
        """Return capabilities for *model*.

        The default implementation returns a generic
        ``ModelCapabilities`` instance.  Subclasses may override to
        provide model-specific information.
        """
        return ModelCapabilities()

    def list_models(self) -> list[str]:
        """List available model identifiers.

        The default implementation returns an empty list.
        """
        return []


# ── Exception Hierarchy ──────────────────────────────────────────────────────


class ProviderError(Exception):
    """Base exception for provider errors."""
    pass


class RateLimitError(ProviderError):
    """Rate limit exceeded."""
    pass


class AuthenticationError(ProviderError):
    """Authentication failed."""
    pass


class ModelNotFoundError(ProviderError):
    """Model not found in provider."""
    pass


class ContextLengthExceededError(ProviderError):
    """Context length exceeded."""
    pass
