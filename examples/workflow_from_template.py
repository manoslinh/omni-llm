#!/usr/bin/env python3
"""
Example: Workflow Execution from Template

This example demonstrates how to:
1. Load and validate workflow templates
2. Execute workflows with custom variables
3. Handle conditional steps and dependencies
4. Monitor workflow execution in real-time
5. Handle errors and retries
"""

import asyncio
import tempfile
import sys
from pathlib import Path
from typing import Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from omni.orchestration import WorkflowEngine, WorkflowExecution, WorkflowResult
from omni.orchestration.workflow_models import WorkflowTemplate, WorkflowStep


def create_custom_template() -> str:
    """Create a custom workflow template for demonstration."""
    return """
name: "Feature Implementation Workflow"
description: "Complete workflow for implementing new features with testing and review"
version: "1.2.0"
author: "Omni-LLM Demo"
tags: ["feature", "implementation", "testing", "review"]

variables:
  feature_name:
    description: "Name of the feature to implement"
    required: true
    type: "string"
    pattern: "^[a-zA-Z0-9_-]+$"
    
  complexity:
    description: "Complexity level of the feature"
    type: "string"
    default: "medium"
    enum: ["simple", "medium", "complex"]
    
  include_tests:
    description: "Whether to include automated tests"
    type: "boolean"
    default: true
    
  include_docs:
    description: "Whether to include documentation"
    type: "boolean"
    default: true
    
  strict_review:
    description: "Enable strict code review"
    type: "boolean"
    default: false

steps:
  # Analysis phase
  - name: "requirements_analysis"
    task_type: "analysis"
    description: "Analyze requirements for {feature_name}"
    agent: "thinker"
    timeout: 300
    outputs:
      - name: "requirements_spec"
        description: "Requirements specification document"
        
  - name: "technical_design"
    task_type: "design"
    description: "Create technical design for {feature_name}"
    depends_on: ["requirements_analysis"]
    agent: "thinker"
    condition: "{complexity} != 'simple'"
    outputs:
      - name: "design_doc"
        description: "Technical design document"

  # Implementation phase
  - name: "implementation"
    task_type: "code_generation"
    description: "Implement {feature_name}"
    depends_on: ["technical_design", "requirements_analysis"]
    agent: "coder"
    timeout: 600
    retry: 2
    outputs:
      - name: "implementation_code"
        description: "Implementation code"

  # Testing phase (conditional)
  - name: "unit_tests"
    task_type: "testing"
    description: "Write unit tests for {feature_name}"
    depends_on: ["implementation"]
    agent: "intern"
    condition: "{include_tests}"
    timeout: 300
    
  - name: "integration_tests"
    task_type: "testing"
    description: "Write integration tests for {feature_name}"
    depends_on: ["implementation"]
    agent: "coder"
    condition: "{include_tests} and {complexity} != 'simple'"
    timeout: 400

  # Documentation phase (conditional)
  - name: "api_documentation"
    task_type: "documentation"
    description: "Write API documentation for {feature_name}"
    depends_on: ["implementation"]
    agent: "reader"
    condition: "{include_docs}"
    
  - name: "user_documentation"
    task_type: "documentation"
    description: "Write user documentation for {feature_name}"
    depends_on: ["implementation"]
    agent: "reader"
    condition: "{include_docs} and {complexity} != 'simple'"

  # Review phase
  - name: "code_review"
    task_type: "code_review"
    description: "Review implementation of {feature_name}"
    depends_on: ["implementation", "unit_tests", "integration_tests"]
    agent: "reader"
    timeout: 400
    
  - name: "security_review"
    task_type: "security"
    description: "Security review of {feature_name}"
    depends_on: ["implementation"]
    agent: "coder"
    condition: "{strict_review} or {complexity} == 'complex'"
    timeout: 300

  # Finalization
  - name: "final_integration"
    task_type: "integration"
    description: "Final integration and validation of {feature_name}"
    depends_on: ["code_review", "security_review", "api_documentation", "user_documentation"]
    agent: "coder"
    timeout: 500
    outputs:
      - name: "final_result"
        description: "Final integrated feature"
        
  - name: "deployment_prep"
    task_type: "configuration"
    description: "Prepare {feature_name} for deployment"
    depends_on: ["final_integration"]
    agent: "intern"
    timeout: 200
"""


