#!/usr/bin/env python3
"""
Test the complete edit cycle workflow with Git integration.
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


class FlexibleMockModelProvider(ModelProvider):
    """Mock model provider that can return different edit blocks."""
    
    def __init__(self):
        self.call_count = 0
    
    async def complete(
        self,
        messages: list[Message],
        model: str = "openai/gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> CompletionResult:
        """Return a mock completion with edit blocks."""
        self.call_count += 1
        
        # For first call, return edit for original text
        # For reflections, return different edit
        if self.call_count == 1:
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
        else:
            # For reflections, fix any issues
            content = """test.py
SEARCH
```
def hello():
    return "Hello, world!"
```
REPLACE
```
def hello():
    return "Hello, World!"
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


async def test_edit_cycle_workflow():
    """Test the complete edit cycle workflow."""
    print("=== Testing Edit Cycle Workflow with Git ===\n")
    
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
        
        print("Initial state:")
        print(f"  File content: {test_file.read_text().strip()}")
        print(f"  Git commits: ", end="")
        os.system("git log --oneline | head -1")
        
        # Create GitRepository and EditLoop
        git_repo = GitRepository(
            path=str(tmpdir),
            auto_commit=True,
        )
        
        model_provider = FlexibleMockModelProvider()
        edit_loop = EditLoop(
            model_provider=model_provider,
            git_repo=git_repo,
            max_reflections=2,
        )
        
        print("\nRunning edit cycle...")
        result = await edit_loop.run_cycle(
            user_input="Capitalize the greeting",
            model="openai/gpt-3.5-turbo",
        )
        
        print(f"\nResults:")
        print(f"  Success: {result.success}")
        print(f"  Cost: ${result.cost:.4f}")
        print(f"  Reflections: {result.reflections}")
        print(f"  Edits applied: {len(result.edits)}")
        
        print(f"\nFinal file content: {test_file.read_text().strip()}")
        
        print("\nGit history:")
        os.system("git log --oneline --graph")
        
        print("\nLatest commit details:")
        os.system("git show --stat HEAD")
        
        # Test that we can undo
        print("\nTesting undo...")
        can_undo = await git_repo.undo_last_edit()
        print(f"  Can undo: {can_undo}")
        if can_undo:
            print(f"  File after undo: {test_file.read_text().strip()}")
            
            # Check git history after undo
            print("  Git history after undo:")
            os.system("git log --oneline --graph")
        
        # Clean up
        await edit_loop.close()
        
        print("\n=== Workflow Test Complete ===")
        
        return result.success


if __name__ == "__main__":
    success = asyncio.run(test_edit_cycle_workflow())
    sys.exit(0 if success else 1)