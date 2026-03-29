"""
Resource management for P2-15: Workflow Orchestration.

Provides global resource tracking, per-workflow budgets, and
concurrency limits with semaphores.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from threading import Semaphore
from typing import Any


class ResourceType(StrEnum):
    """Types of resources that can be tracked and limited."""

    CONCURRENCY = "concurrency"  # Number of concurrent tasks
    TOKENS = "tokens"  # LLM token usage
    COST = "cost"  # Monetary cost in USD
    TIME = "time"  # Execution time in seconds
    MEMORY = "memory"  # Memory usage in bytes
    API_CALLS = "api_calls"  # API call count


@dataclass
class ResourceLimit:
    """A limit for a specific resource type."""

    resource_type: ResourceType
    limit: float  # Maximum allowed value
    current: float = 0.0  # Current usage
    unit: str = ""  # Unit of measurement (e.g., "tokens", "USD", "seconds")

    def can_acquire(self, amount: float = 1.0) -> bool:
        """Check if the resource can be acquired without exceeding the limit."""
        return self.current + amount <= self.limit

    def acquire(self, amount: float = 1.0) -> bool:
        """
        Acquire the resource if available.

        Returns:
            True if acquired, False if would exceed limit.
        """
        if self.can_acquire(amount):
            self.current += amount
            return True
        return False

    def release(self, amount: float = 1.0) -> None:
        """Release previously acquired resource."""
        self.current = max(0.0, self.current - amount)

    @property
    def available(self) -> float:
        """Get available resource amount."""
        return max(0.0, self.limit - self.current)

    @property
    def usage_percentage(self) -> float:
        """Get resource usage as percentage of limit."""
        if self.limit == 0:
            return 0.0
        return (self.current / self.limit) * 100.0


@dataclass
class WorkflowResources:
    """
    Resource budgets for a single workflow execution.

    Tracks per-workflow limits and current usage.
    """

    workflow_id: str
    execution_id: str
    limits: dict[ResourceType, ResourceLimit] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        # Initialize default limits if not provided
        defaults = {
            ResourceType.CONCURRENCY: ResourceLimit(
                ResourceType.CONCURRENCY, 5, 0, "tasks"
            ),
            ResourceType.TOKENS: ResourceLimit(
                ResourceType.TOKENS, 100_000, 0, "tokens"
            ),
            ResourceType.COST: ResourceLimit(ResourceType.COST, 10.0, 0, "USD"),
            ResourceType.TIME: ResourceLimit(ResourceType.TIME, 3600, 0, "seconds"),
        }

        for resource_type, default_limit in defaults.items():
            if resource_type not in self.limits:
                self.limits[resource_type] = default_limit

    def can_acquire(
        self,
        resource_type: ResourceType,
        amount: float = 1.0,
    ) -> bool:
        """Check if resource can be acquired for this workflow."""
        if resource_type not in self.limits:
            return True  # No limit for this resource type
        return self.limits[resource_type].can_acquire(amount)

    def acquire(
        self,
        resource_type: ResourceType,
        amount: float = 1.0,
    ) -> bool:
        """
        Acquire resource for this workflow if available.

        Returns:
            True if acquired, False if would exceed limit.
        """
        if resource_type not in self.limits:
            return True  # No limit for this resource type
        return self.limits[resource_type].acquire(amount)

    def release(
        self,
        resource_type: ResourceType,
        amount: float = 1.0,
    ) -> None:
        """Release previously acquired resource."""
        if resource_type in self.limits:
            self.limits[resource_type].release(amount)

    def get_usage(self, resource_type: ResourceType) -> float:
        """Get current usage of a resource."""
        if resource_type in self.limits:
            return self.limits[resource_type].current
        return 0.0

    def get_available(self, resource_type: ResourceType) -> float:
        """Get available amount of a resource."""
        if resource_type in self.limits:
            return self.limits[resource_type].available
        return float("inf")  # Unlimited

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "limits": {
                rt.value: {
                    "limit": limit.limit,
                    "current": limit.current,
                    "unit": limit.unit,
                    "available": limit.available,
                    "usage_percentage": limit.usage_percentage,
                }
                for rt, limit in self.limits.items()
            },
            "created_at": self.created_at.isoformat(),
        }


class ConcurrencyLimiter:
    """
    Semaphore-based concurrency limiter.

    Provides thread-safe acquisition and release of concurrency slots.
    """

    def __init__(self, max_concurrent: int = 5):
        """
        Initialize the concurrency limiter.

        Args:
            max_concurrent: Maximum number of concurrent tasks allowed.
        """
        self.semaphore = Semaphore(max_concurrent)
        self.max_concurrent = max_concurrent
        self.active_tasks: set[str] = set()
        self._lock = threading.Lock()

    def acquire(self, task_id: str = "") -> bool:
        """
        Acquire a concurrency slot.

        Args:
            task_id: Optional task identifier for tracking.

        Returns:
            True if acquired immediately, False if would block.
        """
        acquired = self.semaphore.acquire(blocking=False)
        if acquired and task_id:
            with self._lock:
                self.active_tasks.add(task_id)
        return acquired

    def release(self, task_id: str = "") -> None:
        """
        Release a concurrency slot.

        Args:
            task_id: Optional task identifier for tracking.
        """
        if task_id:
            with self._lock:
                self.active_tasks.discard(task_id)
        self.semaphore.release()

    @property
    def available(self) -> int:
        """Get number of available concurrency slots."""
        return self.semaphore._value

    @property
    def active_count(self) -> int:
        """Get number of active tasks."""
        with self._lock:
            return len(self.active_tasks)

    @property
    def usage_percentage(self) -> float:
        """Get concurrency usage as percentage."""
        return ((self.max_concurrent - self.available) / self.max_concurrent) * 100


class ResourceManager:
    """
    Global resource manager for workflow orchestration.

    Tracks resource usage across all workflows and provides
    global limits and visibility.
    """

    def __init__(self) -> None:
        """Initialize the resource manager."""
        self._workflow_resources: dict[str, WorkflowResources] = {}
        self._global_limits: dict[ResourceType, ResourceLimit] = {}
        self._concurrency_limiters: dict[str, ConcurrencyLimiter] = {}
        self._lock = threading.Lock()

        # Initialize default global limits
        self._global_limits[ResourceType.CONCURRENCY] = ResourceLimit(
            ResourceType.CONCURRENCY, 50, 0, "tasks"
        )
        self._global_limits[ResourceType.TOKENS] = ResourceLimit(
            ResourceType.TOKENS, 1_000_000, 0, "tokens"
        )
        self._global_limits[ResourceType.COST] = ResourceLimit(
            ResourceType.COST, 100.0, 0, "USD"
        )

    def register_workflow(
        self,
        workflow_id: str,
        execution_id: str,
        limits: dict[ResourceType, ResourceLimit] | None = None,
    ) -> WorkflowResources:
        """
        Register a new workflow for resource tracking.

        Args:
            workflow_id: Workflow identifier.
            execution_id: Execution identifier.
            limits: Optional custom resource limits for this workflow.

        Returns:
            The created WorkflowResources instance.
        """
        with self._lock:
            key = f"{workflow_id}:{execution_id}"
            if key in self._workflow_resources:
                return self._workflow_resources[key]

            workflow_resources = WorkflowResources(
                workflow_id=workflow_id,
                execution_id=execution_id,
                limits=limits or {},
            )
            self._workflow_resources[key] = workflow_resources

            # Create concurrency limiter for this workflow
            concurrency_limit = workflow_resources.limits.get(
                ResourceType.CONCURRENCY,
                ResourceLimit(ResourceType.CONCURRENCY, 5, 0, "tasks"),
            )
            self._concurrency_limiters[key] = ConcurrencyLimiter(
                int(concurrency_limit.limit)
            )

            return workflow_resources

    def unregister_workflow(self, workflow_id: str, execution_id: str) -> None:
        """
        Unregister a workflow and release all its resources.

        Args:
            workflow_id: Workflow identifier.
            execution_id: Execution identifier.
        """
        with self._lock:
            key = f"{workflow_id}:{execution_id}"
            if key in self._workflow_resources:
                del self._workflow_resources[key]
            if key in self._concurrency_limiters:
                del self._concurrency_limiters[key]

    def acquire_resource(
        self,
        workflow_id: str,
        execution_id: str,
        resource_type: ResourceType,
        amount: float = 1.0,
    ) -> bool:
        """
        Acquire a resource for a workflow.

        Checks both workflow-specific and global limits.

        Args:
            workflow_id: Workflow identifier.
            execution_id: Execution identifier.
            resource_type: Type of resource to acquire.
            amount: Amount to acquire.

        Returns:
            True if acquired, False if would exceed any limit.
        """
        key = f"{workflow_id}:{execution_id}"

        with self._lock:
            # Check global limit
            if resource_type in self._global_limits:
                if not self._global_limits[resource_type].can_acquire(amount):
                    return False

            # Check workflow limit
            if key in self._workflow_resources:
                if not self._workflow_resources[key].acquire(resource_type, amount):
                    return False

            # Acquire global limit
            if resource_type in self._global_limits:
                self._global_limits[resource_type].acquire(amount)

            return True

    def release_resource(
        self,
        workflow_id: str,
        execution_id: str,
        resource_type: ResourceType,
        amount: float = 1.0,
    ) -> None:
        """
        Release a previously acquired resource.

        Args:
            workflow_id: Workflow identifier.
            execution_id: Execution identifier.
            resource_type: Type of resource to release.
            amount: Amount to release.
        """
        key = f"{workflow_id}:{execution_id}"

        with self._lock:
            # Release workflow limit
            if key in self._workflow_resources:
                self._workflow_resources[key].release(resource_type, amount)

            # Release global limit
            if resource_type in self._global_limits:
                self._global_limits[resource_type].release(amount)

    def acquire_concurrency(
        self,
        workflow_id: str,
        execution_id: str,
        task_id: str = "",
    ) -> bool:
        """
        Acquire a concurrency slot for a workflow.

        Args:
            workflow_id: Workflow identifier.
            execution_id: Execution identifier.
            task_id: Optional task identifier for tracking.

        Returns:
            True if acquired, False if no slots available.
        """
        key = f"{workflow_id}:{execution_id}"

        with self._lock:
            if key not in self._concurrency_limiters:
                # Create default limiter if not exists
                self._concurrency_limiters[key] = ConcurrencyLimiter(5)

            return self._concurrency_limiters[key].acquire(task_id)

    def release_concurrency(
        self,
        workflow_id: str,
        execution_id: str,
        task_id: str = "",
    ) -> None:
        """
        Release a concurrency slot for a workflow.

        Args:
            workflow_id: Workflow identifier.
            execution_id: Execution identifier.
            task_id: Optional task identifier for tracking.
        """
        key = f"{workflow_id}:{execution_id}"

        with self._lock:
            if key in self._concurrency_limiters:
                self._concurrency_limiters[key].release(task_id)

    def get_workflow_resources(
        self,
        workflow_id: str,
        execution_id: str,
    ) -> WorkflowResources | None:
        """Get resource tracking for a specific workflow."""
        key = f"{workflow_id}:{execution_id}"
        with self._lock:
            return self._workflow_resources.get(key)

    def get_global_usage(self, resource_type: ResourceType) -> float:
        """Get global usage of a resource type."""
        with self._lock:
            if resource_type in self._global_limits:
                return self._global_limits[resource_type].current
            return 0.0

    def get_global_available(self, resource_type: ResourceType) -> float:
        """Get global available amount of a resource type."""
        with self._lock:
            if resource_type in self._global_limits:
                return self._global_limits[resource_type].available
            return float("inf")

    def get_concurrency_usage(
        self,
        workflow_id: str,
        execution_id: str,
    ) -> dict[str, Any]:
        """Get concurrency usage for a workflow."""
        key = f"{workflow_id}:{execution_id}"

        with self._lock:
            if key in self._concurrency_limiters:
                limiter = self._concurrency_limiters[key]
                return {
                    "available": limiter.available,
                    "active_count": limiter.active_count,
                    "max_concurrent": limiter.max_concurrent,
                    "usage_percentage": limiter.usage_percentage,
                    "active_tasks": list(limiter.active_tasks),
                }
            return {
                "available": 0,
                "active_count": 0,
                "max_concurrent": 0,
                "usage_percentage": 0.0,
                "active_tasks": [],
            }

    def get_global_summary(self) -> dict[str, Any]:
        """Get global resource usage summary."""
        with self._lock:
            return {
                "global_limits": {
                    rt.value: {
                        "limit": limit.limit,
                        "current": limit.current,
                        "available": limit.available,
                        "usage_percentage": limit.usage_percentage,
                        "unit": limit.unit,
                    }
                    for rt, limit in self._global_limits.items()
                },
                "active_workflows": len(self._workflow_resources),
                "total_concurrency_active": sum(
                    limiter.active_count
                    for limiter in self._concurrency_limiters.values()
                ),
                "total_concurrency_available": sum(
                    limiter.available for limiter in self._concurrency_limiters.values()
                ),
            }


# Global singleton instance
_resource_manager = ResourceManager()


def get_resource_manager() -> ResourceManager:
    """Get the global resource manager instance."""
    return _resource_manager
