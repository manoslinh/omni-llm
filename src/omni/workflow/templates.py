"""
Workflow templates for P2-15: Workflow Orchestration.

Provides built-in workflow patterns that can be used as reusable
building blocks for common orchestration scenarios.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .definition import WorkflowDefinition
from .nodes import (
    CompensationAction,
    Condition,
    EdgeType,
    NodeEdge,
    NodeType,
    ResourceConstraint,
    WorkflowNode,
)


@dataclass
class TemplateParameter:
    """A parameter for a workflow template."""

    name: str
    description: str
    default: Any = None
    required: bool = False
    type: str = "str"  # str, int, float, bool, list, dict


@dataclass
class WorkflowTemplate:
    """A reusable workflow template."""

    template_id: str
    name: str
    description: str
    parameters: list[TemplateParameter] = field(default_factory=list)
    builder: Callable[[dict[str, Any]], WorkflowDefinition] | None = None
    version: str = "1.0"
    tags: list[str] = field(default_factory=list)

    def build(self, **kwargs: Any) -> WorkflowDefinition:
        """
        Build a workflow definition from this template.

        Args:
            **kwargs: Parameter values for the template.

        Returns:
            A configured WorkflowDefinition.

        Raises:
            ValueError: If required parameters are missing or invalid.
        """
        # Validate parameters
        provided_params = set(kwargs.keys())

        for param in self.parameters:
            if param.required and param.name not in provided_params:
                raise ValueError(
                    f"Required parameter '{param.name}' not provided for template '{self.name}'"
                )

        # Set defaults for missing optional parameters
        for param in self.parameters:
            if param.name not in provided_params and param.default is not None:
                kwargs[param.name] = param.default

        # Call the builder function
        if self.builder:
            return self.builder(kwargs)
        else:
            raise ValueError(f"Template '{self.name}' has no builder function")


class TemplateRegistry:
    """Registry for workflow templates."""

    def __init__(self) -> None:
        """Initialize the template registry."""
        self._templates: dict[str, WorkflowTemplate] = {}
        self._register_builtin_templates()

    def register(self, template: WorkflowTemplate) -> None:
        """
        Register a workflow template.

        Args:
            template: The template to register.

        Raises:
            ValueError: If a template with the same ID is already registered.
        """
        if template.template_id in self._templates:
            raise ValueError(
                f"Template with ID '{template.template_id}' is already registered"
            )
        self._templates[template.template_id] = template

    def get(self, template_id: str) -> WorkflowTemplate | None:
        """
        Get a template by ID.

        Args:
            template_id: The template identifier.

        Returns:
            The template, or None if not found.
        """
        return self._templates.get(template_id)

    def list(self) -> builtins.list[WorkflowTemplate]:
        """List all registered templates."""
        return list(self._templates.values())

    def list_by_tag(self, tag: str) -> builtins.list[WorkflowTemplate]:
        """List templates with a specific tag."""
        return [
            template for template in self._templates.values() if tag in template.tags
        ]

    def _register_builtin_templates(self) -> None:
        """Register built-in workflow templates."""
        # 1. Analyze-Implement-Test-Review (default pipeline)
        self.register(
            WorkflowTemplate(
                template_id="analyze_implement_test_review",
                name="Analyze → Implement → Test → Review",
                description="Standard pipeline for code changes: analyze requirements, "
                "implement changes, run tests, and review results.",
                parameters=[
                    TemplateParameter(
                        name="task_id",
                        description="Base task ID for the workflow",
                        required=True,
                    ),
                    TemplateParameter(
                        name="complexity_threshold",
                        description="Complexity threshold for task decomposition",
                        default=0.7,
                        type="float",
                    ),
                    TemplateParameter(
                        name="max_reviewers",
                        description="Maximum number of parallel reviewers",
                        default=2,
                        type="int",
                    ),
                ],
                builder=self._build_analyze_implement_test_review,
                tags=["code", "development", "pipeline"],
            )
        )

        # 2. Explore-Plan-Implement (codebase workflow)
        self.register(
            WorkflowTemplate(
                template_id="explore_plan_implement",
                name="Explore → Plan → Implement",
                description="For understanding a codebase: explore structure, "
                "plan implementation strategy, then execute.",
                parameters=[
                    TemplateParameter(
                        name="codebase_path",
                        description="Path to the codebase to explore",
                        required=True,
                    ),
                    TemplateParameter(
                        name="target_files",
                        description="List of files to focus on",
                        default=None,
                        type="list",
                    ),
                ],
                builder=self._build_explore_plan_implement,
                tags=["exploration", "codebase", "planning"],
            )
        )

        # 3. Parallel Review (fan-out review chain)
        self.register(
            WorkflowTemplate(
                template_id="parallel_review",
                name="Parallel Review Chain",
                description="Fan-out review workflow where multiple agents review "
                "the same artifact in parallel, then consolidate feedback.",
                parameters=[
                    TemplateParameter(
                        name="artifact_id",
                        description="ID of the artifact to review",
                        required=True,
                    ),
                    TemplateParameter(
                        name="reviewer_count",
                        description="Number of parallel reviewers",
                        default=3,
                        type="int",
                    ),
                    TemplateParameter(
                        name="consolidation_threshold",
                        description="Minimum agreement threshold for consolidation",
                        default=0.6,
                        type="float",
                    ),
                ],
                builder=self._build_parallel_review,
                tags=["review", "parallel", "consolidation"],
            )
        )

        # 4. Retry-Until-Success (resilient execution)
        self.register(
            WorkflowTemplate(
                template_id="retry_until_success",
                name="Retry Until Success",
                description="Execute a task with retries until it succeeds or "
                "maximum attempts are reached.",
                parameters=[
                    TemplateParameter(
                        name="task_id",
                        description="Task to execute with retries",
                        required=True,
                    ),
                    TemplateParameter(
                        name="max_attempts",
                        description="Maximum number of retry attempts",
                        default=3,
                        type="int",
                    ),
                    TemplateParameter(
                        name="backoff_factor",
                        description="Exponential backoff factor between retries",
                        default=2.0,
                        type="float",
                    ),
                    TemplateParameter(
                        name="success_condition",
                        description="Python expression that defines success",
                        default="result.success",
                        type="str",
                    ),
                ],
                builder=self._build_retry_until_success,
                tags=["retry", "resilient", "recovery"],
            )
        )

        # 5. Safe Deploy (with rollback)
        self.register(
            WorkflowTemplate(
                template_id="safe_deploy",
                name="Safe Deploy with Rollback",
                description="Deployment workflow with pre-checks, deployment, "
                "verification, and automatic rollback on failure.",
                parameters=[
                    TemplateParameter(
                        name="deployment_target",
                        description="Target environment or system to deploy to",
                        required=True,
                    ),
                    TemplateParameter(
                        name="verification_timeout",
                        description="Timeout for verification checks (seconds)",
                        default=300,
                        type="int",
                    ),
                    TemplateParameter(
                        name="rollback_on_failure",
                        description="Whether to automatically rollback on failure",
                        default=True,
                        type="bool",
                    ),
                ],
                builder=self._build_safe_deploy,
                tags=["deployment", "safe", "rollback", "operations"],
            )
        )

    # ── Template Builder Functions ──────────────────────────────

    def _build_analyze_implement_test_review(
        self,
        params: dict[str, Any],
    ) -> WorkflowDefinition:
        """Build the Analyze → Implement → Test → Review workflow."""
        task_id = params["task_id"]
        complexity_threshold = params["complexity_threshold"]
        max_reviewers = params["max_reviewers"]

        # Create nodes
        nodes: dict[str, WorkflowNode] = {}

        # 1. Analyze task
        nodes["analyze"] = WorkflowNode(
            node_id="analyze",
            node_type=NodeType.TASK,
            label=f"Analyze {task_id}",
            task_id=f"{task_id}_analyze",
            agent_id="thinker",  # Thinker for analysis
        )

        # 2. Implement task (conditional on analysis success)
        nodes["implement"] = WorkflowNode(
            node_id="implement",
            node_type=NodeType.TASK,
            label=f"Implement {task_id}",
            task_id=f"{task_id}_implement",
            agent_id="coder",  # Coder for implementation
        )

        # 3. Test task
        nodes["test"] = WorkflowNode(
            node_id="test",
            node_type=NodeType.TASK,
            label=f"Test {task_id}",
            task_id=f"{task_id}_test",
            agent_id="intern",  # Intern for testing
        )

        # 4. Parallel review
        review_nodes = []
        for i in range(min(max_reviewers, 5)):  # Cap at 5 reviewers
            review_node_id = f"review_{i}"
            review_nodes.append(review_node_id)
            nodes[review_node_id] = WorkflowNode(
                node_id=review_node_id,
                node_type=NodeType.TASK,
                label=f"Review {task_id} (Reviewer {i + 1})",
                task_id=f"{task_id}_review_{i}",
                agent_id="reader",  # Reader for review
            )

        nodes["review_parallel"] = WorkflowNode(
            node_id="review_parallel",
            node_type=NodeType.PARALLEL,
            label="Parallel Review",
            children=review_nodes,
        )

        # 5. Consolidate reviews
        nodes["consolidate"] = WorkflowNode(
            node_id="consolidate",
            node_type=NodeType.TASK,
            label=f"Consolidate reviews for {task_id}",
            task_id=f"{task_id}_consolidate",
            agent_id="thinker",  # Thinker for consolidation
        )

        # Set up edges
        nodes["analyze"].edges = [NodeEdge(target_node_id="implement")]
        nodes["implement"].edges = [NodeEdge(target_node_id="test")]
        nodes["test"].edges = [NodeEdge(target_node_id="review_parallel")]
        nodes["review_parallel"].edges = [NodeEdge(target_node_id="consolidate")]

        # Add conditional edge from analyze to implement
        # Only implement if analysis passes complexity threshold
        nodes["analyze"].edges = [
            NodeEdge(
                target_node_id="implement",
                edge_type=EdgeType.CONDITIONAL,
                condition=Condition(
                    expression=f"result.outputs.get('complexity_score', 0) <= {complexity_threshold}",
                    description=f"Complexity below threshold {complexity_threshold}",
                ),
            )
        ]

        return WorkflowDefinition(
            workflow_id=f"analyze_implement_test_review_{task_id}",
            name=f"Analyze → Implement → Test → Review for {task_id}",
            nodes=nodes,
            entry_node_id="analyze",
            exit_node_ids=["consolidate"],
            description="Standard pipeline for code changes with analysis, "
            "implementation, testing, and review stages.",
        )

    def _build_explore_plan_implement(
        self,
        params: dict[str, Any],
    ) -> WorkflowDefinition:
        """Build the Explore → Plan → Implement workflow."""
        codebase_path = params["codebase_path"]
        target_files = params.get("target_files", [])

        nodes: dict[str, WorkflowNode] = {}

        # 1. Explore codebase
        nodes["explore"] = WorkflowNode(
            node_id="explore",
            node_type=NodeType.TASK,
            label=f"Explore {codebase_path}",
            task_id=f"explore_{codebase_path.replace('/', '_')}",
            agent_id="reader",  # Reader for exploration
        )

        # 2. Plan implementation
        nodes["plan"] = WorkflowNode(
            node_id="plan",
            node_type=NodeType.TASK,
            label="Plan implementation strategy",
            task_id="plan_implementation",
            agent_id="thinker",  # Thinker for planning
        )

        # 3. Implement changes
        nodes["implement"] = WorkflowNode(
            node_id="implement",
            node_type=NodeType.TASK,
            label="Implement planned changes",
            task_id="implement_changes",
            agent_id="coder",  # Coder for implementation
        )

        # Set up edges
        nodes["explore"].edges = [NodeEdge(target_node_id="plan")]
        nodes["plan"].edges = [NodeEdge(target_node_id="implement")]

        # Add metadata about target files
        if target_files:
            nodes["explore"].metadata["target_files"] = target_files

        return WorkflowDefinition(
            workflow_id=f"explore_plan_implement_{codebase_path.replace('/', '_')}",
            name=f"Explore → Plan → Implement for {codebase_path}",
            nodes=nodes,
            entry_node_id="explore",
            exit_node_ids=["implement"],
            description="Workflow for understanding a codebase and implementing changes.",
        )

    def _build_parallel_review(
        self,
        params: dict[str, Any],
    ) -> WorkflowDefinition:
        """Build the Parallel Review workflow."""
        artifact_id = params["artifact_id"]
        reviewer_count = params["reviewer_count"]
        consolidation_threshold = params["consolidation_threshold"]

        nodes: dict[str, WorkflowNode] = {}

        # Create parallel review nodes
        review_nodes = []
        for i in range(reviewer_count):
            review_node_id = f"review_{i}"
            review_nodes.append(review_node_id)
            nodes[review_node_id] = WorkflowNode(
                node_id=review_node_id,
                node_type=NodeType.TASK,
                label=f"Review {artifact_id} (Reviewer {i + 1})",
                task_id=f"{artifact_id}_review_{i}",
                agent_id="reader",  # Reader for review
            )

        # Parallel node for reviews
        nodes["parallel_review"] = WorkflowNode(
            node_id="parallel_review",
            node_type=NodeType.PARALLEL,
            label="Parallel Review",
            children=review_nodes,
        )

        # Consolidation node
        nodes["consolidate"] = WorkflowNode(
            node_id="consolidate",
            node_type=NodeType.TASK,
            label=f"Consolidate reviews for {artifact_id}",
            task_id=f"{artifact_id}_consolidate",
            agent_id="thinker",  # Thinker for consolidation
        )

        # Set up edges
        nodes["parallel_review"].edges = [NodeEdge(target_node_id="consolidate")]

        # Add consolidation threshold to metadata
        nodes["consolidate"].metadata["consolidation_threshold"] = (
            consolidation_threshold
        )

        return WorkflowDefinition(
            workflow_id=f"parallel_review_{artifact_id}",
            name=f"Parallel Review for {artifact_id}",
            nodes=nodes,
            entry_node_id="parallel_review",
            exit_node_ids=["consolidate"],
            description=f"Parallel review by {reviewer_count} reviewers with consolidation.",
        )

    def _build_retry_until_success(
        self,
        params: dict[str, Any],
    ) -> WorkflowDefinition:
        """Build the Retry Until Success workflow."""
        task_id = params["task_id"]
        max_attempts = params["max_attempts"]
        backoff_factor = params["backoff_factor"]

        nodes: dict[str, WorkflowNode] = {}

        # Create retry loop body
        nodes["execute_task"] = WorkflowNode(
            node_id="execute_task",
            node_type=NodeType.TASK,
            label=f"Execute {task_id}",
            task_id=task_id,
        )

        # While loop node for retries — stops when task succeeds or max reached
        # Condition: continue while we haven't succeeded AND haven't hit max
        loop_cond = (
            f"(iteration == 0 or not (node_results.get('execute_task') "
            f"and node_results['execute_task'].success)) "
            f"and iteration < {max_attempts}"
        )
        nodes["retry_loop"] = WorkflowNode(
            node_id="retry_loop",
            node_type=NodeType.WHILE,
            label=f"Retry {task_id} until success",
            loop_condition=Condition(
                expression=loop_cond,
                description=f"Retry until success or {max_attempts} attempts",
            ),
            loop_body=["execute_task"],
            max_iterations=max_attempts,
        )

        # Success check node (after loop exits)
        nodes["check_success"] = WorkflowNode(
            node_id="check_success",
            node_type=NodeType.IF,
            label="Check if task succeeded",
            condition=Condition(
                expression="node_results.get('execute_task') and node_results['execute_task'].success",
                description="Task succeeded",
            ),
            true_branch=["success_handler"],
            false_branch=["failure_handler"],
        )

        # Success handler
        nodes["success_handler"] = WorkflowNode(
            node_id="success_handler",
            node_type=NodeType.TASK,
            label="Handle success",
            task_id=f"{task_id}_success",
        )

        # Failure handler
        nodes["failure_handler"] = WorkflowNode(
            node_id="failure_handler",
            node_type=NodeType.TASK,
            label="Handle failure after retries",
            task_id=f"{task_id}_failure",
        )

        # Set up edges
        nodes["retry_loop"].edges = [NodeEdge(target_node_id="check_success")]

        # Add backoff factor to metadata
        nodes["retry_loop"].metadata["backoff_factor"] = backoff_factor

        return WorkflowDefinition(
            workflow_id=f"retry_until_success_{task_id}",
            name=f"Retry Until Success for {task_id}",
            nodes=nodes,
            entry_node_id="retry_loop",
            exit_node_ids=["success_handler", "failure_handler"],
            description=f"Execute {task_id} with up to {max_attempts} retries until success.",
        )

    def _build_safe_deploy(
        self,
        params: dict[str, Any],
    ) -> WorkflowDefinition:
        """Build the Safe Deploy with Rollback workflow."""
        deployment_target = params["deployment_target"]
        verification_timeout = params["verification_timeout"]
        rollback_on_failure = params["rollback_on_failure"]

        nodes: dict[str, WorkflowNode] = {}

        # 1. Pre-deployment checks
        nodes["pre_checks"] = WorkflowNode(
            node_id="pre_checks",
            node_type=NodeType.TASK,
            label=f"Pre-deployment checks for {deployment_target}",
            task_id=f"{deployment_target}_pre_checks",
        )

        # 2. Deployment (in try-catch block)
        nodes["deploy"] = WorkflowNode(
            node_id="deploy",
            node_type=NodeType.TASK,
            label=f"Deploy to {deployment_target}",
            task_id=f"{deployment_target}_deploy",
        )

        # 3. Verification
        nodes["verify"] = WorkflowNode(
            node_id="verify",
            node_type=NodeType.TASK,
            label=f"Verify deployment to {deployment_target}",
            task_id=f"{deployment_target}_verify",
            resource=ResourceConstraint(
                timeout_seconds=verification_timeout,
            ),
        )

        # 4. Rollback (compensation action)
        nodes["rollback"] = WorkflowNode(
            node_id="rollback",
            node_type=NodeType.COMPENSATE,
            label=f"Rollback deployment from {deployment_target}",
        )

        # Try-catch node for deployment
        nodes["deploy_try_catch"] = WorkflowNode(
            node_id="deploy_try_catch",
            node_type=NodeType.TRY_CATCH,
            label="Deployment with error handling",
            try_body=["deploy", "verify"],
            catch_handlers=[
                NodeEdge(
                    target_node_id="rollback",
                    edge_type=EdgeType.ERROR,
                )
            ]
            if rollback_on_failure
            else [],
        )

        # 5. Post-deployment
        nodes["post_deploy"] = WorkflowNode(
            node_id="post_deploy",
            node_type=NodeType.TASK,
            label=f"Post-deployment tasks for {deployment_target}",
            task_id=f"{deployment_target}_post_deploy",
        )

        # Set up edges
        nodes["pre_checks"].edges = [NodeEdge(target_node_id="deploy_try_catch")]
        nodes["deploy_try_catch"].edges = [NodeEdge(target_node_id="post_deploy")]

        # Add rollback configuration
        if rollback_on_failure:
            nodes["deploy"].compensations = [
                CompensationAction(
                    action_node_id="rollback",
                    trigger_on=["failed"],
                    description="Rollback on deployment failure",
                )
            ]
            nodes["verify"].compensations = [
                CompensationAction(
                    action_node_id="rollback",
                    trigger_on=["failed"],
                    description="Rollback on verification failure",
                )
            ]

        return WorkflowDefinition(
            workflow_id=f"safe_deploy_{deployment_target.replace('/', '_')}",
            name=f"Safe Deploy to {deployment_target}",
            nodes=nodes,
            entry_node_id="pre_checks",
            exit_node_ids=["post_deploy", "rollback"],
            description="Safe deployment workflow with pre-checks, deployment, "
            "verification, and rollback on failure.",
        )


# Global template registry instance
_template_registry = TemplateRegistry()


def get_template_registry() -> TemplateRegistry:
    """Get the global template registry instance."""
    return _template_registry


def register_template(template: WorkflowTemplate) -> None:
    """Register a template in the global registry."""
    _template_registry.register(template)


def get_template(template_id: str) -> WorkflowTemplate | None:
    """Get a template from the global registry."""
    return _template_registry.get(template_id)


def list_templates() -> list[WorkflowTemplate]:
    """List all templates in the global registry."""
    return _template_registry.list()
