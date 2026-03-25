#!/usr/bin/env python3
"""
Test EditLoop Git integration.
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
from omni.models.provider import ModelProvider, Message, MessageRole, CompletionResult, TokenUsage


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
    ) -> "ModelCapabilities":
        """Mock capabilities."""
        from omni.models.provider import ModelCapabilities
        
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


async def test_git_integration():
    """Test EditLoop Git integration."""
    print("Testing EditLoop Git integration...")
    
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
        print("Running edit cycle...")
        result = await edit_loop.run_cycle(
            user_input="Update hello function to return 'Hello, world!'",
            model="openai/gpt-3.5-turbo",
        )
        
        print(f"Success: {result.success}")
        print(f"Cost: ${result.cost:.4f}")
        print(f"Reflections: {result.reflections}")
        
        # Check git status
        print("\nGit status:")
        status = await git_repo.get_status()
        for key, files in status.items():
            if files:
                print(f"  {key}: {files}")
        
        # Check current branch
        branch = await git_repo.get_current_branch()
        print(f"Current branch: {branch}")
        
        # Check commit history
        print("\nRecent commits:")
        os.system("git log --oneline -3")
        
        # Clean up
        await edit_loop.close()
        
        return result.success


if __name__ == "__main__":
    success = asyncio.run(test_git_integration())
    sys.exit(0 if success else 1)