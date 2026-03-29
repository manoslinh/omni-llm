# Scheduling Policies (P2-16 Component 1)

## Overview

Scheduling policies determine the order in which ready tasks are executed. This component implements 6 pluggable scheduling policies that can be used with the P2-11 scheduler.

## Available Policies

### 1. FIFOPolicy (`"fifo"`)
- **Description**: First In, First Out (backward compatible with P2-11)
- **Behavior**: Executes tasks in the order they become ready
- **Use case**: Simple workloads, backward compatibility

### 2. PriorityPolicy (`"priority"`)
- **Description**: Highest priority tasks first
- **Behavior**: Sorts tasks by `Task.priority` (higher number = higher priority)
- **Use case**: Workloads with clear priority distinctions

### 3. DeadlinePolicy (`"deadline"`)
- **Description**: Earliest deadline first
- **Behavior**: Tasks with nearer deadlines execute first. Tasks without deadlines have lowest priority.
- **Use case**: Time-sensitive workloads, real-time systems
- **Note**: Deadlines are set in task context: `task.context = {"deadline": timestamp}`

### 4. CostAwarePolicy (`"cost_aware"`)
- **Description**: Cost/budget optimization
- **Behavior**: Prefers cheaper tasks when budget is tight, behaves like FIFO when budget is plentiful
- **Use case**: Cost-constrained workloads, budget management

### 5. FairPolicy (`"fair"`)
- **Description**: Fair resource distribution across workflows
- **Behavior**: Prevents one workflow from monopolizing resources by penalizing overrepresented workflows
- **Use case**: Multi-tenant systems, fair resource sharing

### 6. BalancedPolicy (`"balanced"`)
- **Description**: Weighted combination of all factors (default)
- **Behavior**: Combines priority, deadline, cost, fairness, and agent availability with configurable weights
- **Default weights**: priority=0.30, deadline=0.25, cost=0.20, fairness=0.10, agent=0.15
- **Use case**: General-purpose workloads, balanced trade-offs

## Usage

### Basic Usage

```python
from src.omni.scheduling.policies import get_policy
from src.omni.execution.scheduler import Scheduler

# Get a policy by name
policy = get_policy("priority")

# Or with custom parameters (for BalancedPolicy)
policy = get_policy("balanced", 
    priority_weight=0.4,
    deadline_weight=0.3,
    cost_weight=0.1,
    fairness_weight=0.1,
    agent_weight=0.1,
)

# Use with scheduler
scheduler = Scheduler(
    graph=task_graph,
    config=config,
    task_executor=executor,
    on_task_complete=callback,
    on_propagate_skip=skip_callback,
    policy=policy,  # Optional, defaults to FIFO
)
```

### Backward Compatibility

The scheduler defaults to `FIFOPolicy` when no policy is specified, maintaining backward compatibility with P2-11.

```python
# This uses FIFO (P2-11 default behavior)
scheduler = Scheduler(
    graph=task_graph,
    config=config,
    task_executor=executor,
    on_task_complete=callback,
    on_propagate_skip=skip_callback,
    # policy parameter omitted
)
```

### Task Configuration

Tasks can provide scheduling hints through their context:

```python
from src.omni.task.models import Task
import time

# Task with priority and deadline
task = Task(
    description="Urgent task",
    priority=10,  # Higher number = higher priority
    context={
        "deadline": time.time() + 300,  # 5 minutes from now
        "preferred_agent": "coder",  # Hint for agent availability scoring
    }
)
```

## Integration Points

### P2-11 Scheduler Integration
- Modified `Scheduler.__init__` to accept optional `policy` parameter
- Modified `_get_ready_tasks()` to use policy ranking instead of simple priority sort
- Added `_build_scheduling_context()` to provide policy context
- Added `scheduling_decisions` list for observability

### Changes to Scheduler (≈15 lines)
1. Added import for scheduling policies
2. Added `policy` parameter to `__init__` (defaults to `FIFOPolicy`)
3. Added `scheduling_decisions` list
4. Modified `_get_ready_tasks()` to use policy ranking
5. Added `_build_scheduling_context()` method

### P2-15 Workflow Resource Budgets
Policies can access workflow resource budgets via `SchedulingContext.cost_budget_remaining` for cost-aware scheduling.

### P2-13 Observability
Scheduling decisions are recorded in `scheduler.scheduling_decisions` for observability and debugging.

## API Reference

### `SchedulingPolicyBase` (Abstract Base Class)
```python
class SchedulingPolicyBase(ABC):
    @abstractmethod
    def rank_tasks(self, context: SchedulingContext) -> List[SchedulingScore]
    @property
    @abstractmethod
    def name(self) -> str
```

### `SchedulingContext`
```python
@dataclass
class SchedulingContext:
    ready_tasks: List[Task]
    running_tasks: Dict[str, Any]  # task_id → execution info
    workflow_id: str
    resource_snapshot: Dict[str, Any]
    agent_availability: Dict[str, bool]
    deadline_info: Dict[str, Optional[float]]
    cost_budget_remaining: Optional[float]
    execution_history: List[Dict[str, Any]]
```

### `SchedulingScore`
```python
@dataclass
class SchedulingScore:
    task_id: str
    composite_score: float  # Higher = more urgent
    priority_score: float = 0.0
    deadline_score: float = 0.0
    cost_score: float = 0.0
    fairness_score: float = 0.0
    agent_availability_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### Factory Functions
```python
def get_policy(name: str, **kwargs) -> SchedulingPolicyBase
def list_policies() -> List[str]
```

## Testing

### Unit Tests
```bash
cd projects/omni-llm
python3 -m pytest tests/test_scheduling_policies.py -v
```

### Integration Tests
```bash
cd projects/omni-llm
python3 -m pytest tests/test_scheduling_integration.py -v
```

### Example
```bash
cd projects/omni-llm
python3 examples/scheduling_policies_example.py
```

## Design Decisions

1. **Pluggable Architecture**: Policies are separate classes that can be easily added or modified
2. **Backward Compatibility**: Defaults to FIFO policy, identical to P2-11 behavior
3. **Zero Dependencies**: Pure Python with asyncio, no external dependencies
4. **Observability**: All scheduling decisions are recorded for debugging and analysis
5. **Configurable**: Policies can be configured via constructor parameters
6. **Extensible**: New policies can be added by extending `SchedulingPolicyBase`

## Performance Considerations

- Policy ranking is O(n) for simple policies, O(n log n) for sorting
- Context building is O(n) where n is number of ready tasks
- Memory usage is minimal (scores are small dataclasses)
- No I/O operations in policy ranking (all in-memory)

## Future Extensions

1. **Dynamic Policy Switching**: Switch policies at runtime based on workload
2. **Policy Composition**: Combine multiple policies (e.g., priority within deadline buckets)
3. **Machine Learning**: Learn optimal scheduling from execution history
4. **Distributed Scheduling**: Coordinate scheduling across multiple nodes
5. **QoS Guarantees**: Provide quality-of-service guarantees for different workflow classes