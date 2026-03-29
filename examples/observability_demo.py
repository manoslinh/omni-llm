#!/usr/bin/env python3
"""
Demonstration of P2-13 Observability & Live Visualization features.

This script shows how to use the new observability features:
1. Live ASCII Dashboard
2. Mermaid Snapshots
3. Execution Replay
4. Performance Metrics
5. Adaptive Concurrency
"""

import asyncio
import tempfile
from pathlib import Path

from omni.execution.config import ExecutionConfig
from omni.execution.models import ExecutionMetrics
from omni.observability.dashboard import DashboardConfig, LiveDashboard
from omni.observability.mermaid import MermaidSnapshotConfig, MermaidSnapshotter
from omni.observability.metrics import MetricsAnalyzer
from omni.observability.tuning import AdaptiveConcurrencyController, TuningConfig
from omni.task.models import Task, TaskGraph, TaskStatus, TaskType


def create_sample_task_graph() -> TaskGraph:
    """Create a sample task graph for demonstration."""
    graph = TaskGraph(name="Observability Demo Graph")

    # Create tasks
    tasks = [
        Task(
            task_id="analyze",
            description="Analyze requirements",
            task_type=TaskType.ANALYSIS,
            dependencies=set(),
            priority=5,
        ),
        Task(
            task_id="design",
            description="Design solution",
            task_type=TaskType.DESIGN,
            dependencies={"analyze"},
            priority=4,
        ),
        Task(
            task_id="implement",
            description="Implement solution",
            task_type=TaskType.CODE_GENERATION,
            dependencies={"design"},
            priority=3,
        ),
        Task(
            task_id="test",
            description="Test implementation",
            task_type=TaskType.TESTING,
            dependencies={"implement"},
            priority=2,
        ),
        Task(
            task_id="document",
            description="Document solution",
            task_type=TaskType.DOCUMENTATION,
            dependencies={"implement"},
            priority=1,
        ),
    ]

    for task in tasks:
        graph.add_task(task)

    return graph


async def demo_dashboard() -> None:
    """Demonstrate the live ASCII dashboard."""
    print("=" * 60)
    print("DEMO 1: Live ASCII Dashboard")
    print("=" * 60)

    graph = create_sample_task_graph()

    # Create dashboard
    config = DashboardConfig(
        refresh_rate=0.5,
        colors_enabled=True,
        show_progress_bars=True,
        show_parallelism=True,
        show_metrics=True,
        show_task_list=True,
    )

    dashboard = LiveDashboard(graph, config)

    # Simulate some execution progress
    print("\nStarting dashboard...")
    dashboard.start()

    # Simulate metrics updates
    for i in range(5):
        metrics = ExecutionMetrics(
            execution_id="demo-exec-123",
            total_tasks=5,
            completed=i,
            failed=0,
            skipped=0,
            running=min(1, 5 - i),
            pending=5 - i - min(1, 5 - i),
            total_tokens_used=i * 1000,
            total_cost=i * 0.01,
            wall_clock_seconds=i * 2.0,
            parallel_efficiency=0.8 if i > 0 else 0.0,
        )

        # Update task statuses
        if i >= 1:
            graph.tasks["analyze"].status = TaskStatus.COMPLETED
        if i >= 2:
            graph.tasks["design"].status = TaskStatus.COMPLETED
        if i >= 3:
            graph.tasks["implement"].status = TaskStatus.RUNNING

        dashboard.update(metrics)
        await asyncio.sleep(1.0)

    dashboard.stop()
    print("\nDashboard demo complete!\n")


def demo_mermaid_snapshots() -> None:
    """Demonstrate Mermaid snapshot generation."""
    print("=" * 60)
    print("DEMO 2: Mermaid Live Snapshots")
    print("=" * 60)

    graph = create_sample_task_graph()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create snapshotter
        config = MermaidSnapshotConfig(
            output_dir=tmpdir,
            save_on_state_change=True,
            format="mermaid",
        )

        snapshotter = MermaidSnapshotter(graph, config)
        snapshotter.set_execution_id("demo-exec-456")

        # Simulate task completion and save snapshots
        print(f"\nSaving snapshots to: {tmpdir}")

        # Initial state
        snapshotter.save_snapshot()
        print("  ✓ Saved initial snapshot")

        # Task 1 completes
        graph.tasks["analyze"].status = TaskStatus.COMPLETED
        snapshotter.save_snapshot()
        print("  ✓ Saved snapshot after task 1 completion")

        # Task 2 completes
        graph.tasks["design"].status = TaskStatus.COMPLETED
        snapshotter.save_snapshot()
        print("  ✓ Saved snapshot after task 2 completion")

        # Show snapshot files
        snapshot_files = list(Path(tmpdir).glob("*.mmd"))
        print(f"\nCreated {len(snapshot_files)} snapshot files:")
        for f in snapshot_files[:3]:  # Show first 3
            print(f"  • {f.name}")

        if len(snapshot_files) > 3:
            print(f"  ... and {len(snapshot_files) - 3} more")

    print("\nMermaid snapshots demo complete!\n")


