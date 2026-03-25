"""
Comprehensive provider integration tests for Omni-LLM.

Tests ModelProvider interface compliance, LiteLLMProvider initialization,
and configuration loading.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from typing import Dict, Any, List

from omni.models.provider import (
    ModelProvider,
    Message,
    MessageRole,
    CompletionResult,
    TokenUsage,
    ModelCapabilities,
    ProviderError,
    ModelNotFoundError,
    RateLimitError,
    AuthenticationError,
    ContextLengthExceededError,
)

from omni.models.litellm_provider import LiteLLMProvider
from omni.models.mock_provider import MockProvider


class TestModelProviderInterface:
    """Test ModelProvider abstract interface compliance."""
    
    def test_abstract_methods_exist(self):
        """Verify all abstract methods are defined in the interface."""
        abstract_methods = ModelProvider.__abstractmethods__
        expected_methods = {
            'complete',
            'count_tokens',
            'estimate_cost',
            'get_capabilities',
            'list_models',
            'close',
        }
        
        # Check all expected methods are abstract
        for method in expected_methods:
            assert method in abstract_methods, f"Method {method} should be abstract"
        
        # Check no unexpected abstract methods
        for method in abstract_methods:
            assert method in expected_methods, f"Unexpected abstract method: {method}"
    
    def test_message_dataclass(self):
        """Test Message dataclass creation and properties."""
        # Basic message
        msg = Message(role=MessageRole.USER, content="Hello")
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"
        assert msg.name is None
        assert msg.tool_calls is None
        assert msg.tool_call_id is None
        
        # Message with all fields
        msg = Message(
            role=MessageRole.ASSISTANT,
            content="Response",
            name="assistant-1",
            tool_calls=[{"type": "function", "function": {"name": "test"}}],
            tool_call_id="call_123",
        )
        assert msg.role == MessageRole.ASSISTANT
        assert msg.content == "Response"
        assert msg.name == "assistant-1"
        assert msg.tool_calls == [{"type": "function", "function": {"name": "test"}}]
        assert msg.tool_call_id == "call_123"
    
    def test_message_role_enum(self):
        """Test MessageRole enum values."""
        assert MessageRole.SYSTEM.value == "system"
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.TOOL.value == "tool"
        
        # Test string conversion
        assert str(MessageRole.SYSTEM) == "system"
        assert MessageRole("system") == MessageRole.SYSTEM
    
    def test_completion_result_dataclass(self):
        """Test CompletionResult dataclass."""
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        result = CompletionResult(
            content="Test response",
            model="test-model",
            usage=usage,
            finish_reason="stop",
            tool_calls=[{"type": "function"}],
        )
        
        assert result.content == "Test response"
        assert result.model == "test-model"
        assert result.usage == usage
        assert result.finish_reason == "stop"
        assert result.tool_calls == [{"type": "function"}]
    
    def test_token_usage_dataclass(self):
        """Test TokenUsage dataclass and calculation."""
        # Basic creation
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150
        
        # Verify total calculation
        assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens
        
        # Test with mismatched total (should still work)
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=200)
        assert usage.total_tokens == 200  # Not validated, just stored
    
    def test_model_capabilities_dataclass(self):
        """Test ModelCapabilities dataclass."""
        capabilities = ModelCapabilities(
            supports_edit_format="editblock",
            max_context_tokens=128000,
            supports_tools=True,
            supports_streaming=True,
            supports_vision=False,
            supports_audio=False,
            temperature_range=(0.0, 2.0),
            top_p_range=(0.0, 1.0),
        )
        
        assert capabilities.supports_edit_format == "editblock"
        assert capabilities.max_context_tokens == 128000
        assert capabilities.supports_tools is True
        assert capabilities.supports_streaming is True
        assert capabilities.supports_vision is False
        assert capabilities.supports_audio is False
        assert capabilities.temperature_range == (0.0, 2.0)
        assert capabilities.top_p_range == (0.0, 1.0)
        
        # Test defaults
        default_capabilities = ModelCapabilities()
        assert default_capabilities.supports_edit_format == "whole"
        assert default_capabilities.max_context_tokens == 128_000
        assert default_capabilities.supports_tools is False
        assert default_capabilities.supports_streaming is True
    
    def test_provider_error_hierarchy(self):
        """Test provider error class hierarchy."""
        # Base error
        base_error = ProviderError("Test error")
        assert str(base_error) == "Test error"
        
        # Subclass errors
        model_error = ModelNotFoundError("Model not found")
        assert isinstance(model_error, ProviderError)
        assert str(model_error) == "Model not found"
        
        rate_error = RateLimitError("Rate limit")
        assert isinstance(rate_error, ProviderError)
        
        auth_error = AuthenticationError("Auth failed")
        assert isinstance(auth_error, ProviderError)
        
        context_error = ContextLengthExceededError("Context exceeded")
        assert isinstance(context_error, ProviderError)


class TestMockProvider:
    """Test MockProvider implementation."""
    
    @pytest.fixture
    def provider(self):
        """Create a MockProvider for testing."""
        return MockProvider()
    
    @pytest.mark.asyncio
    async def test_complete_basic(self, provider):
        """Test basic completion with MockProvider."""
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
    async def test_complete_with_custom_responses(self):
        """Test MockProvider with custom responses."""
        custom_responses = {
            "custom/model": "Custom response for custom model",
        }
        provider = MockProvider(responses=custom_responses)
        
        result = await provider.complete(
            messages=[Message(role=MessageRole.USER, content="Test")],
            model="custom/model",
        )
        
        assert result.content == "Custom response for custom model"
        await provider.close()
    
    def test_count_tokens(self, provider):
        """Test token counting with MockProvider."""
        text = "Hello, world! This is a test."
        tokens = provider.count_tokens(text, "openai/gpt-4")
        
        # Rough estimate: 4 chars per token
        expected_min = len(text) // 5
        expected_max = len(text) // 3
        
        assert expected_min <= tokens <= expected_max
    
    def test_estimate_cost(self, provider):
        """Test cost estimation with MockProvider."""
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
        """Test getting model capabilities with MockProvider."""
        capabilities = provider.get_capabilities("openai/gpt-4")
        
        assert capabilities.supports_edit_format == "editblock"
        assert capabilities.max_context_tokens == 128_000
        assert capabilities.supports_tools is True
        assert capabilities.supports_streaming is True
    
    def test_list_models(self, provider):
        """Test listing available models with MockProvider."""
        models = provider.list_models()
        
        assert isinstance(models, list)
        assert len(models) > 0
        assert "openai/gpt-4" in models
        assert "anthropic/claude-3-sonnet" in models
        assert "deepseek/deepseek-chat" in models
    
    @pytest.mark.asyncio
    async def test_call_logging(self, provider):
        """Test that calls are logged in MockProvider."""
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
        """Test closing the MockProvider."""
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


class TestLiteLLMProvider:
    """Test LiteLLMProvider implementation."""
    
    @pytest.fixture
    def mock_litellm(self):
        """Mock LiteLLM module."""
        with patch('omni.models.litellm_provider.litellm') as mock_litellm, \
             patch('omni.models.litellm_provider.token_counter') as mock_token_counter, \
             patch('omni.models.litellm_provider.LITELLM_AVAILABLE', True):
            
            # Mock completion response
            mock_response = Mock()
            mock_choice = Mock()
            mock_message = Mock()
            mock_message.content = "Mock response"
            mock_message.tool_calls = None
            mock_choice.message = mock_message
            mock_choice.finish_reason = "stop"
            mock_response.choices = [mock_choice]
            
            mock_usage = Mock()
            mock_usage.prompt_tokens = 100
            mock_usage.completion_tokens = 50
            mock_usage.total_tokens = 150
            mock_response.usage = mock_usage
            
            mock_litellm.completion.return_value = mock_response
            mock_litellm.completion_cost.return_value = 0.0015  # $0.0015
            
            # Mock token counter
            mock_token_counter.return_value = 25
            
            yield {
                'litellm': mock_litellm,
                'token_counter': mock_token_counter,
                'response': mock_response,
            }
    
    @pytest.fixture
    def provider(self, mock_litellm):
        """Create a LiteLLMProvider with mocked dependencies."""
        return LiteLLMProvider(config={"drop_params": True})
    
    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test LiteLLMProvider initialization."""
        # Test with LiteLLM available
        with patch('omni.models.litellm_provider.LITELLM_AVAILABLE', True):
            provider = LiteLLMProvider()
            assert provider.config == {"drop_params": True}
            assert provider._model_cache == {}
        
        # Test with custom config
        config = {"custom_key": "value", "drop_params": False}
        with patch('omni.models.litellm_provider.LITELLM_AVAILABLE', True):
            provider = LiteLLMProvider(config=config)
            assert provider.config == config
        
        # Test without LiteLLM installed
        with patch('omni.models.litellm_provider.LITELLM_AVAILABLE', False):
            with pytest.raises(ImportError) as exc_info:
                LiteLLMProvider()
            assert "LiteLLM is not installed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_complete_basic(self, provider, mock_litellm):
        """Test basic completion."""
        messages = [
            Message(role=MessageRole.USER, content="Hello, world!")
        ]
        
        result = await provider.complete(
            messages=messages,
            model="openai/gpt-4",
            temperature=0.7,
            max_tokens=100,
        )
        
        # Verify result
        assert result.content == "Mock response"
        assert result.model == "openai/gpt-4"
        assert result.finish_reason == "stop"
        assert result.tool_calls is None
        
        # Verify usage
        assert result.usage.prompt_tokens == 100
        assert result.usage.completion_tokens == 50
        assert result.usage.total_tokens == 150
        
        # Verify LiteLLM was called correctly
        mock_litellm['litellm'].completion.assert_called_once()
        call_args = mock_litellm['litellm'].completion.call_args
        
        assert call_args.kwargs['model'] == "openai/gpt-4"
        assert call_args.kwargs['temperature'] == 0.7
        assert call_args.kwargs['max_tokens'] == 100
        assert call_args.kwargs['drop_params'] is True
        
        # Verify message conversion
        litellm_messages = call_args.kwargs['messages']
        assert len(litellm_messages) == 1
        assert litellm_messages[0]['role'] == 'user'
        assert litellm_messages[0]['content'] == 'Hello, world!'
    
    @pytest.mark.asyncio
    async def test_complete_with_system_message(self, provider, mock_litellm):
        """Test completion with system message."""
        messages = [
            Message(role=MessageRole.SYSTEM, content="You are helpful"),
            Message(role=MessageRole.USER, content="What is 2+2?"),
        ]
        
        result = await provider.complete(
            messages=messages,
            model="anthropic/claude-3-sonnet",
        )
        
        assert result.content == "Mock response"
        assert result.model == "anthropic/claude-3-sonnet"
        
        # Verify messages were converted correctly
        call_args = mock_litellm['litellm'].completion.call_args
        litellm_messages = call_args.kwargs['messages']
        
        assert len(litellm_messages) == 2
        assert litellm_messages[0]['role'] == 'system'
        assert litellm_messages[0]['content'] == "You are helpful"
        assert litellm_messages[1]['role'] == 'user'
        assert litellm_messages[1]['content'] == "What is 2+2?"
    
    @pytest.mark.asyncio
    async def test_complete_with_tool_calls(self, provider, mock_litellm):
        """Test completion with tool calls in messages."""
        # Mock response with tool calls
        mock_response = mock_litellm['response']
        mock_message = mock_response.choices[0].message
        mock_message.tool_calls = [{"type": "function", "function": {"name": "test"}}]
        
        messages = [
            Message(
                role=MessageRole.USER,
                content="Call the test function",
                tool_calls=[{"type": "function"}],
                tool_call_id="call_123",
            )
        ]
        
        result = await provider.complete(
            messages=messages,
            model="openai/gpt-4",
        )
        
        assert result.tool_calls == [{"type": "function", "function": {"name": "test"}}]
        
        # Verify message conversion includes tool fields
        call_args = mock_litellm['litellm'].completion.call_args
        litellm_messages = call_args.kwargs['messages']
        
        assert litellm_messages[0]['tool_calls'] == [{"type": "function"}]
        assert litellm_messages[0]['tool_call_id'] == "call_123"
    
    @pytest.mark.asyncio
    async def test_complete_error_handling(self, provider, mock_litellm):
        """Test error handling in complete method."""
        mock_litellm_instance = mock_litellm['litellm']
        
        # Test AuthenticationError
        from litellm.exceptions import AuthenticationError as LiteLLMAuthError
        mock_litellm_instance.completion.side_effect = LiteLLMAuthError("Invalid API key")
        
        with pytest.raises(AuthenticationError) as exc_info:
            await provider.complete(
                messages=[Message(role=MessageRole.USER, content="Test")],
                model="openai/gpt-4",
            )
        assert "Authentication failed" in str(exc_info.value)
        
        # Test RateLimitError
        from litellm.exceptions import RateLimitError as LiteLLMRateLimitError
        mock_litellm_instance.completion.side_effect = LiteLLMRateLimitError("Rate limit")
        
        with pytest.raises(RateLimitError) as exc_info:
            await provider.complete(
                messages=[Message(role=MessageRole.USER, content="Test")],
                model="openai/gpt-4",
            )
        assert "Rate limit exceeded" in str(exc_info.value)
        
        # Test ContextLengthExceededError
        from litellm.exceptions import ContextWindowExceededError as LiteLLMContextError
        mock_litellm_instance.completion.side_effect = LiteLLMContextError("Context")
        
        with pytest.raises(ContextLengthExceededError) as exc_info:
            await provider.complete(
                messages=[Message(role=MessageRole.USER, content="Test")],
                model="openai/gpt-4",
            )
        assert "Context length exceeded" in str(exc_info.value)
        
        # Test ModelNotFoundError (BadRequestError with "model" in message)
        from litellm.exceptions import BadRequestError as LiteLLMBadRequestError
        mock_litellm_instance.completion.side_effect = LiteLLMBadRequestError(
            "Model 'invalid-model' not found"
        )
        
        with pytest.raises(ModelNotFoundError) as exc_info:
            await provider.complete(
                messages=[Message(role=MessageRole.USER, content="Test")],
                model="invalid-model",
            )
        assert "Model not found" in str(exc_info.value)
        
        # Test generic ProviderError for other BadRequestError
        mock_litellm_instance.completion.side_effect = LiteLLMBadRequestError(
            "Invalid parameter"
        )
        
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(
                messages=[Message(role=MessageRole.USER, content="Test")],
                model="openai/gpt-4",
            )
        assert "Bad request" in str(exc_info.value)
        
        # Test generic ProviderError for unexpected exceptions
        mock_litellm_instance.completion.side_effect = Exception("Unexpected")
        
        with pytest.raises(ProviderError) as exc_info:
            await provider.complete(
                messages=[Message(role=MessageRole.USER, content="Test")],
                model="openai/gpt-4",
            )
        assert "Unexpected error" in str(exc_info.value)
    
    def test_count_tokens(self, provider, mock_litellm):
        """Test token counting."""
        text = "Hello, world! This is a test."
        
        tokens = provider.count_tokens(text, "openai/gpt-4")
        
        # Verify LiteLLM token counter was called
        mock_litellm['token_counter'].assert_called_once_with(
            model="openai/gpt-4",
            text=text,
        )
        assert tokens == 25
        
        # Test fallback when token counter fails
        mock_litellm['token_counter'].side_effect = Exception("Counter failed")
        
        tokens = provider.count_tokens(text, "openai/gpt-4")
        
        # Should fall back to rough estimate (len // 4)
        expected_tokens = len(text) // 4
        assert tokens == expected_tokens
    
    def test_estimate_cost(self, provider, mock_litellm):
        """Test cost estimation."""
        input_tokens = 1000
        output_tokens = 500
        
        cost = provider.estimate_cost(input_tokens, output_tokens, "openai/gpt-4")
        
        # Verify LiteLLM cost calculation was called
        mock_litellm['litellm'].completion_cost.assert_called_once_with(
            model="openai/gpt-4",
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
        assert cost == 0.0015
        
        # Test fallback when cost calculation fails
        mock_litellm['litellm'].completion_cost.side_effect = Exception("Cost failed")
        
        cost = provider.estimate_cost(input_tokens, output_tokens, "openai/gpt-4")
        
        # Should use fallback estimation
        assert cost > 0
    
    def test_get_capabilities(self, provider):
        """Test getting model capabilities."""
        # Test caching
        capabilities1 = provider.get_capabilities("openai/gpt-4")
        capabilities2 = provider.get_capabilities("openai/gpt-4")
        
        assert capabilities1 is capabilities2  # Same object from cache
        
        # Test different models have different capabilities
        gpt4_capabilities = provider.get_capabilities("openai/gpt-4")
        gpt35_capabilities = provider.get_capabilities("openai/gpt-3.5-turbo")
        
        assert gpt4_capabilities.supports_edit_format == "editblock"
        assert gpt35_capabilities.supports_edit_format == "diff"
        
        # Test Claude 3 capabilities
        claude_capabilities = provider.get_capabilities("anthropic/claude-3-sonnet")
        assert claude_capabilities.max_context_tokens == 200_000
        assert claude_capabilities.supports_tools is True
        assert claude_capabilities.supports_vision is True
        
        # Test Gemini 1.5 capabilities
        gemini_capabilities = provider.get_capabilities("google/gemini-1.5-pro")
        assert gemini_capabilities.max_context_tokens == 1_000_000
        
        # Test default capabilities
        unknown_capabilities = provider.get_capabilities("unknown/model")
        assert unknown_capabilities.supports_edit_format == "whole"
        assert unknown_capabilities.max_context_tokens == 128_000
    
    def test_list_models(self, provider):
        """Test listing available models."""
        models = provider.list_models()
        
        assert isinstance(models, list)
        assert len(models) > 0
        
        # Check for common models
        expected_models = [
            "openai/gpt-4",
            "openai/gpt-3.5-turbo",
            "anthropic/claude-3-sonnet",
            "google/gemini-1.5-pro",
            "deepseek/deepseek-chat",
        ]
        
        for expected in expected_models:
            assert expected in models, f"Expected model {expected} not in list"
        
        # Verify no duplicates
        assert len(models) == len(set(models))
    
    @pytest.mark.asyncio
    async def test_close(self, provider):
        """Test closing the provider."""
        # Populate cache
        provider.get_capabilities("openai/gpt-4")
        assert len(provider._model_cache) > 0
        
        # Close provider
        await provider.close()
        
        # Cache should be cleared
        assert len(provider._model_cache) == 0
    
    def test_convert_messages(self, provider):
        """Test internal message conversion."""
        messages = [
            Message(role=MessageRole.SYSTEM, content="System"),
            Message(role=MessageRole.USER, content="User", name="user1"),
            Message(
                role=MessageRole.ASSISTANT,
                content="Assistant",
                tool_calls=[{"type": "function"}],
                tool_call_id="call_123",
            ),
        ]
        
        litellm_messages = provider._convert_messages(messages)
        
        assert len(litellm_messages) == 3
        
        # Check first message (system)
        assert litellm_messages[0]["role"] == "system"
        assert litellm_messages[0]["content"] == "System"
        assert "name" not in litellm_messages[0]
        
        # Check second message (user with name)
        assert litellm_messages[1]["role"] == "user"
        assert litellm_messages[1]["content"] == "User"
        assert litellm_messages[1]["name"] == "user1"
        
        # Check third message (assistant with tool calls)
        assert litellm_messages[2]["role"] == "assistant"
        assert litellm_messages[2]["content"] == "Assistant"
        assert litellm_messages[2]["tool_calls"] == [{"type": "function"}]
        assert litellm_messages[2]["tool_call_id"] == "call_123"


class TestConfigurationLoading:
    """Test configuration loading and integration."""
    
    def test_provider_config_loading(self):
        """Test that providers can be configured with different settings."""
        # Test with various config options
        configs = [
            {"drop_params": False, "timeout": 30},
            {"api_base": "http://localhost:8080"},
            {"custom_llm_provider": "openai"},
            {},  # Empty config should use defaults
        ]
        
        for config in configs:
            with patch('omni.models.litellm_provider.LITELLM_AVAILABLE', True):
                provider = LiteLLMProvider(config=config)
                # Config should be merged with defaults
                if "drop_params" not in config:
                    assert provider.config["drop_params"] is True
                for key, value in config.items():
                    assert provider.config[key] == value
    
    @pytest.mark.asyncio
    async def test_integration_workflow(self):
        """Test complete workflow: provider -> completion."""
        # Mock LiteLLM
        with patch('omni.models.litellm_provider.litellm') as mock_litellm, \
             patch('omni.models.litellm_provider.token_counter') as mock_token_counter, \
             patch('omni.models.litellm_provider.LITELLM_AVAILABLE', True):
            
            # Setup mock response
            mock_response = Mock()
            mock_choice = Mock()
            mock_message = Mock()
            mock_message.content = "Integration test response"
            mock_message.tool_calls = None
            mock_choice.message = mock_message
            mock_choice.finish_reason = "stop"
            mock_response.choices = [mock_choice]
            
            mock_usage = Mock()
            mock_usage.prompt_tokens = 150
            mock_usage.completion_tokens = 75
            mock_usage.total_tokens = 225
            mock_response.usage = mock_usage
            
            mock_litellm.completion.return_value = mock_response
            mock_litellm.completion_cost.return_value = 0.00225
            mock_token_counter.return_value = 30
            
            # Create provider with config
            provider = LiteLLMProvider(config={"timeout": 60})
            
            # Make a completion
            messages = [Message(role=MessageRole.USER, content="Integration test")]
            result = await provider.complete(
                messages=messages,
                model="openai/gpt-4",
                temperature=0.8,
            )
            
            # Verify completion
            assert result.content == "Integration test response"
            assert result.usage.prompt_tokens == 150
            assert result.usage.completion_tokens == 75
            
            # Verify provider was called with config
            mock_litellm.completion.assert_called_once()
            assert mock_litellm.completion.call_args.kwargs["timeout"] == 60
            
            # Clean up
            await provider.close()
    
    def test_backward_compatibility(self):
        """Test backward compatibility with existing code."""
        # Verify MessageRole enum values haven't changed
        assert MessageRole.SYSTEM.value == "system"
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.TOOL.value == "tool"
        
        # Verify TokenUsage structure
        usage = TokenUsage(100, 50, 150)
        assert hasattr(usage, 'prompt_tokens')
        assert hasattr(usage, 'completion_tokens')
        assert hasattr(usage, 'total_tokens')
        
        # Verify CompletionResult structure
        result = CompletionResult("test", "model", usage)
        assert hasattr(result, 'content')
        assert hasattr(result, 'model')
        assert hasattr(result, 'usage')
        assert hasattr(result, 'finish_reason')
        assert hasattr(result, 'tool_calls')
        
        # Verify ModelProvider interface methods exist
        provider_methods = set(ModelProvider.__abstractmethods__)
        required_methods = {
            'complete',
            'count_tokens',
            'estimate_cost',
            'get_capabilities',
            'list_models',
            'close',
        }
        assert required_methods.issubset(provider_methods)


class TestMockTesting:
    """Test mock testing patterns for providers."""
    
    def test_mock_provider_creation(self):
        """Test creating a mock provider for testing."""
        # Create a simple mock provider
        mock_provider = Mock(spec=ModelProvider)
        
        # Setup mock methods
        mock_provider.complete = AsyncMock()
        mock_provider.count_tokens = Mock(return_value=25)
        mock_provider.estimate_cost = Mock(return_value=0.001)
        mock_provider.get_capabilities = Mock(return_value=ModelCapabilities())
        mock_provider.list_models = Mock(return_value=["mock-model"])
        mock_provider.close = AsyncMock()
        
        # Verify mock can be used as ModelProvider
        assert isinstance(mock_provider, ModelProvider)
        
        # Test mock methods
        assert mock_provider.count_tokens("test", "model") == 25
        assert mock_provider.estimate_cost(100, 50, "model") == 0.001
        assert isinstance(mock_provider.get_capabilities("model"), ModelCapabilities)
        assert mock_provider.list_models() == ["mock-model"]
    
    @pytest.mark.asyncio
    async def test_mock_completion(self):
        """Test mocking completion calls."""
        mock_provider = Mock(spec=ModelProvider)
        
        # Setup async completion
        mock_result = CompletionResult(
            content="Mock response",
            model="mock-model",
            usage=TokenUsage(100, 50, 150),
        )
        mock_provider.complete = AsyncMock(return_value=mock_result)
        
        # Call mock
        messages = [Message(role=MessageRole.USER, content="Test")]
        result = await mock_provider.complete(
            messages=messages,
            model="mock-model",
            temperature=0.7,
        )
        
        # Verify
        assert result.content == "Mock response"
        assert result.model == "mock-model"
        assert result.usage.prompt_tokens == 100
        
        # Verify mock was called correctly
        mock_provider.complete.assert_called_once_with(
            messages=messages,
            model="mock-model",
            temperature=0.7,
        )
    
    def test_patch_litellm_imports(self):
        """Test patching LiteLLM imports for testing."""
        # Simulate LiteLLM not being installed
        with patch('omni.models.litellm_provider.LITELLM_AVAILABLE', False):
            with pytest.raises(ImportError):
                LiteLLMProvider()
        
        # Simulate LiteLLM being installed
        with patch('omni.models.litellm_provider.LITELLM_AVAILABLE', True):
            # Mock the actual imports
            with patch('omni.models.litellm_provider.litellm'), \
                 patch('omni.models.litellm_provider.token_counter'), \
                 patch('omni.models.litellm_provider.LiteLLMAuthError', Exception), \
                 patch('omni.models.litellm_provider.LiteLLMRateLimitError', Exception), \
                 patch('omni.models.litellm_provider.LiteLLMContextError', Exception), \
                 patch('omni.models.litellm_provider.LiteLLMBadRequestError', Exception):
                
                provider = LiteLLMProvider()
                assert provider.config["drop_params"] is True
    
    def test_error_path_mocking(self):
        """Test mocking error paths."""
        # Create a mock that raises specific errors
        mock_provider = Mock(spec=ModelProvider)
        
        # Test AuthenticationError
        mock_provider.complete = AsyncMock(side_effect=AuthenticationError("Auth failed"))
        
        with pytest.raises(AuthenticationError):
            asyncio.run(mock_provider.complete([], "model"))
        
        # Test RateLimitError
        mock_provider.complete = AsyncMock(side_effect=RateLimitError("Rate limit"))
        
        with pytest.raises(RateLimitError):
            asyncio.run(mock_provider.complete([], "model"))
        
        # Test ModelNotFoundError
        mock_provider.complete = AsyncMock(side_effect=ModelNotFoundError("Not found"))
        
        with pytest.raises(ModelNotFoundError):
            asyncio.run(mock_provider.complete([], "model"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])