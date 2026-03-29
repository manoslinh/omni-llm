"""
Tests for predictive scheduling components.
"""

import os
import sys
import time

import pytest

# Add the src directory to Python path for direct imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

# Import directly from the predictive module to avoid import chain issues
# with resource_pool.py (which has ResourceBudget import issue being handled separately)
from src.omni.scheduling.predictive import (
    BottleneckDetector,
    DemandForecaster,
    ExecutionRecord,
    WorkloadForecast,
    WorkloadTracker,
)


@pytest.mark.scheduling
class TestExecutionRecord:
    """Tests for ExecutionRecord class."""

    def test_initialization(self):
        record = ExecutionRecord(
            task_id="task1",
            agent_id="coder",
            task_type="coding",
            complexity=5.0,
            duration_seconds=12.5,
            tokens_used=2000,
            cost=0.003,
            success=True,
            workflow_id="wf1",
        )

        assert record.task_id == "task1"
        assert record.agent_id == "coder"
        assert record.task_type == "coding"
        assert record.complexity == 5.0
        assert record.duration_seconds == 12.5
        assert record.tokens_used == 2000
        assert record.cost == 0.003
        assert record.success is True
        assert record.workflow_id == "wf1"
        assert record.completed_at > 0

    def test_default_values(self):
        record = ExecutionRecord(
            task_id="task1",
            agent_id="coder",
            task_type="coding",
            complexity=1.0,
            duration_seconds=10.0,
            tokens_used=1000,
            cost=0.001,
            success=True,
        )

        assert record.workflow_id == ""
        assert record.completed_at > 0


@pytest.mark.scheduling
class TestWorkloadForecast:
    """Tests for WorkloadForecast class."""

    def test_initialization(self):
        forecast = WorkloadForecast(
            forecast_window_seconds=300,
            estimated_tasks=10,
            estimated_concurrent_peak=3,
            estimated_total_tokens=50000,
            estimated_total_cost=0.5,
            estimated_duration_seconds=120.0,
            bottleneck_agents=["coder"],
            confidence=0.8,
            details={"agent_loads": {"coder": 5}},
        )

        assert forecast.forecast_window_seconds == 300
        assert forecast.estimated_tasks == 10
        assert forecast.estimated_concurrent_peak == 3
        assert forecast.estimated_total_tokens == 50000
        assert forecast.estimated_total_cost == 0.5
        assert forecast.estimated_duration_seconds == 120.0
        assert forecast.bottleneck_agents == ["coder"]
        assert forecast.confidence == 0.8
        assert forecast.details == {"agent_loads": {"coder": 5}}


