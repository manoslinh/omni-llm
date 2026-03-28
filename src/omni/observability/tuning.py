"""
Performance Tuning for Parallel Execution Engine.

Provides adaptive concurrency control and performance optimization
based on real-time execution metrics.
"""

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from ..execution.config import ExecutionConfig
from ..execution.models import ExecutionMetrics


@dataclass
class TuningConfig:
    """Configuration for performance tuning."""

    # Adaptive concurrency
    enable_adaptive_concurrency: bool = True
    min_concurrent: int = 1
    max_concurrent: int = 20
    adjustment_interval: float = 5.0  # seconds between adjustments
    completion_rate_window: int = 10  # number of tasks to consider

    # Thresholds for adjustment
    high_utilization_threshold: float = 0.8  # 80% CPU utilization
    low_utilization_threshold: float = 0.3  # 30% CPU utilization
    target_completion_rate: float = 2.0  # tasks per second

    # Safety limits
    max_adjustment_step: int = 2
    cooldown_period: float = 10.0  # seconds after adjustment

    # Resource monitoring
    monitor_memory: bool = False
    memory_threshold_mb: float = 1024.0  # 1GB


class AdaptiveConcurrencyController:
    """Dynamically adjusts concurrency based on execution performance."""

    def __init__(
        self,
        initial_config: ExecutionConfig,
        tuning_config: TuningConfig | None = None,
    ) -> None:
        """Initialize the adaptive concurrency controller.

        Args:
            initial_config: Initial execution configuration.
            tuning_config: Tuning configuration.
        """
        self.initial_config = initial_config
        self.tuning_config = tuning_config or TuningConfig()

        # Current state
        self.current_concurrent = initial_config.max_concurrent
        self.last_adjustment_time: float = 0.0
        self.is_cooldown: bool = False
        self.cooldown_until: float = 0.0

        # Performance history
        self.completion_times: deque[float] = deque(
            maxlen=self.tuning_config.completion_rate_window
        )
        self.task_start_times: dict[str, float] = {}

        # Statistics
        self.adjustment_count: int = 0
        self.total_tasks_completed: int = 0

    def record_task_start(self, task_id: str) -> None:
        """Record when a task starts.

        Args:
            task_id: ID of the starting task.
        """
        self.task_start_times[task_id] = time.time()

    def record_task_completion(self, task_id: str) -> None:
        """Record when a task completes.

        Args:
            task_id: ID of the completed task.
        """
        if task_id in self.task_start_times:
            start_time = self.task_start_times.pop(task_id)
            duration = time.time() - start_time
            self.completion_times.append(duration)
            self.total_tasks_completed += 1

    def should_adjust(self, metrics: ExecutionMetrics) -> bool:
        """Determine if concurrency should be adjusted.

        Args:
            metrics: Current execution metrics.

        Returns:
            True if adjustment should be considered.
        """
        if not self.tuning_config.enable_adaptive_concurrency:
            return False

        current_time = time.time()

        # Check cooldown
        if self.is_cooldown:
            if current_time >= self.cooldown_until:
                self.is_cooldown = False
            else:
                return False

        # Check adjustment interval
        time_since_adjustment = current_time - self.last_adjustment_time
        if time_since_adjustment < self.tuning_config.adjustment_interval:
            return False

        # Need enough data to make decision
        if len(self.completion_times) < 3:
            return False

        return True

    def calculate_adjustment(self, metrics: ExecutionMetrics) -> int | None:
        """Calculate concurrency adjustment based on metrics.

        Args:
            metrics: Current execution metrics.

        Returns:
            Suggested new concurrency level, or None for no change.
        """
        if not self.should_adjust(metrics):
            return None

        current_time = time.time()

        # Calculate completion rate (tasks per second)
        if self.completion_times:
            avg_completion_time = sum(self.completion_times) / len(self.completion_times)
            completion_rate = 1.0 / avg_completion_time if avg_completion_time > 0 else 0
        else:
            completion_rate = 0

        # Calculate utilization
        running_tasks = metrics.running
        utilization = running_tasks / self.current_concurrent if self.current_concurrent > 0 else 0

        # Determine adjustment direction
        adjustment = 0

        # Rule 1: If completion rate is below target and utilization is low, increase concurrency
        if (completion_rate < self.tuning_config.target_completion_rate and
            utilization < self.tuning_config.low_utilization_threshold):
            adjustment = min(
                self.tuning_config.max_adjustment_step,
                self.tuning_config.max_concurrent - self.current_concurrent
            )

        # Rule 2: If utilization is very high and completion rate is dropping, decrease concurrency
        elif (utilization > self.tuning_config.high_utilization_threshold and
              self._is_completion_rate_declining()):
            adjustment = max(
                -self.tuning_config.max_adjustment_step,
                self.tuning_config.min_concurrent - self.current_concurrent
            )

        # Rule 3: If we're at max concurrency but completion rate is still low, check for bottlenecks
        elif (self.current_concurrent >= self.tuning_config.max_concurrent and
              completion_rate < self.tuning_config.target_completion_rate * 0.5):
            # Could indicate system bottlenecks beyond concurrency
            # For now, we'll not adjust
            pass

        # Apply adjustment if needed
        if adjustment != 0:
            new_concurrent = self.current_concurrent + adjustment
            new_concurrent = max(
                self.tuning_config.min_concurrent,
                min(self.tuning_config.max_concurrent, new_concurrent)
            )

            # Only adjust if it's a meaningful change
            if new_concurrent != self.current_concurrent:
                self.last_adjustment_time = current_time
                self.is_cooldown = True
                self.cooldown_until = current_time + self.tuning_config.cooldown_period
                self.adjustment_count += 1

                # Clear history after adjustment to get fresh data
                self.completion_times.clear()

                return new_concurrent

        return None

    def _is_completion_rate_declining(self) -> bool:
        """Check if completion rate is declining.

        Returns:
            True if completion rate appears to be declining.
        """
        if len(self.completion_times) < 5:
            return False

        # Split completion times into halves
        half = len(self.completion_times) // 2
        first_half = list(self.completion_times)[:half]
        second_half = list(self.completion_times)[half:]

        if not first_half or not second_half:
            return False

        # Calculate average completion times
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)

        # If recent tasks are taking longer, rate is declining
        return avg_second > avg_first * 1.2  # 20% slower

    def get_adjusted_config(self, new_concurrent: int) -> ExecutionConfig:
        """Get a new ExecutionConfig with adjusted concurrency.

        Args:
            new_concurrent: New concurrency level.

        Returns:
            Updated execution configuration.
        """
        # Create new config with updated concurrency
        config_dict = self.initial_config.__dict__.copy()
        config_dict["max_concurrent"] = new_concurrent

        # Update current concurrency
        self.current_concurrent = new_concurrent

        return ExecutionConfig(**config_dict)

    def get_stats(self) -> dict:
        """Get controller statistics.

        Returns:
            Dictionary of controller statistics.
        """
        completion_rate = 0.0
        if self.completion_times:
            avg_time = sum(self.completion_times) / len(self.completion_times)
            completion_rate = 1.0 / avg_time if avg_time > 0 else 0.0

        utilization = len(self.task_start_times) / self.current_concurrent if self.current_concurrent > 0 else 0

        return {
            "current_concurrency": self.current_concurrent,
            "adjustment_count": self.adjustment_count,
            "total_tasks_completed": self.total_tasks_completed,
            "completion_rate": completion_rate,
            "current_utilization": utilization,
            "is_cooldown": self.is_cooldown,
            "cooldown_remaining": max(0.0, self.cooldown_until - time.time()),
        }


