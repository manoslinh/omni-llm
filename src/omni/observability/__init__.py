"""
Observability & Live Visualization for Parallel Execution Engine.

Provides real-time feedback, visualization, metrics, and performance tuning
for the Omni-LLM parallel execution engine.
"""

from .cli import register_execute_command
from .dashboard import DashboardConfig, LiveDashboard, create_dashboard_callback
from .mermaid import (
    MermaidSnapshotConfig,
    MermaidSnapshotter,
    create_mermaid_callback,
    generate_execution_animation,
)
from .metrics import MetricsAnalyzer, PerformanceMetrics, generate_performance_report
from .replay import ExecutionReplayer, ReplayConfig, replay_execution
from .tuning import (
    AdaptiveConcurrencyController,
    PerformanceOptimizer,
    TuningConfig,
    create_adaptive_callback,
)

__all__ = [
    # Dashboard
    "LiveDashboard",
    "DashboardConfig",
    "create_dashboard_callback",
    # Mermaid visualization
    "MermaidSnapshotter",
    "MermaidSnapshotConfig",
    "create_mermaid_callback",
    "generate_execution_animation",
    # Execution replay
    "ExecutionReplayer",
    "ReplayConfig",
    "replay_execution",
    # Metrics and analytics
    "MetricsAnalyzer",
    "PerformanceMetrics",
    "generate_performance_report",
    # Performance tuning
    "AdaptiveConcurrencyController",
    "PerformanceOptimizer",
    "TuningConfig",
    "create_adaptive_callback",
    # CLI integration
    "register_execute_command",
]

__version__ = "0.1.0"
