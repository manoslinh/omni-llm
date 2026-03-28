"""
SQLite persistence for execution state.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from ..task.models import TaskResult, TaskStatus
from .config import ExecutionConfig
from .models import ExecutionStatus


class ExecutionDB:
    """SQLite database for execution state persistence."""

    def __init__(self, db_path: str | Path = "omni_executions.db") -> None:
        """
        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema if it doesn't exist."""
        conn = self._get_connection()
        
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        
        # Create tables
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS executions (
                execution_id TEXT PRIMARY KEY,
                graph_name   TEXT NOT NULL,
                started_at   TEXT NOT NULL,
                completed_at TEXT,
                status       TEXT NOT NULL DEFAULT 'running',
                config_json  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_states (
                execution_id TEXT NOT NULL,
                task_id      TEXT NOT NULL,
                status       TEXT NOT NULL,
                started_at   TEXT,
                completed_at TEXT,
                retry_count  INTEGER NOT NULL DEFAULT 0,
                result_json  TEXT,
                error_msg    TEXT,
                PRIMARY KEY (execution_id, task_id),
                FOREIGN KEY (execution_id) REFERENCES executions(execution_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_task_states_status 
            ON task_states(execution_id, status);
        """)
        
        conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,  # Longer timeout for concurrent access
            )
            # Enable foreign keys
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def save_execution(
        self,
        execution_id: str,
        graph_name: str,
        config: ExecutionConfig,
        status: ExecutionStatus = ExecutionStatus.RUNNING,
        completed_at: datetime | None = None,
    ) -> None:
        """Save or update execution metadata."""
        conn = self._get_connection()
        
        # Check if execution already exists
        cursor = conn.execute(
            "SELECT 1 FROM executions WHERE execution_id = ?",
            (execution_id,)
        )
        exists = cursor.fetchone() is not None
        
        if exists:
            # Update existing execution
            conn.execute(
                """
                UPDATE executions 
                SET status = ?, completed_at = ?
                WHERE execution_id = ?
                """,
                (
                    status.value,
                    completed_at.isoformat() if completed_at else None,
                    execution_id,
                )
            )
        else:
            # Insert new execution
            conn.execute(
                """
                INSERT INTO executions 
                (execution_id, graph_name, started_at, status, config_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    graph_name,
                    datetime.now().isoformat(),
                    status.value,
                    json.dumps(self._config_to_dict(config)),
                )
            )
        
        conn.commit()

    def save_task_state(
        self,
        execution_id: str,
        task_id: str,
        status: TaskStatus,
        retry_count: int = 0,
        result: TaskResult | None = None,
        error_msg: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        """Save or update task state."""
        conn = self._get_connection()
        
        # Check if task state already exists
        cursor = conn.execute(
            """
            SELECT 1 FROM task_states 
            WHERE execution_id = ? AND task_id = ?
            """,
            (execution_id, task_id)
        )
        exists = cursor.fetchone() is not None
        
        result_json = json.dumps(self._result_to_dict(result)) if result else None
        
        if exists:
            # Update existing task state
            conn.execute(
                """
                UPDATE task_states 
                SET status = ?, started_at = ?, completed_at = ?,
                    retry_count = ?, result_json = ?, error_msg = ?
                WHERE execution_id = ? AND task_id = ?
                """,
                (
                    status.value,
                    started_at.isoformat() if started_at else None,
                    completed_at.isoformat() if completed_at else None,
                    retry_count,
                    result_json,
                    error_msg,
                    execution_id,
                    task_id,
                )
            )
        else:
            # Insert new task state
            conn.execute(
                """
                INSERT INTO task_states 
                (execution_id, task_id, status, started_at, completed_at,
                 retry_count, result_json, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    task_id,
                    status.value,
                    started_at.isoformat() if started_at else None,
                    completed_at.isoformat() if completed_at else None,
                    retry_count,
                    result_json,
                    error_msg,
                )
            )
        
        conn.commit()

    def load_execution(
        self,
        execution_id: str,
    ) -> tuple[str, datetime | None, datetime | None, ExecutionStatus, ExecutionConfig]:
        """Load execution metadata."""
        conn = self._get_connection()
        
        cursor = conn.execute(
            """
            SELECT graph_name, started_at, completed_at, status, config_json
            FROM executions 
            WHERE execution_id = ?
            """,
            (execution_id,)
        )
        
        row = cursor.fetchone()
        if not row:
            raise KeyError(f"Execution {execution_id} not found")
        
        graph_name, started_at_str, completed_at_str, status_str, config_json = row
        
        # Parse dates
        started_at = datetime.fromisoformat(started_at_str) if started_at_str else None
        completed_at = datetime.fromisoformat(completed_at_str) if completed_at_str else None
        
        # Parse config
        config_dict = json.loads(config_json)
        config = self._dict_to_config(config_dict)
        
        # Parse status
        status = ExecutionStatus(status_str)
        
        return graph_name, started_at, completed_at, status, config

    def load_task_states(
        self,
        execution_id: str,
    ) -> dict[str, tuple[TaskStatus, int, TaskResult | None, str | None]]:
        """Load all task states for an execution."""
        conn = self._get_connection()
        
        cursor = conn.execute(
            """
            SELECT task_id, status, retry_count, result_json, error_msg
            FROM task_states 
            WHERE execution_id = ?
            """,
            (execution_id,)
        )
        
        results = {}
        for task_id, status_str, retry_count, result_json, error_msg in cursor:
            status = TaskStatus(status_str)
            result = self._dict_to_result(json.loads(result_json)) if result_json else None
            results[task_id] = (status, retry_count, result, error_msg)
        
        return results

    def get_execution_status(self, execution_id: str) -> ExecutionStatus:
        """Get current status of an execution."""
        conn = self._get_connection()
        
        cursor = conn.execute(
            "SELECT status FROM executions WHERE execution_id = ?",
            (execution_id,)
        )
        
        row = cursor.fetchone()
        if not row:
            raise KeyError(f"Execution {execution_id} not found")
        
        return ExecutionStatus(row[0])

    def list_executions(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[tuple[str, str, ExecutionStatus, datetime]]:
        """List executions with pagination."""
        conn = self._get_connection()
        
        cursor = conn.execute(
            """
            SELECT execution_id, graph_name, status, started_at
            FROM executions 
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        )
        
        return [
            (exec_id, graph_name, ExecutionStatus(status), datetime.fromisoformat(started_at))
            for exec_id, graph_name, status, started_at in cursor
        ]

    def delete_execution(self, execution_id: str) -> None:
        """Delete an execution and all its task states."""
        conn = self._get_connection()
        
        # Foreign key cascade should delete task_states automatically
        conn.execute(
            "DELETE FROM executions WHERE execution_id = ?",
            (execution_id,)
        )
        
        conn.commit()

    # Helper methods for serialization

    def _config_to_dict(self, config: ExecutionConfig) -> dict[str, Any]:
        """Convert ExecutionConfig to dict."""
        return {
            "max_concurrent": config.max_concurrent,
            "retry_enabled": config.retry_enabled,
            "backoff_base": config.backoff_base,
            "backoff_max": config.backoff_max,
            "timeout_per_task": config.timeout_per_task,
            "fail_fast": config.fail_fast,
            "skip_on_dep_failure": config.skip_on_dep_failure,
            "checkpoint_interval": config.checkpoint_interval,
        }

    def _dict_to_config(self, data: dict[str, Any]) -> ExecutionConfig:
        """Convert dict to ExecutionConfig."""
        return ExecutionConfig(**data)

    def _result_to_dict(self, result: TaskResult) -> dict[str, Any]:
        """Convert TaskResult to dict."""
        return {
            "task_id": result.task_id,
            "status": result.status.value,
            "outputs": result.outputs,
            "errors": result.errors,
            "metadata": result.metadata,
            "tokens_used": result.tokens_used,
            "cost": result.cost,
        }

    def _dict_to_result(self, data: dict[str, Any]) -> TaskResult:
        """Convert dict to TaskResult."""
        # Need to import TaskStatus from the right place
        from ..task.models import TaskStatus
        
        return TaskResult(
            task_id=data["task_id"],
            status=TaskStatus(data["status"]),
            outputs=data.get("outputs", {}),
            errors=data.get("errors", []),
            metadata=data.get("metadata", {}),
            tokens_used=data.get("tokens_used", 0),
            cost=data.get("cost", 0.0),
        )