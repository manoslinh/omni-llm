"""
Tests for P2-16 Predictive Module.
"""

import time

from src.omni.scheduling.predictive import (
    BottleneckDetector,
    DemandForecaster,
    ExecutionRecord,
    WorkloadTracker,
)


class TestWorkloadTracker:
    """Tests for WorkloadTracker."""

    def test_initialization(self) -> None:
        """Test WorkloadTracker initialization."""
        tracker = WorkloadTracker(window_size=100)
        assert tracker.get_history_size() == 0

    def test_record_execution(self) -> None:
        """Test recording execution records."""
        tracker = WorkloadTracker()

        record = ExecutionRecord(
            task_id="task1",
            agent_id="coder",
            task_type="coding",
            complexity=1.0,
            duration_seconds=30.0,
            tokens_used=1000,
            cost=0.01,
            success=True,
        )

        tracker.record(record)
        assert tracker.get_history_size() == 1

    def test_agent_statistics(self) -> None:
        """Test agent-specific statistics tracking."""
        tracker = WorkloadTracker()

        # Record multiple executions for same agent
        for i in range(3):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id="coder",
                task_type="coding",
                complexity=1.0,
                duration_seconds=20.0 + i * 5.0,  # 20, 25, 30
                tokens_used=1000,
                cost=0.01,
                success=(i != 1),  # Second task fails
            )
            tracker.record(record)

        avg_duration = tracker.get_agent_avg_duration("coder")
        assert avg_duration == 25.0  # (20 + 25 + 30) / 3

        success_rate = tracker.get_agent_success_rate("coder")
        assert success_rate == 2/3  # 2 out of 3 succeeded

    def test_task_type_statistics(self) -> None:
        """Test task type statistics tracking."""
        tracker = WorkloadTracker()

        for i in range(3):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id="coder",
                task_type="coding",
                complexity=1.0,
                duration_seconds=10.0 + i * 5.0,  # 10, 15, 20
                tokens_used=1000,
                cost=0.01,
                success=True,
            )
            tracker.record(record)

        avg_duration = tracker.get_type_avg_duration("coding")
        assert avg_duration == 15.0  # (10 + 15 + 20) / 3

    def test_window_size_limit(self) -> None:
        """Test that window size limits history."""
        tracker = WorkloadTracker(window_size=3)

        for i in range(5):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id="coder",
                task_type="coding",
                complexity=1.0,
                duration_seconds=10.0,
                tokens_used=1000,
                cost=0.01,
                success=True,
            )
            tracker.record(record)

        # Should only keep last 3 records
        assert tracker.get_history_size() == 3

    def test_throughput_calculation(self) -> None:
        """Test throughput calculation."""
        tracker = WorkloadTracker()

        now = time.time()

        # Create records with recent timestamps
        for i in range(5):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id="coder",
                task_type="coding",
                complexity=1.0,
                duration_seconds=10.0,
                tokens_used=1000,
                cost=0.01,
                success=True,
                completed_at=now - i * 10,  # Spread over 40 seconds
            )
            tracker.record(record)

        # Should see 5 tasks in last 300 seconds
        throughput = tracker.get_throughput(300)
        assert throughput == 5 / 300

        # Should see only recent tasks in smaller window
        throughput = tracker.get_throughput(20)
        assert throughput == 2 / 20  # Last 2 tasks within 20 seconds

    def test_clear_history(self) -> None:
        """Test clearing all tracking data."""
        tracker = WorkloadTracker()

        record = ExecutionRecord(
            task_id="task1",
            agent_id="coder",
            task_type="coding",
            complexity=1.0,
            duration_seconds=30.0,
            tokens_used=1000,
            cost=0.01,
            success=True,
        )

        tracker.record(record)
        assert tracker.get_history_size() == 1

        tracker.clear()
        assert tracker.get_history_size() == 0
        assert tracker.get_agent_avg_duration("coder") is None


