# Health Monitoring & Circuit Breaker System

## Overview

The Health Monitoring & Circuit Breaker system provides resilient provider management for the Omni-LLM router. It implements:

1. **Health Monitoring**: Continuous tracking of provider health metrics (latency, error rates, success rates)
2. **Circuit Breaker Pattern**: Fail-fast protection for unhealthy providers with automatic recovery
3. **Resilient Provider Wrapper**: Transparent wrapper that adds health tracking and circuit breaking to any provider
4. **Health Manager**: Centralized management of provider health states

## Architecture

### Core Components

#### 1. HealthMonitor
- Tracks sliding-window metrics per provider
- Calculates success rates, error rates, latency statistics
- Provides health scores (0.0-1.0) for routing decisions
- Thread-safe with configurable window sizes

#### 2. CircuitBreaker
- Implements three-state circuit breaker pattern:
  - **CLOSED**: Normal operation, requests pass through
  - **OPEN**: Fail-fast, requests rejected immediately
  - **HALF_OPEN**: Recovery probe, limited requests allowed
- Configurable thresholds (error rate, latency)
- Exponential backoff for recovery
- Automatic state transitions

#### 3. ResilientProvider
- Wraps any ModelProvider with health monitoring
- Automatically records call metrics
- Integrates with circuit breaker for fail-fast protection
- Transparent interface (same API as underlying provider)

#### 4. HealthManager
- Central registry for provider health states
- Factory for creating resilient providers
- Methods for filtering providers by health status
- Comprehensive health status reporting

## Configuration

### HealthConfig
All parameters are configurable:

```python
config = HealthConfig(
    # Sliding window
    window_size=100,                    # Number of recent calls to track
    window_duration_seconds=300.0,      # Max age of entries (5 minutes)
    
    # Circuit breaker thresholds
    error_rate_threshold=0.5,           # Open circuit at 50% error rate
    latency_threshold_seconds=30.0,     # Consider slow if p95 > 30s
    min_requests_for_threshold=5,       # Min requests before evaluating
    
    # Recovery settings
    recovery_timeout_seconds=60.0,      # Wait before trying HALF_OPEN
    half_open_max_requests=3,           # Max probes in HALF_OPEN state
    half_open_success_threshold=2,      # Successes needed to close circuit
    backoff_multiplier=2.0,             # Exponential backoff multiplier
    max_recovery_timeout=600.0,         # Max backoff (10 minutes)
    
    # Health check
    health_check_interval=30.0,         # Periodic health check interval
    health_check_timeout=10.0,          # Timeout for health check calls
    health_score_decay=0.95,            # Exponential decay for health score
)
```

## Usage Examples

### Basic Health Monitoring

```python
from omni.router.health import HealthMonitor, HealthConfig

config = HealthConfig(window_size=50)
monitor = HealthMonitor(config)

# Record calls
monitor.record_call("provider-1", latency=0.5, success=True)
monitor.record_call("provider-1", latency=1.0, success=False, error=RuntimeError())

# Get metrics
metrics = monitor.get_metrics("provider-1")
print(f"Success rate: {metrics.success_rate:.2f}")
print(f"Avg latency: {metrics.avg_latency:.3f}s")
print(f"Is healthy: {metrics.is_healthy}")
```

### Circuit Breaker

```python
from omni.router.health import CircuitBreaker

breaker = CircuitBreaker("my-provider", config)

# Check availability
if breaker.is_available:
    result = await breaker.call(some_async_function, arg1, arg2)
else:
    print("Circuit is open - failing fast")

# Manual state management
breaker.record_success()    # Record success
breaker.record_failure()    # Record failure
breaker.reset()             # Manually reset circuit
```

### Resilient Provider Wrapper

```python
from omni.router.health import HealthManager

manager = HealthManager(config)

# Wrap any provider
resilient = manager.get_resilient_provider("openai", openai_provider)

# Use exactly like the original provider
result = await resilient.complete(messages, model="gpt-4")

# Access health information
print(f"Circuit state: {resilient.circuit_state}")
print(f"Is available: {resilient.is_available()}")
metrics = resilient.health_metrics
```

### Health Manager for Multiple Providers

```python
# Register providers
manager.register_provider("openai")
manager.register_provider("anthropic")
manager.register_provider("google")

# Get health status
status = manager.get_all_health_status()
for provider_id, info in status.items():
    print(f"{provider_id}: {info['circuit_state']}, healthy={info['is_healthy']}")

# Filter healthy providers
healthy = manager.filter_by_health(
    ["openai", "anthropic", "google"],
    min_health_score=0.5,
    require_available=True
)

# Get all healthy providers
all_healthy = manager.get_healthy_providers()
```

