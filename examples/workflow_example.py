#!/usr/bin/env python3
"""
Example demonstrating P2-15 Workflow Orchestration.

This example shows how to create and execute a workflow with
conditional branching, loops, and error handling.
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Import from source directly
from omni.workflow import (
    Condition,
    NodeEdge,
    NodeType,
    OrchestratorConfig,
    WorkflowDefinition,
    WorkflowNode,
    WorkflowOrchestrator,
    get_template_registry,
)


def create_simple_workflow() -> WorkflowDefinition:
    """Create a simple workflow with conditional branching."""

    # Create nodes
    nodes = {}

    # Start node
    nodes["start"] = WorkflowNode(
        node_id="start",
        node_type=NodeType.TASK,
        label="Start Task",
        task_id="analyze_requirements",
        agent_id="thinker",
    )

    # Decision node (IF)
    nodes["decision"] = WorkflowNode(
        node_id="decision",
        node_type=NodeType.IF,
        label="Complexity Decision",
        condition=Condition(
            expression="variables['complexity'] > 0.7",
            description="Check if task is complex",
        ),
        true_branch=["complex_path"],
        false_branch=["simple_path"],
    )

    # Complex path
    nodes["complex_path"] = WorkflowNode(
        node_id="complex_path",
        node_type=NodeType.TASK,
        label="Complex Implementation",
        task_id="implement_complex",
        agent_id="coder",
    )

    # Simple path
    nodes["simple_path"] = WorkflowNode(
        node_id="simple_path",
        node_type=NodeType.TASK,
        label="Simple Implementation",
        task_id="implement_simple",
        agent_id="intern",
    )

    # Merge point
    nodes["merge"] = WorkflowNode(
        node_id="merge",
        node_type=NodeType.TASK,
        label="Merge Results",
        task_id="merge_results",
        agent_id="reader",
    )

    # Set up edges
    nodes["start"].edges = [NodeEdge(target_node_id="decision")]
    nodes["decision"].edges = []  # Branches handled by IF node
    nodes["complex_path"].edges = [NodeEdge(target_node_id="merge")]
    nodes["simple_path"].edges = [NodeEdge(target_node_id="merge")]

    # Create workflow definition
    workflow = WorkflowDefinition(
        workflow_id="example_workflow",
        name="Example Workflow with Conditional Branching",
        nodes=nodes,
        entry_node_id="start",
        exit_node_ids=["merge"],
        variables={"complexity": 0.8},  # Will take complex path
        description="Example workflow demonstrating conditional branching",
    )

    return workflow


def create_loop_workflow() -> WorkflowDefinition:
    """Create a workflow with a WHILE loop."""

    nodes = {}

    # Setup node
    nodes["setup"] = WorkflowNode(
        node_id="setup",
        node_type=NodeType.TASK,
        label="Setup Retry Counter",
        task_id="setup_retry",
    )

    # WHILE loop node
    nodes["retry_loop"] = WorkflowNode(
        node_id="retry_loop",
        node_type=NodeType.WHILE,
        label="Retry Until Success",
        loop_condition=Condition(
            expression="not result.success and iteration < 3",
            description="Retry while not successful and under 3 attempts",
        ),
        loop_body=["attempt_task"],
        max_iterations=3,
    )

    # Task to attempt
    nodes["attempt_task"] = WorkflowNode(
        node_id="attempt_task",
        node_type=NodeType.TASK,
        label="Attempt Task",
        task_id="attempt_with_retry",
    )

    # Success handler
    nodes["success"] = WorkflowNode(
        node_id="success",
        node_type=NodeType.TASK,
        label="Handle Success",
        task_id="handle_success",
    )

    # Failure handler
    nodes["failure"] = WorkflowNode(
        node_id="failure",
        node_type=NodeType.TASK,
        label="Handle Failure",
        task_id="handle_failure",
    )

    # Decision node after loop
    nodes["check_result"] = WorkflowNode(
        node_id="check_result",
        node_type=NodeType.IF,
        label="Check Result",
        condition=Condition(
            expression="node_results['attempt_task'].success",
            description="Check if last attempt succeeded",
        ),
        true_branch=["success"],
        false_branch=["failure"],
    )

    # Set up edges
    nodes["setup"].edges = [NodeEdge(target_node_id="retry_loop")]
    nodes["retry_loop"].edges = [NodeEdge(target_node_id="check_result")]

    workflow = WorkflowDefinition(
        workflow_id="loop_workflow",
        name="Workflow with Retry Loop",
        nodes=nodes,
        entry_node_id="setup",
        exit_node_ids=["success", "failure"],
        description="Example workflow with WHILE loop for retries",
    )

    return workflow


def main():
    """Run workflow examples."""
    print("=== P2-15 Workflow Orchestration Examples ===\n")

    # Create orchestrator
    config = OrchestratorConfig(
        default_max_concurrent_tasks=3,
        default_token_budget=50000,
        validate_before_execution=True,
    )
    orchestrator = WorkflowOrchestrator(config)

    # Example 1: Simple workflow with conditional branching
    print("1. Creating simple workflow with conditional branching...")
    simple_workflow = create_simple_workflow()

    # Validate workflow
    issues = simple_workflow.validate()
    if issues:
        print(f"  Validation issues: {issues}")
    else:
        print("  ✓ Workflow validation passed")

    # Execute workflow
    print("  Executing workflow...")
    execution = orchestrator.execute_workflow(simple_workflow)

    print(f"  Execution ID: {execution.execution_id}")
    print(f"  Status: {execution.status}")
    print(f"  Success: {execution.result.success if execution.result else 'N/A'}")
    print()

    # Example 2: Workflow with loop
    print("2. Creating workflow with WHILE loop...")
    loop_workflow = create_loop_workflow()

    issues = loop_workflow.validate()
    if issues:
        print(f"  Validation issues: {issues}")
    else:
        print("  ✓ Workflow validation passed")

    print("  Executing workflow...")
    execution = orchestrator.execute_workflow(loop_workflow)

    print(f"  Execution ID: {execution.execution_id}")
    print(f"  Status: {execution.status}")
    print(f"  Success: {execution.result.success if execution.result else 'N/A'}")
    print()

    # Example 3: Using built-in templates
    print("3. Using built-in workflow templates...")
    registry = get_template_registry()
    templates = registry.list()

    print(f"  Available templates: {len(templates)}")
    for template in templates[:3]:  # Show first 3
        print(f"    - {template.name} ({template.template_id})")

    # Try to execute a template
    if templates:
        template = templates[0]  # First template
        print(f"\n  Executing template: {template.name}...")

        try:
            execution = orchestrator.execute_template(
                template_id=template.template_id,
                parameters={"task_id": "example_task"},
            )
            print(f"  Template execution: {execution.status}")
        except Exception as e:
            print(f"  Template execution failed (expected for demo): {e}")

    print("\n=== Examples Complete ===")


if __name__ == "__main__":
    main()
