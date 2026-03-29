#!/usr/bin/env python3
"""
Example: Single Agent with Smart Model Routing

This example demonstrates how the Model Router automatically selects
the most appropriate model for different types of tasks based on:
1. Task type and complexity
2. Required capabilities
3. Cost constraints
4. Quality requirements
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omni.router import ModelRouter
from omni.router.strategy import (
    CostOptimizedStrategy,
    RoutingStrategy,
)
from omni.task.models import Task, TaskType, ComplexityEstimate


async def demonstrate_basic_routing():
    """Demonstrate basic model routing for different task types."""
    print("🚀 Single Agent with Smart Model Routing")
    print("=" * 60)

    # Create router with cost-optimized strategy
    router = ModelRouter(strategy=CostOptimizedStrategy())

    # Example 1: Simple formatting task
    print("\n1. Simple Formatting Task")
    print("-" * 40)

    format_task = Task(
        description="Format Python code according to PEP 8 guidelines",
        task_type=TaskType.CONFIGURATION,
        complexity=ComplexityEstimate(
            code_complexity=1,
            integration_complexity=1,
            testing_complexity=1,
            unknown_factor=1,
            reasoning="Simple formatting task",
        ),
    )

    selected_model = await router.select_model(format_task)
    print(f"   Task: {format_task.description[:50]}...")
    print(f"   Type: {format_task.task_type.value}")
    print(f"   Selected model: {selected_model}")
    print(f"   Reasoning: {router.get_last_selection_reasoning()}")

    # Example 2: Code generation task
    print("\n2. Code Generation Task")
    print("-" * 40)

    code_task = Task(
        description="Implement user authentication API with JWT tokens",
        task_type=TaskType.CODE_GENERATION,
        complexity=ComplexityEstimate(
            code_complexity=5,
            integration_complexity=4,
            testing_complexity=3,
            unknown_factor=2,
            reasoning="Standard API implementation",
        ),
    )

    selected_model = await router.select_model(code_task)
    print(f"   Task: {code_task.description[:50]}...")
    print(f"   Type: {code_task.task_type.value}")
    print(f"   Selected model: {selected_model}")
    print(f"   Reasoning: {router.get_last_selection_reasoning()}")

    # Example 3: Complex architecture task
    print("\n3. Architecture Design Task")
    print("-" * 40)

    arch_task = Task(
        description="Design microservices architecture for scalable e-commerce platform",
        task_type=TaskType.ANALYSIS,
        complexity=ComplexityEstimate(
            code_complexity=8,
            integration_complexity=9,
            testing_complexity=7,
            unknown_factor=8,
            reasoning="Complex architectural design",
        ),
    )

    selected_model = await router.select_model(arch_task)
    print(f"   Task: {arch_task.description[:50]}...")
    print(f"   Type: {arch_task.task_type.value}")
    print(f"   Selected model: {selected_model}")
    print(f"   Reasoning: {router.get_last_selection_reasoning()}")

    return router


async def demonstrate_strategy_comparison():
    """Compare different routing strategies."""
    print("\n\n🔍 Comparing Routing Strategies")
    print("=" * 60)

    task = Task(
        description="Implement real-time chat feature with WebSockets",
        task_type=TaskType.CODE_GENERATION,
        complexity=ComplexityEstimate(
            code_complexity=6,
            integration_complexity=7,
            testing_complexity=5,
            unknown_factor=4,
            reasoning="Real-time feature with integration complexity",
        ),
    )

    strategies = [
        ("Cost-Optimized", CostOptimizedStrategy()),
        # Note: QualityOptimizedStrategy and BalancedStrategy would be implemented
        # in a real deployment. Using CostOptimizedStrategy for demo.
        ("Cost-Optimized (Alternative)", CostOptimizedStrategy()),
    ]

    for strategy_name, strategy in strategies:
        print(f"\n{strategy_name} Strategy:")
        print("-" * 30)

        router = ModelRouter(strategy=strategy)
        selected_model = await router.select_model(task)

        # Get cost estimate
        cost_estimate = await router.estimate_cost(task, selected_model)

        print(f"   Selected model: {selected_model}")
        print(f"   Estimated cost: ${cost_estimate:.6f}")
        print(f"   Reasoning: {router.get_last_selection_reasoning()[:80]}...")


async def demonstrate_budget_constraints():
    """Demonstrate routing with budget constraints."""
    print("\n\n💰 Routing with Budget Constraints")
    print("=" * 60)

    # Create router with budget constraint
    from omni.router.budget import BudgetConstraint

    budget = BudgetConstraint(max_cost=0.001)  # $0.001 maximum
    router = ModelRouter(constraints=[budget])

    tasks = [
        Task(
            description="Write comprehensive unit tests for authentication module",
            task_type=TaskType.TESTING,
            complexity=ComplexityEstimate(
                code_complexity=3,
                integration_complexity=2,
                testing_complexity=4,
                unknown_factor=2,
                reasoning="Test writing with moderate complexity",
            ),
        ),
        Task(
            description="Perform security audit of payment processing code",
            task_type=TaskType.SECURITY,
            complexity=ComplexityEstimate(
                code_complexity=7,
                integration_complexity=6,
                testing_complexity=8,
                unknown_factor=5,
                reasoning="Critical security audit",
            ),
        ),
    ]

    for i, task in enumerate(tasks, 1):
        print(f"\n{i}. {task.task_type.value.title()} Task (Budget: ${budget.max_cost})")
        print("-" * 50)

        try:
            selected_model = await router.select_model(task)
            cost_estimate = await router.estimate_cost(task, selected_model)

            print(f"   Task: {task.description[:60]}...")
            print(f"   Selected model: {selected_model}")
            print(f"   Estimated cost: ${cost_estimate:.6f}")

            if cost_estimate > budget.max_cost:
                print("   ⚠️  Warning: Cost exceeds budget, but router found best option")

        except Exception as e:
            print(f"   ❌ Error: {e}")
            print(f"   Reason: No model found within budget constraints")


async def demonstrate_fallback_chain():
    """Demonstrate automatic fallback when primary model fails."""
    print("\n\n🔄 Automatic Fallback Chain")
    print("=" * 60)

    from omni.router.models import RoutingDecision

    router = ModelRouter()

    # Simulate a task that might fail with first choice
    task = Task(
        description="Generate complex data visualization with interactive elements",
        task_type=TaskType.CODE_GENERATION,
        complexity=ComplexityEstimate(
            code_complexity=7,
            integration_complexity=6,
            testing_complexity=5,
            unknown_factor=6,
            reasoning="Complex visualization with integration needs",
        ),
    )

    print("Primary selection:")
    primary_model = await router.select_model(task)
    print(f"   Primary model: {primary_model}")

    # Simulate failure and get fallback
    print("\nSimulating primary model failure...")
    fallback_chain = router.get_fallback_chain(task, primary_model)

    print(f"   Fallback chain ({len(fallback_chain)} models):")
    for i, fallback in enumerate(fallback_chain, 1):
        cost = await router.estimate_cost(task, fallback.model_id)
        print(f"   {i}. {fallback.model_id} (${cost:.6f})")
        print(f"      Reason: {fallback.reasoning}")


async def demonstrate_real_time_adaptation():
    """Demonstrate real-time routing adaptation based on performance."""
    print("\n\n📊 Real-time Routing Adaptation")
    print("=" * 60)

    from omni.router.health import ModelHealthMonitor

    # Create health monitor to track model performance
    monitor = ModelHealthMonitor()

    # Simulate some performance data
    performance_data = [
        ("openai/gpt-4", 0.95, 2.5, 0.00003),  # success_rate, avg_latency_sec, avg_cost
        ("anthropic/claude-3-haiku", 0.92, 1.8, 0.00001),
        ("deepseek/deepseek-chat", 0.88, 1.5, 0.000005),
    ]

    for model_id, success_rate, latency, cost in performance_data:
        monitor.record_performance(
            model_id=model_id,
            success_rate=success_rate,
            avg_latency=latency,
            avg_cost=cost,
            task_type="code_generation",
        )

    # Create router with adaptive strategy
    # Note: AdaptiveStrategy would be implemented in a real deployment
    # Using CostOptimizedStrategy for demo
    from omni.router.strategy import RoutingStrategy
    
    class AdaptiveStrategy(RoutingStrategy):
        """Demo adaptive strategy for illustration."""
        def __init__(self, health_monitor=None, update_interval=300):
            self.health_monitor = health_monitor
            self.update_interval = update_interval
            
        def select_model(self, task, available_models, context=None):
            # Simplified demo implementation
            return available_models[0] if available_models else None

    adaptive_router = ModelRouter(
        strategy=AdaptiveStrategy(health_monitor=monitor, update_interval=300)
    )

    task = Task(
        description="Refactor database layer to use connection pooling",
        task_type=TaskType.CODE_GENERATION,
    )

    print("Current performance-aware routing:")
    selected_model = await adaptive_router.select_model(task)
    print(f"   Selected model: {selected_model}")
    print(f"   Reasoning: {adaptive_router.get_last_selection_reasoning()}")

    # Show performance metrics
    print("\nModel performance metrics:")
    for model_id, success_rate, latency, cost in performance_data:
        health = monitor.get_model_health(model_id, "code_generation")
        if health:
            print(f"   {model_id}:")
            print(f"      Success rate: {health.success_rate:.1%}")
            print(f"      Avg latency: {health.avg_latency:.1f}s")
            print(f"      Avg cost: ${health.avg_cost:.6f}")
            print(f"      Health score: {health.health_score:.2f}/10")


async def main():
    """Run all demonstrations."""
    try:
        # Basic routing examples
        router = await demonstrate_basic_routing()

        # Strategy comparison
        await demonstrate_strategy_comparison()

        # Budget constraints
        await demonstrate_budget_constraints()

        # Fallback chain
        await demonstrate_fallback_chain()

        # Real-time adaptation
        await demonstrate_real_time_adaptation()

        # Show router statistics
        print("\n\n📈 Router Statistics")
        print("=" * 60)
        stats = router.get_statistics()
        print(f"   Total routing decisions: {stats.total_decisions}")
        print(f"   Average decision time: {stats.avg_decision_time_ms:.1f}ms")
        print(f"   Models available: {stats.models_available}")

        print("\n✅ Demonstration completed successfully!")

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