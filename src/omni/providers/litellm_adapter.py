"""
LiteLLM Adapter for Omni-LLM.

Thin wrapper around LiteLLM implementing the ModelProvider interface from base.py.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from .base import (
    AuthenticationError,
    ChatCompletion,
    ContextLengthExceededError,
    CostRate,
    Message,
    ModelNotFoundError,
    ModelProvider,
    ProviderError,
    RateLimitError,
    TokenUsage,
)

logger = logging.getLogger(__name__)


# Try to import LiteLLM, but make it optional for testing
try:
    from litellm import acompletion
    from litellm.exceptions import (
        AuthenticationError as LiteLLMAuthError,
    )
    from litellm.exceptions import (
        BadRequestError as LiteLLMBadRequestError,
    )
    from litellm.exceptions import (
        ContextWindowExceededError as LiteLLMContextError,
    )
    from litellm.exceptions import (
        NotFoundError as LiteLLMNotFoundError,
    )
    from litellm.exceptions import (
        RateLimitError as LiteLLMRateLimitError,
    )

    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logger.warning("LiteLLM not installed. Install with: pip install litellm")


class LiteLLMAdapter(ModelProvider):
    """LiteLLM adapter implementing the ModelProvider interface."""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize LiteLLM adapter.

        Args:
            config: LiteLLM configuration dictionary
        """
        if not LITELLM_AVAILABLE:
            raise ImportError(
                "LiteLLM is not installed. Install with: pip install litellm"
            )

        self._config = config or {}
        self._model_cache: dict[str, CostRate] = {}

        # Configure LiteLLM defaults
        if "drop_params" not in self._config:
            self._config["drop_params"] = True
        if "timeout" not in self._config:
            self._config["timeout"] = 30

        logger.info("LiteLLM adapter initialized")

    @property
    def name(self) -> str:
        """Name of the provider."""
        return "litellm"

    @property
    def supports_streaming(self) -> bool:
        """Whether the provider supports streaming."""
        return True

    @property
    def cost_per_token(self) -> dict[str, CostRate]:
        """
        Cost per token for each model.

        Returns cached cost rates or fetches them if not cached.
        """
        if not self._model_cache:
            # Initialize cache with common models
            self._initialize_cost_cache()

        return self._model_cache

    async def chat_completion(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ChatCompletion:
        """
        Send messages to the model via LiteLLM.

        Args:
            messages: List of messages in the conversation
            model: Model identifier (e.g., "openai/gpt-4")
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional LiteLLM parameters

        Returns:
            ChatCompletion with content and usage

        Raises:
            ModelNotFoundError: If model is not found
            RateLimitError: If rate limit exceeded
            AuthenticationError: If authentication failed
            ContextLengthExceededError: If context length exceeded
            ProviderError: For other provider errors
        """
        try:
            # Convert our Message objects to LiteLLM format
            litellm_messages = self._convert_messages(messages)

            # Prepare completion parameters
            params = {
                "model": model,
                "messages": litellm_messages,
                "temperature": temperature,
                **self._config,
            }

            if max_tokens is not None:
                params["max_tokens"] = max_tokens

            # Add any additional kwargs
            params.update(kwargs)

            logger.debug(f"Calling LiteLLM with model: {model}")

            # Call LiteLLM (async)
            response = await acompletion(**params)

            # Extract content
            if hasattr(response.choices[0].message, "content"):
                content = response.choices[0].message.content or ""
            else:
                content = ""

            # Extract usage
            usage = response.usage
            token_usage = TokenUsage(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )

            # Extract tool calls if present
            tool_calls = None
            if hasattr(response.choices[0].message, "tool_calls"):
                tool_calls = response.choices[0].message.tool_calls

            return ChatCompletion(
                content=content,
                model=model,
                usage=token_usage,
                finish_reason=response.choices[0].finish_reason,
                tool_calls=tool_calls,
            )

        except LiteLLMAuthError as e:
            logger.error(f"Authentication error for model {model}: {e}")
            raise AuthenticationError(f"Authentication failed for {model}: {e}") from e
        except LiteLLMRateLimitError as e:
            logger.warning(f"Rate limit exceeded for model {model}: {e}")
            raise RateLimitError(f"Rate limit exceeded for {model}: {e}") from e
        except LiteLLMContextError as e:
            logger.warning(f"Context length exceeded for model {model}: {e}")
            raise ContextLengthExceededError(
                f"Context length exceeded for {model}: {e}"
            ) from e
        except LiteLLMNotFoundError:
            logger.error(f"Model not found: {model}")
            raise ModelNotFoundError(f"Model not found: {model}") from None
        except LiteLLMBadRequestError as e:
            if "model" in str(e).lower():
                logger.error(f"Model not found: {model}")
                raise ModelNotFoundError(f"Model not found: {model}") from e
            else:
                logger.error(f"Bad request for model {model}: {e}")
                raise ProviderError(f"Bad request for {model}: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error calling LiteLLM for model {model}: {e}")
            raise ProviderError(f"Unexpected error for {model}: {e}") from e

    async def stream_chat_completion(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:  # type: ignore[override]
        """
        Stream messages to the model via LiteLLM.

        Args:
            messages: List of messages in the conversation
            model: Model identifier (e.g., "openai/gpt-4")
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional LiteLLM parameters

        Returns:
            AsyncGenerator yielding chunks of the response

        Raises:
            ModelNotFoundError: If model is not found
            RateLimitError: If rate limit exceeded
            AuthenticationError: If authentication failed
            ContextLengthExceededError: If context length exceeded
            ProviderError: For other provider errors
        """
        try:
            # Convert our Message objects to LiteLLM format
            litellm_messages = self._convert_messages(messages)

            # Prepare completion parameters for streaming
            params = {
                "model": model,
                "messages": litellm_messages,
                "temperature": temperature,
                "stream": True,
                **self._config,
            }

            if max_tokens is not None:
                params["max_tokens"] = max_tokens

            # Add any additional kwargs
            params.update(kwargs)

            logger.debug(f"Streaming from LiteLLM with model: {model}")

            # Call LiteLLM with streaming (async)
            response = await acompletion(**params)

            # Stream the response
            async for chunk in response:
                if (
                    hasattr(chunk.choices[0].delta, "content")
                    and chunk.choices[0].delta.content
                ):
                    yield chunk.choices[0].delta.content

        except LiteLLMAuthError as e:
            logger.error(f"Authentication error for model {model}: {e}")
            raise AuthenticationError(f"Authentication failed for {model}: {e}") from e
        except LiteLLMRateLimitError as e:
            logger.warning(f"Rate limit exceeded for model {model}: {e}")
            raise RateLimitError(f"Rate limit exceeded for {model}: {e}") from e
        except LiteLLMContextError as e:
            logger.warning(f"Context length exceeded for model {model}: {e}")
            raise ContextLengthExceededError(
                f"Context length exceeded for {model}: {e}"
            ) from e
        except LiteLLMNotFoundError:
            logger.error(f"Model not found: {model}")
            raise ModelNotFoundError(f"Model not found: {model}") from None
        except LiteLLMBadRequestError as e:
            if "model" in str(e).lower():
                logger.error(f"Model not found: {model}")
                raise ModelNotFoundError(f"Model not found: {model}") from e
            else:
                logger.error(f"Bad request for model {model}: {e}")
                raise ProviderError(f"Bad request for {model}: {e}") from e
        except Exception as e:
            logger.error(
                f"Unexpected error streaming from LiteLLM for model {model}: {e}"
            )
            raise ProviderError(f"Unexpected error for {model}: {e}") from e

    def count_tokens(self, text: str, model: str) -> int:
        """
        Count tokens using LiteLLM's token counter.

        Args:
            text: Text to count tokens for
            model: Model identifier

        Returns:
            Number of tokens
        """
        try:
            # LiteLLM's token_counter is synchronous
            import litellm

            return litellm.token_counter(model=model, text=text)
        except Exception as e:
            logger.warning(f"Failed to count tokens for {model}: {e}")
            # Fallback: rough estimate of 4 chars per token
            return len(text) // 4

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """
        Estimate cost using LiteLLM's cost tracking.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model identifier

        Returns:
            Estimated cost in USD
        """
        try:
            # Use LiteLLM's cost tracking
            import litellm

            cost = litellm.completion_cost(
                model=model,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
            )
            return cost
        except Exception as e:
            logger.warning(f"Failed to estimate cost for {model}: {e}")
            # Fallback: use cached cost rates
            return self._estimate_cost_fallback(model, input_tokens, output_tokens)

    async def close(self) -> None:
        """Clean up resources."""
        # LiteLLM doesn't require cleanup, but we clear the cache
        self._model_cache.clear()
        logger.info("LiteLLM adapter closed")

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert our Message objects to LiteLLM format."""
        result = []
        for msg in messages:
            litellm_msg: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
            if msg.name:
                litellm_msg["name"] = msg.name
            if msg.tool_calls:
                litellm_msg["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                litellm_msg["tool_call_id"] = msg.tool_call_id
            result.append(litellm_msg)
        return result

    def _initialize_cost_cache(self) -> None:
        """Initialize the cost cache with common models."""
        # Common models with approximate costs (USD per million tokens)
        # Prices as of March 2026
        common_costs = {
            # OpenAI
            "openai/gpt-4": CostRate(input_per_million=30.00, output_per_million=60.00),
            "openai/gpt-4-turbo-preview": CostRate(
                input_per_million=10.00, output_per_million=30.00
            ),
            "openai/gpt-3.5-turbo": CostRate(
                input_per_million=0.50, output_per_million=1.50
            ),
            "openai/gpt-3.5-turbo-0125": CostRate(
                input_per_million=0.50, output_per_million=1.50
            ),
            # Anthropic
            "anthropic/claude-3-opus-20240229": CostRate(
                input_per_million=15.00, output_per_million=75.00
            ),
            "anthropic/claude-3-sonnet-20240229": CostRate(
                input_per_million=3.00, output_per_million=15.00
            ),
            "anthropic/claude-3-haiku-20240307": CostRate(
                input_per_million=0.25, output_per_million=1.25
            ),
            "anthropic/claude-2.1": CostRate(
                input_per_million=8.00, output_per_million=24.00
            ),
            # Google
            "google/gemini-1.5-pro-latest": CostRate(
                input_per_million=3.50, output_per_million=10.50
            ),
            "google/gemini-1.5-flash-latest": CostRate(
                input_per_million=0.075, output_per_million=0.30
            ),
            "google/gemini-pro": CostRate(
                input_per_million=0.50, output_per_million=1.50
            ),
            # DeepSeek
            "deepseek/deepseek-chat": CostRate(
                input_per_million=0.28, output_per_million=0.42
            ),
            "deepseek/deepseek-coder": CostRate(
                input_per_million=0.28, output_per_million=0.42
            ),
            # Cohere
            "cohere/command-r-plus": CostRate(
                input_per_million=3.00, output_per_million=15.00
            ),
            "cohere/command-r": CostRate(
                input_per_million=0.50, output_per_million=1.50
            ),
            # Mistral
            "mistral/mistral-large-latest": CostRate(
                input_per_million=2.00, output_per_million=6.00
            ),
            "mistral/mistral-medium-latest": CostRate(
                input_per_million=0.50, output_per_million=1.50
            ),
            "mistral/mistral-small-latest": CostRate(
                input_per_million=0.10, output_per_million=0.30
            ),
            # Local (via Ollama) - free
            "ollama/llama2": CostRate(input_per_million=0.00, output_per_million=0.00),
            "ollama/codellama": CostRate(
                input_per_million=0.00, output_per_million=0.00
            ),
            "ollama/mistral": CostRate(input_per_million=0.00, output_per_million=0.00),
        }

        self._model_cache = common_costs

    def _estimate_cost_fallback(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Fallback cost estimation when LiteLLM fails."""
        # Get cost rates from cache
        if not self._model_cache:
            self._initialize_cost_cache()

        # Find matching cost rate
        cost_rate = None
        for model_pattern, rate in self._model_cache.items():
            if model_pattern in model:
                cost_rate = rate
                break

        # Default fallback if no match found
        if cost_rate is None:
            cost_rate = CostRate(input_per_million=5.00, output_per_million=15.00)

        # Calculate cost
        input_cost_usd = (input_tokens / 1_000_000) * cost_rate.input_per_million
        output_cost_usd = (output_tokens / 1_000_000) * cost_rate.output_per_million

        return input_cost_usd + output_cost_usd
