"""
Schedule Adjuster - Real-time adjustments for task scheduling.

Provides ScheduleAdjuster for runtime adjustments:
- Failure recovery (reassign to different agents)
- Deadline pressure (priority escalation)
- Capacity bursting (dynamic resource allocation)

Integration Points:
- Uses P2-14 agent matcher for reassignment
- Integrates with scheduling policies for priority changes
- Works with ResourcePool for capacity adjustments
- Provides observability data to P2-13 monitoring
- Reacts to Predictive Module alerts
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from ..task.models import Task

logger = logging.getLogger(__name__)


class AdjustmentType(StrEnum):
    """Types of runtime schedule adjustments."""
    RESCHEDULE = "reschedule"           # Re-prioritize a task
    REASSIGN = "reassign"               # Change agent assignment
    ESCALATE = "escalate"               # Escalate to higher-tier agent
    RENEGOTIATE_DEADLINE = "renegotiate" # Extend a deadline
    BURST = "burst"                     # Temporarily increase concurrency


@dataclass
class Adjustment:
    """A runtime schedule adjustment."""
    adjustment_type: AdjustmentType
    task_id: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdjustmentResult:
    """Result of applying an adjustment."""
    adjustment: Adjustment
    applied: bool
    previous_value: Any = None
    new_value: Any = None
    message: str = ""


class TaskMatcherProtocol(Protocol):
    """Protocol for P2-14 agent matcher integration."""

    async def match(self, task: Task) -> dict[str, Any]:
        """Match a task to an agent."""
        ...


class WorkloadTrackerProtocol(Protocol):
    """Protocol for WorkloadTracker integration."""

    def get_agent_avg_duration(self, agent_id: str) -> float | None:
        """Get average execution duration for an agent."""
        ...

    def get_agent_success_rate(self, agent_id: str) -> float | None:
        """Get success rate for an agent (0.0 to 1.0)."""
        ...

    def get_throughput(self, window_seconds: float = 300) -> float:
        """Get tasks completed per second over the recent window."""
        ...


class ResourcePoolProtocol(Protocol):
    """Protocol for ResourcePool integration."""

    def can_allocate(self, requested_concurrent: int = 1) -> bool:
        """Check if global pool can satisfy a request."""
        ...

    def allocate(self, execution_id: str, concurrent: int = 1) -> bool:
        """Reserve capacity from the global pool."""
        ...

    def release(self, execution_id: str, concurrent: int = 1) -> None:
        """Return capacity to the global pool."""
        ...

    @property
    def available_concurrent(self) -> int:
        """Get available concurrent capacity."""
        ...

    @property
    def utilization(self) -> dict[str, Any]:
        """Get pool utilization statistics."""
        ...


class ScheduleAdjuster:
    """
    Applies runtime adjustments to the schedule.

    Integrates with:
    - P2-14 TaskMatcher for agent reassignment
    - WorkloadTracker for data-driven decisions
    - ResourcePool for capacity adjustments
    - P2-13 Observability for event emission

    Usage:
        adjuster = ScheduleAdjuster(matcher=task_matcher)

        # React to a failure
        result = await adjuster.adjust_for_failure(
            task=failed_task,
            failure_reason="Rate limit exceeded",
        )

        # React to a deadline approaching
        result = await adjuster.adjust_for_deadline_pressure(
            task=urgent_task,
            time_remaining=30,
        )

        # Request capacity burst
        result = await adjuster.burst_capacity(
            workflow_id="wf-001",
            additional_concurrent=2,
            duration_seconds=300,
            reason="Workload surge",
        )
    """

    def __init__(
        self,
        matcher: TaskMatcherProtocol | None = None,
        tracker: WorkloadTrackerProtocol | None = None,
        resource_pool: ResourcePoolProtocol | None = None,
        event_emitter: Any | None = None,
    ) -> None:
        self.matcher = matcher
        self.tracker = tracker
        self.resource_pool = resource_pool
        self.event_emitter = event_emitter
        self._adjustment_log: list[AdjustmentResult] = []
        self._capacity_bursts: dict[str, dict[str, Any]] = {}  # burst_id -> burst info
        self._lock = asyncio.Lock()

    async def adjust_for_failure(
        self,
        task: Task,
        failure_reason: str,
    ) -> AdjustmentResult:
        """
        React to a task failure by reassigning or rescheduling.

        Strategy:
        1. If error is transient (rate limit, timeout) → reschedule with backoff
        2. If error is permanent (auth, bad input) → reassign to higher-tier agent
        3. If no higher-tier available → reschedule with lower priority

        Args:
            task: The failed task
            failure_reason: Description of why the task failed

        Returns:
            AdjustmentResult with details of the adjustment
        """
        # Use workload tracker data if available
        agent_id = task.context.get("assigned_agent") if task.context else None
        if self.tracker and agent_id:
            success_rate = self.tracker.get_agent_success_rate(agent_id)
            if success_rate is not None and success_rate < 0.5:
                # Agent has low success rate, consider escalation
                failure_reason = f"{failure_reason} (agent {agent_id} success rate: {success_rate:.0%})"

        # Determine if failure is transient
        is_transient = self._is_transient_failure(failure_reason)

        if is_transient:
            adjustment = Adjustment(
                adjustment_type=AdjustmentType.RESCHEDULE,
                task_id=task.task_id,
                reason=f"Transient failure: {failure_reason}",
                details={
                    "backoff_seconds": 5.0,
                    "retry_count": task.retry_count + 1,
                    "failure_type": "transient",
                },
            )
        elif self.matcher:
            # Permanent failure → try reassigning
            try:
                new_assignment = await self.matcher.match(task)
                if new_assignment.get("agent_id"):
                    adjustment = Adjustment(
                        adjustment_type=AdjustmentType.REASSIGN,
                        task_id=task.task_id,
                        reason=f"Permanent failure: {failure_reason}",
                        details={
                            "previous_agent": task.context.get("assigned_agent"),
                            "new_agent": new_assignment.get("agent_id"),
                            "confidence": new_assignment.get("confidence", 0.0),
                            "failure_type": "permanent",
                        },
                    )
                else:
                    # No suitable agent found, escalate
                    adjustment = Adjustment(
                        adjustment_type=AdjustmentType.ESCALATE,
                        task_id=task.task_id,
                        reason=f"Reassignment unavailable, escalating: {failure_reason}",
                        details={
                            "escalate_from": task.context.get("assigned_agent"),
                            "failure_type": "permanent",
                        },
                    )
            except Exception as e:
                logger.warning(f"Failed to match task for reassignment: {e}")
                adjustment = Adjustment(
                    adjustment_type=AdjustmentType.RESCHEDULE,
                    task_id=task.task_id,
                    reason=f"Matcher error, rescheduling: {failure_reason}",
                    details={
                        "matcher_error": str(e),
                        "failure_type": "permanent",
                    },
                )
        else:
            # No matcher available
            adjustment = Adjustment(
                adjustment_type=AdjustmentType.RESCHEDULE,
                task_id=task.task_id,
                reason=f"No matcher available, rescheduling: {failure_reason}",
                details={
                    "failure_type": "permanent",
                    "retry": True,
                },
            )

        result = AdjustmentResult(
            adjustment=adjustment,
            applied=True,
            message=f"Applied {adjustment.adjustment_type.value} for {task.task_id}",
        )

        async with self._lock:
            self._adjustment_log.append(result)

        # Emit P2-13 event
        await self._emit_adjustment_event(adjustment, result)

        logger.info(
            f"Schedule adjustment: {adjustment.adjustment_type.value} "
            f"for {task.task_id} — {adjustment.reason}"
        )
        return result

    async def adjust_for_deadline_pressure(
        self,
        task: Task,
        time_remaining: float,
    ) -> AdjustmentResult:
        """
        Escalate a task that's approaching its deadline.

        Actions:
        1. If matcher available → reassign to faster/cheaper agent
        2. Flag for priority boost in scheduling queue

        Args:
            task: The task with deadline pressure
            time_remaining: Seconds until deadline (negative if overdue)

        Returns:
            AdjustmentResult with details of the adjustment
        """
        # Use workload tracker data if available
        agent_id = task.context.get("assigned_agent") if task.context else None
        estimated_duration = None
        if self.tracker and agent_id:
            estimated_duration = self.tracker.get_agent_avg_duration(agent_id)
            if estimated_duration and estimated_duration > time_remaining:
                # Agent is too slow for this deadline
                time_remaining = max(0, time_remaining - estimated_duration)

        # Determine urgency level
        if time_remaining <= 0:
            urgency = "overdue"
        elif time_remaining < 60:
            urgency = "critical"
        elif time_remaining < 300:
            urgency = "high"
        else:
            urgency = "normal"

        # Choose adjustment type based on urgency
        if urgency in ("critical", "overdue") and self.matcher:
            adjustment_type = AdjustmentType.REASSIGN
        else:
            adjustment_type = AdjustmentType.RESCHEDULE

        adjustment = Adjustment(
            adjustment_type=adjustment_type,
            task_id=task.task_id,
            reason=f"Deadline {urgency}: {time_remaining:.0f}s remaining",
            details={
                "urgency": urgency,
                "seconds_remaining": time_remaining,
                "priority_boost": urgency in ("critical", "overdue"),
                "deadline_escalation": True,
                "estimated_agent_duration": estimated_duration,
            },
        )

        result = AdjustmentResult(
            adjustment=adjustment,
            applied=True,
            message=f"Deadline escalation ({urgency}) for {task.task_id}",
        )

        async with self._lock:
            self._adjustment_log.append(result)

        # Emit P2-13 event
        await self._emit_adjustment_event(adjustment, result)

        logger.info(
            f"Deadline adjustment: {urgency} urgency for {task.task_id} "
            f"({time_remaining:.0f}s remaining)"
        )
        return result

    async def burst_capacity(
        self,
        workflow_id: str,
        additional_concurrent: int,
        duration_seconds: float,
        reason: str,
    ) -> AdjustmentResult:
        """
        Temporarily increase concurrency for a workflow.

        Used when a workflow is falling behind and needs a burst.
        The burst is time-limited — capacity is returned after duration.

        Args:
            workflow_id: ID of the workflow needing capacity
            additional_concurrent: Number of additional concurrent slots
            duration_seconds: How long the burst should last
            reason: Explanation for why burst is needed

        Returns:
            AdjustmentResult with details of the burst
        """
        # Try to allocate from resource pool if available
        allocated = False
        if self.resource_pool:
            if self.resource_pool.can_allocate(additional_concurrent):
                allocated = self.resource_pool.allocate(workflow_id, additional_concurrent)
            else:
                # Can't allocate from pool
                adjustment = Adjustment(
                    adjustment_type=AdjustmentType.BURST,
                    task_id="",  # Workflow-level, not task-level
                    reason=f"{reason} (insufficient resources)",
                    details={
                        "workflow_id": workflow_id,
                        "additional_concurrent": 0,  # Couldn't allocate
                        "duration_seconds": duration_seconds,
                        "requested_at": time.time(),
                        "allocated": False,
                        "pool_available": self.resource_pool.available_concurrent,
                    },
                )

                result = AdjustmentResult(
                    adjustment=adjustment,
                    applied=False,
                    message=f"Failed to burst capacity for {workflow_id}: insufficient resources",
                )

                async with self._lock:
                    self._adjustment_log.append(result)

                await self._emit_adjustment_event(adjustment, result)
                return result
        else:
            # No resource pool - for backward compatibility, treat as allocated
            allocated = True

        adjustment = Adjustment(
            adjustment_type=AdjustmentType.BURST,
            task_id="",  # Workflow-level, not task-level
            reason=reason,
            details={
                "workflow_id": workflow_id,
                "additional_concurrent": additional_concurrent,
                "duration_seconds": duration_seconds,
                "requested_at": time.time(),
                "allocated": allocated,
                "pool_utilization": self.resource_pool.utilization if self.resource_pool else {},
            },
        )

        # Store burst information for later cleanup
        burst_id = f"{workflow_id}_{int(time.time())}"
        async with self._lock:
            self._capacity_bursts[burst_id] = {
                "workflow_id": workflow_id,
                "concurrent": additional_concurrent,
                "duration_seconds": duration_seconds,
                "requested_at": time.time(),
                "expires_at": time.time() + duration_seconds,
                "allocated": allocated,
                "burst_id": burst_id,
            }

        result = AdjustmentResult(
            adjustment=adjustment,
            applied=allocated,
            message=f"Burst +{additional_concurrent} concurrent for {workflow_id} "
                    f"for {duration_seconds:.0f}s: {reason}",
        )

        async with self._lock:
            self._adjustment_log.append(result)

        logger.info(
            f"Capacity burst: +{additional_concurrent} concurrent for {workflow_id} "
            f"for {duration_seconds:.0f}s"
        )

        # Emit P2-13 event
        await self._emit_adjustment_event(adjustment, result)

        # Schedule cleanup of the burst
        if allocated:
            asyncio.create_task(self._cleanup_burst(burst_id, duration_seconds))

        return result

    async def adjust_for_capacity_needs(
        self,
        workflow_id: str,
        additional_resources: dict[str, Any],
    ) -> AdjustmentResult:
        """
        Temporarily increase capacity for a workflow.

        Legacy method that wraps burst_capacity for backward compatibility.

        Args:
            workflow_id: ID of the workflow needing capacity
            additional_resources: Dictionary of resources to add, e.g.,
                {"concurrent": 2, "duration_seconds": 300}

        Returns:
            AdjustmentResult with details of the burst
        """
        concurrent = additional_resources.get("concurrent", 1)
        duration = additional_resources.get("duration_seconds", 300.0)
        reason = additional_resources.get("reason", "Workload surge")

        return await self.burst_capacity(
            workflow_id=workflow_id,
            additional_concurrent=concurrent,
            duration_seconds=duration,
            reason=reason,
        )

    def get_adjustment_history(self) -> list[AdjustmentResult]:
        """Get all adjustments made this session."""
        # Note: This is a synchronous method, so we can't use async lock
        # In a real implementation, we'd need async versions or thread-safe access
        return self._adjustment_log.copy()

    def get_adjustment_summary(self) -> dict[str, Any]:
        """Summary of adjustments by type."""
        # Note: This is a synchronous method
        summary: dict[str, int] = {}
        for r in self._adjustment_log:
            t = r.adjustment.adjustment_type.value
            summary[t] = summary.get(t, 0) + 1
        return {
            "total_adjustments": len(self._adjustment_log),
            "by_type": summary,
            "active_bursts": len(self._capacity_bursts),
        }

    def get_active_bursts(self) -> dict[str, dict[str, Any]]:
        """Get information about active capacity bursts."""
        now = time.time()
        active = {}
        for burst_id, info in self._capacity_bursts.items():
            if info["expires_at"] > now:
                active[burst_id] = info.copy()
                active[burst_id]["remaining_seconds"] = info["expires_at"] - now
        return active

    def _is_transient_failure(self, failure_reason: str) -> bool:
        """Determine if a failure is likely transient."""
        reason_lower = failure_reason.lower()
        transient_indicators = [
            "rate limit", "timeout", "429", "500", "502", "503", "504",
            "temporary", "retry", "busy", "overloaded", "connection",
            "network", "service unavailable", "too many requests",
        ]
        return any(indicator in reason_lower for indicator in transient_indicators)

    async def _cleanup_burst(self, burst_id: str, delay_seconds: float) -> None:
        """Clean up a capacity burst after its duration expires."""
        await asyncio.sleep(delay_seconds)

        async with self._lock:
            if burst_id not in self._capacity_bursts:
                return

            info = self._capacity_bursts.pop(burst_id)

        # Release resources back to pool if they were allocated
        if info.get("allocated") and self.resource_pool:
            self.resource_pool.release(info["workflow_id"], info["concurrent"])

        logger.info(
            f"Capacity burst expired: {burst_id} for "
            f"{info['workflow_id']} (+{info['concurrent']} concurrent)"
        )

        # Emit cleanup event
        if self.event_emitter:
            try:
                await self.event_emitter.emit("burst_expired", {
                    "burst_id": burst_id,
                    "workflow_id": info["workflow_id"],
                    "concurrent": info["concurrent"],
                    "duration_seconds": info["duration_seconds"],
                })
            except Exception as e:
                logger.debug(f"Failed to emit burst_expired event: {e}")

    async def _emit_adjustment_event(self, adjustment: Adjustment, result: AdjustmentResult) -> None:
        """Emit P2-13 observability event for schedule adjustment."""
        if not self.event_emitter:
            return

        try:
            event_data = {
                "adjustment_type": adjustment.adjustment_type.value,
                "task_id": adjustment.task_id,
                "reason": adjustment.reason,
                "details": adjustment.details,
                "applied": result.applied,
                "message": result.message,
                "timestamp": time.time(),
            }

            await self.event_emitter.emit("schedule_adjusted", event_data)
        except Exception as e:
            logger.debug(f"Failed to emit schedule_adjusted event: {e}")
