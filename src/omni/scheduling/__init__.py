"""
Advanced scheduling and resource management for P2-16.

Provides:
- GlobalResourceManager for cross-workflow resource management
- ResourcePool for global capacity tracking
- WorkloadTracker, DemandForecaster, BottleneckDetector for predictive scheduling
- ScheduleAdjuster for real-time adjustments
"""

from .adjuster import (
    Adjustment,
    AdjustmentResult,
    AdjustmentType,
    ScheduleAdjuster,
)
from .models import ResourceBudget
from .predictive import (
    BottleneckDetector,
    DemandForecaster,
    ExecutionRecord,
    WorkloadForecast,
    WorkloadTracker,
)
from .resource_pool import GlobalResourceManager, ResourcePool, WorkflowQuota

__all__ = [
    # Models
    "ResourceBudget",

    # Global resource management
    "ResourcePool",
    "GlobalResourceManager",
    "WorkflowQuota",

    # Predictive scheduling
    "WorkloadTracker",
    "DemandForecaster",
    "BottleneckDetector",
    "ExecutionRecord",
    "WorkloadForecast",

    # Real-time adjustments
    "ScheduleAdjuster",
    "Adjustment",
    "AdjustmentResult",
    "AdjustmentType",
]
