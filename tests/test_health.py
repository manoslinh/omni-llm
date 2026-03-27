"""
Tests for Health Monitoring & Circuit Breaker (P2-05).

Validates:
- CircuitBreaker state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
- HealthMonitor sliding-window metrics and aggregation
- ResilientProvider wrapper integration
- HealthManager centralized management
- Configuration validation
- Thread-safety and concurrency
- Edge cases and error handling
"""

import sys
import threading
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, "src")

from omni.router.health import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    HealthConfig,
    HealthManager,
    HealthMetrics,
    HealthMonitor,
    ResilientProvider,
)

# ── Test Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def config() -> HealthConfig:
    """Default health config for testing."""
    return HealthConfig(
        window_size=20,
        window_duration_seconds=60.0,
        error_rate_threshold=0.5,
        latency_threshold_seconds=5.0,
        min_requests_for_threshold=3,
        recovery_timeout_seconds=1.0,  # Short for tests
        half_open_max_requests=2,
        half_open_success_threshold=2,
        backoff_multiplier=2.0,
        max_recovery_timeout=10.0,
        health_check_interval=5.0,
        health_check_timeout=2.0,
    )


@pytest.fixture
def fast_config() -> HealthConfig:
    """Ultra-fast config for quick tests."""
    return HealthConfig(
        window_size=10,
        window_duration_seconds=10.0,
        error_rate_threshold=0.5,
        latency_threshold_seconds=1.0,
        min_requests_for_threshold=2,
        recovery_timeout_seconds=0.1,  # Very short
        half_open_max_requests=2,
        half_open_success_threshold=1,
        backoff_multiplier=1.5,
        max_recovery_timeout=2.0,
    )


@pytest.fixture
def monitor(config: HealthConfig) -> HealthMonitor:
    """HealthMonitor with test config."""
    return HealthMonitor(config)


@pytest.fixture
def breaker(config: HealthConfig) -> CircuitBreaker:
    """CircuitBreaker with test config."""
    return CircuitBreaker("test-provider", config)


@pytest.fixture
def manager(config: HealthConfig) -> HealthManager:
    """HealthManager with test config."""
    return HealthManager(config)


@pytest.fixture
def mock_provider() -> MagicMock:
    """Mock model provider."""
    provider = MagicMock()
    provider.complete = AsyncMock(return_value="Mock result")
    provider.count_tokens = MagicMock(return_value=100)
    provider.estimate_cost = MagicMock(return_value=0.001)
    provider.get_capabilities = MagicMock()
    provider.list_models = MagicMock(return_value=["model-a", "model-b"])
    provider.close = AsyncMock()
    return provider


# ── HealthConfig Tests ─────────────────────────────────────────────────────


