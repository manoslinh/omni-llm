"""
Execution Replay for analyzing past executions.

Loads past execution from database and replays state transitions
for visualization and analysis.
"""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..execution.db import ExecutionDB
from ..execution.models import ExecutionMetrics, ExecutionResult
from ..task.models import TaskGraph, TaskStatus
from .dashboard import LiveDashboard
from .mermaid import MermaidSnapshotter


@dataclass
class ReplayConfig:
    """Configuration for execution replay."""

    playback_speed: float = 1.0  # 1.0 = realtime, 2.0 = 2x speed, etc.
    show_dashboard: bool = True
    save_snapshots: bool = False
    snapshot_dir: str | Path = "replay_snapshots"
    pause_on_failure: bool = False
    metrics_callback: Callable[[ExecutionMetrics], None] | None = None


class ExecutionReplayer:
    """Replays past executions from database."""

    def __init__(
        self,
        db_path: str | Path = "omni_executions.db",
        config: ReplayConfig | None = None,
    ) -> None:
        """Initialize the execution replayer.

        Args:
            db_path: Path to SQLite database.
            config: Replay configuration.
        """
        self.db = ExecutionDB(db_path)
        self.config = config or ReplayConfig()

        # Replay state
        self.current_execution_id: str | None = None
        self.task_graph: TaskGraph | None = None
        self.execution_result: ExecutionResult | None = None
        self.task_states: list[dict[str, Any]] = []
        self.current_state_index: int = 0

        # Visualization components
        self.dashboard: LiveDashboard | None = None
        self.snapshotter: MermaidSnapshotter | None = None

    async def load_execution(self, execution_id: str) -> None:
        """Load an execution from the database.

        Args:
            execution_id: ID of the execution to load.

        Raises:
            ValueError: If execution not found.
        """
        try:
            # Load execution record - returns tuple
            graph_name, started_at, completed_at, status, config = self.db.load_execution(execution_id)
        except KeyError:
            raise ValueError(f"Execution {execution_id} not found") from None

        # Load task states - returns dict
        task_states_dict = self.db.load_task_states(execution_id)

        # Convert task states dict to list of dicts for sorting
        self.task_states = []
        for task_id, (task_status, retry_count, _result, _error_msg) in task_states_dict.items():
            # Create a dict representation for sorting and display
            state_dict = {
                "task_id": task_id,
                "status": task_status.value if hasattr(task_status, 'value') else str(task_status),
                "retry_count": retry_count,
            }
            # Add timestamps if available (we'd need to store these in the database)
            # For now, we'll use placeholder
            self.task_states.append(state_dict)

        # Sort task states by task_id for now (since we don't have timestamps)
        self.task_states = sorted(
            self.task_states,
            key=lambda x: x.get("task_id", "")
        )

        # TODO: Reconstruct TaskGraph from execution config
        # For now, we'll create a minimal task graph
        self.task_graph = TaskGraph(name=graph_name)

        self.current_execution_id = execution_id
        self.execution_result = ExecutionResult(
            execution_id=execution_id,
            graph_name=graph_name,
            status=status,  # status is already ExecutionStatus type
            results={},
            metrics=ExecutionMetrics(
                execution_id=execution_id,
                total_tasks=0,
                completed=0,
                failed=0,
                skipped=0,
                running=0,
                pending=0,
                total_tokens_used=0,
                total_cost=0.0,
                wall_clock_seconds=0.0,
                parallel_efficiency=0.0,
            ),
            started_at=started_at or datetime.now(),
            completed_at=completed_at,
            dead_letter=[],
            config=config.__dict__ if config else {},
        )

        # Initialize visualization if configured
        if self.config.show_dashboard and self.task_graph:
            from .dashboard import DashboardConfig, LiveDashboard
            self.dashboard = LiveDashboard(
                self.task_graph,
                DashboardConfig(refresh_rate=0.1)
            )

        if self.config.save_snapshots and self.task_graph:
            from .mermaid import MermaidSnapshotConfig, MermaidSnapshotter
            self.snapshotter = MermaidSnapshotter(
                self.task_graph,
                MermaidSnapshotConfig(
                    output_dir=self.config.snapshot_dir,
                    save_on_state_change=True,
                )
            )
            self.snapshotter.set_execution_id(execution_id)

    async def replay(self) -> None:
        """Replay the loaded execution.

        Raises:
            RuntimeError: If no execution is loaded.
        """
        if not self.current_execution_id:
            raise RuntimeError("No execution loaded. Call load_execution() first.")

        if self.dashboard:
            self.dashboard.start()

        # Replay each state transition
        for i, state in enumerate(self.task_states):
            self.current_state_index = i
            await self._apply_state(state)

            # Calculate metrics for this state
            metrics = self._calculate_current_metrics()

            # Update dashboard
            if self.dashboard:
                self.dashboard.update(metrics)

            # Save snapshot
            if self.snapshotter:
                self.snapshotter.save_snapshot(metrics)

            # Call metrics callback
            if self.config.metrics_callback:
                self.config.metrics_callback(metrics)

            # Pause on failure if configured
            if (
                self.config.pause_on_failure
                and state.get("status") == TaskStatus.FAILED.value
            ):
                print("\n⏸ Task failed. Press Enter to continue...")
                input()

            # Sleep to simulate real-time playback
            if i < len(self.task_states) - 1:
                next_state = self.task_states[i + 1]
                current_time = self._parse_time(state)
                next_time = self._parse_time(next_state)

                if current_time and next_time:
                    time_diff = (next_time - current_time).total_seconds()
                    adjusted_diff = time_diff / self.config.playback_speed

                    if adjusted_diff > 0:
                        await asyncio.sleep(adjusted_diff)

        # Final update
        if self.dashboard:
            final_metrics = self._calculate_final_metrics()
            self.dashboard.update(final_metrics)
            self.dashboard.stop()

    def _parse_time(self, state: dict[str, Any]) -> datetime | None:
        """Parse timestamp from state record."""
        for time_field in ["started_at", "completed_at"]:
            if time_field in state and state[time_field]:
                try:
                    return datetime.fromisoformat(state[time_field])
                except (ValueError, TypeError):
                    continue
        return None

    async def _apply_state(self, state: dict[str, Any]) -> None:
        """Apply a single state transition to the task graph.

        Args:
            state: Task state record from database.
        """
        if not self.task_graph:
            return

        task_id = state["task_id"]
        status_str = state.get("status", "")

        # Try to find the task in the graph
        # In a real implementation, we'd have reconstructed the full graph
        # For now, we'll just track state in a separate dict
        if not hasattr(self, '_task_states'):
            self._task_states: dict[str, str] = {}

        # Update task state
        self._task_states[task_id] = status_str

        # Print status update
        print(f"  [{status_str}] Task {task_id}")

        # If we had the actual task objects, we would update them:
        # if task_id in self.task_graph.tasks:
        #     task = self.task_graph.tasks[task_id]
        #     try:
        #         task.status = TaskStatus(status_str)
        #     except ValueError:
        #         # Handle unknown status
        #         pass

    def _calculate_current_metrics(self) -> ExecutionMetrics:
        """Calculate metrics for current replay state.

        Returns:
            Current execution metrics.
        """
        if not self.task_graph or not self.execution_result:
            return ExecutionMetrics(
                execution_id=self.current_execution_id or "",
                total_tasks=0,
                completed=0,
                failed=0,
                skipped=0,
                running=0,
                pending=0,
                total_tokens_used=0,
                total_cost=0.0,
                wall_clock_seconds=0.0,
                parallel_efficiency=0.0,
            )

        # Count tasks by status in current state
        completed = 0
        failed = 0
        skipped = 0
        running = 0
        pending = 0

        # Process states up to current index
        for i in range(self.current_state_index + 1):
            if i >= len(self.task_states):
                break

            state = self.task_states[i]
            status = state.get("status")

            if status == TaskStatus.COMPLETED.value:
                completed += 1
            elif status == TaskStatus.FAILED.value:
                failed += 1
            elif status == TaskStatus.SKIPPED.value:
                skipped += 1
            elif status == TaskStatus.RUNNING.value:
                running += 1
            elif status == TaskStatus.PENDING.value:
                pending += 1

        total_tasks = len(self.task_graph.tasks) if self.task_graph else 0

        # Calculate wall clock time
        wall_clock = 0.0
        if self.task_states:
            first_state = self.task_states[0]
            current_state = self.task_states[min(self.current_state_index, len(self.task_states) - 1)]

            first_time = self._parse_time(first_state)
            current_time = self._parse_time(current_state)

            if first_time and current_time:
                wall_clock = (current_time - first_time).total_seconds()

        return ExecutionMetrics(
            execution_id=self.current_execution_id or "",
            total_tasks=total_tasks,
            completed=completed,
            failed=failed,
            skipped=skipped,
            running=running,
            pending=pending,
            total_tokens_used=0,  # TODO: Sum from states
            total_cost=0.0,  # TODO: Calculate from states
            wall_clock_seconds=wall_clock,
            parallel_efficiency=self._calculate_efficiency(),
        )

    def _calculate_final_metrics(self) -> ExecutionMetrics:
        """Calculate final metrics after replay completes.

        Returns:
            Final execution metrics.
        """
        metrics = self._calculate_current_metrics()

        # Use actual completion time if available
        if self.execution_result and self.execution_result.completed_at:
            total_time = (
                self.execution_result.completed_at - self.execution_result.started_at
            ).total_seconds()
            metrics.wall_clock_seconds = total_time

        return metrics

    def _calculate_efficiency(self) -> float:
        """Calculate parallel efficiency for current state.

        Returns:
            Parallel efficiency (0.0 to 1.0), or -1 if not calculable.
        """
        # Simplified efficiency calculation
        # In a real implementation, this would analyze task dependencies
        # and compare actual vs theoretical completion time

        if not self.task_states or self.current_state_index < 1:
            return -1.0

        # Count how many tasks were running concurrently at peak
        # This is a simplified approximation
        running_tasks = 0
        max_concurrent = 0

        for i in range(self.current_state_index + 1):
            state = self.task_states[i]
            if state.get("status") == TaskStatus.RUNNING.value:
                running_tasks += 1
                max_concurrent = max(max_concurrent, running_tasks)
            elif state.get("status") in [
                TaskStatus.COMPLETED.value,
                TaskStatus.FAILED.value,
                TaskStatus.SKIPPED.value,
            ]:
                running_tasks = max(0, running_tasks - 1)

        total_tasks = len(self.task_graph.tasks) if self.task_graph else 1
        efficiency = min(1.0, max_concurrent / total_tasks)

        return efficiency

    def export_timeline(self, output_file: str | Path) -> str:
        """Export replay timeline to JSON file.

        Args:
            output_file: Path to output JSON file.

        Returns:
            Path to the exported file.
        """
        if not self.task_states:
            raise RuntimeError("No execution loaded or no states available.")

        timeline: dict[str, Any] = {
            "execution_id": self.current_execution_id,
            "graph_name": self.execution_result.graph_name if self.execution_result else "",
            "states": self.task_states,
            "metrics_over_time": [],
        }

        # Calculate metrics at each state
        for i in range(len(self.task_states)):
            self.current_state_index = i
            metrics = self._calculate_current_metrics()

            timeline["metrics_over_time"].append({
                "state_index": i,
                "timestamp": self.task_states[i].get("started_at") or self.task_states[i].get("completed_at"),
                "metrics": {
                    "completed": metrics.completed,
                    "failed": metrics.failed,
                    "skipped": metrics.skipped,
                    "running": metrics.running,
                    "pending": metrics.pending,
                    "parallel_efficiency": metrics.parallel_efficiency,
                    "wall_clock_seconds": metrics.wall_clock_seconds,
                }
            })

        output_file = Path(output_file)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(timeline, f, indent=2, default=str)

        return str(output_file)


async def replay_execution(
    execution_id: str,
    db_path: str | Path = "omni_executions.db",
    config: ReplayConfig | None = None,
) -> None:
    """Convenience function to replay an execution.

    Args:
        execution_id: ID of the execution to replay.
        db_path: Path to SQLite database.
        config: Replay configuration.
    """
    replayer = ExecutionReplayer(db_path, config)
    await replayer.load_execution(execution_id)
    await replayer.replay()