@pytest.mark.scheduling
class TestWorkloadTracker:
    """Tests for WorkloadTracker class."""

    def test_initialization(self):
        tracker = WorkloadTracker(window_size=100)
        assert tracker._history.maxlen == 100
        assert len(tracker._history) == 0

    def test_record_execution(self):
        tracker = WorkloadTracker()

        record = ExecutionRecord(
            task_id="task1",
            agent_id="coder",
            task_type="coding",
            complexity=5.0,
            duration_seconds=12.5,
            tokens_used=2000,
            cost=0.003,
            success=True,
        )

        tracker.record(record)

        assert len(tracker._history) == 1
        assert tracker._history[0] == record

        # Check that agent stats were updated
        assert "coder" in tracker._agent_durations
        assert len(tracker._agent_durations["coder"]) == 1
        assert tracker._agent_durations["coder"][0] == 12.5

        assert "coder" in tracker._agent_success_rates
        assert tracker._agent_success_rates["coder"][0] is True

        # Check that type stats were updated
        assert "coding" in tracker._type_durations
        assert tracker._type_durations["coding"][0] == 12.5

    def test_get_agent_avg_duration(self):
        tracker = WorkloadTracker()

        # Record multiple executions for same agent
        for i in range(3):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id="coder",
                task_type="coding",
                complexity=5.0,
                duration_seconds=10.0 + i * 2.0,  # 10, 12, 14
                tokens_used=2000,
                cost=0.003,
                success=True,
            )
            tracker.record(record)

        avg_duration = tracker.get_agent_avg_duration("coder")
        assert avg_duration == 12.0  # (10 + 12 + 14) / 3

    def test_get_agent_avg_duration_no_data(self):
        tracker = WorkloadTracker()
        assert tracker.get_agent_avg_duration("nonexistent") is None

    def test_get_agent_success_rate(self):
        tracker = WorkloadTracker()

        # Record 3 successes and 1 failure
        for i in range(3):
            record = ExecutionRecord(
                task_id=f"task_success{i}",
                agent_id="coder",
                task_type="coding",
                complexity=5.0,
                duration_seconds=10.0,
                tokens_used=2000,
                cost=0.003,
                success=True,
            )
            tracker.record(record)

        record = ExecutionRecord(
            task_id="task_fail",
            agent_id="coder",
            task_type="coding",
            complexity=5.0,
            duration_seconds=5.0,
            tokens_used=500,
            cost=0.001,
            success=False,
        )
        tracker.record(record)

        success_rate = tracker.get_agent_success_rate("coder")
        assert success_rate == 0.75  # 3 out of 4

    def test_get_type_avg_duration(self):
        tracker = WorkloadTracker()

        # Record multiple executions of same type
        for i in range(3):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id="coder",
                task_type="coding",
                complexity=5.0,
                duration_seconds=8.0 + i * 1.0,  # 8, 9, 10
                tokens_used=2000,
                cost=0.003,
                success=True,
            )
            tracker.record(record)

        avg_duration = tracker.get_type_avg_duration("coding")
        assert avg_duration == 9.0  # (8 + 9 + 10) / 3

    def test_get_avg_cost(self):
        tracker = WorkloadTracker()

        # Record executions with different costs
        costs = [0.001, 0.002, 0.003]
        for i, cost in enumerate(costs):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id="coder",
                task_type="coding",
                complexity=5.0,
                duration_seconds=10.0,
                tokens_used=2000,
                cost=cost,
                success=True,
            )
            tracker.record(record)

        avg_cost = tracker.get_avg_cost()
        assert avg_cost == 0.002  # (0.001 + 0.002 + 0.003) / 3

    def test_get_avg_cost_no_data(self):
        tracker = WorkloadTracker()
        assert tracker.get_avg_cost() is None

    def test_get_throughput(self):
        tracker = WorkloadTracker()
        now = time.time()

        # Record executions within last 100 seconds
        for i in range(5):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id="coder",
                task_type="coding",
                complexity=5.0,
                duration_seconds=10.0,
                tokens_used=2000,
                cost=0.003,
                success=True,
                completed_at=now - i * 20,  # 0, 20, 40, 60, 80 seconds ago
            )
            tracker.record(record)

        # Throughput over last 100 seconds should be 5/100 = 0.05 tasks/sec
        throughput = tracker.get_throughput(100)
        assert throughput == 0.05

        # Throughput over last 50 seconds should be 3/50 = 0.06 tasks/sec
        # (tasks completed 0, 20, 40 seconds ago)
        throughput = tracker.get_throughput(50)
        assert throughput == 0.06


@pytest.mark.scheduling
class TestDemandForecaster:
    """Tests for DemandForecaster class."""

    def test_forecast_empty_pending_tasks(self):
        tracker = WorkloadTracker()
        forecaster = DemandForecaster(tracker)

        forecast = forecaster.forecast([], time_horizon_seconds=300)

        assert forecast.estimated_tasks == 0
        assert forecast.estimated_concurrent_peak == 0
        assert forecast.estimated_total_tokens == 0
        assert forecast.estimated_total_cost == 0.0
        assert forecast.estimated_duration_seconds == 0.0
        assert forecast.confidence == 0.0

    def test_forecast_with_history(self):
        tracker = WorkloadTracker()

        # Add some history
        for i in range(10):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id="coder",
                task_type="coding",
                complexity=5.0,
                duration_seconds=15.0,
                tokens_used=2000,
                cost=0.003,
                success=True,
            )
            tracker.record(record)

        forecaster = DemandForecaster(tracker)

        # Forecast for 5 pending tasks
        pending_tasks = [
            {"agent_id": "coder", "task_type": "coding", "complexity": 5.0},
            {"agent_id": "coder", "task_type": "coding", "complexity": 5.0},
            {"agent_id": "intern", "task_type": "formatting", "complexity": 2.0},
            {"agent_id": "coder", "task_type": "coding", "complexity": 5.0},
            {"agent_id": "intern", "task_type": "formatting", "complexity": 2.0},
        ]

        forecast = forecaster.forecast(pending_tasks, time_horizon_seconds=300)

        assert forecast.estimated_tasks == 5
        assert 1 <= forecast.estimated_concurrent_peak <= 5
        assert forecast.estimated_total_cost > 0
        assert forecast.estimated_total_tokens > 0
        assert forecast.estimated_duration_seconds > 0
        assert forecast.confidence > 0

        # Should detect coder as bottleneck (3 tasks)
        assert "coder" in forecast.bottleneck_agents
        assert forecast.details["agent_loads"]["coder"] == 3
        assert forecast.details["agent_loads"]["intern"] == 2

    def test_forecast_no_history(self):
        tracker = WorkloadTracker()  # Empty tracker
        forecaster = DemandForecaster(tracker)

        pending_tasks = [
            {"agent_id": "coder", "task_type": "coding", "complexity": 5.0},
        ]

        forecast = forecaster.forecast(pending_tasks, time_horizon_seconds=300)

        # Should still produce forecast with default values
        assert forecast.estimated_tasks == 1
        assert forecast.estimated_concurrent_peak == 1
        assert forecast.estimated_total_cost > 0
        assert forecast.confidence == 0.0  # No history = low confidence


