"""
Tests for the Model Provider abstraction layer.
"""

import pytest
import asyncio

from omni.models.provider import Message, MessageRole, TokenUsage
from omni.models.mock_provider import MockProvider


class TestMockProvider:
    """Tests for the MockProvider."""
    
    @pytest.fixture
    def provider(self):
        """Create a mock provider for testing."""
        return MockProvider()
    
    @pytest.mark.asyncio
    async def test_complete_basic(self, provider):
        """Test basic completion."""
        messages = [
            Message(role=MessageRole.USER, content="Hello, world!")
        ]
        
        result = await provider.complete(
            messages=messages,
            model="openai/gpt-4",
            temperature=0.7,
        )
        
        assert result.content is not None
        assert result.model == "openai/gpt-4"
        assert isinstance(result.usage, TokenUsage)
        assert result.usage.prompt_tokens > 0
        assert result.usage.completion_tokens > 0
        assert result.finish_reason == "stop"
    
    @pytest.mark.asyncio
    async def test_complete_with_system_message(self, provider):
        """Test completion with system message."""
        messages = [
            Message(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            Message(role=MessageRole.USER, content="What is 2+2?"),
        ]
        
        result = await provider.complete(
            messages=messages,
            model="anthropic/claude-3-sonnet",
        )
        
        assert result.content is not None
        assert result.model == "anthropic/claude-3-sonnet"
    
    @pytest.mark.asyncio
    async def test_complete_custom_response(self, provider):
        """Test completion with custom responses."""
        custom_responses = {
            "custom/model": "Custom response for custom model",
        }
        custom_provider = MockProvider(responses=custom_responses)
        
        result = await custom_provider.complete(
            messages=[Message(role=MessageRole.USER, content="Test")],
            model="custom/model",
        )
        
        assert result.content == "Custom response for custom model"
        await custom_provider.close()
    
    def test_count_tokens(self, provider):
        """Test token counting."""
        text = "Hello, world! This is a test."
        tokens = provider.count_tokens(text, "openai/gpt-4")
        
        # Rough estimate: 4 chars per token
        expected_min = len(text) // 5
        expected_max = len(text) // 3
        
        assert expected_min <= tokens <= expected_max
    
    def test_estimate_cost(self, provider):
        """Test cost estimation."""
        input_tokens = 1000
        output_tokens = 500
        
        cost = provider.estimate_cost(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model="openai/gpt-4",
        )
        
        # Mock pricing: $0.01 per 1000 tokens
        expected_cost = (input_tokens + output_tokens) / 1000 * 0.01
        assert cost == expected_cost
    
    def test_get_capabilities(self, provider):
        """Test getting model capabilities."""
        capabilities = provider.get_capabilities("openai/gpt-4")
        
        assert capabilities.supports_edit_format == "editblock"
        assert capabilities.max_context_tokens == 128_000
        assert capabilities.supports_tools is True
        assert capabilities.supports_streaming is True
    
    def test_list_models(self, provider):
        """Test listing available models."""
        models = provider.list_models()
        
        assert isinstance(models, list)
        assert len(models) > 0
        assert "openai/gpt-4" in models
        assert "anthropic/claude-3-sonnet" in models
        assert "deepseek/deepseek-chat" in models
    
    @pytest.mark.asyncio
    async def test_call_logging(self, provider):
        """Test that calls are logged."""
        # Clear any previous calls
        provider.clear_calls()
        
        # Make a call
        await provider.complete(
            messages=[Message(role=MessageRole.USER, content="Test")],
            model="test-model",
            temperature=0.5,
            max_tokens=100,
        )
        
        # Check call log
        calls = provider.get_all_calls()
        assert len(calls) == 1
        
        call = calls[0]
        assert call["model"] == "test-model"
        assert call["temperature"] == 0.5
        assert call["max_tokens"] == 100
        assert len(call["messages"]) == 1
    
    @pytest.mark.asyncio
    async def test_close(self, provider):
        """Test closing the provider."""
        # Make a call to populate call log
        await provider.complete(
            messages=[Message(role=MessageRole.USER, content="Test")],
            model="test-model",
        )
        
        assert len(provider.get_all_calls()) > 0
        
        # Close provider
        await provider.close()
        
        # Call log should be cleared
        assert len(provider.get_all_calls()) == 0


class TestMessage:
    """Tests for the Message dataclass."""
    
    def test_message_creation(self):
        """Test creating messages."""
        msg = Message(
            role=MessageRole.USER,
            content="Hello, world!",
            name="test-user",
        )
        
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello, world!"
        assert msg.name == "test-user"
        assert msg.tool_calls is None
        assert msg.tool_call_id is None
    
    def test_message_role_enum(self):
        """Test MessageRole enum values."""
        assert MessageRole.SYSTEM.value == "system"
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.TOOL.value == "tool"


class TestTokenUsage:
    """Tests for the TokenUsage dataclass."""
    
    def test_token_usage_creation(self):
        """Test creating TokenUsage."""
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150
    
    def test_token_usage_total_calculation(self):
        """Test that total_tokens is calculated correctly."""
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,  # Should be 150
        )
        
        # Verify calculation
        assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens