# LLMTaskExecutor

## Overview

`LLMTaskExecutor` is a task executor implementation that connects the Parallel Execution Engine to real LLM providers via the existing provider/router layer. It replaces the `MockTaskExecutor` with real LLM calls while maintaining backward compatibility.

## Features

1. **Tier-based Model Routing**: Automatically routes tasks to appropriate models based on `ComplexityEstimate.tier`:
   - `intern` → `provider/fast-model`
   - `coder` → `provider/standard-model`
   - `reader` → `provider/advanced-model`
   - `thinker` → `provider/premium-model`

2. **Context Assembly**: Builds comprehensive prompts from:
   - Task description
   - Dependency results (outputs and errors)
   - Execution context (execution ID, task position)
   - Complexity analysis

3. **Timeout Handling**: Uses `asyncio.wait_for` for per-task timeouts.

4. **Fallback Mechanism**: Automatically falls back to alternative models (`gpt-4o-mini` → `gpt-4o-mini`) on failures.

5. **Cost Tracking**: Calculates token usage costs based on provider rates.

6. **Structured JSON Responses**: Expects and parses JSON responses from LLMs.

## Usage

### Basic Usage

```python
from omni.execution.executor import LLMTaskExecutor
from omni.router import ModelRouter, RouterConfig
from omni.providers.mock_provider import MockProvider
from omni.task.models import Task, TaskType, ComplexityEstimate
from omni.execution.config import ExecutionContext

# Create router with providers
mock_provider = MockProvider()
config = RouterConfig(providers={
    "provider/fast-model": mock_provider,
    "provider/standard-model": mock_provider,
    # ... other providers
})
router = ModelRouter(config)

# Create executor
executor = LLMTaskExecutor(
    router=router,
    timeout_per_task=300.0,  # 5 minutes
    default_temperature=0.7,
    max_tokens_per_task=4000,
)

# Create task
task = Task(
    description="Write a function to calculate factorial",
    task_type=TaskType.CODE_GENERATION,
    complexity=ComplexityEstimate(
        code_complexity=3,
        integration_complexity=2,
        testing_complexity=1,
        unknown_factor=1,
    ),
)

# Create execution context
context = ExecutionContext(
    dependency_results={},
    execution_id="test-123",
    task_index=1,
    total_tasks=5,
)

# Execute task
result = await executor.execute(task, context)
```

### With ParallelExecutionEngine

```python
from omni.execution.engine import ParallelExecutionEngine
from omni.task.models import TaskGraph

# Create task graph
graph = TaskGraph(tasks=[task1, task2, task3], dependencies={...})

# Create engine with LLMTaskExecutor
engine = ParallelExecutionEngine(
    graph=graph,
    executor=executor,  # LLMTaskExecutor instance
    config=ExecutionConfig(max_concurrent_tasks=5),
)

# Execute the graph
execution_result = await engine.execute()
```

## Prompt Structure

The executor builds prompts with the following structure:

```
# TASK: [Task description]
Task Type: [task_type]

## DEPENDENCY RESULTS:
### Dependency: [dep_id] ✅/❌
Outputs:
```json
[formatted JSON outputs]
```
Errors: [error messages]

## EXECUTION CONTEXT:
- Execution ID: [execution_id]
- Task [index] of [total]
- Dependencies: [count]

## COMPLEXITY ANALYSIS:
- Tier: [tier]
- Overall Score: [score]/10
- Reasoning: [reasoning]

## INSTRUCTIONS:
Complete this task. Provide your response as a JSON object with the following structure:
```json
{
  "result": "The main result of the task",
  "explanation": "Brief explanation of what you did",
  "next_steps": ["Optional next steps or recommendations"]
}
```
If the task fails, include an 'error' field instead of 'result'.
```

## Response Parsing

The executor expects JSON responses and handles:
- JSON in code blocks (```json ... ```)
- Plain JSON responses
- Error responses (with "error" field)

## Configuration

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `router` | `ModelRouter` | Required | ModelRouter instance for LLM calls |
| `timeout_per_task` | `float` | `300.0` | Maximum seconds per task execution |
| `default_temperature` | `float` | `0.7` | Default temperature for LLM calls |
| `max_tokens_per_task` | `int` | `4000` | Maximum tokens to generate per task |

### Tier-to-Model Mapping

The default mapping can be customized by modifying the `tier_to_model` dictionary:

```python
executor.tier_to_model = {
    "intern": "custom/intern-model",
    "coder": "custom/coder-model",
    # ...
}
```

### Fallback Models

The fallback chain can be customized:

```python
executor.fallback_models = [
    "custom/fallback-1",
    "custom/fallback-2",
]
```

## Testing

Integration tests are available in `tests/test_execution_executor.py`:

```bash
# Run all executor tests
pytest tests/test_execution_executor.py

# Run only LLMTaskExecutor tests
pytest tests/test_execution_executor.py -k "llm"
```

## Example

See `examples/llm_executor_demo.py` for a complete working example.

## Backward Compatibility

`LLMTaskExecutor` implements the same `TaskExecutor` protocol as `MockTaskExecutor`, so it can be used as a drop-in replacement in existing code.

## Requirements

- Python 3.12+
- `asyncio` for async execution
- Access to LLM providers via the router layer
- Provider configurations for the models in the tier mapping