async def demonstrate_template_loading():
    """Demonstrate loading and validating workflow templates."""
    print("\n1. Template Loading and Validation")
    print("=" * 60)

    # Create workflow engine
    engine = WorkflowEngine()

    # Create temporary template file
    template_content = create_custom_template()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(template_content)
        temp_path = f.name

    try:
        # Load template
        print("Loading template...")
        template = engine.load_template(temp_path)
        
        print(f"✅ Template loaded: {template.name} v{template.version}")
        print(f"   Description: {template.description}")
        print(f"   Author: {template.author}")
        print(f"   Tags: {', '.join(template.tags)}")
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
        print(f"   Variables defined:")
        for var_name, var_def in template.variables.items():
            required = "✓" if var_def.required else " "
            default = f" (default: {var_def.default})" if var_def.default else ""
            print(f"     [{required}] {var_name}: {var_def.description}{default}")

        return template

    finally:
        # Clean up temporary file
        import os
        os.unlink(temp_path)


async def demonstrate_execution_planning(template: WorkflowTemplate):
    """Demonstrate execution planning based on template."""
    print("\n\n2. Execution Planning")
    print("=" * 60)

    engine = WorkflowEngine()

    # Test with different variable sets
    test_cases = [
        {
            "name": "Simple Feature",
            "variables": {
                "feature_name": "user-profile-avatar",
                "complexity": "simple",
                "include_tests": True,
                "include_docs": False,
                "strict_review": False,
            }
        },
        {
            "name": "Complex Feature",
            "variables": {
                "feature_name": "payment-processing",
                "complexity": "complex",
                "include_tests": True,
                "include_docs": True,
                "strict_review": True,
            }
        },
        {
            "name": "Medium Feature (No Tests)",
            "variables": {
                "feature_name": "search-filter",
                "complexity": "medium",
                "include_tests": False,
                "include_docs": True,
                "strict_review": False,
            }
        }
    ]

    for test_case in test_cases:
        print(f"\n📊 Test case: {test_case['name']}")
        print("-" * 40)
        
        variables = test_case["variables"]
        print(f"   Variables: {variables}")

        # Create execution plan
        plan = engine.create_execution_plan(template, variables)
        
        # Show which steps will execute
        active_steps = [s for s in template.steps if plan.is_step_active(s.name)]
        skipped_steps = [s for s in template.steps if not plan.is_step_active(s.name)]
        
        print(f"   Active steps: {len(active_steps)}")
        print(f"   Skipped steps: {len(skipped_steps)}")
        
        if skipped_steps:
            print(f"   Skipped due to conditions: {[s.name for s in skipped_steps]}")

        # Show execution order
        execution_waves = plan.get_execution_order()
        print(f"   Execution waves: {len(execution_waves)}")
        
        for i, wave in enumerate(execution_waves, 1):
            print(f"     Wave {i}: {len(wave)} steps")
            for step_id in wave:
                step = template.get_step(step_id)
                if step:
                    print(f"       • {step.name} ({step.task_type})")


async def demonstrate_workflow_execution(template: WorkflowTemplate):
    """Demonstrate actual workflow execution."""
    print("\n\n3. Workflow Execution")
    print("=" * 60)

    engine = WorkflowEngine()
    
    # Set up execution variables
    variables = {
        "feature_name": "demo-authentication",
        "complexity": "medium",
        "include_tests": True,
        "include_docs": True,
        "strict_review": True,
    }
    
    print(f"Executing workflow with variables:")
    for key, value in variables.items():
        print(f"   {key}: {value}")

    # Create mock execution (since we don't have actual agents in demo)
    print("\n🏗️  Simulating workflow execution...")
    
    # In a real scenario, this would execute actual tasks
    # For demo purposes, we'll simulate the execution
    
    execution_states = [
        ("requirements_analysis", "✅ Completed", "Generated requirements spec"),
        ("technical_design", "✅ Completed", "Created technical design doc"),
        ("implementation", "✅ Completed", "Implemented authentication feature"),
        ("unit_tests", "✅ Completed", "Wrote 15 unit tests"),
        ("integration_tests", "✅ Completed", "Wrote 5 integration tests"),
        ("api_documentation", "✅ Completed", "Documented API endpoints"),
        ("user_documentation", "⏸️  Skipped", "Condition not met"),
        ("code_review", "✅ Completed", "Code review passed"),
        ("security_review", "✅ Completed", "Security review passed"),
        ("final_integration", "✅ Completed", "Integration successful"),
        ("deployment_prep", "✅ Completed", "Ready for deployment"),
    ]
    
    for step_name, status, details in execution_states:
        print(f"   {step_name:25} {status:15} {details}")
    
    # Simulate execution result
    print("\n📈 Execution completed successfully!")
    print("   Total steps: 11")
    print("   Completed: 10")
    print("   Skipped: 1")
    print("   Estimated cost: $0.0245")
    print("   Total time: 42m 18s")


