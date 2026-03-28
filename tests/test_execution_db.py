"""
Tests for execution database.
"""

import tempfile
from datetime import datetime

import pytest

from src.omni.execution.config import ExecutionConfig
from src.omni.execution.db import ExecutionDB
from src.omni.execution.models import ExecutionStatus
from src.omni.task.models import TaskResult, TaskStatus


def test_execution_db_creation() -> None:
    """Test ExecutionDB creation and schema initialization."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db_path = tmp.name

        # Create database
        db = ExecutionDB(db_path)

        # Verify tables exist by querying them
        conn = db._get_connection()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        assert "executions" in tables
        assert "task_states" in tables

        # Verify indexes exist
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cursor.fetchall()}

        assert "idx_task_states_status" in indexes

        db.close()


def test_save_and_load_execution() -> None:
    """Test saving and loading execution metadata."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db = ExecutionDB(tmp.name)

        config = ExecutionConfig(max_concurrent=3, fail_fast=True)

        # Save execution
        db.save_execution(
            execution_id="test123",
            graph_name="test_graph",
            config=config,
            status=ExecutionStatus.RUNNING,
        )

        # Load execution
        graph_name, started_at, completed_at, status, loaded_config = db.load_execution(
            "test123"
        )

        assert graph_name == "test_graph"
        assert status == ExecutionStatus.RUNNING
        assert completed_at is None
        assert started_at is not None

        # Verify config
        assert loaded_config.max_concurrent == 3
        assert loaded_config.fail_fast is True
        assert isinstance(loaded_config, ExecutionConfig)

        # Update execution
        completed_time = datetime.now()
        db.save_execution(
            execution_id="test123",
            graph_name="test_graph",
            config=config,
            status=ExecutionStatus.COMPLETED,
            completed_at=completed_time,
        )

        # Reload and verify update
        _, _, loaded_completed_at, loaded_status, _ = db.load_execution("test123")

        assert loaded_status == ExecutionStatus.COMPLETED
        assert loaded_completed_at is not None
        # Allow small time difference due to serialization
        assert abs((loaded_completed_at - completed_time).total_seconds()) < 1

        db.close()


def test_save_and_load_task_state() -> None:
    """Test saving and loading task states."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db = ExecutionDB(tmp.name)

        # First save an execution (required for foreign key)
        config = ExecutionConfig()
        db.save_execution(
            execution_id="test123",
            graph_name="test_graph",
            config=config,
        )

        # Save task state with result
        result = TaskResult(
            task_id="task1",
            status=TaskStatus.COMPLETED,
            outputs={"result": "success"},
            tokens_used=100,
            cost=0.002,
        )

        started_at = datetime.now()
        completed_at = datetime.now()

        db.save_task_state(
            execution_id="test123",
            task_id="task1",
            status=TaskStatus.COMPLETED,
            retry_count=0,
            result=result,
            error_msg=None,
            started_at=started_at,
            completed_at=completed_at,
        )

        # Save task state with error
        db.save_task_state(
            execution_id="test123",
            task_id="task2",
            status=TaskStatus.FAILED,
            retry_count=2,
            result=None,
            error_msg="Task failed",
            started_at=started_at,
            completed_at=completed_at,
        )

        # Load task states
        task_states = db.load_task_states("test123")

        assert len(task_states) == 2

        # Check task1
        status1, retry_count1, result1, error_msg1 = task_states["task1"]
        assert status1 == TaskStatus.COMPLETED
        assert retry_count1 == 0
        assert result1 is not None
        assert result1.task_id == "task1"
        assert result1.status == TaskStatus.COMPLETED
        assert result1.outputs == {"result": "success"}
        assert result1.tokens_used == 100
        assert result1.cost == 0.002
        assert error_msg1 is None

        # Check task2
        status2, retry_count2, result2, error_msg2 = task_states["task2"]
        assert status2 == TaskStatus.FAILED
        assert retry_count2 == 2
        assert result2 is None
        assert error_msg2 == "Task failed"

        # Update task state
        db.save_task_state(
            execution_id="test123",
            task_id="task1",
            status=TaskStatus.FAILED,  # Changed status
            retry_count=1,  # Changed retry count
            result=None,
            error_msg="Updated error",
        )

        # Reload and verify update
        task_states = db.load_task_states("test123")
        status1, retry_count1, result1, error_msg1 = task_states["task1"]

        assert status1 == TaskStatus.FAILED
        assert retry_count1 == 1
        assert result1 is None  # Result cleared
        assert error_msg1 == "Updated error"

        db.close()


def test_get_execution_status() -> None:
    """Test getting execution status."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db = ExecutionDB(tmp.name)

        config = ExecutionConfig()

        # Save execution
        db.save_execution(
            execution_id="test123",
            graph_name="test_graph",
            config=config,
            status=ExecutionStatus.RUNNING,
        )

        # Get status
        status = db.get_execution_status("test123")
        assert status == ExecutionStatus.RUNNING

        # Update status
        db.save_execution(
            execution_id="test123",
            graph_name="test_graph",
            config=config,
            status=ExecutionStatus.COMPLETED,
        )

        # Get updated status
        status = db.get_execution_status("test123")
        assert status == ExecutionStatus.COMPLETED

        # Test non-existent execution
        with pytest.raises(KeyError, match="Execution not_found not found"):
            db.get_execution_status("not_found")

        db.close()


