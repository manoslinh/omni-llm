"""
Tests for execution configuration.
"""

from typing import Any

import pytest

from src.omni.execution.config import (
    ExecutionCallbacks,
    ExecutionConfig,
    ExecutionContext,
)
from src.omni.task.models import Task, TaskResult, TaskStatus


def test_execution_config_defaults() -> None:
    """Test ExecutionConfig with default values."""
    config = ExecutionConfig()

    assert config.max_concurrent == 5
    assert config.retry_enabled is True
    assert config.backoff_base == 2.0
    assert config.backoff_max == 60.0
    assert config.timeout_per_task == 300.0
    assert config.fail_fast is False
    assert config.skip_on_dep_failure is True
    assert config.checkpoint_interval == 1


def test_execution_config_custom() -> None:
    """Test ExecutionConfig with custom values."""
    config = ExecutionConfig(
        max_concurrent=10,
        retry_enabled=False,
        backoff_base=1.0,
        backoff_max=30.0,
        timeout_per_task=60.0,
        fail_fast=True,
        skip_on_dep_failure=False,
        checkpoint_interval=5,
    )

    assert config.max_concurrent == 10
    assert config.retry_enabled is False
    assert config.backoff_base == 1.0
    assert config.backoff_max == 30.0
    assert config.timeout_per_task == 60.0
    assert config.fail_fast is True
    assert config.skip_on_dep_failure is False
    assert config.checkpoint_interval == 5


def test_execution_config_validation() -> None:
    """Test ExecutionConfig validation."""
    # Valid configs should not raise
    ExecutionConfig(max_concurrent=1)
    ExecutionConfig(backoff_base=0.1)
    ExecutionConfig(timeout_per_task=0.1)
    ExecutionConfig(checkpoint_interval=100)

    # Invalid configs should raise ValueError
    with pytest.raises(ValueError, match="max_concurrent must be at least 1"):
        ExecutionConfig(max_concurrent=0)

    with pytest.raises(ValueError, match="max_concurrent must be at least 1"):
        ExecutionConfig(max_concurrent=-1)

    with pytest.raises(ValueError, match="backoff_base must be positive"):
        ExecutionConfig(backoff_base=0)

    with pytest.raises(ValueError, match="backoff_base must be positive"):
        ExecutionConfig(backoff_base=-1.0)

    with pytest.raises(ValueError, match="backoff_max must be >= backoff_base"):
        ExecutionConfig(backoff_base=10.0, backoff_max=5.0)

    with pytest.raises(ValueError, match="timeout_per_task must be positive"):
        ExecutionConfig(timeout_per_task=0)

    with pytest.raises(ValueError, match="timeout_per_task must be positive"):
        ExecutionConfig(timeout_per_task=-1.0)

    with pytest.raises(ValueError, match="checkpoint_interval must be at least 1"):
        ExecutionConfig(checkpoint_interval=0)

    with pytest.raises(ValueError, match="checkpoint_interval must be at least 1"):
        ExecutionConfig(checkpoint_interval=-1)


def test_execution_context() -> None:
    """Test ExecutionContext."""
    dependency_results = {
        "dep1": TaskResult(task_id="dep1", status=TaskStatus.COMPLETED),
        "dep2": TaskResult(task_id="dep2", status=TaskStatus.COMPLETED),
    }

    context = ExecutionContext(
        dependency_results=dependency_results,
        execution_id="exec123",
        task_index=3,
        total_tasks=10,
    )

    assert context.dependency_results == dependency_results
    assert context.execution_id == "exec123"
    assert context.task_index == 3
    assert context.total_tasks == 10


def test_execution_callbacks() -> None:
    """Test ExecutionCallbacks."""
    callbacks = ExecutionCallbacks()

    # Callbacks should be None by default
    assert callbacks.on_task_start is None
    assert callbacks.on_task_complete is None
    assert callbacks.on_task_fail is None
    assert callbacks.on_progress is None
    assert callbacks.on_execution_complete is None

    # Test with actual callbacks
    task_start_called = False
    task_complete_called = False
    task_fail_called = False
    progress_called = False
    execution_complete_called = False

    def on_task_start(task_id: str, task: Task) -> None:
        nonlocal task_start_called
        task_start_called = True

    def on_task_complete(task_id: str, result: TaskResult) -> None:
        nonlocal task_complete_called
        task_complete_called = True

    def on_task_fail(task_id: str, task: Task, error: Exception) -> None:
        nonlocal task_fail_called
        task_fail_called = True

    def on_progress(metrics: Any) -> None:
        nonlocal progress_called
        progress_called = True

    def on_execution_complete(result: Any) -> None:
        nonlocal execution_complete_called
        execution_complete_called = True

    callbacks = ExecutionCallbacks(
        on_task_start=on_task_start,
        on_task_complete=on_task_complete,
        on_task_fail=on_task_fail,
        on_progress=on_progress,
        on_execution_complete=on_execution_complete,
    )

    # Test safe_call with actual callback
    task = Task(description="test")
    callbacks._safe_call(callbacks.on_task_start, "task1", task)
    assert task_start_called is True

    # Test safe_call with None callback (should not crash)
    callbacks._safe_call(None, "arg1", "arg2")

    # Test safe_call with callback that raises (should not crash)
    def raising_callback() -> None:
        raise ValueError("Test error")

    callbacks._safe_call(raising_callback)
