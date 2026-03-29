#!/usr/bin/env python3
"""
Example demonstrating the ResultIntegrator (P2-19).

This example shows how to use the ResultIntegrator to merge results
from multiple parallel tasks.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from omni.orchestration.integrator import ResultIntegrator, OrchestrationResult
from omni.orchestration.conflicts import ConflictResolver
from omni.task.models import TaskResult, TaskStatus


def main():
    """Run a simple example of result integration."""
    print("=== ResultIntegrator Example (P2-19) ===\n")
    
    # Create a result integrator
    integrator = ResultIntegrator()
    
    # Example 1: Single successful task
    print("Example 1: Single successful task")
    print("-" * 40)
    
    results = [
        TaskResult(
            task_id="task1",
            status=TaskStatus.COMPLETED,
            outputs={
                "files_modified": ["src/main.py"],
                "file_contents": {
                    "src/main.py": "print('Hello, World!')\n"
                },
            },
            metadata={"description": "Add print statement"},
            tokens_used=150,
            cost=0.0015,
        ),
    ]
    
    result = integrator.integrate(results, "Add hello world print statement")
    
    print(f"Success: {result.success}")
    print(f"Merged files: {list(result.merged_files.keys())}")
    print(f"Total cost: ${result.total_cost:.4f}")
    print(f"Commit message preview:\n{result.commit_message[:100]}...")
    print(f"Summary: {result.summary}")
    print()
    
    # Example 2: Multiple tasks with partial success
    print("Example 2: Multiple tasks with partial success")
    print("-" * 40)
    
    results = [
        TaskResult(
            task_id="task1",
            status=TaskStatus.COMPLETED,
            outputs={
                "files_modified": ["src/utils.py"],
                "file_contents": {
                    "src/utils.py": "def helper():\n    return 42\n"
                },
            },
            metadata={"description": "Add helper function", "task_type": "code_generation"},
            tokens_used=200,
            cost=0.0020,
        ),
        TaskResult(
            task_id="task2",
            status=TaskStatus.COMPLETED,
            outputs={
                "files_modified": ["tests/test_utils.py"],
                "file_contents": {
                    "tests/test_utils.py": "def test_helper():\n    assert helper() == 42\n"
                },
            },
            metadata={"description": "Add test for helper", "task_type": "testing"},
            tokens_used=180,
            cost=0.0018,
        ),
        TaskResult(
            task_id="task3",
            status=TaskStatus.FAILED,
            errors=["Timeout error"],
            metadata={"description": "Add documentation"},
            tokens_used=50,
            cost=0.0005,
        ),
    ]
    
    result = integrator.integrate(results, "Add utility function with tests")
    
    print(f"Success: {result.success}")
    print(f"Merged files: {list(result.merged_files.keys())}")
    print(f"Total cost: ${result.total_cost:.4f}")
    print(f"Tasks: {result.metadata['successful_tasks']} succeeded, {result.metadata['failed_tasks']} failed")
    print(f"Warnings: {result.warnings}")
    print(f"Summary: {result.summary}")
    print()
    
    # Example 3: Generate summary only
    print("Example 3: Generate summary only")
    print("-" * 40)
    
    summary = integrator.generate_summary(results)
    print(summary)
    print()
    
    print("=== Example Complete ===")


if __name__ == "__main__":
    main()