class TestHealthConfig:
    """Tests for HealthConfig validation."""

    def test_valid_defaults(self) -> None:
        """Should accept default config."""
        config = HealthConfig()
        assert config.window_size == 100
        assert config.error_rate_threshold == 0.5
        assert config.recovery_timeout_seconds == 60.0

    def test_valid_custom(self) -> None:
        """Should accept valid custom values."""
        config = HealthConfig(
            window_size=50,
            error_rate_threshold=0.3,
            recovery_timeout_seconds=30.0,
        )
        assert config.window_size == 50
        assert config.error_rate_threshold == 0.3

    def test_invalid_window_size(self) -> None:
        """Should reject window_size < 1."""
        with pytest.raises(ValueError, match="window_size must be >= 1"):
            HealthConfig(window_size=0)

    def test_invalid_window_duration(self) -> None:
        """Should reject non-positive window duration."""
        with pytest.raises(ValueError, match="window_duration_seconds must be > 0"):
            HealthConfig(window_duration_seconds=0)

    def test_invalid_error_rate_threshold_zero(self) -> None:
        """Should reject error_rate_threshold = 0."""
        with pytest.raises(ValueError, match="error_rate_threshold"):
            HealthConfig(error_rate_threshold=0.0)

    def test_invalid_error_rate_threshold_over_one(self) -> None:
        """Should reject error_rate_threshold > 1."""
        with pytest.raises(ValueError, match="error_rate_threshold"):
            HealthConfig(error_rate_threshold=1.5)

    def test_invalid_latency_threshold(self) -> None:
        """Should reject non-positive latency threshold."""
        with pytest.raises(ValueError, match="latency_threshold_seconds"):
            HealthConfig(latency_threshold_seconds=0)

    def test_invalid_recovery_timeout(self) -> None:
        """Should reject non-positive recovery timeout."""
        with pytest.raises(ValueError, match="recovery_timeout_seconds"):
            HealthConfig(recovery_timeout_seconds=-1)

    def test_invalid_max_recovery_less_than_recovery(self) -> None:
        """Should reject max_recovery_timeout < recovery_timeout_seconds."""
        with pytest.raises(ValueError, match="max_recovery_timeout"):
            HealthConfig(
                recovery_timeout_seconds=60.0,
                max_recovery_timeout=30.0,
            )

    def test_invalid_backoff_multiplier(self) -> None:
        """Should reject backoff_multiplier < 1."""
        with pytest.raises(ValueError, match="backoff_multiplier"):
            HealthConfig(backoff_multiplier=0.5)

    def test_invalid_half_open_max_requests(self) -> None:
        """Should reject half_open_max_requests < 1."""
        with pytest.raises(ValueError, match="half_open_max_requests"):
            HealthConfig(half_open_max_requests=0)

    def test_invalid_half_open_success_threshold(self) -> None:
        """Should reject half_open_success_threshold < 1."""
        with pytest.raises(ValueError, match="half_open_success_threshold"):
            HealthConfig(half_open_success_threshold=0)


# ── HealthMetrics Tests ────────────────────────────────────────────────────


class TestHealthMetrics:
    """Tests for HealthMetrics data model."""

    def test_valid_metrics(self) -> None:
        """Should accept valid metrics."""
        metrics = HealthMetrics(
            provider_id="test",
            total_requests=100,
            successful_requests=90,
            failed_requests=10,
            success_rate=0.9,
            error_rate=0.1,
            health_score=0.85,
        )
        assert metrics.provider_id == "test"
        assert metrics.success_rate == 0.9

    def test_invalid_success_rate(self) -> None:
        """Should reject out-of-range success_rate."""
        with pytest.raises(ValueError, match="success_rate"):
            HealthMetrics(provider_id="test", success_rate=1.5)

    def test_invalid_error_rate(self) -> None:
        """Should reject out-of-range error_rate."""
        with pytest.raises(ValueError, match="error_rate"):
            HealthMetrics(provider_id="test", error_rate=-0.1)

    def test_invalid_health_score(self) -> None:
        """Should reject out-of-range health_score."""
        with pytest.raises(ValueError, match="health_score"):
            HealthMetrics(provider_id="test", health_score=2.0)


# ── CircuitBreaker Tests ──────────────────────────────────────────────────


