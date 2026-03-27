"""
Example: Task Graph Visualization

Demonstrates how to use the TaskGraphVisualizer to create visualizations
in DOT, Mermaid, and ASCII formats.
"""

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


def create_sample_task_graph() -> TaskGraph:
    """Create a sample task graph for demonstration."""
    graph = TaskGraph(name="Omni-LLM Development Plan")

    # Define tasks for a typical development workflow
    tasks = [
        Task(
            description="Design system architecture",
            task_type=TaskType.ANALYSIS,
            task_id="design",
            status=TaskStatus.COMPLETED,
            priority=8,
            complexity=ComplexityEstimate(
                code_complexity=2,
                integration_complexity=7,
                testing_complexity=3,
                unknown_factor=4,
                estimated_tokens=2000,
                reasoning="Architectural design requires integration planning",
            ),
        ),
        Task(
            description="Implement core module",
            task_type=TaskType.CODE_GENERATION,
            task_id="core",
            dependencies=["design"],
            status=TaskStatus.RUNNING,
            priority=7,
            complexity=ComplexityEstimate(
                code_complexity=6,
                integration_complexity=5,
                testing_complexity=4,
                unknown_factor=3,
                estimated_tokens=5000,
                reasoning="Core functionality with moderate complexity",
            ),
        ),
        Task(
            description="Write unit tests for core",
            task_type=TaskType.TESTING,
            task_id="core_tests",
            dependencies=["core"],
            status=TaskStatus.PENDING,
            priority=5,
            complexity=ComplexityEstimate(
                code_complexity=4,
                integration_complexity=3,
                testing_complexity=6,
                unknown_factor=2,
                estimated_tokens=3000,
                reasoning="Test coverage for core functionality",
            ),
        ),
        Task(
            description="Implement API layer",
            task_type=TaskType.CODE_GENERATION,
            task_id="api",
            dependencies=["design"],
            status=TaskStatus.PENDING,
            priority=6,
            complexity=ComplexityEstimate(
                code_complexity=5,
                integration_complexity=7,
                testing_complexity=5,
                unknown_factor=3,
                estimated_tokens=4000,
                reasoning="API needs to integrate with core and external systems",
            ),
        ),
        Task(
            description="Write documentation",
            task_type=TaskType.DOCUMENTATION,
            task_id="docs",
            dependencies=["core", "api"],
            status=TaskStatus.PENDING,
            priority=3,
            complexity=ComplexityEstimate(
                code_complexity=2,
                integration_complexity=4,
                testing_complexity=1,
                unknown_factor=2,
                estimated_tokens=2500,
                reasoning="Document both core and API functionality",
            ),
        ),
        Task(
            description="Deploy to staging",
            task_type=TaskType.DEPLOYMENT,
            task_id="deploy",
            dependencies=["core_tests", "docs"],
            status=TaskStatus.PENDING,
            priority=4,
            complexity=ComplexityEstimate(
                code_complexity=3,
                integration_complexity=6,
                testing_complexity=5,
                unknown_factor=5,
                estimated_tokens=1500,
                reasoning="Deployment involves multiple systems and configurations",
            ),
        ),
        Task(
            description="Fix critical bug found in testing",
            task_type=TaskType.REFACTORING,
            task_id="bugfix",
            dependencies=["core_tests"],
            status=TaskStatus.FAILED,
            priority=9,  # High priority for bug fixes
            retry_count=1,
            max_retries=3,
            complexity=ComplexityEstimate(
                code_complexity=4,
                integration_complexity=5,
                testing_complexity=7,
                unknown_factor=6,
                estimated_tokens=2000,
                reasoning="Bug requires investigation and careful fixing",
            ),
        ),
    ]

    # Add all tasks to the graph
    for task in tasks:
        graph.add_task(task)

    return graph


def demonstrate_dot_visualization(graph: TaskGraph) -> None:
    """Demonstrate DOT format visualization."""
    print("=" * 60)
    print("DOT Format Visualization")
    print("=" * 60)

    visualizer = TaskGraphVisualizer(graph)
    dot_output = visualizer.visualize(OutputFormat.DOT)

    # Print first few lines to show structure
    lines = dot_output.split("\n")
    for _i, line in enumerate(lines[:15]):
        print(line)

    if len(lines) > 15:
        print("...")
        print(f"[Output truncated. Total lines: {len(lines)}]")

    # Save to file
    visualizer.save_to_file("task_graph.dot", OutputFormat.DOT)
    print("\n✓ DOT visualization saved to 'task_graph.dot'")
    print("  Render with: dot -Tpng task_graph.dot -o task_graph.png")


