#!/usr/bin/env python3
"""
Example demonstrating health monitoring and circuit breaker usage.

This example shows:
1. Basic health monitoring with sliding window metrics
2. Circuit breaker state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
3. Resilient provider wrapper for automatic health tracking
4. Health manager for centralized provider health management
"""

import asyncio
import logging
import random

# Add src to path
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omni.router.health import (
    CircuitBreaker,
    HealthConfig,
    HealthManager,
    HealthMonitor,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def example_basic_health_monitoring() -> None:
    """Example 1: Basic health monitoring with sliding window."""
    print("\n=== Example 1: Basic Health Monitoring ===")

    # Create health monitor with fast config for demo
    config = HealthConfig(
        window_size=10,
        window_duration_seconds=30.0,
        error_rate_threshold=0.5,
        latency_threshold_seconds=2.0,
        min_requests_for_threshold=3,
        recovery_timeout_seconds=2.0,
    )

    monitor = HealthMonitor(config)

    # Simulate some calls
    print("Recording calls...")
    for i in range(15):
        success = random.random() > 0.3  # 70% success rate
        latency = random.uniform(0.1, 1.5)  # 0.1-1.5 seconds
        monitor.record_call("provider-1", latency=latency, success=success)

        # Print metrics every 5 calls
        if (i + 1) % 5 == 0:
            metrics = monitor.get_metrics("provider-1")
            print(f"  After {i+1} calls:")
            print(f"    Success rate: {metrics.success_rate:.2f}")
            print(f"    Avg latency: {metrics.avg_latency:.3f}s")
            print(f"    Is healthy: {metrics.is_healthy}")
            print(f"    Health score: {metrics.health_score:.2f}")

    print("\nFinal metrics:")
    metrics = monitor.get_metrics("provider-1")
    print(f"Total requests: {metrics.total_requests}")
    print(f"Successful: {metrics.successful_requests}")
    print(f"Failed: {metrics.failed_requests}")
    print(f"P95 latency: {metrics.p95_latency:.3f}s")


async def example_circuit_breaker() -> None:
    """Example 2: Circuit breaker state transitions."""
    print("\n=== Example 2: Circuit Breaker ===")

    # Create circuit breaker with fast recovery for demo
    config = HealthConfig(
        error_rate_threshold=0.5,
        min_requests_for_threshold=3,
        recovery_timeout_seconds=2.0,
        half_open_max_requests=2,
        half_open_success_threshold=1,
    )

    breaker = CircuitBreaker("demo-provider", config)
    print(f"Initial state: {breaker.state}")
    print(f"Is available: {breaker.is_available}")

    # Simulate failures to open circuit
    print("\nSimulating failures...")
    for i in range(3):
        breaker.record_failure(RuntimeError(f"Failure {i+1}"))
        print(f"  Failure {i+1}: State = {breaker.state}, Available = {breaker.is_available}")

    # Circuit should be OPEN now
    print(f"\nCircuit state after failures: {breaker.state}")
    print(f"Is available: {breaker.is_available}")

    # Wait for recovery timeout
    print(f"\nWaiting {config.recovery_timeout_seconds}s for recovery timeout...")
    await asyncio.sleep(config.recovery_timeout_seconds + 0.1)

    # Circuit should be HALF_OPEN now
    print(f"State after timeout: {breaker.state}")
    print(f"Is available: {breaker.is_available}")

    # Success in HALF_OPEN should close circuit
    print("\nRecording success in HALF_OPEN state...")
    breaker.record_success()
    print(f"State after success: {breaker.state}")
    print(f"Is available: {breaker.is_available}")


async def example_resilient_provider() -> None:
    """Example 3: Resilient provider wrapper."""
    print("\n=== Example 3: Resilient Provider ===")

    # Create mock provider
    mock_provider = MagicMock()
    mock_provider.complete = AsyncMock()

    # Create health manager
    config = HealthConfig(
        error_rate_threshold=0.5,
        min_requests_for_threshold=2,
        recovery_timeout_seconds=1.0,
    )
    manager = HealthManager(config)

    # Get resilient provider
    resilient = manager.get_resilient_provider("mock-provider", mock_provider)

    print(f"Provider ID: {resilient.provider_id}")
    print(f"Circuit state: {resilient.circuit_state}")
    print(f"Is available: {resilient.is_available()}")

    # Simulate successful call
    print("\nSimulating successful call...")
    mock_provider.complete.return_value = "Mock response"

    try:
        result = await resilient.complete([{"role": "user", "content": "Hello"}], model="gpt-4")
        print(f"  Result: {result}")
        print(f"  Circuit state: {resilient.circuit_state}")

        # Check health metrics
        metrics = resilient.health_metrics
        print("  Health metrics:")
        print(f"    Total requests: {metrics.total_requests}")
        print(f"    Success rate: {metrics.success_rate:.2f}")

    except Exception as e:
        print(f"  Error: {e}")


async def example_health_manager() -> None:
    """Example 4: Health manager for multiple providers."""
    print("\n=== Example 4: Health Manager ===")

    # Create health manager
    config = HealthConfig(
        window_size=20,
        error_rate_threshold=0.4,
        latency_threshold_seconds=3.0,
        min_requests_for_threshold=3,
        recovery_timeout_seconds=3.0,
    )

    manager = HealthManager(config)

    # Register multiple providers
    providers = ["openai", "anthropic", "google", "deepseek"]
    for provider_id in providers:
        manager.register_provider(provider_id)
        print(f"Registered: {provider_id}")

    # Simulate different health patterns
    print("\nSimulating health patterns...")

    # OpenAI: mostly healthy
    for _ in range(10):
        manager.monitor.record_call("openai", latency=0.2, success=True)

    # Anthropic: some failures
    for _ in range(8):
        manager.monitor.record_call("anthropic", latency=0.3, success=True)
    for _ in range(2):
        manager.monitor.record_call("anthropic", latency=5.0, success=False)

    # Google: many failures (circuit should open)
    for _ in range(5):
        manager.monitor.record_call("google", latency=0.1, success=False)
    google_breaker = manager.get_breaker("google")
    for _ in range(3):
        google_breaker.record_failure()

    # Deepseek: no calls yet

    # Get health status
    print("\nHealth status:")
    status = manager.get_all_health_status()
    for provider_id, info in status.items():
        print(f"  {provider_id}:")
        print(f"    Healthy: {info['is_healthy']}")
        print(f"    Health score: {info['health_score']:.2f}")
        print(f"    Circuit: {info['circuit_state']}")
        print(f"    Available: {info['circuit_available']}")
        print(f"    Success rate: {info['success_rate']:.2f}")

    # Filter healthy providers
    print("\nHealthy providers (available and health_score > 0.5):")
    healthy = manager.filter_by_health(providers, min_health_score=0.5, require_available=True)
    for provider_id in healthy:
        print(f"  ✓ {provider_id}")

    print("\nAll healthy providers (from manager):")
    all_healthy = manager.get_healthy_providers()
    for provider_id in all_healthy:
        print(f"  ✓ {provider_id}")


async def main() -> None:
    """Run all examples."""
    print("Health Monitoring & Circuit Breaker Examples")
    print("=" * 50)

    await example_basic_health_monitoring()
    await example_circuit_breaker()
    await example_resilient_provider()
    await example_health_manager()

    print("\n" + "=" * 50)
    print("All examples completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
