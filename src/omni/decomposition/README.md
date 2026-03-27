# Task Decomposition Module

This module provides visualization capabilities for task decomposition graphs in Omni-LLM.

## Overview

The `TaskGraphVisualizer` class converts `TaskGraph` instances into multiple visualization formats:
- **DOT** (Graphviz) - For professional diagrams and rendering to PNG/SVG
- **Mermaid** - For markdown/notebook integration
- **ASCII** - For terminal/quick inspection

## Installation

The visualizer is part of the Omni-LLM package. No additional dependencies are required beyond:
- `networkx` (already a dependency for TaskGraph)
- Optional: `graphviz` for rendering DOT files to images

## Usage

### Basic Usage

```python
from omni.decomposition.visualizer import TaskGraphVisualizer, OutputFormat
from omni.task.models import Task, TaskGraph

# Create a task graph
graph = TaskGraph(name="My Project")
task1 = Task(description="Design", task_id="design")
task2 = Task(description="Implement", task_id="implement", dependencies=["design"])
graph.add_task(task1)
graph.add_task(task2)

# Create visualizer
visualizer = TaskGraphVisualizer(graph)

# Generate visualizations
dot_output = visualizer.visualize(OutputFormat.DOT)
mermaid_output = visualizer.visualize(OutputFormat.MERMAID)
ascii_output = visualizer.visualize(OutputFormat.ASCII)

# Save to files
visualizer.save_to_file("graph.dot", OutputFormat.DOT)
visualizer.save_to_file("graph.mmd", OutputFormat.MERMAID)
visualizer.save_to_file("graph.txt", OutputFormat.ASCII)
```

### Convenience Function

```python
from omni.decomposition.visualizer import visualize_task_graph

# One-liner visualization
dot_output = visualize_task_graph(graph, OutputFormat.DOT)
```

### String Format Support

The `visualize()` method accepts both enum values and strings:

```python
# All of these work:
visualizer.visualize(OutputFormat.DOT)
visualizer.visualize("dot")
visualizer.visualize("DOT")  # Case-insensitive
```

## Visualization Features

### DOT Format Features
- **Status-based coloring**: Pending (orange), Running (blue), Completed (green), Failed (red)
- **Task type shapes**: Code generation (ellipse), Testing (diamond), Documentation (note), Deployment (cds)
- **Priority styling**: High priority tasks get thicker, colored borders
- **Failed tasks**: Dashed borders with red color
- **Tooltips**: Hover information with task details

### Mermaid Format Features
- **CSS classes**: Automatic styling based on task status
- **Compact labels**: Truncated descriptions with ellipsis
- **Flowchart syntax**: Compatible with Mermaid.js and markdown

### ASCII Format Features
- **Tree visualization**: Hierarchical dependency tree
- **Status icons**: ○ Pending, ▶ Running, ✓ Completed, ✗ Failed
- **Statistics**: Completion percentage, task counts by status
- **Task details**: Full information for each task
- **Execution order**: Topological ordering when possible

## Integration with TaskDecompositionEngine

The visualizer is designed to work seamlessly with the `TaskDecompositionEngine` (P2-08):

```python
# Example integration
from omni.decomposition.engine import TaskDecompositionEngine
from omni.decomposition.visualizer import TaskGraphVisualizer

# Decompose a complex task
engine = TaskDecompositionEngine()
graph = engine.decompose("Build a web API with authentication")

# Visualize the decomposition
visualizer = TaskGraphVisualizer(graph)
visualizer.save_to_file("decomposition.dot", OutputFormat.DOT)
```

## Examples

See `examples/task_graph_visualization.py` for a complete demonstration.

## Rendering DOT Files

To render DOT files to images:

```bash
# Install Graphviz
sudo apt-get install graphviz  # Ubuntu/Debian
brew install graphviz          # macOS

# Render to PNG
dot -Tpng task_graph.dot -o task_graph.png

# Render to SVG
dot -Tsvg task_graph.dot -o task_graph.svg
```

## Using Mermaid Visualizations

Mermaid files can be used in:
- GitHub/GitLab markdown (with Mermaid support)
- Jupyter notebooks
- Mermaid Live Editor (https://mermaid.live/)
- VS Code with Mermaid extension

## Testing

Run the visualizer tests:

```bash
pytest tests/test_decomposition_visualizer.py -v
```

## API Reference

### `OutputFormat` Enum
- `DOT`: Graphviz DOT format
- `MERMAID`: Mermaid flowchart format  
- `ASCII`: Plain text ASCII art format

### `TaskGraphVisualizer` Class

#### `__init__(task_graph: TaskGraph)`
Initialize with a TaskGraph to visualize.

#### `visualize(format: OutputFormat | str = OutputFormat.DOT) -> str`
Generate visualization in the specified format.

#### `save_to_file(filepath: str, format: OutputFormat | str = OutputFormat.DOT) -> None`
Save visualization to a file.

#### `from_file(filepath: str, format: OutputFormat | str = OutputFormat.DOT) -> str` (classmethod)
Read visualization from a file.

### `visualize_task_graph(task_graph: TaskGraph, format: OutputFormat | str = OutputFormat.DOT) -> str`
Convenience function to visualize a TaskGraph.

## Design Principles

1. **Minimal dependencies**: Uses only stdlib + existing project dependencies
2. **Integration-ready**: Works with existing Task/TaskGraph models
3. **Multiple formats**: Supports different use cases (docs, debugging, presentation)
4. **Extensible**: Easy to add new output formats
5. **Type-safe**: Full type annotations for IDE support