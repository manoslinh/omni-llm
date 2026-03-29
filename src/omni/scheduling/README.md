# P2-16: Global Resource Manager - ResourcePool

## Overview

The `ResourcePool` component is part of P2-16: Advanced Scheduling & Resource Management. It provides a global resource management layer that wraps P2-15's `ResourceManager` to enable:

- **Cross-workflow capacity tracking** - View and manage resources across all active workflows
- **Priority-based preemption** - Steal slots from lower-priority workflows when needed
- **Resource contention resolution** - Handle conflicts when demand exceeds capacity
- **Thread-safe operations** - Safe concurrent access from multiple workflows
- **Rate limiting** - Token and cost usage tracking with window-based limits
- **Agent capacity management** - Per-agent concurrency limits

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                 Global Resource Manager                  │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │               ResourcePool                      │   │
│  │  • Global capacity tracking                     │   │
│  │  • Priority-based allocation                    │   │
│  │  • Slot stealing/preemption                     │   │
│  │  • Rate limiting (tokens/cost)                  │   │
│  │  • Agent capacity limits                        │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │           P2-15 ResourceManager                 │   │
│  │  (wrapped for backward compatibility)           │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Key Features

### 1. Global Capacity Tracking
- Tracks total concurrent slots across all workflows
- Monitors token usage per minute and cost per hour
- Provides real-time utilization metrics

### 2. Priority-Based Allocation
- Workflows specify priority (0-10, higher = more important)
- High-priority workflows get resources first
- When pool is full, low-priority workflows wait

### 3. Slot Stealing (Preemption)
- High-priority workflows can steal slots from lower-priority ones
- Steals one slot at a time to avoid starvation
- Logs all preemption events for observability

### 4. Thread-Safe Operations
- Uses `asyncio.Lock` for all state modifications
- Safe for concurrent access from multiple workflows
- No race conditions in allocation/deallocation

### 5. Rate Limiting
- Tracks token usage with 60-second sliding window
- Tracks cost usage with 1-hour sliding window
- Prevents API rate limit violations and cost overruns

### 6. Agent Capacity Management
- Set per-agent maximum concurrent tasks
- Useful for agents with limited capacity (e.g., GPU-bound models)
- Integrated with overall pool limits

## Usage

### Basic Allocation

```python
from omni.scheduling.resource_pool import ResourcePool

# Create a pool with 10 concurrent slots
pool = ResourcePool(max_total_concurrent=10)

# Allocate resources for a workflow
success = await pool.allocate(
    workflow_id="wf-001",
    resources={"concurrent": 3},
    priority=7  # Medium-high priority
)

# Check if workflow can run another task
can_run = await pool.can_allocate(concurrent=1)

# Deallocate when workflow completes
await pool.deallocate(
    workflow_id="wf-001",
    resources={"concurrent": 3}
)
```

### Priority-Based Preemption

```python
# Low-priority workflow gets resources
await pool.allocate(
    workflow_id="wf-low",
    resources={"concurrent": 5},
    priority=2
)

# High-priority workflow needs resources (pool is full)
# Try to steal a slot
success, message = await pool.steal_slot(
    from_workflow_id="wf-low",
    to_workflow_id="wf-high"
)
```

### Resource Usage Tracking

```python
# Set rate limits
pool = ResourcePool(
    max_total_concurrent=10,
    max_total_tokens_per_minute=50000,
    max_total_cost_per_hour=10.0
)

# Record usage after task execution
await pool.record_usage(tokens=1500, cost=0.15)

# Check available capacity
capacity = pool.get_available_capacity()
# {'concurrent': 9, 'tokens_per_minute': 48500, 'cost_per_hour': 9.85}
```

### Agent Capacity Management

```python
# Set agent-specific limits
await pool.set_agent_capacity("coder", 3)
await pool.set_agent_capacity("reviewer", 2)

# Get agent capacity
coder_cap = await pool.get_agent_capacity("coder")  # Returns 3
```

## Integration with P2-15

The `ResourcePool` is designed to wrap P2-15's `ResourceManager`:

1. **Additive, not replacement** - Doesn't replace existing P2-15 code
2. **Backward compatible** - Existing workflows continue to work
3. **Enhanced visibility** - Adds cross-workflow resource tracking
4. **Priority awareness** - Adds priority-based scheduling missing in P2-15

### Integration Example

```python
# P2-15 style (existing code)
from omni.workflow.resources import ResourceManager

resource_manager = ResourceManager(global_max_concurrent=20)
budget = resource_manager.create_budget(
    execution_id="wf-001",
    max_concurrent=5
)

# P2-16 enhanced (new code)
from omni.scheduling.resource_pool import ResourcePool

pool = ResourcePool(max_total_concurrent=20)
success = await pool.allocate(
    workflow_id="wf-001",
    resources={"concurrent": 5},
    priority=7
)

# Still use P2-15 ResourceManager for workflow-level tracking
budget = resource_manager.create_budget(
    execution_id="wf-001",
    max_concurrent=5
)
```

## Testing

The implementation includes comprehensive tests:

- **Unit tests** (`test_resource_pool.py`) - Test individual methods
- **Integration tests** (`test_resource_pool_integration.py`) - Test with P2-15 components
- **Demo script** (`examples/resource_pool_demo.py`) - End-to-end demonstration

Run tests with:
```bash
pytest tests/test_resource_pool.py -v
pytest tests/test_resource_pool_integration.py -v
python examples/resource_pool_demo.py
```

## Design Decisions

### 1. Async Interface
- All methods are `async` to support concurrent access
- Uses `asyncio.Lock` for thread safety
- Compatible with async/await patterns in the codebase

### 2. Dictionary-Based Resources
- Resources specified as dict for flexibility
- Can add new resource types without API changes
- Easy to serialize/deserialize

### 3. Simple Priority System
- Integer priorities (0-10)
- Higher number = higher priority
- Simple to understand and use

### 4. Conservative Preemption
- Steals one slot at a time
- Prevents starvation of low-priority workflows
- Logs all preemption events for debugging

### 5. No External Dependencies
- Pure Python implementation
- No database or external services required
- Easy to deploy and test

## Future Enhancements

1. **Persistent storage** - Save pool state to database for recovery
2. **Dynamic resizing** - Adjust pool capacity at runtime
3. **Workflow groups** - Group workflows for hierarchical resource allocation
4. **Advanced preemption** - Consider workflow progress when preempting
5. **Integration with P2-13** - Export metrics to observability dashboard

## Performance Characteristics

- **Allocation/Deallocation**: O(1) with lock contention
- **Memory usage**: O(n) where n = number of active workflows
- **Concurrent access**: Safe with `asyncio.Lock`
- **Rate limiting**: O(1) with periodic window resets

## Error Handling

- **Insufficient capacity**: Returns `False` from `allocate()`
- **Invalid workflow ID**: Silently ignores in `deallocate()`
- **Rate limit exceeded**: Doesn't prevent allocation, just tracks usage
- **Concurrent modification**: Protected by locks, no data corruption