class TestCircuitBreaker:
    """Tests for CircuitBreaker state machine."""

    def test_initial_state_closed(self, breaker: CircuitBreaker) -> None:
        """Should start in CLOSED state."""
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_available

    def test_stays_closed_on_success(self, breaker: CircuitBreaker) -> None:
        """Should stay CLOSED on successful calls."""
        for _ in range(10):
            breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    def test_opens_after_threshold_failures(self, breaker: CircuitBreaker) -> None:
        """Should OPEN after min_requests_for_threshold consecutive failures."""
        # Config has min_requests_for_threshold=3
        breaker.record_failure(RuntimeError("fail 1"))
        assert breaker.state == CircuitState.CLOSED

        breaker.record_failure(RuntimeError("fail 2"))
        assert breaker.state == CircuitState.CLOSED

        breaker.record_failure(RuntimeError("fail 3"))
        assert breaker.state == CircuitState.OPEN
        assert not breaker.is_available

    def test_success_resets_failure_count(self, breaker: CircuitBreaker) -> None:
        """Should reset failure count on success."""
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()  # Reset
        breaker.record_failure()
        breaker.record_failure()
        # Only 2 failures after reset, need 3 to open
        assert breaker.state == CircuitState.CLOSED

    def test_half_open_after_recovery_timeout(
        self, fast_config: HealthConfig
    ) -> None:
        """Should transition to HALF_OPEN after recovery timeout."""
        breaker = CircuitBreaker("test", fast_config)

        # Force OPEN
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout (0.1s in fast_config)
        time.sleep(0.15)

        # Access state triggers auto-transition
        assert breaker.state == CircuitState.HALF_OPEN

    def test_half_open_limits_requests(self, fast_config: HealthConfig) -> None:
        """Should limit requests in HALF_OPEN state."""
        breaker = CircuitBreaker("test", fast_config)

        # Force to HALF_OPEN
        for _ in range(3):
            breaker.record_failure()
        time.sleep(0.15)
        assert breaker.state == CircuitState.HALF_OPEN

        # half_open_max_requests=2
        assert breaker.is_available  # First probe
        breaker._half_open_requests = 1
        assert breaker.is_available  # Second probe
        breaker._half_open_requests = 2
        assert not breaker.is_available  # Max reached

    def test_half_open_success_closes_circuit(
        self, fast_config: HealthConfig
    ) -> None:
        """Should CLOSE circuit after enough successes in HALF_OPEN."""
        breaker = CircuitBreaker("test", fast_config)

        # Force to HALF_OPEN
        for _ in range(3):
            breaker.record_failure()
        time.sleep(0.15)
        assert breaker.state == CircuitState.HALF_OPEN

        # half_open_success_threshold=1 in fast_config
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self, fast_config: HealthConfig) -> None:
        """Should re-OPEN on failure during HALF_OPEN."""
        breaker = CircuitBreaker("test", fast_config)

        # Force to HALF_OPEN
        for _ in range(3):
            breaker.record_failure()
        time.sleep(0.15)
        assert breaker.state == CircuitState.HALF_OPEN

        # Failure during probe
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    def test_exponential_backoff(self, fast_config: HealthConfig) -> None:
        """Should increase recovery timeout exponentially."""
        fast_config.recovery_timeout_seconds = 0.1
        fast_config.backoff_multiplier = 2.0
        breaker = CircuitBreaker("test", fast_config)
        initial_timeout = fast_config.recovery_timeout_seconds

        # First open
        for _ in range(3):
            breaker.record_failure()
        assert breaker._recovery_timeout == initial_timeout

        # Wait and force another open
        time.sleep(breaker._recovery_timeout + 0.05)
        _ = breaker.state  # Trigger half-open check
        breaker.record_failure()  # Re-opens
        assert breaker._recovery_timeout == initial_timeout * fast_config.backoff_multiplier

    def test_max_backoff_cap(self, fast_config: HealthConfig) -> None:
        """Should cap recovery timeout at max_recovery_timeout."""
        # Use fast config with short timeouts
        fast_config.max_recovery_timeout = 0.5
        fast_config.recovery_timeout_seconds = 0.1
        breaker = CircuitBreaker("test", fast_config)

        # Force many consecutive opens to trigger backoff accumulation
        for _ in range(10):
            # Force open
            for _ in range(3):
                breaker.record_failure()
            # Wait for recovery timeout
            time.sleep(breaker._recovery_timeout + 0.05)
            # Trigger half-open transition by accessing state
            _ = breaker.state
            # Fail during half-open to re-open with increased backoff
            breaker.record_failure()

        assert breaker._recovery_timeout <= fast_config.max_recovery_timeout

    def test_reset(self, breaker: CircuitBreaker) -> None:
        """Should reset to CLOSED state."""
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_available

    def test_get_state_info(self, breaker: CircuitBreaker) -> None:
        """Should return comprehensive state info."""
        info = breaker.get_state_info()
        assert info["provider_id"] == "test-provider"
        assert info["state"] == "closed"
        assert info["failure_count"] == 0
        assert info["is_available"] is True

    @pytest.mark.asyncio
    async def test_call_success(self, breaker: CircuitBreaker) -> None:
        """Should execute and record success."""
        mock_func = AsyncMock(return_value="result")
        result = await breaker.call(mock_func, "arg1", key="value")

        assert result == "result"
        mock_func.assert_called_once_with("arg1", key="value")
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_call_failure_records(self, breaker: CircuitBreaker) -> None:
        """Should record failure on exception."""
        mock_func = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            await breaker.call(mock_func)

        assert breaker._failure_count == 1

    @pytest.mark.asyncio
    async def test_call_open_circuit_raises(self, breaker: CircuitBreaker) -> None:
        """Should raise CircuitOpenError when circuit is OPEN."""
        # Force OPEN
        for _ in range(3):
            breaker.record_failure()

        mock_func = AsyncMock()
        with pytest.raises(CircuitOpenError) as exc_info:
            await breaker.call(mock_func)

        assert exc_info.value.provider_id == "test-provider"
        assert exc_info.value.state == CircuitState.OPEN
        mock_func.assert_not_called()


