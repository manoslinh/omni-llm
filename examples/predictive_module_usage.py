"""
Example usage of the P2-16 Predictive Module.

This demonstrates how the predictive components work together
to track execution patterns, forecast demand, and detect bottlenecks.
"""

import sys
import time

# Add the project root to the Python path
sys.path.insert(0, ".")

from omni.scheduling.predictive import (
    BottleneckDetector,
    DemandForecaster,
    ExecutionRecord,
    WorkloadTracker,
)


def main() -> None:
    """Demonstrate predictive module usage."""
    print("=== P2-16 Predictive Module Demo ===\n")

    # 1. Create workload tracker
    tracker = WorkloadTracker(window_size=100)
    print("1. Created WorkloadTracker with 100-record window")

    # 2. Simulate some execution history
    print("\n2. Simulating execution history...")
    agents = ["coder", "reviewer", "thinker"]
    task_types = ["coding", "review", "analysis"]

    for i in range(15):
        record = ExecutionRecord(
            task_id=f"task_{i:03d}",
            agent_id=agents[i % 3],
            task_type=task_types[i % 3],
            complexity=0.5 + (i % 3) * 0.25,
            duration_seconds=15.0 + (i % 7) * 3.0,
            tokens_used=800 + (i % 10) * 100,
            cost=0.008 + (i % 3) * 0.004,
            success=(i % 12 != 0),  # One failure
        )
        tracker.record(record)
        time.sleep(0.01)  # Small delay to spread timestamps

    print(f"   Recorded {tracker.get_history_size()} execution records")

    # 3. Show agent statistics
    print("\n3. Agent Statistics:")
    for agent in agents:
        avg_duration = tracker.get_agent_avg_duration(agent)
        success_rate = tracker.get_agent_success_rate(agent)
        if avg_duration is not None:
            print(f"   - {agent}: avg duration={avg_duration:.1f}s, "
                  f"success rate={success_rate:.1%}")

    # 4. Create forecaster and make predictions
    print("\n4. Forecasting demand for pending tasks...")
    forecaster = DemandForecaster(tracker)

    pending_tasks = [
        {"agent_id": "coder", "task_type": "coding", "complexity": 1.0},
        {"agent_id": "coder", "task_type": "coding", "complexity": 1.0},
        {"agent_id": "reviewer", "task_type": "review", "complexity": 0.8},
        {"agent_id": "thinker", "task_type": "analysis", "complexity": 1.2},
        {"agent_id": "thinker", "task_type": "analysis", "complexity": 1.0},
    ]

    forecast = forecaster.forecast(pending_tasks, time_horizon_seconds=600)

    print(f"   Estimated tasks: {forecast.estimated_tasks}")
    print(f"   Peak concurrency: {forecast.estimated_concurrent_peak}")
    print(f"   Total cost estimate: ${forecast.estimated_total_cost:.4f}")
    print(f"   Total duration: {forecast.estimated_duration_seconds:.1f}s")
    print(f"   Confidence: {forecast.confidence:.1%}")
    print(f"   Bottleneck agents: {forecast.bottleneck_agents}")

    # 5. Create bottleneck detector and monitor queue
    print("\n5. Monitoring for bottlenecks...")
    detector = BottleneckDetector(tracker)

    # Simulate queue depth changes
    queue_depths = [2, 3, 5, 7, 9, 12, 15, 18, 20, 22]
    for depth in queue_depths:
        detector.sample_queue_depth(depth)
        time.sleep(0.05)

    # Check for bottlenecks
    report = detector.detect()

    if report["has_bottleneck"]:
        print("   ⚠️  Bottlenecks detected:")
        for bottleneck in report["bottlenecks"]:
            print(f"     - {bottleneck['type']}: {bottleneck['detail']}")
        print("   Suggestions:")
        for suggestion in report["suggestions"]:
            print(f"     • {suggestion}")
    else:
        print("   ✅ No bottlenecks detected")

    # 6. Show queue trend
    trend = detector.get_queue_trend()
    print(f"\n6. Queue trend: {trend}")

    # 7. Show throughput
    throughput_5m = tracker.get_throughput(300)
    throughput_1m = tracker.get_throughput(60)
    print("\n7. Throughput:")
    print(f"   - Last 5 minutes: {throughput_5m:.3f} tasks/second")
    print(f"   - Last 1 minute: {throughput_1m:.3f} tasks/second")

    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    main()
