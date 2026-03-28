"""
CLI Integration for Observability Features.

Provides the `omni execute` command and related subcommands for
executing task graphs with live visualization.
"""

import asyncio
import json
import sys
from collections.abc import Callable
from typing import Any

import click

from ..execution.config import ExecutionCallbacks, ExecutionConfig
from ..execution.engine import ParallelExecutionEngine
from ..execution.executor import LLMTaskExecutor, MockTaskExecutor
from ..execution.models import ExecutionMetrics
from ..models.litellm_provider import LiteLLMProvider
from ..router import ModelRouter, RouterConfig
from ..router.provider_registry import ModelProvider
from ..task.models import Task, TaskGraph, TaskType
from .dashboard import DashboardConfig, LiveDashboard
from .mermaid import MermaidSnapshotConfig, MermaidSnapshotter
from .metrics import MetricsAnalyzer, generate_performance_report
from .replay import ExecutionReplayer, ReplayConfig
from .tuning import AdaptiveConcurrencyController, TuningConfig


@click.group(name="execute")
def execute_cli() -> None:
    """Execute task graphs with live visualization and monitoring."""
    pass


@execute_cli.command()
@click.argument("graph_file", type=click.Path(exists=True))
@click.option("--mock", is_flag=True, help="Use mock executor (no API calls)")
@click.option("--concurrent", "-c", type=int, default=5, help="Max concurrent tasks")
@click.option("--timeout", "-t", type=float, default=300.0, help="Per-task timeout (seconds)")
@click.option("--no-dashboard", is_flag=True, help="Disable live dashboard")
@click.option("--save-snapshots", is_flag=True, help="Save Mermaid snapshots")
@click.option("--snapshot-dir", type=click.Path(), default="execution_snapshots", help="Snapshot directory")
@click.option("--adaptive", is_flag=True, help="Enable adaptive concurrency")
@click.option("--output", "-o", type=click.Path(), help="Save results to JSON file")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def run(
    graph_file: str,
    mock: bool,
    concurrent: int,
    timeout: float,
    no_dashboard: bool,
    save_snapshots: bool,
    snapshot_dir: str,
    adaptive: bool,
    output: str | None,
    verbose: bool,
) -> None:
    """Execute a task graph from JSON file."""
    asyncio.run(
        _run_async(
            graph_file=graph_file,
            mock=mock,
            concurrent=concurrent,
            timeout=timeout,
            no_dashboard=no_dashboard,
            save_snapshots=save_snapshots,
            snapshot_dir=snapshot_dir,
            adaptive=adaptive,
            output=output,
            verbose=verbose,
        )
    )


@execute_cli.command()
@click.argument("execution_id")
@click.option("--db", type=click.Path(exists=True), default="omni_executions.db", help="Database path")
@click.option("--speed", type=float, default=1.0, help="Playback speed (1.0 = realtime)")
@click.option("--no-dashboard", is_flag=True, help="Disable live dashboard")
@click.option("--save-snapshots", is_flag=True, help="Save replay snapshots")
@click.option("--export-timeline", type=click.Path(), help="Export timeline to JSON")
@click.option("--pause-on-failure", is_flag=True, help="Pause replay on task failures")
def replay(
    execution_id: str,
    db: str,
    speed: float,
    no_dashboard: bool,
    save_snapshots: bool,
    export_timeline: str | None,
    pause_on_failure: bool,
) -> None:
    """Replay a past execution from database."""
    asyncio.run(
        _replay_async(
            execution_id=execution_id,
            db_path=db,
            speed=speed,
            no_dashboard=no_dashboard,
            save_snapshots=save_snapshots,
            export_timeline=export_timeline,
            pause_on_failure=pause_on_failure,
        )
    )


