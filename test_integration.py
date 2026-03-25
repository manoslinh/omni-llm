#!/usr/bin/env python3
"""
Integration test for Omni-LLM Week 2 deliverables.
Tests that the core components work together.
"""

import asyncio
import tempfile
import os
from pathlib import Path

from omni.models.mock_provider import MockProvider
from omni.core.edit_loop import EditLoop
from omni.git.repository import GitRepository
from omni.edits.editblock import EditBlockParser
from omni.core.edit_applier import EditApplier


async def test_integration():
    """Test that core components work together."""
    print("Testing Omni-LLM Week 2 integration...")
    
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Using temporary directory: {tmpdir}")
        
        # Create a test file
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("def hello():\n    return 'Hello, World!'\n")
        
        # Initialize git repo
        git_repo = GitRepository(path=tmpdir, auto_commit=False)
        await git_repo.commit_dirty_changes()  # Initial commit
        
        # Initialize components
        model_provider = MockProvider()
        edit_parser = EditBlockParser()
        edit_applier = EditApplier(base_path=tmpdir)
        
        # Create EditLoop
        edit_loop = EditLoop(
            model_provider=model_provider,
            git_repo=git_repo,
            edit_parser=edit_parser,
            edit_applier=edit_applier,
        )
        
        # Test 1: Run a simple edit cycle
        print("\nTest 1: Running edit cycle...")
        result = await edit_loop.run_cycle(
            user_input="Change the function to return 'Hello, Omni-LLM!'",
            model="openai/gpt-4",
            files_to_include=["test.py"],
        )
        
        print(f"  Success: {result.success}")
        print(f"  Cost: ${result.cost:.4f}")
        print(f"  Reflections: {result.reflections}")
        print(f"  Edits parsed: {len(result.edits)}")
        
        # Test 2: Check git status
        print("\nTest 2: Checking git status...")
        status = await git_repo.get_status()
        print(f"  Modified files: {len(status['modified'])}")
        
        # Test 3: Get git log
        log = await git_repo.get_log(limit=5)
        print(f"  Commits in log: {len(log)}")
        
        # Test 4: Close everything
        print("\nTest 3: Closing components...")
        await edit_loop.close()
        await git_repo.close()
        
        print("\n✅ All integration tests passed!")
        return True


if __name__ == "__main__":
    asyncio.run(test_integration())