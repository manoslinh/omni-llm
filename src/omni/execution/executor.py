"""
Task executor protocol and implementations.
"""

import asyncio
import json
import random
from typing import Any, Protocol

from ..providers.base import Message, MessageRole
from ..router import ModelRouter
from ..task.models import Task, TaskResult, TaskStatus
from .config import ExecutionContext
from .models import TaskExecutionError, TaskFatalError


class TaskExecutor(Protocol):
    """Pluggable task execution backend."""

    async def execute(
        self,
        task: Task,
        context: ExecutionContext,
    ) -> TaskResult:
        """Execute a task and return its result.

        Args:
            task: The task to execute (includes description, type, complexity).
            context: Accumulated results from dependency tasks.

        Returns:
            TaskResult with status, outputs, tokens_used, cost.

        Raises:
            TaskExecutionError: On recoverable failures (triggers retry).
            TaskFatalError: On non-recoverable failures (no retry).
        """
        ...


class MockTaskExecutor:
    """Mock executor for testing without real LLM calls."""

    def __init__(
        self,
        success_rate: float = 0.8,
        avg_delay: float = 0.5,
        delay_variance: float = 0.3,
        token_cost_per_task: int = 100,
        cost_per_token: float = 0.00002,
    ) -> None:
        """
        Args:
            success_rate: Probability of task success (0.0 to 1.0)
            avg_delay: Average execution delay in seconds
            delay_variance: Variance in delay (uniform distribution)
            token_cost_per_task: Mock tokens used per task
            cost_per_token: Mock cost per token
        """
        self.success_rate = success_rate
        self.avg_delay = avg_delay
        self.delay_variance = delay_variance
        self.token_cost_per_task = token_cost_per_task
        self.cost_per_token = cost_per_token

    async def execute(
        self,
        task: Task,
        context: ExecutionContext,
    ) -> TaskResult:
        """Execute a task with configurable mock behavior."""

        # Simulate execution delay
        delay = self.avg_delay + random.uniform(
            -self.delay_variance, self.delay_variance
        )
        delay = max(0.1, delay)  # Minimum delay
        await asyncio.sleep(delay)

        # Determine success/failure
        if random.random() < self.success_rate:
            # Success case
            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.COMPLETED,
                outputs={
                    "result": f"Mock result for task {task.task_id}",
                    "context_size": len(context.dependency_results),
                    "execution_id": context.execution_id,
                },
                tokens_used=self.token_cost_per_task,
                cost=self.token_cost_per_task * self.cost_per_token,
                metadata={
                    "mock_executor": True,
                    "delay_seconds": delay,
                    "success_rate": self.success_rate,
                },
            )
        else:
            # Failure case - simulate different error types
            error_type = random.choice(["recoverable", "fatal", "transient"])

            if error_type == "fatal":
                raise TaskFatalError(f"Mock fatal error for task {task.task_id}")
            elif error_type == "transient":
                # Transient error that should trigger retry
                raise TaskExecutionError(f"Mock transient error for task {task.task_id}")
            else:
                # Recoverable error but task completes with errors
                return TaskResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    errors=[f"Mock recoverable error for task {task.task_id}"],
                    tokens_used=self.token_cost_per_task // 2,  # Partial tokens used
                    cost=(self.token_cost_per_task // 2) * self.cost_per_token,
                    metadata={
                        "mock_executor": True,
                        "delay_seconds": delay,
                        "error_type": "recoverable",
                    },
                )