@execute_cli.command()
@click.argument("execution_id")
@click.option("--db", type=click.Path(exists=True), default="omni_executions.db", help="Database path")
@click.option("--output", "-o", type=click.Path(), help="Save report to file")
def report(
    execution_id: str,
    db: str,
    output: str | None,
) -> None:
    """Generate performance report for a past execution."""
    asyncio.run(
        _report_async(
            execution_id=execution_id,
            db_path=db,
            output=output,
        )
    )


@execute_cli.command()
@click.option("--db", type=click.Path(exists=True), default="omni_executions.db", help="Database path")
def optimize(db: str) -> None:
    """Generate optimization suggestions from historical data."""
    from .tuning import PerformanceOptimizer

    optimizer = PerformanceOptimizer(db)
    report = optimizer.generate_optimization_report()

    click.echo(report)


async def _run_async(
    graph_file: str,
    mock: bool,
    concurrent: int,
    timeout: float,
    no_dashboard: bool,
    save_snapshots: bool,
    snapshot_dir: str,
    adaptive: bool,
    output: str | None,
    verbose: bool,
) -> None:
    """Async implementation of the run command."""
    try:
        # Load task graph
        click.echo(f"📂 Loading task graph from {graph_file}...")
        task_graph = _load_task_graph(graph_file)

        click.echo(f"📊 Graph loaded: {task_graph.size} tasks, {task_graph.edge_count} dependencies")

        # Create executor
        executor: MockTaskExecutor | LLMTaskExecutor
        if mock:
            executor = MockTaskExecutor()
            click.echo("🧪 Using mock executor (no API calls)")
        else:
            # Create router with LiteLLM provider
            provider: ModelProvider = LiteLLMProvider()  # type: ignore[assignment]
            router = ModelRouter(RouterConfig(providers={"litellm": provider}))
            executor = LLMTaskExecutor(router=router)
            click.echo("🚀 Using LLM executor (real API calls)")

        # Create execution config
        config = ExecutionConfig(
            max_concurrent=concurrent,
            timeout_per_task=timeout,
        )

        # Initialize observability components
        dashboard = None
        snapshotter = None
        analyzer = None
        controller = None

        callbacks = ExecutionCallbacks()

        # Setup dashboard
        if not no_dashboard:
            dashboard = LiveDashboard(
                task_graph,
                DashboardConfig(refresh_rate=0.5)
            )
            dashboard.start()
            callbacks.on_progress = _create_dashboard_callback(dashboard)

        # Setup Mermaid snapshots
        if save_snapshots:
            snapshotter = MermaidSnapshotter(
                task_graph,
                MermaidSnapshotConfig(output_dir=snapshot_dir)
            )
            mermaid_callback = _create_mermaid_callback(snapshotter)

            # Combine with existing progress callback
            if callbacks.on_progress:
                original_callback = callbacks.on_progress
                def combined_callback(metrics: ExecutionMetrics) -> None:
                    original_callback(metrics)
                    mermaid_callback(metrics)
                callbacks.on_progress = combined_callback
            else:
                callbacks.on_progress = mermaid_callback

        # Setup metrics analyzer
        analyzer = MetricsAnalyzer(task_graph)

        def on_task_start(task_id: str, task: Any) -> None:
            analyzer.record_task_start(task_id, task)
            if verbose:
                click.echo(f"  ▶ Starting task: {task_id}")

        def on_task_complete(task_id: str, result: Any) -> None:
            analyzer.record_task_end(task_id, result)
            if verbose:
                status = "✓" if result.status == "COMPLETED" else "✗"
                click.echo(f"  {status} Completed task: {task_id}")

        callbacks.on_task_start = on_task_start
        callbacks.on_task_complete = on_task_complete

        # Setup adaptive concurrency
        if adaptive:
            controller = AdaptiveConcurrencyController(
                config,
                TuningConfig(enable_adaptive_concurrency=True)
            )

            def update_config(new_config: ExecutionConfig) -> None:
                nonlocal config
                config = new_config
                if verbose:
                    click.echo(f"  🔧 Adjusted concurrency to {config.max_concurrent}")

            adaptive_callback = _create_adaptive_callback(controller, update_config)

            # Combine with existing progress callback
            if callbacks.on_progress:
                original_callback = callbacks.on_progress
                def combined_adaptive_callback(metrics: ExecutionMetrics) -> None:
                    original_callback(metrics)
                    adaptive_callback(metrics)
                callbacks.on_progress = combined_adaptive_callback
            else:
                callbacks.on_progress = adaptive_callback

        # Create and run engine
        click.echo("\n🚀 Starting execution...")
        engine = ParallelExecutionEngine(
            graph=task_graph,
            executor=executor,
            config=config,
            callbacks=callbacks,
        )

        result = await engine.execute()

        # Stop dashboard
        if dashboard:
            dashboard.stop()

        # Display results
        click.echo("\n" + "=" * 60)
        click.echo("EXECUTION COMPLETE")
        click.echo("=" * 60)

        click.echo("\n📊 Results:")
        click.echo(f"  Status: {result.status}")
        click.echo(f"  Completed: {result.metrics.completed}/{result.metrics.total_tasks}")
        click.echo(f"  Failed: {result.metrics.failed}")
        click.echo(f"  Skipped: {result.metrics.skipped}")
        click.echo(f"  Time: {result.metrics.wall_clock_seconds:.1f}s")
        click.echo(f"  Tokens: {result.metrics.total_tokens_used:,}")
        click.echo(f"  Cost: ${result.metrics.total_cost:.4f}")

        # Generate performance report
        if analyzer:
            report = generate_performance_report(result, analyzer)
            click.echo("\n" + report)

        # Save results if requested
        if output:
            _save_results(result, output, analyzer)
            click.echo(f"\n💾 Results saved to {output}")

        # Show snapshot info
        if save_snapshots and snapshotter:
            click.echo(f"\n📸 Saved {snapshotter.snapshot_count} Mermaid snapshots to {snapshot_dir}")
            click.echo(f"  Run `omni execute replay {result.execution_id}` to replay")

        # Show adaptive concurrency stats
        if adaptive and controller:
            stats = controller.get_stats()
            click.echo("\n⚡ Adaptive Concurrency Stats:")
            click.echo(f"  Final concurrency: {stats['current_concurrency']}")
            click.echo(f"  Adjustments made: {stats['adjustment_count']}")
            click.echo(f"  Completion rate: {stats['completion_rate']:.2f} tasks/s")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


