# P2-15: Workflow Orchestration

Advanced workflow orchestration with conditional control flow, resource management, and reusable templates.

## Overview

This module extends P2-14 Coordination Engine with advanced workflow capabilities:

- **Conditional branching** (IF/ELSE)
- **Loops** (WHILE, FOR_EACH)
- **Error handling** (TRY_CATCH)
- **Compensation actions** (rollback/undo)
- **Resource-aware execution** (concurrency, tokens, cost, time limits)
- **Reusable workflow templates** (5 built-in patterns)

## Architecture

### Core Components

1. **Workflow Definition Language**
   - 7 node types: TASK, PARALLEL, SEQUENCE, IF, WHILE, FOR_EACH, TRY_CATCH, COMPENSATE, SUB_WORKFLOW
   - Python expression evaluator with safe sandbox
   - Backward compatible with P2-14 `WorkflowPlan`

2. **Execution State Machine**
   - `WorkflowContext` - single source of truth for runtime state
   - State machine handling arbitrary control flow
   - TRY_CATCH stack (mirrors Python exception model)
   - Memory-safe loop execution

3. **Resource Manager**
   - Per-workflow budgets: concurrency, tokens, cost, time
   - Global resource visibility
   - Semaphore-based concurrency limits

4. **Workflow Templates**
   - 5 built-in patterns
   - Templates as Python functions
   - Template registry for discovery

5. **Workflow Orchestrator**
   - Main facade class
   - Integration with P2-11, P2-12, P2-13, P2-14

## Usage

### Basic Workflow Creation

```python
from omni.workflow import (
    Condition, NodeEdge, NodeType, WorkflowDefinition, WorkflowNode
)

# Create nodes
nodes = {
    "start": WorkflowNode(
        node_id="start",
        node_type=NodeType.TASK,
        task_id="analyze_task",
    ),
    "decision": WorkflowNode(
        node_id="decision",
        node_type=NodeType.IF,
        condition=Condition("variables['score'] > 0.8"),
        true_branch=["complex_path"],
        false_branch=["simple_path"],
    ),
}

# Create workflow
workflow = WorkflowDefinition(
    workflow_id="example",
    name="Example Workflow",
    nodes=nodes,
    entry_node_id="start",
    exit_node_ids=["end"],
    variables={"score": 0.9},
)
```

### Using Templates

```python
from omni.workflow import execute_template

# Execute built-in template
execution = execute_template(
    template_id="analyze_implement_test_review",
    parameters={
        "task_id": "fix_bug_123",
        "complexity_threshold": 0.7,
        "max_reviewers": 2,
    },
)

print(f"Status: {execution.status}")
print(f"Success: {execution.result.success}")
```

### Resource Management

```python
from omni.workflow import get_resource_manager

# Get global resource summary
manager = get_resource_manager()
summary = manager.get_global_summary()

print(f"Global concurrency usage: {summary['global_limits']['concurrency']['usage_percentage']}%")
print(f"Active workflows: {summary['active_workflows']}")
```

## Built-in Templates

1. **Analyze → Implement → Test → Review**
   - Standard pipeline for code changes
   - Conditional complexity threshold
   - Parallel review with consolidation

2. **Explore → Plan → Implement**
   - For understanding codebases
   - Exploration phase with focused targets
   - Strategic planning before implementation

3. **Parallel Review Chain**
   - Fan-out review workflow
   - Multiple agents review same artifact
   - Feedback consolidation with threshold

4. **Retry Until Success**
   - Resilient execution with retries
   - Exponential backoff between attempts
   - Configurable success conditions

5. **Safe Deploy with Rollback**
   - Deployment with pre-checks
   - Verification phase with timeout
   - Automatic rollback on failure

## Integration Points

### P2-14 Coordination Engine
- Enhanced `TaskGraph` with conditional edges
- Agent assignment with overrides
- Backward compatibility with `WorkflowPlan`

### P2-11 Parallel Engine
- Resource-constrained task execution
- Concurrency limits per workflow
- Priority-based scheduling

### P2-12 Model Routing
- LLM execution with token tracking
- Cost-aware workflow execution
- Model selection per task

### P2-13 Observability
- 9 new event types for workflow execution
- Real-time monitoring of control flow
- Resource usage tracking

## API Reference

### Core Classes

- `WorkflowDefinition` - Complete workflow graph
- `WorkflowNode` - Node in workflow (7 types)
- `WorkflowContext` - Runtime execution state
- `WorkflowStateMachine` - Execution engine
- `WorkflowOrchestrator` - Main facade
- `ResourceManager` - Global resource tracking
- `TemplateRegistry` - Reusable workflow patterns

### Node Types

1. **TASK** - Execute a single task
2. **PARALLEL** - Execute children concurrently
3. **SEQUENCE** - Execute children in order
4. **IF** - Conditional branch
5. **WHILE** - Loop while condition is true
6. **FOR_EACH** - Iterate over collection
7. **TRY_CATCH** - Error handling zone
8. **COMPENSATE** - Undo/rollback action
9. **SUB_WORKFLOW** - Reference to another workflow

## Examples

See `examples/workflow_example.py` for complete usage examples.

## Development

### Running Tests
```bash
pytest tests/workflow/ -v
```

### Code Quality
```bash
ruff check src/omni/workflow/
mypy src/omni/workflow/ --ignore-missing-imports
```

### Architecture Reference
See `docs/workflow-orchestration.md` for complete design documentation.