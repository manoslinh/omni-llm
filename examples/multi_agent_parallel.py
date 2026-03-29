#!/usr/bin/env python3
"""
Example: Multi-Agent Parallel Execution

This example demonstrates how Omni-LLM coordinates multiple AI agents
to work in parallel on complex tasks, including:
1. Task decomposition into subtasks
2. Dependency analysis and parallelization
3. Multi-agent coordination and assignment
4. Parallel execution with result integration
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omni.coordination import CoordinationEngine, CoordinationObserver, WorkflowPlan
from omni.coordination.agents import AgentProfile
from omni.coordination.matcher import AgentAssignment
from omni.decomposition import TaskDecompositionEngine
from omni.decomposition.models import Subtask, SubtaskType
from omni.task.models import ComplexityEstimate, TaskGraph, TaskType


class DemoObserver(CoordinationObserver):
    """Observer that prints coordination events for demonstration."""

    def on_agent_assigned(self, task_id: str, assignment: AgentAssignment) -> None:
        print(f"   🤝 Task '{task_id[:8]}...' → {assignment.agent_id}")
        print(f"      Model: {assignment.agent_profile.model_id}")
        print(f"      Confidence: {assignment.confidence.value}")

    def on_workflow_planned(self, plan: WorkflowPlan) -> None:
        print(f"   📋 Workflow plan created: {plan.plan_id}")
        print(f"      Steps: {plan.total_steps}, Parallel: {plan.parallel_steps}")

    def on_step_started(self, step_id: str, task_ids: list[str]) -> None:
        print(f"   ▶️  Step '{step_id}' started with {len(task_ids)} tasks")

    def on_step_completed(self, step_id: str, results: dict[str, str]) -> None:
        print(f"   ✅ Step '{step_id}' completed: {len(results)} results")

    def on_escalation(self, task_id: str, from_agent: str, to_agent: str, reason: str) -> None:
        print(f"   ⚠️  Escalation: {task_id[:8]}... from {from_agent} to {to_agent}")
        print(f"      Reason: {reason}")


def create_agent_profiles() -> list[AgentProfile]:
    """Create example agent profiles with different capabilities."""
    return [
        AgentProfile(
            agent_id="intern",
            display_name="Intern",
            model_id="mimo/mimo-v2-flash",
            capabilities=["formatting", "simple_tasks", "testing", "documentation"],
            cost_per_token=0.000001,
            max_concurrent_tasks=5,
            description="Fast, cheap agent for simple tasks",
        ),
        AgentProfile(
            agent_id="coder",
            display_name="Coder",
            model_id="deepseek/deepseek-chat",
            capabilities=[
                "code_generation",
                "debugging",
                "refactoring",
                "testing",
                "integration",
            ],
            cost_per_token=0.000002,
            max_concurrent_tasks=3,
            description="General-purpose coding agent",
        ),
        AgentProfile(
            agent_id="reader",
            display_name="Reader",
            model_id="moonshot/kimi-k2.5",
            capabilities=[
                "code_review",
                "long_context",
                "analysis",
                "documentation",
                "research",
            ],
            cost_per_token=0.000003,
            max_concurrent_tasks=2,
            description="Agent for reading and analyzing large contexts",
        ),
        AgentProfile(
            agent_id="thinker",
            display_name="Thinker",
            model_id="mimo/mimo-v2-pro",
            capabilities=[
                "architecture",
                "complex_reasoning",
                "planning",
                "design",
                "problem_solving",
            ],
            cost_per_token=0.000005,
            max_concurrent_tasks=1,
            description="High-level reasoning and architecture agent",
        ),
    ]


def create_complex_task() -> str:
    """Create a complex task description for demonstration."""
    return """
    Refactor the entire e-commerce application to improve performance and maintainability:

    1. Analyze current architecture and identify bottlenecks
    2. Design improved microservices architecture
    3. Refactor authentication service to use OAuth2
    4. Optimize database queries and add indexing
    5. Implement caching layer for product catalog
    6. Add comprehensive logging and monitoring
    7. Write unit tests for critical paths
    8. Update documentation for new architecture
    9. Create deployment scripts for new services
    10. Perform security audit of all changes

    The application currently has:
    - 50+ Python files
    - 3 main services (auth, products, orders)
    - PostgreSQL database
    - Redis cache (underutilized)
    - Basic monitoring with Prometheus
    """


async def demonstrate_task_decomposition():
    """Demonstrate decomposing a complex task into subtasks."""
    print("\n1. Task Decomposition")
    print("=" * 60)

    # Create decomposition engine
    decomposer = TaskDecompositionEngine()

    # Get complex task
    complex_task = create_complex_task()
    print(f"Complex task: {complex_task[:100]}...")

    # Decompose into subtasks
    print("\nDecomposing task...")
    task_graph = decomposer.decompose(complex_task)

    print(f"✅ Decomposed into {task_graph.size} subtasks")
    print(f"   Dependencies: {task_graph.dependency_count}")
    print(f"   Estimated complexity: {task_graph.estimated_complexity:.1f}/10")

    # Show some subtasks
    print("\nSample subtasks:")
    for i, (_task_id, task) in enumerate(list(task_graph.tasks.items())[:3], 1):
        print(f"   {i}. {task.description[:60]}...")
        print(f"      Type: {task.task_type.value}")
        print(f"      Dependencies: {len(task.dependencies)}")

    return task_graph


async def demonstrate_coordination(task_graph: TaskGraph):
    """Demonstrate coordinating agents for parallel execution."""
    print("\n\n2. Multi-Agent Coordination")
    print("=" * 60)

    # Create agent profiles
    agents = create_agent_profiles()
    print(f"Available agents: {', '.join(a.agent_id for a in agents)}")

    # Create coordination engine with observer
    observer = DemoObserver()
    coordinator = CoordinationEngine(observers=[observer])

    # Coordinate tasks to agents
    print("\nCoordinating tasks to agents...")
    result = await coordinator.coordinate(task_graph, plan_id="demo-parallel-001")

    # Show coordination results
    print("\n✅ Coordination complete!")
    print(f"   Agents used: {result.total_agents_used}")
    print(f"   Estimated cost: ${result.estimated_total_cost:.4f}")
    print(f"   Estimated time: {result.estimated_total_time:.1f}s")

    # Show agent utilization
    print("\nAgent utilization:")
    for agent_id, count in result.agent_utilization.items():
        print(f"   {agent_id}: {count} tasks")

    return result


async def demonstrate_parallel_execution_plan(result):
    """Demonstrate the parallel execution plan."""
    print("\n\n3. Parallel Execution Plan")
    print("=" * 60)

    plan = result.plan

    # Show execution waves (parallel steps)
    waves = plan.get_execution_order()
    print(f"Execution plan has {len(waves)} parallel waves:")

    total_parallel_tasks = 0
    for i, wave in enumerate(waves, 1):
        parallel_in_wave = len(wave)
        total_parallel_tasks += parallel_in_wave

        print(f"\n   Wave {i}: {parallel_in_wave} parallel tasks")
        for step_id in wave:
            step = plan.get_step(step_id)
            print(f"      • {step.step_id}: {len(step.task_ids)} tasks")

    sequential_tasks = plan.total_steps - total_parallel_tasks
    parallelization_rate = (total_parallel_tasks / plan.total_steps) * 100

    print("\n📊 Parallelization analysis:")
    print(f"   Total tasks: {plan.total_steps}")
    print(f"   Parallel tasks: {total_parallel_tasks}")
    print(f"   Sequential tasks: {sequential_tasks}")
    print(f"   Parallelization rate: {parallelization_rate:.1f}%")

    # Show critical path
    print("\n⏱️  Critical path (longest sequential chain):")
    critical_path = plan.get_critical_path()
    print(f"   Length: {len(critical_path)} steps")
    print(f"   Steps: {' → '.join(critical_path)}")


async def demonstrate_dynamic_escalation():
    """Demonstrate dynamic task escalation when agents fail."""
    print("\n\n4. Dynamic Task Escalation")
    print("=" * 60)

    # Create coordination engine
    coordinator = CoordinationEngine()

    # Simulate a task that might need escalation
    task = Subtask(
        description="Design distributed transaction system for financial processing",
        task_type=TaskType.ANALYSIS,
        subtask_type=SubtaskType.IMPLEMENTATION,
        complexity=ComplexityEstimate(
            code_complexity=9,
            integration_complexity=9,
            testing_complexity=8,
            unknown_factor=8,
            reasoning="Highly complex distributed systems design",
        ),
    )

    # First, try with intern (will likely fail or need escalation)
    print("Simulating task assignment to 'intern' agent...")
    print(f"Task: {task.description[:60]}...")

    # Simulate failure and escalation
    escalation = coordinator.handle_failure(
        task_id=task.task_id,
        current_agent_id="intern",
        error="Task too complex: requires distributed systems expertise",
        available_agents=create_agent_profiles(),
    )

    if escalation:
        print("\n✅ Task escalated successfully!")
        print("   From: intern")
        print(f"   To: {escalation.agent_profile.display_name}")
        print(f"   Reason: {escalation.reasoning}")
        print(f"   Model: {escalation.agent_profile.model_id}")
    else:
        print("\n❌ No suitable agent found for escalation")


async def demonstrate_resource_pool():
    """Demonstrate resource pool for managing concurrent agents."""
    print("\n\n5. Resource Pool Management")
    print("=" * 60)

    from omni.coordination.resource_pool import ResourcePool

    # Create resource pool with agents
    agents = create_agent_profiles()
    pool = ResourcePool(agents)

    # Simulate concurrent task requests
    task_types = [
        ("simple_formatting", "intern"),
        ("code_generation", "coder"),
        ("code_review", "reader"),
        ("architecture", "thinker"),
        ("another_code_gen", "coder"),
        ("more_formatting", "intern"),
    ]

    print("Simulating concurrent task assignments:")
    print("-" * 40)

    assignments = []
    for task_name, preferred_agent in task_types:
        # Try to get agent from pool
        agent = pool.acquire_agent(
            preferred_agent_id=preferred_agent,
            required_capabilities=[],  # No specific requirements for demo
        )

        if agent:
            assignments.append((task_name, agent.agent_id))
            print(f"   {task_name} → {agent.agent_id} (acquired)")
        else:
            # Try any available agent
            fallback_agent = pool.acquire_agent()
            if fallback_agent:
                assignments.append((task_name, fallback_agent.agent_id))
                print(f"   {task_name} → {fallback_agent.agent_id} (fallback)")
            else:
                print(f"   {task_name} → ❌ no agents available")

    # Show pool status
    print("\n📊 Resource pool status:")
    print(f"   Total agents: {pool.total_agents}")
    print(f"   Available agents: {pool.available_agents}")
    print(f"   Busy agents: {pool.busy_agents}")

    # Release agents back to pool
    for task_name, agent_id in assignments:
        pool.release_agent(agent_id)
        print(f"   Released {agent_id} from {task_name}")

    print(f"\n✅ All agents released. Available: {pool.available_agents}")


async def demonstrate_cost_tracking():
    """Demonstrate cost tracking across multiple agents."""
    print("\n\n6. Cost Tracking and Optimization")
    print("=" * 60)

    from omni.coordination.cost_tracker import CostTracker

    # Create cost tracker
    tracker = CostTracker(budget=0.10)  # $0.10 budget

    # Simulate task executions with different agents
    executions = [
        ("task_1", "intern", 1000, 500),  # task_id, agent_id, input_tokens, output_tokens
        ("task_2", "coder", 2000, 1500),
        ("task_3", "reader", 3000, 1000),
        ("task_4", "thinker", 4000, 2000),
        ("task_5", "coder", 1500, 1200),
    ]

    agents = {a.agent_id: a for a in create_agent_profiles()}

    print("Tracking task executions:")
    print("-" * 40)

    total_cost = 0
    for task_id, agent_id, input_tokens, output_tokens in executions:
        agent = agents[agent_id]
        cost = (input_tokens + output_tokens) * agent.cost_per_token
        total_cost += cost

        tracker.record_execution(
            task_id=task_id,
            agent_id=agent_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            success=True,
        )

        print(f"   {task_id}: {agent_id} (${cost:.6f})")

    # Get cost breakdown
    print("\n📊 Cost breakdown:")
    print(f"   Total cost: ${total_cost:.6f}")
    print(f"   Budget: ${tracker.budget:.6f}")
    print(f"   Remaining: ${tracker.budget - total_cost:.6f}")

    if total_cost > tracker.budget:
        print("   ⚠️  Budget exceeded!")
    else:
        print("   ✅ Within budget")

    # Show per-agent costs
    print("\nPer-agent costs:")
    for agent_id in agents:
        agent_cost = tracker.get_agent_cost(agent_id)
        if agent_cost > 0:
            print(f"   {agent_id}: ${agent_cost:.6f}")


async def main():
    """Run all multi-agent parallel execution demonstrations."""
    print("🚀 Multi-Agent Parallel Execution Demo")
    print("=" * 60)

    try:
        # 1. Task decomposition
        task_graph = await demonstrate_task_decomposition()

        # 2. Agent coordination
        result = await demonstrate_coordination(task_graph)

        # 3. Parallel execution plan
        await demonstrate_parallel_execution_plan(result)

        # 4. Dynamic escalation
        await demonstrate_dynamic_escalation()

        # 5. Resource pool management
        await demonstrate_resource_pool()

        # 6. Cost tracking
        await demonstrate_cost_tracking()

        print("\n" + "=" * 60)
        print("✅ All demonstrations completed successfully!")
        print("\nKey takeaways:")
        print("1. Complex tasks are automatically decomposed into subtasks")
        print("2. Agents are matched to tasks based on capabilities and cost")
        print("3. Independent tasks execute in parallel for speed")
        print("4. Failed tasks automatically escalate to more capable agents")
        print("5. Resource pools manage concurrent agent usage")
        print("6. Costs are tracked across all agents and tasks")

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