async def demonstrate_error_handling():
    """Demonstrate error handling and retries in workflows."""
    print("\n\n4. Error Handling and Retries")
    print("=" * 60)

    error_template = """
name: "Error Handling Demo"
description: "Demonstrate error handling in workflows"
version: "1.0.0"

variables:
  should_fail:
    description: "Whether to simulate failure"
    type: "boolean"
    default: true

steps:
  - name: "step_1"
    task_type: "analysis"
    description: "First step (always succeeds)"
    agent: "intern"
    
  - name: "step_2_fail"
    task_type: "code_generation"
    description: "Step that might fail"
    depends_on: ["step_1"]
    agent: "coder"
    retry: 2
    on_error:
      action: "retry_then_skip"
      max_attempts: 3
      fallback_step: "step_2_fallback"
    condition: "{should_fail}"
    
  - name: "step_2_fallback"
    task_type: "code_generation"
    description: "Fallback step if step_2 fails"
    depends_on: ["step_1"]
    agent: "coder"
    
  - name: "step_3"
    task_type: "testing"
    description: "Final step"
    depends_on: ["step_2_fail", "step_2_fallback"]
    agent: "intern"
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(error_template)
        temp_path = f.name
    
    try:
        engine = WorkflowEngine()
        template = engine.load_template(temp_path)
        
        print("Template with error handling loaded")
        print(f"Steps: {len(template.steps)}")
        
        # Show error handling configuration
        fail_step = template.get_step("step_2_fail")
        if fail_step and fail_step.on_error:
            print(f"\nError handling for 'step_2_fail':")
            print(f"   Action: {fail_step.on_error.action}")
            print(f"   Max attempts: {fail_step.on_error.max_attempts}")
            print(f"   Fallback step: {fail_step.on_error.fallback_step}")
        
        # Simulate execution with failure
        print("\n🔧 Simulating execution with failure...")
        
        execution_scenario = [
            ("step_1", "started", None),
            ("step_1", "completed", "Step 1 successful"),
            ("step_2_fail", "started", None),
            ("step_2_fail", "failed", "Timeout after 300s"),
            ("step_2_fail", "retrying", "Attempt 2/3"),
            ("step_2_fail", "failed", "Model error: context too long"),
            ("step_2_fail", "retrying", "Attempt 3/3"),
            ("step_2_fail", "failed", "All retries exhausted"),
            ("step_2_fallback", "started", "Starting fallback step"),
            ("step_2_fallback", "completed", "Fallback completed successfully"),
            ("step_3", "started", None),
            ("step_3", "completed", "Workflow completed with fallback"),
        ]
        
        for step, status, message in execution_scenario:
            if message:
                print(f"   {step:20} {status:15} {message}")
            else:
                print(f"   {step:20} {status:15}")
        
        print("\n✅ Error handling demonstration complete!")
        print("   The workflow handled failures gracefully using:")
        print("   1. Automatic retries (3 attempts)")
        print("   2. Fallback step execution")
        print("   3. Continued execution after failure")
        
    finally:
        import os
        os.unlink(temp_path)


async def demonstrate_template_variations():
    """Demonstrate different ways to use workflow templates."""
    print("\n\n5. Template Variations and Customization")
    print("=" * 60)

    print("Workflow templates support several advanced features:")

    # 1. Template inheritance
    print("\n1. Template Inheritance")
    print("-" * 30)
    print("   Base templates can be extended:")
    print("   - Reuse common steps across workflows")
    print("   - Override specific steps or variables")
    print("   - Maintain consistency across similar workflows")

    # 2. Template composition
    print("\n2. Template Composition")
    print("-" * 30)
    print("   Combine multiple templates:")
    print("   - Include other templates as steps")
    print("   - Pass variables between templates")
    print("   - Create complex workflows from simple building blocks")

    # 3. Dynamic steps
    print("\n3. Dynamic Steps")
    print("-" * 30)
    print("   Steps can be created dynamically:")
    print("   - Loop over arrays to create multiple similar steps")
    print("   - Generate steps based on variable values")
    print("   - Adapt workflow structure at runtime")

    # 4. Conditional execution paths
    print("\n4. Conditional Execution Paths")
    print("-" * 30)
    print("   Different paths based on conditions:")
    print("   - IF/ELSE branching in workflows")
    print("   - Switch-like behavior with multiple conditions")
    print("   - Dynamic dependency resolution")

    # 5. Output chaining
    print("\n5. Output Chaining")
    print("-" * 30)
    print("   Pass outputs between steps:")
    print("   - Step outputs become available to dependent steps")
    print("   - Type checking and validation of outputs")
    print("   - Automatic input preparation for dependent steps")

    # Example of dynamic workflow
    print("\n🔧 Example: Dynamic workflow based on file list")
    print("-" * 40)
    
    dynamic_example = """
variables:
  files:
    description: "List of files to process"
    type: "array"
    items:
      type: "string"
    default: ["file1.py", "file2.py", "file3.py"]

