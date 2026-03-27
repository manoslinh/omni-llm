"""
Tests for Task Graph Visualizer.
"""

from __future__ import annotations

import tempfile

import pytest

from omni.decomposition.visualizer import (
    OutputFormat,
    TaskGraphVisualizer,
    visualize_task_graph,
)
from omni.task.models import (
    ComplexityEstimate,
    Task,
    TaskGraph,
    TaskStatus,
    TaskType,
)


def test_output_format_enum() -> None:
    """Test OutputFormat enum values and conversion."""
    assert OutputFormat.DOT == "dot"
    assert OutputFormat.MERMAID == "mermaid"
    assert OutputFormat.ASCII == "ascii"

    assert str(OutputFormat.DOT) == "dot"
    assert OutputFormat("dot") == OutputFormat.DOT
    # Note: StrEnum is case-sensitive in Python 3.12
    # Our visualizer.visualize() method handles case-insensitive strings

    with pytest.raises(ValueError):
        OutputFormat("invalid")


def test_visualizer_initialization() -> None:
    """Test TaskGraphVisualizer initialization."""
    graph = TaskGraph(name="test")
    visualizer = TaskGraphVisualizer(graph)
    assert visualizer.task_graph is graph

    with pytest.raises(ValueError, match="Expected TaskGraph"):
        TaskGraphVisualizer("not a graph")  # type: ignore


def test_dot_visualization() -> None:
    """Test DOT format visualization."""
    graph = TaskGraph(name="sample")

    task1 = Task(
        description="Write implementation",
        task_type=TaskType.CODE_GENERATION,
        task_id="task1",
        priority=5,
    )
    task2 = Task(
        description="Write tests",
        task_type=TaskType.TESTING,
        task_id="task2",
        dependencies=["task1"],
        priority=3,
    )

    graph.add_task(task1)
    graph.add_task(task2)

    visualizer = TaskGraphVisualizer(graph)
    dot_output = visualizer.visualize(OutputFormat.DOT)

    assert "digraph TaskGraph {" in dot_output
    assert "rankdir=TB;" in dot_output
    assert '"task1"' in dot_output
    assert '"task2"' in dot_output
    assert '"task1" -> "task2"' in dot_output


def test_dot_styling() -> None:
    """Test DOT node styling based on task properties."""
    graph = TaskGraph(name="styling")

    pending = Task(
        description="Pending",
        task_id="pending",
        status=TaskStatus.PENDING,
    )
    completed = Task(
        description="Completed",
        task_id="completed",
        status=TaskStatus.COMPLETED,
    )
    failed = Task(
        description="Failed",
        task_id="failed",
        status=TaskStatus.FAILED,
    )

    graph.add_task(pending)
    graph.add_task(completed)
    graph.add_task(failed)

    visualizer = TaskGraphVisualizer(graph)
    dot_output = visualizer.visualize(OutputFormat.DOT)

    # Check status-based coloring
    assert 'fillcolor="#FFE5B4"' in dot_output  # PENDING
    assert 'fillcolor="#90EE90"' in dot_output  # COMPLETED
    assert 'fillcolor="#FFB6C1"' in dot_output  # FAILED
    assert 'style=filled,dashed' in dot_output  # Failed style


def test_mermaid_visualization() -> None:
    """Test Mermaid format visualization."""
    graph = TaskGraph(name="mermaid")

    task1 = Task(
        description="Task one",
        task_id="t1",
        status=TaskStatus.PENDING,
    )
    task2 = Task(
        description="Task two",
        task_id="t2",
        status=TaskStatus.RUNNING,
        dependencies=["t1"],
    )

    graph.add_task(task1)
    graph.add_task(task2)

    visualizer = TaskGraphVisualizer(graph)
    mermaid_output = visualizer.visualize(OutputFormat.MERMAID)

    assert "%% Task Graph Visualization" in mermaid_output
    assert "graph TB" in mermaid_output
    assert "classDef pending" in mermaid_output
    assert "classDef running" in mermaid_output
    assert 't1["' in mermaid_output
    assert 't2["' in mermaid_output
    assert "t1 --> t2" in mermaid_output
    assert "class t1 pending" in mermaid_output
    assert "class t2 running" in mermaid_output


def test_ascii_visualization() -> None:
    """Test ASCII format visualization."""
    graph = TaskGraph(name="ascii")

    task1 = Task(
        description="Root task",
        task_id="root",
        status=TaskStatus.COMPLETED,
        priority=5,
        complexity=ComplexityEstimate(
            code_complexity=3,
            integration_complexity=2,
            testing_complexity=4,
            unknown_factor=1,
            estimated_tokens=1000,
        ),
    )
    task2 = Task(
        description="Child task",
        task_id="child",
        status=TaskStatus.RUNNING,
        dependencies=["root"],
        priority=3,
    )

    graph.add_task(task1)
    graph.add_task(task2)

    visualizer = TaskGraphVisualizer(graph)
    ascii_output = visualizer.visualize(OutputFormat.ASCII)

    assert "Task Graph: ascii" in ascii_output
    assert "Tasks: 2, Edges: 1" in ascii_output
    assert "Execution Order (topological):" in ascii_output
    assert "Dependency Tree:" in ascii_output
    assert "[✓] root:" in ascii_output
    assert "[▶] child:" in ascii_output
    assert "Statistics:" in ascii_output
    assert "Task Details:" in ascii_output


def test_ascii_empty_graph() -> None:
    """Test ASCII visualization of empty graph."""
    graph = TaskGraph(name="empty")
    visualizer = TaskGraphVisualizer(graph)
    ascii_output = visualizer.visualize(OutputFormat.ASCII)

    assert "Empty task graph" in ascii_output


def test_visualize_convenience_function() -> None:
    """Test the convenience function visualize_task_graph."""
    graph = TaskGraph(name="convenience")
    task = Task(description="Test", task_id="test")
    graph.add_task(task)

    dot_output = visualize_task_graph(graph, OutputFormat.DOT)
    assert "digraph TaskGraph {" in dot_output

    mermaid_output = visualize_task_graph(graph, "mermaid")
    assert "graph TB" in mermaid_output

    ascii_output = visualize_task_graph(graph, OutputFormat.ASCII)
    assert "Task Graph: convenience" in ascii_output


def test_file_save() -> None:
    """Test saving visualization to file."""
    graph = TaskGraph(name="file_test")
    task = Task(description="Test task", task_id="test")
    graph.add_task(task)

    visualizer = TaskGraphVisualizer(graph)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".dot", delete=False) as f:
        dot_file = f.name

    try:
        visualizer.save_to_file(dot_file, OutputFormat.DOT)

        with open(dot_file) as f:
            content = f.read()

        assert "digraph TaskGraph {" in content
        assert '"test"' in content
    finally:
        import os
        os.unlink(dot_file)


def test_string_format_argument() -> None:
    """Test that format can be passed as string."""
    graph = TaskGraph(name="string_format")
    task = Task(description="Test", task_id="test")
    graph.add_task(task)

    visualizer = TaskGraphVisualizer(graph)

    # Test with string format
    dot_output = visualizer.visualize("dot")
    assert "digraph TaskGraph {" in dot_output

    mermaid_output = visualizer.visualize("mermaid")
    assert "graph TB" in mermaid_output

    ascii_output = visualizer.visualize("ascii")
    assert "Task Graph: string_format" in ascii_output

    with pytest.raises(ValueError, match="Unsupported format"):
        visualizer.visualize("invalid_format")