# ── HealthMonitor Tests ────────────────────────────────────────────────────


class TestHealthMonitor:
    """Tests for HealthMonitor sliding-window metrics."""

    def test_empty_metrics(self, monitor: HealthMonitor) -> None:
        """Should return healthy metrics for unknown provider."""
        metrics = monitor.get_metrics("unknown")
        assert metrics.is_healthy
        assert metrics.health_score == 1.0
        assert metrics.total_requests == 0

    def test_record_and_retrieve(self, monitor: HealthMonitor) -> None:
        """Should track recorded calls."""
        monitor.record_call("p1", latency=0.5, success=True)
        monitor.record_call("p1", latency=0.3, success=True)
        monitor.record_call("p1", latency=1.0, success=False, error=RuntimeError())

        metrics = monitor.get_metrics("p1")
        assert metrics.total_requests == 3
        assert metrics.successful_requests == 2
        assert metrics.failed_requests == 1
        assert abs(metrics.success_rate - 2 / 3) < 0.01
        assert abs(metrics.error_rate - 1 / 3) < 0.01

    def test_latency_stats(self, monitor: HealthMonitor) -> None:
        """Should calculate latency statistics."""
        for lat in [0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0]:
            monitor.record_call("p1", latency=lat, success=True)

        metrics = monitor.get_metrics("p1")
        assert metrics.min_latency == 0.1
        assert metrics.max_latency == 5.0
        assert metrics.avg_latency > 0
        assert metrics.p95_latency > 0
        assert metrics.p99_latency > 0

    def test_health_score_degrades_with_errors(self, monitor: HealthMonitor) -> None:
        """Should lower health score with high error rate."""
        # All successes
        for _ in range(10):
            monitor.record_call("p1", latency=0.1, success=True)
        healthy_score = monitor.get_health_score("p1")

        # Reset and add failures
        monitor.reset("p1")
        for _ in range(5):
            monitor.record_call("p1", latency=0.1, success=False, error=RuntimeError())
        for _ in range(5):
            monitor.record_call("p1", latency=0.1, success=True)
        unhealthy_score = monitor.get_health_score("p1")

        assert unhealthy_score < healthy_score

    def test_is_healthy_threshold(self, monitor: HealthMonitor) -> None:
        """Should mark unhealthy when error rate exceeds threshold."""
        # error_rate_threshold = 0.5
        for _ in range(6):
            monitor.record_call("p1", latency=0.1, success=False, error=RuntimeError())
        for _ in range(4):
            monitor.record_call("p1", latency=0.1, success=True)

        metrics = monitor.get_metrics("p1")
        assert metrics.error_rate > 0.5
        assert not metrics.is_healthy

    def test_window_pruning(self, config: HealthConfig) -> None:
        """Should prune old records outside window duration."""
        config.window_duration_seconds = 0.5  # 500ms window
        monitor = HealthMonitor(config)

        # Add old record
        monitor.record_call("p1", latency=0.1, success=True)
        time.sleep(0.6)  # Wait past window

        # Add new record
        monitor.record_call("p1", latency=0.2, success=True)

        metrics = monitor.get_metrics("p1")
        # Only the new record should count
        assert metrics.total_requests == 1
        assert metrics.avg_latency == 0.2

    def test_get_all_metrics(self, monitor: HealthMonitor) -> None:
        """Should return metrics for all tracked providers."""
        monitor.record_call("p1", latency=0.1, success=True)
        monitor.record_call("p2", latency=0.2, success=False, error=RuntimeError())

        all_metrics = monitor.get_all_metrics()
        assert "p1" in all_metrics
        assert "p2" in all_metrics

    def test_get_unhealthy_providers(self, monitor: HealthMonitor) -> None:
        """Should list providers with high error rates."""
        # p1: healthy
        for _ in range(10):
            monitor.record_call("p1", latency=0.1, success=True)

        # p2: unhealthy (>50% errors)
        for _ in range(6):
            monitor.record_call("p2", latency=0.1, success=False, error=RuntimeError())
        for _ in range(4):
            monitor.record_call("p2", latency=0.1, success=True)

        unhealthy = monitor.get_unhealthy_providers()
        assert "p2" in unhealthy
        assert "p1" not in unhealthy

    def test_reset_single_provider(self, monitor: HealthMonitor) -> None:
        """Should reset metrics for one provider."""
        monitor.record_call("p1", latency=0.1, success=True)
        monitor.record_call("p2", latency=0.2, success=True)

        monitor.reset("p1")

        metrics_p1 = monitor.get_metrics("p1")
        metrics_p2 = monitor.get_metrics("p2")
        assert metrics_p1.total_requests == 0
        assert metrics_p2.total_requests == 1

    def test_reset_all(self, monitor: HealthMonitor) -> None:
        """Should reset all metrics."""
        monitor.record_call("p1", latency=0.1, success=True)
        monitor.record_call("p2", latency=0.2, success=True)

        monitor.reset()

        assert monitor.get_metrics("p1").total_requests == 0
        assert monitor.get_metrics("p2").total_requests == 0


