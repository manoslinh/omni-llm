"""
Health Monitoring & Circuit Breaker for Omni-LLM Router.

Provides resilient provider management through:
- Continuous health monitoring with configurable checks
- Circuit breaker pattern (CLOSED → OPEN → HALF_OPEN)
- Latency, error rate, and success rate tracking
- Automatic recovery with exponential backoff
- Thread-safe concurrent access
- Observable metrics for monitoring dashboards

Architecture:
    HealthMonitor tracks per-provider metrics and exposes health status.
    CircuitBreaker wraps provider calls with fail-fast protection.
    Both integrate seamlessly with ModelRouter for resilient routing.
"""

import logging
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from omni.models.provider import ModelCapabilities, ModelProvider

logger = logging.getLogger(__name__)


# ── Circuit Breaker States ─────────────────────────────────────────────────


class CircuitState(StrEnum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation — requests pass through
    OPEN = "open"  # Fail-fast — requests are rejected immediately
    HALF_OPEN = "half_open"  # Recovery probe — limited requests allowed


# ── Data Models ────────────────────────────────────────────────────────────


@dataclass
class HealthMetrics:
    """Aggregated health metrics for a provider/model.

    All time windows are sliding windows based on recent calls.
    """

    provider_id: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0

    # Latency stats (seconds)
    avg_latency: float = 0.0
    p95_latency: float = 0.0
    p99_latency: float = 0.0
    min_latency: float = float("inf")
    max_latency: float = 0.0

    # Rate metrics (0.0 to 1.0)
    success_rate: float = 1.0
    error_rate: float = 0.0

    # Circuit breaker state
    circuit_state: CircuitState = CircuitState.CLOSED
    circuit_open_count: int = 0  # Total times circuit opened
    last_circuit_open_at: float | None = None
    last_failure_at: float | None = None
    last_success_at: float | None = None

    # Health status
    is_healthy: bool = True
    health_score: float = 1.0  # 0.0 (unhealthy) to 1.0 (fully healthy)

    def __post_init__(self) -> None:
        """Validate metrics fields."""
        if not 0.0 <= self.success_rate <= 1.0:
            raise ValueError(
                f"success_rate must be 0.0-1.0, got {self.success_rate}"
            )
        if not 0.0 <= self.error_rate <= 1.0:
            raise ValueError(f"error_rate must be 0.0-1.0, got {self.error_rate}")
        if not 0.0 <= self.health_score <= 1.0:
            raise ValueError(
                f"health_score must be 0.0-1.0, got {self.health_score}"
            )


@dataclass
class HealthConfig:
    """Configuration for health monitoring and circuit breaker.

    All thresholds are configurable to support different provider
    reliability profiles and deployment requirements.
    """

    # ── Sliding window ──
    window_size: int = 100  # Number of recent calls to track
    window_duration_seconds: float = 300.0  # Max age of entries in window (5 min)

    # ── Circuit breaker thresholds ──
    error_rate_threshold: float = 0.5  # Open circuit at 50% error rate
    latency_threshold_seconds: float = 30.0  # Consider slow if p95 > 30s
    min_requests_for_threshold: int = 5  # Min requests before evaluating thresholds

    # ── Recovery settings ──
    recovery_timeout_seconds: float = 60.0  # Wait before trying HALF_OPEN
    half_open_max_requests: int = 3  # Max probes in HALF_OPEN state
    half_open_success_threshold: int = 2  # Successes needed to close circuit
    backoff_multiplier: float = 2.0  # Exponential backoff multiplier
    max_recovery_timeout: float = 600.0  # Max backoff (10 min)

    # ── Health check ──
    health_check_interval: float = 30.0  # Periodic health check interval
    health_check_timeout: float = 10.0  # Timeout for health check calls
    health_score_decay: float = 0.95  # Exponential decay for health score

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.window_size < 1:
            raise ValueError(f"window_size must be >= 1, got {self.window_size}")
        if self.window_duration_seconds <= 0:
            raise ValueError(
                f"window_duration_seconds must be > 0, got {self.window_duration_seconds}"
            )
        if not 0.0 < self.error_rate_threshold <= 1.0:
            raise ValueError(
                f"error_rate_threshold must be 0.0-1.0, got {self.error_rate_threshold}"
            )
        if self.latency_threshold_seconds <= 0:
            raise ValueError(
                f"latency_threshold_seconds must be > 0, got {self.latency_threshold_seconds}"
            )
        if self.min_requests_for_threshold < 1:
            raise ValueError(
                f"min_requests_for_threshold must be >= 1, got {self.min_requests_for_threshold}"
            )
        if self.recovery_timeout_seconds <= 0:
            raise ValueError(
                f"recovery_timeout_seconds must be > 0, got {self.recovery_timeout_seconds}"
            )
        if self.half_open_max_requests < 1:
            raise ValueError(
                f"half_open_max_requests must be >= 1, got {self.half_open_max_requests}"
            )
        if self.half_open_success_threshold < 1:
            raise ValueError(
                f"half_open_success_threshold must be >= 1, got {self.half_open_success_threshold}"
            )
        if self.backoff_multiplier < 1.0:
            raise ValueError(
                f"backoff_multiplier must be >= 1.0, got {self.backoff_multiplier}"
            )
        if self.max_recovery_timeout < self.recovery_timeout_seconds:
            raise ValueError(
                f"max_recovery_timeout ({self.max_recovery_timeout}) must be >= "
                f"recovery_timeout_seconds ({self.recovery_timeout_seconds})"
            )
        if not 0.0 < self.health_score_decay <= 1.0:
            raise ValueError(
                f"health_score_decay must be 0.0-1.0, got {self.health_score_decay}"
            )


@dataclass
class _CallRecord:
    """Internal record of a single call."""

    timestamp: float
    latency: float
    success: bool
    error: Exception | None = None


# ── Circuit Breaker ────────────────────────────────────────────────────────


class CircuitBreaker:
    """
    Circuit breaker for a single provider/model.

    States:
        CLOSED → Normal. Tracks failures. Opens if thresholds exceeded.
        OPEN → Rejects immediately. Waits for recovery timeout.
        HALF_OPEN → Allows limited probes. Closes on success, re-opens on failure.

    Thread-safe: All state transitions use a threading.Lock.

    Usage:
        breaker = CircuitBreaker("provider-1", config)
        result = await breaker.call(some_async_function, *args)
    """

    def __init__(
        self,
        provider_id: str,
        config: HealthConfig | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.config = config or HealthConfig()

        self._state = CircuitState.CLOSED
        self._lock = threading.Lock()
        self._failure_count = 0
        self._success_count = 0
        self._half_open_requests = 0
        self._opened_at: float | None = None
        self._recovery_timeout = self.config.recovery_timeout_seconds
        self._consecutive_opens = 0

        logger.info(
            f"CircuitBreaker initialized for {provider_id}: "
            f"error_threshold={self.config.error_rate_threshold}, "
            f"recovery_timeout={self.config.recovery_timeout_seconds}s"
        )

    @property
    def state(self) -> CircuitState:
        """Current circuit state (thread-safe)."""
        with self._lock:
            # Auto-transition OPEN → HALF_OPEN if recovery timeout elapsed
            if self._state == CircuitState.OPEN and self._opened_at is not None:
                elapsed = time.monotonic() - self._opened_at
                if elapsed >= self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_requests = 0
                    self._success_count = 0
                    logger.info(
                        f"CircuitBreaker[{self.provider_id}]: "
                        f"OPEN → HALF_OPEN (recovery timeout elapsed: {elapsed:.1f}s)"
                    )
            return self._state

    @property
    def is_available(self) -> bool:
        """Whether the circuit allows requests through."""
        state = self.state  # Triggers auto-transition check
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            with self._lock:
                return self._half_open_requests < self.config.half_open_max_requests
        # OPEN — reject
        return False

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            self._success_count += 1
            self._failure_count = 0  # Reset failure streak

            if self._state == CircuitState.HALF_OPEN:
                if self._success_count >= self.config.half_open_success_threshold:
                    self._close_circuit()

    def record_failure(self, error: Exception | None = None) -> None:
        """Record a failed call."""
        with self._lock:
            self._failure_count += 1
            self._success_count = 0  # Reset success streak

            if self._state == CircuitState.HALF_OPEN:
                # Failure during probe → re-open with backoff
                self._open_circuit()
            elif self._state == CircuitState.CLOSED:
                # Check if we should open
                if self._failure_count >= self.config.min_requests_for_threshold:
                    self._open_circuit()

    def _open_circuit(self) -> None:
        """Transition to OPEN state. Caller must hold _lock."""
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._consecutive_opens += 1

        # Exponential backoff for recovery timeout
        if self._consecutive_opens > 1:
            self._recovery_timeout = min(
                self._recovery_timeout * self.config.backoff_multiplier,
                self.config.max_recovery_timeout,
            )

        logger.warning(
            f"CircuitBreaker[{self.provider_id}]: CLOSED/HALF_OPEN → OPEN "
            f"(failures={self._failure_count}, "
            f"recovery_timeout={self._recovery_timeout:.1f}s, "
            f"consecutive_opens={self._consecutive_opens})"
        )

    def _close_circuit(self) -> None:
        """Transition to CLOSED state. Caller must hold _lock."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_requests = 0
        self._consecutive_opens = 0
        self._recovery_timeout = self.config.recovery_timeout_seconds
        self._opened_at = None

        logger.info(f"CircuitBreaker[{self.provider_id}]: HALF_OPEN → CLOSED (recovered)")

    def reset(self) -> None:
        """Manually reset circuit to CLOSED state."""
        with self._lock:
            old_state = self._state
            self._close_circuit()
            if old_state != CircuitState.CLOSED:
                logger.info(
                    f"CircuitBreaker[{self.provider_id}]: manually reset from {old_state}"
                )

    async def call(
        self,
        func: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Execute an async function through the circuit breaker.

        If circuit is OPEN, raises CircuitOpenError immediately.
        If circuit is HALF_OPEN, limits concurrent probes.
        Records latency and success/failure automatically.

        Args:
            func: Async function to call
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            CircuitOpenError: If circuit is OPEN (fail-fast)
            Exception: Any exception raised by func (recorded as failure)
        """
        # Check availability
        if not self.is_available:
            raise CircuitOpenError(
                self.provider_id,
                self.state,
                f"Circuit breaker is {self.state.value} for {self.provider_id}",
            )

        # Track half-open probe
        if self.state == CircuitState.HALF_OPEN:
            with self._lock:
                self._half_open_requests += 1

        # Execute with timing
        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except CircuitOpenError:
            # Don't count circuit-open as a failure of the provider
            raise
        except Exception as e:
            self.record_failure(e)
            raise

    def get_state_info(self) -> dict[str, Any]:
        """Get detailed state information for diagnostics."""
        with self._lock:
            elapsed_since_open = None
            if self._opened_at is not None:
                elapsed_since_open = time.monotonic() - self._opened_at

            # Check availability inline to avoid deadlock with is_available property
            state = self._state
            if state == CircuitState.OPEN and self._opened_at is not None:
                elapsed = time.monotonic() - self._opened_at
                if elapsed >= self._recovery_timeout:
                    state = CircuitState.HALF_OPEN
                    self._state = state
                    self._half_open_requests = 0
                    self._success_count = 0

            if state == CircuitState.CLOSED:
                available = True
            elif state == CircuitState.HALF_OPEN:
                available = self._half_open_requests < self.config.half_open_max_requests
            else:
                available = False

            return {
                "provider_id": self.provider_id,
                "state": state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "half_open_requests": self._half_open_requests,
                "consecutive_opens": self._consecutive_opens,
                "recovery_timeout": self._recovery_timeout,
                "elapsed_since_open": elapsed_since_open,
                "is_available": available,
            }


# ── Health Monitor ─────────────────────────────────────────────────────────


class HealthMonitor:
    """
    Monitors provider health with sliding-window metrics.

    Tracks latency, error rates, and success rates per provider.
    Exposes aggregated metrics and health scores for routing decisions.

    Thread-safe: All state mutations use threading.Lock.

    Usage:
        monitor = HealthMonitor(config)
        monitor.record_call("provider-1", latency=0.5, success=True)
        metrics = monitor.get_metrics("provider-1")
        is_healthy = monitor.is_healthy("provider-1")
    """

    def __init__(self, config: HealthConfig | None = None) -> None:
        self.config = config or HealthConfig()

        # Per-provider call records (sliding window)
        self._records: dict[str, deque[_CallRecord]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

        # Cached metrics (updated lazily)
        self._metrics_cache: dict[str, HealthMetrics] = {}
        self._cache_timestamps: dict[str, float] = {}
        self._cache_ttl = 1.0  # Cache metrics for 1 second

        logger.info(
            f"HealthMonitor initialized: window={self.config.window_size}, "
            f"duration={self.config.window_duration_seconds}s"
        )

    def _get_lock(self, provider_id: str) -> threading.Lock:
        """Get or create a lock for a provider."""
        with self._global_lock:
            if provider_id not in self._locks:
                self._locks[provider_id] = threading.Lock()
            return self._locks[provider_id]

    def _get_records(self, provider_id: str) -> deque[_CallRecord]:
        """Get or create the records deque for a provider."""
        with self._global_lock:
            if provider_id not in self._records:
                self._records[provider_id] = deque(maxlen=self.config.window_size)
            return self._records[provider_id]

    def record_call(
        self,
        provider_id: str,
        latency: float,
        success: bool,
        error: Exception | None = None,
    ) -> None:
        """Record a call result for a provider.

        Args:
            provider_id: Provider or model identifier
            latency: Call duration in seconds
            success: Whether the call succeeded
            error: Exception if the call failed
        """
        lock = self._get_lock(provider_id)
        records = self._get_records(provider_id)

        record = _CallRecord(
            timestamp=time.monotonic(),
            latency=latency,
            success=success,
            error=error,
        )

        with lock:
            records.append(record)
            # Invalidate cache
            self._metrics_cache.pop(provider_id, None)
            self._cache_timestamps.pop(provider_id, None)

    def _prune_old_records(
        self, records: deque[_CallRecord], now: float
    ) -> list[_CallRecord]:
        """Remove records older than window_duration_seconds."""
        cutoff = now - self.config.window_duration_seconds
        return [r for r in records if r.timestamp >= cutoff]

    def _calculate_percentile(
        self, sorted_latencies: list[float], percentile: float
    ) -> float:
        """Calculate a percentile from sorted latencies."""
        if not sorted_latencies:
            return 0.0
        idx = int(len(sorted_latencies) * percentile)
        idx = min(idx, len(sorted_latencies) - 1)
        return sorted_latencies[idx]

    def get_metrics(self, provider_id: str) -> HealthMetrics:
        """Get aggregated health metrics for a provider.

        Returns cached metrics if available and fresh.
        """
        # Check cache
        now = time.monotonic()
        if (
            provider_id in self._metrics_cache
            and provider_id in self._cache_timestamps
            and now - self._cache_timestamps[provider_id] < self._cache_ttl
        ):
            return self._metrics_cache[provider_id]

        lock = self._get_lock(provider_id)
        records = self._get_records(provider_id)

        with lock:
            now_mono = time.monotonic()
            active_records = self._prune_old_records(records, now_mono)

            if not active_records:
                metrics = HealthMetrics(
                    provider_id=provider_id,
                    is_healthy=True,
                    health_score=1.0,
                )
                self._metrics_cache[provider_id] = metrics
                self._cache_timestamps[provider_id] = now_mono
                return metrics

            total = len(active_records)
            successes = sum(1 for r in active_records if r.success)
            failures = total - successes

            latencies = sorted(r.latency for r in active_records)
            avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

            success_rate = successes / total if total > 0 else 1.0
            error_rate = failures / total if total > 0 else 0.0

            # Health score: blend of success rate and latency penalty
            latency_penalty = 0.0
            if avg_latency > self.config.latency_threshold_seconds:
                # Penalize based on how far over threshold
                ratio = avg_latency / self.config.latency_threshold_seconds
                latency_penalty = min(0.5, (ratio - 1.0) * 0.5)

            health_score = max(0.0, success_rate - latency_penalty)
            is_healthy = (
                error_rate < self.config.error_rate_threshold
                and avg_latency < self.config.latency_threshold_seconds * 2
            )

            metrics = HealthMetrics(
                provider_id=provider_id,
                total_requests=total,
                successful_requests=successes,
                failed_requests=failures,
                avg_latency=avg_latency,
                p95_latency=self._calculate_percentile(latencies, 0.95),
                p99_latency=self._calculate_percentile(latencies, 0.99),
                min_latency=latencies[0] if latencies else float("inf"),
                max_latency=latencies[-1] if latencies else 0.0,
                success_rate=success_rate,
                error_rate=error_rate,
                is_healthy=is_healthy,
                health_score=health_score,
            )

            self._metrics_cache[provider_id] = metrics
            self._cache_timestamps[provider_id] = now_mono

            return metrics

    def is_healthy(self, provider_id: str) -> bool:
        """Check if a provider is healthy."""
        metrics = self.get_metrics(provider_id)
        return metrics.is_healthy

    def get_health_score(self, provider_id: str) -> float:
        """Get health score (0.0-1.0) for a provider."""
        metrics = self.get_metrics(provider_id)
        return metrics.health_score

    def get_all_metrics(self) -> dict[str, HealthMetrics]:
        """Get metrics for all tracked providers."""
        with self._global_lock:
            provider_ids = list(self._records.keys())

        return {pid: self.get_metrics(pid) for pid in provider_ids}

    def get_unhealthy_providers(self) -> list[str]:
        """Get list of unhealthy provider IDs."""
        return [
            pid
            for pid, metrics in self.get_all_metrics().items()
            if not metrics.is_healthy
        ]

    def reset(self, provider_id: str | None = None) -> None:
        """Reset metrics for a provider or all providers."""
        if provider_id:
            lock = self._get_lock(provider_id)
            with lock:
                records = self._get_records(provider_id)
                records.clear()
                self._metrics_cache.pop(provider_id, None)
                self._cache_timestamps.pop(provider_id, None)
                logger.info(f"HealthMonitor: reset metrics for {provider_id}")
        else:
            with self._global_lock:
                for lock in self._locks.values():
                    with lock:
                        pass  # Acquire to ensure consistency
                self._records.clear()
                self._metrics_cache.clear()
                self._cache_timestamps.clear()
                logger.info("HealthMonitor: reset all metrics")


# ── Resilient Provider Wrapper ─────────────────────────────────────────────


class ResilientProvider:
    """
    Wraps a provider with health monitoring and circuit breaking.

    Provides a transparent interface that automatically:
    - Records call metrics for health monitoring
    - Opens circuit breaker on repeated failures
    - Routes around unhealthy providers
    - Tracks latency and error rates

    Usage:
        resilient = ResilientProvider("provider-1", actual_provider, monitor, breaker)
        result = await resilient.complete(messages, model="gpt-4")
    """

    def __init__(
        self,
        provider_id: str,
        provider: "ModelProvider",
        health_monitor: HealthMonitor,
        circuit_breaker: CircuitBreaker,
    ) -> None:
        self.provider_id = provider_id
        self._provider = provider
        self._monitor = health_monitor
        self._breaker = circuit_breaker

    async def complete(self, *args: Any, **kwargs: Any) -> Any:
        """Execute completion through circuit breaker with health tracking."""
        start = time.monotonic()
        try:
            result = await self._breaker.call(
                self._provider.complete, *args, **kwargs
            )
            latency = time.monotonic() - start
            self._monitor.record_call(
                self.provider_id, latency=latency, success=True
            )
            return result
        except CircuitOpenError:
            # Circuit is open — don't record as provider failure
            raise
        except Exception as e:
            latency = time.monotonic() - start
            self._monitor.record_call(
                self.provider_id, latency=latency, success=False, error=e
            )
            raise

    def count_tokens(self, text: str, model: str) -> int:
        """Delegate token counting to underlying provider."""
        return self._provider.count_tokens(text, model)

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str
    ) -> float:
        """Delegate cost estimation to underlying provider."""
        return self._provider.estimate_cost(input_tokens, output_tokens, model)

    def get_capabilities(self, model: str) -> "ModelCapabilities":
        """Delegate capability query to underlying provider."""
        return self._provider.get_capabilities(model)

    def list_models(self) -> list[str]:
        """Delegate model listing to underlying provider."""
        return self._provider.list_models()

    async def close(self) -> None:
        """Close underlying provider."""
        await self._provider.close()

    @property
    def health_metrics(self) -> HealthMetrics:
        """Get current health metrics."""
        return self._monitor.get_metrics(self.provider_id)

    @property
    def circuit_state(self) -> CircuitState:
        """Get current circuit breaker state."""
        return self._breaker.state

    def is_available(self) -> bool:
        """Check if this provider is available (circuit not open)."""
        return self._breaker.is_available and self._monitor.is_healthy(self.provider_id)


# ── Exceptions ─────────────────────────────────────────────────────────────


class CircuitOpenError(Exception):
    """Raised when circuit breaker is OPEN (fail-fast)."""

    def __init__(
        self,
        provider_id: str,
        state: CircuitState,
        message: str = "",
    ) -> None:
        self.provider_id = provider_id
        self.state = state
        if not message:
            message = (
                f"Circuit breaker is {state.value} for provider '{provider_id}'"
            )
        super().__init__(message)


# ── Health Manager (Integration Point) ─────────────────────────────────────


class HealthManager:
    """
    Central manager for health monitoring and circuit breaking.

    Provides a unified interface for:
    - Managing circuit breakers per provider
    - Collecting and aggregating health metrics
    - Filtering providers by health status
    - Integration with ModelRouter for health-aware routing

    Thread-safe: All operations use internal locking.

    Usage:
        manager = HealthManager(config)
        manager.register_provider("deepseek-chat")
        resilient = manager.get_resilient_provider("deepseek-chat", provider)
    """

    def __init__(self, config: HealthConfig | None = None) -> None:
        self.config = config or HealthConfig()
        self.monitor = HealthMonitor(self.config)
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

        logger.info("HealthManager initialized")

    def register_provider(
        self,
        provider_id: str,
        config: HealthConfig | None = None,
    ) -> CircuitBreaker:
        """Register a provider for health monitoring.

        Args:
            provider_id: Unique provider identifier
            config: Optional override config for this provider

        Returns:
            CircuitBreaker instance for this provider
        """
        with self._lock:
            if provider_id not in self._breakers:
                breaker_config = config or self.config
                self._breakers[provider_id] = CircuitBreaker(
                    provider_id, breaker_config
                )
                logger.info(f"HealthManager: registered provider {provider_id}")
            return self._breakers[provider_id]

    def get_breaker(self, provider_id: str) -> CircuitBreaker:
        """Get circuit breaker for a provider. Auto-registers if needed."""
        with self._lock:
            if provider_id not in self._breakers:
                self._breakers[provider_id] = CircuitBreaker(
                    provider_id, self.config
                )
            return self._breakers[provider_id]

    def get_resilient_provider(
        self,
        provider_id: str,
        provider: "ModelProvider",
    ) -> ResilientProvider:
        """Wrap a provider with health monitoring and circuit breaking.

        Args:
            provider_id: Unique provider identifier
            provider: The actual ModelProvider to wrap

        Returns:
            ResilientProvider wrapping the original provider
        """
        breaker = self.get_breaker(provider_id)
        return ResilientProvider(provider_id, provider, self.monitor, breaker)

    def get_healthy_providers(self) -> list[str]:
        """Get list of healthy provider IDs."""
        with self._lock:
            return [
                pid
                for pid, breaker in self._breakers.items()
                if breaker.is_available and self.monitor.is_healthy(pid)
            ]

    def get_all_health_status(self) -> dict[str, dict[str, Any]]:
        """Get comprehensive health status for all providers."""
        with self._lock:
            result = {}
            for pid, breaker in self._breakers.items():
                metrics = self.monitor.get_metrics(pid)
                breaker_info = breaker.get_state_info()
                result[pid] = {
                    "is_healthy": metrics.is_healthy,
                    "health_score": metrics.health_score,
                    "circuit_state": breaker.state.value,
                    "circuit_available": breaker.is_available,
                    "success_rate": metrics.success_rate,
                    "error_rate": metrics.error_rate,
                    "avg_latency": metrics.avg_latency,
                    "p95_latency": metrics.p95_latency,
                    "total_requests": metrics.total_requests,
                    "breaker_info": breaker_info,
                }
            return result

    def reset_provider(self, provider_id: str) -> None:
        """Reset health state for a provider."""
        with self._lock:
            if provider_id in self._breakers:
                self._breakers[provider_id].reset()
            self.monitor.reset(provider_id)
            logger.info(f"HealthManager: reset {provider_id}")

    def reset_all(self) -> None:
        """Reset health state for all providers."""
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()
            self.monitor.reset()
            logger.info("HealthManager: reset all providers")

    def filter_by_health(
        self,
        provider_ids: list[str],
        min_health_score: float = 0.0,
        require_available: bool = True,
    ) -> list[str]:
        """Filter providers by health criteria.

        Args:
            provider_ids: List of provider IDs to filter
            min_health_score: Minimum health score (0.0-1.0)
            require_available: Whether circuit must be available

        Returns:
            Filtered list of provider IDs meeting criteria
        """
        result = []
        for pid in provider_ids:
            breaker = self.get_breaker(pid)
            metrics = self.monitor.get_metrics(pid)

            if require_available and not breaker.is_available:
                continue
            if metrics.health_score < min_health_score:
                continue
            result.append(pid)

        return result
