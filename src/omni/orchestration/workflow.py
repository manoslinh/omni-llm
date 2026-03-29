"""
Workflow template engine for reusable multi-step orchestration patterns.

Loads YAML workflow templates, substitutes variables, creates TaskGraphs,
and executes via the coordination system.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from ..task.models import Task, TaskGraph
from ..task.models import TaskType as CoreTaskType
from .integrator import OrchestrationResult
from .workflow_models import TaskType, VariableDef, WorkflowStep, WorkflowTemplate

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """
    Engine for loading and executing workflow templates.

    Responsibilities:
    1. Load YAML workflow templates
    2. Substitute variables in templates
    3. Convert workflow steps to TaskGraph
    4. Execute via coordination system
    5. Validate template structure
    """

    def __init__(self, coordination_engine=None):
        """
        Initialize the workflow engine.

        Args:
            coordination_engine: Optional coordination engine for execution.
                                 If None, will try to import from coordination module.
        """
        self.coordination_engine = coordination_engine

    def load_template(self, path: str) -> WorkflowTemplate:
        """
        Load a workflow template from a YAML file.

        Args:
            path: Path to the YAML template file

        Returns:
            WorkflowTemplate instance

        Raises:
            FileNotFoundError: If the file doesn't exist
            yaml.YAMLError: If the YAML is invalid
            ValueError: If the template structure is invalid
        """
        path_obj = Path(path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Template file not found: {path}")

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("Template must be a YAML dictionary")

        # Parse variables
        variables = {}
        for var_name, var_data in data.get("variables", {}).items():
            if isinstance(var_data, dict):
                var_def = VariableDef(
                    name=var_name,
                    description=var_data.get("description", ""),
                    default=var_data.get("default"),
                    required=var_data.get("required", False),
                    type=var_data.get("type", "string"),
                )
            else:
                # Simple variable definition
                var_def = VariableDef(
                    name=var_name,
                    default=var_data,
                    required=False,
                    type=type(var_data).__name__ if var_data is not None else "string",
                )
            variables[var_name] = var_def

        # Parse steps
        steps = []
        for step_data in data.get("steps", []):
            if not isinstance(step_data, dict):
                raise ValueError(f"Step must be a dictionary, got {type(step_data)}")

            # Convert string task_type to TaskType enum
            task_type_str = step_data.get("task_type", "custom")
            try:
                task_type = TaskType.from_string(task_type_str)
            except ValueError as e:
                raise ValueError(f"Invalid task type '{task_type_str}': {e}")

            step = WorkflowStep(
                name=step_data["name"],
                task_type=task_type,
                description_template=step_data.get("description", ""),
                files=step_data.get("files", []),
                depends_on=step_data.get("depends_on", []),
                model_override=step_data.get("model_override"),
                condition=step_data.get("condition"),
                metadata=step_data.get("metadata", {}),
            )
            steps.append(step)

        template = WorkflowTemplate(
            name=data.get("name", "Unnamed Workflow"),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            variables=variables,
            steps=steps,
            metadata=data.get("metadata", {}),
        )

        # Validate the template
        validation_errors = self.validate_template(template)
        if validation_errors:
            raise ValueError(f"Template validation failed: {validation_errors}")

        logger.info(
            f"Loaded workflow template '{template.name}' v{template.version} "
            f"with {len(steps)} steps and {len(variables)} variables"
        )

        return template

    def execute(
        self,
        template: WorkflowTemplate,
        variables: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> OrchestrationResult:
        """
        Execute a workflow template with the given variables.

        Args:
            template: WorkflowTemplate to execute
            variables: Dictionary of variable values
            context: Optional execution context

        Returns:
            OrchestrationResult with execution results

        Raises:
            ValueError: If required variables are missing or validation fails
        """
        # Substitute variables in template
        substituted = template.substitute_variables(variables)

        # Create TaskGraph from workflow steps
        task_graph = self._create_task_graph(substituted, context or {})

        # Get coordination engine
        coordination = self._get_coordination_engine()
        if coordination is None:
            logger.warning("No coordination engine available, returning mock result")
            return self._create_mock_result(substituted, task_graph)

        # Execute via coordination system
        # Note: In a real implementation, this would use the coordination engine
        # to execute the task graph and return the integrated results
        logger.info(
            f"Executing workflow '{template.name}' with {task_graph.size} tasks"
        )

        # For now, return a mock result since we need to integrate with P2-19
        return self._create_mock_result(substituted, task_graph)

    def validate_template(self, template: WorkflowTemplate) -> list[str]:
        """
        Validate a workflow template structure.

        Args:
            template: WorkflowTemplate to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        return template.validate()

    def _create_task_graph(
        self, template: WorkflowTemplate, context: dict[str, Any]
    ) -> TaskGraph:
        """
        Create a TaskGraph from a workflow template.

        Args:
            template: WorkflowTemplate with substituted variables
            context: Execution context

        Returns:
            TaskGraph ready for execution
        """
        task_graph = TaskGraph(name=f"workflow-{template.name}")

        # First pass: collect which steps will be included
        included_steps = set()
        for step in template.steps:
            # Skip steps with conditions that evaluate to False
            if step.condition and not self._evaluate_condition(step.condition, context):
                logger.debug(
                    f"Skipping step '{step.name}' due to condition: {step.condition}"
                )
                continue
            included_steps.add(step.name)

        # Second pass: create tasks, filtering out dependencies to skipped steps
        for step in template.steps:
            if step.name not in included_steps:
                continue

            # Filter dependencies to only include steps that are actually included
            valid_dependencies = [
                dep for dep in step.depends_on if dep in included_steps
            ]

            # Convert WorkflowStep to Task
            task = Task(
                task_id=f"workflow-{template.name}-{step.name}",
                description=step.description_template,
                task_type=self._map_task_type(step.task_type),
                priority=5,  # Default priority
                dependencies=[
                    f"workflow-{template.name}-{dep}" for dep in valid_dependencies
                ],
                context={
                    "workflow_step": step.name,
                    "workflow_name": template.name,
                    "files": step.files,
                    "model_override": step.model_override,
                    **step.metadata,
                },
            )

            task_graph.add_task(task)

        return task_graph

    def _map_task_type(self, workflow_task_type: TaskType) -> CoreTaskType:
        """Map workflow TaskType to core TaskType."""
        mapping = {
            TaskType.CODE_GENERATION: CoreTaskType.CODE_GENERATION,
            TaskType.CODE_REVIEW: CoreTaskType.CODE_REVIEW,
            TaskType.TESTING: CoreTaskType.TESTING,
            TaskType.REFACTORING: CoreTaskType.REFACTORING,
            TaskType.DOCUMENTATION: CoreTaskType.DOCUMENTATION,
            TaskType.ANALYSIS: CoreTaskType.ANALYSIS,
            TaskType.CONFIGURATION: CoreTaskType.CONFIGURATION,
            TaskType.DEPLOYMENT: CoreTaskType.DEPLOYMENT,
            TaskType.CUSTOM: CoreTaskType.CUSTOM,
        }
        return mapping.get(workflow_task_type, CoreTaskType.CUSTOM)

    def _evaluate_condition(self, condition: str, context: dict[str, Any]) -> bool:
        """
        Evaluate a condition string in the given context.

        Simple implementation: checks if variable exists and is truthy.
        In a real implementation, this could use a proper expression evaluator.

        SECURITY WARNING: This method uses Python's eval() function which poses
        a security risk if condition strings come from untrusted sources.
        The current implementation restricts the namespace to only the context
        dictionary, but eval() can still execute arbitrary Python code.
        
        PHASE 3 MITIGATION PLAN: Replace eval() with ast.literal_eval() for
        simple expressions or implement a restricted expression evaluator that
        only supports safe operations (comparisons, logical operators, arithmetic).
        This will eliminate the security risk while maintaining functionality.

        Args:
            condition: Condition string (e.g., "{variable} == 'value'")
            context: Execution context with variables

        Returns:
            True if condition evaluates to True, False otherwise
        """
        # Simple implementation: check if the condition references a variable
        # and that variable exists and is truthy in the context
        import re

        # Extract variable names from condition (both {var} and bare var names)
        var_pattern = r"{(\w+)}"
        braced_variables = re.findall(var_pattern, condition)

        # Also look for bare variable names that are valid Python identifiers
        # but not keywords or built-in functions
        bare_variables = []
        words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", condition)
        python_keywords = {"and", "or", "not", "in", "is", "True", "False", "None"}
        for word in words:
            if (
                word not in python_keywords
                and word not in braced_variables
                and not word.isdigit()
            ):
                bare_variables.append(word)

        all_variables = set(braced_variables + bare_variables)

        if not all_variables:
            # No variables, treat as Python expression
            # SECURITY NOTE: eval() is used here - see Phase 3 mitigation plan in docstring
            try:
                return bool(eval(condition, {}, context))
            except Exception:
                logger.warning(f"Failed to evaluate condition: {condition}")
                return False

        # For simple variable checks (just {variable} format)
        if (
            len(braced_variables) == 1
            and condition.strip() == f"{{{braced_variables[0]}}}"
        ):
            var_name = braced_variables[0]
            if var_name not in context:
                return False
            return bool(context[var_name])

        # For complex expressions, try to evaluate as Python
        # First substitute braced variables in the condition
        substituted_condition = condition
        for var_name in braced_variables:
            if var_name in context:
                # Replace {var_name} with the actual value
                placeholder = f"{{{var_name}}}"
                value = context[var_name]
                # Handle string values by quoting them
                if isinstance(value, str):
                    value = f"'{value}'"
                substituted_condition = substituted_condition.replace(
                    placeholder, str(value)
                )
            else:
                # Variable not in context
                return False

        # Now evaluate with context available for bare variables
        # SECURITY NOTE: eval() is used here - see Phase 3 mitigation plan in docstring
        try:
            return bool(eval(substituted_condition, {}, context))
        except Exception:
            logger.warning(
                f"Failed to evaluate condition: {condition} (substituted: {substituted_condition})"
            )
            return False

    def _get_coordination_engine(self):
        """Get the coordination engine, importing if necessary."""
        if self.coordination_engine is not None:
            return self.coordination_engine

        try:
            from ..coordination.engine import CoordinationEngine

            self.coordination_engine = CoordinationEngine()
            return self.coordination_engine
        except ImportError:
            logger.warning("Coordination engine not available")
            return None

    def _create_mock_result(
        self, template: WorkflowTemplate, task_graph: TaskGraph
    ) -> OrchestrationResult:
        """Create a mock OrchestrationResult for testing."""
        from .integrator import OrchestrationResult

        return OrchestrationResult(
            success=True,
            merged_files={},
            total_cost=0.0,
            total_tokens=0,
            commit_message=f"Workflow '{template.name}' executed successfully",
            verification_result=None,
            summary=f"Executed workflow '{template.name}' with {len(template.steps)} steps",
            errors=[],
            warnings=["Mock execution - real coordination not integrated yet"],
            metadata={
                "workflow_name": template.name,
                "workflow_version": template.version,
                "task_count": task_graph.size,
                "mock_execution": True,
            },
        )