# ── ResilientProvider Tests ───────────────────────────────────────────────


class TestResilientProvider:
    """Tests for ResilientProvider wrapper."""

    @pytest.fixture
    def resilient(
        self,
        mock_provider: MagicMock,
        monitor: HealthMonitor,
        breaker: CircuitBreaker,
    ) -> ResilientProvider:
        """Create ResilientProvider wrapping mock provider."""
        return ResilientProvider("test-provider", mock_provider, monitor, breaker)

    @pytest.mark.asyncio
    async def test_complete_success(
        self, resilient: ResilientProvider, mock_provider: MagicMock
    ) -> None:
        """Should complete and record metrics."""
        messages = [{"role": "user", "content": "Hello"}]
        result = await resilient.complete(messages, model="gpt-4")

        assert result == "Mock result"
        mock_provider.complete.assert_called_once()

        metrics = resilient.health_metrics
        assert metrics.total_requests == 1
        assert metrics.successful_requests == 1

    @pytest.mark.asyncio
    async def test_complete_failure_records(
        self, resilient: ResilientProvider
    ) -> None:
        """Should record failure on exception."""
        mock_provider = resilient._provider
        mock_provider.complete.side_effect = RuntimeError("API error")

        with pytest.raises(RuntimeError, match="API error"):
            await resilient.complete([], model="gpt-4")

        metrics = resilient.health_metrics
        assert metrics.failed_requests == 1

    @pytest.mark.asyncio
    async def test_circuit_open_blocks(
        self,
        mock_provider: MagicMock,
        monitor: HealthMonitor,
        config: HealthConfig,
    ) -> None:
        """Should block calls when circuit is OPEN."""
        breaker = CircuitBreaker("test", config)
        resilient = ResilientProvider("test", mock_provider, monitor, breaker)

        # Force circuit open
        for _ in range(3):
            breaker.record_failure()

        with pytest.raises(CircuitOpenError):
            await resilient.complete([], model="gpt-4")

        mock_provider.complete.assert_not_called()

    def test_delegates_to_provider(
        self, resilient: ResilientProvider, mock_provider: MagicMock
    ) -> None:
        """Should delegate non-completion methods to underlying provider."""
        assert resilient.count_tokens("text", "model") == 100
        assert resilient.estimate_cost(10, 20, "model") == 0.001
        assert resilient.list_models() == ["model-a", "model-b"]

        mock_provider.count_tokens.assert_called_once()
        mock_provider.estimate_cost.assert_called_once()
        mock_provider.list_models.assert_called_once()

    def test_is_available(self, resilient: ResilientProvider) -> None:
        """Should report availability based on circuit and health."""
        assert resilient.is_available()

    def test_circuit_state(self, resilient: ResilientProvider) -> None:
        """Should expose circuit breaker state."""
        assert resilient.circuit_state == CircuitState.CLOSED


