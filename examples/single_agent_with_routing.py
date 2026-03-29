#!/usr/bin/env python3
"""
Example: Single Agent with Smart Model Routing

This example demonstrates how the Model Router automatically selects
the most appropriate model for different types of tasks based on:
1. Task type and complexity
2. Cost constraints
3. Health monitoring and circuit breaking
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omni.router import (
    CostOptimizedStrategy,
    ModelRouter,
    RouterConfig,
    RoutingContext,
    TaskType,
)
from omni.router.budget import BudgetConfig, BudgetTracker
from omni.router.health import CircuitBreaker, HealthConfig, HealthMonitor


async def demonstrate_basic_routing():
    """Demonstrate basic model routing for different task types."""
    print("🚀 Single Agent with Smart Model Routing")
    print("=" * 60)

    # Create router with cost-optimized strategy
    config = RouterConfig()
    router = ModelRouter(config)

    # Register a cost-optimized strategy
    strategy = CostOptimizedStrategy()
    router.register_strategy("cost_optimized", strategy)

    # Example 1: Simple formatting task
    print("\n1. Simple Formatting Task")
    print("-" * 40)

    context = RoutingContext(
        task_type=TaskType.CODING,
        file_count=1,
        complexity=0.2,
    )

    try:
        selection = router.select_model(
            task_type=TaskType.CODING,
            context=context,
            strategy_name="cost_optimized",
        )
        print(f"   Task type: {TaskType.CODING.value}")
        print(f"   Selected model: {selection.model_id}")
        print(f"   Reason: {selection.reason}")
        print(f"   Estimated cost: ${selection.estimated_cost.total_cost_usd:.6f}")
        print(f"   Confidence: {selection.confidence:.2f}")
    except Exception as e:
        print(f"   ⚠️  Could not select model: {e}")

    # Example 2: Code generation task
    print("\n2. Code Generation Task")
    print("-" * 40)

    context = RoutingContext(
        task_type=TaskType.CODING,
        file_count=5,
        complexity=0.6,
    )

    try:
        selection = router.select_model(
            task_type=TaskType.CODING,
            context=context,
            strategy_name="cost_optimized",
        )
        print(f"   Task type: {TaskType.CODING.value}")
        print(f"   Selected model: {selection.model_id}")
        print(f"   Reason: {selection.reason}")
        print(f"   Estimated cost: ${selection.estimated_cost.total_cost_usd:.6f}")
        print(f"   Confidence: {selection.confidence:.2f}")
    except Exception as e:
        print(f"   ⚠️  Could not select model: {e}")

    # Example 3: Architecture/analysis task
    print("\n3. Architecture Design Task")
    print("-" * 40)

    context = RoutingContext(
        task_type=TaskType.ARCHITECTURE,
        file_count=10,
        complexity=0.9,
    )

    try:
        selection = router.select_model(
            task_type=TaskType.ARCHITECTURE,
            context=context,
            strategy_name="cost_optimized",
        )
        print(f"   Task type: {TaskType.ARCHITECTURE.value}")
        print(f"   Selected model: {selection.model_id}")
        print(f"   Reason: {selection.reason}")
        print(f"   Estimated cost: ${selection.estimated_cost.total_cost_usd:.6f}")
        print(f"   Confidence: {selection.confidence:.2f}")
    except Exception as e:
        print(f"   ⚠️  Could not select model: {e}")

    return router


async def demonstrate_model_ranking():
    """Demonstrate ranking all candidate models for a task."""
    print("\n\n🔍 Model Ranking for Task")
    print("=" * 60)

    config = RouterConfig()
    router = ModelRouter(config)
    strategy = CostOptimizedStrategy()
    router.register_strategy("cost_optimized", strategy)

    context = RoutingContext(
        task_type=TaskType.CODING,
        file_count=3,
        complexity=0.5,
    )

    try:
        ranked = router.rank_models(
            task_type=TaskType.CODING,
            context=context,
            strategy_name="cost_optimized",
        )

        print(f"   Ranked models for {TaskType.CODING.value} task:")
        for i, model in enumerate(ranked[:5], 1):
            print(
                f"   {i}. {model.model_id:25} "
                f"score={model.score:.3f}  "
                f"cost=${model.cost_estimate.total_cost_usd:.6f}  "
                f"quality={model.quality_estimate:.2f}"
            )
    except Exception as e:
        print(f"   ⚠️  Could not rank models: {e}")


async def demonstrate_budget_tracking():
    """Demonstrate budget tracking and enforcement."""
    print("\n\n💰 Budget Tracking")
    print("=" * 60)

    # Create a budget tracker with limits
    budget_config = BudgetConfig(
        daily_limit=1.0,  # $1.00 per day
        per_session_limit=0.10,  # $0.10 per session
    )
    tracker = BudgetTracker(config=budget_config, session_id="demo-session")

    print(f"   Daily limit: ${budget_config.daily_limit:.2f}")
    print(f"   Session limit: ${budget_config.per_session_limit:.2f}")

    # Simulate some spending
    for _i, amount in enumerate([0.01, 0.02, 0.005], 1):
        tracker.track_spending(amount)
        status = tracker.get_budget_status()
        print(f"\n   After ${amount:.3f} spend:")
        print(f"     Session spent: ${status['session']['spent']:.4f}")
        print(f"     Session remaining: ${status['session']['remaining']:.4f}")
        print(f"     Daily spent: ${status['daily']['spent']:.4f}")

    # Check budget before a task
    allowed, reason = tracker.check_budget(estimated_cost=0.05)
    print(f"\n   Budget check for $0.05 task: {'✅ Allowed' if allowed else '❌ Denied'}")
    if not allowed:
        print(f"   Reason: {reason}")

    # Get warnings
    warnings = tracker.get_warnings()
    if warnings:
        print("\n   ⚠️  Budget warnings:")
        for w in warnings:
            print(f"     - {w}")


async def demonstrate_health_monitoring():
    """Demonstrate health monitoring and circuit breaking."""
    print("\n\n🏥 Health Monitoring & Circuit Breaker")
    print("=" * 60)

    # Create health monitor
    health_config = HealthConfig(
        window_size=50,
        error_rate_threshold=0.5,
        latency_threshold_seconds=10.0,
    )
    monitor = HealthMonitor(config=health_config)

    # Simulate provider call results
    provider_results = [
        ("openai/gpt-4", 1.2, True),
        ("openai/gpt-4", 1.5, True),
        ("openai/gpt-4", 2.0, False),
        ("anthropic/claude-3-haiku", 0.8, True),
        ("anthropic/claude-3-haiku", 1.0, True),
        ("deepseek/deepseek-chat", 0.5, True),
        ("deepseek/deepseek-chat", 0.6, True),
    ]

    for provider_id, latency, success in provider_results:
        monitor.record_call(provider_id, latency=latency, success=success)

    # Show health metrics
    print("   Provider health metrics:")
    for provider_id in ["openai/gpt-4", "anthropic/claude-3-haiku", "deepseek/deepseek-chat"]:
        metrics = monitor.get_metrics(provider_id)
        status = "✅" if metrics.is_healthy else "❌"
        print(
            f"   {status} {provider_id:30} "
            f"success_rate={metrics.success_rate:.1%}  "
            f"avg_latency={metrics.avg_latency:.2f}s  "
            f"health_score={metrics.health_score:.2f}"
        )

    # Demonstrate circuit breaker
    print("\n   Circuit Breaker demo:")
    breaker = CircuitBreaker("demo-provider", config=health_config)
    print(f"   Initial state: {breaker.state.value}")
    print(f"   Available: {breaker.is_available}")

    # Simulate failures
    for i in range(6):
        breaker.record_failure(Exception(f"Simulated failure {i+1}"))
        print(
            f"   After failure {i+1}: "
            f"state={breaker.state.value}, "
            f"available={breaker.is_available}"
        )


async def main():
    """Run all demonstrations."""
    try:
        # Basic routing examples
        await demonstrate_basic_routing()

        # Model ranking
        await demonstrate_model_ranking()

        # Budget tracking
        await demonstrate_budget_tracking()

        # Health monitoring
        await demonstrate_health_monitoring()

        print("\n\n✅ Demonstration completed successfully!")

    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        print("Make sure you have installed Omni-LLM in development mode:")
        print("  pip install -e '.[dev]'")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