async def _replay_async(
    execution_id: str,
    db_path: str,
    speed: float,
    no_dashboard: bool,
    save_snapshots: bool,
    export_timeline: str | None,
    pause_on_failure: bool,
) -> None:
    """Async implementation of the replay command."""
    try:
        click.echo(f"📂 Loading execution {execution_id} from {db_path}...")

        config = ReplayConfig(
            playback_speed=speed,
            show_dashboard=not no_dashboard,
            save_snapshots=save_snapshots,
            pause_on_failure=pause_on_failure,
        )

        replayer = ExecutionReplayer(db_path, config)
        await replayer.load_execution(execution_id)

        click.echo("🎬 Starting replay...")
        await replayer.replay()

        # Export timeline if requested
        if export_timeline:
            output_path = replayer.export_timeline(export_timeline)
            click.echo(f"\n💾 Timeline exported to {output_path}")

        click.echo("\n✅ Replay complete")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


async def _report_async(
    execution_id: str,
    db_path: str,
    output: str | None,
) -> None:
    """Async implementation of the report command."""
    try:
        # TODO: Load execution and generate detailed report
        # For now, show a placeholder

        click.echo(f"📊 Performance report for execution {execution_id}")
        click.echo("=" * 60)
        click.echo("\n(Detailed report generation coming soon)")
        click.echo("\nRun `omni execute replay {execution_id}` to visualize execution")

        if output:
            with open(output, "w") as f:
                f.write(f"Report for execution {execution_id}\n")
            click.echo(f"\n💾 Report saved to {output}")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


