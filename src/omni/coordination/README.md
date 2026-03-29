# Multi-Agent Coordination Engine

The coordination engine matches tasks to specialized agents based on capabilities, complexity, and cost, then creates parallel execution workflows with review steps.

## Architecture Overview

```
TaskGraph → CoordinationEngine → WorkflowPlan → Parallel Execution
    │              │                   │
    ▼              ▼                   ▼
Decomposition   Agent Matching    Wave Scheduling
(P2-08)         (Capabilities)    (P2-11)
```

## Core Components

### 1. Agent Definitions (`agents.py`)
- **`AgentProfile`**: Declarative description of a specialized agent
- **`AgentRegistry`**: Registry of available agents with capabilities
- **`DEFAULT_AGENTS`**: From AGENTS.md: Intern, Coder, Reader, Visual, Thinker

### 2. Task Matching (`matcher.py`)
- **`TaskMatcher`**: Weighted scoring algorithm (capability 40%, complexity 25%, cost 20%, priority 15%)
- **`AgentAssignment`**: Result of matching a task to an agent with confidence score

### 3. Workflow Orchestration (`workflow.py`)
- **`WorkflowOrchestrator`**: Converts `TaskGraph` into `WorkflowPlan`
- **`WorkflowPlan`**: Parallel execution waves with review steps
- **`WorkflowStep`**: Individual execution step (sequential, parallel, review, etc.)

### 4. Coordination Engine (`engine.py`)
- **`CoordinationEngine`**: Main facade that ties everything together
- **`CoordinationObserver`**: Protocol for P2-13 observability integration
- **`CoordinationResult`**: Complete coordination result with plan and assignments

## Usage Example

```python
from omni.coordination import CoordinationEngine
from omni.task.models import TaskGraph

# Create coordination engine
engine = CoordinationEngine()

# Coordinate a task graph
result = engine.coordinate(task_graph, plan_id="my-plan")

# Get the execution plan
plan = result.plan
waves = plan.get_execution_order()  # Parallel execution waves

# Get agent assignments
assignments = result.assignments  # task_id → AgentAssignment
```

## Agent Capabilities

| Capability | Description | Agents |
|------------|-------------|--------|
| `code_generation` | Write code | Coder |
| `code_review` | Review code | Coder, Reader, Thinker |
| `testing` | Write tests | Coder |
| `formatting` | Format code | Intern |
| `extraction` | Extract data | Intern, Reader |
| `long_context` | Long document analysis | Reader |
| `vision` | Image analysis | Visual |
| `image_analysis` | Analyze images | Visual |
| `architecture` | System design | Thinker |
| `reasoning` | Complex reasoning | Thinker |
| `debugging` | Debug code | Coder, Thinker |
| `documentation` | Write docs | Intern, Reader |
| `refactoring` | Refactor code | Coder, Thinker |

## Escalation Chain

Tasks can be escalated up the chain when they fail:
```
Intern → Coder → Reader → Thinker
```

Specialists (Visual) escalate directly to Thinker.

## Review Protocol

Implementation tasks get automatic review steps:
- Intern → Coder review
- Coder → Reader review  
- Reader → Thinker review
- Thinker → Self-review

## Integration Points

- **Input**: `TaskGraph` from P2-08 decomposition
- **Scoring**: `ComplexityEstimate.overall_score` + `.tier`
- **Execution**: `WorkflowPlan` waves → P2-11 parallel engine
- **Routing**: `AgentProfile.model_id` → P2-12 `ModelRouter`
- **Events**: `CoordinationObserver` → P2-13 observability

## Configuration

```python
from omni.coordination import CoordinationConfig, MatcherConfig

config = CoordinationConfig(
    matcher_config=MatcherConfig(
        capability_weight=0.4,
        complexity_weight=0.25,
        cost_weight=0.2,
        priority_weight=0.15,
    ),
    enable_reviews=True,
    enable_specialist_routing=True,
    max_parallel_per_step=5,
    auto_escalate_on_failure=True,
)

engine = CoordinationEngine(config=config)
```

## Testing

Run the full test suite:
```bash
pytest tests/coordination/ -v
```

Run CI checks:
```bash
ruff check .
mypy src/omni/coordination --ignore-missing-imports
pytest tests/coordination/ -v
```