steps:
  # Dynamic step generation
  - name: "process_file"
    task_type: "code_generation"
    description: "Process {file}"
    for_each: "{files}"
    loop_variable: "file"
    
  - name: "aggregate_results"
    task_type: "integration"
    description: "Aggregate all file processing results"
    depends_on: ["process_file"]  # Waits for all loop iterations
    """
    
    print("   This template would create:")
    print("   • 3 parallel 'process_file' steps (one for each file)")
    print("   • 1 'aggregate_results' step that waits for all files")
    print("   • Dynamic adaptation based on files array length")


async def demonstrate_real_world_example():
    """Demonstrate a real-world workflow template example."""
    print("\n\n6. Real-World Example: CI/CD Pipeline")
    print("=" * 60)

    ci_cd_template = """
name: "CI/CD Pipeline"
description: "Complete CI/CD pipeline for feature deployment"
version: "2.0.0"

variables:
  feature_branch:
    description: "Git branch containing the feature"
    required: true
    type: "string"
    
  environment:
    description: "Target deployment environment"
    type: "string"
    default: "staging"
    enum: ["development", "staging", "production"]
    
  run_tests:
    description: "Whether to run tests"
    type: "boolean"
    default: true
    
  notify_team:
    description: "Whether to notify team of deployment"
    type: "boolean"
    default: true

steps:
  # Pre-deployment checks
  - name: "code_quality"
    task_type: "analysis"
    description: "Run code quality checks on {feature_branch}"
    agent: "intern"
    
  - name: "security_scan"
    task_type: "security"
    description: "Security scan of {feature_branch}"
    depends_on: ["code_quality"]
    agent: "coder"
    
  - name: "test_suite"
    task_type: "testing"
    description: "Run test suite on {feature_branch}"
    depends_on: ["code_quality"]
    agent: "intern"
    condition: "{run_tests}"
    
  # Build and deployment
  - name: "build_artifact"
    task_type: "configuration"
    description: "Build deployment artifact"
    depends_on: ["security_scan", "test_suite"]
    agent: "coder"
    
  - name: "deploy"
    task_type: "deployment"
    description: "Deploy to {environment}"
    depends_on: ["build_artifact"]
    agent: "coder"
    
  # Post-deployment
  - name: "smoke_test"
    task_type: "testing"
    description: "Post-deployment smoke tests"
    depends_on: ["deploy"]
    agent: "intern"
    
  - name: "monitoring_setup"
    task_type: "monitoring"
    description: "Set up monitoring for deployment"
    depends_on: ["deploy"]
    agent: "coder"
    condition: "{environment} == 'production'"
    
  - name: "notify"
    task_type: "documentation"
    description: "Notify team of deployment"
    depends_on: ["smoke_test", "monitoring_setup"]
    agent: "intern"
    condition: "{notify_team}"
    
  - name: "cleanup"
    task_type: "cleanup"
    description: "Clean up temporary resources"
    depends_on: ["notify"]
    agent: "intern"
"""
    
    print("Real-world CI/CD pipeline template:")
    print("-" * 40)
    print("This template automates:")
    print("1. Code quality and security checks")
    print("2. Test execution (conditional)")
    print("3. Artifact building")
    print("4. Environment deployment")
    print("5. Post-deployment validation")
    print("6. Monitoring setup (production only)")
    print("7. Team notifications (conditional)")
    print("8. Resource cleanup")
    
    print("\nKey features demonstrated:")
    print("• Conditional steps based on variables")
    print("• Environment-specific logic")
    print("• Comprehensive error handling")
    print("• Resource management")
    print("• Team collaboration")


async def main():
    """Run all workflow template demonstrations."""
    print("🚀 Workflow from Template Demo")
    print("=" * 60)

    try:
        # 1. Template loading and validation
        template = await demonstrate_template_loading()

        # 2. Execution planning
        await demonstrate_execution_planning(template)

        # 3. Workflow execution
        await demonstrate_workflow_execution(template)

        # 4. Error handling
        await demonstrate_error_handling()

        # 5. Template variations
        await demonstrate_template_variations()

        # 6. Real-world example
        await demonstrate_real_world_example()

        print("\n" + "=" * 60)
        print("✅ All demonstrations completed successfully!")
        print("\nSummary of workflow template capabilities:")
        print("1. ✅ Template loading and validation")
        print("2. ✅ Variable substitution and conditional execution")
        print("3. ✅ Dependency management and parallel execution")
        print("4. ✅ Error handling with retries and fallbacks")
        print("5. ✅ Dynamic step generation and template composition")
        print("6. ✅ Real-world workflow automation")

        print("\nNext steps:")
        print("1. Create your own templates in examples/workflow_templates/")
        print("2. Use 'omni workflow run' to execute templates")
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
    asyncio.run(main())