@pytest.mark.scheduling
class TestBottleneckDetector:
    """Tests for BottleneckDetector class."""

    def test_initialization(self):
        tracker = WorkloadTracker()
        detector = BottleneckDetector(tracker)

        assert detector.tracker == tracker
        assert detector._queue_depths.maxlen == 60

    def test_sample_queue_depth(self):
        tracker = WorkloadTracker()
        detector = BottleneckDetector(tracker)

        detector.sample_queue_depth(5)
        detector.sample_queue_depth(10)
        detector.sample_queue_depth(15)

        assert list(detector._queue_depths) == [5, 10, 15]

    def test_detect_growing_queue(self):
        tracker = WorkloadTracker()
        detector = BottleneckDetector(tracker)

        # Simulate growing queue
        for depth in [5, 8, 12, 15, 20]:
            detector.sample_queue_depth(depth)

        report = detector.detect()

        assert report["has_bottleneck"] is True
        assert len(report["bottlenecks"]) == 1
        assert report["bottlenecks"][0]["type"] == "growing_queue"
        assert "Increase max_concurrent" in report["suggestions"][0]

    def test_detect_stable_queue(self):
        tracker = WorkloadTracker()
        detector = BottleneckDetector(tracker)

        # Simulate stable queue
        for depth in [5, 5, 5, 5, 5]:
            detector.sample_queue_depth(depth)

        report = detector.detect()

        # Stable queue is not a bottleneck
        assert report["has_bottleneck"] is False

    def test_detect_low_success_rate(self):
        tracker = WorkloadTracker()

        # Add agent with low success rate
        for i in range(5):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id="problematic_agent",
                task_type="coding",
                complexity=5.0,
                duration_seconds=10.0,
                tokens_used=2000,
                cost=0.003,
                success=(i < 2),  # 2 successes out of 5 = 40% success rate
            )
            tracker.record(record)

        detector = BottleneckDetector(tracker)
        report = detector.detect()

        assert report["has_bottleneck"] is True
        assert any(b["type"] == "low_success_rate" for b in report["bottlenecks"])
        assert any("problematic_agent" in b.get("agent_id", "") for b in report["bottlenecks"])

    def test_detect_declining_throughput(self):
        tracker = WorkloadTracker()
        now = time.time()

        # Add many old executions (high throughput period) - within last 5 minutes
        # We need tasks completed between 60-300 seconds ago for 5-minute window
        for i in range(30):  # 30 tasks over 240 seconds = 0.125 tasks/sec
            record = ExecutionRecord(
                task_id=f"task_old{i}",
                agent_id="coder",
                task_type="coding",
                complexity=5.0,
                duration_seconds=10.0,
                tokens_used=2000,
                cost=0.003,
                success=True,
                completed_at=now - 120 - i * 8,  # 120-348 seconds ago
            )
            tracker.record(record)

        # Add very few recent executions (low throughput period) - within last minute
        for i in range(2):  # 2 tasks over 60 seconds = 0.033 tasks/sec
            record = ExecutionRecord(
                task_id=f"task_recent{i}",
                agent_id="coder",
                task_type="coding",
                complexity=5.0,
                duration_seconds=10.0,
                tokens_used=2000,
                cost=0.003,
                success=True,
                completed_at=now - i * 30,  # 0-30 seconds ago
            )
            tracker.record(record)

        detector = BottleneckDetector(tracker)
        report = detector.detect()

        # Should detect declining throughput
        # 5-minute throughput: ~30/300 = 0.1 tasks/sec (actually more since some are outside 5 min)
        # 1-minute throughput: ~2/60 = 0.033 tasks/sec
        # 0.033 < 0.1 * 0.5 = 0.05, so should trigger detection
        assert report["has_bottleneck"] is True
        assert any(b["type"] == "declining_throughput" for b in report["bottlenecks"])
        assert "Check for agent failures" in report["suggestions"][0]

    def test_detect_no_bottlenecks(self):
        tracker = WorkloadTracker()

        # Add some successful history
        for i in range(5):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id="coder",
                task_type="coding",
                complexity=5.0,
                duration_seconds=10.0,
                tokens_used=2000,
                cost=0.003,
                success=True,
            )
            tracker.record(record)

        detector = BottleneckDetector(tracker)

        # Sample stable queue
        for _ in range(5):
            detector.sample_queue_depth(3)

        report = detector.detect()

        # With good success rates and stable queue, no bottlenecks
        assert report["has_bottleneck"] is False
        assert report["bottlenecks"] == []
        assert report["suggestions"] == []
