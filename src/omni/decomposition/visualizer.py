"""
Task Graph Visualizer for Omni-LLM.

Provides visualization capabilities for task decomposition graphs in multiple formats:
- DOT (Graphviz) for professional diagrams
- Mermaid for markdown/notebook integration
- ASCII for terminal/quick inspection
"""

from __future__ import annotations

from enum import StrEnum

from omni.task.models import Task, TaskGraph, TaskStatus, TaskType


class OutputFormat(StrEnum):
    """Supported visualization output formats."""

    DOT = "dot"
    MERMAID = "mermaid"
    ASCII = "ascii"

    def __str__(self) -> str:
        return self.value


class TaskGraphVisualizer:
    """Visualizes TaskGraph objects in multiple formats.

    This class provides methods to convert TaskGraph instances into
    various visualization formats for analysis, debugging, and documentation.
    """

    def __init__(self, task_graph: TaskGraph) -> None:
        """Initialize visualizer with a TaskGraph.

        Args:
            task_graph: The TaskGraph to visualize.

        Raises:
            ValueError: If task_graph is not a valid TaskGraph instance.
        """
        if not isinstance(task_graph, TaskGraph):
            raise ValueError(
                f"Expected TaskGraph, got {type(task_graph).__name__}"
            )
        self.task_graph = task_graph

    def visualize(self, format: OutputFormat | str = OutputFormat.DOT) -> str:
        """Generate visualization in the specified format.

        Args:
            format: Output format (DOT, MERMAID, or ASCII).

        Returns:
            Visualization string in the requested format.

        Raises:
            ValueError: If format is not supported.
        """
        if isinstance(format, str):
            try:
                format = OutputFormat(format)
            except ValueError:
                # Try case-insensitive match
                format_lower = format.lower()
                for fmt in OutputFormat:
                    if fmt.value.lower() == format_lower:
                        format = fmt
                        break
                else:
                    raise ValueError(
                        f"Unsupported format: {format}. "
                        f"Supported formats: {list(OutputFormat)}"
                    )

        if format == OutputFormat.DOT:
            return self._to_dot()
        elif format == OutputFormat.MERMAID:
            return self._to_mermaid()
        elif format == OutputFormat.ASCII:
            return self._to_ascii()
        else:
            raise ValueError(f"Unhandled format: {format}")

    def _to_dot(self) -> str:
        """Generate Graphviz DOT representation.

        Returns:
            DOT language string suitable for rendering with Graphviz.
        """
        lines = [
            "digraph TaskGraph {",
            "  rankdir=TB;",
            "  node [shape=box, style=filled, fontname=\"Helvetica\"];",
            "  edge [color=\"#666666\"];",
            "",
        ]

        # Add nodes with status-based styling
        for task_id, task in self.task_graph.tasks.items():
            node_attrs = self._get_dot_node_attrs(task)
            attrs_str = ", ".join(f"{k}={v}" for k, v in node_attrs.items())
            lines.append(f'  "{task_id}" [{attrs_str}];')

        lines.append("")

        # Add edges for dependencies
        for task_id, task in self.task_graph.tasks.items():
            for dep_id in task.dependencies:
                lines.append(f'  "{dep_id}" -> "{task_id}";')

        lines.append("}")
        return "\n".join(lines)

    def _get_dot_node_attrs(self, task: Task) -> dict[str, str]:
        """Get DOT node attributes for a task based on its properties.

        Args:
            task: The task to get attributes for.

        Returns:
            Dictionary of DOT node attributes.
        """
        # Base attributes
        attrs: dict[str, str] = {
            "label": self._escape_dot_label(
                f"{task.task_id}\\n{task.description[:30]}..."
                if len(task.description) > 30
                else f"{task.task_id}\\n{task.description}"
            ),
            "tooltip": self._escape_dot_label(
                f"Type: {task.task_type}\\n"
                f"Status: {task.status}\\n"
                f"Priority: {task.priority}\\n"
                f"Dependencies: {len(task.dependencies)}"
            ),
        }

        # Status-based coloring
        status_colors = {
            TaskStatus.PENDING: "#FFE5B4",  # Light orange
            TaskStatus.RUNNING: "#ADD8E6",  # Light blue
            TaskStatus.COMPLETED: "#90EE90",  # Light green
            TaskStatus.FAILED: "#FFB6C1",  # Light red
        }
        attrs["fillcolor"] = f'"{status_colors.get(task.status, "#FFFFFF")}"'

        # Type-based shape
        if task.task_type == TaskType.CODE_GENERATION:
            attrs["shape"] = "ellipse"
        elif task.task_type == TaskType.TESTING:
            attrs["shape"] = "diamond"
        elif task.task_type == TaskType.DOCUMENTATION:
            attrs["shape"] = "note"
        elif task.task_type == TaskType.DEPLOYMENT:
            attrs["shape"] = "cds"

        # Priority-based border
        if task.priority >= 7:
            attrs["penwidth"] = "3"
            attrs["color"] = '"#FF0000"'  # Red for high priority
        elif task.priority >= 4:
            attrs["penwidth"] = "2"
            attrs["color"] = '"#FFA500"'  # Orange for medium priority

        # Failed tasks get dashed border
        if task.status == TaskStatus.FAILED:
            attrs["style"] = "filled,dashed"
            attrs["color"] = '"#FF0000"'

        return attrs

    def _escape_dot_label(self, text: str) -> str:
        """Escape special characters for DOT labels.

        Args:
            text: Text to escape.

        Returns:
            Escaped text safe for DOT labels.
        """
        # Escape backslashes first
        text = text.replace("\\", "\\\\")
        # Escape quotes
        text = text.replace('"', '\\"')
        # Escape newlines (already handled with \\n in our labels)
        return f'"{text}"'

    def _to_mermaid(self) -> str:
        """Generate Mermaid flowchart representation.

        Returns:
            Mermaid flowchart syntax string.
        """
        lines = [
            "%% Task Graph Visualization",
            "graph TB",
        ]

        # Define node styles
        lines.extend([
            "  classDef pending fill:#FFE5B4,stroke:#333,stroke-width:1px;",
            "  classDef running fill:#ADD8E6,stroke:#333,stroke-width:1px;",
            "  classDef completed fill:#90EE90,stroke:#333,stroke-width:1px;",
            "  classDef failed fill:#FFB6C1,stroke:#FF0000,stroke-width:2px,stroke-dasharray: 5 5;",
            "",
        ])

        # Add nodes
        for task_id, task in self.task_graph.tasks.items():
            node_text = self._escape_mermaid_label(
                f"{task.task_id}: {task.description[:25]}..."
                if len(task.description) > 25
                else f"{task.task_id}: {task.description}"
            )
            lines.append(f'  {task_id}["{node_text}"]')

        lines.append("")

        # Add edges
        for task_id, task in self.task_graph.tasks.items():
            for dep_id in task.dependencies:
                lines.append(f"  {dep_id} --> {task_id}")

        lines.append("")

        # Apply CSS classes based on status
        for task_id, task in self.task_graph.tasks.items():
            status_class = str(task.status).lower()
            lines.append(f"  class {task_id} {status_class};")

        return "\n".join(lines)

    def _escape_mermaid_label(self, text: str) -> str:
        """Escape special characters for Mermaid labels.

        Args:
            text: Text to escape.

        Returns:
            Escaped text safe for Mermaid labels.
        """
        # Escape quotes
        text = text.replace('"', '&quot;')
        # Escape HTML entities
        text = text.replace("<", "&lt;").replace(">", "&gt;")
        return text

    def _to_ascii(self) -> str:
        """Generate ASCII art representation of the task graph.

        Returns:
            ASCII representation showing task hierarchy and status.
        """
        if not self.task_graph.tasks:
            return "Empty task graph"

        # Build adjacency list
        adjacency: dict[str, list[str]] = {tid: [] for tid in self.task_graph.tasks}
        for task_id, task in self.task_graph.tasks.items():
            for dep_id in task.dependencies:
                adjacency[dep_id].append(task_id)

        # Find roots (tasks with no dependencies)
        roots = [
            tid for tid in self.task_graph.tasks
            if not self.task_graph.tasks[tid].dependencies
        ]

        lines: list[str] = []
        lines.append(f"Task Graph: {self.task_graph.name}")
        lines.append(f"Tasks: {self.task_graph.size}, "
                    f"Edges: {self.task_graph.edge_count}")
        lines.append("=" * 60)

        # Display by topological order if possible
        try:
            order = self.task_graph.topological_order()
            lines.append("Execution Order (topological):")
            for i, task_id in enumerate(order, 1):
                task = self.task_graph.tasks[task_id]
                status_icon = self._get_status_icon(task.status)
                lines.append(
                    f"  {i:2d}. [{status_icon}] {task_id}: "
                    f"{task.description[:40]}"
                    f"{'...' if len(task.description) > 40 else ''}"
                )
            lines.append("")
        except Exception:
            # Graph has cycles or other issues
            pass

        # Display dependency tree
        lines.append("Dependency Tree:")
        for root_id in roots:
            self._build_ascii_tree(root_id, adjacency, lines, "", True)

        # Display statistics
        lines.append("")
        lines.append("Statistics:")
        lines.append(f"  Completed: {self.task_graph.completed_fraction:.0%}")
        lines.append(f"  Failed: {len(self.task_graph.failed_tasks)}")
        lines.append(f"  Pending: {sum(1 for t in self.task_graph.tasks.values() if t.status == TaskStatus.PENDING)}")
        lines.append(f"  Running: {sum(1 for t in self.task_graph.tasks.values() if t.status == TaskStatus.RUNNING)}")

        # Display task details
        lines.append("")
        lines.append("Task Details:")
        for task_id, task in self.task_graph.tasks.items():
            status_icon = self._get_status_icon(task.status)
            deps = ", ".join(task.dependencies) if task.dependencies else "none"
            lines.append(
                f"  {task_id} [{status_icon}] {task.task_type.value}:"
            )
            lines.append(f"    Description: {task.description}")
            lines.append(f"    Dependencies: {deps}")
            lines.append(f"    Priority: {task.priority}, "
                        f"Retries: {task.retry_count}/{task.max_retries}")
            if task.complexity:
                lines.append(
                    f"    Complexity: {task.complexity.overall_score:.1f}/10 "
                    f"({task.complexity.tier})"
                )

        return "\n".join(lines)

    def _build_ascii_tree(
        self,
        node_id: str,
        adjacency: dict[str, list[str]],
        lines: list[str],
        prefix: str,
        is_last: bool
    ) -> None:
        """Recursively build ASCII tree representation.

        Args:
            node_id: Current node ID.
            adjacency: Adjacency list of the graph.
            lines: List to append output lines to.
            prefix: Current prefix for tree branches.
            is_last: Whether this node is the last child of its parent.
        """
        task = self.task_graph.tasks[node_id]
        status_icon = self._get_status_icon(task.status)

        # Current node line
        connector = "└── " if is_last else "├── "
        lines.append(
            f"{prefix}{connector}[{status_icon}] {node_id}: "
            f"{task.task_type.value}"
        )

        # Update prefix for children
        child_prefix = prefix + ("    " if is_last else "│   ")

        # Process children
        children = adjacency[node_id]
        for i, child_id in enumerate(children):
            is_child_last = i == len(children) - 1
            self._build_ascii_tree(
                child_id, adjacency, lines, child_prefix, is_child_last
            )

    def _get_status_icon(self, status: TaskStatus) -> str:
        """Get ASCII icon for task status.

        Args:
            status: Task status.

        Returns:
            Single character icon representing the status.
        """
        icons = {
            TaskStatus.PENDING: "○",
            TaskStatus.RUNNING: "▶",
            TaskStatus.COMPLETED: "✓",
            TaskStatus.FAILED: "✗",
        }
        return icons.get(status, "?")

    def save_to_file(self, filepath: str, format: OutputFormat | str = OutputFormat.DOT) -> None:
        """Save visualization to a file.

        Args:
            filepath: Path to save the visualization to.
            format: Output format (DOT, MERMAID, or ASCII).

        Raises:
            IOError: If file cannot be written.
        """
        content = self.visualize(format)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    @classmethod
    def from_file(cls, filepath: str, format: OutputFormat | str = OutputFormat.DOT) -> str:
        """Read visualization from a file.

        This is a convenience method for reading previously saved visualizations.

        Args:
            filepath: Path to read the visualization from.
            format: Format of the file (for validation).

        Returns:
            Visualization content.

        Raises:
            IOError: If file cannot be read.
            ValueError: If format doesn't match file extension.
        """
        with open(filepath, encoding="utf-8") as f:
            return f.read()


def visualize_task_graph(
    task_graph: TaskGraph,
    format: OutputFormat | str = OutputFormat.DOT
) -> str:
    """Convenience function to visualize a TaskGraph.

    Args:
        task_graph: The TaskGraph to visualize.
        format: Output format (DOT, MERMAID, or ASCII).

    Returns:
        Visualization string in the requested format.
    """
    return TaskGraphVisualizer(task_graph).visualize(format)

