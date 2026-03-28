"""
Tests for task executors.
"""

import asyncio
import json

import pytest

from src.omni.execution.config import ExecutionContext
from src.omni.execution.executor import LLMTaskExecutor, MockTaskExecutor
from src.omni.execution.models import TaskExecutionError, TaskFatalError
from src.omni.providers.base import ChatCompletion, TokenUsage
from src.omni.providers.mock_provider import MockProvider
from src.omni.router import ModelRouter, RouterConfig
from src.omni.task.models import ComplexityEstimate, Task, TaskStatus, TaskType


@pytest.mark.asyncio
async def test_mock_executor_success() -> None:
    """Test MockTaskExecutor with high success rate."""
    executor = MockTaskExecutor(
        success_rate=1.0,  # Always succeed
        avg_delay=0.01,    # Fast execution for tests
        delay_variance=0.0,
    )

    task = Task(description="Test task")
    context = ExecutionContext(
        dependency_results={},
        execution_id="test123",
        task_index=1,
        total_tasks=5,
    )

    result = await executor.execute(task, context)

    assert result.task_id == task.task_id
    assert result.status == TaskStatus.COMPLETED
    assert "result" in result.outputs
    assert "Mock result for task" in result.outputs["result"]
    assert result.tokens_used > 0
    assert result.cost > 0
    assert result.metadata["mock_executor"] is True


@pytest.mark.asyncio
async def test_mock_executor_failure() -> None:
    """Test MockTaskExecutor with low success rate."""
    executor = MockTaskExecutor(
        success_rate=0.0,  # Always fail
        avg_delay=0.01,
        delay_variance=0.0,
    )

    task = Task(description="Test task")
    context = ExecutionContext(
        dependency_results={},
        execution_id="test123",
        task_index=1,
        total_tasks=5,
    )

    # Run multiple times to test different failure modes
    fatal_error_count = 0
    execution_error_count = 0
    failed_result_count = 0

    for _ in range(30):  # Run enough times to likely hit all failure modes
        try:
            result = await executor.execute(task, context)
            # If we get here, it's a failed result (not an exception)
            assert result.status == TaskStatus.FAILED
            failed_result_count += 1
        except TaskFatalError:
            fatal_error_count += 1
        except TaskExecutionError:
            execution_error_count += 1

    # We should have seen all failure modes
    assert fatal_error_count + execution_error_count + failed_result_count == 30
    # Each should have occurred at least once
    assert fatal_error_count > 0
    assert execution_error_count > 0
    assert failed_result_count > 0


@pytest.mark.asyncio
async def test_mock_executor_delay() -> None:
    """Test MockTaskExecutor delay simulation."""
    executor = MockTaskExecutor(
        success_rate=1.0,
        avg_delay=0.1,
        delay_variance=0.05,
    )

    task = Task(description="Test task")
    context = ExecutionContext(
        dependency_results={},
        execution_id="test123",
        task_index=1,
        total_tasks=5,
    )

    # Measure execution time
    import time
    start_time = time.time()
    result = await executor.execute(task, context)
    end_time = time.time()

    elapsed = end_time - start_time

    # Should take roughly 0.1 seconds +/- variance
    assert 0.05 <= elapsed <= 0.15  # Allow some tolerance
    assert result.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_mock_executor_context() -> None:
    """Test MockTaskExecutor with dependency context."""
    executor = MockTaskExecutor(success_rate=1.0, avg_delay=0.01)

    # Create a task with mock dependency results
    from src.omni.task.models import TaskResult

    dependency_results = {
        "dep1": TaskResult(task_id="dep1", status=TaskStatus.COMPLETED),
        "dep2": TaskResult(task_id="dep2", status=TaskStatus.COMPLETED),
    }

    task = Task(description="Test task with dependencies")
    context = ExecutionContext(
        dependency_results=dependency_results,
        execution_id="test123",
        task_index=3,
        total_tasks=10,
    )

    result = await executor.execute(task, context)

    assert result.status == TaskStatus.COMPLETED
    assert result.outputs["context_size"] == 2
    assert result.outputs["execution_id"] == "test123"


def test_mock_executor_configuration() -> None:
    """Test MockTaskExecutor configuration."""
    executor = MockTaskExecutor(
        success_rate=0.7,
        avg_delay=2.0,
        delay_variance=1.0,
        token_cost_per_task=500,
        cost_per_token=0.00001,
    )

    # Test with success
    # Note: We can't easily test the exact configuration without running many times
    # But we can verify the executor was created with these values
    assert executor.success_rate == 0.7
    assert executor.avg_delay == 2.0
    assert executor.delay_variance == 1.0
    assert executor.token_cost_per_task == 500
    assert executor.cost_per_token == 0.00001


