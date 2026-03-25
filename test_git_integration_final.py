#!/usr/bin/env python3
"""
Final test of EditLoop Git integration.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from omni.core.edit_loop import EditLoop
from omni.git.repository import GitRepository
from omni.models.provider import ModelProvider, Message, MessageRole, CompletionResult, TokenUsage


async def test_git_integration():
    """Test EditLoop Git integration end-to-end."""
    print("=== Testing EditLoop Git Integration ===\n")
    
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Initialize git repo
        os.chdir(tmpdir)
        os.system("git init -q")
        os.system("git config user.email 'test@example.com'")
        os.system("git config user.name 'Test User'")
        
        # Create a test file
        test_file = tmpdir / "test.py"
        test_file.write_text('def hello():\n    return "world"\n')
        
        # Add and commit initial file
        os.system("git add .")
        os.system("git commit -q -m 'Initial commit'")
        
        print(f"Created test repo at: {tmpdir}")
        print(f"Initial commit: {os.popen('git log --oneline -1').read().strip()}")
        
        # Create GitRepository with AI attribution
        git_repo = GitRepository(
            path=str(tmpdir),
            auto_commit=True,
            ai_author_name="AI Assistant",
            ai_author_email="ai@omni-llm.dev",
            user_author_name="Test User",
            user_author_email="test@example.com",
        )
        
        # Create EditLoop with git repo
        model_provider = MockProvider()
        edit_loop = EditLoop(
            model_provider=model_provider,
            git_repo=git_repo,
        )
        
        print("\n1. Testing basic edit cycle with Git...")
        result = await edit_loop.run_cycle(
            user_input="Update hello function to return 'Hello, world!'",
            model="openai/gpt-3.5-turbo",
        )
        
        print(f"   Success: {result.success}")
        print(f"   Cost: ${result.cost:.4f}")
        print(f"   Reflections: {result.reflections}")
        
        # Check git status
        status = await git_repo.get_status()
        print(f"   Git status: {len(status.get('staged', []))} staged, "
              f"{len(status.get('unstaged', []))} unstaged, "
              f"{len(status.get('untracked', []))} untracked")
        
        # Check commit history
        commits = await git_repo.get_log(limit=3)
        print(f"   Recent commits: {len(commits)}")
        for commit in commits[:2]:
            print(f"     - {commit.hash[:8]}: {commit.message[:50]}...")
            if "AI Assistant" in commit.author:
                print(f"       (AI-authored)")
        
        print("\n2. Testing feature branch creation...")
        original_branch = await git_repo.get_current_branch()
        print(f"   Original branch: {original_branch}")
        
        # Create a feature branch
        feature_branch = await edit_loop._create_feature_branch(
            branch_name="feature/test-branch",
            user_input="Test feature",
        )
        
        if feature_branch:
            print(f"   Created feature branch from: {feature_branch}")
            current_branch = await git_repo.get_current_branch()
            print(f"   Current branch: {current_branch}")
            
            # List all branches
            branches = await git_repo.list_branches()
            print(f"   All branches: {[b.name for b in branches]}")
        else:
            print("   Failed to create feature branch")
        
        print("\n3. Testing undo functionality...")
        # Save current state
        current_commit = await git_repo.get_current_commit()
        print(f"   Current commit: {current_commit[:8]}")
        
        # Try to undo (should work if we have a last commit saved)
        can_undo = await git_repo.undo_last_edit()
        print(f"   Can undo: {can_undo}")
        
        if can_undo:
            new_commit = await git_repo.get_current_commit()
            print(f"   After undo commit: {new_commit[:8]}")
        
        # Clean up
        await edit_loop.close()
        
        print("\n=== Test Complete ===")
        return result.success


if __name__ == "__main__":
    success = asyncio.run(test_git_integration())
    sys.exit(0 if success else 1)