def demo_metrics_analyzer() -> None:
    """Demonstrate performance metrics analysis."""
    print("=" * 60)
    print("DEMO 3: Performance Metrics & Analytics")
    print("=" * 60)

    graph = create_sample_task_graph()
    analyzer = MetricsAnalyzer(graph)

    # Simulate task execution
    from datetime import datetime, timedelta

    start_time = datetime.now()

    # Record task starts and ends
    analyzer.record_task_start("analyze", start_time)
    analyzer.record_task_end("analyze", start_time + timedelta(seconds=30))

    analyzer.record_task_start("design", start_time + timedelta(seconds=5))
    analyzer.record_task_end("design", start_time + timedelta(seconds=50))

    analyzer.record_task_start("implement", start_time + timedelta(seconds=10))
    # Task still running...

    # Create mock execution result
    from omni.execution.models import ExecutionResult

    result = ExecutionResult(
        execution_id="metrics-demo-789",
        graph_name=graph.name,
        status="RUNNING",
        results={},
        metrics=ExecutionMetrics(
            execution_id="metrics-demo-789",
            total_tasks=5,
            completed=2,
            failed=0,
            skipped=0,
            running=1,
            pending=2,
            total_tokens_used=5000,
            total_cost=0.05,
            wall_clock_seconds=60.0,
            parallel_efficiency=0.75,
        ),
        started_at=start_time,
        completed_at=None,
        dead_letter=[],
        config=None,
    )

    # Generate performance report
    from omni.observability.metrics import generate_performance_report

    report = generate_performance_report(result, analyzer)
    print("\nPerformance Report:")
    print(report)

    print("\nMetrics analysis demo complete!\n")


def demo_adaptive_concurrency() -> None:
    """Demonstrate adaptive concurrency control."""
    print("=" * 60)
    print("DEMO 4: Adaptive Concurrency Control")
    print("=" * 60)

    # Create initial config
    initial_config = ExecutionConfig(max_concurrent=3)

    # Create controller
    tuning_config = TuningConfig(
        enable_adaptive_concurrency=True,
        min_concurrent=1,
        max_concurrent=10,
        target_completion_rate=2.0,  # 2 tasks per second
    )

    controller = AdaptiveConcurrencyController(initial_config, tuning_config)

    print(f"\nInitial concurrency: {controller.current_concurrent}")

    # Simulate task execution
    print("\nSimulating task execution...")

    for i in range(5):
        task_id = f"task_{i}"
        controller.record_task_start(task_id)

        # Simulate task duration
        import time
        time.sleep(0.5)

        controller.record_task_completion(task_id)

        # Create mock metrics
        metrics = ExecutionMetrics(
            execution_id="adaptive-demo-999",
            total_tasks=10,
            completed=i + 1,
            failed=0,
            skipped=0,
            running=min(2, 10 - i - 1),
            pending=10 - i - 1 - min(2, 10 - i - 1),
            total_tokens_used=(i + 1) * 1000,
            total_cost=(i + 1) * 0.01,
            wall_clock_seconds=(i + 1) * 0.6,
            parallel_efficiency=0.6,
        )

        # Check if adjustment is needed
        adjustment = controller.calculate_adjustment(metrics)
        if adjustment is not None:
            controller.get_adjusted_config(adjustment)
            print(f"  ⚡ Adjusted concurrency from {controller.current_concurrent - (adjustment - controller.current_concurrent)} to {controller.current_concurrent}")

    # Show final stats
    stats = controller.get_stats()
    print(f"\nFinal concurrency: {stats['current_concurrency']}")
    print(f"Total adjustments: {stats['adjustment_count']}")
    print(f"Tasks completed: {stats['total_tasks_completed']}")
    print(f"Completion rate: {stats['completion_rate']:.2f} tasks/s")

    print("\nAdaptive concurrency demo complete!\n")


def demo_cli_integration() -> None:
    """Demonstrate CLI integration."""
    print("=" * 60)
    print("DEMO 5: CLI Integration")
    print("=" * 60)

    print("\nNew CLI commands available:")
    print("""
  omni execute run graph.json          # Execute task graph with live dashboard
  omni execute replay <execution_id>   # Replay past execution
  omni execute report <execution_id>   # Generate performance report
  omni execute optimize                # Get optimization suggestions
    """)

    print("Example usage:")
    print("""
  # Execute a task graph with live visualization
  $ omni execute run examples/task_graph.json --concurrent 5 --save-snapshots

  # Replay a past execution
  $ omni execute replay exec_20240328_123456 --speed 2.0

  # Generate performance report
  $ omni execute report exec_20240328_123456 --output report.md

  # Get optimization suggestions
  $ omni execute optimize
    """)

    print("CLI integration demo complete!\n")


async def main() -> None:
    """Run all demos."""
    print("\n" + "=" * 60)
    print("P2-13: Observability & Live Visualization Demo")
    print("=" * 60)

    # Demo 1: Live Dashboard
    await demo_dashboard()

    # Demo 2: Mermaid Snapshots
    demo_mermaid_snapshots()

    # Demo 3: Metrics Analyzer
    demo_metrics_analyzer()

    # Demo 4: Adaptive Concurrency
    demo_adaptive_concurrency()

    # Demo 5: CLI Integration
    demo_cli_integration()

    print("=" * 60)
    print("All demos completed successfully!")
    print("=" * 60)

    print("\n🎉 P2-13 Implementation Complete!")
    print("\nKey Features Implemented:")
    print("  1. ✅ Live ASCII Dashboard - Terminal-based real-time visualization")
    print("  2. ✅ Mermaid Live Updates - Diagram snapshots at state changes")
    print("  3. ✅ Execution Replay - Load and replay past executions")
    print("  4. ✅ Parallelism Metrics - Efficiency calculation and bottleneck detection")
    print("  5. ✅ CLI Integration - `omni execute` command with live dashboard")
    print("  6. ✅ Performance Tuning - Adaptive concurrency control")
    print("\nReady for review and integration!")


if __name__ == "__main__":
    asyncio.run(main())
