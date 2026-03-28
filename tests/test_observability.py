"""
Tests for Observability & Live Visualization module.
"""

import tempfile
from pathlib import Path

import pytest

from omni.observability.dashboard import DashboardConfig, LiveDashboard
from omni.observability.mermaid import MermaidSnapshotConfig, MermaidSnapshotter
from omni.observability.metrics import MetricsAnalyzer
from omni.observability.tuning import AdaptiveConcurrencyController, TuningConfig
from omni.task.models import Task, TaskGraph, TaskStatus, TaskType


@pytest.fixture
def sample_task_graph() -> TaskGraph:
    """Create a sample task graph for testing."""
    graph = TaskGraph(name="Test Graph")

    # Add some tasks
    task1 = Task(
        task_id="task1",
        description="First task",
        task_type=TaskType.CODE_GENERATION,
        dependencies=set(),
        priority=5,
    )

    task2 = Task(
        task_id="task2",
        description="Second task",
        task_type=TaskType.TESTING,
        dependencies={"task1"},
        priority=3,
    )

    task3 = Task(
        task_id="task3",
        description="Third task",
        task_type=TaskType.DOCUMENTATION,
        dependencies={"task1"},
        priority=2,
    )

    graph.add_task(task1)
    graph.add_task(task2)
    graph.add_task(task3)

    return graph


class TestDashboard:
    """Tests for LiveDashboard."""

    def test_dashboard_initialization(self, sample_task_graph):
        """Test dashboard initialization."""
        config = DashboardConfig(refresh_rate=0.1, colors_enabled=False)
        dashboard = LiveDashboard(sample_task_graph, config)

        assert dashboard.task_graph == sample_task_graph
        assert dashboard.config.refresh_rate == 0.1
        assert dashboard.config.colors_enabled is False

    def test_dashboard_color_methods(self, sample_task_graph):
        """Test dashboard color methods."""
        dashboard = LiveDashboard(sample_task_graph)

        # Test color application
        colored_text = dashboard._color("red", "error")
        assert "error" in colored_text

        # Test bold
        bold_text = dashboard._bold("important")
        assert "important" in bold_text

    def test_dashboard_status_config(self, sample_task_graph):
        """Test dashboard status configuration."""
        dashboard = LiveDashboard(sample_task_graph)

        # Check status icons and colors are defined
        assert TaskStatus.PENDING in dashboard._status_config
        assert TaskStatus.RUNNING in dashboard._status_config
        assert TaskStatus.COMPLETED in dashboard._status_config
        assert TaskStatus.FAILED in dashboard._status_config


class TestMermaidSnapshotter:
    """Tests for MermaidSnapshotter."""

    def test_snapshotter_initialization(self, sample_task_graph):
        """Test snapshotter initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = MermaidSnapshotConfig(output_dir=tmpdir)
            snapshotter = MermaidSnapshotter(sample_task_graph, config)

            assert snapshotter.task_graph == sample_task_graph
            assert Path(snapshotter.output_dir).exists()

    def test_snapshot_saving(self, sample_task_graph):
        """Test snapshot saving."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = MermaidSnapshotConfig(output_dir=tmpdir)
            snapshotter = MermaidSnapshotter(sample_task_graph, config)

            # Set execution ID
            snapshotter.set_execution_id("test-exec-123")

            # Save a snapshot
            filepath = snapshotter.save_snapshot()

            assert filepath != ""
            assert Path(filepath).exists()
            assert snapshotter.snapshot_count == 1

    def test_json_snapshot_format(self, sample_task_graph):
        """Test JSON snapshot format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = MermaidSnapshotConfig(output_dir=tmpdir, format="json")
            snapshotter = MermaidSnapshotter(sample_task_graph, config)

            filepath = snapshotter.save_snapshot()

            # Check file extension
            assert filepath.endswith(".json")
            assert Path(filepath).exists()


class TestMetricsAnalyzer:
    """Tests for MetricsAnalyzer."""

    def test_analyzer_initialization(self, sample_task_graph):
        """Test metrics analyzer initialization."""
        analyzer = MetricsAnalyzer(sample_task_graph)

        assert analyzer.task_graph == sample_task_graph
        assert analyzer.task_durations == {}
        assert analyzer.task_start_times == {}
        assert analyzer.task_end_times == {}

    def test_task_recording(self, sample_task_graph):
        """Test task start/end recording."""
        analyzer = MetricsAnalyzer(sample_task_graph)

        from datetime import datetime

        start_time = datetime(2024, 1, 1, 10, 0, 0)
        end_time = datetime(2024, 1, 1, 10, 0, 30)

        analyzer.record_task_start("task1", start_time)
        analyzer.record_task_end("task1", end_time)

        assert "task1" in analyzer.task_start_times
        assert "task1" in analyzer.task_end_times
        assert "task1" in analyzer.task_durations
        assert analyzer.task_durations["task1"] == 30.0


class TestAdaptiveConcurrencyController:
    """Tests for AdaptiveConcurrencyController."""

    def test_controller_initialization(self):
        """Test controller initialization."""
        from omni.execution.config import ExecutionConfig

        initial_config = ExecutionConfig(max_concurrent=5)
        tuning_config = TuningConfig(enable_adaptive_concurrency=True)

        controller = AdaptiveConcurrencyController(initial_config, tuning_config)

        assert controller.current_concurrent == 5
        assert controller.tuning_config.enable_adaptive_concurrency is True
        assert controller.adjustment_count == 0

    def test_task_recording(self):
        """Test task start/completion recording."""
        from omni.execution.config import ExecutionConfig

        initial_config = ExecutionConfig(max_concurrent=5)
        controller = AdaptiveConcurrencyController(initial_config)

        controller.record_task_start("task1")
        controller.record_task_completion("task1")

        assert len(controller.completion_times) == 1
        assert controller.total_tasks_completed == 1

    def test_config_adjustment(self):
        """Test configuration adjustment."""
        from omni.execution.config import ExecutionConfig

        initial_config = ExecutionConfig(max_concurrent=5)
        controller = AdaptiveConcurrencyController(initial_config)

        new_config = controller.get_adjusted_config(8)

        assert new_config.max_concurrent == 8
        assert controller.current_concurrent == 8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
