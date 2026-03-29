"""
Workflow orchestrator for P2-15: Workflow Orchestration.

Main facade class that integrates workflow orchestration with
P2-14 Coordination Engine and other Omni-LLM components.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .context import WorkflowContext
from .definition import WorkflowDefinition
from .evaluator import ExpressionEvaluator
from .resources import get_resource_manager
from .state_machine import (
    ExecutionEvent,
    ExecutionEventType,
    ExecutionObserver,
    ExecutionResult,
    WorkflowStateMachine,
)
from .templates import get_template_registry


@dataclass
class OrchestratorConfig:
    """Configuration for the workflow orchestrator."""

    # Resource management
    default_max_concurrent_tasks: int = 5
    default_token_budget: int = 100_000
    default_cost_budget: float = 10.0
    default_timeout_seconds: float = 3600

    # Execution
    enable_observability: bool = True
    emit_events: bool = True
    validate_before_execution: bool = True

    # Integration
    coordination_engine_enabled: bool = True  # P2-14 integration
    parallel_engine_enabled: bool = True  # P2-11 integration
    model_routing_enabled: bool = True  # P2-12 integration
    observability_enabled: bool = True  # P2-13 integration


@dataclass
class WorkflowExecution:
    """Represents an executing workflow instance."""

    execution_id: str
    workflow_id: str
    definition: WorkflowDefinition
    context: WorkflowContext
    state_machine: WorkflowStateMachine
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    result: ExecutionResult | None = None
    status: str = "pending"  # pending, running, completed, failed, cancelled

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "result": self.result.to_dict() if self.result else None,
            "context": self.context.to_dict(),
        }


class WorkflowOrchestrator:
    """
    Main facade class for workflow orchestration.

    Integrates with:
    - P2-14 Coordination Engine (agent assignment)
    - P2-11 Parallel Engine (task execution)
    - P2-12 Model Router (LLM execution)
    - P2-13 Observability (monitoring and events)
    - Resource Manager (resource constraints)
    - Template Registry (reusable patterns)
    """

    def __init__(self, config: OrchestratorConfig | None = None):
        """
        Initialize the workflow orchestrator.

        Args:
            config: Orchestrator configuration. Uses defaults if None.
        """
        self.config = config or OrchestratorConfig()
        self.resource_manager = get_resource_manager()
        self.template_registry = get_template_registry()
        self.evaluator = ExpressionEvaluator()

        # Active executions
        self._executions: dict[str, WorkflowExecution] = {}
        self._execution_lock = None  # Would be a threading.Lock in real implementation

        # Observers
        self._observers: list[ExecutionObserver] = []

        # Integration points (would be initialized with actual components)
        self._coordination_engine = None  # P2-14
        self._parallel_engine = None  # P2-11
        self._model_router = None  # P2-12
        self._observability = None  # P2-13

    # ── Workflow Execution ─────────────────────────────────────

    def execute_workflow(
        self,
        definition: WorkflowDefinition,
        execution_id: str | None = None,
        variables: dict[str, Any] | None = None,
    ) -> WorkflowExecution:
        """
        Execute a workflow definition.

        Args:
            definition: The workflow definition to execute.
            execution_id: Optional execution ID. Generated if not provided.
            variables: Optional initial workflow variables.

        Returns:
            WorkflowExecution object representing the executing workflow.

        Raises:
            ValueError: If the workflow definition is invalid.
        """
        # Generate execution ID if not provided
        if not execution_id:
            execution_id = f"exec_{uuid.uuid4().hex[:8]}"

        # Validate workflow definition
        if self.config.validate_before_execution:
            issues = definition.validate()
            if issues:
                raise ValueError(
                    "Workflow definition validation failed:\n"
                    + "\n".join(f"  - {issue}" for issue in issues)
                )

        # Register workflow with resource manager
        self.resource_manager.register_workflow(
            workflow_id=definition.workflow_id,
            execution_id=execution_id,
        )

        # Create workflow context
        context = WorkflowContext(
            workflow_id=definition.workflow_id,
            execution_id=execution_id,
            variables=variables or {},
        )

        # Create state machine
        state_machine = WorkflowStateMachine(
            definition=definition,
            context=context,
            evaluator=self.evaluator,
            observers=self._observers if self.config.emit_events else [],
        )

        # Create execution record
        execution = WorkflowExecution(
            execution_id=execution_id,
            workflow_id=definition.workflow_id,
            definition=definition,
            context=context,
            state_machine=state_machine,
            status="running",
        )

        # Store execution
        self._executions[execution_id] = execution

        # Execute workflow (synchronously for now)
        # In a real implementation, this would be async
        try:
            result = state_machine.execute()
            execution.result = result
            execution.completed_at = datetime.now()
            execution.status = "completed" if result.success else "failed"
        except Exception as e:
            execution.completed_at = datetime.now()
            execution.status = "failed"
            # Create a failed execution result
            execution.result = ExecutionResult(
                success=False,
                workflow_id=definition.workflow_id,
                execution_id=execution_id,
                context=context,
                error=str(e),
                error_type=type(e).__name__,
                started_at=execution.started_at,
                completed_at=execution.completed_at,
            )

        # Unregister workflow from resource manager
        self.resource_manager.unregister_workflow(
            workflow_id=definition.workflow_id,
            execution_id=execution_id,
        )

        return execution

    def execute_template(
        self,
        template_id: str,
        parameters: dict[str, Any] | None = None,
        execution_id: str | None = None,
    ) -> WorkflowExecution:
        """
        Execute a workflow from a template.

        Args:
            template_id: ID of the template to use.
            parameters: Template parameters.
            execution_id: Optional execution ID. Generated if not provided.

        Returns:
            WorkflowExecution object representing the executing workflow.

        Raises:
            ValueError: If template not found or parameters invalid.
        """
        # Get template
        template = self.template_registry.get(template_id)
        if not template:
            raise ValueError(f"Template '{template_id}' not found")

        # Build workflow definition from template
        definition = template.build(**(parameters or {}))

        # Execute the workflow
        return self.execute_workflow(
            definition=definition,
            execution_id=execution_id,
            variables=parameters,  # Pass parameters as initial variables
        )

    # ── Execution Management ───────────────────────────────────

    def get_execution(self, execution_id: str) -> WorkflowExecution | None:
        """Get an execution by ID."""
        return self._executions.get(execution_id)

    def list_executions(
        self,
        workflow_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[WorkflowExecution]:
        """List workflow executions with optional filtering."""
        executions = list(self._executions.values())

        # Apply filters
        if workflow_id:
            executions = [e for e in executions if e.workflow_id == workflow_id]
        if status:
            executions = [e for e in executions if e.status == status]

        # Sort by started_at (newest first)
        executions.sort(key=lambda e: e.started_at, reverse=True)

        return executions[:limit]

    def cancel_execution(self, execution_id: str) -> bool:
        """
        Cancel a running execution.

        Args:
            execution_id: ID of the execution to cancel.

        Returns:
            True if cancelled, False if not found or not running.
        """
        execution = self._executions.get(execution_id)
        if not execution or execution.status != "running":
            return False

        # In a real implementation, we would signal the state machine to stop
        # For now, we'll just mark it as cancelled
        execution.status = "cancelled"
        execution.completed_at = datetime.now()

        return True

    # ── Resource Management ────────────────────────────────────

    def get_resource_usage(
        self,
        workflow_id: str,
        execution_id: str,
    ) -> dict[str, Any]:
        """Get resource usage for a workflow execution."""
        resources = self.resource_manager.get_workflow_resources(
            workflow_id=workflow_id,
            execution_id=execution_id,
        )

        if resources:
            return resources.to_dict()
        else:
            return {"error": "Workflow resources not found"}

    def get_global_resource_summary(self) -> dict[str, Any]:
        """Get global resource usage summary."""
        return self.resource_manager.get_global_summary()

    def set_resource_limits(
        self,
        workflow_id: str,
        execution_id: str,
        limits: dict[str, Any],
    ) -> bool:
        """
        Set resource limits for a workflow execution.

        Args:
            workflow_id: Workflow identifier.
            execution_id: Execution identifier.
            limits: Dictionary of resource limits.
                Example: {"concurrency": 10, "tokens": 50000, "cost": 5.0}

        Returns:
            True if limits were set, False if execution not found.
        """
        # This would update limits in the resource manager
        # For now, we'll return a placeholder implementation
        return True

    # ── Observability ──────────────────────────────────────────

    def add_observer(self, observer: ExecutionObserver) -> None:
        """Add an execution observer."""
        self._observers.append(observer)

    def remove_observer(self, observer: ExecutionObserver) -> None:
        """Remove an execution observer."""
        if observer in self._observers:
            self._observers.remove(observer)

    def emit_custom_event(
        self,
        execution_id: str,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """
        Emit a custom observability event.

        Args:
            execution_id: Execution ID to associate event with.
            event_type: Custom event type.
            data: Optional event data.

        Returns:
            True if event was emitted, False if execution not found.
        """
        execution = self._executions.get(execution_id)
        if not execution:
            return False

        # Create and emit event
        try:
            event_type_enum = ExecutionEventType(event_type)
        except ValueError:
            # Custom event type not in enum
            event_type_enum = ExecutionEventType.WORKFLOW_COMPLETED  # Default

        event = ExecutionEvent(
            event_type=event_type_enum,
            timestamp=datetime.now(),
            workflow_id=execution.workflow_id,
            execution_id=execution_id,
            data=data or {},
        )

        for observer in self._observers:
            try:
                observer(event)
            except Exception:
                pass  # Don't let observer errors break things

        return True

    # ── Integration with P2-14 Coordination Engine ─────────────

    def integrate_coordination_engine(self, coordination_engine: Any) -> None:
        """
        Integrate with P2-14 Coordination Engine.

        Args:
            coordination_engine: Instance of P2-14 CoordinationEngine.
        """
        self._coordination_engine = coordination_engine

        # Register as observer if coordination engine supports it
        if hasattr(coordination_engine, "add_observer"):
            coordination_engine.add_observer(self._handle_coordination_event)

    def _handle_coordination_event(self, event: Any) -> None:
        """Handle events from the coordination engine."""
        # This would process coordination events and update workflows
        # For now, it's a placeholder
        pass

    # ── Integration with P2-11 Parallel Engine ─────────────────

    def integrate_parallel_engine(self, parallel_engine: Any) -> None:
        """
        Integrate with P2-11 Parallel Engine.

        Args:
            parallel_engine: Instance of P2-11 ParallelEngine.
        """
        self._parallel_engine = parallel_engine

    # ── Integration with P2-12 Model Router ────────────────────

    def integrate_model_router(self, model_router: Any) -> None:
        """
        Integrate with P2-12 Model Router.

        Args:
            model_router: Instance of P2-12 ModelRouter.
        """
        self._model_router = model_router

    # ── Integration with P2-13 Observability ───────────────────

    def integrate_observability(self, observability: Any) -> None:
        """
        Integrate with P2-13 Observability.

        Args:
            observability: Instance of P2-13 Observability system.
        """
        self._observability = observability

        # Register as event source if observability supports it
        if hasattr(observability, "register_event_source"):
            observability.register_event_source("workflow_orchestrator", self)

    # ── Utility Methods ────────────────────────────────────────

    def validate_workflow(self, definition: WorkflowDefinition) -> list[str]:
        """
        Validate a workflow definition.

        Args:
            definition: Workflow definition to validate.

        Returns:
            List of validation issues. Empty list means valid.
        """
        return definition.validate()

    def create_workflow_from_plan(self, plan: Any) -> WorkflowDefinition:
        """
        Create a workflow definition from a P2-14 WorkflowPlan.

        Delegates to WorkflowDefinition.from_plan() for the conversion.
        """
        return WorkflowDefinition.from_plan(plan)

    def get_available_templates(self) -> list[dict[str, Any]]:
        """Get list of available workflow templates."""
        templates = self.template_registry.list()
        return [
            {
                "template_id": t.template_id,
                "name": t.name,
                "description": t.description,
                "parameters": [
                    {
                        "name": p.name,
                        "description": p.description,
                        "default": p.default,
                        "required": p.required,
                        "type": p.type,
                    }
                    for p in t.parameters
                ],
                "version": t.version,
                "tags": t.tags,
            }
            for t in templates
        ]


# Global orchestrator instance
_orchestrator: WorkflowOrchestrator | None = None


def get_orchestrator(config: OrchestratorConfig | None = None) -> WorkflowOrchestrator:
    """
    Get the global workflow orchestrator instance.

    Args:
        config: Optional configuration. Only used on first call.

    Returns:
        Global WorkflowOrchestrator instance.
    """
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = WorkflowOrchestrator(config)
    return _orchestrator


def execute_workflow(
    definition: WorkflowDefinition,
    execution_id: str | None = None,
    variables: dict[str, Any] | None = None,
) -> WorkflowExecution:
    """
    Execute a workflow using the global orchestrator.

    Convenience function for simple workflow execution.
    """
    orchestrator = get_orchestrator()
    return orchestrator.execute_workflow(definition, execution_id, variables)


def execute_template(
    template_id: str,
    parameters: dict[str, Any] | None = None,
    execution_id: str | None = None,
) -> WorkflowExecution:
    """
    Execute a workflow template using the global orchestrator.

    Convenience function for template-based workflow execution.
    """
    orchestrator = get_orchestrator()
    return orchestrator.execute_template(template_id, parameters, execution_id)