# ── HealthManager Tests ────────────────────────────────────────────────────


class TestHealthManager:
    """Tests for HealthManager integration."""

    def test_register_provider(self, manager: HealthManager) -> None:
        """Should register and return circuit breaker."""
        breaker = manager.register_provider("deepseek-chat")
        assert breaker.provider_id == "deepseek-chat"
        assert breaker.state == CircuitState.CLOSED

    def test_register_idempotent(self, manager: HealthManager) -> None:
        """Should return same breaker on repeated registration."""
        b1 = manager.register_provider("p1")
        b2 = manager.register_provider("p1")
        assert b1 is b2

    def test_get_breaker_auto_registers(self, manager: HealthManager) -> None:
        """Should auto-register when getting unregistered breaker."""
        breaker = manager.get_breaker("new-provider")
        assert breaker.provider_id == "new-provider"

    def test_get_resilient_provider(
        self, manager: HealthManager, mock_provider: MagicMock
    ) -> None:
        """Should wrap provider with health monitoring."""
        resilient = manager.get_resilient_provider("p1", mock_provider)
        assert isinstance(resilient, ResilientProvider)
        assert resilient.provider_id == "p1"

    def test_get_healthy_providers(self, manager: HealthManager) -> None:
        """Should list healthy providers."""
        manager.register_provider("healthy")
        manager.register_provider("unhealthy")

        # Make unhealthy provider fail
        unhealthy_breaker = manager.get_breaker("unhealthy")
        for _ in range(3):
            unhealthy_breaker.record_failure()

        healthy = manager.get_healthy_providers()
        assert "healthy" in healthy
        assert "unhealthy" not in healthy

    def test_get_all_health_status(self, manager: HealthManager) -> None:
        """Should return comprehensive status for all providers."""
        manager.register_provider("p1")
        manager.register_provider("p2")

        # Record some activity
        manager.monitor.record_call("p1", latency=0.5, success=True)
        manager.monitor.record_call("p2", latency=1.0, success=False, error=RuntimeError())

        status = manager.get_all_health_status()
        assert "p1" in status
        assert "p2" in status
        assert status["p1"]["is_healthy"] is True
        assert "circuit_state" in status["p1"]

    def test_reset_provider(self, manager: HealthManager) -> None:
        """Should reset provider state."""
        manager.register_provider("p1")
        manager.monitor.record_call("p1", latency=0.5, success=False, error=RuntimeError())

        manager.reset_provider("p1")

        metrics = manager.monitor.get_metrics("p1")
        assert metrics.total_requests == 0

    def test_reset_all(self, manager: HealthManager) -> None:
        """Should reset all providers."""
        manager.register_provider("p1")
        manager.register_provider("p2")
        manager.monitor.record_call("p1", latency=0.5, success=True)
        manager.monitor.record_call("p2", latency=0.5, success=True)

        manager.reset_all()

        assert manager.monitor.get_metrics("p1").total_requests == 0
        assert manager.monitor.get_metrics("p2").total_requests == 0

    def test_filter_by_health(self, manager: HealthManager) -> None:
        """Should filter providers by health criteria."""
        manager.register_provider("healthy")
        manager.register_provider("sick")

        # Make sick provider have high error rate
        for _ in range(10):
            manager.monitor.record_call("sick", latency=0.1, success=False, error=RuntimeError())
        for _ in range(10):
            manager.monitor.record_call("healthy", latency=0.1, success=True)

        filtered = manager.filter_by_health(
            ["healthy", "sick"],
            min_health_score=0.5,
            require_available=True,
        )
        assert "healthy" in filtered
        assert "sick" not in filtered


