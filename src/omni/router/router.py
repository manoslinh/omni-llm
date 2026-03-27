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

from omni.models.provider import CompletionResult, Message, ModelProvider

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
from .strategy import RoutingStrategy

logger = logging.getLogger(__name__)


@dataclass
class RouterConfig:
    """Configuration for the ModelRouter."""

    # Default strategy to use if not specified per-task
    default_strategy: type[RoutingStrategy] | None = None

    # Strategy instances keyed by name
    strategies: dict[str, RoutingStrategy] = field(default_factory=dict)

    # Provider instances keyed by model ID or provider name
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


@dataclass
class RouterResult:
    """Result from a router invocation."""

    # The selected model ID
    model_id: str

    # The completion result
    completion: CompletionResult

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
        self._provider_cache: dict[str, ModelProvider] = {}
        self._cost_tracker: dict[str, float] = {}  # model_id -> total_cost

        # Health monitoring
        self._health_manager: HealthManager | None = None
        if config.health_config is not None:
            self._health_manager = HealthManager(config.health_config)

        # Initialize caches
        for name, strategy in config.strategies.items():
            self._strategy_cache[name] = strategy

        for model_id, provider in config.providers.items():
            self._provider_cache[model_id] = provider

        # Set default strategy if provided
        if config.default_strategy and not self._strategy_cache:
            try:
                default_instance = config.default_strategy()
                self._strategy_cache["default"] = default_instance
            except Exception as e:
                logger.warning(f"Failed to instantiate default strategy: {e}")

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
        Get a provider for a model ID.

        Args:
            model_id: Model identifier

        Returns:
            ModelProvider instance

        Raises:
            ValueError: If no provider found for the model
        """
        # Try exact match first
        if model_id in self._provider_cache:
            return self._provider_cache[model_id]

        # Try to find a provider that can handle this model
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
        messages: list[Message],
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
        self._provider_cache[model_id] = provider
