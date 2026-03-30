# P2-16 Predictive Module

## Overview

The Predictive Module is a lightweight statistical forecasting system for the P2-16 Advanced Scheduling & Resource Management architecture. It provides three core components:

1. **WorkloadTracker** - Tracks execution history for pattern analysis
2. **DemandForecaster** - Forecasts resource demand based on workload patterns  
3. **BottleneckDetector** - Detects resource bottlenecks in real-time

## Key Features

- **No ML dependencies** - Uses pure statistical methods (moving averages, trend detection)
- **Lightweight and fast** - Minimal overhead, suitable for real-time scheduling
- **Configurable window sizes** - Adjustable history windows for different workloads
- **Zero new dependencies** - Uses only Python standard library collections
- **Integration-ready** - Designed to plug into existing P2-11/14/15 interfaces

## Architecture

```
┌─────────────────────────────────┐
│      Predictive Module          │
│                                 │
│  ┌─────────────────────────┐   │
│  │    WorkloadTracker      │   │
│  │  • Sliding window       │   │
│  │  • Per-agent stats      │   │
│  │  • Per-type stats       │   │
│  │  • Throughput tracking  │   │
│  └───────────┬─────────────┘   │
│              │                  │
│  ┌───────────▼─────────────┐   │
│  │    DemandForecaster     │   │
│  │  • Moving average       │   │
│  │  • Trend detection      │   │
│  │  • Confidence scoring   │   │
│  │  • Bottleneck prediction│   │
│  └───────────┬─────────────┘   │
│              │                  │
│  ┌───────────▼─────────────┐   │
│  │   BottleneckDetector    │   │
│  │  • Queue growth         │   │
│  │  • Success rate drops   │   │
│  │  • Throughput decline   │   │
│  │  • Real-time alerts     │   │
│  └─────────────────────────┘   │
└─────────────────────────────────┘
```

## Components

### ExecutionRecord
```python
@dataclass
class ExecutionRecord:
    task_id: str
    agent_id: str
    task_type: str
    complexity: float
    duration_seconds: float
    tokens_used: int
    cost: float
    success: bool
    completed_at: float
    workflow_id: str = ""
```

### WorkloadTracker
Maintains a sliding window of execution history with configurable size (default: 500 records).

**Key Methods:**
- `record(record: ExecutionRecord)` - Add a completed execution
- `get_agent_avg_duration(agent_id: str)` - Average duration per agent
- `get_agent_success_rate(agent_id: str)` - Success rate per agent (0.0-1.0)
- `get_type_avg_duration(task_type: str)` - Average duration per task type
- `get_throughput(window_seconds: float)` - Tasks completed per second

### DemandForecaster
Forecasts resource demand using moving averages and historical patterns.

**Key Methods:**
- `forecast(pending_tasks, time_horizon_seconds)` - Generate workload forecast
- Returns `WorkloadForecast` with estimates for tasks, concurrency, cost, duration

### BottleneckDetector
Monitors system metrics to identify constraints in real-time.

**Detects:**
- Growing queue depth (5 consecutive increases)
- Low agent success rates (< 50%)
- Declining throughput (> 50% drop in 1m vs 5m)
- Provides actionable suggestions for each bottleneck

## Integration Points

### With P2-13 Observability
- Execution records should be emitted as P2-13 events
- Bottleneck alerts should trigger observability notifications
- Forecasts can be visualized in dashboards

### With Scheduling Policies
- Forecasts inform priority and deadline scheduling decisions
- Bottleneck detection triggers schedule adjustments
- Historical patterns guide policy selection

### With Resource Management
- Demand forecasts feed into capacity planning
- Bottleneck detection informs resource allocation
- Agent performance data guides load balancing

## Usage Example

```python
from omni.scheduling.predictive import (
    WorkloadTracker, DemandForecaster, BottleneckDetector, ExecutionRecord
)

# Track execution history
tracker = WorkloadTracker()
tracker.record(ExecutionRecord(
    task_id="task1", agent_id="coder", task_type="coding",
    duration_seconds=30.0, cost=0.01, success=True, ...
))

# Forecast demand
forecaster = DemandForecaster(tracker)
forecast = forecaster.forecast([
    {"agent_id": "coder", "task_type": "coding"},
    {"agent_id": "reviewer", "task_type": "review"},
])

# Detect bottlenecks
detector = BottleneckDetector(tracker)
detector.sample_queue_depth(5)
report = detector.detect()
if report["has_bottleneck"]:
    print(f"Bottleneck: {report['bottlenecks'][0]['type']}")
```

## Testing

The module includes comprehensive tests covering:
- Unit tests for each component
- Integration tests with mock execution data
- Forecast accuracy validation
- Bottleneck detection scenarios

Run tests with:
```bash
pytest tests/test_predictive_module.py -v
```

## Configuration

### WorkloadTracker
- `window_size`: Number of execution records to keep (default: 500)
- Per-agent windows: 100 records per agent
- Per-type windows: 100 records per task type

### DemandForecaster
- `time_horizon_seconds`: Forecast window (default: 300 seconds)
- Confidence calculation: `min(1.0, history_size / 100)`
- Default estimates when no history available

### BottleneckDetector
- Queue depth window: 60 samples
- Detection thresholds configurable via code
- Severity levels: "high", "medium" based on impact

## Performance Considerations

- **Memory**: O(n) where n = window_size + agents × 100 + types × 100
- **CPU**: O(1) for record operations, O(m) for forecasting where m = pending tasks
- **Thread Safety**: Not thread-safe by default (use locks if needed)
- **Persistence**: In-memory only (consider database for long-term history)

## Future Extensions

1. **Seasonal Patterns**: Day-of-week, time-of-day adjustments
2. **Cross-Workflow Analysis**: Pattern correlation across workflows
3. **Predictive Scaling**: Auto-scale resources based on forecasts
4. **Anomaly Detection**: Statistical outlier detection
5. **A/B Testing**: Compare scheduling policy effectiveness

## See Also

- [P2-16 Architecture](../docs/P2-16-ARCHITECTURE.md) - Full architecture design
- [Example Usage](../examples/predictive_module_usage.py) - Working demo
- [Test Suite](../tests/test_predictive_module.py) - Comprehensive tests