def demonstrate_mermaid_visualization(graph: TaskGraph) -> None:
    """Demonstrate Mermaid format visualization."""
    print("\n" + "=" * 60)
    print("Mermaid Format Visualization")
    print("=" * 60)

    visualizer = TaskGraphVisualizer(graph)
    mermaid_output = visualizer.visualize(OutputFormat.MERMAID)

    # Print first few lines to show structure
    lines = mermaid_output.split("\n")
    for _i, line in enumerate(lines[:20]):
        print(line)

    if len(lines) > 20:
        print("...")
        print(f"[Output truncated. Total lines: {len(lines)}]")

    # Save to file
    visualizer.save_to_file("task_graph.mmd", OutputFormat.MERMAID)
    print("\n✓ Mermaid visualization saved to 'task_graph.mmd'")
    print("  Use in Markdown: ```mermaid ... ``` or Mermaid Live Editor")


def demonstrate_ascii_visualization(graph: TaskGraph) -> None:
    """Demonstrate ASCII format visualization."""
    print("\n" + "=" * 60)
    print("ASCII Format Visualization")
    print("=" * 60)

    visualizer = TaskGraphVisualizer(graph)
    ascii_output = visualizer.visualize(OutputFormat.ASCII)

    print(ascii_output)

    # Save to file
    visualizer.save_to_file("task_graph.txt", OutputFormat.ASCII)
    print("\n✓ ASCII visualization saved to 'task_graph.txt'")


def demonstrate_convenience_function(graph: TaskGraph) -> None:
    """Demonstrate the convenience function."""
    print("\n" + "=" * 60)
    print("Convenience Function Usage")
    print("=" * 60)

    # Using the convenience function
    dot_output = visualize_task_graph(graph, OutputFormat.DOT)
    mermaid_output = visualize_task_graph(graph, "mermaid")  # String format works too
    ascii_output = visualize_task_graph(graph, OutputFormat.ASCII)

    print("✓ visualize_task_graph() returns visualization strings directly")
    print(f"  DOT length: {len(dot_output)} characters")
    print(f"  Mermaid length: {len(mermaid_output)} characters")
    print(f"  ASCII length: {len(ascii_output)} characters")


def demonstrate_graph_statistics(graph: TaskGraph) -> None:
    """Demonstrate graph statistics and properties."""
    print("\n" + "=" * 60)
    print("Task Graph Statistics")
    print("=" * 60)

    summary = graph.summary()
    print(f"Graph Name: {summary['name']}")
    print(f"Total Tasks: {summary['total_tasks']}")
    print(f"Dependency Edges: {summary['edges']}")
    print(f"Completed: {summary['completed_fraction']:.0%}")
    print(f"Has Failures: {summary['has_failures']}")
    print(f"Total Estimated Tokens: {summary['total_estimated_tokens']}")

    print("\nStatus Breakdown:")
    for status, count in summary['status_counts'].items():
        print(f"  {status}: {count}")

    print("\nReady Tasks (can be executed now):")
    ready_tasks = graph.get_ready_tasks()
    for task in ready_tasks:
        print(f"  - {task.task_id}: {task.description[:40]}...")

    print("\nTopological Execution Order:")
    try:
        order = graph.topological_order()
        for i, task_id in enumerate(order, 1):
            task = graph.get_task(task_id)
            status_icon = "✓" if task.status == TaskStatus.COMPLETED else "○"
            print(f"  {i:2d}. [{status_icon}] {task_id}")
    except Exception as e:
        print(f"  Cannot compute order (graph may have cycles): {e}")


def main() -> None:
    """Main demonstration function."""
    print("Task Graph Visualizer Example")
    print("=" * 60)

    # Create a sample task graph
    graph = create_sample_task_graph()
    print(f"Created task graph: {graph.name}")
    print(f"Total tasks: {graph.size}")
    print(f"Dependencies: {graph.edge_count}")

    # Demonstrate different visualization formats
    demonstrate_dot_visualization(graph)
    demonstrate_mermaid_visualization(graph)
    demonstrate_ascii_visualization(graph)

    # Demonstrate convenience function
    demonstrate_convenience_function(graph)

    # Show graph statistics
    demonstrate_graph_statistics(graph)

    print("\n" + "=" * 60)
    print("Example Complete!")
    print("=" * 60)
    print("\nGenerated files:")
    print("  - task_graph.dot   (Graphviz DOT format)")
    print("  - task_graph.mmd   (Mermaid format)")
    print("  - task_graph.txt   (ASCII format)")
    print("\nNext steps:")
    print("  1. Render DOT file: dot -Tpng task_graph.dot -o task_graph.png")
    print("  2. Use Mermaid in Markdown or online editor")
    print("  3. View ASCII output in terminal or text editor")


if __name__ == "__main__":
    main()

