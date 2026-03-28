"""
Parallelism Metrics and Analytics for Execution Engine.

Computes parallel efficiency, bottleneck detection, cost/time metrics,
and provides performance tuning recommendations.
"""

import statistics
from dataclasses import dataclass
from datetime import datetime

from ..execution.models import ExecutionMetrics, ExecutionResult
from ..task.models import TaskGraph


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics for an execution."""

    # Basic metrics
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    skipped_tasks: int

    # Timing metrics
    wall_clock_time: float  # seconds
    total_task_time: float  # sum of individual task durations
    critical_path_length: float  # longest dependency chain

    # Parallelism metrics
    max_concurrent_tasks: int
    average_concurrency: float
    parallel_efficiency: float  # actual_speedup / theoretical_max_speedup
    cpu_utilization: float  # percentage of time CPU was busy

    # Cost metrics
    total_tokens: int
    total_cost: float
    cost_per_task: float
    tokens_per_task: float

    # Quality metrics
    success_rate: float
    retry_rate: float  # percentage of tasks that required retries

    # Bottleneck analysis
    bottleneck_tasks: list[str]  # task IDs that were bottlenecks
    longest_tasks: list[tuple[str, float]]  # (task_id, duration)
    dependency_chains: list[list[str]]  # critical paths

    # Recommendations
    recommendations: list[str]


class MetricsAnalyzer:
    """Analyzes execution metrics and provides insights."""

    def __init__(self, task_graph: TaskGraph) -> None:
        """Initialize the metrics analyzer.

        Args:
            task_graph: The task graph being analyzed.
        """
        self.task_graph = task_graph
        self.task_durations: dict[str, float] = {}
        self.task_start_times: dict[str, datetime] = {}
        self.task_end_times: dict[str, datetime] = {}

    def record_task_start(self, task_id: str, timestamp: datetime) -> None:
        """Record when a task started.

        Args:
            task_id: ID of the task.
            timestamp: Start time.
        """
        self.task_start_times[task_id] = timestamp

    def record_task_end(self, task_id: str, timestamp: datetime) -> None:
        """Record when a task ended.

        Args:
            task_id: ID of the task.
            timestamp: End time.
        """
        self.task_end_times[task_id] = timestamp

        # Calculate duration
        if task_id in self.task_start_times:
            start = self.task_start_times[task_id]
            duration = (timestamp - start).total_seconds()
            self.task_durations[task_id] = duration

    def analyze_execution(self, result: ExecutionResult) -> PerformanceMetrics:
        """Analyze an execution result and compute performance metrics.

        Args:
            result: Execution result to analyze.

        Returns:
            Comprehensive performance metrics.
        """
        # Basic metrics
        total_tasks = result.metrics.total_tasks
        completed_tasks = result.metrics.completed
        failed_tasks = result.metrics.failed
        skipped_tasks = result.metrics.skipped

        # Timing metrics
        wall_clock_time = result.metrics.wall_clock_seconds

        # Calculate total task time and critical path
        total_task_time = sum(self.task_durations.values())
        critical_path_length = self._calculate_critical_path_length()

        # Parallelism metrics
        max_concurrent, avg_concurrency = self._calculate_concurrency()
        parallel_efficiency = self._calculate_parallel_efficiency(
            wall_clock_time, critical_path_length
        )
        cpu_utilization = total_task_time / (wall_clock_time * max_concurrent) if max_concurrent > 0 else 0

        # Cost metrics
        total_tokens = result.metrics.total_tokens_used
        total_cost = result.metrics.total_cost
        cost_per_task = total_cost / completed_tasks if completed_tasks > 0 else 0
        tokens_per_task = total_tokens / completed_tasks if completed_tasks > 0 else 0

        # Quality metrics
        success_rate = completed_tasks / total_tasks if total_tasks > 0 else 0

        # Calculate retry rate (simplified - would need retry count per task)
        retry_rate = 0.0  # TODO: Track retries

        # Bottleneck analysis
        bottleneck_tasks = self._identify_bottlenecks()
        longest_tasks = self._identify_longest_tasks()
        dependency_chains = self._find_critical_paths()

        # Generate recommendations
        recommendations = self._generate_recommendations(
            parallel_efficiency,
            cpu_utilization,
            success_rate,
            bottleneck_tasks,
        )

        return PerformanceMetrics(
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            skipped_tasks=skipped_tasks,
            wall_clock_time=wall_clock_time,
            total_task_time=total_task_time,
            critical_path_length=critical_path_length,
            max_concurrent_tasks=max_concurrent,
            average_concurrency=avg_concurrency,
            parallel_efficiency=parallel_efficiency,
            cpu_utilization=cpu_utilization,
            total_tokens=total_tokens,
            total_cost=total_cost,
            cost_per_task=cost_per_task,
            tokens_per_task=tokens_per_task,
            success_rate=success_rate,
            retry_rate=retry_rate,
            bottleneck_tasks=bottleneck_tasks,
            longest_tasks=longest_tasks,
            dependency_chains=dependency_chains,
            recommendations=recommendations,
        )

    def _calculate_critical_path_length(self) -> float:
        """Calculate the length of the critical path (longest dependency chain).

        Returns:
            Length of critical path in seconds.
        """
        if not self.task_durations:
            return 0.0

        # Use topological sort and dynamic programming to find longest path
        # Build adjacency list for dependencies
        adj: dict[str, list[str]] = {task_id: [] for task_id in self.task_graph.tasks}
        for task_id, task in self.task_graph.tasks.items():
            for dep in task.dependencies:
                if dep in adj:
                    adj[dep].append(task_id)  # dep -> task (task depends on dep)

        # Topological sort using Kahn's algorithm
        in_degree: dict[str, int] = {}
        for task_id in self.task_graph.tasks:
            in_degree[task_id] = 0

        for _task_id, deps in adj.items():
            for dep in deps:
                in_degree[dep] = in_degree.get(dep, 0) + 1

        # Queue for nodes with no incoming edges
        queue = [task_id for task_id, deg in in_degree.items() if deg == 0]

        # Topological order
        topo_order: list[str] = []
        while queue:
            node = queue.pop(0)
            topo_order.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Dynamic programming for longest path
        dist: dict[str, float] = dict.fromkeys(self.task_graph.tasks, 0.0)

        # Process in topological order
        for node in topo_order:
            # Update distances to neighbors
            for neighbor in adj[node]:
                # Duration of node -> edge weight
                duration = self.task_durations.get(node, 0.0)
                if dist[node] + duration > dist[neighbor]:
                    dist[neighbor] = dist[node] + duration

        # Add the duration of the last node in each path
        max_length = 0.0
        for node in self.task_graph.tasks:
            duration = self.task_durations.get(node, 0.0)
            max_length = max(max_length, dist[node] + duration)

        return max_length

    def _calculate_concurrency(self) -> tuple[int, float]:
        """Calculate maximum and average concurrency.

        Returns:
            Tuple of (max_concurrent, average_concurrency).
        """
        # Simplified implementation
        # In a real implementation, this would analyze task overlap

        if not self.task_start_times or not self.task_end_times:
            return 0, 0.0

        # Create timeline of events
        events = []
        for _task_id, start_time in self.task_start_times.items():
            events.append((start_time, 1))  # Task started

        for _task_id, end_time in self.task_end_times.items():
            events.append((end_time, -1))  # Task ended

        # Sort events by time
        events.sort(key=lambda x: x[0])

        # Calculate concurrency over time
        current_concurrency = 0
        max_concurrency = 0
        concurrency_samples = []

        for _time, delta in events:
            current_concurrency += delta
            max_concurrency = max(max_concurrency, current_concurrency)
            concurrency_samples.append(current_concurrency)

        avg_concurrency = statistics.mean(concurrency_samples) if concurrency_samples else 0

        return max_concurrency, avg_concurrency

    def _calculate_parallel_efficiency(
        self,
        wall_clock_time: float,
        critical_path_length: float,
    ) -> float:
        """Calculate parallel efficiency.

        Args:
            wall_clock_time: Total execution time.
            critical_path_length: Length of critical path.

        Returns:
            Parallel efficiency (0.0 to 1.0).
        """
        if wall_clock_time <= 0 or critical_path_length <= 0:
            return 0.0

        # Theoretical speedup if perfectly parallel
        total_task_time = sum(self.task_durations.values())
        if total_task_time <= 0:
            return 0.0

        theoretical_min_time = critical_path_length
        actual_speedup = total_task_time / wall_clock_time
        theoretical_max_speedup = total_task_time / theoretical_min_time

        if theoretical_max_speedup <= 0:
            return 0.0

        efficiency = actual_speedup / theoretical_max_speedup
        return min(1.0, max(0.0, efficiency))

    def _identify_bottlenecks(self) -> list[str]:
        """Identify tasks that were bottlenecks.

        Returns:
            List of task IDs that were bottlenecks.
        """
        bottlenecks = []

        for task_id, duration in self.task_durations.items():
            task = self.task_graph.tasks.get(task_id)
            if not task:
                continue

            # Check if this task has many dependents
            dependents = [
                t for t in self.task_graph.tasks.values()
                if task_id in t.dependencies
            ]

            # Long task with many dependents is likely a bottleneck
            if duration > 10.0 and len(dependents) > 2:  # Thresholds
                bottlenecks.append(task_id)

        return bottlenecks

    def _identify_longest_tasks(self) -> list[tuple[str, float]]:
        """Identify the longest-running tasks.

        Returns:
            List of (task_id, duration) tuples, sorted by duration.
        """
        tasks = list(self.task_durations.items())
        tasks.sort(key=lambda x: x[1], reverse=True)
        return tasks[:10]  # Top 10 longest tasks

    def _find_critical_paths(self) -> list[list[str]]:
        """Find critical paths in the task graph.

        Returns:
            List of critical paths (lists of task IDs).
        """
        # Simplified implementation
        # In a real implementation, this would use topological sort
        # and longest path algorithm

        paths = []

        # Find root tasks (no dependencies)
        root_tasks = [
            task_id for task_id, task in self.task_graph.tasks.items()
            if not task.dependencies
        ]

        # For each root, find longest path
        for root in root_tasks:
            path = self._find_longest_path_from(root)
            if path:
                paths.append(path)

        return paths

    def _find_longest_path_from(self, start_task: str) -> list[str]:
        """Find longest path starting from a task.

        Args:
            start_task: Starting task ID.

        Returns:
            Longest path as list of task IDs.
        """
        # Depth-first search to find longest path
        def dfs(current: str, path: list[str], visited: set) -> list[str]:
            visited.add(current)
            path.append(current)

            longest_path = path.copy()

            # Find dependents
            dependents = [
                task_id for task_id, task in self.task_graph.tasks.items()
                if current in task.dependencies
            ]

            for dependent in dependents:
                if dependent not in visited:
                    candidate_path = dfs(dependent, path.copy(), visited.copy())
                    if len(candidate_path) > len(longest_path):
                        longest_path = candidate_path

            return longest_path

        return dfs(start_task, [], set())

    def _generate_recommendations(
        self,
        parallel_efficiency: float,
        cpu_utilization: float,
        success_rate: float,
        bottleneck_tasks: list[str],
    ) -> list[str]:
        """Generate performance tuning recommendations.

        Args:
            parallel_efficiency: Calculated parallel efficiency.
            cpu_utilization: CPU utilization percentage.
            success_rate: Task success rate.
            bottleneck_tasks: List of bottleneck task IDs.

        Returns:
            List of recommendations.
        """
        recommendations = []

        # Parallel efficiency recommendations
        if parallel_efficiency < 0.5:
            recommendations.append(
                "Low parallel efficiency. Consider increasing max_concurrent "
                "or restructuring task dependencies to allow more parallelism."
            )
        elif parallel_efficiency < 0.8:
            recommendations.append(
                "Moderate parallel efficiency. Some tasks may be waiting "
                "for dependencies. Review task graph for optimization."
            )

        # CPU utilization recommendations
        if cpu_utilization < 0.3:
            recommendations.append(
                "Low CPU utilization. Tasks may be I/O-bound. "
                "Consider using async I/O or increasing concurrency."
            )

        # Success rate recommendations
        if success_rate < 0.9:
            recommendations.append(
                f"Low success rate ({success_rate:.1%}). "
                "Review error logs and consider increasing retry limits "
                "or improving error handling."
            )

        # Bottleneck recommendations
        if bottleneck_tasks:
            recommendations.append(
                f"Bottlenecks detected: {', '.join(bottleneck_tasks[:3])}. "
                "Consider breaking these tasks into smaller subtasks "
                "or optimizing their execution."
            )

        # General recommendations
        if not recommendations:
            recommendations.append(
                "Performance is good. Consider fine-tuning configuration "
                "for specific use cases."
            )

        return recommendations


def calculate_parallel_efficiency_from_metrics(
    metrics: ExecutionMetrics,
    task_durations: dict[str, float],
    critical_path_length: float,
) -> float:
    """Calculate parallel efficiency from basic metrics.

    Args:
        metrics: Execution metrics.
        task_durations: Dictionary of task_id -> duration.
        critical_path_length: Length of critical path.

    Returns:
        Parallel efficiency.
    """
    if metrics.wall_clock_seconds <= 0 or critical_path_length <= 0:
        return 0.0

    total_task_time = sum(task_durations.values())
    if total_task_time <= 0:
        return 0.0

    theoretical_min_time = critical_path_length
    actual_speedup = total_task_time / metrics.wall_clock_seconds
    theoretical_max_speedup = total_task_time / theoretical_min_time

    if theoretical_max_speedup <= 0:
        return 0.0

    efficiency = actual_speedup / theoretical_max_speedup
    return min(1.0, max(0.0, efficiency))


def generate_performance_report(
    result: ExecutionResult,
    analyzer: MetricsAnalyzer,
) -> str:
    """Generate a human-readable performance report.

    Args:
        result: Execution result.
        analyzer: Metrics analyzer.

    Returns:
        Performance report as string.
    """
    metrics = analyzer.analyze_execution(result)

    report = []
    report.append("=" * 60)
    report.append("PERFORMANCE REPORT")
    report.append("=" * 60)
    report.append("")

    # Summary
    report.append("📊 EXECUTION SUMMARY")
    report.append(f"  Tasks: {metrics.total_tasks} total, "
                 f"{metrics.completed_tasks} completed, "
                 f"{metrics.failed_tasks} failed, "
                 f"{metrics.skipped_tasks} skipped")
    report.append(f"  Time: {metrics.wall_clock_time:.1f}s wall clock, "
                 f"{metrics.total_task_time:.1f}s total task time")
    report.append(f"  Cost: ${metrics.total_cost:.4f}, "
                 f"{metrics.total_tokens:,} tokens")
    report.append("")

    # Parallelism Analysis
    report.append("⚡ PARALLELISM ANALYSIS")
    report.append(f"  Max Concurrent Tasks: {metrics.max_concurrent_tasks}")
    report.append(f"  Average Concurrency: {metrics.average_concurrency:.1f}")
    report.append(f"  Parallel Efficiency: {metrics.parallel_efficiency:.1%}")
    report.append(f"  CPU Utilization: {metrics.cpu_utilization:.1%}")
    report.append(f"  Critical Path Length: {metrics.critical_path_length:.1f}s")
    report.append("")

    # Bottleneck Analysis
    if metrics.bottleneck_tasks:
        report.append("⚠️  BOTTLENECKS DETECTED")
        for task_id in metrics.bottleneck_tasks[:5]:
            duration = next(
                (d for tid, d in metrics.longest_tasks if tid == task_id),
                0.0
            )
            report.append(f"  • {task_id}: {duration:.1f}s")
        report.append("")

    # Longest Tasks
    if metrics.longest_tasks:
        report.append("⏱️  LONGEST TASKS")
        for task_id, duration in metrics.longest_tasks[:5]:
            report.append(f"  • {task_id}: {duration:.1f}s")
        report.append("")

    # Recommendations
    if metrics.recommendations:
        report.append("💡 RECOMMENDATIONS")
        for i, rec in enumerate(metrics.recommendations, 1):
            report.append(f"  {i}. {rec}")
        report.append("")

    report.append("=" * 60)

    return "\n".join(report)
