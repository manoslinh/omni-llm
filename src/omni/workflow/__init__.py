"""
Workflow Orchestration for Omni-LLM (P2-15).

Advanced workflow orchestration with conditional control flow,
resource management, and reusable templates.

This module extends P2-14 Coordination Engine with:
- Conditional branching (IF/ELSE)
- Loops (WHILE, FOR_EACH)
- Error handling (TRY_CATCH)
- Compensation actions
- Resource-aware execution
- Reusable workflow templates
"""

from .context import (
    ExecutionError,
    NodeResult,
    NodeStatus,
    ResourceSnapshot,
    WorkflowContext,
)
from .definition import WorkflowDefinition
from .evaluator import (
    ConditionEvaluationError,
    ExpressionEvaluator,
    evaluate_collection,
    evaluate_condition,
)
from .nodes import (
    CompensationAction,
    Condition,
    EdgeType,
    NodeEdge,
    NodeType,
    ResourceConstraint,
    WorkflowNode,
)
from .orchestrator import (
    OrchestratorConfig,
    WorkflowExecution,
    WorkflowOrchestrator,
    execute_template,
    execute_workflow,
    get_orchestrator,
)
from .resources import (
    ConcurrencyLimiter,
    ResourceLimit,
    ResourceManager,
    ResourceType,
    WorkflowResources,
    get_resource_manager,
)
from .state_machine import (
    ExecutionEvent,
    ExecutionEventType,
    ExecutionObserver,
    ExecutionResult,
    WorkflowStateMachine,
)
from .templates import (
    TemplateParameter,
    TemplateRegistry,
    WorkflowTemplate,
    get_template,
    get_template_registry,
    list_templates,
    register_template,
)

__all__ = [
    # Context
    "ExecutionError",
    "NodeResult",
    "NodeStatus",
    "ResourceSnapshot",
    "WorkflowContext",
    # Definition
    "WorkflowDefinition",
    # Evaluator
    "ConditionEvaluationError",
    "ExpressionEvaluator",
    "evaluate_condition",
    "evaluate_collection",
    # Nodes
    "CompensationAction",
    "Condition",
    "EdgeType",
    "NodeEdge",
    "NodeType",
    "ResourceConstraint",
    "WorkflowNode",
    # Orchestrator
    "OrchestratorConfig",
    "WorkflowExecution",
    "WorkflowOrchestrator",
    "execute_template",
    "execute_workflow",
    "get_orchestrator",
    # Resources
    "ConcurrencyLimiter",
    "ResourceLimit",
    "ResourceManager",
    "ResourceType",
    "WorkflowResources",
    "get_resource_manager",
    # State Machine
    "ExecutionEvent",
    "ExecutionEventType",
    "ExecutionObserver",
    "ExecutionResult",
    "WorkflowStateMachine",
    # Templates
    "TemplateParameter",
    "TemplateRegistry",
    "WorkflowTemplate",
    "get_template",
    "get_template_registry",
    "list_templates",
    "register_template",
]

__version__ = "1.0.0"