@pytest.mark.asyncio
async def test_mock_executor_cancellation() -> None:
    """Test that MockTaskExecutor respects cancellation."""
    executor = MockTaskExecutor(
        success_rate=1.0,
        avg_delay=1.0,  # Long delay to allow cancellation
        delay_variance=0.0,
    )

    task = Task(description="Test task")
    context = ExecutionContext(
        dependency_results={},
        execution_id="test123",
        task_index=1,
        total_tasks=5,
    )

    # Create a task and cancel it
    task_future = asyncio.create_task(executor.execute(task, context))

    # Cancel immediately
    task_future.cancel()

    # Should raise CancelledError
    with pytest.raises(asyncio.CancelledError):
        await task_future


# LLMTaskExecutor Tests
@pytest.fixture
def mock_router() -> ModelRouter:
    """Create a mock router with mock provider for testing."""
    # Create mock provider
    mock_provider = MockProvider(config={"response_delay": 0.01})

    # Create router config
    config = RouterConfig(
        providers={
            "mimo/mimo-v2-flash": mock_provider,
            "deepseek/deepseek-chat": mock_provider,
            "moonshot/kimi-k2.5": mock_provider,
            "mimo/mimo-v2-pro": mock_provider,
            "openai/gpt-5-mini": mock_provider,
            "openai/gpt-4.1-mini": mock_provider,
        }
    )

    return ModelRouter(config)


@pytest.mark.asyncio
async def test_llm_executor_basic(mock_router: ModelRouter) -> None:
    """Test LLMTaskExecutor basic functionality."""
    executor = LLMTaskExecutor(
        router=mock_router,
        timeout_per_task=5.0,
        default_temperature=0.7,
        max_tokens_per_task=1000,
    )

    task = Task(
        description="Write a function to add two numbers",
        task_type=TaskType.CODE_GENERATION,
        complexity=ComplexityEstimate(
            code_complexity=3,
            integration_complexity=2,
            testing_complexity=1,
            unknown_factor=1,
            estimated_tokens=500,
            reasoning="Simple code generation task",
        ),
    )

    context = ExecutionContext(
        dependency_results={},
        execution_id="test-llm-123",
        task_index=1,
        total_tasks=3,
    )

    result = await executor.execute(task, context)

    assert result.task_id == task.task_id
    assert result.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
    assert result.tokens_used > 0
    assert "model" in result.metadata
    assert "tier" in result.metadata
    assert result.metadata["tier"] == "intern"  # Based on complexity score


@pytest.mark.asyncio
async def test_llm_executor_with_dependencies(mock_router: ModelRouter) -> None:
    """Test LLMTaskExecutor with dependency results."""
    executor = LLMTaskExecutor(
        router=mock_router,
        timeout_per_task=5.0,
    )

    # Create dependency results
    from src.omni.task.models import TaskResult

    dependency_results = {
        "dep1": TaskResult(
            task_id="dep1",
            status=TaskStatus.COMPLETED,
            outputs={"result": "Dependency 1 completed successfully"},
        ),
        "dep2": TaskResult(
            task_id="dep2",
            status=TaskStatus.COMPLETED,
            outputs={"result": "Dependency 2 completed successfully"},
        ),
    }

    task = Task(
        description="Combine the results from dependencies",
        task_type=TaskType.CODE_GENERATION,
        complexity=ComplexityEstimate(
            code_complexity=5,
            integration_complexity=6,
            testing_complexity=3,
            unknown_factor=2,
            estimated_tokens=800,
            reasoning="Integration task with dependencies",
        ),
    )

    context = ExecutionContext(
        dependency_results=dependency_results,
        execution_id="test-llm-456",
        task_index=2,
        total_tasks=3,
    )

    result = await executor.execute(task, context)

    assert result.task_id == task.task_id
    assert result.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
    assert result.tokens_used > 0
    assert result.metadata["tier"] == "coder"  # Based on complexity score


@pytest.mark.asyncio
async def test_llm_executor_tier_routing(mock_router: ModelRouter) -> None:
    """Test LLMTaskExecutor tier-based model routing."""
    executor = LLMTaskExecutor(
        router=mock_router,
        timeout_per_task=5.0,
    )

    # Test different complexity tiers
    # Based on ComplexityEstimate.tier property:
    # - score <= 3.0: intern
    # - score <= 5.5: coder
    # - score <= 7.5: reader
    # - score > 7.5: thinker
    test_cases = [
        (ComplexityEstimate(code_complexity=1, integration_complexity=1, testing_complexity=1, unknown_factor=1), "intern"),  # score = 1.0
        (ComplexityEstimate(code_complexity=5, integration_complexity=4, testing_complexity=3, unknown_factor=3), "coder"),   # score ≈ 4.0
        (ComplexityEstimate(code_complexity=7, integration_complexity=6, testing_complexity=5, unknown_factor=5), "reader"),  # score ≈ 6.0
        (ComplexityEstimate(code_complexity=9, integration_complexity=8, testing_complexity=7, unknown_factor=8), "thinker"), # score ≈ 8.0
    ]

    for complexity, expected_tier in test_cases:
        task = Task(
            description=f"Test task for {expected_tier} tier",
            task_type=TaskType.ANALYSIS,
            complexity=complexity,
        )

        context = ExecutionContext(
            dependency_results={},
            execution_id=f"test-tier-{expected_tier}",
            task_index=1,
            total_tasks=1,
        )

        result = await executor.execute(task, context)
        assert result.metadata["tier"] == expected_tier


