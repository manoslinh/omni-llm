"""
Mock Provider for testing.

Provides deterministic responses without API calls.
Essential for unit testing and development.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from .provider import (
    ChatCompletion,
    CompletionResult,
    CostRate,
    Message,
    ModelCapabilities,
    ModelProvider,
    TokenUsage,
)

logger = logging.getLogger(__name__)


class MockProvider(ModelProvider):
    """Mock provider for testing and development."""

    def __init__(self, responses: dict[str, str] | None = None):
        """
        Initialize mock provider.

        Args:
            responses: Optional dictionary mapping model names to responses.
                      If not provided, uses default responses.
        """
        self.responses = responses or self._get_default_responses()
        self.call_log: list[dict[str, Any]] = []
        logger.info("Mock provider initialized")

    # ── Required abstract properties ─────────────────────────────────────

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
        return {}

    # ── Required abstract methods ────────────────────────────────────────

    async def chat_completion(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ChatCompletion:
        """Delegate to ``complete()``."""
        return await self.complete(
            messages, model, temperature=temperature,
            max_tokens=max_tokens, **kwargs,
        )

    async def stream_chat_completion(  # type: ignore[override]
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """Stream mock response character by character."""
        result = await self.complete(
            messages, model, temperature=temperature,
            max_tokens=max_tokens, **kwargs,
        )
        yield result.content

    # ── Legacy entry-point kept for backward compatibility ────────────────

    async def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any
    ) -> CompletionResult:
        """
        Return a mock completion.

        Args:
            messages: List of messages in the conversation
            model: Model identifier
            temperature: Ignored in mock
            max_tokens: Ignored in mock
            **kwargs: Ignored

        Returns:
            Mock CompletionResult
        """
        # Log the call
        call_info = {
            "model": model,
            "messages": [(msg.role.value, msg.content[:100]) for msg in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "kwargs": kwargs,
        }
        self.call_log.append(call_info)

        logger.debug(f"Mock provider called with model: {model}")

        # Get response based on model or default
        # Handle both versioned and unversioned model names
        if model in self.responses:
            content = self.responses[model]
        elif model == "anthropic/claude-3-sonnet":
            # Support unversioned name for backward compatibility
            content = self.responses.get("anthropic/claude-3-sonnet-20240229", "Mock response")
        else:
            content = self.responses.get("default", "Mock response")

        # Simulate async delay
        await asyncio.sleep(0.01)

        # Generate mock token usage
        input_tokens = sum(len(msg.content) // 4 for msg in messages)
        output_tokens = len(content) // 4

        return CompletionResult(
            content=content,
            model=model,
            usage=TokenUsage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
            finish_reason="stop",
        )

    def count_tokens(self, text: str, model: str) -> int:
        """Count tokens (rough estimate)."""
        return len(text) // 4

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str
    ) -> float:
        """Estimate cost (mock)."""
        # Mock pricing: $0.01 per 1000 tokens
        return (input_tokens + output_tokens) / 1000 * 0.01

    def get_capabilities(self, model: str) -> ModelCapabilities:
        """Get mock capabilities."""
        return ModelCapabilities(
            supports_edit_format="editblock",
            max_context_tokens=128_000,
            supports_tools=True,
            supports_streaming=True,
            supports_vision=False,
            supports_audio=False,
        )

    def list_models(self) -> list[str]:
        """List mock models."""
        # Return versioned model names to match LiteLLMProvider
        return [
            "openai/gpt-4",
            "anthropic/claude-3-sonnet-20240229",
            "deepseek/deepseek-chat",
        ]

    async def close(self) -> None:
        """Clean up."""
        self.call_log.clear()
        logger.info("Mock provider closed")

    def _get_default_responses(self) -> dict[str, str]:
        """Get default mock responses."""
        return {
            "default": "I'm a mock LLM. This is a test response.",
            "openai/gpt-4": """Here's the implementation you requested:

test.py
SEARCH
```

```
REPLACE
```python
def calculate_sum(numbers):
    \"\"\"Calculate the sum of a list of numbers.\"\"\"
    return sum(numbers)
```""",

            "anthropic/claude-3-sonnet-20240229": """I'll implement that for you. Here's a robust solution:

test.py
SEARCH
```

```
REPLACE
```python
from typing import List, Union

def calculate_sum(numbers: List[Union[int, float]]) -> Union[int, float]:
    \"\"\"
    Calculate the sum of a list of numbers.

    Args:
        numbers: List of integers or floats to sum

    Returns:
        The sum of all numbers in the list

    Raises:
        TypeError: If any element is not a number
    \"\"\"
    if not numbers:
        return 0

    total = 0
    for i, num in enumerate(numbers):
        if not isinstance(num, (int, float)):
            raise TypeError(f"Element at index {i} is not a number: {type(num)}")
        total += num

    return total
```""",

            "deepseek/deepseek-chat": """```python
def calculate_sum(nums):
    total = 0
    for n in nums:
        total += n
    return total
```""",
        }

    def get_last_call(self) -> dict[str, Any] | None:
        """Get the last call made to the provider."""
        return self.call_log[-1] if self.call_log else None

    def get_all_calls(self) -> list[dict[str, Any]]:
        """Get all calls made to the provider."""
        return self.call_log.copy()

    def clear_calls(self) -> None:
        """Clear the call log."""
        self.call_log.clear()
