"""
Model Provider Abstraction Layer.

Defines the interface between Omni-LLM and LLM providers.
All providers (LiteLLM, direct APIs, mock) implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class MessageRole(StrEnum):
    """Message roles for chat completion."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

    def __str__(self):
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
class CompletionResult:
    """Result from a model completion."""
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


class ModelProvider(ABC):
    """Abstract base class for all model providers."""

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs
    ) -> CompletionResult:
        """
        Send messages to the model and get a completion.

        Args:
            messages: List of messages in the conversation
            model: Model identifier (provider-specific)
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Returns:
            CompletionResult with content and usage
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
    def get_capabilities(self, model: str) -> ModelCapabilities:
        """
        Get capabilities of a specific model.

        Args:
            model: Model identifier

        Returns:
            ModelCapabilities object
        """
        pass

    @abstractmethod
    def list_models(self) -> list[str]:
        """
        List all available models from this provider.

        Returns:
            List of model identifiers
        """
        pass

    @abstractmethod
    async def close(self):
        """Clean up provider resources."""
        pass


class ProviderError(Exception):
    """Base exception for provider errors."""
    pass


class ModelNotFoundError(ProviderError):
    """Model not found in provider."""
    pass


class RateLimitError(ProviderError):
    """Rate limit exceeded."""
    pass


class AuthenticationError(ProviderError):
    """Authentication failed."""
    pass


class ContextLengthExceededError(ProviderError):
    """Context length exceeded."""
    pass
