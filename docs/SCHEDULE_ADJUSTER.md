# Schedule Adjuster Component

## Overview

The Schedule Adjuster is a real-time adjustment engine for task scheduling that provides runtime optimizations for:
- **Failure Recovery**: Automatic reassignment of failed tasks
- **Deadline Pressure**: Priority escalation as deadlines approach  
- **Capacity Bursting**: Dynamic resource allocation for workload surges

## Architecture

### Core Components

```python
from src.omni.scheduling.adjuster import ScheduleAdjuster

# Create adjuster with optional matcher
adjuster = ScheduleAdjuster(matcher=task_matcher)
```

### Adjustment Types

| Type | Description | Trigger |
|------|-------------|---------|
| `RESCHEDULE` | Re-prioritize and retry task | Transient failures, normal deadlines |
| `REASSIGN` | Change agent assignment | Permanent failures, critical deadlines |
| `ESCALATE` | Escalate to higher-tier agent | When reassignment unavailable |
| `BURST` | Temporarily increase capacity | Workload surges, parallel processing needs |

## Integration Points

### P2-14 Agent Matcher
```python
class TaskMatcherProtocol(Protocol):
    async def match(self, task: Task) -> dict[str, Any]:
        """Match task to optimal agent."""
```

### P2-13 Monitoring
All adjustments are logged and available via:
- `get_adjustment_history()` - Complete adjustment log
- `get_adjustment_summary()` - Statistics by adjustment type
- `get_active_bursts()` - Currently active capacity bursts

### Resource Pool Integration
Capacity bursting integrates with the global resource manager to:
- Request additional concurrent slots
- Automatically release capacity after duration
- Track burst expiration

## Usage Examples

### 1. Failure Recovery
```python
# Handle task failure
result = await adjuster.adjust_for_failure(
    task=failed_task,
    failure_reason="Rate limit exceeded",
)

# Result contains adjustment details
print(f"Adjustment: {result.adjustment.adjustment_type}")
print(f"Details: {result.adjustment.details}")
```

### 2. Deadline Pressure
```python
# Escalate task approaching deadline
result = await adjuster.adjust_for_deadline_pressure(
    task=urgent_task,
    time_remaining=30.0,  # 30 seconds remaining
)

# Urgency levels: overdue, critical, high, normal
urgency = result.adjustment.details["urgency"]
```

### 3. Capacity Bursting
```python
# Request temporary capacity increase
result = await adjuster.adjust_for_capacity_needs(
    workflow_id="data-import-001",
    additional_resources={
        "concurrent": 3,
        "duration_seconds": 300,
        "reason": "Data import backlog",
    },
)
```

## Configuration

### Adjustment Thresholds
The adjuster uses configurable thresholds:

| Threshold | Default | Description |
|-----------|---------|-------------|
| Transient failure detection | Automatic | Based on error message patterns |
| Critical deadline | < 60s | Triggers reassignment |
| High deadline | 60-300s | Triggers reschedule |
| Default burst duration | 300s | 5 minutes capacity boost |

### Failure Classification
- **Transient**: Rate limits, timeouts, network issues (→ reschedule)
- **Permanent**: Authentication, invalid input, syntax errors (→ reassign)

## Observability

### Metrics
- Adjustment counts by type
- Failure recovery success rate
- Deadline escalation frequency
- Active capacity bursts

### Logging
All adjustments are logged with:
- Timestamp
- Task/Workflow ID
- Adjustment type and reason
- Details (urgency, resources, etc.)

## Testing

### Unit Tests
```bash
# Run all adjuster tests
pytest tests/test_schedule_adjuster.py -v

# Run specific test category
pytest tests/test_schedule_adjuster.py::TestFailureRecovery -v
```

### Integration Tests
Tests cover:
- Failure recovery scenarios
- Deadline pressure handling
- Capacity bursting lifecycle
- Concurrent adjustment safety

## Dependencies

- **Required**: Python 3.12+, asyncio
- **Optional**: P2-14 TaskMatcher for agent reassignment
- **Zero new dependencies**: Uses existing omni-llm infrastructure

## Performance

- **Async**: Non-blocking adjustment operations
- **Thread-safe**: Lock-protected shared state
- **Memory-efficient**: Bounded adjustment history
- **Scalable**: Designed for high-volume scheduling

## Error Handling

### Graceful Degradation
- Matcher unavailable → fallback to reschedule
- Resource pool full → queue burst requests
- Invalid inputs → log and continue

### Recovery
- Failed adjustments are logged but don't crash
- Burst cleanup handles expired resources
- History provides audit trail for debugging

## Example Workflow

```python
# Complete adjustment workflow
async def handle_task_crisis(task, failure_reason, time_remaining):
    # 1. Recover from failure
    await adjuster.adjust_for_failure(task, failure_reason)
    
    # 2. Escalate for deadline
    await adjuster.adjust_for_deadline_pressure(task, time_remaining)
    
    # 3. Request capacity burst
    await adjuster.adjust_for_capacity_needs(
        workflow_id=task.workflow_id,
        additional_resources={"concurrent": 2, "duration_seconds": 600},
    )
    
    # 4. Monitor results
    summary = adjuster.get_adjustment_summary()
    return summary
```

## Related Components

- **P2-14 TaskMatcher**: Agent assignment for reassignment
- **P2-13 Monitoring**: Observability data collection
- **Resource Pool**: Capacity management for bursting
- **Predictive Module**: Early warning for deadline pressure