#!/usr/bin/env python3
"""
Example: Workflow Execution from Template

This example demonstrates how to:
1. Load and validate workflow templates from YAML
2. Create execution plans with variable substitution
3. Handle conditional steps and dependencies
4. Execute workflows via the WorkflowEngine
"""

import os
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omni.orchestration import WorkflowEngine
from omni.orchestration.workflow_models import WorkflowTemplate


def create_custom_template() -> str:
    """Create a custom workflow template for demonstration."""
    return """
name: "Feature Implementation Workflow"
description: "Complete workflow for implementing new features with testing and review"
version: "1.2.0"

variables:
  feature_name:
    description: "Name of the feature to implement"
    required: true
    type: "string"

  complexity:
    description: "Complexity level of the feature"
    type: "string"
    default: "medium"

  include_tests:
    description: "Whether to include automated tests"
    type: "boolean"
    default: true

  include_docs:
    description: "Whether to include documentation"
    type: "boolean"
    default: true

steps:
  - name: "requirements_analysis"
    task_type: "analysis"
    description: "Analyze requirements for {feature_name}"

  - name: "technical_design"
    task_type: "analysis"
    description: "Create technical design for {feature_name}"
    depends_on: ["requirements_analysis"]
    condition: "{complexity} != 'simple'"

  - name: "implementation"
    task_type: "code_generation"
    description: "Implement {feature_name}"
    depends_on: ["requirements_analysis"]

  - name: "unit_tests"
    task_type: "testing"
    description: "Write unit tests for {feature_name}"
    depends_on: ["implementation"]
    condition: "{include_tests}"

  - name: "documentation"
    task_type: "documentation"
    description: "Write documentation for {feature_name}"
    depends_on: ["implementation"]
    condition: "{include_docs}"

  - name: "code_review"
    task_type: "code_review"
    description: "Review implementation of {feature_name}"
    depends_on: ["implementation"]

  - name: "final_integration"
    task_type: "analysis"
    description: "Final integration and validation of {feature_name}"
    depends_on: ["code_review"]
"""


def demonstrate_template_loading():
    """Demonstrate loading and validating workflow templates."""
    print("\n1. Template Loading and Validation")
    print("=" * 60)

    engine = WorkflowEngine()

    # Create temporary template file
    template_content = create_custom_template()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(template_content)
        temp_path = f.name

    try:
        # Load template
        print("Loading template...")
        template = engine.load_template(temp_path)

        print(f"✅ Template loaded: {template.name} v{template.version}")
        print(f"   Description: {template.description}")
        print(f"   Steps: {len(template.steps)}")
        print(f"   Variables: {len(template.variables)}")

        # Validate template
        print("\nValidating template...")
        validation_errors = engine.validate_template(template)

        if validation_errors:
            print("❌ Validation errors:")
            for error in validation_errors:
                print(f"   - {error}")
        else:
            print("✅ Template validation passed!")

        # Show template structure
        print("\n📋 Template structure:")
        print("   Variables defined:")
        for var_name, var_def in template.variables.items():
            required = "✓" if var_def.required else " "
            default = f" (default: {var_def.default})" if var_def.default is not None else ""
            print(f"     [{required}] {var_name}: {var_def.description}{default}")

        return template

    finally:
        os.unlink(temp_path)


