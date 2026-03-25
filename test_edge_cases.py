#!/usr/bin/env python3
"""
Test edge cases for Git auto-commit functionality.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from omni.git.repository import GitRepository


async def test_no_commits_yet():
    """Test git repo with no commits yet."""
    print("Testing git repo with no commits...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        os.chdir(tmpdir)
        
        # Initialize git repo but don't commit
        os.system("git init")
        os.system("git config user.email 'test@example.com'")
        os.system("git config user.name 'Test User'")
        
        # Create a test file but don't commit
        test_file = tmpdir / "test.py"
        test_file.write_text('def hello():\n    return "world"\n')
        
        try:
            # Create GitRepository
            git_repo = GitRepository(
                path=str(tmpdir),
                auto_commit=True,
            )
            
            # Try to get current commit - should handle gracefully
            commit = await git_repo.get_current_commit()
            print(f"Current commit: {commit}")
            
            # Try dirty commit
            result = await git_repo.commit_dirty_changes()
            print(f"Dirty commit result: {result}")
            
        except Exception as e:
            print(f"Error (expected): {e}")
            return False
    
    return True


async def test_auto_commit_disabled():
    """Test with auto_commit=False."""
    print("\nTesting with auto_commit=False...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        os.chdir(tmpdir)
        
        # Initialize git repo
        os.system("git init")
        os.system("git config user.email 'test@example.com'")
        os.system("git config user.name 'Test User'")
        
        # Create and commit initial file
        test_file = tmpdir / "test.py"
        test_file.write_text('def hello():\n    return "world"\n')
        os.system("git add .")
        os.system("git commit -m 'Initial commit'")
        
        # Modify file
        test_file.write_text('def hello():\n    return "modified"\n')
        
        # Create GitRepository with auto_commit=False
        git_repo = GitRepository(
            path=str(tmpdir),
            auto_commit=False,
        )
        
        # Try dirty commit - should return None
        result = await git_repo.commit_dirty_changes()
        print(f"Dirty commit result with auto_commit=False: {result}")
        
        # Check that _last_commit_before_edit is still set
        # Actually, looking at the code, it won't be set when auto_commit=False
        # because the entire method returns early
        
        # Check git status
        status = await git_repo.get_status()
        print(f"Git status (should show unstaged changes): {status}")
        
        return result is None


async def test_no_dirty_changes():
    """Test when there are no dirty changes."""
    print("\nTesting with no dirty changes...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        os.chdir(tmpdir)
        
        # Initialize git repo
        os.system("git init")
        os.system("git config user.email 'test@example.com'")
        os.system("git config user.name 'Test User'")
        
        # Create and commit initial file
        test_file = tmpdir / "test.py"
        test_file.write_text('def hello():\n    return "world"\n')
        os.system("git add .")
        os.system("git commit -m 'Initial commit'")
        
        # Create GitRepository
        git_repo = GitRepository(
            path=str(tmpdir),
            auto_commit=True,
        )
        
        # Get initial commit
        initial_commit = await git_repo.get_current_commit()
        print(f"Initial commit: {initial_commit[:8]}")
        
        # Try dirty commit with no changes
        result = await git_repo.commit_dirty_changes()
        print(f"Dirty commit result with no changes: {result}")
        
        # Check that _last_commit_before_edit is set
        # Actually, we can't access private attribute easily
        
        # Check current commit (should be same)
        current_commit = await git_repo.get_current_commit()
        print(f"Current commit after dirty_commit: {current_commit[:8]}")
        
        return result is None and initial_commit == current_commit


async def test_merge_conflict_handling():
    """Test handling of merge conflicts."""
    print("\nTesting merge conflict scenario...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        os.chdir(tmpdir)
        
        # Initialize git repo
        os.system("git init")
        os.system("git config user.email 'test@example.com'")
        os.system("git config user.name 'Test User'")
        
        # Create and commit initial file
        test_file = tmpdir / "test.py"
        test_file.write_text('def hello():\n    return "world"\n')
        os.system("git add .")
        os.system("git commit -m 'Initial commit'")
        
        # Create a branch and make conflicting change
        os.system("git checkout -b feature")
        test_file.write_text('def hello():\n    return "feature change"\n')
        os.system("git add .")
        os.system("git commit -m 'Feature change'")
        
        # Go back to main and make another change
        os.system("git checkout master")
        test_file.write_text('def hello():\n    return "main change"\n')
        os.system("git add .")
        os.system("git commit -m 'Main change'")
        
        # Create GitRepository
        git_repo = GitRepository(
            path=str(tmpdir),
            auto_commit=True,
        )
        
        # Try to merge (should create conflict)
        try:
            await git_repo.merge_branch("feature")
            print("Merge succeeded (unexpected)")
            return False
        except Exception as e:
            print(f"Merge failed as expected: {e}")
            
            # Check status
            status = await git_repo.get_status()
            print(f"Git status after conflict: {status}")
            
            return True


async def main():
    """Run all edge case tests."""
    print("Running edge case tests for Git auto-commit...")
    
    tests = [
        ("No commits yet", test_no_commits_yet),
        ("Auto-commit disabled", test_auto_commit_disabled),
        ("No dirty changes", test_no_dirty_changes),
        ("Merge conflict", test_merge_conflict_handling),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = await test_func()
            results.append((name, success))
            print(f"{name}: {'PASS' if success else 'FAIL'}\n")
        except Exception as e:
            print(f"{name}: ERROR - {e}\n")
            results.append((name, False))
    
    # Summary
    print("\n=== SUMMARY ===")
    all_passed = True
    for name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{name}: {status}")
        if not success:
            all_passed = False
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)