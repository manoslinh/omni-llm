#!/usr/bin/env python3
"""
Demo showing how the Workflow Template Engine integrates with the Coordination System.
"""

import os
import tempfile

from omni.orchestration import WorkflowEngine


def demo_integration_with_coordination():
    """Demo how workflow templates integrate with the coordination system."""
    print("=== Workflow Template + Coordination Integration Demo ===\n")

    # Create a simple workflow template
    yaml_content = """
name: "Integration Demo Workflow"
description: "Demo showing workflow template integration with coordination"
version: "1.0.0"

variables:
  component:
    description: "Component to implement"
    required: true
    type: "string"
  add_docs:
    description: "Whether to add documentation"
    default: true
    type: "boolean"

steps:
  - name: "design"
    task_type: "analysis"
    description: "Design architecture for {component}"

  - name: "implement"
    task_type: "code_generation"
    description: "Implement {component}"
    depends_on: ["design"]

  - name: "test"
    task_type: "testing"
    description: "Test {component}"
    depends_on: ["implement"]

  - name: "document"
    task_type: "documentation"
    description: "Document {component}"
    depends_on: ["implement"]
    condition: "{add_docs}"

  - name: "review"
    task_type: "code_review"
    description: "Review {component} implementation"
    depends_on: ["test", "document"]
"""

    # Write to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_content)
        temp_path = f.name

    try:
        # 1. Load workflow template
        print("1. Loading workflow template...")
        workflow_engine = WorkflowEngine()
        template = workflow_engine.load_template(temp_path)
        print(f"   ✓ Loaded: {template.name}")

        # 2. Execute workflow (creates TaskGraph)
        print("\n2. Creating TaskGraph from workflow...")
        variables = {
            "component": "authentication module",
            "add_docs": True
        }

        # Note: In a real integration, we would pass the coordination engine
        # to WorkflowEngine and it would use it for execution.
        # For now, we'll manually show the integration points.
        result = workflow_engine.execute(template, variables)
        print(f"   ✓ Created TaskGraph with {result.metadata.get('task_count', 0)} tasks")
        print(f"   ✓ TaskGraph name: workflow-{template.name}")

        # 3. Show how the TaskGraph would be processed by CoordinationEngine
        print("\n3. How CoordinationEngine would process the TaskGraph:")
        print("   a) WorkflowEngine creates TaskGraph from template")
        print("   b) TaskGraph passed to CoordinationEngine")
        print("   c) CoordinationEngine uses WorkflowOrchestrator to create WorkflowPlan")
        print("   d) WorkflowPlan executed with agent assignments")
        print("   e) Results integrated via ResultIntegrator")

        # 4. Show execution waves
        print("\n4. Execution waves (parallel execution groups):")
        waves = template.get_execution_order()
        for i, wave in enumerate(waves, 1):
            parallel = " (parallel)" if len(wave) > 1 else ""
            print(f"   Wave {i}: {', '.join(wave)}{parallel}")

        # 5. Demo conditional execution
        print("\n5. Conditional execution demo:")
        print("   With add_docs=True:")
        variables_with_docs = {"component": "module", "add_docs": True}
        result_with = workflow_engine.execute(template, variables_with_docs)
        print(f"     - Tasks created: {result_with.metadata.get('task_count', 0)}")

        print("   With add_docs=False:")
        variables_without = {"component": "module", "add_docs": False}
        result_without = workflow_engine.execute(template, variables_without)
        print(f"     - Tasks created: {result_without.metadata.get('task_count', 0)}")
        print("     - 'document' step skipped due to condition")

        # 6. Integration with P2-19 ResultIntegrator
        print("\n6. Integration with P2-19 ResultIntegrator:")
        print("   ✓ WorkflowEngine returns OrchestrationResult")
        print("   ✓ OrchestrationResult includes:")
        print(f"     - success: {result.success}")
        print(f"     - summary: {result.summary}")
        print("     - metadata: workflow_name, task_count, etc.")
        print("   ✓ ResultIntegrator can process multiple workflow results")

    finally:
        os.unlink(temp_path)

    print("\n=== Integration Demo Complete ===")
    print("\nKey Integration Points:")
    print("1. WorkflowEngine.load_template() → WorkflowTemplate")
    print("2. WorkflowEngine.execute() → TaskGraph → OrchestrationResult")
    print("3. TaskGraph → CoordinationEngine → WorkflowPlan")
    print("4. WorkflowPlan execution → Agent assignments")
    print("5. Results → ResultIntegrator → Final output")


if __name__ == "__main__":
    demo_integration_with_coordination()
