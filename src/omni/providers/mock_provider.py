"""
Mock Provider for testing and development.

Provides a deterministic, local provider for testing without external API calls.
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from .base import (
    ChatCompletion,
    CostRate,
    Message,
    MessageRole,
    ModelProvider,
    TokenUsage,
)


class MockProvider(ModelProvider):
    """Mock provider for testing and development."""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize mock provider.

        Args:
            config: Mock provider configuration
        """
        self._config = config or {}
        self._debug = self._config.get("debug", False)
        self._response_delay = self._config.get("response_delay", 0.1)
        self._deterministic = self._config.get("deterministic", True)

        # Mock responses for testing
        self._mock_responses = {
            "default": "This is a mock response for testing purposes.",
            "code": "def hello_world():\n    print('Hello, World!')\n    return True",
            "edit": "```python\n# Updated code\nprint('Hello, World!')\n```",
        }

    @property
    def name(self) -> str:
        """Name of the provider."""
        return "mock"

    @property
    def supports_streaming(self) -> bool:
        """Whether the provider supports streaming."""
        return True

    @property
    def cost_per_token(self) -> dict[str, CostRate]:
        """Cost per token for each model."""
        return {
            "mock-gpt": CostRate(input_per_million=0.00, output_per_million=0.00),
        }

    async def chat_completion(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any
    ) -> ChatCompletion:
        """
        Return a mock chat completion.

        Args:
            messages: List of messages in the conversation
            model: Model identifier
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            Mock chat completion
        """
        # Simulate delay
        if self._response_delay > 0:
            await asyncio.sleep(self._response_delay)

        # Generate mock response based on last user message
        last_user_message = None
        for msg in reversed(messages):
            if msg.role == MessageRole.USER:
                last_user_message = msg.content.lower()
                break

        # Determine mock response
        if last_user_message:
            if "code" in last_user_message or "function" in last_user_message:
                content = self._mock_responses["code"]
            elif "edit" in last_user_message or "update" in last_user_message:
                content = self._mock_responses["edit"]
            else:
                content = self._mock_responses["default"]
        else:
            content = self._mock_responses["default"]

        # Estimate token usage
        input_tokens = sum(len(msg.content.split()) for msg in messages)
        output_tokens = len(content.split())

        return ChatCompletion(
            content=content,
            model=model,
            usage=TokenUsage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
            finish_reason="stop",
        )

    async def stream_chat_completion(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any
    ) -> AsyncGenerator[str, None]:  # type: ignore[override]
        """
        Stream a mock chat completion.

        Args:
            messages: List of messages in the conversation
            model: Model identifier
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            AsyncGenerator yielding chunks of the response
        """
        # Get the full response
        response = await self.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

        # Stream it character by character
        for char in response.content:
            if self._response_delay > 0:
                await asyncio.sleep(self._response_delay / 10)
            yield char

    def count_tokens(self, text: str, model: str) -> int:
        """
        Count tokens in text.

        Args:
            text: Text to count tokens for
            model: Model identifier

        Returns:
            Number of tokens (approximate)
        """
        # Simple word-based token counting
        return len(text.split())

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
            Estimated cost in USD (always 0 for mock provider)
        """
        return 0.0

    async def close(self) -> None:
        """Clean up resources."""
        pass
