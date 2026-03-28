#!/usr/bin/env python3
"""
Example demonstrating the multi-agent coordination engine.

This example shows how to:
1. Create a task graph with different types of tasks
2. Use the coordination engine to match tasks to agents
3. Create a workflow plan with parallel execution waves
4. Handle task failures with escalation
"""

import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omni.coordination import (
    AgentCapability,
    CoordinationEngine,
    CoordinationObserver,
    WorkflowPlan,
)
from omni.coordination.matcher import AgentAssignment
from omni.decomposition.models import Subtask, SubtaskType
from omni.task.models import ComplexityEstimate, TaskGraph, TaskType


class ExampleObserver(CoordinationObserver):
    """Example observer that prints coordination events."""
    
    def on_agent_assigned(self, task_id: str, assignment: AgentAssignment) -> None:
        print(f"📋 Task '{task_id}' assigned to {assignment.agent_id}")
        print(f"   Confidence: {assignment.confidence.value}, Score: {assignment.score:.2f}")
        print(f"   Reasoning: {assignment.reasoning}")
    
    def on_workflow_planned(self, plan: WorkflowPlan) -> None:
        print(f"\n📊 Workflow Plan '{plan.plan_id}' created")
        print(f"   Total steps: {plan.total_steps}")
        print(f"   Parallel steps: {plan.parallel_steps}")
        print(f"   Review steps: {plan.review_steps}")
        
        # Show execution waves
        waves = plan.get_execution_order()
        print(f"   Execution waves: {len(waves)}")
        for i, wave in enumerate(waves, 1):
            print(f"     Wave {i}: {len(wave)} steps")
    
    def on_step_started(self, step_id: str, task_ids: list[str]) -> None:
        print(f"▶️  Step '{step_id}' started with tasks: {task_ids}")
    
    def on_step_completed(self, step_id: str, results: dict[str, str]) -> None:
        print(f"✅ Step '{step_id}' completed with {len(results)} results")
    
    def on_escalation(self, task_id: str, from_agent: str, to_agent: str, reason: str) -> None:
        print(f"⚠️  Task '{task_id}' escalated from {from_agent} to {to_agent}: {reason}")


def create_example_task_graph() -> TaskGraph:
    """Create an example task graph with various task types."""
    graph = TaskGraph(name="Example Project")
    
    # 1. Simple formatting task (Intern)
    format_task = Subtask(
        description="Format Python code according to PEP 8",
        task_type=TaskType.CONFIGURATION,
        subtask_type=SubtaskType.IMPLEMENTATION,
        required_capabilities=["formatting"],
        complexity=ComplexityEstimate(
            code_complexity=1,
            integration_complexity=1,
            testing_complexity=1,
            unknown_factor=1,
            reasoning="Simple formatting task",
        ),
    )
    
    # 2. Code generation task (Coder)
    code_task = Subtask(
        description="Implement user authentication API endpoint",
        task_type=TaskType.CODE_GENERATION,
        subtask_type=SubtaskType.IMPLEMENTATION,
        required_capabilities=["code_generation", "testing"],
        complexity=ComplexityEstimate(
            code_complexity=4,
            integration_complexity=3,
            testing_complexity=3,
            unknown_factor=2,
            reasoning="Standard API implementation",
        ),
    )
    
    # 3. Code review task (Reader)
    review_task = Subtask(
        description="Review authentication implementation",
        task_type=TaskType.CODE_REVIEW,
        subtask_type=SubtaskType.VALIDATION,
        required_capabilities=["code_review", "long_context"],
        complexity=ComplexityEstimate(
            code_complexity=3,
            integration_complexity=4,
            testing_complexity=3,
            unknown_factor=2,
            reasoning="Comprehensive code review",
        ),
        dependencies=[code_task.task_id],
    )
    
    # 4. Architecture design task (Thinker)
    arch_task = Subtask(
        description="Design microservices architecture for scaling",
        task_type=TaskType.ANALYSIS,
        subtask_type=SubtaskType.IMPLEMENTATION,
        required_capabilities=["architecture", "reasoning"],
        complexity=ComplexityEstimate(
            code_complexity=8,
            integration_complexity=9,
            testing_complexity=7,
            unknown_factor=8,
            reasoning="Complex architectural design",
        ),
    )
    
    # Add tasks to graph
    tasks = [format_task, code_task, review_task, arch_task]
    for task in tasks:
        graph.add_task(task)
    
    return graph, tasks


def main() -> None:
    """Run the coordination example."""
    print("🚀 Multi-Agent Coordination Engine Example")
    print("=" * 50)
    
    # Create task graph
    print("\n📝 Creating example task graph...")
    task_graph, tasks = create_example_task_graph()
    format_task, code_task, review_task, arch_task = tasks
    print(f"   Graph '{task_graph.name}' created with {task_graph.size} tasks")
    
    # Create coordination engine with observer
    observer = ExampleObserver()
    engine = CoordinationEngine(observers=[observer])
    
    # Coordinate the task graph
    print("\n🤝 Coordinating tasks to agents...")
    result = engine.coordinate(task_graph, plan_id="example-plan-001")
    
    # Show results
    print("\n📈 Coordination Results:")
    print(f"   Total agents used: {result.total_agents_used}")
    print(f"   Estimated cost: {result.estimated_total_cost:.2f}")
    
    # Show agent assignments
    print("\n👥 Agent Assignments:")
    for task_id, assignment in result.assignments.items():
        task = task_graph.tasks[task_id]
        print(f"   • {task.description[:50]}...")
        print(f"     → {assignment.agent_profile.display_name}")
        print(f"     Model: {assignment.agent_profile.model_id}")
    
    # Show workflow plan
    print("\n📋 Workflow Execution Plan:")
    for i, step in enumerate(result.plan.steps, 1):
        print(f"   {i}. Step {step.step_id} ({step.step_type.value})")
        print(f"      Tasks: {', '.join(step.task_ids)}")
        if step.depends_on:
            print(f"      Depends on: {', '.join(step.depends_on)}")
    
    # Demonstrate escalation
    print("\n⚠️  Simulating task failure and escalation...")
    escalation = engine.handle_failure(
        task_id=code_task.task_id,
        current_agent_id="intern",  # Pretend it was assigned to intern
        error="Failed to implement authentication: missing dependencies",
    )
    
    if escalation:
        print(f"   Task escalated to: {escalation.agent_profile.display_name}")
        print(f"   Reasoning: {escalation.reasoning}")
    
    print("\n✅ Example completed successfully!")


if __name__ == "__main__":
    main()