class TestDemandForecaster:
    """Tests for DemandForecaster."""

    def test_forecast_empty_pending(self) -> None:
        """Test forecasting with no pending tasks."""
        tracker = WorkloadTracker()
        forecaster = DemandForecaster(tracker)

        forecast = forecaster.forecast([])

        assert forecast.estimated_tasks == 0
        assert forecast.estimated_concurrent_peak == 0
        assert forecast.estimated_total_cost == 0.0
        assert forecast.confidence == 0.0

    def test_forecast_with_history(self) -> None:
        """Test forecasting with historical data."""
        tracker = WorkloadTracker()

        # Add some history
        for i in range(10):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id="coder",
                task_type="coding",
                complexity=1.0,
                duration_seconds=25.0,
                tokens_used=1000,
                cost=0.015,
                success=True,
            )
            tracker.record(record)

        forecaster = DemandForecaster(tracker)

        pending_tasks = [
            {"agent_id": "coder", "task_type": "coding", "complexity": 1.0},
            {"agent_id": "coder", "task_type": "coding", "complexity": 1.0},
            {"agent_id": "reviewer", "task_type": "review", "complexity": 0.5},
        ]

        forecast = forecaster.forecast(pending_tasks)

        assert forecast.estimated_tasks == 3
        assert forecast.estimated_concurrent_peak == 3  # min(3, 5)
        assert forecast.bottleneck_agents == ["coder"]  # coder has 2 tasks
        assert forecast.confidence > 0.0  # Should have some confidence with history
        assert "agent_loads" in forecast.details
        assert forecast.details["agent_loads"]["coder"] == 2
        assert forecast.details["agent_loads"]["reviewer"] == 1

    def test_forecast_without_history(self) -> None:
        """Test forecasting without historical data (should use defaults)."""
        tracker = WorkloadTracker()  # Empty tracker
        forecaster = DemandForecaster(tracker)

        pending_tasks = [
            {"agent_id": "coder", "task_type": "coding"},
        ]

        forecast = forecaster.forecast(pending_tasks)

        # Should still produce forecast with default values
        assert forecast.estimated_tasks == 1
        assert forecast.estimated_concurrent_peak == 1
        assert forecast.estimated_duration_seconds == 30.0  # Default estimate
        assert forecast.confidence == 0.0  # No history = no confidence

    def test_confidence_calculation(self) -> None:
        """Test confidence calculation based on history size."""
        tracker = WorkloadTracker()
        forecaster = DemandForecaster(tracker)

        pending_tasks = [{"agent_id": "coder", "task_type": "coding"}]

        # No history
        forecast = forecaster.forecast(pending_tasks)
        assert forecast.confidence == 0.0

        # Some history
        for i in range(50):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id="coder",
                task_type="coding",
                complexity=1.0,
                duration_seconds=25.0,
                tokens_used=1000,
                cost=0.01,
                success=True,
            )
            tracker.record(record)

        forecast = forecaster.forecast(pending_tasks)
        assert forecast.confidence == 0.5  # 50/100

        # Max confidence
        for i in range(50, 150):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id="coder",
                task_type="coding",
                complexity=1.0,
                duration_seconds=25.0,
                tokens_used=1000,
                cost=0.01,
                success=True,
            )
            tracker.record(record)

        forecast = forecaster.forecast(pending_tasks)
        assert forecast.confidence == 1.0  # Capped at 1.0


