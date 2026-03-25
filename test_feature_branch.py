#!/usr/bin/env python3
"""
Test EditLoop feature branch functionality.
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


async def test_feature_branch():
    """Test EditLoop feature branch creation."""
    print("Testing EditLoop feature branch functionality...")
    
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Initialize git repo
        os.chdir(tmpdir)
        os.system("git init")
        os.system("git config user.email 'test@example.com'")
        os.system("git config user.name 'Test User'")
        
        # Create a test file
        test_file = tmpdir / "test.py"
        test_file.write_text('def hello():\n    return "world"\n')
        
        # Add and commit initial file
        os.system("git add .")
        os.system("git commit -m 'Initial commit'")
        
        # Check initial state
        print(f"\nInitial file content:\n{test_file.read_text()}")
        
        # Create GitRepository
        git_repo = GitRepository(
            path=str(tmpdir),
            auto_commit=True,
            ai_author_name="AI Assistant",
            ai_author_email="ai@omni-llm.dev",
            user_author_name="Test User",
            user_author_email="test@example.com",
        )
        
        # Check initial branch
        initial_branch = await git_repo.get_current_branch()
        print(f"Initial branch: {initial_branch}")
        
        # Create EditLoop with git repo
        model_provider = MockModelProvider()
        edit_loop = EditLoop(
            model_provider=model_provider,
            git_repo=git_repo,
        )
        
        # Run an edit cycle with feature branch
        print("\nRunning edit cycle with feature branch...")
        result = await edit_loop.run_cycle(
            user_input="Update hello function to return 'Hello, world!'",
            model="openai/gpt-3.5-turbo",
            create_feature_branch=True,
        )
        
        print(f"Success: {result.success}")
        
        # Check final branch
        final_branch = await git_repo.get_current_branch()
        print(f"Final branch: {final_branch}")
        
        # Check file content
        print(f"\nFile content after edit:\n{test_file.read_text()}")
        
        # List all branches
        print("\nAll branches:")
        branches = await git_repo.list_branches()
        for branch in branches:
            print(f"  {'* ' if branch.is_current else '  '}{branch.name}")
        
        # Check commit history
        print("\nCommit history:")
        os.system("git log --oneline --graph --all")
        
        # Clean up
        await edit_loop.close()
        
        return result.success


if __name__ == "__main__":
    success = asyncio.run(test_feature_branch())
    sys.exit(0 if success else 1)