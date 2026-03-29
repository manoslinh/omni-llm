#!/usr/bin/env python3
"""
Demo script showing how to use LLMTaskExecutor.

This example demonstrates:
1. Creating a ModelRouter with mock providers
2. Creating an LLMTaskExecutor
3. Executing tasks with different complexity tiers
4. Handling dependency results
"""

import asyncio
import json
from typing import Any

from omni.execution.config import ExecutionContext
from omni.execution.executor import LLMTaskExecutor
from omni.providers.base import ChatCompletion, Message, MessageRole, TokenUsage
from omni.providers.mock_provider import MockProvider
from omni.router import ModelRouter, RouterConfig
from omni.task.models import ComplexityEstimate, Task, TaskStatus, TaskType


class DemoMockProvider(MockProvider):
    """Mock provider that returns JSON responses for demo purposes."""

    async def chat_completion(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any
    ) -> ChatCompletion:
        # Simulate delay
        await asyncio.sleep(0.1)

        # Extract the task description from messages
        task_description = "Unknown task"
        for msg in messages:
            if msg.role == MessageRole.USER and "TASK:" in msg.content:
                # Extract task description
                lines = msg.content.split("\n")
                for line in lines:
                    if line.startswith("# TASK:"):
                        task_description = line[7:].strip()
                        break
                break

        # Create a mock JSON response based on the task
        json_response = {
            "result": f"Successfully completed: {task_description}",
            "explanation": f"This task was executed by {model} based on complexity tier",
            "next_steps": ["Review the result", "Proceed to next task"],
            "model_used": model,
            "task_complexity": "low" if "intern" in model else "medium" if "coder" in model else "high"
        }

        return ChatCompletion(
            content=json.dumps(json_response, indent=2),
            model=model,
            usage=TokenUsage(prompt_tokens=150, completion_tokens=100, total_tokens=250),
            finish_reason="stop",
        )


async def main() -> None:
    """Run the LLMTaskExecutor demo."""
    print("=== LLMTaskExecutor Demo ===\n")

    # Create mock provider
    mock_provider = DemoMockProvider(config={"response_delay": 0.1})

    # Create router with providers for all tiers
    config = RouterConfig(
        providers={
            "mimo/mimo-v2-flash": mock_provider,      # Intern tier
            "deepseek/deepseek-chat": mock_provider,  # Coder tier
            "moonshot/kimi-k2.5": mock_provider,      # Reader tier
            "mimo/mimo-v2-pro": mock_provider,        # Thinker tier
            "openai/gpt-5-mini": mock_provider,       # Fallback 1
            "openai/gpt-4.1-mini": mock_provider,     # Fallback 2
        }
    )
    router = ModelRouter(config)

    # Create LLMTaskExecutor
    executor = LLMTaskExecutor(
        router=router,
        timeout_per_task=30.0,
        default_temperature=0.7,
        max_tokens_per_task=2000,
    )

    print("1. Testing basic task execution...")

    # Create a simple task (intern tier)
    simple_task = Task(
        description="Write a function to calculate factorial",
        task_type=TaskType.CODE_GENERATION,
        complexity=ComplexityEstimate(
            code_complexity=2,
            integration_complexity=1,
            testing_complexity=1,
            unknown_factor=1,
            estimated_tokens=300,
            reasoning="Simple code generation task",
        ),
    )

    simple_context = ExecutionContext(
        dependency_results={},
        execution_id="demo-1",
        task_index=1,
        total_tasks=3,
    )

    result = await executor.execute(simple_task, simple_context)
    print(f"   Task: {simple_task.description}")
    print(f"   Status: {result.status}")
    print(f"   Tier: {result.metadata['tier']}")
    print(f"   Model: {result.metadata['model']}")
    print(f"   Result: {result.outputs.get('result', 'N/A')[:80]}...")
    print(f"   Tokens used: {result.tokens_used}")
    print(f"   Cost: ${result.cost:.6f}\n")

    print("2. Testing task with dependencies...")

    # Create dependency results
    from omni.task.models import TaskResult

    dependency_results = {
        "data_fetch": TaskResult(
            task_id="data_fetch",
            status=TaskStatus.COMPLETED,
            outputs={"data": [1, 2, 3, 4, 5], "source": "API"},
        ),
        "validation": TaskResult(
            task_id="validation",
            status=TaskStatus.COMPLETED,
            outputs={"is_valid": True, "checks_passed": 5},
        ),
    }

    # Create a more complex task (coder tier)
    complex_task = Task(
        description="Process and analyze the data from dependencies",
        task_type=TaskType.ANALYSIS,
        complexity=ComplexityEstimate(
            code_complexity=5,
            integration_complexity=6,
            testing_complexity=3,
            unknown_factor=3,
            estimated_tokens=800,
            reasoning="Data analysis with multiple dependencies",
        ),
    )

    complex_context = ExecutionContext(
        dependency_results=dependency_results,
        execution_id="demo-2",
        task_index=2,
        total_tasks=3,
    )

    result = await executor.execute(complex_task, complex_context)
    print(f"   Task: {complex_task.description}")
    print(f"   Status: {result.status}")
    print(f"   Tier: {result.metadata['tier']}")
    print(f"   Model: {result.metadata['model']}")
    print(f"   Dependencies processed: {len(dependency_results)}")
    print(f"   Result: {result.outputs.get('result', 'N/A')[:80]}...\n")

    print("3. Testing different complexity tiers...")

    # Test tasks with different complexity levels
    test_tasks = [
        ("Write documentation for a simple function", ComplexityEstimate(1, 1, 1, 1)),
        ("Refactor a medium-sized module", ComplexityEstimate(4, 3, 2, 2)),
        ("Analyze a complex system architecture", ComplexityEstimate(7, 6, 4, 5)),
        ("Design a novel algorithm for optimization", ComplexityEstimate(9, 8, 6, 7)),
    ]

    for i, (description, complexity) in enumerate(test_tasks, 1):
        task = Task(
            description=description,
            task_type=TaskType.ANALYSIS,
            complexity=complexity,
        )

        context = ExecutionContext(
            dependency_results={},
            execution_id=f"demo-tier-{i}",
            task_index=i,
            total_tasks=len(test_tasks),
        )

        result = await executor.execute(task, context)
        print(f"   {i}. {description}")
        print(f"      Complexity score: {complexity.overall_score:.1f}")
        print(f"      Tier: {result.metadata['tier']}")
        print(f"      Model: {result.metadata['model']}")

    print("\n=== Demo Complete ===")
    print("\nSummary:")
    print("- LLMTaskExecutor successfully routes tasks to appropriate models based on complexity tier")
    print("- Handles dependency results in context assembly")
    print("- Implements timeout and fallback mechanisms")
    print("- Tracks token usage and costs")
    print("- Returns structured JSON responses")


if __name__ == "__main__":
    asyncio.run(main())