class TestBottleneckDetector:
    """Tests for BottleneckDetector."""

    def test_queue_growth_detection(self) -> None:
        """Test detection of growing queue."""
        tracker = WorkloadTracker()
        detector = BottleneckDetector(tracker)

        # Simulate growing queue
        detector.sample_queue_depth(2)
        detector.sample_queue_depth(4)
        detector.sample_queue_depth(6)
        detector.sample_queue_depth(8)
        detector.sample_queue_depth(10)

        report = detector.detect()

        assert report["has_bottleneck"] is True
        assert len(report["bottlenecks"]) == 1
        assert report["bottlenecks"][0]["type"] == "growing_queue"
        assert "Queue depth grew from" in report["bottlenecks"][0]["detail"]
        assert "Increase max_concurrent" in report["suggestions"][0]

    def test_no_bottleneck(self) -> None:
        """Test when no bottlenecks exist."""
        tracker = WorkloadTracker()
        detector = BottleneckDetector(tracker)

        # Simulate stable or shrinking queue
        detector.sample_queue_depth(10)
        detector.sample_queue_depth(8)
        detector.sample_queue_depth(6)

        report = detector.detect()

        assert report["has_bottleneck"] is False
        assert len(report["bottlenecks"]) == 0
        assert len(report["suggestions"]) == 0

    def test_low_success_rate_detection(self) -> None:
        """Test detection of low agent success rate."""
        tracker = WorkloadTracker()

        # Record multiple failures for an agent
        for i in range(10):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id="problematic_agent",
                task_type="coding",
                complexity=1.0,
                duration_seconds=10.0,
                tokens_used=1000,
                cost=0.01,
                success=(i < 3),  # Only first 3 succeed
            )
            tracker.record(record)

        detector = BottleneckDetector(tracker)
        report = detector.detect()

        assert report["has_bottleneck"] is True
        assert len(report["bottlenecks"]) == 1
        assert report["bottlenecks"][0]["type"] == "low_success_rate"
        assert report["bottlenecks"][0]["agent_id"] == "problematic_agent"
        assert "Consider escalating tasks" in report["suggestions"][0]

    def test_throughput_decline_detection(self) -> None:
        """Test detection of declining throughput."""
        tracker = WorkloadTracker()
        detector = BottleneckDetector(tracker)

        now = time.time()

        # Create history with high throughput in 5m window
        for i in range(30):  # 30 tasks in last 5 minutes
            record = ExecutionRecord(
                task_id=f"task_5m_{i}",
                agent_id="coder",
                task_type="coding",
                complexity=1.0,
                duration_seconds=10.0,
                tokens_used=1000,
                cost=0.01,
                success=True,
                completed_at=now - 60 - i * 10,  # Spread over 5 minutes
            )
            tracker.record(record)

        # Add fewer tasks in last 1 minute
        for i in range(2):  # Only 2 tasks in last minute
            record = ExecutionRecord(
                task_id=f"task_1m_{i}",
                agent_id="coder",
                task_type="coding",
                complexity=1.0,
                duration_seconds=10.0,
                tokens_used=1000,
                cost=0.01,
                success=True,
                completed_at=now - i * 30,  # Within last minute
            )
            tracker.record(record)

        report = detector.detect()

        # Throughput dropped from 30/300 = 0.1 to 2/60 = 0.033
        # That's more than 50% decline, should trigger detection
        assert report["has_bottleneck"] is True
        assert len(report["bottlenecks"]) == 1
        assert report["bottlenecks"][0]["type"] == "declining_throughput"
        assert "Check for agent failures" in report["suggestions"][0]

    def test_queue_trend_analysis(self) -> None:
        """Test queue trend analysis."""
        tracker = WorkloadTracker()
        detector = BottleneckDetector(tracker)

        # Growing trend
        detector.sample_queue_depth(2)
        detector.sample_queue_depth(4)
        detector.sample_queue_depth(6)
        assert detector.get_queue_trend() == "growing"

        # Shrinking trend
        detector.sample_queue_depth(4)
        detector.sample_queue_depth(2)
        detector.sample_queue_depth(0)
        assert detector.get_queue_trend() == "shrinking"

        # Stable/mixed trend
        detector.sample_queue_depth(2)
        detector.sample_queue_depth(4)
        detector.sample_queue_depth(2)
        assert detector.get_queue_trend() == "stable"


class TestIntegration:
    """Integration tests for the predictive module."""

    def test_workflow_with_all_components(self) -> None:
        """Test integrated workflow of all predictive components."""
        # Create tracker with history
        tracker = WorkloadTracker()

        # Add diverse execution history
        agents = ["coder", "reviewer", "thinker"]
        task_types = ["coding", "review", "analysis"]

        for i in range(20):
            record = ExecutionRecord(
                task_id=f"task{i}",
                agent_id=agents[i % 3],
                task_type=task_types[i % 3],
                complexity=0.5 + (i % 3) * 0.25,
                duration_seconds=20.0 + (i % 5) * 5.0,
                tokens_used=500 + (i % 10) * 100,
                cost=0.005 + (i % 3) * 0.005,
                success=(i % 10 != 0),  # 10% failure rate
            )
            tracker.record(record)

        # Create forecaster and bottleneck detector
        forecaster = DemandForecaster(tracker)
        detector = BottleneckDetector(tracker)

        # Simulate pending tasks
        pending_tasks = [
            {"agent_id": "coder", "task_type": "coding", "complexity": 1.0},
            {"agent_id": "coder", "task_type": "coding", "complexity": 1.0},
            {"agent_id": "reviewer", "task_type": "review", "complexity": 0.8},
            {"agent_id": "thinker", "task_type": "analysis", "complexity": 1.2},
        ]

        # Get forecast
        forecast = forecaster.forecast(pending_tasks)

        assert forecast.estimated_tasks == 4
        assert forecast.estimated_concurrent_peak == 4
        assert "coder" in forecast.bottleneck_agents
        assert forecast.confidence > 0.0

        # Simulate queue growth
        for depth in [2, 4, 6, 8, 10]:
            detector.sample_queue_depth(depth)

        # Detect bottlenecks
        report = detector.detect()

        assert report["has_bottleneck"] is True
        assert len(report["bottlenecks"]) >= 1
        assert len(report["suggestions"]) >= 1

        # Verify all components work together
        assert tracker.get_history_size() == 20
        assert tracker.get_throughput(300) > 0
        assert forecast.details["agent_loads"]["coder"] == 2
