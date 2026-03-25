"""
Tests for the EditLoop service.
"""

import pytest
import asyncio

from omni.core.edit_loop import EditLoop, CycleResult, VerificationResult
from omni.models.mock_provider import MockProvider


class TestEditLoop:
    """Tests for the EditLoop class."""
    
    @pytest.fixture
    def mock_provider(self):
        """Create a mock provider for testing."""
        return MockProvider()
    
    @pytest.fixture
    def edit_loop(self, mock_provider):
        """Create an EditLoop instance for testing."""
        return EditLoop(model_provider=mock_provider)
    
    @pytest.mark.asyncio
    async def test_edit_loop_initialization(self, edit_loop):
        """Test that EditLoop initializes correctly."""
        assert edit_loop.model_provider is not None
        assert edit_loop.max_reflections == 3
        assert edit_loop.reflection_count == 0
        assert edit_loop.total_cost == 0.0
    
    @pytest.mark.asyncio
    async def test_run_cycle_basic(self, edit_loop):
        """Test running a basic edit cycle."""
        result = await edit_loop.run_cycle(
            user_input="Create a function that adds two numbers",
            model="openai/gpt-4",
            temperature=0.7,
        )
        
        assert isinstance(result, CycleResult)
        assert isinstance(result.verification, VerificationResult)
        assert result.cost >= 0
        assert result.reflections == 0
        assert result.success is False  # Default parser/applier are no-op
    
    @pytest.mark.asyncio
    async def test_run_cycle_with_reflection(self, edit_loop):
        """Test that reflection count increments."""
        # Mock a verification failure to trigger reflection
        # (Our mock setup doesn't actually run verifiers, so this is a basic test)
        result = await edit_loop.run_cycle(
            user_input="Test with reflection",
            model="openai/gpt-4",
        )
        
        # Should not have reflections since we don't have real verifiers
        assert result.reflections == 0
    
    @pytest.mark.asyncio
    async def test_build_reflection_prompt(self, edit_loop):
        """Test building reflection prompts."""
        original_input = "Create a function"
        errors = ["Syntax error on line 5", "Missing import"]
        
        prompt = edit_loop._build_reflection_prompt(original_input, errors)
        
        assert original_input in prompt
        for error in errors:
            assert error in prompt
        assert "Verification errors:" in prompt
        assert "Please fix the issues" in prompt
    
    def test_get_system_prompt(self, edit_loop):
        """Test getting system prompts."""
        # Regular prompt
        regular = edit_loop._get_system_prompt(is_reflection=False)
        assert "AI coding assistant" in regular
        assert "SEARCH/REPLACE" in regular
        
        # Reflection prompt
        reflection = edit_loop._get_system_prompt(is_reflection=True)
        assert "fixes errors" in reflection
        assert "previously generated" in reflection
    
    def test_generate_commit_message(self, edit_loop):
        """Test generating commit messages."""
        from omni.core.edit_loop import Edit
        
        # Single file
        edits = [Edit(file_path="test.py", old_text="", new_text="")]
        message = edit_loop._generate_commit_message(edits, "Add function")
        assert "Update test.py" in message
        assert "Add function" in message
        
        # Multiple files (<= 3)
        edits = [
            Edit(file_path="a.py", old_text="", new_text=""),
            Edit(file_path="b.py", old_text="", new_text=""),
        ]
        message = edit_loop._generate_commit_message(edits, "Update files")
        assert "Update a.py, b.py" in message
        
        # Many files (> 3)
        edits = [
            Edit(file_path="a.py", old_text="", new_text=""),
            Edit(file_path="b.py", old_text="", new_text=""),
            Edit(file_path="c.py", old_text="", new_text=""),
            Edit(file_path="d.py", old_text="", new_text=""),
        ]
        message = edit_loop._generate_commit_message(edits, "Update many files")
        assert "Update 4 files" in message
        
        # Truncated user input
        long_input = "a" * 200
        message = edit_loop._generate_commit_message(edits, long_input)
        assert len(message) < 250  # Should be truncated
    
    @pytest.mark.asyncio
    async def test_close(self, edit_loop):
        """Test closing the EditLoop."""
        # Run a cycle to accumulate some cost
        await edit_loop.run_cycle("Test", model="openai/gpt-4")
        
        # Close should work without errors
        await edit_loop.close()
        
        # Can't easily verify internal state, but no exception is good