def _load_task_graph(filepath: str) -> TaskGraph:
    """Load a TaskGraph from JSON file.

    Args:
        filepath: Path to JSON file.

    Returns:
        Loaded TaskGraph.

    Raises:
        ValueError: If file cannot be loaded or parsed.
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        # Create task graph
        graph = TaskGraph(name=data.get("name", "Unnamed Graph"))

        # Add tasks from data
        for task_data in data.get("tasks", []):
            # Create task from data
            task = Task(
                description=task_data.get("description", ""),
                task_type=TaskType(task_data.get("task_type", "custom")),
                task_id=task_data.get("task_id", ""),
                dependencies=task_data.get("dependencies", []),
                priority=task_data.get("priority", 0),
                max_retries=task_data.get("max_retries", 3),
            )

            # Add task to graph
            graph.add_task(task)

        return graph

    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"Failed to load task graph from {filepath}: {e}") from e


def _create_dashboard_callback(dashboard: LiveDashboard) -> Callable[[ExecutionMetrics], None]:
    """Create dashboard update callback."""
    def callback(metrics: ExecutionMetrics) -> None:
        dashboard.update(metrics)
    return callback


def _create_mermaid_callback(snapshotter: MermaidSnapshotter) -> Callable[[ExecutionMetrics], None]:
    """Create Mermaid snapshot callback."""
    def callback(metrics: ExecutionMetrics) -> None:
        snapshotter.save_snapshot(metrics)
    return callback


def _create_adaptive_callback(
    controller: AdaptiveConcurrencyController,
    update_callback: Callable[[ExecutionConfig], None]
) -> Callable[[ExecutionMetrics], None]:
    """Create adaptive concurrency callback."""
    def callback(metrics: ExecutionMetrics) -> None:
        adjustment = controller.calculate_adjustment(metrics)
        if adjustment is not None:
            new_config = controller.get_adjusted_config(adjustment)
            update_callback(new_config)
    return callback


def _save_results(result: Any, output_path: str, analyzer: MetricsAnalyzer | None = None) -> None:
    """Save execution results to JSON file.

    Args:
        result: Execution result.
        output_path: Path to save results.
        analyzer: Optional metrics analyzer.
    """
    output_data = {
        "execution_id": result.execution_id,
        "status": result.status,
        "metrics": {
            "total_tasks": result.metrics.total_tasks,
            "completed": result.metrics.completed,
            "failed": result.metrics.failed,
            "skipped": result.metrics.skipped,
            "wall_clock_seconds": result.metrics.wall_clock_seconds,
            "total_tokens_used": result.metrics.total_tokens_used,
            "total_cost": result.metrics.total_cost,
            "parallel_efficiency": result.metrics.parallel_efficiency,
        },
        "results": {},
    }

    # Add task results
    for task_id, task_result in result.results.items():
        output_data["results"][task_id] = {
            "status": task_result.status,
            "outputs": task_result.outputs,
            "tokens_used": task_result.tokens_used,
            "cost": task_result.cost,
        }

    # Add performance metrics if analyzer available
    if analyzer:
        performance_metrics = analyzer.analyze_execution(result)
        output_data["performance_analysis"] = {
            "parallel_efficiency": performance_metrics.parallel_efficiency,
            "max_concurrent_tasks": performance_metrics.max_concurrent_tasks,
            "critical_path_length": performance_metrics.critical_path_length,
            "bottleneck_tasks": performance_metrics.bottleneck_tasks,
            "recommendations": performance_metrics.recommendations,
        }

    # Save to file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, default=str)


def register_execute_command(cli: click.Group) -> None:
    """Register the execute command group with the main CLI.

    Args:
        cli: Main click CLI group.
    """
    cli.add_command(execute_cli)
