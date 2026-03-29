"""
Model Router Service — facade for unified model routing.

The ModelRouter coordinates:
- Multiple providers (LiteLLM, mock, etc.)
- Multiple routing strategies (cost-optimized, quality-first, etc.)
- Fallback chains with retry logic
- Integration with EditLoop and other services

This implements the facade pattern, providing a simple interface
for complex routing decisions with automatic fallback handling.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .errors import AllModelsFailedError, BudgetExceededError, NoEligibleModelError
from .health import CircuitOpenError, HealthConfig, HealthManager
from .models import (
    CostEstimate,
    FallbackConfig,
    ModelSelection,
    RankedModel,
    RoutingContext,
    TaskType,
)
from .provider_registry import Capability, ModelProvider, ProviderRegistry
from .strategy import RoutingStrategy

logger = logging.getLogger(__name__)


@dataclass
class RouterConfig:
    """Configuration for the ModelRouter."""

    # Default strategy to use if not specified per-task
    default_strategy: type[RoutingStrategy] | None = None

    # Strategy instances keyed by name
    strategies: dict[str, RoutingStrategy] = field(default_factory=dict)

    # Provider registry for managing providers with capability discovery
    provider_registry: ProviderRegistry | None = None

    # Provider instances keyed by model ID or provider name (legacy support)
    providers: dict[str, ModelProvider] = field(default_factory=dict)

    # Fallback configuration
    fallback_config: FallbackConfig = field(default_factory=FallbackConfig)

    # Maximum retries per model
    max_retries_per_model: int = 3

    # Backoff base in seconds (exponential backoff)
    backoff_base: float = 1.0

    # Timeout for model calls in seconds
    call_timeout: float = 60.0

    # Whether to enable cost tracking
    enable_cost_tracking: bool = True

    # Health monitoring configuration (None to disable)
    health_config: HealthConfig | None = None

    def __post_init__(self) -> None:
        """Validate router configuration."""
        if self.max_retries_per_model < 0:
            raise ValueError(
                f"max_retries_per_model must be >= 0, got {self.max_retries_per_model}"
            )
        if self.backoff_base <= 0:
            raise ValueError(f"backoff_base must be > 0, got {self.backoff_base}")
        if self.call_timeout <= 0:
            raise ValueError(f"call_timeout must be > 0, got {self.call_timeout}")

        # Initialize provider registry if not provided
        if self.provider_registry is None:
            self.provider_registry = ProviderRegistry()

        # Register legacy providers with the registry
        for model_id, provider in self.providers.items():
            try:
                self.provider_registry.register(provider)
                logger.debug(f"Registered legacy provider '{provider.name}' for model '{model_id}'")
            except Exception as e:
                logger.warning(f"Failed to register legacy provider '{provider.name}': {e}")


@dataclass
class RouterResult:
    """Result from a router invocation."""

    # The selected model ID
    model_id: str

    # The completion result
    completion: Any

    # Total cost in USD
    total_cost_usd: float

    # Which provider was used
    provider_name: str

    # Which strategy was used
    strategy_name: str

    # Number of retries attempted
    retries: int = 0

    # Time taken in seconds
    elapsed_seconds: float = 0.0

    # Any errors that occurred (but were recovered from)
    errors: list[Exception] = field(default_factory=list)


class ModelRouter:
    """
    Main model router facade.

    Provides a unified interface for:
    1. Selecting models based on task type and context
    2. Executing completions with automatic fallback
    3. Tracking costs and usage
    4. Handling errors and retries
    """

    def __init__(self, config: RouterConfig) -> None:
        """
        Initialize the model router.

        Args:
            config: Router configuration
        """
        self.config = config
        self._strategy_cache: dict[str, RoutingStrategy] = {}
        self._provider_cache: dict[str, ModelProvider] = {}  # Legacy cache for backward compatibility
        self._cost_tracker: dict[str, float] = {}  # model_id -> total_cost

        # Health monitoring
        self._health_manager: HealthManager | None = None
        if config.health_config is not None:
            self._health_manager = HealthManager(config.health_config)

        # Initialize caches
        for name, strategy in config.strategies.items():
            self._strategy_cache[name] = strategy

        # Store legacy providers for backward compatibility
        for model_id, provider in config.providers.items():
            self._provider_cache[model_id] = provider

        # Set default strategy if provided
        if config.default_strategy and not self._strategy_cache:
            try:
                default_instance = config.default_strategy()
                self._strategy_cache["default"] = default_instance
            except Exception as e:
                logger.warning(f"Failed to instantiate default strategy: {e}")

        # Ensure provider registry is available
        if config.provider_registry is None:
            config.provider_registry = ProviderRegistry()

    def get_strategy(self, strategy_name: str | None = None) -> RoutingStrategy:
        """
        Get a routing strategy by name.

        Args:
            strategy_name: Name of the strategy, or None for default

        Returns:
            RoutingStrategy instance

        Raises:
            ValueError: If strategy not found and no default available
        """
        if strategy_name is None:
            if "default" in self._strategy_cache:
                return self._strategy_cache["default"]
            elif len(self._strategy_cache) == 1:
                return next(iter(self._strategy_cache.values()))
            else:
                raise ValueError(
                    "No default strategy specified and multiple strategies available"
                )

        if strategy_name not in self._strategy_cache:
            raise ValueError(f"Strategy '{strategy_name}' not found")

        return self._strategy_cache[strategy_name]

    def get_provider(self, model_id: str) -> ModelProvider:
        """
        Get a provider for a model ID or provider name.

        Args:
            model_id: Model identifier or provider name

        Returns:
            ModelProvider instance

        Raises:
            ValueError: If no provider found for the model
        """
        # First try legacy cache for backward compatibility
        if model_id in self._provider_cache:
            return self._provider_cache[model_id]

        # Try to find a provider using the registry
        if self.config.provider_registry:
            # Try lookup by model ID (e.g., "openai/gpt-4")
            providers = self.config.provider_registry.get_providers_for_model(model_id)
            if providers:
                # Get the first provider (sorted by success rate)
                provider_name = providers[0]
                provider = self.config.provider_registry.get_provider(provider_name)
                if provider:
                    return provider

            # Try lookup by provider name (e.g., "openai")
            provider = self.config.provider_registry.get_provider(model_id)
            if provider:
                return provider

        # Fallback to legacy heuristic
        for provider_id, provider in self._provider_cache.items():
            # Simple heuristic: if provider ID is in model ID or vice versa
            if provider_id in model_id or model_id in provider_id:
                return provider

        raise ValueError(f"No provider found for model '{model_id}'")

    def select_model(
        self,
        task_type: TaskType,
        context: RoutingContext,
        strategy_name: str | None = None,
    ) -> ModelSelection:
        """
        Select a model for a task using the specified strategy.

        Args:
            task_type: Type of task
            context: Routing context
            strategy_name: Strategy to use (None for default)

        Returns:
            ModelSelection with chosen model and reasoning

        Raises:
            NoEligibleModelError: If no model meets requirements
            BudgetExceededError: If budget is insufficient
        """
        strategy = self.get_strategy(strategy_name)
        selection = strategy.select_model(task_type, context)

        if selection is None:
            raise NoEligibleModelError(
                task_type.value,
                reason=f"Strategy '{strategy.name}' returned no selection",
            )

        return selection

    def rank_models(
        self,
        task_type: TaskType,
        context: RoutingContext,
        strategy_name: str | None = None,
    ) -> list[RankedModel]:
        """
        Rank all candidate models for a task.

        Args:
            task_type: Type of task
            context: Routing context
            strategy_name: Strategy to use (None for default)

        Returns:
            List of RankedModel sorted by suitability
        """
        strategy = self.get_strategy(strategy_name)
        return strategy.rank_models(task_type, context)

    def estimate_cost(
        self,
        task_type: TaskType,
        model_id: str,
        context: RoutingContext,
        strategy_name: str | None = None,
    ) -> CostEstimate:
        """
        Estimate cost for using a specific model.

        Args:
            task_type: Type of task
            model_id: Model identifier
            context: Routing context
            strategy_name: Strategy to use (None for default)

        Returns:
            CostEstimate with predicted token usage and cost
        """
        strategy = self.get_strategy(strategy_name)
        return strategy.estimate_cost(task_type, model_id, context)

    async def complete(
        self,
        messages: list[Any],
        task_type: TaskType,
        context: RoutingContext,
        strategy_name: str | None = None,
        fallback_chain: list[str] | None = None,
    ) -> RouterResult:
        """
        Execute a completion with automatic fallback handling.

        This is the main entry point for the router. It:
        1. Selects a model based on task type and context
        2. Attempts completion with the selected model
        3. Falls back to other models if failures occur
        4. Tracks costs and errors

        Args:
            messages: Chat messages to send
            task_type: Type of task
            context: Routing context
            strategy_name: Strategy to use (None for default)
            fallback_chain: Custom fallback chain (overrides config)

        Returns:
            RouterResult with completion and metadata

        Raises:
            AllModelsFailedError: If all models in the fallback chain fail
        """
        start_time = time.monotonic()
        errors: list[Exception] = []
        total_attempts = 0

        # Get strategy early to avoid redundant calls
        strategy = self.get_strategy(strategy_name)

        # Get fallback chain
        if fallback_chain is None:
            fallback_chain = self.config.fallback_config.chain

        # If no fallback chain specified, we'll build one dynamically
        if not fallback_chain:
            # Get ranked models and use them as fallback chain
            ranked = strategy.rank_models(task_type, context)
            fallback_chain = [model.model_id for model in ranked]

        # Try each model in the chain
        for _attempt, model_id in enumerate(fallback_chain):
            # Check budget before attempting
            if context.budget_remaining is not None:
                cost_est = strategy.estimate_cost(task_type, model_id, context)
                if cost_est.total_cost_usd > context.budget_remaining:
                    logger.warning(
                        f"Model {model_id} exceeds budget: "
                        f"${cost_est.total_cost_usd:.6f} > ${context.budget_remaining:.6f}"
                    )
                    errors.append(
                        BudgetExceededError(
                            budget_remaining=context.budget_remaining,
                            estimated_cost=cost_est.total_cost_usd,
                        )
                    )
                    continue

            # Health check — skip providers with OPEN circuit breaker
            if self._health_manager is not None:
                breaker = self._health_manager.get_breaker(model_id)
                if not breaker.is_available:
                    logger.warning(
                        f"Model {model_id} circuit breaker is {breaker.state.value}, skipping"
                    )
                    errors.append(
                        CircuitOpenError(model_id, breaker.state)
                    )
                    continue

            # Get provider for this model
            try:
                provider = self.get_provider(model_id)
            except ValueError as e:
                logger.warning(f"Could not get provider for {model_id}: {e}")
                errors.append(e)
                continue

            # Try with retries
            for retry in range(self.config.max_retries_per_model + 1):
                try:
                    # Execute completion with timeout
                    completion = await asyncio.wait_for(
                        provider.complete(
                            model=model_id,
                            messages=messages,
                            temperature=0.1,  # Low temperature for deterministic tasks
                            max_tokens=4000,  # Reasonable default
                        ),
                        timeout=self.config.call_timeout,
                    )

                    # Calculate cost
                    total_cost = 0.0
                    if self.config.enable_cost_tracking:
                        # This would integrate with a cost tracker service
                        # For now, we'll use the estimate
                        cost_est = strategy.estimate_cost(task_type, model_id, context)
                        total_cost = cost_est.total_cost_usd

                        # Update internal tracker
                        self._cost_tracker[model_id] = (
                            self._cost_tracker.get(model_id, 0.0) + total_cost
                        )

                    # Record health success
                    if self._health_manager is not None:
                        elapsed_call = time.monotonic() - start_time
                        self._health_manager.monitor.record_call(
                            model_id, latency=elapsed_call, success=True
                        )

                    # Success!
                    elapsed = time.monotonic() - start_time
                    return RouterResult(
                        model_id=model_id,
                        completion=completion,
                        total_cost_usd=total_cost,
                        provider_name=provider.__class__.__name__,
                        strategy_name=strategy.name,
                        retries=total_attempts + retry,
                        elapsed_seconds=elapsed,
                        errors=errors,
                    )

                except CircuitOpenError:
                    # Don't count circuit-open as a provider failure
                    raise
                except Exception as e:
                    logger.warning(
                        f"Attempt {retry + 1} failed for model {model_id}: {e}"
                    )
                    errors.append(e)

                    # Record health failure
                    if self._health_manager is not None:
                        breaker = self._health_manager.get_breaker(model_id)
                        breaker.record_failure(e)

                    # If we have retries left, wait with exponential backoff
                    if retry < self.config.max_retries_per_model:
                        wait_time = self.config.backoff_base * (2**retry)
                        logger.info(f"Retrying in {wait_time:.1f}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        # No more retries for this model
                        break

            # This model failed, try next in chain
            total_attempts += self.config.max_retries_per_model + 1

        # All models failed
        elapsed = time.monotonic() - start_time
        raise AllModelsFailedError(
            model_ids=fallback_chain,
            last_error=errors[-1] if errors else None,
        )

    def get_total_cost(self, model_id: str | None = None) -> float:
        """
        Get total cost incurred by the router.

        Args:
            model_id: Specific model to get cost for, or None for all models

        Returns:
            Total cost in USD
        """
        if model_id is None:
            return sum(self._cost_tracker.values())
        return self._cost_tracker.get(model_id, 0.0)

    def reset_cost_tracking(self) -> None:
        """Reset the cost tracker."""
        self._cost_tracker.clear()

    def register_strategy(self, name: str, strategy: RoutingStrategy) -> None:
        """
        Register a new routing strategy.

        Args:
            name: Strategy name
            strategy: Strategy instance
        """
        self._strategy_cache[name] = strategy

    def register_provider(self, model_id: str, provider: ModelProvider) -> None:
        """
        Register a provider for a model.

        Args:
            model_id: Model identifier
            provider: Provider instance
        """
        # Legacy registration for backward compatibility
        self._provider_cache[model_id] = provider

        # Also register with the provider registry if available
        if self.config.provider_registry:
            try:
                self.config.provider_registry.register(provider)
                logger.debug(f"Registered provider '{provider.name}' with registry")
            except Exception as e:
                logger.warning(f"Failed to register provider '{provider.name}' with registry: {e}")

    # ProviderRegistry integration methods

    def get_provider_registry(self) -> ProviderRegistry | None:
        """Get the provider registry instance."""
        return self.config.provider_registry

    async def check_provider_health(self, provider_name: str | None = None) -> dict:
        """
        Check health of one or all providers.

        Args:
            provider_name: Name of specific provider to check, or None for all

        Returns:
            Dictionary with health check results
        """
        if not self.config.provider_registry:
            return {}

        if provider_name:
            try:
                result = await self.config.provider_registry.check_health(provider_name)
                return {provider_name: result}
            except KeyError:
                return {}
        else:
            return await self.config.provider_registry.check_all_health()

    def get_providers_by_capability(self, capability: str) -> list[str]:
        """
        Get providers that support a specific capability.

        Args:
            capability: Capability to filter by (e.g., "streaming", "supports_streaming")

        Returns:
            List of provider names
        """
        if not self.config.provider_registry:
            return []

        # Normalize capability string
        cap_name = capability
        if cap_name.startswith("supports_"):
            cap_name = cap_name[len("supports_"):]

        capability_mapping = {
            "streaming": "streaming",
            "tools": "function_calling",
            "function_calling": "function_calling",
            "vision": "vision",
            "audio": "audio",
            "long_context": "long_context",
            "embeddings": "embeddings",
            "fine_tuning": "fine_tuning",
            "batch_processing": "batch_processing",
        }

        mapped_cap = capability_mapping.get(cap_name, cap_name)
        try:
            cap_enum = Capability(mapped_cap)
            return self.config.provider_registry.get_providers_by_capability(cap_enum)
        except ValueError:
            logger.warning(f"Unknown capability: {capability}")
            return []

    def find_providers_by_capability(self, capability: str, value: bool = True) -> list[str]:
        """
        Find providers by capability. Supports both Capability enum values
        and common capability strings like "supports_streaming", "supports_tools".

        Args:
            capability: Capability to filter by (e.g., "streaming", "supports_streaming")
            value: Required value (default True, ignored for compatibility)

        Returns:
            List of provider names
        """
        if not self.config.provider_registry:
            raise RuntimeError("Provider registry not configured")

        # Normalize capability string
        cap_name = capability
        if cap_name.startswith("supports_"):
            cap_name = cap_name[len("supports_"):]

        # Map common capability strings to Capability enum values
        capability_mapping = {
            "streaming": "streaming",
            "tools": "function_calling",
            "function_calling": "function_calling",
            "vision": "vision",
            "audio": "audio",
            "long_context": "long_context",
            "embeddings": "embeddings",
            "fine_tuning": "fine_tuning",
            "batch_processing": "batch_processing",
        }

        mapped_cap = capability_mapping.get(cap_name, cap_name)
        try:
            cap_enum = Capability(mapped_cap)
            providers = self.config.provider_registry.get_providers_by_capability(cap_enum)
            # If value=False, filter OUT providers that have the capability
            if not value:
                all_providers = self.config.provider_registry.get_all_providers()
                providers = [p for p in all_providers if p not in providers]
            return providers
        except ValueError:
            logger.warning(f"Unknown capability: {capability}")
            return []

    def list_providers(self) -> list[str]:
        """
        List all registered providers.

        Returns:
            List of provider names
        """
        if not self.config.provider_registry:
            return list(self.config.providers.keys())
        return self.config.provider_registry.get_all_providers()

    def get_provider_capabilities(self, provider_name: str, model_id: str | None = None) -> dict | None:
        """
        Get capabilities for a provider or specific model.

        Args:
            provider_name: Name of the provider
            model_id: Optional model ID for model-specific capabilities

        Returns:
            Dictionary of capabilities, or None if provider not found

        Raises:
            RuntimeError: If provider registry is not configured
        """
        if not self.config.provider_registry:
            raise RuntimeError("Provider registry not configured")

        metadata = self.get_provider_metadata(provider_name)
        if not metadata:
            return None

        # Map Capability enum values to feature strings
        capability_to_feature = {
            "streaming": "streaming",
            "function_calling": "tools",
            "vision": "vision",
            "audio": "audio",
            "long_context": "long_context",
            "embeddings": "embeddings",
            "fine_tuning": "fine_tuning",
            "batch_processing": "batch_processing",
        }

        if model_id:
            # Return model-specific capabilities
            # First check for stored model capabilities from discovery
            stored_model_caps = metadata.get("model_capabilities", {}).get(model_id)
            if stored_model_caps:
                return dict(stored_model_caps)

            # Fall back to building from provider-level capabilities
            model_caps = {}
            capabilities = metadata.get("capabilities", [])
            for cap in capabilities:
                feature_name = capability_to_feature.get(cap, cap)
                model_caps[f"supports_{feature_name}"] = True
            # Add max_context_tokens if available
            if "max_context_tokens" in metadata:
                model_caps["max_context_tokens"] = metadata["max_context_tokens"]
            return model_caps
        else:
            # Return provider-level capabilities
            features = []
            capabilities = metadata.get("capabilities", [])
            for cap in capabilities:
                feature_name = capability_to_feature.get(cap, cap)
                features.append(feature_name)

            return {
                "models": list(metadata.get("supported_models", [])),
                "features": features,
            }

    def get_provider_metadata(self, provider_name: str) -> dict | None:
        """
        Get metadata for a provider.

        Args:
            provider_name: Name of the provider

        Returns:
            Provider metadata as dictionary, or None if not found
        """
        if not self.config.provider_registry:
            return None

        metadata = self.config.provider_registry.get_metadata(provider_name)
        if metadata:
            # Convert to dictionary for easier consumption
            result = {
                'name': metadata.name,
                'provider_type': metadata.provider_type,
                'description': metadata.description,
                'capabilities': list(metadata.capabilities),
                'supported_models': list(metadata.supported_models),
                'avg_latency_ms': metadata.avg_latency_ms,
                'success_rate': metadata.success_rate,
                'status': metadata.status.value,
                'status_message': metadata.status_message,
                'last_checked': metadata.last_checked,
            }
            # Include model capabilities if available
            if metadata.model_capabilities:
                result['model_capabilities'] = {
                    model_id: dict(caps)
                    for model_id, caps in metadata.model_capabilities.items()
                }
            return result
        return None
