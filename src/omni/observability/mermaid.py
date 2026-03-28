"""
Mermaid Live Updates for Execution Visualization.

Generates Mermaid diagram snapshots at each state change during execution.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..decomposition.visualizer import TaskGraphVisualizer
from ..execution.models import ExecutionMetrics
from ..task.models import TaskGraph


@dataclass
class MermaidSnapshotConfig:
    """Configuration for Mermaid snapshots."""

    output_dir: str | Path = "execution_snapshots"
    save_on_state_change: bool = True
    save_on_progress: bool = False  # Save on every progress update
    progress_interval: float = 0.1  # Save if progress changes by at least this amount
    max_snapshots: int = 1000  # Maximum number of snapshots to keep
    include_metrics: bool = True  # Include metrics in snapshot metadata
    format: str = "mermaid"  # "mermaid" or "json"


class MermaidSnapshotter:
    """Generates and saves Mermaid diagram snapshots during execution."""

    def __init__(
        self,
        task_graph: TaskGraph,
        config: MermaidSnapshotConfig | None = None,
    ) -> None:
        """Initialize the Mermaid snapshotter.

        Args:
            task_graph: The task graph being executed.
            config: Snapshot configuration.
        """
        self.task_graph = task_graph
        self.config = config or MermaidSnapshotConfig()

        # Create output directory
        self.output_dir = Path(self.config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # State tracking
        self.snapshot_count: int = 0
        self.last_progress: float = 0.0
        self.visualizer = TaskGraphVisualizer(task_graph)

        # Snapshot metadata
        self.execution_id: str | None = None
        self.start_time: datetime | None = None

    def set_execution_id(self, execution_id: str) -> None:
        """Set the execution ID for snapshot naming.

        Args:
            execution_id: Unique execution identifier.
        """
        self.execution_id = execution_id
        self.start_time = datetime.now()

    def save_snapshot(self, metrics: ExecutionMetrics | None = None) -> str:
        """Save a snapshot of the current task graph state.

        Args:
            metrics: Optional execution metrics to include.

        Returns:
            Path to the saved snapshot file.
        """
        if self.snapshot_count >= self.config.max_snapshots:
            return ""

        self.snapshot_count += 1

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        exec_prefix = f"{self.execution_id}_" if self.execution_id else ""
        filename = f"{exec_prefix}snapshot_{timestamp}_{self.snapshot_count:04d}"

        if self.config.format == "json":
            filepath = self.output_dir / f"{filename}.json"
            content = self._generate_json_snapshot(metrics)
        else:
            filepath = self.output_dir / f"{filename}.mmd"
            content = self._generate_mermaid_snapshot(metrics)

        # Save to file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return str(filepath)

    def _generate_mermaid_snapshot(self, metrics: ExecutionMetrics | None = None) -> str:
        """Generate Mermaid diagram with metadata.

        Args:
            metrics: Optional execution metrics.

        Returns:
            Mermaid diagram string with metadata comments.
        """
        # Generate base Mermaid diagram
        mermaid = self.visualizer.visualize("mermaid")

        # Add metadata as comments
        metadata_lines = [
            "%% Execution Snapshot Metadata",
            f"%% Snapshot: {self.snapshot_count}",
            f"%% Timestamp: {datetime.now().isoformat()}",
        ]

        if self.execution_id:
            metadata_lines.append(f"%% Execution ID: {self.execution_id}")

        if metrics:
            metadata_lines.extend([
                f"%% Progress: {metrics.completed}/{metrics.total_tasks} ({metrics.completed/metrics.total_tasks:.1%})",
                f"%% Running: {metrics.running}",
                f"%% Failed: {metrics.failed}",
                f"%% Skipped: {metrics.skipped}",
                f"%% Efficiency: {metrics.parallel_efficiency:.1%}",
            ])

        metadata = "\n".join(metadata_lines)
        return f"{metadata}\n\n{mermaid}"

    def _generate_json_snapshot(self, metrics: ExecutionMetrics | None = None) -> str:
        """Generate JSON snapshot with full state.

        Args:
            metrics: Optional execution metrics.

        Returns:
            JSON string containing snapshot data.
        """
        snapshot: dict[str, Any] = {
            "snapshot_number": self.snapshot_count,
            "timestamp": datetime.now().isoformat(),
            "execution_id": self.execution_id,
            "task_graph": {
                "name": self.task_graph.name,
                "size": self.task_graph.size,
                "edge_count": self.task_graph.edge_count,
            },
            "tasks": {},
        }

        # Add task states
        for task_id, task in self.task_graph.tasks.items():
            snapshot["tasks"][task_id] = {
                "description": task.description,
                "task_type": task.task_type.value if hasattr(task.task_type, 'value') else str(task.task_type),
                "status": task.status.value if hasattr(task.status, 'value') else str(task.status),
                "dependencies": list(task.dependencies),
                "priority": task.priority,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries,
            }

            if task.complexity:
                snapshot["tasks"][task_id]["complexity"] = {
                    "overall_score": task.complexity.overall_score,
                    "tier": task.complexity.tier.value if hasattr(task.complexity.tier, 'value') else str(task.complexity.tier),
                }

        # Add metrics if provided
        if metrics:
            snapshot["metrics"] = {
                "total_tasks": metrics.total_tasks,
                "completed": metrics.completed,
                "failed": metrics.failed,
                "skipped": metrics.skipped,
                "running": metrics.running,
                "pending": metrics.pending,
                "total_tokens_used": metrics.total_tokens_used,
                "total_cost": metrics.total_cost,
                "wall_clock_seconds": metrics.wall_clock_seconds,
                "parallel_efficiency": metrics.parallel_efficiency,
            }

        return json.dumps(snapshot, indent=2)

    def should_save_snapshot(self, metrics: ExecutionMetrics) -> bool:
        """Determine if a snapshot should be saved based on configuration.

        Args:
            metrics: Current execution metrics.

        Returns:
            True if a snapshot should be saved.
        """
        if not self.config.save_on_state_change and not self.config.save_on_progress:
            return False

        # Check if we've reached max snapshots
        if self.snapshot_count >= self.config.max_snapshots:
            return False

        # Always save on state change if configured
        if self.config.save_on_state_change:
            # Check if any task status changed since last snapshot
            # (This would require tracking previous state, simplified for now)
            return True

        # Save on progress if configured
        if self.config.save_on_progress:
            current_progress = metrics.completed / metrics.total_tasks if metrics.total_tasks > 0 else 0
            progress_change = abs(current_progress - self.last_progress)

            if progress_change >= self.config.progress_interval:
                self.last_progress = current_progress
                return True

        return False


def create_mermaid_callback(
    snapshotter: MermaidSnapshotter,
) -> Callable[[ExecutionMetrics], None]:
    """Create a callback function for saving Mermaid snapshots.

    Args:
        snapshotter: The snapshotter instance.

    Returns:
        Callback function that can be passed to ExecutionCallbacks.on_progress.
    """
    def callback(metrics: ExecutionMetrics) -> None:
        if snapshotter.should_save_snapshot(metrics):
            snapshotter.save_snapshot(metrics)

    return callback


def generate_execution_animation(
    snapshot_dir: str | Path,
    output_file: str | Path = "execution_animation.html",
) -> str:
    """Generate an HTML file that animates through execution snapshots.

    Args:
        snapshot_dir: Directory containing Mermaid snapshot files.
        output_file: Path to output HTML file.

    Returns:
        Path to the generated HTML file.
    """
    # Import and use the simple version to avoid f-string complexity
    from .mermaid_simple import generate_execution_animation as simple_generate
    return simple_generate(snapshot_dir, output_file)