# ── Thread Safety Tests ────────────────────────────────────────────────────


class TestThreadSafety:
    """Tests for concurrent access safety."""

    def test_concurrent_monitor_writes(self) -> None:
        """Should handle concurrent writes without corruption."""
        # Use larger window to hold all records
        config = HealthConfig(
            window_size=500,  # Large enough for all concurrent writes
            window_duration_seconds=60.0,
            error_rate_threshold=0.5,
            latency_threshold_seconds=5.0,
            min_requests_for_threshold=3,
            recovery_timeout_seconds=1.0,
            half_open_max_requests=2,
            half_open_success_threshold=2,
        )
        monitor = HealthMonitor(config)
        errors = []
        records_per_thread = 50  # Reduced for faster test

        def writer(provider_id: str, count: int) -> None:
            try:
                for i in range(count):
                    monitor.record_call(
                        provider_id,
                        latency=0.1 + (i % 10) * 0.01,
                        success=i % 5 != 0,
                        error=RuntimeError() if i % 5 == 0 else None,
                    )
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(f"p{j}", records_per_thread))
            for j in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Verify all providers tracked
        for j in range(5):
            metrics = monitor.get_metrics(f"p{j}")
            assert metrics.total_requests == records_per_thread

    def test_concurrent_breaker_state_transitions(
        self, config: HealthConfig
    ) -> None:
        """Should handle concurrent state transitions safely."""
        breaker = CircuitBreaker("test", config)
        errors = []

        def record_cycle() -> None:
            try:
                for _ in range(50):
                    if breaker.state == CircuitState.CLOSED:
                        breaker.record_failure()
                    elif breaker.state == CircuitState.HALF_OPEN:
                        breaker.record_success()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_cycle) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # State should be valid
        assert breaker.state in (CircuitState.CLOSED, CircuitState.OPEN, CircuitState.HALF_OPEN)


# ── Integration Tests ──────────────────────────────────────────────────────