class LLMTaskExecutor:
    """Task executor that uses real LLM providers via the router layer."""

    def __init__(
        self,
        router: ModelRouter,
        timeout_per_task: float = 300.0,
        default_temperature: float = 0.7,
        max_tokens_per_task: int = 4000,
    ) -> None:
        """
        Initialize the LLM task executor.

        Args:
            router: ModelRouter instance for LLM calls
            timeout_per_task: Maximum seconds per task execution
            default_temperature: Default temperature for LLM calls
            max_tokens_per_task: Maximum tokens to generate per task
        """
        self.router = router
        self.timeout_per_task = timeout_per_task
        self.default_temperature = default_temperature
        self.max_tokens_per_task = max_tokens_per_task

        # Tier to model mapping based on AGENTS.md routing law
        self.tier_to_model = {
            "intern": "mimo/mimo-v2-flash",
            "coder": "deepseek/deepseek-chat",
            "reader": "moonshot/kimi-k2.5",
            "thinker": "mimo/mimo-v2-pro",
        }

        # Fallback models in order
        self.fallback_models = [
            "openai/gpt-5-mini",
            "openai/gpt-4.1-mini",
        ]

    def _build_prompt(self, task: Task, context: ExecutionContext) -> str:
        """Build a prompt from task description and dependency results."""
        prompt_parts = []

        # Add task description
        prompt_parts.append(f"# TASK: {task.description}")

        # Add task type if not CUSTOM
        if task.task_type != "custom":
            prompt_parts.append(f"Task Type: {task.task_type}")

        # Add dependency results if available
        if context.dependency_results:
            prompt_parts.append("\n## DEPENDENCY RESULTS:")
            for dep_id, result in context.dependency_results.items():
                status_emoji = "✅" if result.success else "❌"
                prompt_parts.append(f"\n### Dependency: {dep_id} {status_emoji}")
                if result.outputs:
                    # Format outputs as JSON for readability
                    outputs_str = json.dumps(result.outputs, indent=2)
                    prompt_parts.append(f"Outputs:\n```json\n{outputs_str}\n```")
                if result.errors:
                    prompt_parts.append(f"Errors: {', '.join(result.errors)}")

        # Add execution context
        prompt_parts.append("\n## EXECUTION CONTEXT:")
        prompt_parts.append(f"- Execution ID: {context.execution_id}")
        prompt_parts.append(f"- Task {context.task_index} of {context.total_tasks}")
        prompt_parts.append(f"- Dependencies: {len(context.dependency_results)}")

        # Add complexity tier if available
        if task.complexity:
            prompt_parts.append("\n## COMPLEXITY ANALYSIS:")
            prompt_parts.append(f"- Tier: {task.complexity.tier}")
            prompt_parts.append(f"- Overall Score: {task.complexity.overall_score:.1f}/10")
            if task.complexity.reasoning:
                prompt_parts.append(f"- Reasoning: {task.complexity.reasoning}")

        # Add instructions
        prompt_parts.append("\n## INSTRUCTIONS:")
        prompt_parts.append("Complete this task. Provide your response as a JSON object with the following structure:")
        prompt_parts.append('```json\n{\n  "result": "The main result of the task",\n  "explanation": "Brief explanation of what you did",\n  "next_steps": ["Optional next steps or recommendations"]\n}\n```')
        prompt_parts.append("If the task fails, include an 'error' field instead of 'result'.")

        return "\n".join(prompt_parts)

    def _select_model_for_tier(self, tier: str) -> str:
        """Select model based on complexity tier."""
        # Get primary model for tier
        primary_model = self.tier_to_model.get(tier.lower())
        if primary_model:
            return primary_model

        # Default to coder model if tier not found
        return self.tier_to_model["coder"]



    async def execute(
        self,
        task: Task,
        context: ExecutionContext,
    ) -> TaskResult:
        """Execute a task using real LLM providers."""
        try:
            # Build prompt from task and context
            prompt = self._build_prompt(task, context)

            # Determine model based on complexity tier
            tier = task.effective_complexity.tier
            primary_model = self._select_model_for_tier(tier)

            # Create messages for LLM
            messages = [
                Message(
                    role=MessageRole.SYSTEM,
                    content="You are an AI assistant executing tasks in a parallel execution engine. "
                    "You receive tasks with dependency results and must complete them. "
                    "Always respond with valid JSON as requested in the prompt."
                ),
                Message(role=MessageRole.USER, content=prompt),
            ]

            # Execute with timeout
            async def _execute_llm() -> tuple[Any, Any, str, Any]:
                # Try primary model first
                models_to_try = [primary_model] + self.fallback_models

                for model in models_to_try:
                    try:
                        # Get provider for the model
                        provider = self.router.get_provider(model)

                        # Call provider directly
                        result = await provider.chat_completion(  # type: ignore[attr-defined]
                            messages=messages,
                            model=model,
                            temperature=self.default_temperature,
                            max_tokens=self.max_tokens_per_task,
                        )
                        return result, provider, model, tier
                    except Exception as e:
                        # Log and try next model
                        print(f"Model {model} failed: {e}")
                        if model == models_to_try[-1]:
                            # Last model failed
                            raise

                # This should never be reached, but mypy needs it
                raise RuntimeError("No models available for execution")

            # Execute with timeout
            llm_result, provider, model_used, tier_used = await asyncio.wait_for(
                _execute_llm(),
                timeout=self.timeout_per_task,
            )

            # Parse the response
            try:
                # Try to extract JSON from response
                response_text = llm_result.content.strip()

                # Handle code block markers
                if "```json" in response_text:
                    # Extract JSON from code block
                    start_idx = response_text.find("```json") + 7
                    end_idx = response_text.find("```", start_idx)
                    if end_idx == -1:
                        end_idx = response_text.rfind("```")
                    json_str = response_text[start_idx:end_idx].strip()
                elif "```" in response_text:
                    # Extract from generic code block
                    start_idx = response_text.find("```") + 3
                    end_idx = response_text.find("```", start_idx)
                    if end_idx == -1:
                        end_idx = response_text.rfind("```")
                    json_str = response_text[start_idx:end_idx].strip()
                else:
                    # Assume it's plain JSON
                    json_str = response_text

                # Parse JSON
                parsed_result = json.loads(json_str)

                # Calculate cost based on token usage
                # Get cost rate for the model
                cost_rate = provider.cost_per_token.get(model_used, None)
                cost = 0.0
                if cost_rate:
                    # Calculate cost: (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
                    cost = (
                        llm_result.usage.prompt_tokens * cost_rate.input_per_million +
                        llm_result.usage.completion_tokens * cost_rate.output_per_million
                    ) / 1_000_000

                # Check for error field
                if "error" in parsed_result:
                    return TaskResult(
                        task_id=task.task_id,
                        status=TaskStatus.FAILED,
                        errors=[parsed_result["error"]],
                        outputs=parsed_result,
                        tokens_used=llm_result.usage.total_tokens,
                        cost=cost,
                        metadata={
                            "model": llm_result.model,
                            "tier": tier_used,
                            "provider": provider.name,
                        },
                    )
                else:
                    return TaskResult(
                        task_id=task.task_id,
                        status=TaskStatus.COMPLETED,
                        outputs=parsed_result,
                        tokens_used=llm_result.usage.total_tokens,
                        cost=cost,
                        metadata={
                            "model": llm_result.model,
                            "tier": tier_used,
                            "provider": provider.name,
                        },
                    )

            except (json.JSONDecodeError, KeyError) as e:
                # If JSON parsing fails, treat as error but include raw response
                # Calculate cost for error case
                error_cost = 0.0
                cost_rate = provider.cost_per_token.get(model_used, None)
                if cost_rate:
                    error_cost = (
                        llm_result.usage.prompt_tokens * cost_rate.input_per_million +
                        llm_result.usage.completion_tokens * cost_rate.output_per_million
                    ) / 1_000_000

                return TaskResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    errors=[f"Failed to parse LLM response: {str(e)}"],
                    outputs={"raw_response": llm_result.content},
                    tokens_used=llm_result.usage.total_tokens,
                    cost=error_cost,
                    metadata={
                        "model": llm_result.model,
                        "tier": tier_used,
                        "provider": provider.name,
                        "parse_error": str(e),
                    },
                )

        except TimeoutError:
            raise TaskExecutionError(f"Task {task.task_id} timed out after {self.timeout_per_task} seconds") from None
        except Exception as e:
            # Check if it's a fatal error
            if isinstance(e, (TaskExecutionError, TaskFatalError)):
                raise
            # For other errors, raise as TaskExecutionError to trigger retry
            raise TaskExecutionError(f"Task execution failed: {str(e)}") from e
