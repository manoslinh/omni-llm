"""
Model Provider Abstraction Layer - Phase 1 Foundation.

Defines the core ModelProvider interface for Omni-LLM.
All providers must implement this interface.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class MessageRole(StrEnum):
    """Message roles for chat completion."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


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


class ModelProvider(ABC):
    """Abstract base class for all model providers."""

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
        **kwargs
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
        **kwargs
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
    async def close(self):
        """Clean up provider resources."""
        pass


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
