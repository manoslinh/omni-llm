"""
Tests for ModelRouter facade.

Validates:
- ModelRouter initialization and configuration
- Strategy selection and model ranking
- Fallback chain execution with retries
- Cost tracking and budget enforcement
- Error handling and recovery
- Integration with providers
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, "src")

from omni.models.provider import CompletionResult, Message, MessageRole, TokenUsage
from omni.router import (
    AllModelsFailedError,
    BudgetExceededError,
    CostEstimate,
    CostOptimizedStrategy,
    FallbackConfig,
    HealthConfig,
    ModelRouter,
    NoEligibleModelError,
    RouterConfig,
    RoutingContext,
    TaskType,
)

# ── Test Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_provider() -> MagicMock:
    """Create a mock model provider."""
    provider = MagicMock()
    provider.complete = AsyncMock()
    provider.__class__.__name__ = "MockProvider"
    return provider


@pytest.fixture
def mock_strategy() -> MagicMock:
    """Create a mock routing strategy."""
    strategy = MagicMock(spec=CostOptimizedStrategy)
    strategy.name = "mock_strategy"
    strategy.select_model = MagicMock()
    strategy.rank_models = MagicMock()
    strategy.estimate_cost = MagicMock(return_value=CostEstimate(100, 200, 0.005))
    return strategy


@pytest.fixture
def router_config(mock_provider: MagicMock, mock_strategy: MagicMock) -> RouterConfig:
    """Create a router configuration for testing."""
    # Create a second mock provider for backup model
    backup_provider = MagicMock()
    backup_provider.complete = AsyncMock()
    backup_provider.__class__.__name__ = "BackupProvider"

    return RouterConfig(
        strategies={"mock_strategy": mock_strategy},
        providers={"test-model": mock_provider, "backup-model": backup_provider},
        fallback_config=FallbackConfig(chain=["test-model", "backup-model"]),
        max_retries_per_model=2,
        backoff_base=0.01,  # Short for tests
        call_timeout=1.0,
    )


@pytest.fixture
def model_router(router_config: RouterConfig) -> ModelRouter:
    """Create a ModelRouter instance for testing."""
    return ModelRouter(router_config)


@pytest.fixture
def sample_messages() -> list[Message]:
    """Create sample chat messages."""
    return [
        Message(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
        Message(role=MessageRole.USER, content="Write a function to add two numbers."),
    ]


@pytest.fixture
def sample_context() -> RoutingContext:
    """Create sample routing context."""
    return RoutingContext(
        task_type=TaskType.CODING,
        file_count=1,
        complexity=0.5,
        budget_remaining=1.0,
    )


@pytest.fixture
def sample_completion() -> CompletionResult:
    """Create a sample completion result."""
    return CompletionResult(
        content="def add(a, b):\n    return a + b",
        model="test-model",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        finish_reason="stop",
    )


# ── Initialization Tests ───────────────────────────────────────────────────


class TestModelRouterInit:
    """Tests for ModelRouter initialization."""

    def test_valid_initialization(self, router_config: RouterConfig) -> None:
        """ModelRouter should initialize with valid config."""
        router = ModelRouter(router_config)
        assert router.config == router_config
        assert "mock_strategy" in router._strategy_cache
        assert "test-model" in router._provider_cache

    def test_default_strategy_instantiation(self) -> None:
        """ModelRouter should instantiate default strategy if provided."""
        config = RouterConfig(
            default_strategy=CostOptimizedStrategy,
            providers={},
        )
        router = ModelRouter(config)
        assert "default" in router._strategy_cache
        assert isinstance(router._strategy_cache["default"], CostOptimizedStrategy)

    def test_invalid_config_rejected(self) -> None:
        """ModelRouter should reject invalid configuration."""
        with pytest.raises(ValueError, match="max_retries_per_model must be >= 0"):
            RouterConfig(max_retries_per_model=-1)

        with pytest.raises(ValueError, match="backoff_base must be > 0"):
            RouterConfig(backoff_base=0.0)

        with pytest.raises(ValueError, match="call_timeout must be > 0"):
            RouterConfig(call_timeout=0.0)

    def test_empty_config_allowed(self) -> None:
        """ModelRouter should allow empty configuration."""
        config = RouterConfig()
        router = ModelRouter(config)
        assert router._strategy_cache == {}
        assert router._provider_cache == {}


# ── Strategy Management Tests ──────────────────────────────────────────────


class TestStrategyManagement:
    """Tests for strategy registration and retrieval."""

    def test_get_strategy_by_name(
        self, model_router: ModelRouter, mock_strategy: MagicMock
    ) -> None:
        """Should retrieve strategy by name."""
        strategy = model_router.get_strategy("mock_strategy")
        assert strategy == mock_strategy

    def test_get_strategy_default(
        self, model_router: ModelRouter, mock_strategy: MagicMock
    ) -> None:
        """Should retrieve default strategy when name is None."""
        strategy = model_router.get_strategy()
        assert strategy == mock_strategy

    def test_get_strategy_not_found(self, model_router: ModelRouter) -> None:
        """Should raise ValueError for unknown strategy."""
        with pytest.raises(ValueError, match="Strategy 'unknown' not found"):
            model_router.get_strategy("unknown")

    def test_get_strategy_no_default(self) -> None:
        """Should raise ValueError when no default strategy available."""
        config = RouterConfig()
        router = ModelRouter(config)
        with pytest.raises(
            ValueError,
            match="No default strategy specified and multiple strategies available",
        ):
            router.get_strategy()

    def test_register_strategy(self, model_router: ModelRouter) -> None:
        """Should register a new strategy."""
        new_strategy = MagicMock()
        new_strategy.name = "new_strategy"
        model_router.register_strategy("new_strategy", new_strategy)
        assert model_router.get_strategy("new_strategy") == new_strategy


# ── Provider Management Tests ──────────────────────────────────────────────


class TestProviderManagement:
    """Tests for provider registration and retrieval."""

    def test_get_provider_by_name(
        self, model_router: ModelRouter, mock_provider: MagicMock
    ) -> None:
        """Should retrieve provider by model ID."""
        provider = model_router.get_provider("test-model")
        assert provider == mock_provider

    def test_get_provider_not_found(self, model_router: ModelRouter) -> None:
        """Should raise ValueError for unknown provider."""
        with pytest.raises(ValueError, match="No provider found for model 'unknown'"):
            model_router.get_provider("unknown")

    def test_register_provider(self, model_router: ModelRouter) -> None:
        """Should register a new provider."""
        new_provider = MagicMock()
        model_router.register_provider("new-model", new_provider)
        assert model_router.get_provider("new-model") == new_provider


# ── Model Selection Tests ──────────────────────────────────────────────────


class TestModelSelection:
    """Tests for model selection functionality."""

    def test_select_model_success(
        self,
        model_router: ModelRouter,
        mock_strategy: MagicMock,
        sample_context: RoutingContext,
    ) -> None:
        """Should select a model using the specified strategy."""
        from omni.router.models import CostEstimate, ModelSelection

        mock_selection = ModelSelection(
            model_id="test-model",
            reason="Test selection",
            estimated_cost=CostEstimate(100, 200, 0.005),
            confidence=0.9,
        )
        mock_strategy.select_model.return_value = mock_selection

        result = model_router.select_model(TaskType.CODING, sample_context)
        assert result == mock_selection
        mock_strategy.select_model.assert_called_once_with(
            TaskType.CODING, sample_context
        )

    def test_select_model_no_strategy(
        self, sample_context: RoutingContext
    ) -> None:
        """Should raise error when no strategy available."""
        config = RouterConfig()
        router = ModelRouter(config)
        with pytest.raises(ValueError):
            router.select_model(TaskType.CODING, sample_context)

    def test_select_model_no_eligible_model(
        self,
        model_router: ModelRouter,
        mock_strategy: MagicMock,
        sample_context: RoutingContext,
    ) -> None:
        """Should raise NoEligibleModelError when strategy returns None."""
        mock_strategy.select_model.return_value = None
        with pytest.raises(NoEligibleModelError):
            model_router.select_model(TaskType.CODING, sample_context)

    def test_rank_models(
        self,
        model_router: ModelRouter,
        mock_strategy: MagicMock,
        sample_context: RoutingContext,
    ) -> None:
        """Should rank models using the specified strategy."""
        from omni.router.models import CostEstimate, RankedModel

        mock_ranked = [
            RankedModel(
                model_id="test-model",
                score=0.9,
                cost_estimate=CostEstimate(100, 200, 0.005),
                quality_estimate=0.95,
            )
        ]
        mock_strategy.rank_models.return_value = mock_ranked

        result = model_router.rank_models(TaskType.CODING, sample_context)
        assert result == mock_ranked
        mock_strategy.rank_models.assert_called_once_with(
            TaskType.CODING, sample_context
        )

    def test_estimate_cost(
        self,
        model_router: ModelRouter,
        mock_strategy: MagicMock,
        sample_context: RoutingContext,
    ) -> None:
        """Should estimate cost using the specified strategy."""
        from omni.router.models import CostEstimate

        mock_estimate = CostEstimate(100, 200, 0.005)
        mock_strategy.estimate_cost.return_value = mock_estimate

        result = model_router.estimate_cost(
            TaskType.CODING, "test-model", sample_context
        )
        assert result == mock_estimate
        mock_strategy.estimate_cost.assert_called_once_with(
            TaskType.CODING, "test-model", sample_context
        )


# ── Completion Tests ───────────────────────────────────────────────────────


class TestCompletion:
    """Tests for the complete() method with fallback handling."""

    @pytest.mark.asyncio
    async def test_completion_success(
        self,
        model_router: ModelRouter,
        mock_provider: MagicMock,
        mock_strategy: MagicMock,
        sample_messages: list[Message],
        sample_context: RoutingContext,
        sample_completion: CompletionResult,
    ) -> None:
        """Should successfully complete with first model in chain."""
        # Mock the strategy to return ranked models
        from omni.router.models import CostEstimate, RankedModel

        mock_ranked = [
            RankedModel(
                model_id="test-model",
                score=0.9,
                cost_estimate=CostEstimate(100, 200, 0.005),
                quality_estimate=0.95,
            )
        ]
        mock_strategy.rank_models.return_value = mock_ranked
        mock_strategy.estimate_cost.return_value = CostEstimate(100, 200, 0.005)

        # Mock provider to return success
        mock_provider.complete.return_value = sample_completion

        result = await model_router.complete(
            sample_messages, TaskType.CODING, sample_context
        )

        assert result.model_id == "test-model"
        assert result.completion == sample_completion
        assert result.total_cost_usd == 0.005
        assert result.provider_name == "MockProvider"
        assert result.strategy_name == "mock_strategy"
        assert result.retries == 0
        assert result.errors == []

        mock_provider.complete.assert_called_once()
        call_kwargs = mock_provider.complete.call_args[1]
        assert call_kwargs["model"] == "test-model"
        assert call_kwargs["messages"] == sample_messages

    @pytest.mark.asyncio
    async def test_completion_with_fallback(
        self,
        model_router: ModelRouter,
        mock_strategy: MagicMock,
        sample_messages: list[Message],
        sample_context: RoutingContext,
        sample_completion: CompletionResult,
    ) -> None:
        """Should fall back to second model when first fails."""
        # Get the providers from the router
        test_provider = model_router.get_provider("test-model")
        backup_provider = model_router.get_provider("backup-model")

        # First provider fails, backup succeeds
        test_provider.complete.side_effect = RuntimeError("First model failed")
        backup_provider.complete.return_value = sample_completion

        # Mock cost estimation
        mock_strategy.estimate_cost.return_value = CostEstimate(100, 200, 0.005)

        result = await model_router.complete(
            sample_messages, TaskType.CODING, sample_context
        )

        # Should have used backup-model (second in chain)
        assert result.model_id == "backup-model"
        # With max_retries_per_model=2, we get 3 attempts (initial + 2 retries)
        assert len(result.errors) == 3
        assert all("First model failed" in str(e) for e in result.errors)
        assert test_provider.complete.call_count == 3  # 3 attempts on test-model
        assert backup_provider.complete.call_count == 1  # 1 successful attempt on backup-model

    @pytest.mark.asyncio
    async def test_completion_all_models_fail(
        self,
        model_router: ModelRouter,
        sample_messages: list[Message],
        sample_context: RoutingContext,
    ) -> None:
        """Should raise AllModelsFailedError when all models fail."""
        # Get both providers
        test_provider = model_router.get_provider("test-model")
        backup_provider = model_router.get_provider("backup-model")

        # Both providers fail
        test_provider.complete.side_effect = RuntimeError("Test model failed")
        backup_provider.complete.side_effect = RuntimeError("Backup model failed")

        with pytest.raises(AllModelsFailedError) as exc_info:
            await model_router.complete(
                sample_messages, TaskType.CODING, sample_context
            )

        assert "test-model" in str(exc_info.value)
        assert "backup-model" in str(exc_info.value)
        assert "Backup model failed" in str(exc_info.value.last_error)

    @pytest.mark.asyncio
    async def test_completion_budget_exceeded(
        self,
        model_router: ModelRouter,
        mock_strategy: MagicMock,
        sample_messages: list[Message],
    ) -> None:
        """Should skip models that exceed budget."""
        # Create context with very small budget
        context = RoutingContext(
            task_type=TaskType.CODING,
            file_count=1,
            complexity=0.5,
            budget_remaining=0.001,  # Very small budget
        )

        # Mock cost estimation to exceed budget
        from omni.router.models import CostEstimate

        mock_strategy.estimate_cost.return_value = CostEstimate(100, 200, 0.005)

        # Should raise AllModelsFailedError because all models exceed budget
        with pytest.raises(AllModelsFailedError) as exc_info:
            await model_router.complete(sample_messages, TaskType.CODING, context)

        # Should contain BudgetExceededError as last_error
        # When budget is exceeded for all models, the last error will be BudgetExceededError
        assert isinstance(exc_info.value.last_error, BudgetExceededError)

    @pytest.mark.asyncio
    async def test_completion_with_retries(
        self,
        model_router: ModelRouter,
        mock_provider: MagicMock,
        sample_messages: list[Message],
        sample_context: RoutingContext,
        sample_completion: CompletionResult,
    ) -> None:
        """Should retry failed calls with exponential backoff."""
        # First two calls fail, third succeeds
        mock_provider.complete.side_effect = [
            RuntimeError("First attempt"),
            RuntimeError("Second attempt"),
            sample_completion,
        ]

        result = await model_router.complete(
            sample_messages, TaskType.CODING, sample_context
        )

        assert result.model_id == "test-model"
        assert result.retries == 2  # Two retries before success
        assert len(result.errors) == 2
        assert mock_provider.complete.call_count == 3

    @pytest.mark.asyncio
    async def test_completion_timeout(
        self,
        model_router: ModelRouter,
        sample_messages: list[Message],
        sample_context: RoutingContext,
    ) -> None:
        """Should handle timeout errors."""
        # Get the providers
        test_provider = model_router.get_provider("test-model")
        backup_provider = model_router.get_provider("backup-model")

        # Both providers timeout
        test_provider.complete.side_effect = TimeoutError("Request timed out")
        backup_provider.complete.side_effect = TimeoutError("Request timed out")

        with pytest.raises(AllModelsFailedError) as exc_info:
            await model_router.complete(
                sample_messages, TaskType.CODING, sample_context
            )

        # Check that timeout error is in the exception chain
        assert exc_info.value.last_error is not None
        assert "timed out" in str(exc_info.value.last_error).lower()

    @pytest.mark.asyncio
    async def test_completion_custom_fallback_chain(
        self,
        model_router: ModelRouter,
        sample_messages: list[Message],
        sample_context: RoutingContext,
        sample_completion: CompletionResult,
    ) -> None:
        """Should use custom fallback chain when provided."""
        # Register providers for custom models
        custom_provider1 = MagicMock()
        custom_provider1.complete = AsyncMock(return_value=sample_completion)
        custom_provider1.__class__.__name__ = "CustomProvider1"

        custom_provider2 = MagicMock()
        custom_provider2.complete = AsyncMock()
        custom_provider2.__class__.__name__ = "CustomProvider2"

        model_router.register_provider("custom-model-1", custom_provider1)
        model_router.register_provider("custom-model-2", custom_provider2)

        custom_chain = ["custom-model-1", "custom-model-2"]
        result = await model_router.complete(
            sample_messages,
            TaskType.CODING,
            sample_context,
            fallback_chain=custom_chain,
        )

        # Should have used custom-model-1 (first in custom chain)
        assert result.model_id == "custom-model-1"
        assert custom_provider1.complete.call_count == 1
        assert custom_provider2.complete.call_count == 0

    @pytest.mark.asyncio
    async def test_completion_dynamic_fallback_chain(
        self,
        model_router: ModelRouter,
        mock_strategy: MagicMock,
        sample_messages: list[Message],
        sample_context: RoutingContext,
        sample_completion: CompletionResult,
    ) -> None:
        """Should build fallback chain from ranked models when no chain specified."""
        # Remove fallback chain from config
        model_router.config.fallback_config.chain = []

        # Register providers for ranked models
        ranked_provider1 = MagicMock()
        ranked_provider1.complete = AsyncMock(return_value=sample_completion)
        ranked_provider1.__class__.__name__ = "RankedProvider1"

        ranked_provider2 = MagicMock()
        ranked_provider2.complete = AsyncMock()
        ranked_provider2.__class__.__name__ = "RankedProvider2"

        model_router.register_provider("ranked-1", ranked_provider1)
        model_router.register_provider("ranked-2", ranked_provider2)

        # Mock ranked models
        from omni.router.models import CostEstimate, RankedModel

        mock_ranked = [
            RankedModel(
                model_id="ranked-1",
                score=0.9,
                cost_estimate=CostEstimate(100, 200, 0.005),
                quality_estimate=0.95,
            ),
            RankedModel(
                model_id="ranked-2",
                score=0.8,
                cost_estimate=CostEstimate(100, 200, 0.006),
                quality_estimate=0.9,
            ),
        ]
        mock_strategy.rank_models.return_value = mock_ranked
        mock_strategy.estimate_cost.return_value = CostEstimate(100, 200, 0.005)

        result = await model_router.complete(
            sample_messages, TaskType.CODING, sample_context
        )

        # Should have used ranked-1 (first in ranked list)
        assert result.model_id == "ranked-1"
        assert ranked_provider1.complete.call_count == 1
        assert ranked_provider2.complete.call_count == 0


# ── Cost Tracking Tests ────────────────────────────────────────────────────


class TestCostTracking:
    """Tests for cost tracking functionality."""

    def test_get_total_cost_empty(self, model_router: ModelRouter) -> None:
        """Should return 0 when no costs tracked."""
        assert model_router.get_total_cost() == 0.0

    def test_get_total_cost_by_model(self, model_router: ModelRouter) -> None:
        """Should return cost for specific model."""
        # Simulate some costs
        model_router._cost_tracker = {"model-a": 0.5, "model-b": 0.3}
        assert model_router.get_total_cost("model-a") == 0.5
        assert model_router.get_total_cost("model-b") == 0.3
        assert model_router.get_total_cost("model-c") == 0.0

    def test_get_total_cost_all(self, model_router: ModelRouter) -> None:
        """Should return sum of all costs."""
        model_router._cost_tracker = {"model-a": 0.5, "model-b": 0.3, "model-c": 0.2}
        assert model_router.get_total_cost() == 1.0

    def test_reset_cost_tracking(self, model_router: ModelRouter) -> None:
        """Should reset cost tracker."""
        model_router._cost_tracker = {"model-a": 0.5, "model-b": 0.3}
        model_router.reset_cost_tracking()
        assert model_router._cost_tracker == {}
        assert model_router.get_total_cost() == 0.0

    @pytest.mark.asyncio
    async def test_cost_tracking_disabled(
        self,
        mock_provider: MagicMock,
        mock_strategy: MagicMock,
        sample_messages: list[Message],
        sample_context: RoutingContext,
        sample_completion: CompletionResult,
    ) -> None:
        """Should not track costs when disabled."""
        config = RouterConfig(
            strategies={"mock_strategy": mock_strategy},
            providers={"test-model": mock_provider},
            fallback_config=FallbackConfig(chain=["test-model"]),  # Explicit chain
            enable_cost_tracking=False,
        )
        router = ModelRouter(config)

        mock_provider.complete.return_value = sample_completion
        mock_strategy.estimate_cost.return_value = CostEstimate(100, 200, 0.005)

        result = await router.complete(
            sample_messages, TaskType.CODING, sample_context
        )

        assert result.total_cost_usd == 0.0
        assert router.get_total_cost() == 0.0


# ── Integration Tests ──────────────────────────────────────────────────────


class TestIntegration:
    """Integration tests for ModelRouter with real components."""

    def test_with_real_cost_optimized_strategy(self) -> None:
        """Should work with real CostOptimizedStrategy."""
        config = RouterConfig(
            default_strategy=CostOptimizedStrategy,
            providers={},
        )
        router = ModelRouter(config)

        strategy = router.get_strategy()
        assert isinstance(strategy, CostOptimizedStrategy)
        assert strategy.name == "cost_optimized"

    @pytest.mark.asyncio
    async def test_end_to_end_with_mocks(
        self,
        mock_provider: MagicMock,
        sample_messages: list[Message],
        sample_completion: CompletionResult,
    ) -> None:
        """End-to-end test with mocked components."""
        # Create real strategy
        strategy = CostOptimizedStrategy()

        # Configure router
        config = RouterConfig(
            strategies={"cost_optimized": strategy},
            providers={"deepseek-chat": mock_provider},
            fallback_config=FallbackConfig(chain=["deepseek-chat", "gpt-4o-mini"]),
        )
        router = ModelRouter(config)

        # Mock provider response
        mock_provider.complete.return_value = sample_completion

        # Create context
        context = RoutingContext(
            task_type=TaskType.CODING,
            file_count=1,
            complexity=0.5,
            budget_remaining=1.0,
        )

        # Execute
        result = await router.complete(sample_messages, TaskType.CODING, context)

        # Verify
        assert result.model_id == "deepseek-chat"
        assert result.completion == sample_completion
        assert result.provider_name == "MockProvider"
        assert result.strategy_name == "cost_optimized"


# ── Error Handling Tests ───────────────────────────────────────────────────


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    def test_strategy_methods_propagate_errors(
        self,
        model_router: ModelRouter,
        mock_strategy: MagicMock,
        sample_context: RoutingContext,
    ) -> None:
        """Should propagate errors from strategy methods."""
        # Test select_model error
        mock_strategy.select_model.side_effect = NoEligibleModelError(
            "coding", "No models available"
        )
        with pytest.raises(NoEligibleModelError):
            model_router.select_model(TaskType.CODING, sample_context)

        # Test estimate_cost error
        mock_strategy.estimate_cost.side_effect = ValueError("Invalid model")
        with pytest.raises(ValueError):
            model_router.estimate_cost(TaskType.CODING, "invalid", sample_context)

    def test_provider_not_found_in_fallback(
        self,
        model_router: ModelRouter,
        sample_messages: list[Message],
        sample_context: RoutingContext,
    ) -> None:
        """Should handle missing providers in fallback chain gracefully."""
        # Use a model that has no provider
        model_router.config.fallback_config.chain = ["unknown-model"]

        # Should raise AllModelsFailedError
        with pytest.raises(AllModelsFailedError) as exc_info:
            asyncio.run(
                model_router.complete(sample_messages, TaskType.CODING, sample_context)
            )

        assert "unknown-model" in str(exc_info.value)

    def test_empty_fallback_chain(
        self,
        model_router: ModelRouter,
        mock_strategy: MagicMock,
        sample_messages: list[Message],
        sample_context: RoutingContext,
    ) -> None:
        """Should handle empty fallback chain."""
        # Empty chain and no ranked models
        model_router.config.fallback_config.chain = []
        mock_strategy.rank_models.return_value = []

        with pytest.raises(AllModelsFailedError) as exc_info:
            asyncio.run(
                model_router.complete(sample_messages, TaskType.CODING, sample_context)
            )

        assert "All models failed" in str(exc_info.value)


# ── Performance and Concurrency Tests ──────────────────────────────────────


class TestPerformance:
    """Tests for performance and concurrency aspects."""

    @pytest.mark.asyncio
    async def test_concurrent_completions(
        self,
        model_router: ModelRouter,
        mock_provider: MagicMock,
        sample_messages: list[Message],
        sample_context: RoutingContext,
        sample_completion: CompletionResult,
    ) -> None:
        """Should handle concurrent completion requests."""
        mock_provider.complete.return_value = sample_completion

        # Run multiple completions concurrently
        tasks = [
            model_router.complete(sample_messages, TaskType.CODING, sample_context)
            for _ in range(5)
        ]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for result in results:
            assert result.model_id == "test-model"
            assert result.completion == sample_completion

        # Provider should have been called 5 times
        assert mock_provider.complete.call_count == 5

    @pytest.mark.asyncio
    async def test_backoff_respect(
        self,
        model_router: ModelRouter,
        mock_provider: MagicMock,
        sample_messages: list[Message],
        sample_context: RoutingContext,
        sample_completion: CompletionResult,
    ) -> None:
        """Should respect backoff timing between retries."""
        import time

        # First call fails, second succeeds
        call_times = []

        def track_time(*args, **kwargs):
            call_times.append(time.time())
            if len(call_times) == 1:
                raise RuntimeError("First attempt")
            return sample_completion

        mock_provider.complete.side_effect = track_time

        await model_router.complete(
            sample_messages, TaskType.CODING, sample_context
        )

        # Should have waited ~0.01s (backoff_base) between attempts
        if len(call_times) >= 2:
            wait_time = call_times[1] - call_times[0]
            # Allow some tolerance
            assert 0.005 <= wait_time <= 0.02


# ── Configuration Tests ────────────────────────────────────────────────────


class TestConfiguration:
    """Tests for router configuration and validation."""

    def test_router_config_defaults(self) -> None:
        """RouterConfig should have sensible defaults."""
        config = RouterConfig()
        assert config.default_strategy is None
        assert config.strategies == {}
        assert config.providers == {}
        assert config.fallback_config == FallbackConfig()
        assert config.max_retries_per_model == 3
        assert config.backoff_base == 1.0
        assert config.call_timeout == 60.0
        assert config.enable_cost_tracking is True

    def test_router_config_custom_values(self) -> None:
        """RouterConfig should accept custom values."""
        fallback = FallbackConfig(chain=["a", "b"], max_retries=5)
        config = RouterConfig(
            strategies={"s": MagicMock()},
            providers={"p": MagicMock()},
            fallback_config=fallback,
            max_retries_per_model=10,
            backoff_base=2.0,
            call_timeout=120.0,
            enable_cost_tracking=False,
        )
        assert config.max_retries_per_model == 10
        assert config.backoff_base == 2.0
        assert config.call_timeout == 120.0
        assert config.enable_cost_tracking is False
        assert config.fallback_config == fallback


# ── Health Monitoring Integration Tests ────────────────────────────────────


class TestHealthIntegration:
    """Tests for health monitoring integration with ModelRouter."""

    @pytest.fixture
    def health_config(self) -> HealthConfig:
        """Fast health config for testing."""
        return HealthConfig(
            window_size=20,
            window_duration_seconds=60.0,
            error_rate_threshold=0.5,
            latency_threshold_seconds=5.0,
            min_requests_for_threshold=3,
            recovery_timeout_seconds=0.5,
            half_open_max_requests=2,
            half_open_success_threshold=1,
        )

    @pytest.fixture
    def healthy_router(self, health_config: HealthConfig) -> tuple[ModelRouter, MagicMock]:
        """Router with health monitoring enabled."""
        mock_strategy = MagicMock()
        mock_strategy.name = "mock-strategy"
        mock_strategy.rank_models.return_value = [
            MagicMock(model_id="model-a", score=0.9),
            MagicMock(model_id="model-b", score=0.5),
        ]
        mock_strategy.estimate_cost.return_value = CostEstimate(
            input_tokens=100, output_tokens=50, total_cost_usd=0.001
        )

        provider_a = MagicMock()
        provider_a.__class__.__name__ = "ProviderA"
        provider_a.complete = AsyncMock(
            return_value=CompletionResult(
                content="Success from A",
                model="model-a",
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            )
        )

        provider_b = MagicMock()
        provider_b.__class__.__name__ = "ProviderB"
        provider_b.complete = AsyncMock(
            return_value=CompletionResult(
                content="Success from B",
                model="model-b",
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            )
        )

        config = RouterConfig(
            strategies={"mock": mock_strategy},
            providers={"model-a": provider_a, "model-b": provider_b},
            health_config=health_config,
            max_retries_per_model=1,
            backoff_base=0.01,
            call_timeout=10.0,
        )
        router = ModelRouter(config)
        return router, mock_strategy

    def test_health_manager_initialized(self, healthy_router: tuple[ModelRouter, MagicMock]) -> None:
        """HealthManager should be initialized when health_config is set."""
        router, _ = healthy_router
        assert router._health_manager is not None

    def test_no_health_manager_without_config(self) -> None:
        """HealthManager should be None without health_config."""
        config = RouterConfig()
        router = ModelRouter(config)
        assert router._health_manager is None

    @pytest.mark.asyncio
    async def test_records_success_on_completion(
        self, healthy_router: tuple[ModelRouter, MagicMock]
    ) -> None:
        """Should record health success after successful completion."""
        router, strategy = healthy_router
        context = RoutingContext(task_type=TaskType.CODING)

        result = await router.complete(
            messages=[],
            task_type=TaskType.CODING,
            context=context,
            fallback_chain=["model-a"],
        )

        assert result.model_id == "model-a"
        metrics = router._health_manager.monitor.get_metrics("model-a")
        assert metrics.successful_requests == 1

    @pytest.mark.asyncio
    async def test_records_failure_on_error(
        self, healthy_router: tuple[ModelRouter, MagicMock]
    ) -> None:
        """Should record health failure after provider error."""
        router, _ = healthy_router
        # Make provider A fail
        router._provider_cache["model-a"].complete.side_effect = RuntimeError("Provider down")
        context = RoutingContext(task_type=TaskType.CODING)

        result = await router.complete(
            messages=[],
            task_type=TaskType.CODING,
            context=context,
            fallback_chain=["model-a", "model-b"],
        )

        # Should have fallen back to model-b
        assert result.model_id == "model-b"
        # model-a should have recorded failure via breaker
        breaker = router._health_manager.get_breaker("model-a")
        assert breaker._failure_count > 0

    @pytest.mark.asyncio
    async def test_skips_open_circuit(
        self, healthy_router: tuple[ModelRouter, MagicMock]
    ) -> None:
        """Should skip providers with OPEN circuit breaker."""
        router, _ = healthy_router
        context = RoutingContext(task_type=TaskType.CODING)

        # Force model-a's circuit open
        breaker = router._health_manager.get_breaker("model-a")
        for _ in range(3):
            breaker.record_failure()

        result = await router.complete(
            messages=[],
            task_type=TaskType.CODING,
            context=context,
            fallback_chain=["model-a", "model-b"],
        )

        # Should skip model-a and use model-b
        assert result.model_id == "model-b"
        # model-a's provider should not have been called
        router._provider_cache["model-a"].complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_circuits_open_raises(
        self, healthy_router: tuple[ModelRouter, MagicMock]
    ) -> None:
        """Should raise AllModelsFailedError when all circuits are open."""
        router, _ = healthy_router
        context = RoutingContext(task_type=TaskType.CODING)

        # Force all circuits open
        for model_id in ["model-a", "model-b"]:
            breaker = router._health_manager.get_breaker(model_id)
            for _ in range(3):
                breaker.record_failure()

        with pytest.raises(AllModelsFailedError):
            await router.complete(
                messages=[],
                task_type=TaskType.CODING,
                context=context,
                fallback_chain=["model-a", "model-b"],
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
