"""
Predictive scheduling components for workload forecasting and bottleneck detection.

Provides:
- WorkloadTracker: Sliding window execution history
- DemandForecaster: Moving-average forecasts
- BottleneckDetector: Reactive queue detection

Note: Originally specified in architecture as src/omni/execution/predictive.py,
but implemented in src/omni/scheduling/predictive.py to align with scheduling
module organization. This is a documented deviation from the original spec.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExecutionRecord:
    """Record of a completed task execution for pattern analysis."""
    task_id: str
    agent_id: str
    task_type: str
    complexity: float
    duration_seconds: float
    tokens_used: int
    cost: float
    success: bool
    completed_at: float = field(default_factory=time.time)
    workflow_id: str = ""


@dataclass
class WorkloadForecast:
    """Forecast of expected resource demand."""
    forecast_window_seconds: float
    estimated_tasks: int
    estimated_concurrent_peak: int
    estimated_total_tokens: int
    estimated_total_cost: float
    estimated_duration_seconds: float
    bottleneck_agents: list[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0 to 1.0 — higher with more history
    details: dict[str, Any] = field(default_factory=dict)


class WorkloadTracker:
    """
    Tracks execution history for pattern analysis.

    Maintains a sliding window of recent executions to compute
    statistics for scheduling decisions and forecasting.
    """

    def __init__(self, window_size: int = 500) -> None:
        self._history: deque[ExecutionRecord] = deque(maxlen=window_size)
        # Per-agent stats
        self._agent_durations: dict[str, deque[float]] = {}
        self._agent_success_rates: dict[str, deque[bool]] = {}
        # Per-task-type stats
        self._type_durations: dict[str, deque[float]] = {}

    def record(self, record: ExecutionRecord) -> None:
        """Record a completed task execution."""
        self._history.append(record)

        # Per-agent tracking
        if record.agent_id not in self._agent_durations:
            self._agent_durations[record.agent_id] = deque(maxlen=100)
            self._agent_success_rates[record.agent_id] = deque(maxlen=100)
        self._agent_durations[record.agent_id].append(record.duration_seconds)
        self._agent_success_rates[record.agent_id].append(record.success)

        # Per-type tracking
        if record.task_type not in self._type_durations:
            self._type_durations[record.task_type] = deque(maxlen=100)
        self._type_durations[record.task_type].append(record.duration_seconds)

    def get_agent_avg_duration(self, agent_id: str) -> float | None:
        """Get average execution duration for an agent."""
        durations = self._agent_durations.get(agent_id)
        if not durations:
            return None
        return sum(durations) / len(durations)

    def get_agent_success_rate(self, agent_id: str) -> float | None:
        """Get success rate for an agent (0.0 to 1.0)."""
        successes = self._agent_success_rates.get(agent_id)
        if not successes:
            return None
        return sum(successes) / len(successes)

    def get_type_avg_duration(self, task_type: str) -> float | None:
        """Get average duration for a task type."""
        durations = self._type_durations.get(task_type)
        if not durations:
            return None
        return sum(durations) / len(durations)

    def get_avg_cost(self) -> float | None:
        """Get average task cost across all history."""
        if not self._history:
            return None
        return sum(r.cost for r in self._history) / len(self._history)

    def get_throughput(self, window_seconds: float = 300) -> float:
        """Get tasks completed per second over the recent window."""
        now = time.time()
        recent = [r for r in self._history if now - r.completed_at <= window_seconds]
        if not recent or window_seconds <= 0:
            return 0.0
        return len(recent) / window_seconds

    def get_history_size(self) -> int:
        """Get the number of execution records in history."""
        return len(self._history)

    def clear(self) -> None:
        """Clear all tracking data."""
        self._history.clear()
        self._agent_durations.clear()
        self._agent_success_rates.clear()
        self._type_durations.clear()


class DemandForecaster:
    """
    Forecasts resource demand based on workload patterns.

    Uses moving averages and trend detection — no ML required.
    """

    def __init__(self, tracker: WorkloadTracker) -> None:
        self.tracker = tracker

    def forecast(
        self,
        pending_tasks: list[dict[str, Any]],
        time_horizon_seconds: float = 300,
    ) -> WorkloadForecast:
        """
        Forecast resource demand for pending tasks.

        Args:
            pending_tasks: List of task descriptors with 'agent_id', 'task_type', 'complexity'
            time_horizon_seconds: How far ahead to forecast

        Returns:
            WorkloadForecast with estimates
        """
        if not pending_tasks:
            return WorkloadForecast(
                forecast_window_seconds=time_horizon_seconds,
                estimated_tasks=0,
                estimated_concurrent_peak=0,
                estimated_total_tokens=0,
                estimated_total_cost=0.0,
                estimated_duration_seconds=0.0,
                confidence=0.0,
            )

        total_duration = 0.0
        total_cost = 0.0
        total_tokens = 0
        agent_loads: dict[str, int] = {}

        for task_desc in pending_tasks:
            agent_id = task_desc.get("agent_id", "coder")
            task_type = task_desc.get("task_type", "coding")

            # Estimate duration from history
            agent_dur = self.tracker.get_agent_avg_duration(agent_id)
            type_dur = self.tracker.get_type_avg_duration(task_type)
            if agent_dur is not None:
                est_duration = agent_dur
            elif type_dur is not None:
                est_duration = type_dur
            else:
                est_duration = 30.0  # Default estimate

            total_duration += est_duration

            # Estimate cost
            avg_cost = self.tracker.get_avg_cost()
            total_cost += avg_cost if avg_cost else 0.01

            # Estimate tokens (rough: $0.14/1M → 1000 tokens/$0.00014)
            total_tokens += int(total_cost / 0.00014 * 1000) if total_cost > 0 else 1000

            # Track agent load
            agent_loads[agent_id] = agent_loads.get(agent_id, 0) + 1

        # Peak concurrent estimate: min of task count and typical concurrency
        peak_concurrent = min(len(pending_tasks), 5)

        # Bottleneck agents: those with the most tasks
        sorted_agents = sorted(agent_loads.items(), key=lambda x: -x[1])
        bottlenecks = [a for a, count in sorted_agents if count > 1]

        # Confidence based on history size
        history_size = len(self.tracker._history)
        confidence = min(1.0, history_size / 100)

        return WorkloadForecast(
            forecast_window_seconds=time_horizon_seconds,
            estimated_tasks=len(pending_tasks),
            estimated_concurrent_peak=peak_concurrent,
            estimated_total_tokens=total_tokens,
            estimated_total_cost=round(total_cost, 4),
            estimated_duration_seconds=round(total_duration / peak_concurrent, 1),
            bottleneck_agents=bottlenecks,
            confidence=round(confidence, 2),
            details={
                "agent_loads": agent_loads,
                "avg_task_duration": round(total_duration / len(pending_tasks), 1),
            },
        )


class BottleneckDetector:
    """
    Detects resource bottlenecks in real-time.

    Monitors queue depth, agent utilization, and throughput
    to identify when the system is constrained.
    """

    def __init__(self, tracker: WorkloadTracker) -> None:
        self.tracker = tracker
        self._queue_depths: deque[int] = deque(maxlen=60)  # Last 60 samples

    def sample_queue_depth(self, depth: int) -> None:
        """Record a queue depth sample."""
        self._queue_depths.append(depth)

    def detect(self) -> dict[str, Any]:
        """
        Detect current bottlenecks.

        Returns a report with bottleneck type, severity, and suggestions.
        """
        report: dict[str, Any] = {
            "has_bottleneck": False,
            "bottlenecks": [],
            "suggestions": [],
        }

        # 1. Queue depth growing = scheduling bottleneck
        if len(self._queue_depths) >= 5:
            recent = list(self._queue_depths)[-5:]
            if all(recent[i] < recent[i + 1] for i in range(len(recent) - 1)):
                report["has_bottleneck"] = True
                report["bottlenecks"].append({
                    "type": "growing_queue",
                    "severity": "high" if recent[-1] > 10 else "medium",
                    "detail": f"Queue depth grew from {recent[0]} to {recent[-1]} over last 5 samples",
                })
                report["suggestions"].append("Increase max_concurrent or add more agents")

        # 2. Agent success rates dropping
        for agent_id in list(self.tracker._agent_success_rates.keys())[-5:]:
            rate = self.tracker.get_agent_success_rate(agent_id)
            if rate is not None and rate < 0.5:
                report["has_bottleneck"] = True
                report["bottlenecks"].append({
                    "type": "low_success_rate",
                    "severity": "high",
                    "agent_id": agent_id,
                    "detail": f"Agent {agent_id} success rate: {rate:.0%}",
                })
                report["suggestions"].append(f"Consider escalating tasks from {agent_id}")

        # 3. Throughput declining
        throughput_5m = self.tracker.get_throughput(300)
        throughput_1m = self.tracker.get_throughput(60)
        if throughput_5m > 0 and throughput_1m < throughput_5m * 0.5:
            report["has_bottleneck"] = True
            report["bottlenecks"].append({
                "type": "declining_throughput",
                "severity": "medium",
                "detail": f"Throughput dropped from {throughput_5m:.2f}/s to {throughput_1m:.2f}/s",
            })
            report["suggestions"].append("Check for agent failures or API rate limiting")

        return report

    def get_queue_trend(self) -> str:
        """
        Analyze queue depth trend.

        Returns:
            "growing" if queue depth is consistently increasing
            "shrinking" if queue depth is consistently decreasing
            "stable" otherwise
        """
        if len(self._queue_depths) < 3:
            return "stable"

        # Get last 3 samples
        recent = list(self._queue_depths)[-3:]

        # Check if strictly increasing
        if all(recent[i] < recent[i + 1] for i in range(len(recent) - 1)):
            return "growing"

        # Check if strictly decreasing
        if all(recent[i] > recent[i + 1] for i in range(len(recent) - 1)):
            return "shrinking"

        return "stable"