@pytest.mark.asyncio
async def test_llm_executor_json_response(mock_router: ModelRouter) -> None:
    """Test LLMTaskExecutor with JSON response parsing."""
    # Create a custom mock provider that returns JSON responses
    class JSONMockProvider(MockProvider):
        async def chat_completion(self, messages, model, **kwargs):
            # Simulate delay
            await asyncio.sleep(0.01)

            # Return a JSON response
            json_response = {
                "result": "Mock JSON response for testing",
                "explanation": "This is a test response in JSON format",
                "next_steps": ["Test step 1", "Test step 2"]
            }

            return ChatCompletion(
                content=json.dumps(json_response, indent=2),
                model=model,
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                finish_reason="stop",
            )

    # Create router with JSON mock provider
    json_provider = JSONMockProvider(config={"response_delay": 0.01})
    config = RouterConfig(
        providers={
            "mimo/mimo-v2-flash": json_provider,
            "deepseek/deepseek-chat": json_provider,
            "moonshot/kimi-k2.5": json_provider,
            "mimo/mimo-v2-pro": json_provider,
            "openai/gpt-5-mini": json_provider,
            "openai/gpt-4.1-mini": json_provider,
        }
    )
    router = ModelRouter(config)

    executor = LLMTaskExecutor(router=router, timeout_per_task=5.0)

    task = Task(
        description="Test JSON response parsing",
        task_type=TaskType.CODE_GENERATION,
        complexity=ComplexityEstimate(
            code_complexity=4,
            integration_complexity=3,
            testing_complexity=2,
            unknown_factor=1,
        ),
    )

    context = ExecutionContext(
        dependency_results={},
        execution_id="test-json-123",
        task_index=1,
        total_tasks=1,
    )

    result = await executor.execute(task, context)

    assert result.status == TaskStatus.COMPLETED
    assert "result" in result.outputs
    assert result.outputs["result"] == "Mock JSON response for testing"
    assert "explanation" in result.outputs
    assert "next_steps" in result.outputs


@pytest.mark.asyncio
async def test_llm_executor_timeout(mock_router: ModelRouter) -> None:
    """Test LLMTaskExecutor timeout handling."""
    # Create a slow mock provider
    class SlowMockProvider(MockProvider):
        async def chat_completion(self, messages, model, **kwargs):
            # Sleep longer than timeout
            await asyncio.sleep(2.0)
            return await super().chat_completion(messages, model, **kwargs)

    slow_provider = SlowMockProvider(config={"response_delay": 0})
    config = RouterConfig(
        providers={
            "deepseek/deepseek-chat": slow_provider,
        }
    )
    router = ModelRouter(config)

    # Create executor with very short timeout
    executor = LLMTaskExecutor(router=router, timeout_per_task=0.5)

    task = Task(
        description="Test timeout",
        task_type=TaskType.CODE_GENERATION,
    )

    context = ExecutionContext(
        dependency_results={},
        execution_id="test-timeout-123",
        task_index=1,
        total_tasks=1,
    )

    # Should raise TaskExecutionError due to timeout
    with pytest.raises(TaskExecutionError):
        await executor.execute(task, context)


def test_llm_executor_configuration() -> None:
    """Test LLMTaskExecutor configuration."""
    # Create a minimal router for testing config
    mock_provider = MockProvider()
    config = RouterConfig(providers={"test-model": mock_provider})
    router = ModelRouter(config)

    executor = LLMTaskExecutor(
        router=router,
        timeout_per_task=10.0,
        default_temperature=0.5,
        max_tokens_per_task=2000,
    )

    assert executor.router == router
    assert executor.timeout_per_task == 10.0
    assert executor.default_temperature == 0.5
    assert executor.max_tokens_per_task == 2000
    assert "intern" in executor.tier_to_model
    assert "coder" in executor.tier_to_model
    assert "reader" in executor.tier_to_model
    assert "thinker" in executor.tier_to_model