def demonstrate_execution_planning(template: WorkflowTemplate):
    """Demonstrate execution planning based on template."""
    print("\n\n2. Execution Planning")
    print("=" * 60)

    engine = WorkflowEngine()

    test_cases = [
        {
            "name": "Simple Feature",
            "variables": {
                "feature_name": "user-profile-avatar",
                "complexity": "simple",
                "include_tests": True,
                "include_docs": False,
            },
        },
        {
            "name": "Complex Feature",
            "variables": {
                "feature_name": "payment-processing",
                "complexity": "complex",
                "include_tests": True,
                "include_docs": True,
            },
        },
        {
            "name": "Medium Feature (No Tests)",
            "variables": {
                "feature_name": "search-filter",
                "complexity": "medium",
                "include_tests": False,
                "include_docs": True,
            },
        },
    ]

    for test_case in test_cases:
        print(f"\n📊 Test case: {test_case['name']}")
        print("-" * 40)

        variables = test_case["variables"]
        print(f"   Variables: {variables}")

        # Substitute variables in template
        substituted = template.substitute_variables(variables)

        # Create execution plan
        plan = engine.create_execution_plan(substituted, variables)

        # Show which steps will execute
        active_steps = [s for s in substituted.steps if plan.is_step_active(s.name)]
        skipped_steps = [s for s in substituted.steps if not plan.is_step_active(s.name)]

        print(f"   Active steps: {len(active_steps)}")
        print(f"   Skipped steps: {len(skipped_steps)}")

        if skipped_steps:
            print(f"   Skipped: {[s.name for s in skipped_steps]}")

        # Show execution order
        execution_waves = plan.get_execution_order()
        print(f"   Execution waves: {len(execution_waves)}")

        for i, wave in enumerate(execution_waves, 1):
            print(f"     Wave {i}: {wave}")


def demonstrate_workflow_execution(template: WorkflowTemplate):
    """Demonstrate actual workflow execution via WorkflowEngine."""
    print("\n\n3. Workflow Execution")
    print("=" * 60)

    engine = WorkflowEngine()

    variables = {
        "feature_name": "demo-authentication",
        "complexity": "medium",
        "include_tests": True,
        "include_docs": True,
    }

    print("Executing workflow with variables:")
    for key, value in variables.items():
        print(f"   {key}: {value}")

    # Execute the workflow (returns OrchestrationResult)
    result = engine.execute(template, variables)

    print("\n✅ Execution result:")
    print(f"   Success: {result.success}")
    print(f"   Summary: {result.summary}")
    print(f"   Total cost: ${result.total_cost:.6f}")
    print(f"   Total tokens: {result.total_tokens}")

    if result.warnings:
        print(f"   Warnings: {result.warnings}")

    if result.errors:
        print(f"   Errors: {result.errors}")


def demonstrate_existing_templates():
    """Demonstrate loading the existing example templates."""
    print("\n\n4. Existing Workflow Templates")
    print("=" * 60)

    engine = WorkflowEngine()
    templates_dir = Path(__file__).parent / "workflow_templates"

    if not templates_dir.exists():
        print("   ⚠️  No workflow_templates directory found")
        return

    yaml_files = list(templates_dir.glob("*.yaml")) + list(templates_dir.glob("*.yml"))

    if not yaml_files:
        print("   ⚠️  No YAML template files found")
        return

    for yaml_file in yaml_files:
        print(f"\n   📄 {yaml_file.name}")
        try:
            template = engine.load_template(str(yaml_file))
            print(f"      Name: {template.name}")
            print(f"      Version: {template.version}")
            print(f"      Steps: {len(template.steps)}")
            print(f"      Variables: {len(template.variables)}")

            # Show execution waves
            waves = template.get_execution_order()
            print(f"      Execution waves: {len(waves)}")
        except Exception as e:
            print(f"      ❌ Error loading: {e}")


def main():
    """Run all workflow template demonstrations."""
    print("🚀 Workflow from Template Demo")
    print("=" * 60)

    try:
        # 1. Template loading and validation
        template = demonstrate_template_loading()

        # 2. Execution planning
        demonstrate_execution_planning(template)

        # 3. Workflow execution
        demonstrate_workflow_execution(template)

        # 4. Existing templates
        demonstrate_existing_templates()

        print("\n" + "=" * 60)
        print("✅ All demonstrations completed successfully!")

        print("\nSummary of workflow template capabilities:")
        print("1. ✅ Template loading and validation")
        print("2. ✅ Variable substitution and conditional execution")
        print("3. ✅ Dependency management and parallel execution")
        print("4. ✅ Workflow execution via WorkflowEngine")

        print("\nNext steps:")
        print("1. Create your own templates in examples/workflow_templates/")
        print("2. Use 'omni workflow' CLI to execute templates")
        print("3. Check docs/workflow-templates.md for detailed guide")

    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        print("Make sure you have installed Omni-LLM in development mode:")
        print("  pip install -e '.[dev]'")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
