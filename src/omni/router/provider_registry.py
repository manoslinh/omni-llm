"""
Provider Registry & Capability Discovery for Omni-LLM.

Implements a central registry for model providers with dynamic capability
discovery, metadata management, and health status tracking.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ModelProvider(Protocol):
    """Protocol for model providers."""

    @property
    def name(self) -> str:
        ...

    # These properties are optional for backward compatibility
    @property
    def supports_streaming(self) -> bool:
        ...

    @property
    def cost_per_token(self) -> dict[str, Any]:
        ...

    async def complete(
        self,
        messages: list[Any],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any
    ) -> Any:
        ...

    def count_tokens(self, text: str, model: str) -> int:
        ...

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        ...

    async def close(self) -> None:
        ...

    # Optional properties and methods for capability discovery
    @property
    def supports_tools(self) -> bool:
        ...

    def list_models(self) -> list[str]:
        ...

    def get_capabilities(self, model: str) -> Any:
        ...

logger = logging.getLogger(__name__)


class ProviderStatus(StrEnum):
    """Status of a provider."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # High latency, partial failures
    OFFLINE = "offline"    # Unreachable or consistently failing
    UNKNOWN = "unknown"    # Not yet probed


class Capability(StrEnum):
    """Capabilities that providers may support."""
    STREAMING = "streaming"
    FUNCTION_CALLING = "function_calling"
    VISION = "vision"
    AUDIO = "audio"
    LONG_CONTEXT = "long_context"  # > 100K tokens
    EMBEDDINGS = "embeddings"
    FINE_TUNING = "fine_tuning"
    BATCH_PROCESSING = "batch_processing"


