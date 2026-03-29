#!/usr/bin/env python3
"""
Demo script showing how to use the Workflow Template Engine.
"""

import os
import tempfile
from pathlib import Path

from omni.orchestration import WorkflowEngine


def demo_basic_workflow():
    """Demo basic workflow loading and execution."""
    print("=== Workflow Template Engine Demo ===\n")

    # Create a simple workflow template
    yaml_content = """
name: "Demo Workflow"
description: "A simple demo workflow for testing"
version: "1.0.0"

variables:
  filename:
    description: "Name of the file to process"
    required: true
    type: "string"
  add_tests:
    description: "Whether to add tests"
    default: true
    type: "boolean"

steps:
  - name: "analyze"
    task_type: "analysis"
    description: "Analyze requirements for {filename}"

  - name: "implement"
    task_type: "code_generation"
    description: "Implement functionality for {filename}"
    depends_on: ["analyze"]

  - name: "add_tests"
    task_type: "testing"
    description: "Add tests for {filename}"
    depends_on: ["implement"]
    condition: "{add_tests}"

  - name: "review"
    task_type: "code_review"
    description: "Review implementation of {filename}"
    depends_on: ["implement", "add_tests"]
"""

    # Write to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        temp_path = f.name

    try:
        # Create workflow engine
        engine = WorkflowEngine()

        # Load the template
        print("1. Loading workflow template...")
        template = engine.load_template(temp_path)
        print(f"   Loaded: {template.name} v{template.version}")
        print(f"   Description: {template.description}")
        print(f"   Steps: {len(template.steps)}")
        print(f"   Variables: {len(template.variables)}")

        # Validate the template
        print("\n2. Validating template...")
        errors = engine.validate_template(template)
        if errors:
            print(f"   Validation errors: {errors}")
        else:
            print("   Template is valid!")

        # Show execution order
        print("\n3. Execution order:")
        waves = template.get_execution_order()
        for i, wave in enumerate(waves, 1):
            print(f"   Wave {i}: {', '.join(wave)}")

        # Execute with variables
        print("\n4. Executing workflow...")
        variables = {
            "filename": "example.py",
            "add_tests": True
        }

        result = engine.execute(template, variables)
        print(f"   Success: {result.success}")
        print(f"   Summary: {result.summary}")
        print(f"   Tasks created: {result.metadata.get('task_count', 0)}")

        # Test with add_tests = False
        print("\n5. Executing workflow without tests...")
        variables = {
            "filename": "example.py",
            "add_tests": False
        }

        result = engine.execute(template, variables)
        print(f"   Success: {result.success}")
        print(f"   Summary: {result.summary}")

    finally:
        os.unlink(temp_path)

    print("\n=== Demo Complete ===")


def demo_example_templates():
    """Demo loading example templates."""
    print("\n=== Loading Example Templates ===\n")

    engine = WorkflowEngine()
    example_dir = Path(__file__).parent / "workflow_templates"

    if not example_dir.exists():
        print("Example templates directory not found")
        return

    for template_file in example_dir.glob("*.yaml"):
        print(f"Loading {template_file.name}...")
        try:
            template = engine.load_template(str(template_file))
            print(f"  ✓ {template.name} v{template.version}")
            print(f"    {template.description[:60]}...")
            print(f"    Steps: {len(template.steps)}, Variables: {len(template.variables)}")

            # Show a quick execution plan
            waves = template.get_execution_order()
            print(f"    Execution waves: {len(waves)}")

        except Exception as e:
            print(f"  ✗ Error: {e}")

        print()


if __name__ == "__main__":
    demo_basic_workflow()
    demo_example_templates()
