"""
Tests for Provider Registry & Capability Discovery.
"""


import pytest

from omni.providers.base import CostRate
from omni.router.provider_registry import ModelProvider
from omni.router.provider_registry import (
    Capability,
    ProviderHealthCheck,
    ProviderMetadata,
    ProviderRegistry,
    ProviderStatus,
)


class MockProvider(ModelProvider):
    """Mock provider for testing."""

    def __init__(self, name="test-provider", supports_streaming=True):
        self._name = name
        self._supports_streaming = supports_streaming
        self._cost_per_token = {
            "model-1": CostRate(input_per_million=1.0, output_per_million=2.0),
            "model-2": CostRate(input_per_million=0.5, output_per_million=1.0),
        }

    @property
    def name(self) -> str:
        return self._name

    @property
    def supports_streaming(self) -> bool:
        return self._supports_streaming

    @property
    def cost_per_token(self) -> dict[str, CostRate]:
        return self._cost_per_token

    async def chat_completion(self, messages, model, temperature=0.7, max_tokens=None, **kwargs):
        # Mock implementation
        from omni.providers.base import ChatCompletion, TokenUsage
        return ChatCompletion(
            content="Mock response",
            model=model,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            finish_reason="stop"
        )
    
    async def stream_chat_completion(self, messages, model, temperature=0.7, max_tokens=None, **kwargs):
        # Mock implementation
        async def _stream():
            yield "Mock stream response"
        
        async for chunk in _stream():
            yield chunk

    def count_tokens(self, text: str, model: str) -> int:
        """Count tokens in text for a specific model."""
        # Simple mock: assume 4 characters per token
        return len(text) // 4

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Estimate cost for given token counts."""
        if model in self._cost_per_token:
            rate = self._cost_per_token[model]
            input_cost = (input_tokens / 1_000_000) * rate.input_per_million
            output_cost = (output_tokens / 1_000_000) * rate.output_per_million
            return input_cost + output_cost
        return 0.0

    async def close(self) -> None:
        """Close the provider."""
        pass  # Nothing to close in mock


class TestProviderMetadata:
    """Tests for ProviderMetadata dataclass."""

    def test_basic_metadata(self):
        """Test basic metadata creation."""
        metadata = ProviderMetadata(
            name="test-provider",
            provider_type="mock",
            description="Test provider",
            capabilities={Capability.STREAMING, Capability.FUNCTION_CALLING},
            supported_models={"model-1", "model-2"},
            avg_latency_ms=100.0,
            success_rate=0.95,
            status=ProviderStatus.HEALTHY,
        )

        assert metadata.name == "test-provider"
        assert metadata.provider_type == "mock"
        assert metadata.description == "Test provider"
        assert Capability.STREAMING in metadata.capabilities
        assert Capability.FUNCTION_CALLING in metadata.capabilities
        assert "model-1" in metadata.supported_models
        assert metadata.avg_latency_ms == 100.0
        assert metadata.success_rate == 0.95
        assert metadata.status == ProviderStatus.HEALTHY

    def test_metadata_validation(self):
        """Test metadata field validation."""
        # Test invalid success rate
        with pytest.raises(ValueError, match="success_rate must be between 0.0 and 1.0"):
            ProviderMetadata(
                name="test",
                provider_type="mock",
                success_rate=1.5  # Invalid
            )

        # Test invalid latency
        with pytest.raises(ValueError, match="avg_latency_ms must be >= 0"):
            ProviderMetadata(
                name="test",
                provider_type="mock",
                avg_latency_ms=-10.0  # Invalid
            )

        # Test empty name
        with pytest.raises(ValueError, match="Provider name cannot be empty"):
            ProviderMetadata(name="", provider_type="mock")


class TestProviderRegistry:
    """Tests for ProviderRegistry class."""

    @pytest.fixture
    def registry(self):
        """Create a fresh ProviderRegistry for each test."""
        return ProviderRegistry()

    @pytest.fixture
    def mock_provider(self):
        """Create a mock provider."""
        return MockProvider(name="test-provider")

    @pytest.fixture
    def mock_provider_with_metadata(self):
        """Create a mock provider with custom metadata."""
        provider = MockProvider(name="test-provider-2")
        metadata = ProviderMetadata(
            name="test-provider-2",
            provider_type="mock",
            description="Custom metadata",
            capabilities={Capability.VISION, Capability.LONG_CONTEXT},
            supported_models={"special-model"},
        )
        return provider, metadata

    def test_initialization(self, registry):
        """Test registry initialization."""
        assert len(registry.get_all_providers()) == 0
        assert len(registry.get_all_models()) == 0

    def test_register_provider(self, registry, mock_provider):
        """Test registering a provider."""
        registry.register(mock_provider)

        assert "test-provider" in registry.get_all_providers()
        assert registry.get_provider("test-provider") == mock_provider

        # Check that capabilities were discovered
        metadata = registry.get_metadata("test-provider")
        assert metadata is not None
        assert Capability.STREAMING in metadata.capabilities
        assert "model-1" in metadata.supported_models
        assert "model-2" in metadata.supported_models

    def test_register_provider_with_metadata(self, registry, mock_provider_with_metadata):
        """Test registering a provider with custom metadata."""
        provider, metadata = mock_provider_with_metadata
        registry.register(provider, metadata=metadata)

        assert "test-provider-2" in registry.get_all_providers()

        # Check that custom metadata was used
        stored_metadata = registry.get_metadata("test-provider-2")
        assert stored_metadata.description == "Custom metadata"
        assert Capability.VISION in stored_metadata.capabilities
        assert Capability.LONG_CONTEXT in stored_metadata.capabilities
        assert "special-model" in stored_metadata.supported_models

    def test_register_duplicate_provider(self, registry, mock_provider):
        """Test that duplicate registration raises error."""
        registry.register(mock_provider)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(mock_provider)

    def test_unregister_provider(self, registry, mock_provider):
        """Test unregistering a provider."""
        registry.register(mock_provider)
        assert "test-provider" in registry.get_all_providers()

        registry.unregister("test-provider")
        assert "test-provider" not in registry.get_all_providers()
        assert registry.get_provider("test-provider") is None
        assert registry.get_metadata("test-provider") is None

    def test_unregister_nonexistent_provider(self, registry):
        """Test unregistering a non-existent provider."""
        with pytest.raises(KeyError, match="is not registered"):
            registry.unregister("nonexistent")

    def test_get_providers_by_capability(self, registry, mock_provider):
        """Test getting providers by capability."""
        registry.register(mock_provider)

        providers = registry.get_providers_by_capability(Capability.STREAMING)
        assert "test-provider" in providers

        # Test with non-existent capability
        providers = registry.get_providers_by_capability(Capability.VISION)
        assert len(providers) == 0

    def test_get_providers_by_capability_with_filters(self, registry, mock_provider):
        """Test getting providers by capability with performance filters."""
        registry.register(mock_provider)

        # Update metadata with specific performance metrics
        registry.update_metadata(
            "test-provider",
            avg_latency_ms=2000.0,  # 2 seconds - high latency
            success_rate=0.5,  # Low success rate
        )

        # Should not return provider with low success rate filter
        providers = registry.get_providers_by_capability(
            Capability.STREAMING,
            min_success_rate=0.8,
        )
        assert len(providers) == 0

        # Should return provider with relaxed filters
        providers = registry.get_providers_by_capability(
            Capability.STREAMING,
            min_success_rate=0.3,
            max_latency_ms=3000.0,
        )
        assert "test-provider" in providers

    def test_get_providers_for_model(self, registry, mock_provider):
        """Test getting providers that support a specific model."""
        registry.register(mock_provider)

        providers = registry.get_providers_for_model("model-1")
        assert "test-provider" in providers

        providers = registry.get_providers_for_model("model-2")
        assert "test-provider" in providers

        # Test with non-existent model
        providers = registry.get_providers_for_model("nonexistent-model")
        assert len(providers) == 0

    def test_get_providers_for_model_with_filters(self, registry, mock_provider):
        """Test getting providers for model with performance filters."""
        registry.register(mock_provider)

        # Update metadata with specific performance metrics
        registry.update_metadata(
            "test-provider",
            avg_latency_ms=500.0,
            success_rate=0.9,
        )

        # Should return provider with good metrics
        providers = registry.get_providers_for_model(
            "model-1",
            min_success_rate=0.8,
            max_latency_ms=1000.0,
        )
        assert "test-provider" in providers

        # Should not return provider with strict filters
        providers = registry.get_providers_for_model(
            "model-1",
            min_success_rate=0.95,  # Too high
            max_latency_ms=100.0,   # Too low
        )
        assert len(providers) == 0

    def test_get_all_models(self, registry, mock_provider):
        """Test getting all supported models."""
        registry.register(mock_provider)

        models = registry.get_all_models()
        assert "model-1" in models
        assert "model-2" in models
        assert len(models) == 2

    def test_update_metadata(self, registry, mock_provider):
        """Test updating provider metadata."""
        registry.register(mock_provider)

        # Update metadata
        registry.update_metadata(
            "test-provider",
            description="Updated description",
            avg_latency_ms=150.0,
            success_rate=0.99,
        )

        metadata = registry.get_metadata("test-provider")
        assert metadata.description == "Updated description"
        assert metadata.avg_latency_ms == 150.0
        assert metadata.success_rate == 0.99

    def test_update_metadata_invalid_field(self, registry, mock_provider):
        """Test updating metadata with invalid field."""
        registry.register(mock_provider)

        with pytest.raises(ValueError, match="Invalid metadata field"):
            registry.update_metadata("test-provider", invalid_field="value")

    def test_update_metadata_nonexistent_provider(self, registry):
        """Test updating metadata for non-existent provider."""
        with pytest.raises(KeyError, match="is not registered"):
            registry.update_metadata("nonexistent", description="test")

    @pytest.mark.asyncio
    async def test_check_health_success(self, registry, mock_provider):
        """Test health check for a healthy provider."""
        registry.register(mock_provider)

        result = await registry.check_health("test-provider")

        assert isinstance(result, ProviderHealthCheck)
        assert result.success is True
        assert result.status in [ProviderStatus.HEALTHY, ProviderStatus.DEGRADED]
        assert result.latency_ms >= 0

        # Check that metadata was updated
        metadata = registry.get_metadata("test-provider")
        assert metadata.status == result.status
        assert metadata.last_checked > 0

    @pytest.mark.asyncio
    async def test_check_health_nonexistent_provider(self, registry):
        """Test health check for non-existent provider."""
        with pytest.raises(KeyError, match="is not registered"):
            await registry.check_health("nonexistent")

    @pytest.mark.asyncio
    async def test_check_all_health(self, registry, mock_provider):
        """Test health check for all providers."""
        # Register two providers
        provider1 = MockProvider(name="provider-1")
        provider2 = MockProvider(name="provider-2")

        registry.register(provider1)
        registry.register(provider2)

        results = await registry.check_all_health()

        assert "provider-1" in results
        assert "provider-2" in results
        assert isinstance(results["provider-1"], ProviderHealthCheck)
        assert isinstance(results["provider-2"], ProviderHealthCheck)

    @pytest.mark.asyncio
    async def test_check_all_health_with_interval(self, registry, mock_provider):
        """Test health check respects interval."""
        registry.register(mock_provider)

        # First check
        results1 = await registry.check_all_health()
        assert "test-provider" in results1

        # Immediate second check should be skipped due to interval
        results2 = await registry.check_all_health()
        assert len(results2) == 0  # Should be empty due to interval

    def test_set_health_check_interval(self, registry):
        """Test setting health check interval."""
        registry.set_health_check_interval(60.0)  # 1 minute
        # No assertion needed, just ensure no error

    def test_set_health_check_interval_invalid(self, registry):
        """Test setting invalid health check interval."""
        with pytest.raises(ValueError, match="must be positive"):
            registry.set_health_check_interval(0.0)

        with pytest.raises(ValueError, match="must be positive"):
            registry.set_health_check_interval(-10.0)

    def test_capability_index_maintenance(self, registry, mock_provider_with_metadata):
        """Test that capability index is properly maintained."""
        provider, metadata = mock_provider_with_metadata
        registry.register(provider, metadata=metadata)

        # Check initial capabilities
        providers_with_vision = registry.get_providers_by_capability(Capability.VISION)
        assert "test-provider-2" in providers_with_vision

        # Update capabilities
        registry.update_metadata(
            "test-provider-2",
            capabilities={Capability.STREAMING},  # Remove VISION, add STREAMING
        )

        # Check updated capabilities
        providers_with_vision = registry.get_providers_by_capability(Capability.VISION)
        assert "test-provider-2" not in providers_with_vision

        providers_with_streaming = registry.get_providers_by_capability(Capability.STREAMING)
        assert "test-provider-2" in providers_with_streaming

    def test_model_index_maintenance(self, registry, mock_provider_with_metadata):
        """Test that model index is properly maintained."""
        provider, metadata = mock_provider_with_metadata
        registry.register(provider, metadata=metadata)

        # Check initial models
        providers_for_special = registry.get_providers_for_model("special-model")
        assert "test-provider-2" in providers_for_special

        # Update supported models
        registry.update_metadata(
            "test-provider-2",
            supported_models={"new-model"},  # Remove special-model, add new-model
        )

        # Check updated models
        providers_for_special = registry.get_providers_for_model("special-model")
        assert "test-provider-2" not in providers_for_special

        providers_for_new = registry.get_providers_for_model("new-model")
        assert "test-provider-2" in providers_for_new


class TestProviderRegistryIntegration:
    """Integration tests for ProviderRegistry with other components."""

    @pytest.fixture
    def router_config(self):
        """Create a router config with provider registry."""
        from omni.router import ProviderRegistry, RouterConfig

        registry = ProviderRegistry()
        config = RouterConfig(provider_registry=registry)
        return config

    def test_router_config_with_registry(self, router_config):
        """Test RouterConfig integrates with ProviderRegistry."""
        assert router_config.provider_registry is not None
        assert isinstance(router_config.provider_registry, ProviderRegistry)

    def test_router_config_auto_registry_creation(self):
        """Test RouterConfig automatically creates registry if None."""
        from omni.router import RouterConfig

        config = RouterConfig()
        assert config.provider_registry is not None
        assert isinstance(config.provider_registry, ProviderRegistry)

    @pytest.mark.asyncio
    async def test_model_router_with_registry(self):
        """Test ModelRouter integration with ProviderRegistry."""
        from omni.providers.mock_provider import MockProvider
        from omni.router import ModelRouter, RouterConfig

        # Create registry and register a provider
        registry = ProviderRegistry()
        provider = MockProvider()
        registry.register(provider)

        # Create router config with registry
        config = RouterConfig(provider_registry=registry)
        router = ModelRouter(config)

        # Test that router can access registry
        assert router.get_provider_registry() == registry

        # Test health check through router
        health_results = await router.check_provider_health()
        assert len(health_results) > 0

        # Test getting provider metadata
        metadata = router.get_provider_metadata(provider.name)
        assert metadata is not None
        assert metadata["name"] == provider.name

    def test_cost_optimized_strategy_with_registry(self):
        """Test CostOptimizedStrategy integration with ProviderRegistry."""
        from omni.router import CostOptimizedStrategy, ProviderRegistry

        registry = ProviderRegistry()

        # Create strategy with registry
        strategy = CostOptimizedStrategy(provider_registry=registry)

        # Strategy should have registry reference
        assert strategy._provider_registry == registry
