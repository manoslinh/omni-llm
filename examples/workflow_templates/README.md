# Workflow Template Engine

The Workflow Template Engine provides reusable YAML-based workflow templates for multi-step orchestration patterns.

## Overview

Workflow templates allow you to define reusable orchestration patterns with:
- **Variables**: Parameterize workflows with typed variables
- **Steps**: Define tasks with dependencies and conditions
- **Conditional execution**: Skip steps based on runtime conditions
- **Model overrides**: Specify which AI model to use for each step
- **Parallel execution**: Steps without dependencies run in parallel

## Template Structure

A workflow template is a YAML file with the following structure:

```yaml
name: "Workflow Name"
description: "Workflow description"
version: "1.0.0"

variables:
  variable_name:
    description: "Variable description"
    required: true
    type: "string"  # string, number, boolean, list, dict
    default: "default_value"

metadata:
  category: "workflow-category"
  estimated_time: "30 minutes"

steps:
  - name: "step_name"
    task_type: "code_generation"  # analysis, testing, documentation, etc.
    description: "Step description with {variable} substitution"
    files: ["{file_path}"]
    depends_on: ["previous_step"]
    model_override: "coder"  # Optional model override
    condition: "{run_this_step}"  # Optional condition
```

## Supported Task Types

- `analysis` - Analyze requirements or code
- `code_generation` - Generate or modify code
- `code_review` - Review code for quality
- `testing` - Create or run tests
- `refactoring` - Refactor existing code
- `documentation` - Create or update documentation
- `configuration` - Update configuration files
- `deployment` - Deployment-related tasks
- `custom` - Custom task type

## Usage Examples

### Basic Usage

```python
from omni.orchestration import WorkflowEngine

# Load a template
engine = WorkflowEngine()
template = engine.load_template("path/to/template.yaml")

# Execute with variables
variables = {
    "file_path": "src/example.py",
    "feature_name": "New Feature"
}
result = engine.execute(template, variables)

print(f"Success: {result.success}")
print(f"Summary: {result.summary}")
```

### Creating a Template Programmatically

```python
from omni.orchestration import WorkflowTemplate, WorkflowStep, TaskType, VariableDef

template = WorkflowTemplate(
    name="My Workflow",
    description="Custom workflow",
    version="1.0.0",
    variables={
        "target_file": VariableDef(
            name="target_file",
            description="File to process",
            required=True,
            type="string"
        )
    },
    steps=[
        WorkflowStep(
            name="analyze",
            task_type=TaskType.ANALYSIS,
            description="Analyze {target_file}"
        ),
        WorkflowStep(
            name="implement",
            task_type=TaskType.CODE_GENERATION,
            description="Implement changes in {target_file}",
            depends_on=["analyze"]
        )
    ]
)
```

## Example Templates

This directory contains example workflow templates:

### 1. `code_review_workflow.yaml`
Standard workflow for code review with automatic fixes.

**Variables:**
- `file_path` (required): Path to the file to review
- `issue_description` (required): Description of the issue
- `target_branch`: Target branch for the fix (default: "main")

**Steps:** Analyze → Implement → Review → Tests → Documentation

### 2. `feature_implementation.yaml`
End-to-end workflow for implementing a new feature.

**Variables:**
- `feature_name` (required): Name of the feature
- `module_path` (required): Path to the module
- `test_coverage`: Minimum test coverage (default: 80)

**Steps:** Design → Implement Core → Implement Tests → Review → Integration Test → Document → Validate

### 3. `refactoring_workflow.yaml`
Safe refactoring workflow with validation at each step.

**Variables:**
- `target_file` (required): File to refactor
- `refactoring_type` (required): Type of refactoring
- `safety_level`: Safety level (default: "medium")

**Steps:** Analysis → Backup → Refactor → Unit Tests → Review → Integration → Documentation → Verification

## Variable Substitution

Variables are substituted using `{variable_name}` syntax:

```yaml
steps:
  - name: "process_file"
    task_type: "code_generation"
    description: "Process {file_path} with {algorithm}"
    files: ["{file_path}"]
```

## Conditional Execution

Steps can include conditions that are evaluated at runtime:

```yaml
steps:
  - name: "run_tests"
    task_type: "testing"
    description: "Run tests"
    condition: "{run_tests_enabled}"
```

Conditions can be simple variable checks or complex expressions:
- `{variable}` - True if variable exists and is truthy
- `{count} > 3` - Python expression with variable substitution
- `{enabled} and {mode} == 'production'` - Complex logic

## Execution Order

The engine automatically calculates execution order based on dependencies:

```python
waves = template.get_execution_order()
# Returns: [["step1"], ["step2", "step3"], ["step4"]]
# Steps in the same list can execute in parallel
```

## Integration with Coordination System

The workflow engine integrates with the existing coordination system:

1. **Load template** from YAML
2. **Substitute variables** in the template
3. **Create TaskGraph** from workflow steps
4. **Execute** via coordination engine
5. **Return OrchestrationResult** with execution results

## Validation

Templates are validated for:
- Required fields
- Valid version format (X.Y.Z)
- No circular dependencies
- Valid task types
- Variable name conflicts

```python
errors = engine.validate_template(template)
if errors:
    print(f"Validation errors: {errors}")
```

## Best Practices

1. **Use semantic versioning** for templates
2. **Provide defaults** for optional variables
3. **Keep steps focused** on single responsibilities
4. **Use conditions** for optional steps
5. **Document variables** with descriptions
6. **Test templates** with different variable combinations
7. **Use metadata** for categorization and search