@dataclass
class ProviderMetadata:
    """Metadata for a registered provider."""

    # Basic identification
    name: str
    provider_type: str
    description: str = ""

    # Capabilities
    capabilities: set[Capability] = field(default_factory=set)
    supported_models: set[str] = field(default_factory=set)

    # Performance metrics
    avg_latency_ms: float = 0.0
    success_rate: float = 1.0  # 0.0 to 1.0
    last_checked: float = 0.0  # Unix timestamp

    # Cost information
    cost_per_token: dict[str, tuple[float, float]] = field(default_factory=dict)
    # Format: {model_id: (input_per_million, output_per_million)}

    # Status
    status: ProviderStatus = ProviderStatus.UNKNOWN
    status_message: str = ""

    # Configuration
    config: dict[str, Any] = field(default_factory=dict)

    # Per-model capabilities (model_id -> capability dict)
    model_capabilities: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate metadata fields."""
        if not self.name:
            raise ValueError("Provider name cannot be empty")
        if not 0.0 <= self.success_rate <= 1.0:
            raise ValueError(f"success_rate must be between 0.0 and 1.0, got {self.success_rate}")
        if self.avg_latency_ms < 0:
            raise ValueError(f"avg_latency_ms must be >= 0, got {self.avg_latency_ms}")


@dataclass
class ProviderHealthCheck:
    """Result of a provider health check."""

    status: ProviderStatus
    latency_ms: float
    success: bool
    message: str = ""
    timestamp: float = field(default_factory=time.time)


class ProviderRegistry:
    """
    Central registry for model providers with capability discovery.

    Features:
    - Register/unregister providers
    - Dynamic capability discovery
    - Health status tracking
    - Query providers by capability
    - Integration with ModelRouter and CostOptimizedStrategy
    """

    def __init__(self) -> None:
        """Initialize an empty provider registry."""
        self._providers: dict[str, ModelProvider] = {}
        self._metadata: dict[str, ProviderMetadata] = {}
        self._capability_index: dict[Capability, set[str]] = {
            capability: set() for capability in Capability
        }
        self._model_index: dict[str, set[str]] = {}  # model_id -> provider_names

        # Health check configuration
        self._health_check_interval = 300.0  # 5 minutes
        self._last_health_check: dict[str, float] = {}

        logger.info("ProviderRegistry initialized")

    def register(
        self,
        provider: ModelProvider,
        metadata: ProviderMetadata | None = None,
        discover_capabilities: bool = True,
    ) -> None:
        """
        Register a provider with the registry.

        Args:
            provider: The provider instance to register
            metadata: Optional metadata; if None, will be auto-discovered
            discover_capabilities: Whether to auto-discover capabilities

        Raises:
            ValueError: If provider is already registered
        """
        provider_name = provider.name

        if provider_name in self._providers:
            raise ValueError(f"Provider '{provider_name}' is already registered")

        # Store provider instance
        self._providers[provider_name] = provider

        # Create or update metadata
        if metadata is None:
            metadata = ProviderMetadata(
                name=provider_name,
                provider_type=type(provider).__name__,
                description=f"{provider_name} provider",
            )

        # Auto-discover capabilities if requested
        if discover_capabilities:
            self._discover_capabilities(provider_name, provider, metadata)

        # Store metadata
        self._metadata[provider_name] = metadata

        # Update indices
        self._update_indices(provider_name, metadata)

        logger.info(f"Registered provider '{provider_name}' with {len(metadata.capabilities)} capabilities")

    def register_provider(
        self,
        provider_name: str,
        provider: ModelProvider,
        metadata: ProviderMetadata | None = None,
        discover_capabilities: bool = True,
    ) -> None:
        """
        Register a provider with the registry.

        Args:
            provider_name: Name of the provider
            provider: The provider instance to register
            metadata: Optional metadata; if None, will be auto-discovered
            discover_capabilities: Whether to auto-discover capabilities

        Raises:
            ValueError: If provider is already registered
        """
        if provider_name in self._providers:
            raise ValueError(f"Provider '{provider_name}' is already registered")

        # Store provider instance using the provided name
        self._providers[provider_name] = provider

        # Create or update metadata
        if metadata is None:
            metadata = ProviderMetadata(
                name=provider_name,
                provider_type=type(provider).__name__,
                description=f"{provider_name} provider",
            )
        else:
            # Ensure metadata name matches the provided name
            metadata.name = provider_name

        # Auto-discover capabilities if requested
        if discover_capabilities:
            self._discover_capabilities(provider_name, provider, metadata)

        # Store metadata
        self._metadata[provider_name] = metadata

        # Update indices
        self._update_indices(provider_name, metadata)

        logger.info(f"Registered provider '{provider_name}' with {len(metadata.capabilities)} capabilities")

    def unregister(self, provider_name: str) -> None:
        """
        Unregister a provider from the registry.

        Args:
            provider_name: Name of the provider to unregister

        Raises:
            KeyError: If provider is not registered
        """
        if provider_name not in self._providers:
            raise KeyError(f"Provider '{provider_name}' is not registered")

        # Remove from indices
        metadata = self._metadata[provider_name]
        for capability in metadata.capabilities:
            self._capability_index[capability].discard(provider_name)

        for model_id in metadata.supported_models:
            if model_id in self._model_index:
                self._model_index[model_id].discard(provider_name)
                if not self._model_index[model_id]:
                    del self._model_index[model_id]

        # Remove from registries
        del self._providers[provider_name]
        del self._metadata[provider_name]

        if provider_name in self._last_health_check:
            del self._last_health_check[provider_name]

        logger.info(f"Unregistered provider '{provider_name}'")

    def get_provider(self, provider_name: str) -> ModelProvider | None:
        """Get a provider instance by name."""
        return self._providers.get(provider_name)

    def get_metadata(self, provider_name: str) -> ProviderMetadata | None:
        """Get provider metadata by name."""
        return self._metadata.get(provider_name)

    def get_providers_by_capability(
        self,
        capability: Capability,
        min_success_rate: float = 0.0,
        max_latency_ms: float = float('inf'),
    ) -> list[str]:
        """
        Get providers that support a specific capability.

        Args:
            capability: The capability to filter by
            min_success_rate: Minimum success rate (0.0 to 1.0)
            max_latency_ms: Maximum average latency in milliseconds

        Returns:
            List of provider names sorted by success rate (descending)
        """
        provider_names = list(self._capability_index[capability])

        # Filter by performance metrics
        filtered = []
        for name in provider_names:
            metadata = self._metadata.get(name)
            if not metadata:
                continue

            if (metadata.success_rate >= min_success_rate and
                metadata.avg_latency_ms <= max_latency_ms):
                filtered.append((name, metadata.success_rate))

        # Sort by success rate (descending)
        filtered.sort(key=lambda x: x[1], reverse=True)

        return [name for name, _ in filtered]

    def get_providers_for_model(
        self,
        model_id: str,
        min_success_rate: float = 0.0,
        max_latency_ms: float = float('inf'),
    ) -> list[str]:
        """
        Get providers that support a specific model.

        Args:
            model_id: The model identifier
            min_success_rate: Minimum success rate (0.0 to 1.0)
            max_latency_ms: Maximum average latency in milliseconds

        Returns:
            List of provider names sorted by success rate (descending)
        """
        provider_names = list(self._model_index.get(model_id, set()))

        # Filter by performance metrics
        filtered = []
        for name in provider_names:
            metadata = self._metadata.get(name)
            if not metadata:
                continue

            if (metadata.success_rate >= min_success_rate and
                metadata.avg_latency_ms <= max_latency_ms):
                filtered.append((name, metadata.success_rate))

        # Sort by success rate (descending)
        filtered.sort(key=lambda x: x[1], reverse=True)

        return [name for name, _ in filtered]

    def get_all_providers(self) -> list[str]:
        """Get names of all registered providers."""
        return list(self._providers.keys())

    def __len__(self) -> int:
        """Return number of registered providers."""
        return len(self._providers)

    def __contains__(self, provider_name: str) -> bool:
        """Check if a provider is registered."""
        return provider_name in self._providers

    def get_all_models(self) -> set[str]:
        """Get all model IDs supported by registered providers."""
        return set(self._model_index.keys())

    async def check_health(self, provider_name: str) -> ProviderHealthCheck:
        """
        Perform a health check on a provider.

        Args:
            provider_name: Name of the provider to check

        Returns:
            ProviderHealthCheck with results

        Raises:
            KeyError: If provider is not registered
        """
        if provider_name not in self._providers:
            raise KeyError(f"Provider '{provider_name}' is not registered")

        provider = self._providers[provider_name]
        metadata = self._metadata[provider_name]

        start_time = time.time()
        success = False
        message = ""

        try:
            # Simple health check: try to get provider properties
            # This tests basic connectivity without making actual API calls
            _ = provider.name
            # Try to access optional properties
            try:
                _ = provider.supports_streaming
            except AttributeError:
                pass  # Optional property
            try:
                _ = provider.cost_per_token
            except AttributeError:
                pass  # Optional property

            latency_ms = (time.time() - start_time) * 1000
            success = True
            message = "Health check passed"

            # Update status based on latency
            if latency_ms < 1000:
                status = ProviderStatus.HEALTHY
            elif latency_ms < 5000:
                status = ProviderStatus.DEGRADED
                message = f"High latency: {latency_ms:.0f}ms"
            else:
                status = ProviderStatus.DEGRADED
                message = f"Very high latency: {latency_ms:.0f}ms"

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            status = ProviderStatus.OFFLINE
            message = f"Health check failed: {str(e)}"
            logger.warning(f"Health check failed for '{provider_name}': {e}")

        # Update metadata
        if success:
            # Update latency with exponential moving average
            alpha = 0.3  # Smoothing factor
            old_latency = metadata.avg_latency_ms
            metadata.avg_latency_ms = (
                alpha * latency_ms + (1 - alpha) * old_latency
            )

            # Update success rate
            metadata.success_rate = 0.95 * metadata.success_rate + 0.05  # Slight decay with success

        metadata.status = status
        metadata.status_message = message
        metadata.last_checked = time.time()

        self._last_health_check[provider_name] = time.time()

        return ProviderHealthCheck(
            status=status,
            latency_ms=latency_ms,
            success=success,
            message=message,
            timestamp=time.time(),
        )

    async def check_all_health(self) -> dict[str, ProviderHealthCheck]:
        """
        Perform health checks on all registered providers.

        Returns:
            Dictionary mapping provider names to health check results
        """
        results = {}

        for provider_name in list(self._providers.keys()):
            try:
                # Check if health check is needed (based on interval)
                last_check = self._last_health_check.get(provider_name, 0)
                if time.time() - last_check < self._health_check_interval:
                    continue

                result = await self.check_health(provider_name)
                results[provider_name] = result

            except Exception as e:
                logger.error(f"Error checking health for '{provider_name}': {e}")
                # Mark as offline if health check itself fails
                metadata = self._metadata.get(provider_name)
                if metadata:
                    metadata.status = ProviderStatus.OFFLINE
                    metadata.status_message = f"Health check error: {str(e)}"

        return results

    def set_health_check_interval(self, interval_seconds: float) -> None:
        """Set the interval between automatic health checks."""
        if interval_seconds <= 0:
            raise ValueError("Health check interval must be positive")
        self._health_check_interval = interval_seconds

    def _discover_capabilities(
        self,
        provider_name: str,
        provider: ModelProvider,
        metadata: ProviderMetadata,
    ) -> None:
        """
        Discover capabilities of a provider.

        This is a basic implementation that can be extended with
        more sophisticated discovery logic.
        """
        # Check for streaming support (handle providers that don't have this property)
        try:
            if provider.supports_streaming:
                metadata.capabilities.add(Capability.STREAMING)
        except AttributeError:
            logger.debug(f"Provider '{provider_name}' doesn't have supports_streaming property")

        # Check for function/tools calling support
        try:
            if provider.supports_tools:
                metadata.capabilities.add(Capability.FUNCTION_CALLING)
        except AttributeError:
            logger.debug(f"Provider '{provider_name}' doesn't have supports_tools property")

        # Check cost per token to infer supported models
        try:
            cost_data = provider.cost_per_token
            if cost_data:
                metadata.cost_per_token = {
                    model_id: (rate.input_per_million, rate.output_per_million)
                    for model_id, rate in cost_data.items()
                }
                metadata.supported_models.update(cost_data.keys())
        except AttributeError:
            logger.debug(f"Provider '{provider_name}' doesn't have cost_per_token property")

        # Check for list_models method to discover supported models
        try:
            models = provider.list_models()
            if models:
                metadata.supported_models.update(models)
        except (AttributeError, TypeError):
            logger.debug(f"Provider '{provider_name}' doesn't have list_models method")

        # Check for get_capabilities method to discover per-model capabilities
        try:
            models_to_check = list(metadata.supported_models) if metadata.supported_models else []
            if not models_to_check:
                try:
                    models_to_check = provider.list_models() or []
                except (AttributeError, TypeError):
                    pass
            for model_id in models_to_check:
                try:
                    caps = provider.get_capabilities(model_id)
                    model_cap = {}
                    # Copy all capability fields from ModelCapabilities
                    for attr in ['supports_streaming', 'supports_tools', 'supports_vision',
                                 'supports_audio', 'max_context_tokens', 'supports_edit_format',
                                 'temperature_range', 'top_p_range']:
                        if hasattr(caps, attr):
                            model_cap[attr] = getattr(caps, attr)
                    if model_cap:
                        metadata.model_capabilities[model_id] = model_cap
                except (AttributeError, TypeError):
                    pass
        except (AttributeError, TypeError):
            logger.debug(f"Provider '{provider_name}' doesn't have get_capabilities method")

        # TODO: More sophisticated capability discovery
        # - Test function calling with a simple test
        # - Check for vision support by examining model names/descriptions
        # - Detect long context support
        # - etc.

        logger.debug(f"Discovered {len(metadata.capabilities)} capabilities for '{provider_name}'")

    def _update_indices(self, provider_name: str, metadata: ProviderMetadata) -> None:
        """Update capability and model indices for a provider."""
        # Update capability index
        for capability in metadata.capabilities:
            self._capability_index[capability].add(provider_name)

        # Update model index
        for model_id in metadata.supported_models:
            if model_id not in self._model_index:
                self._model_index[model_id] = set()
            self._model_index[model_id].add(provider_name)

    def update_metadata(self, provider_name: str, **kwargs: Any) -> None:
        """
        Update metadata for a registered provider.

        Args:
            provider_name: Name of the provider
            **kwargs: Metadata fields to update

        Raises:
            KeyError: If provider is not registered
            ValueError: If invalid fields are provided
        """
        if provider_name not in self._metadata:
            raise KeyError(f"Provider '{provider_name}' is not registered")

        metadata = self._metadata[provider_name]

        # Update fields
        for key, value in kwargs.items():
            if hasattr(metadata, key):
                setattr(metadata, key, value)
            else:
                raise ValueError(f"Invalid metadata field: {key}")

        # Re-index if capabilities or models changed
        if 'capabilities' in kwargs or 'supported_models' in kwargs:
            # Clear old indices
            for capability in Capability:
                self._capability_index[capability].discard(provider_name)

            for model_id in list(self._model_index.keys()):
                self._model_index[model_id].discard(provider_name)
                if not self._model_index[model_id]:
                    del self._model_index[model_id]

            # Update with new values
            self._update_indices(provider_name, metadata)

        logger.debug(f"Updated metadata for '{provider_name}'")
