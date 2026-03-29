"""
Workflow template models for reusable multi-step orchestration patterns.

Defines YAML-serializable workflow templates with variable substitution,
step definitions, and validation rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskType(StrEnum):
    """Supported task types for workflow steps."""

    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    TESTING = "testing"
    REFACTORING = "refactoring"
    DOCUMENTATION = "documentation"
    ANALYSIS = "analysis"
    CONFIGURATION = "configuration"
    DEPLOYMENT = "deployment"
    CUSTOM = "custom"

    @classmethod
    def from_string(cls, value: str) -> TaskType:
        """Convert string to TaskType, handling case-insensitive matching."""
        value_upper = value.upper().replace("-", "_")
        for task_type in cls:
            if task_type.value.upper() == value_upper:
                return task_type
        # Try to match without underscores
        for task_type in cls:
            if task_type.value.replace("_", "").upper() == value_upper.replace("_", ""):
                return task_type
        raise ValueError(f"Invalid task type: {value}")


@dataclass
class VariableDef:
    """Definition of a workflow variable."""

    name: str
    description: str = ""
    default: Any = None
    required: bool = False
    type: str = "string"  # string, number, boolean, list, dict

    def validate_value(self, value: Any) -> bool:
        """Validate a value against the variable definition."""
        if value is None:
            return not self.required

        if self.type == "string":
            return isinstance(value, str)
        elif self.type == "number":
            return isinstance(value, (int, float))
        elif self.type == "boolean":
            return isinstance(value, bool)
        elif self.type == "list":
            return isinstance(value, list)
        elif self.type == "dict":
            return isinstance(value, dict)
        return True


@dataclass
class WorkflowStep:
    """A single step in a workflow template."""

    name: str
    task_type: TaskType
    description_template: str
    files: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    model_override: str | None = None
    condition: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def substitute_variables(self, variables: dict[str, Any]) -> WorkflowStep:
        """Create a new step with variables substituted in templates."""

        # Helper function to substitute variables in a string
        def substitute(text: str) -> str:
            if not text:
                return text
            for var_name, var_value in variables.items():
                placeholder = f"{{{var_name}}}"
                if placeholder in text:
                    text = text.replace(placeholder, str(var_value))
            return text

        return WorkflowStep(
            name=substitute(self.name),
            task_type=self.task_type,
            description_template=substitute(self.description_template),
            files=[substitute(f) for f in self.files],
            depends_on=self.depends_on.copy(),  # Don't substitute in dependencies
            model_override=self.model_override,
            condition=substitute(self.condition) if self.condition else None,
            metadata=self.metadata.copy(),
        )

    def validate(self) -> list[str]:
        """Validate the step configuration."""
        errors = []

        if not self.name.strip():
            errors.append("Step name cannot be empty")

        if not self.description_template.strip():
            errors.append("Step description cannot be empty")

        # Check for circular dependencies (will be checked at workflow level)
        if self.name in self.depends_on:
            errors.append(f"Step '{self.name}' cannot depend on itself")

        return errors


@dataclass
class WorkflowTemplate:
    """Complete workflow template definition."""

    name: str
    description: str
    version: str = "1.0.0"
    variables: dict[str, VariableDef] = field(default_factory=dict)
    steps: list[WorkflowStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def substitute_variables(self, variables: dict[str, Any]) -> WorkflowTemplate:
        """Create a new template with variables substituted."""

        # Helper function to substitute variables in a string
        def substitute(text: str, vars_dict: dict[str, Any]) -> str:
            if not text:
                return text
            for var_name, var_value in vars_dict.items():
                placeholder = f"{{{var_name}}}"
                if placeholder in text:
                    text = text.replace(placeholder, str(var_value))
            return text

        # Merge provided variables with defaults
        all_vars = {}
        for var_name, var_def in self.variables.items():
            if var_name in variables:
                all_vars[var_name] = variables[var_name]
            elif var_def.default is not None:
                all_vars[var_name] = var_def.default
            elif var_def.required:
                raise ValueError(f"Required variable '{var_name}' not provided")

        # Substitute variables in description and steps
        substituted_description = substitute(self.description, all_vars)
        substituted_steps = [step.substitute_variables(all_vars) for step in self.steps]

        return WorkflowTemplate(
            name=self.name,
            description=substituted_description,
            version=self.version,
            variables=self.variables.copy(),
            steps=substituted_steps,
            metadata=self.metadata.copy(),
        )

    def validate(self) -> list[str]:
        """Validate the template structure."""
        errors = []

        if not self.name.strip():
            errors.append("Template name cannot be empty")

        if not self.description.strip():
            errors.append("Template description cannot be empty")

        # Validate version format (semver-ish)
        if not re.match(r"^\d+\.\d+\.\d+$", self.version):
            errors.append(f"Invalid version format: {self.version}. Expected X.Y.Z")

        # Validate variables
        for var_name, var_def in self.variables.items():
            if not var_name.strip():
                errors.append("Variable name cannot be empty")

        # Validate steps
        step_names = set()
        for i, step in enumerate(self.steps):
            step_errors = step.validate()
            if step_errors:
                errors.extend([f"Step {i} ('{step.name}'): {e}" for e in step_errors])

            if step.name in step_names:
                errors.append(f"Duplicate step name: '{step.name}'")
            step_names.add(step.name)

        # Check for circular dependencies
        if self._has_circular_dependencies():
            errors.append("Workflow contains circular dependencies")

        return errors

    def _has_circular_dependencies(self) -> bool:
        """Check if the workflow has circular dependencies."""
        # Build adjacency list
        adj = {step.name: set(step.depends_on) for step in self.steps}

        # Kahn's algorithm for cycle detection
        in_degree = {step.name: 0 for step in self.steps}
        for step in self.steps:
            for dep in step.depends_on:
                if dep in in_degree:
                    in_degree[dep] += 1

        # Find nodes with no incoming edges
        queue = [node for node, deg in in_degree.items() if deg == 0]

        processed = 0
        while queue:
            node = queue.pop(0)
            processed += 1

            for neighbor in adj.get(node, []):
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        return processed != len(self.steps)

    def get_execution_order(self) -> list[list[str]]:
        """
        Get steps grouped by execution wave (parallel execution groups).

        Returns:
            List of lists where each inner list contains step names
            that can execute in parallel (same dependency depth).
        """
        # Build adjacency list and reverse adjacency list
        adj = {step.name: set(step.depends_on) for step in self.steps}
        reverse_adj = {step.name: set() for step in self.steps}

        for step in self.steps:
            for dep in step.depends_on:
                if dep in reverse_adj:
                    reverse_adj[dep].add(step.name)

        # Find nodes with no dependencies
        current_wave = [step.name for step in self.steps if not step.depends_on]
        waves = []
        visited = set()

        while current_wave:
            waves.append(current_wave.copy())
            visited.update(current_wave)

            # Find next wave: nodes whose dependencies are all in visited
            next_wave = []
            for step in self.steps:
                if step.name in visited:
                    continue
                if all(dep in visited for dep in step.depends_on):
                    next_wave.append(step.name)

            current_wave = next_wave

        return waves
