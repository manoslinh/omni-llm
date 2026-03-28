"""
Live ASCII Dashboard for Parallel Execution Engine.

Provides real-time terminal visualization of task graph execution.
"""

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from ..execution.models import ExecutionMetrics
from ..task.models import TaskGraph, TaskStatus


@dataclass
class DashboardConfig:
    """Configuration for the live dashboard."""

    refresh_rate: float = 0.5  # seconds between updates
    max_history: int = 100  # maximum history points for metrics
    show_progress_bars: bool = True
    show_parallelism: bool = True
    show_metrics: bool = True
    show_task_list: bool = True
    max_task_display: int = 10  # max tasks to show in list
    colors_enabled: bool = True  # enable ANSI colors


class LiveDashboard:
    """Terminal-based real-time execution visualization."""

    def __init__(
        self,
        task_graph: TaskGraph,
        config: DashboardConfig | None = None,
    ) -> None:
        """Initialize the live dashboard.

        Args:
            task_graph: The task graph being executed.
            config: Dashboard configuration.
        """
        self.task_graph = task_graph
        self.config = config or DashboardConfig()

        # Execution state
        self.start_time: float | None = None
        self.last_update: float = 0.0
        self.metrics_history: deque[ExecutionMetrics] = deque(
            maxlen=self.config.max_history
        )

        # Display state
        self._last_height: int = 0
        self._running: bool = False

        # Color codes (ANSI)
        self._colors = {
            "reset": "\033[0m",
            "bold": "\033[1m",
            "dim": "\033[2m",
            "red": "\033[31m",
            "green": "\033[32m",
            "yellow": "\033[33m",
            "blue": "\033[34m",
            "magenta": "\033[35m",
            "cyan": "\033[36m",
            "white": "\033[37m",
            "bg_blue": "\033[44m",
            "bg_green": "\033[42m",
            "bg_yellow": "\033[43m",
            "bg_red": "\033[41m",
        }

        # Status icons and colors
        self._status_config = {
            TaskStatus.PENDING: ("○", "dim"),
            TaskStatus.RUNNING: ("▶", "cyan"),
            TaskStatus.COMPLETED: ("✓", "green"),
            TaskStatus.FAILED: ("✗", "red"),
            TaskStatus.SKIPPED: ("-", "yellow"),
            TaskStatus.CANCELLED: ("×", "dim"),
        }

    def _color(self, name: str, text: str) -> str:
        """Apply color to text if colors are enabled."""
        if not self.config.colors_enabled or name not in self._colors:
            return text
        return f"{self._colors[name]}{text}{self._colors['reset']}"

    def _bold(self, text: str) -> str:
        """Apply bold styling."""
        return self._color("bold", text)

    def start(self) -> None:
        """Start the dashboard display."""
        self.start_time = time.time()
        self._running = True

        # Clear screen and hide cursor
        print("\033[2J\033[H\033[?25l", end="")

    def stop(self) -> None:
        """Stop the dashboard display."""
        self._running = False

        # Show cursor and move below dashboard
        print("\033[?25h\n" + "=" * 60 + "\n")

    def update(self, metrics: ExecutionMetrics) -> None:
        """Update dashboard with new metrics.

        Args:
            metrics: Current execution metrics.
        """
        if not self._running:
            return

        self.metrics_history.append(metrics)
        current_time = time.time()

        # Throttle updates
        if current_time - self.last_update < self.config.refresh_rate:
            return

        self.last_update = current_time
        self._render(metrics)

    def _render(self, metrics: ExecutionMetrics) -> None:
        """Render the dashboard to terminal."""
        lines = []

        # Header
        elapsed = time.time() - (self.start_time or time.time())
        lines.append(self._bold("🚀 Omni-LLM Execution Dashboard"))
        lines.append(f"Execution: {metrics.execution_id[:8]} | "
                    f"Elapsed: {elapsed:.1f}s | "
                    f"Tasks: {metrics.completed}/{metrics.total_tasks}")
        lines.append("=" * 60)

        # Progress overview
        if self.config.show_progress_bars:
            lines.append(self._render_progress_bar(metrics))
            lines.append("")

        # Parallelism visualization
        if self.config.show_parallelism:
            lines.append(self._render_parallelism(metrics))
            lines.append("")

        # Metrics
        if self.config.show_metrics:
            lines.append(self._render_metrics(metrics))
            lines.append("")

        # Task list
        if self.config.show_task_list:
            lines.append(self._render_task_list())

        # Clear previous output and render new
        output = "\n".join(lines)
        height = len(lines)

        # Move cursor to top and clear below
        print(f"\033[H{output}", end="")

        # Clear any remaining lines from previous render
        if height < self._last_height:
            for _ in range(self._last_height - height):
                print("\033[K")  # Clear line

        self._last_height = height

    def _render_progress_bar(self, metrics: ExecutionMetrics) -> str:
        """Render progress bar for task completion."""
        width = 40
        completed_pct = metrics.completed / metrics.total_tasks if metrics.total_tasks > 0 else 0

        # Calculate filled width
        filled = int(width * completed_pct)
        bar = "█" * filled + "░" * (width - filled)

        # Color based on completion
        if completed_pct >= 1.0:
            color = "green"
        elif completed_pct >= 0.7:
            color = "cyan"
        elif completed_pct >= 0.3:
            color = "yellow"
        else:
            color = "red"

        bar_colored = self._color(color, bar)

        return (f"Progress: {bar_colored} "
                f"{completed_pct:.1%} ({metrics.completed}/{metrics.total_tasks})")

    def _render_parallelism(self, metrics: ExecutionMetrics) -> str:
        """Render parallelism visualization."""
        max_concurrent = 10  # TODO: Get from config
        current_running = metrics.running

        # Create parallelism bar
        width = 30
        active_width = int(width * (current_running / max_concurrent))
        bar = "▓" * active_width + "░" * (width - active_width)

        # Calculate parallel efficiency
        if metrics.parallel_efficiency >= 0:
            efficiency_str = f"{metrics.parallel_efficiency:.1%}"
            if metrics.parallel_efficiency > 0.8:
                eff_color = "green"
            elif metrics.parallel_efficiency > 0.5:
                eff_color = "yellow"
            else:
                eff_color = "red"
            efficiency_str = self._color(eff_color, efficiency_str)
        else:
            efficiency_str = "N/A"

        return (f"Parallelism: {bar} {current_running}/{max_concurrent} concurrent\n"
                f"Efficiency:  {efficiency_str}")

    def _render_metrics(self, metrics: ExecutionMetrics) -> str:
        """Render execution metrics."""
        lines = []

        # Status counts
        status_line = (
            f"{self._color('green', f'✓ {metrics.completed}')} | "
            f"{self._color('red', f'✗ {metrics.failed}')} | "
            f"{self._color('yellow', f'- {metrics.skipped}')} | "
            f"{self._color('cyan', f'▶ {metrics.running}')} | "
            f"{self._color('dim', f'○ {metrics.pending}')}"
        )
        lines.append(f"Status: {status_line}")

        # Performance metrics
        if metrics.total_tokens_used > 0:
            lines.append(f"Tokens: {metrics.total_tokens_used:,} "
                        f"(≈${metrics.total_cost:.4f})")

        if metrics.wall_clock_seconds > 0:
            tasks_per_second = metrics.completed / metrics.wall_clock_seconds
            lines.append(f"Speed: {tasks_per_second:.2f} tasks/s")

        return "\n".join(lines)

    def _render_task_list(self) -> str:
        """Render list of recent tasks."""
        lines = [self._bold("Recent Tasks:"), ""]

        # Get tasks sorted by recent activity
        tasks = list(self.task_graph.tasks.values())

        # Sort by status (running first) then by ID
        status_order = {
            TaskStatus.RUNNING: 0,
            TaskStatus.FAILED: 1,
            TaskStatus.COMPLETED: 2,
            TaskStatus.SKIPPED: 3,
            TaskStatus.PENDING: 4,
            TaskStatus.CANCELLED: 5,
        }

        tasks.sort(key=lambda t: (status_order.get(t.status, 99), t.task_id))

        # Show limited number of tasks
        display_count = min(self.config.max_task_display, len(tasks))

        for _i, task in enumerate(tasks[:display_count]):
            icon, color = self._status_config.get(task.status, ("?", "white"))
            icon_colored = self._color(color, icon)

            # Truncate description
            desc = (task.description[:40] + "...") if len(task.description) > 40 else task.description

            lines.append(f"  {icon_colored} {task.task_id}: {desc}")

        if len(tasks) > display_count:
            remaining = len(tasks) - display_count
            lines.append(f"  ... and {remaining} more tasks")

        return "\n".join(lines)


def create_dashboard_callback(
    dashboard: LiveDashboard,
) -> Callable[[ExecutionMetrics], None]:
    """Create a callback function for updating the dashboard.

    Args:
        dashboard: The dashboard instance.

    Returns:
        Callback function that can be passed to ExecutionCallbacks.on_progress.
    """
    def callback(metrics: ExecutionMetrics) -> None:
        dashboard.update(metrics)

    return callback
