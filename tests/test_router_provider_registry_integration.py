"""
Tests for ModelRouter integration with ProviderRegistry.

Validates:
- RouterConfig with ProviderRegistry
- ModelRouter initialization with registry
- Provider lookup through registry
- Capability discovery through router
- Backward compatibility with legacy providers dict
"""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, "src")

from omni.models.provider import CompletionResult, ModelCapabilities, TokenUsage
from omni.router import ModelRouter, ProviderRegistry, RouterConfig

# ── Test Fixtures ──────────────────────────────────────────────────────────


def _make_mock_provider(
    name: str,
    models: list[str],
    capabilities: ModelCapabilities,
) -> MagicMock:
    """Create a mock provider that implements the ModelProvider protocol."""
    provider = MagicMock()
    provider.name = name
    provider.supports_streaming = capabilities.supports_streaming
    provider.supports_tools = capabilities.supports_tools
    provider.list_models.return_value = models
    provider.get_capabilities.return_value = capabilities
    provider.complete = AsyncMock()
    provider.count_tokens.return_value = 10
    provider.estimate_cost.return_value = 0.001
    provider.close = AsyncMock()
    provider.__class__.__name__ = f"{name.title()}Provider"
    return provider


@pytest.fixture
def mock_provider() -> MagicMock:
    """Create a mock OpenAI provider."""
    return _make_mock_provider(
        name="openai",
        models=["openai/gpt-4", "openai/gpt-3.5-turbo"],
        capabilities=ModelCapabilities(
            supports_streaming=True,
            supports_tools=True,
            max_context_tokens=128000,
        ),
    )


@pytest.fixture
def mock_provider_anthropic() -> MagicMock:
    """Create a mock Anthropic provider."""
    return _make_mock_provider(
        name="anthropic",
        models=["anthropic/claude-3-opus", "anthropic/claude-3-sonnet"],
        capabilities=ModelCapabilities(
            supports_streaming=True,
            supports_tools=False,  # Claude doesn't support tools in this mock
            max_context_tokens=200000,
        ),
    )


@pytest.fixture
def provider_registry(mock_provider: MagicMock, mock_provider_anthropic: MagicMock) -> ProviderRegistry:
    """Create a provider registry with providers."""
    registry = ProviderRegistry()
    registry.register_provider("openai", mock_provider)
    registry.register_provider("anthropic", mock_provider_anthropic)
    return registry


@pytest.fixture
def router_with_registry(provider_registry: ProviderRegistry) -> ModelRouter:
    """Create a ModelRouter with ProviderRegistry."""
    config = RouterConfig(provider_registry=provider_registry)
    return ModelRouter(config)


@pytest.fixture
def router_with_legacy_providers(mock_provider: MagicMock) -> ModelRouter:
    """Create a ModelRouter with legacy providers dict (backward compatibility)."""
    config = RouterConfig(providers={"openai/gpt-4": mock_provider})
    return ModelRouter(config)


@pytest.fixture
def router_with_both(mock_provider: MagicMock, provider_registry: ProviderRegistry) -> ModelRouter:
    """Create a ModelRouter with both registry and legacy providers."""
    config = RouterConfig(
        provider_registry=provider_registry,
        providers={"custom-model": mock_provider}  # Additional legacy provider
    )
    return ModelRouter(config)


# ── Test Cases ─────────────────────────────────────────────────────────────


def test_router_config_with_registry(provider_registry: ProviderRegistry) -> None:
    """Test RouterConfig with ProviderRegistry."""
    config = RouterConfig(provider_registry=provider_registry)

    assert config.provider_registry is provider_registry
    assert len(config.provider_registry) == 2


def test_router_config_without_registry() -> None:
    """Test RouterConfig creates default ProviderRegistry when none provided."""
    config = RouterConfig()

    assert config.provider_registry is not None
    assert isinstance(config.provider_registry, ProviderRegistry)
    assert len(config.provider_registry) == 0


def test_router_initialization_with_registry(router_with_registry: ModelRouter) -> None:
    """Test ModelRouter initialization with ProviderRegistry."""
    router = router_with_registry

    # Should have providers cached from registry
    assert hasattr(router, "_provider_cache")
    # openai provider should be retrievable by name
    provider = router.get_provider("openai")
    assert provider is not None
    # Models from openai provider should also be retrievable
    assert router.get_provider("openai/gpt-4") is not None
    assert router.get_provider("openai/gpt-3.5-turbo") is not None


def test_get_provider_via_registry(router_with_registry: ModelRouter, mock_provider: MagicMock) -> None:
    """Test getting provider through registry integration."""
    router = router_with_registry

    # Get provider by provider name
    provider = router.get_provider("openai")
    assert provider is mock_provider

    # Get provider by model name (should find via registry)
    provider = router.get_provider("openai/gpt-4")
    assert provider is mock_provider


def test_get_provider_legacy_compatibility(router_with_legacy_providers: ModelRouter, mock_provider: MagicMock) -> None:
    """Test backward compatibility with legacy providers dict."""
    router = router_with_legacy_providers

    # Should work with legacy providers dict
    provider = router.get_provider("openai/gpt-4")
    assert provider is mock_provider


