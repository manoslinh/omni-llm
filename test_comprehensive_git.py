#!/usr/bin/env python3
"""
Comprehensive test of EditLoop Git integration.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from omni.core.edit_loop import EditLoop
from omni.git.repository import GitRepository
from omni.models.provider import ModelProvider, Message, MessageRole, CompletionResult, TokenUsage, ModelCapabilities


class MockModelProvider(ModelProvider):
    """Mock model provider for testing."""
    
    async def complete(
        self,
        messages: list[Message],
        model: str = "openai/gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> CompletionResult:
        """Return a mock completion with edit blocks."""
        # Create a simple edit block with file path
        content = """test.py
SEARCH
```
def hello():
    return "world"
```
REPLACE
```
def hello():
    return "Hello, world!"
```"""
        
        return CompletionResult(
            content=content,
            usage=TokenUsage(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            model=model,
            finish_reason="stop",
        )
    
    def estimate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: str,
    ) -> float:
        """Mock cost estimation."""
        return 0.001
    
    def count_tokens(
        self,
        text: str,
        model: str = "openai/gpt-3.5-turbo",
    ) -> int:
        """Mock token counting."""
        return len(text.split())
    
    def get_capabilities(
        self,
        model: str,
    ) -> ModelCapabilities:
        """Mock capabilities."""
        return ModelCapabilities(
            max_tokens=4096,
            supports_tools=False,
            supports_vision=False,
            supports_json=False,
            supports_function_calling=False,
        )
    
    def list_models(self) -> List[str]:
        """Mock model list."""
        return ["openai/gpt-3.5-turbo", "openai/gpt-4"]
    
    async def close(self):
        """Mock close."""
        pass


async def test_comprehensive():
    """Comprehensive test of EditLoop Git integration."""
    print("=== Comprehensive EditLoop Git Integration Test ===\n")
    
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
        
        print("1. Testing basic Git integration...")
        
        # Create GitRepository
        git_repo = GitRepository(
            path=str(tmpdir),
            auto_commit=True,
            ai_author_name="AI Assistant",
            ai_author_email="ai@omni-llm.dev",
            user_author_name="Test User",
            user_author_email="test@example.com",
        )
        
        # Create EditLoop with git repo
        model_provider = MockModelProvider()
        edit_loop = EditLoop(
            model_provider=model_provider,
            git_repo=git_repo,
        )
        
        # Run an edit cycle
        result = await edit_loop.run_cycle(
            user_input="Update hello function",
            model="openai/gpt-3.5-turbo",
        )
        
        print(f"   Success: {result.success}")
        print(f"   Cost: ${result.cost:.4f}")
        
        # Check commit was made with AI attribution
        print("\n2. Checking AI attribution...")
        os.system("git log -1 --pretty=full")
        
        # Test undo functionality
        print("\n3. Testing undo functionality...")
        can_undo = await git_repo.undo_last_edit()
        print(f"   Can undo: {can_undo}")
        if can_undo:
            print(f"   File after undo: {test_file.read_text().strip()}")
        
        # Run another edit to test dirty commit
        print("\n4. Testing dirty commit...")
        
        # Make a manual change without committing
        test_file.write_text('def hello():\n    return "manual change"\n')
        
        # Run edit cycle - should commit dirty changes first
        result2 = await edit_loop.run_cycle(
            user_input="Update hello function again",
            model="openai/gpt-3.5-turbo",
        )
        
        print(f"   Success: {result2.success}")
        
        # Check commit history
        print("\n5. Checking commit history...")
        os.system("git log --oneline --graph --all")
        
        # Test feature branch creation
        print("\n6. Testing feature branch creation...")
        
        # Create a new file for feature branch test
        test_file2 = tmpdir / "test2.py"
        test_file2.write_text('def goodbye():\n    return "bye"\n')
        os.system("git add .")
        os.system("git commit -q -m 'Add test2.py'")
        
        # Run with feature branch
        result3 = await edit_loop.run_cycle(
            user_input="Update goodbye function",
            model="openai/gpt-3.5-turbo",
            create_feature_branch=True,
            branch_name="feature/test-branch",
        )
        
        print(f"   Success: {result3.success}")
        
        # Check branches
        branches = await git_repo.list_branches()
        print(f"   Branches: {[b.name for b in branches]}")
        
        # Check we're back on original branch
        current_branch = await git_repo.get_current_branch()
        print(f"   Current branch: {current_branch}")
        
        # Clean up
        await edit_loop.close()
        
        print("\n=== Test Complete ===")
        
        return all([result.success, result2.success, result3.success])


if __name__ == "__main__":
    success = asyncio.run(test_comprehensive())
    sys.exit(0 if success else 1)