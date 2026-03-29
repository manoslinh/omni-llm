# P2-16: Advanced Scheduling & Resource Management

## Overview

Implementation of advanced scheduling and resource management for the Omni-LLM orchestration system. This provides pluggable scheduling policies, global resource management, predictive scheduling, and real-time schedule adjustments.

## Architecture Components

### 1. Pluggable Scheduling Policies (`src/omni/execution/policies.py`)

Six scheduling policies for different workload characteristics:

- **FIFO**: First In, First Out (P2-11 default behavior)
- **Priority**: Highest priority tasks first
- **Deadline**: Earliest deadline first
- **CostAware**: Minimize total cost within constraints
- **Fair**: Fair distribution across workflows
- **Balanced**: Weighted combination of all factors (default)

**Integration**: Modified `Scheduler` class in `src/omni/execution/scheduler.py` to accept a policy parameter and use it for task ranking.

### 2. Global Resource Manager (`src/omni/scheduling/resource_pool.py`)

Manages resources across all active workflows:

- **ResourcePool**: Global capacity tracking with rate limiting
- **GlobalResourceManager**: Priority-based allocation and preemption
- **WorkflowQuota**: Per-workflow resource guarantees

**Integration**: Wraps P2-15's `ResourceManager` for cross-workflow visibility and contention resolution.

### 3. Predictive Module (`src/omni/scheduling/predictive.py`)

Lightweight forecasting and bottleneck detection:

- **WorkloadTracker**: Sliding window execution history
- **DemandForecaster**: Moving-average resource demand forecasts
- **BottleneckDetector**: Real-time queue and throughput analysis

### 4. Schedule Adjuster (`src/omni/scheduling/adjuster.py`)

Real-time schedule adjustments:

- **ScheduleAdjuster**: Reacts to failures, deadlines, and capacity needs
- **Adjustment types**: Reschedule, reassign, escalate, renegotiate, burst
- **Integration**: Works with P2-14 agent matcher for task reassignment

## Usage Examples

### Using Different Scheduling Policies

```python
from omni.execution.policies import get_policy
from omni.execution.engine import ParallelExecutionEngine

# Create engine with specific policy
policy = get_policy("balanced")  # or "priority", "deadline", etc.
engine = ParallelExecutionEngine(
    graph=task_graph,
    executor=executor,
    policy=policy,  # Pass policy to engine
)
```

### Global Resource Management

```python
from omni.scheduling.resource_pool import GlobalResourceManager

manager = GlobalResourceManager()

# Create workflow budget
budget = await manager.create_workflow_budget(
    execution_id="wf-001",
    requested_concurrent=5,
    priority=7,
)

# Check capacity during scheduling
if manager.check_capacity("wf-001", task_concurrent=1):
    # Schedule task
    pass

# Release budget when done
await manager.release_workflow_budget("wf-001")
```

### Predictive Scheduling

```python
from omni.scheduling.predictive import WorkloadTracker, DemandForecaster

tracker = WorkloadTracker()
forecaster = DemandForecaster(tracker)

# Record execution history
tracker.record(execution_record)

# Forecast demand
forecast = forecaster.forecast(pending_tasks, time_horizon_seconds=300)
print(f"Estimated peak concurrency: {forecast.estimated_concurrent_peak}")
```

### Real-time Adjustments

```python
from omni.scheduling.adjuster import ScheduleAdjuster

adjuster = ScheduleAdjuster()

# Handle task failure
result = await adjuster.handle_task_failure(
    task=failed_task,
    current_agent="coder",
    error="Rate limit exceeded",
)

# Escalate for deadline
result = await adjuster.escalate_for_deadline(
    task=urgent_task,
    seconds_remaining=30,
)
```

## Backward Compatibility

- **Default behavior**: FIFO policy maintains P2-11 scheduling behavior
- **Optional integration**: All new features are opt-in via constructor parameters
- **No breaking changes**: Existing code continues to work unchanged

## Testing

Comprehensive test coverage:

```
tests/scheduling/test_policies.py        # Scheduling policy tests
tests/scheduling/test_global_resources.py # Resource manager tests
tests/scheduling/test_predictive.py      # Predictive module tests
tests/scheduling/test_adjuster.py        # Schedule adjuster tests
```

Run tests with:
```bash
pytest tests/scheduling/ -v
```

## Performance Characteristics

- **Efficiency**: All algorithms O(n log n) or better
- **Memory**: Sliding windows limit history size
- **Concurrency**: Thread-safe resource management
- **Zero dependencies**: Pure Python with asyncio

## Integration Points

1. **P2-11 Scheduler**: Modified to accept scheduling policies
2. **P2-14 Agent Matcher**: Used for task reassignment
3. **P2-15 ResourceManager**: Wrapped for global visibility
4. **P2-13 Observability**: Scheduling decisions logged for monitoring

## Configuration

Default configuration can be tuned via:

```python
# Balanced policy with custom weights
from omni.execution.policies import BalancedPolicy
policy = BalancedPolicy(
    priority_weight=0.40,
    deadline_weight=0.30,
    cost_weight=0.15,
    fairness_weight=0.10,
    agent_weight=0.05,
)

# Resource pool with custom capacity
from omni.scheduling.resource_pool import ResourcePool
pool = ResourcePool(
    max_total_concurrent=50,
    max_total_cost_per_hour=100.0,
)
```

## Demo

See `examples/scheduling_demo.py` for a complete demonstration of all features.

## Future Extensions

1. **ML-based forecasting**: Replace moving averages with simple regression
2. **Dynamic policy switching**: Auto-select policy based on workload
3. **Cost optimization**: Integrate with provider cost tracking
4. **Multi-cluster scheduling**: Extend resource pool across nodes