class TestIntegration:
    """Integration tests combining multiple components."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(
        self,
        manager: HealthManager,
        mock_provider: MagicMock,
    ) -> None:
        """Test full lifecycle: register → use → fail → recover."""
        # Register provider
        resilient = manager.get_resilient_provider("test-model", mock_provider)

        # Successful calls
        for _ in range(5):
            result = await resilient.complete([], model="test-model")
            assert result == "Mock result"

        metrics = resilient.health_metrics
        assert metrics.success_rate == 1.0
        assert resilient.circuit_state == CircuitState.CLOSED

        # Simulate failures
        mock_provider.complete.side_effect = RuntimeError("Provider down")
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await resilient.complete([], model="test-model")

        # Circuit should be open
        assert resilient.circuit_state == CircuitState.OPEN
        assert not resilient.is_available()

        # Wait for recovery
        time.sleep(manager.config.recovery_timeout_seconds + 0.1)

        # Provider recovers
        mock_provider.complete.side_effect = None
        mock_provider.complete.return_value = "Recovered!"

        # Should allow probe in HALF_OPEN
        result = await resilient.complete([], model="test-model")
        assert result == "Recovered!"

        # After enough successes, circuit closes
        result = await resilient.complete([], model="test-model")
        assert resilient.circuit_state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_multiple_providers_health_aware_routing(
        self, manager: HealthManager
    ) -> None:
        """Test using health manager for provider selection."""
        # Create mock providers
        providers = {}
        for name in ["fast", "slow", "broken"]:
            mock = MagicMock()
            mock.complete = AsyncMock()
            mock.list_models = MagicMock(return_value=[name])
            providers[name] = mock
            manager.get_resilient_provider(name, mock)

        # fast: all success, low latency
        for _ in range(10):
            manager.monitor.record_call("fast", latency=0.1, success=True)

        # slow: all success, high latency
        for _ in range(10):
            manager.monitor.record_call("slow", latency=4.0, success=True)

        # broken: all failures
        for _ in range(10):
            manager.monitor.record_call(
                "broken", latency=0.1, success=False, error=RuntimeError()
            )
        manager.get_breaker("broken").record_failure()
        manager.get_breaker("broken").record_failure()
        manager.get_breaker("broken").record_failure()

        # Filter healthy providers
        healthy = manager.filter_by_health(
            ["fast", "slow", "broken"],
            min_health_score=0.5,
            require_available=True,
        )

        assert "fast" in healthy
        assert "broken" not in healthy

    def test_metrics_persistence_across_checks(self, monitor: HealthMonitor) -> None:
        """Metrics should be consistent across multiple reads."""
        for _ in range(20):
            monitor.record_call("p1", latency=0.5, success=True)

        m1 = monitor.get_metrics("p1")
        m2 = monitor.get_metrics("p1")

        assert m1.total_requests == m2.total_requests
        assert m1.success_rate == m2.success_rate
        assert m1.avg_latency == m2.avg_latency


# ── Edge Cases ─────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_single_request_metrics(self, monitor: HealthMonitor) -> None:
        """Should handle single-request metrics correctly."""
        monitor.record_call("p1", latency=0.5, success=True)
        metrics = monitor.get_metrics("p1")

        assert metrics.total_requests == 1
        assert metrics.success_rate == 1.0
        assert metrics.avg_latency == 0.5
        assert metrics.min_latency == 0.5
        assert metrics.max_latency == 0.5

    def test_zero_latency(self, monitor: HealthMonitor) -> None:
        """Should handle zero latency calls."""
        monitor.record_call("p1", latency=0.0, success=True)
        metrics = monitor.get_metrics("p1")
        assert metrics.avg_latency == 0.0

    def test_very_high_latency(self, monitor: HealthMonitor) -> None:
        """Should handle very high latency calls."""
        monitor.record_call("p1", latency=1000.0, success=True)
        metrics = monitor.get_metrics("p1")
        assert metrics.max_latency == 1000.0

    def test_all_failures(self, monitor: HealthMonitor) -> None:
        """Should handle 100% failure rate."""
        for _ in range(10):
            monitor.record_call("p1", latency=0.1, success=False, error=RuntimeError())

        metrics = monitor.get_metrics("p1")
        assert metrics.error_rate == 1.0
        assert metrics.success_rate == 0.0
        assert not metrics.is_healthy

    def test_all_successes(self, monitor: HealthMonitor) -> None:
        """Should handle 100% success rate."""
        for _ in range(10):
            monitor.record_call("p1", latency=0.1, success=True)

        metrics = monitor.get_metrics("p1")
        assert metrics.success_rate == 1.0
        assert metrics.error_rate == 0.0
        assert metrics.is_healthy

    def test_breaker_no_failures(self, breaker: CircuitBreaker) -> None:
        """Should stay closed with zero failures."""
        for _ in range(100):
            breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    def test_manager_empty_providers(self, manager: HealthManager) -> None:
        """Should handle empty provider list."""
        assert manager.get_healthy_providers() == []
        assert manager.get_all_health_status() == {}

    @pytest.mark.asyncio
    async def test_circuit_open_error_message(self, breaker: CircuitBreaker) -> None:
        """CircuitOpenError should have descriptive message."""
        for _ in range(3):
            breaker.record_failure()

        with pytest.raises(CircuitOpenError) as exc_info:
            await breaker.call(AsyncMock())

        assert "test-provider" in str(exc_info.value)
        assert "open" in str(exc_info.value).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
