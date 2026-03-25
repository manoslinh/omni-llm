#!/usr/bin/env python3
"""
Example usage of Omni-LLM verifiers.

This example shows how to use the LintVerifier and TestVerifier
in a verification pipeline.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from omni.core.verifiers import LintVerifier, TestVerifier
from omni.core.verifier import VerificationPipeline


async def verify_single_file():
    """Verify a single Python file."""
    print("=== Verifying a single file ===")
    
    # Create verifiers
    lint_verifier = LintVerifier(
        name="example_lint",
        severity_level="error",  # Only fail on errors, not warnings
    )
    
    test_verifier = TestVerifier(
        name="example_test",
        junit_report=False,
    )
    
    # Create pipeline
    pipeline = VerificationPipeline([lint_verifier, test_verifier])
    
    # Verify a file
    file_to_verify = Path(__file__).parent.parent / "src" / "omni" / "core" / "verifier.py"
    result = await pipeline.verify([str(file_to_verify)])
    
    print(f"File: {file_to_verify}")
    print(f"Passed: {result.passed}")
    print(f"Errors: {len(result.errors)}")
    print(f"Warnings: {len(result.warnings)}")
    
    if result.errors:
        print("\nFirst 3 errors:")
        for error in result.errors[:3]:
            print(f"  - {error}")
    
    await pipeline.close()
    print()


async def verify_project():
    """Verify an entire project directory."""
    print("=== Verifying project directory ===")
    
    # Create verifiers with different configurations
    lint_verifier = LintVerifier(
        name="project_lint",
        severity_level="all",  # Report all issues
        fix=False,  # Don't auto-fix
    )
    
    test_verifier = TestVerifier(
        name="project_test",
        test_dir="tests",
        timeout=60,
        junit_report=True,
    )
    
    pipeline = VerificationPipeline([lint_verifier, test_verifier])
    
    # Get all Python files in src directory
    src_dir = Path(__file__).parent.parent / "src"
    python_files = list(src_dir.rglob("*.py"))
    
    print(f"Found {len(python_files)} Python files in {src_dir}")
    
    # Verify all files
    result = await pipeline.verify([str(f) for f in python_files[:5]])  # Limit to 5 files for example
    
    print(f"Passed: {result.passed}")
    print(f"Total errors: {len(result.errors)}")
    print(f"Total warnings: {len(result.warnings)}")
    
    # Show verifier-specific results
    for verifier_name, details in result.details.items():
        if "findings" in details:
            print(f"\n{verifier_name}: {len(details['findings'])} findings")
        elif "junit_report" in details:
            report = details["junit_report"]
            print(f"\n{verifier_name}: {report.get('tests', 0)} tests, "
                  f"{report.get('failures', 0)} failures")
    
    await pipeline.close()
    print()


async def custom_verification_workflow():
    """Custom verification workflow with conditional execution."""
    print("=== Custom verification workflow ===")
    
    # Create verifiers
    lint_verifier = LintVerifier(name="workflow_lint")
    test_verifier = TestVerifier(name="workflow_test", junit_report=False)
    
    # Don't use pipeline - run verifiers individually for more control
    files_to_check = [__file__]  # Check this example file
    
    print("1. Running lint check...")
    lint_result = await lint_verifier.verify(files_to_check)
    
    if not lint_result.passed:
        print(f"   Lint failed with {len(lint_result.errors)} errors")
        print("   Skipping tests due to lint failures")
        # In a real workflow, you might want to fix lint issues first
    else:
        print("   Lint passed!")
        print("\n2. Running tests...")
        test_result = await test_verifier.verify([])  # Run all tests
        
        if test_result.passed:
            print("   Tests passed!")
        else:
            print(f"   Tests failed: {test_result.details.get('exit_code', 'N/A')}")
    
    await lint_verifier.close()
    await test_verifier.close()
    print()


async def main():
    """Run all examples."""
    print("Omni-LLM Verifier Examples")
    print("=" * 60)
    
    await verify_single_file()
    await verify_project()
    await custom_verification_workflow()
    
    print("=" * 60)
    print("Examples completed!")


if __name__ == "__main__":
    # Note: These examples assume you're running from the virtual environment
    # where ruff and pytest are available
    asyncio.run(main())