## Integration with ModelRouter

The health monitoring system integrates seamlessly with the ModelRouter:

```python
from omni.router import ModelRouter, RouterConfig
from omni.router.health import HealthConfig

# Create router with health monitoring
health_config = HealthConfig()
router_config = RouterConfig(
    health_config=health_config,
    # ... other config
)

router = ModelRouter(router_config)

# The router automatically:
# 1. Creates HealthManager internally
# 2. Wraps all providers with ResilientProvider
# 3. Skips unhealthy providers in fallback chains
# 4. Records health metrics for all calls
```

## Health Metrics

### HealthMetrics Data Model

```python
@dataclass
class HealthMetrics:
    provider_id: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    
    # Latency stats (seconds)
    avg_latency: float
    p95_latency: float
    p99_latency: float
    min_latency: float
    max_latency: float
    
    # Rate metrics (0.0 to 1.0)
    success_rate: float
    error_rate: float
    
    # Circuit breaker state
    circuit_state: CircuitState
    circuit_open_count: int
    
    # Health status
    is_healthy: bool
    health_score: float  # 0.0 (unhealthy) to 1.0 (fully healthy)
```

### Health Score Calculation

The health score is a composite metric:
- **Success rate component**: Direct weight (e.g., 90% success → 0.9)
- **Latency penalty**: Penalty if average latency exceeds threshold
- **Final score**: `max(0.0, success_rate - latency_penalty)`

## Thread Safety

All components are thread-safe:
- **HealthMonitor**: Uses per-provider locks for concurrent writes
- **CircuitBreaker**: Uses threading.Lock for state transitions
- **HealthManager**: Uses global lock for provider registration
- **Metrics cache**: TTL-based caching with thread-safe updates

## Testing

Comprehensive test coverage:
- Unit tests for each component
- Integration tests with ModelRouter
- Concurrency tests for thread safety
- Edge case tests for boundary conditions

Run tests:
```bash
pytest tests/test_health.py -v
pytest tests/test_router.py::TestHealthIntegration -v
```

## Best Practices

### Configuration Guidelines

1. **Window Size**: Balance between responsiveness and stability
   - Small window (10-50): Quick to detect issues, noisy
   - Large window (100-500): Stable metrics, slow to respond

2. **Error Rate Threshold**: Set based on provider reliability
   - Reliable providers: 0.3-0.5 (30-50% errors)
   - Unreliable providers: 0.1-0.2 (10-20% errors)

3. **Recovery Timeout**: Consider provider recovery patterns
   - Fast-recovering providers: 30-60 seconds
   - Slow-recovering providers: 2-5 minutes

4. **Backoff Strategy**: Use exponential backoff for repeated failures
   - Start with 1x recovery timeout
   - Double each time (2x, 4x, 8x...)
   - Cap at reasonable maximum (e.g., 10 minutes)

### Monitoring and Alerting

1. **Health Score Monitoring**: Alert if health score drops below threshold
2. **Circuit State Changes**: Log circuit openings and closings
3. **Latency Spikes**: Alert if p95 latency exceeds threshold
4. **Error Rate Increases**: Alert if error rate trends upward

### Integration Patterns

1. **Graceful Degradation**: Route around unhealthy providers
2. **Fallback Chains**: Include healthy providers in fallback order
3. **Health-Aware Routing**: Prefer providers with higher health scores
4. **Circuit Reset**: Manual reset for maintenance or known issues

## Performance Considerations

- **Memory**: O(window_size) per provider for call records
- **CPU**: Minimal overhead for metrics calculation
- **Latency**: Sub-millisecond overhead for health tracking
- **Concurrency**: Designed for high concurrent access

## Troubleshooting

### Common Issues

1. **Circuit stuck OPEN**: Check recovery timeout and backoff multiplier
2. **Inaccurate health metrics**: Verify window size and duration
3. **Thread deadlocks**: Ensure proper lock acquisition order
4. **Memory growth**: Monitor number of tracked providers

### Debugging

Enable debug logging:
```python
import logging
logging.getLogger("omni.router.health").setLevel(logging.DEBUG)
```

Check circuit breaker state:
```python
info = breaker.get_state_info()
print(f"State: {info['state']}")
print(f"Failures: {info['failure_count']}")
print(f"Recovery timeout: {info['recovery_timeout']}")
```

## Future Enhancements

Planned features:
1. **Health check endpoints**: HTTP endpoints for provider health
2. **Metrics export**: Prometheus/OpenTelemetry integration
3. **Adaptive thresholds**: Auto-adjust based on historical patterns
4. **Health dashboards**: Web UI for monitoring provider health
5. **Predictive failure detection**: ML-based failure prediction