def test_list_executions() -> None:
    """Test listing executions."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db = ExecutionDB(tmp.name)

        config = ExecutionConfig()

        # Save multiple executions
        for i in range(5):
            db.save_execution(
                execution_id=f"test{i}",
                graph_name=f"graph_{i}",
                config=config,
                status=ExecutionStatus.COMPLETED if i % 2 == 0 else ExecutionStatus.FAILED,
            )

        # List all executions
        executions = db.list_executions(limit=10)

        assert len(executions) == 5

        # Check ordering (should be by started_at DESC)
        # Since we created them sequentially, the last one should be first
        exec_ids = [e[0] for e in executions]
        assert "test4" in exec_ids[0]  # Most recent

        # Check contents
        for exec_id, graph_name, status, started_at in executions:
            assert exec_id.startswith("test")
            assert graph_name.startswith("graph_")
            assert status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED)
            assert isinstance(started_at, datetime)

        # Test pagination
        executions_page1 = db.list_executions(limit=2, offset=0)
        executions_page2 = db.list_executions(limit=2, offset=2)

        assert len(executions_page1) == 2
        assert len(executions_page2) == 2
        # Should be different executions
        assert executions_page1[0][0] != executions_page2[0][0]

        db.close()


def test_delete_execution() -> None:
    """Test deleting an execution and its task states."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db = ExecutionDB(tmp.name)

        config = ExecutionConfig()

        # Save execution with task states
        db.save_execution(
            execution_id="test123",
            graph_name="test_graph",
            config=config,
        )

        db.save_task_state(
            execution_id="test123",
            task_id="task1",
            status=TaskStatus.COMPLETED,
        )

        db.save_task_state(
            execution_id="test123",
            task_id="task2",
            status=TaskStatus.FAILED,
        )

        # Verify data exists
        task_states = db.load_task_states("test123")
        assert len(task_states) == 2

        # Delete execution
        db.delete_execution("test123")

        # Verify execution is gone
        with pytest.raises(KeyError, match="Execution test123 not found"):
            db.load_execution("test123")

        # Verify task states are gone (foreign key cascade)
        # Note: SQLite may still have the connection open, so we need to check directly
        conn = db._get_connection()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM task_states WHERE execution_id = ?",
            ("test123",)
        )
        count = cursor.fetchone()[0]
        assert count == 0

        db.close()


def test_serialization_helpers() -> None:
    """Test config and result serialization helpers."""
    db = ExecutionDB(":memory:")  # In-memory database for this test

    # Test config serialization
    config = ExecutionConfig(
        max_concurrent=7,
        retry_enabled=False,
        backoff_base=1.5,
        backoff_max=30.0,
        timeout_per_task=120.0,
        fail_fast=True,
        skip_on_dep_failure=False,
        checkpoint_interval=3,
    )

    config_dict = db._config_to_dict(config)
    assert isinstance(config_dict, dict)
    assert config_dict["max_concurrent"] == 7
    assert config_dict["retry_enabled"] is False
    assert config_dict["fail_fast"] is True

    # Round-trip test
    loaded_config = db._dict_to_config(config_dict)
    assert loaded_config.max_concurrent == 7
    assert loaded_config.retry_enabled is False
    assert loaded_config.fail_fast is True
    assert isinstance(loaded_config, ExecutionConfig)

    # Test result serialization
    result = TaskResult(
        task_id="task1",
        status=TaskStatus.COMPLETED,
        outputs={"key": "value", "nested": {"a": 1}},
        errors=["error1", "error2"],
        metadata={"meta": "data", "count": 42},
        tokens_used=1234,
        cost=0.02468,
    )

    result_dict = db._result_to_dict(result)
    assert isinstance(result_dict, dict)
    assert result_dict["task_id"] == "task1"
    assert result_dict["status"] == "completed"
    assert result_dict["outputs"]["key"] == "value"
    assert result_dict["errors"] == ["error1", "error2"]
    assert result_dict["metadata"]["count"] == 42
    assert result_dict["tokens_used"] == 1234
    assert result_dict["cost"] == 0.02468

    # Round-trip test
    loaded_result = db._dict_to_result(result_dict)
    assert loaded_result.task_id == "task1"
    assert loaded_result.status == TaskStatus.COMPLETED
    assert loaded_result.outputs["key"] == "value"
    assert loaded_result.errors == ["error1", "error2"]
    assert loaded_result.metadata["count"] == 42
    assert loaded_result.tokens_used == 1234
    assert loaded_result.cost == 0.02468
    assert isinstance(loaded_result, TaskResult)

    db.close()
