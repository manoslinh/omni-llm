"""
LiteLLM Provider Implementation.

Wraps LiteLLM behind our ModelProvider interface.
This is our primary provider for Phase 0-1.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from .provider import (
    AuthenticationError,
    ChatCompletion,
    CompletionResult,
    ContextLengthExceededError,
    CostRate,
    Message,
    ModelCapabilities,
    ModelNotFoundError,
    ModelProvider,
    ProviderError,
    RateLimitError,
    TokenUsage,
)

logger = logging.getLogger(__name__)


# Try to import LiteLLM, but make it optional for testing
try:
    import litellm
    from litellm import token_counter
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
        RateLimitError as LiteLLMRateLimitError,
    )
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logger.warning("LiteLLM not installed. Install with: pip install litellm")


class LiteLLMProvider(ModelProvider):
    """Model provider using LiteLLM as the backend."""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize LiteLLM provider.

        Args:
            config: LiteLLM configuration dictionary
        """
        if not LITELLM_AVAILABLE:
            raise ImportError(
                "LiteLLM is not installed. Install with: pip install litellm"
            )

        self.config = config or {}
        self._model_cache: dict[str, ModelCapabilities] = {}

        # Configure LiteLLM
        if "drop_params" not in self.config:
            self.config["drop_params"] = True

        logger.info("LiteLLM provider initialized")

    # ── Required abstract properties ─────────────────────────────────────

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
        """Stream is not yet implemented; falls back to a single yield."""
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
        Send messages to the model via LiteLLM.

        Args:
            messages: List of messages in the conversation
            model: Model identifier (e.g., "openai/gpt-4")
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional LiteLLM parameters

        Returns:
            CompletionResult with content and usage

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
                **self.config,
            }

            if max_tokens is not None:
                params["max_tokens"] = max_tokens

            # Add any additional kwargs
            params.update(kwargs)

            logger.debug(f"Calling LiteLLM with model: {model}")

            # Call LiteLLM (async)
            response = await asyncio.to_thread(
                litellm.completion,
                **params
            )

            # Extract content
            if hasattr(response.choices[0].message, 'content'):
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
            if hasattr(response.choices[0].message, 'tool_calls'):
                tool_calls = response.choices[0].message.tool_calls

            return CompletionResult(
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
            raise ContextLengthExceededError(f"Context length exceeded for {model}: {e}") from e
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
            return token_counter(model=model, text=text)
        except Exception as e:
            logger.warning(f"Failed to count tokens for {model}: {e}")
            # Fallback: rough estimate of 4 chars per token
            return len(text) // 4

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str
    ) -> float:
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
            cost = litellm.completion_cost(
                model=model,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
            )
            return cost
        except Exception as e:
            logger.warning(f"Failed to estimate cost for {model}: {e}")
            # Fallback: use rough estimates
            return self._estimate_cost_fallback(model, input_tokens, output_tokens)

    def get_capabilities(self, model: str) -> ModelCapabilities:
        """
        Get capabilities of a model.

        We cache capabilities to avoid repeated lookups.

        Args:
            model: Model identifier

        Returns:
            ModelCapabilities object
        """
        if model in self._model_cache:
            return self._model_cache[model]

        # Determine capabilities based on model name patterns
        capabilities = self._infer_capabilities(model)
        self._model_cache[model] = capabilities
        return capabilities

    def list_models(self) -> list[str]:
        """
        List available models.

        Note: LiteLLM doesn't have a built-in model listing API,
        so we return a curated list of common models.

        Returns:
            List of model identifiers
        """
        # Common models across providers
        common_models = [
            # OpenAI
            "openai/gpt-4",
            "openai/gpt-4-turbo-preview",
            "openai/gpt-4-0125-preview",
            "openai/gpt-4-1106-preview",
            "openai/gpt-3.5-turbo",
            "openai/gpt-3.5-turbo-0125",

            # Anthropic
            "anthropic/claude-3-opus-20240229",
            "anthropic/claude-3-sonnet-20240229",
            "anthropic/claude-3-haiku-20240307",
            "anthropic/claude-2.1",

            # Google
            "google/gemini-1.5-pro-latest",
            "google/gemini-1.5-flash-latest",
            "google/gemini-pro",

            # DeepSeek
            "deepseek/deepseek-chat",
            "deepseek/deepseek-coder",

            # Cohere
            "cohere/command-r-plus",
            "cohere/command-r",

            # Mistral
            "mistral/mistral-large-latest",
            "mistral/mistral-medium-latest",
            "mistral/mistral-small-latest",

            # Local (via Ollama)
            "ollama/llama2",
            "ollama/codellama",
            "ollama/mistral",
        ]

        return common_models

    async def close(self) -> None:
        """Clean up resources."""
        # LiteLLM doesn't require cleanup, but we clear the cache
        self._model_cache.clear()
        logger.info("LiteLLM provider closed")

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert our Message objects to LiteLLM format."""
        result: list[dict[str, Any]] = []
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

    def _infer_capabilities(self, model: str) -> ModelCapabilities:
        """Infer model capabilities based on name patterns."""
        model_lower = model.lower()

        # Default capabilities
        capabilities = ModelCapabilities()

        # Set edit format based on model intelligence
        if any(pattern in model_lower for pattern in ["gpt-4", "claude-3", "gemini-1.5"]):
            capabilities.supports_edit_format = "editblock"
        elif any(pattern in model_lower for pattern in ["gpt-3.5", "claude-2", "gemini-pro"]):
            capabilities.supports_edit_format = "diff"
        else:
            capabilities.supports_edit_format = "whole"

        # Set context window
        if "claude-3" in model_lower:
            capabilities.max_context_tokens = 200_000
        elif "gemini-1.5" in model_lower:
            capabilities.max_context_tokens = 1_000_000
        elif "gpt-4" in model_lower and "turbo" in model_lower:
            capabilities.max_context_tokens = 128_000
        elif "gpt-4" in model_lower:
            capabilities.max_context_tokens = 8_192
        elif "gpt-3.5" in model_lower:
            capabilities.max_context_tokens = 16_385

        # Tool support
        capabilities.supports_tools = any(
            pattern in model_lower for pattern in ["gpt-4", "claude-3", "gemini-1.5"]
        )

        # Vision support
        capabilities.supports_vision = any(
            pattern in model_lower for pattern in ["gpt-4-vision", "claude-3", "gemini-1.5"]
        )

        return capabilities

    def _estimate_cost_fallback(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """Fallback cost estimation when LiteLLM fails."""
        model_lower = model.lower()

        # Cost per million tokens (input/output)
        # Prices as of March 2026 (approximate)
        cost_per_million = {
            # OpenAI
            "gpt-4": (30.00, 60.00),
            "gpt-4-turbo": (10.00, 30.00),
            "gpt-3.5-turbo": (0.50, 1.50),

            # Anthropic
            "claude-3-opus": (15.00, 75.00),
            "claude-3-sonnet": (3.00, 15.00),
            "claude-3-haiku": (0.25, 1.25),
            "claude-2.1": (8.00, 24.00),

            # Google
            "gemini-1.5-pro": (3.50, 10.50),
            "gemini-1.5-flash": (0.075, 0.30),
            "gemini-pro": (0.50, 1.50),

            # DeepSeek
            "deepseek-chat": (0.28, 0.42),
            "deepseek-coder": (0.28, 0.42),

            # Default fallback
            "default": (5.00, 15.00),
        }

        # Find matching cost
        for pattern, (_input_cost, _output_cost) in cost_per_million.items():
            if pattern in model_lower:
                input_cost, output_cost = _input_cost, _output_cost
                break
        else:
            input_cost, output_cost = cost_per_million["default"]

        # Calculate cost
        input_cost_usd = (input_tokens / 1_000_000) * input_cost
        output_cost_usd = (output_tokens / 1_000_000) * output_cost

        return input_cost_usd + output_cost_usd