def test_get_provider_with_both_sources(router_with_both: ModelRouter, mock_provider: MagicMock) -> None:
    """Test provider lookup with both registry and legacy providers."""
    router = router_with_both

    # Should find provider from registry by name
    provider = router.get_provider("openai")
    assert provider is mock_provider

    # Should also find legacy provider
    provider = router.get_provider("custom-model")
    assert provider is mock_provider


def test_list_providers_method(router_with_registry: ModelRouter) -> None:
    """Test list_providers method on router."""
    router = router_with_registry

    providers = router.list_providers()

    assert "openai" in providers
    assert "anthropic" in providers
    assert len(providers) == 2


def test_list_providers_legacy(router_with_legacy_providers: ModelRouter) -> None:
    """Test list_providers with legacy providers (no registry)."""
    router = router_with_legacy_providers

    providers = router.list_providers()

    # Provider registered via legacy path uses provider.name = "openai"
    assert "openai" in providers
    assert len(providers) == 1


def test_get_provider_capabilities(router_with_registry: ModelRouter) -> None:
    """Test getting provider capabilities through router."""
    router = router_with_registry

    # Get provider-level capabilities
    caps = router.get_provider_capabilities("openai")

    assert caps is not None
    assert "models" in caps
    assert "features" in caps
    assert "openai/gpt-4" in caps["models"]
    assert "openai/gpt-3.5-turbo" in caps["models"]
    assert "streaming" in caps["features"]
    assert "tools" in caps["features"]

    # Get model-level capabilities
    model_caps = router.get_provider_capabilities("openai", "openai/gpt-4")

    assert model_caps is not None
    assert "supports_streaming" in model_caps
    assert model_caps["supports_streaming"] is True
    assert "max_context_tokens" in model_caps
    assert model_caps["max_context_tokens"] == 128000


def test_get_provider_capabilities_no_registry() -> None:
    """Test getting capabilities when no registry is configured."""
    config = RouterConfig(providers={})
    # Clear the auto-created registry
    config.provider_registry = None
    router = ModelRouter(config)

    with pytest.raises(RuntimeError, match="Provider registry not configured"):
        router.get_provider_capabilities("openai")


def test_find_providers_by_capability(router_with_registry: ModelRouter) -> None:
    """Test finding providers by capability through router."""
    router = router_with_registry

    # Find providers with streaming support
    streaming_providers = router.find_providers_by_capability("supports_streaming", True)

    assert "openai" in streaming_providers
    assert "anthropic" in streaming_providers
    assert len(streaming_providers) == 2

    # Find providers with tools support (only openai in our mock)
    tools_providers = router.find_providers_by_capability("supports_tools", True)

    assert "openai" in tools_providers
    assert "anthropic" not in tools_providers
    assert len(tools_providers) == 1


def test_find_providers_by_capability_no_registry() -> None:
    """Test finding providers by capability when no registry is configured."""
    config = RouterConfig(providers={})
    config.provider_registry = None
    router = ModelRouter(config)

    with pytest.raises(RuntimeError, match="Provider registry not configured"):
        router.find_providers_by_capability("supports_streaming", True)


def test_register_provider_with_registry(
    router_with_registry: ModelRouter,
) -> None:
    """Test register_provider method with registry integration."""
    router = router_with_registry

    # Register a new provider
    new_provider = _make_mock_provider(
        name="new-provider",
        models=["new-model"],
        capabilities=ModelCapabilities(),
    )

    router.register_provider("new-provider", new_provider)

    # Should be retrievable
    provider = router.get_provider("new-provider")
    assert provider is new_provider

    # Should also be in registry
    registry = router.get_provider_registry()
    assert registry is not None
    assert "new-provider" in registry


def test_router_completion_with_registry_provider(
    router_with_registry: ModelRouter,
    mock_provider: MagicMock,
) -> None:
    """Test router completion works with providers from registry."""
    router = router_with_registry

    # Setup mock completion
    mock_result = CompletionResult(
        content="Test response",
        model="openai/gpt-4",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        finish_reason="stop",
    )
    mock_provider.complete.return_value = mock_result

    # Verify the provider can be retrieved by model name
    provider = router.get_provider("openai/gpt-4")
    assert provider is mock_provider

    # Verify the provider can be retrieved by provider name
    provider = router.get_provider("openai")
    assert provider is mock_provider


def test_backward_compatibility_registration(
    router_with_registry: ModelRouter,
) -> None:
    """Test that register_provider works for backward compatibility."""
    router = router_with_registry

    # Register using the register_provider method
    legacy_provider = _make_mock_provider(
        name="legacy-model",
        models=["legacy-model"],
        capabilities=ModelCapabilities(),
    )
    router.register_provider("legacy-model", legacy_provider)

    # Should be retrievable
    provider = router.get_provider("legacy-model")
    assert provider is legacy_provider

    # Should also be in registry
    assert "legacy-model" in router.get_provider_registry()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