class PerformanceOptimizer:
    """Optimizes execution performance based on historical data."""

    def __init__(self, db_path: str = "omni_executions.db") -> None:
        """Initialize the performance optimizer.

        Args:
            db_path: Path to SQLite database with execution history.
        """
        self.db_path = db_path

    def analyze_historical_patterns(self) -> dict:
        """Analyze historical execution patterns.

        Returns:
            Dictionary of optimization recommendations.
        """
        # TODO: Implement database querying and pattern analysis
        # For now, return placeholder recommendations

        recommendations = {
            "optimal_concurrency": 8,
            "suggested_timeout": 180.0,
            "retry_strategy": "exponential_backoff",
            "bottleneck_tasks": [],
            "common_failure_patterns": [],
        }

        return recommendations

    def suggest_config_optimizations(
        self,
        task_graph_size: int,
        avg_task_complexity: float,
    ) -> ExecutionConfig:
        """Suggest optimized configuration based on task characteristics.

        Args:
            task_graph_size: Number of tasks in the graph.
            avg_task_complexity: Average complexity score (0-10).

        Returns:
            Suggested execution configuration.
        """
        # Determine concurrency based on graph size
        if task_graph_size < 5:
            max_concurrent = 2
        elif task_graph_size < 20:
            max_concurrent = 5
        elif task_graph_size < 100:
            max_concurrent = 10
        else:
            max_concurrent = 20

        # Determine timeout based on complexity
        if avg_task_complexity > 8:
            timeout_per_task = 600.0  # 10 minutes for complex tasks
        elif avg_task_complexity > 5:
            timeout_per_task = 300.0  # 5 minutes for medium tasks
        else:
            timeout_per_task = 120.0  # 2 minutes for simple tasks

        # Determine retry strategy
        retry_enabled = True
        if avg_task_complexity > 7:
            backoff_base = 5.0  # Longer backoff for complex tasks
        else:
            backoff_base = 2.0

        # Create new config with optimized values
        return ExecutionConfig(
            max_concurrent=max_concurrent,
            timeout_per_task=timeout_per_task,
            retry_enabled=retry_enabled,
            backoff_base=backoff_base,
        )

    def generate_optimization_report(self) -> str:
        """Generate optimization report based on historical data.

        Returns:
            Optimization report as string.
        """
        patterns = self.analyze_historical_patterns()

        report = []
        report.append("=" * 60)
        report.append("PERFORMANCE OPTIMIZATION REPORT")
        report.append("=" * 60)
        report.append("")

        report.append("📈 HISTORICAL ANALYSIS")
        report.append(f"  Optimal Concurrency: {patterns.get('optimal_concurrency', 'N/A')}")
        report.append(f"  Suggested Timeout: {patterns.get('suggested_timeout', 'N/A')}s")
        report.append("")

        if patterns.get("bottleneck_tasks"):
            report.append("⚠️  COMMON BOTTLENECKS")
            for task_id in patterns["bottleneck_tasks"][:5]:
                report.append(f"  • {task_id}")
            report.append("")

        if patterns.get("common_failure_patterns"):
            report.append("❌ COMMON FAILURE PATTERNS")
            for pattern in patterns["common_failure_patterns"][:3]:
                report.append(f"  • {pattern}")
            report.append("")

        report.append("💡 OPTIMIZATION SUGGESTIONS")
        report.append("  1. Use adaptive concurrency for dynamic workloads")
        report.append("  2. Monitor completion rate and adjust concurrency accordingly")
        report.append("  3. Set appropriate timeouts based on task complexity")
        report.append("  4. Review bottleneck tasks for potential optimization")
        report.append("")

        report.append("=" * 60)

        return "\n".join(report)


def create_adaptive_callback(
    controller: AdaptiveConcurrencyController,
    on_config_update: Callable[[ExecutionConfig], None],
) -> Callable[[ExecutionMetrics], None]:
    """Create a callback function for adaptive concurrency control.

    Args:
        controller: Adaptive concurrency controller.
        on_config_update: Function to call when config needs update.

    Returns:
        Callback function for ExecutionCallbacks.on_progress.
    """
    def callback(metrics: ExecutionMetrics) -> None:
        adjustment = controller.calculate_adjustment(metrics)
        if adjustment is not None:
            new_config = controller.get_adjusted_config(adjustment)
            on_config_update(new_config)

    return callback
