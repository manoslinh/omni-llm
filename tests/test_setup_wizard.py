"""
Tests for the interactive setup wizard.
"""

import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
import yaml

from omni.cli.setup import SetupWizard


class TestSetupWizard:
    """Test the SetupWizard class."""

    def test_get_config_path(self) -> None:
        """Test getting configuration file path."""
        wizard = SetupWizard()
        config_path = wizard._get_config_path()

        # Should be in XDG config directory or ~/.config/omni
        assert "omni" in str(config_path)
        assert config_path.name == "config.yaml"

    def test_load_existing_config_exists(self) -> None:
        """Test loading existing configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a mock config file
            config_path = Path(tmpdir) / "config.yaml"
            config_data = {
                "providers": {
                    "test": {
                        "type": "mock",
                        "description": "Test provider",
                        "enabled": True,
                        "config": {},
                        "models": {},
                    }
                }
            }
            with open(config_path, "w") as f:
                yaml.dump(config_data, f)

            # Mock the config path
            wizard = SetupWizard()
            with patch.object(wizard, "config_path", config_path):
                result = wizard._load_existing_config()

            assert result is True
            assert wizard.existing_config is not None

    def test_load_existing_config_not_exists(self) -> None:
        """Test loading when config doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "nonexistent.yaml"

            wizard = SetupWizard()
            with patch.object(wizard, "config_path", config_path):
                result = wizard._load_existing_config()

            assert result is False
            assert wizard.existing_config is None

    def test_save_config(self) -> None:
        """Test saving configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"

            wizard = SetupWizard()
            wizard.new_config = {
                "providers": {
                    "test": {
                        "type": "mock",
                        "description": "Test provider",
                        "enabled": True,
                    }
                }
            }

            with patch.object(wizard, "config_path", config_path):
                result = wizard._save_config()

            assert result is True
            assert config_path.exists()

            # Verify the saved content
            with open(config_path) as f:
                saved_data = yaml.safe_load(f)
            assert saved_data["providers"]["test"]["type"] == "mock"

    def test_save_config_error(self) -> None:
        """Test error handling when saving config fails."""
        wizard = SetupWizard()
        wizard.new_config = {"test": "data"}

        # Mock config_path to be a directory (will cause error)
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(wizard, "config_path", Path(tmpdir)):
                result = wizard._save_config()

            assert result is False

    @patch("omni.cli.setup.Confirm.ask")
    def test_ask_for_api_key_with_key(self, mock_confirm: Mock) -> None:
        """Test asking for API key when user has one."""
        mock_confirm.return_value = True

        wizard = SetupWizard()

        # Mock Prompt.ask to return a test key
        with patch("omni.cli.setup.Prompt.ask") as mock_prompt:
            mock_prompt.return_value = "test-api-key-123"
            result = wizard._ask_for_api_key("Test Provider", "TEST_API_KEY")

        assert result == "test-api-key-123"
        mock_confirm.assert_called_once()

    @patch("omni.cli.setup.Confirm.ask")
    def test_ask_for_api_key_without_key(self, mock_confirm: Mock) -> None:
        """Test asking for API key when user doesn't have one."""
        mock_confirm.return_value = False

        wizard = SetupWizard()
        result = wizard._ask_for_api_key("Test Provider", "TEST_API_KEY")

        assert result is None
        mock_confirm.assert_called_once()

    @patch("omni.cli.setup.Confirm.ask")
    def test_ask_for_api_key_from_env(self, mock_confirm: Mock) -> None:
        """Test using API key from environment."""
        mock_confirm.return_value = True

        wizard = SetupWizard()

        # Set environment variable
        os.environ["TEST_API_KEY"] = "env-api-key-456"

        try:
            # Mock Confirm.ask for using env var
            mock_confirm.side_effect = [True, True]  # Has key, use env

            result = wizard._ask_for_api_key("Test Provider", "TEST_API_KEY")

            assert result == "env-api-key-456"
            assert mock_confirm.call_count == 2
        finally:
            # Clean up
            del os.environ["TEST_API_KEY"]

    @pytest.mark.asyncio
    @patch("omni.cli.setup.os.environ", {})
    @patch("omni.cli.setup.LiteLLMProvider")
    async def test_test_connection_success(self, mock_provider_class: Mock) -> None:
        """Test successful provider connection."""
        # Mock provider
        mock_provider = Mock()
        mock_provider.list_models.return_value = [
            "openai/gpt-4",
            "openai/gpt-3.5-turbo",
            "anthropic/claude-3",
        ]
        # Mock complete method
        mock_provider.complete = AsyncMock()
        mock_provider_class.return_value = mock_provider

        wizard = SetupWizard()
        success, models = await wizard._test_connection(
            provider_name="OpenAI",
            api_key="test-key",
            env_var="OPENAI_API_KEY",
            model_prefix="openai/"
        )

        assert success is True
        assert "openai/gpt-4" in models
        assert "openai/gpt-3.5-turbo" in models
        assert "anthropic/claude-3" not in models  # Should be filtered out

    @pytest.mark.asyncio
    @patch("omni.cli.setup.os.environ", {})
    @patch("omni.cli.setup.LiteLLMProvider")
    async def test_test_connection_failure(self, mock_provider_class: Mock) -> None:
        """Test failed provider connection."""
        # Mock provider to raise exception
        mock_provider = Mock()
        mock_provider.list_models.side_effect = Exception("Connection failed")
        mock_provider_class.return_value = mock_provider

        wizard = SetupWizard()
        success, models = await wizard._test_connection(
            provider_name="OpenAI",
            api_key="test-key",
            env_var="OPENAI_API_KEY",
            model_prefix="openai/"
        )

        assert success is False
        assert models == []

    @pytest.mark.asyncio
    @patch("omni.cli.setup.os.environ", {})
    @patch("omni.cli.setup.LiteLLMProvider")
    async def test_test_connection_no_models(self, mock_provider_class: Mock) -> None:
        """Test provider connection with no provider models."""
        # Mock provider with no OpenAI models
        mock_provider = Mock()
        mock_provider.list_models.return_value = [
            "anthropic/claude-3",
            "google/gemini",
        ]
        mock_provider_class.return_value = mock_provider

        wizard = SetupWizard()
        success, models = await wizard._test_connection(
            provider_name="OpenAI",
            api_key="test-key",
            env_var="OPENAI_API_KEY",
            model_prefix="openai/"
        )

        assert success is False
        assert models == []

    def test_configure_provider_openai(self) -> None:
        """Test configuring OpenAI provider."""
        wizard = SetupWizard()
        api_key = "test-openai-key"
        models = ["openai/gpt-4", "openai/gpt-3.5-turbo"]

        wizard._configure_provider("openai", api_key, models)

        # Check API key
        assert wizard.new_config["api_keys"]["OPENAI_API_KEY"] == api_key

        # Check provider config
        assert "openai" in wizard.new_config["providers"]
        provider = wizard.new_config["providers"]["openai"]
        assert provider["type"] == "litellm"
        assert provider["enabled"] is True

        # Check models
        assert "openai/gpt-4" in provider["models"]
        assert "openai/gpt-3.5-turbo" in provider["models"]

        # Check cost config
        assert "openai/gpt-4" in wizard.new_config["cost_config"]["rates"]
        assert "openai/gpt-3.5-turbo" in wizard.new_config["cost_config"]["rates"]

        # Check configured providers and models
        assert "OpenAI" in wizard.configured_providers
        assert "openai/gpt-4" in wizard.configured_models
        assert "openai/gpt-3.5-turbo" in wizard.configured_models

    def test_configure_provider_anthropic(self) -> None:
        """Test configuring Anthropic provider."""
        wizard = SetupWizard()
        api_key = "test-anthropic-key"
        models = ["anthropic/claude-3-opus", "anthropic/claude-3-haiku"]

        wizard._configure_provider("anthropic", api_key, models)

        # Check API key
        assert wizard.new_config["api_keys"]["ANTHROPIC_API_KEY"] == api_key

        # Check provider config
        assert "anthropic" in wizard.new_config["providers"]
        provider = wizard.new_config["providers"]["anthropic"]
        assert provider["type"] == "litellm"
        assert provider["enabled"] is True

        # Check models
        assert "anthropic/claude-3-opus" in provider["models"]
        assert "anthropic/claude-3-haiku" in provider["models"]

        # Check cost config
        assert "anthropic/claude-3-opus" in wizard.new_config["cost_config"]["rates"]
        assert "anthropic/claude-3-haiku" in wizard.new_config["cost_config"]["rates"]

        # Check configured providers and models
        assert "Anthropic" in wizard.configured_providers
        assert "anthropic/claude-3-opus" in wizard.configured_models
        assert "anthropic/claude-3-haiku" in wizard.configured_models

    @patch("omni.cli.setup.Confirm.ask")
    def test_configure_local_models_with_ollama(self, mock_confirm: Mock) -> None:
        """Test configuring local models with Ollama."""
        mock_confirm.return_value = True

        wizard = SetupWizard()

        # Mock LiteLLMProvider to return Ollama models
        with patch("omni.cli.setup.LiteLLMProvider") as mock_provider_class:
            mock_provider = Mock()
            mock_provider.list_models.return_value = [
                "ollama/llama2",
                "ollama/mistral",
                "openai/gpt-4",  # Should be filtered out
            ]
            mock_provider_class.return_value = mock_provider

            wizard._configure_local_models()

        # Check provider config
        assert "ollama" in wizard.new_config["providers"]
        provider = wizard.new_config["providers"]["ollama"]
        assert provider["type"] == "litellm"
        assert provider["enabled"] is True

        # Check provider configs
        assert "ollama" in wizard.new_config["provider_configs"]
        assert wizard.new_config["provider_configs"]["ollama"]["base_url"] == "http://localhost:11434"

        # Check models
        assert "ollama/llama2" in provider["models"]
        assert "ollama/mistral" in provider["models"]
        assert "openai/gpt-4" not in provider["models"]

        # Check cost config
        assert "ollama/llama2" in wizard.new_config["cost_config"]["rates"]
        assert wizard.new_config["cost_config"]["rates"]["ollama/llama2"]["input"] == 0.00

        # Check configured providers and models
        assert "Ollama" in wizard.configured_providers
        assert "ollama/llama2" in wizard.configured_models

    @patch("omni.cli.setup.Confirm.ask")
    def test_configure_local_models_without_ollama(self, mock_confirm: Mock) -> None:
        """Test configuring local models when user declines."""
        mock_confirm.return_value = False

        wizard = SetupWizard()
        wizard._configure_local_models()

        # Should not configure Ollama
        assert "ollama" not in wizard.new_config["providers"]
        assert "Ollama" not in wizard.configured_providers

    @patch("omni.cli.setup.Confirm.ask")
    def test_configure_local_models_connection_failed(self, mock_confirm: Mock) -> None:
        """Test configuring local models when connection fails."""
        mock_confirm.return_value = True

        wizard = SetupWizard()

        # Mock LiteLLMProvider to raise exception
        with patch("omni.cli.setup.LiteLLMProvider") as mock_provider_class:
            mock_provider = Mock()
            mock_provider.list_models.side_effect = Exception("Connection failed")
            mock_provider_class.return_value = mock_provider

            wizard._configure_local_models()

        # Should not configure Ollama
        assert "ollama" not in wizard.new_config["providers"]
        assert "Ollama" not in wizard.configured_providers

    def test_show_success_summary(self) -> None:
        """Test showing success summary."""
        wizard = SetupWizard()
        wizard.configured_providers = ["OpenAI", "Anthropic"]
        wizard.configured_models = [
            "openai/gpt-4",
            "openai/gpt-3.5-turbo",
            "anthropic/claude-3-opus",
        ]

        # Mock console.print to capture output
        with patch("omni.cli.setup.console.print") as mock_print:
            wizard._show_success_summary()

        # Should call print multiple times
        assert mock_print.call_count >= 2

    @pytest.mark.asyncio
    @patch("omni.cli.setup.SetupWizard._show_welcome")
    @patch("omni.cli.setup.SetupWizard._load_existing_config")
    @patch("omni.cli.setup.SetupWizard._ask_for_api_key")
    @patch("omni.cli.setup.SetupWizard._test_connection")
    @patch("omni.cli.setup.SetupWizard._configure_provider")
    @patch("omni.cli.setup.SetupWizard._save_config")
    @patch("omni.cli.setup.SetupWizard._show_success_summary")
    async def test_run_success(
        self,
        mock_show_success: Mock,
        mock_save_config: Mock,
        mock_configure_provider: Mock,
        mock_test_connection: AsyncMock,
        mock_ask_api_key: Mock,
        mock_load_config: Mock,
        mock_show_welcome: Mock,
    ) -> None:
        """Test successful setup run."""
        # Setup mocks
        mock_load_config.return_value = False  # No existing config
        mock_ask_api_key.return_value = "test-key"
        mock_test_connection.return_value = (True, ["openai/gpt-4"])
        mock_save_config.return_value = True

        # Make configure_provider actually add providers
        def configure_provider_side_effect(provider_name: str, api_key: str, models: list[str], **kwargs: Any) -> None:
            wizard.configured_providers.append("OpenAI")
            wizard.configured_models.extend(models)
        mock_configure_provider.side_effect = configure_provider_side_effect

        wizard = SetupWizard()

        # Mock other provider methods to return None (skip them)
        with patch.object(wizard, "_ask_for_api_key") as mock_ask:
            mock_ask.side_effect = ["test-key", None, None, None]  # Only OpenAI has key
            with patch.object(wizard, "_configure_local_models"):
                result = await wizard.run()

        assert result is True
        mock_show_welcome.assert_called_once()
        mock_configure_provider.assert_called_once()
        mock_save_config.assert_called_once()
        mock_show_success.assert_called_once()

    @pytest.mark.asyncio
    @patch("omni.cli.setup.SetupWizard._show_welcome")
    @patch("omni.cli.setup.SetupWizard._load_existing_config")
    async def test_run_no_providers_configured(
        self,
        mock_load_config: Mock,
        mock_show_welcome: Mock,
    ) -> None:
        """Test setup run with no providers configured."""
        mock_load_config.return_value = False

        wizard = SetupWizard()

        # Mock all provider methods to return None (no keys)
        with patch.object(wizard, "_ask_for_api_key", return_value=None):
            with patch.object(wizard, "_configure_local_models"):
                result = await wizard.run()

        assert result is False
        mock_show_welcome.assert_called_once()

    @pytest.mark.asyncio
    @patch("omni.cli.setup.SetupWizard._show_welcome")
    @patch("omni.cli.setup.SetupWizard._load_existing_config")
    async def test_run_keyboard_interrupt(
        self,
        mock_load_config: Mock,
        mock_show_welcome: Mock,
    ) -> None:
        """Test handling keyboard interrupt."""
        mock_load_config.return_value = False
        mock_show_welcome.side_effect = KeyboardInterrupt()

        wizard = SetupWizard()
        result = await wizard.run()

        assert result is False

    @pytest.mark.asyncio
    @patch("omni.cli.setup.SetupWizard._show_welcome")
    @patch("omni.cli.setup.SetupWizard._load_existing_config")
    async def test_run_exception(
        self,
        mock_load_config: Mock,
        mock_show_welcome: Mock,
    ) -> None:
        """Test handling general exception."""
        mock_load_config.return_value = False
        mock_show_welcome.side_effect = Exception("Test error")

        wizard = SetupWizard()
        result = await wizard.run()

        assert result is False

    def test_save_config_with_permissions(self) -> None:
        """Test saving configuration with secure file permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"

            wizard = SetupWizard()
            wizard.new_config = {
                "providers": {
                    "test": {
                        "type": "mock",
                        "description": "Test provider",
                        "enabled": True,
                    }
                }
            }

            with patch.object(wizard, "config_path", config_path):
                result = wizard._save_config()

            assert result is True
            assert config_path.exists()

            # Check file permissions (should be 0o600)
            import stat
            file_mode = config_path.stat().st_mode
            assert stat.S_IMODE(file_mode) == 0o600  # Owner read/write only

            # Verify the saved content
            with open(config_path) as f:
                saved_data = yaml.safe_load(f)
            assert saved_data["providers"]["test"]["type"] == "mock"

    def test_configure_provider_google(self) -> None:
        """Test configuring Google provider."""
        wizard = SetupWizard()
        api_key = "test-google-key"
        models = ["google/gemini-pro", "google/gemini-flash"]

        wizard._configure_provider("google", api_key, models)

        # Check API key
        assert wizard.new_config["api_keys"]["GOOGLE_API_KEY"] == api_key

        # Check provider config
        assert "google" in wizard.new_config["providers"]
        provider = wizard.new_config["providers"]["google"]
        assert provider["type"] == "litellm"
        assert provider["enabled"] is True

        # Check models
        assert "google/gemini-pro" in provider["models"]
        assert "google/gemini-flash" in provider["models"]

        # Check configured providers and models
        assert "Google AI" in wizard.configured_providers
        assert "google/gemini-pro" in wizard.configured_models

    def test_configure_provider_deepseek(self) -> None:
        """Test configuring DeepSeek provider."""
        wizard = SetupWizard()
        api_key = "test-deepseek-key"
        models = ["deepseek/deepseek-chat", "deepseek/deepseek-coder"]

        wizard._configure_provider("deepseek", api_key, models)

        # Check API key
        assert wizard.new_config["api_keys"]["DEEPSEEK_API_KEY"] == api_key

        # Check provider config
        assert "deepseek" in wizard.new_config["providers"]
        provider = wizard.new_config["providers"]["deepseek"]
        assert provider["type"] == "litellm"
        assert provider["enabled"] is True

        # Check models
        assert "deepseek/deepseek-chat" in provider["models"]
        assert "deepseek/deepseek-coder" in provider["models"]

        # Check configured providers and models
        assert "DeepSeek" in wizard.configured_providers
        assert "deepseek/deepseek-chat" in wizard.configured_models

    def test_configure_provider_ollama(self) -> None:
        """Test configuring Ollama provider."""
        wizard = SetupWizard()
        api_key = ""  # Ollama doesn't need API key
        models = ["ollama/llama2", "ollama/mistral"]

        wizard._configure_provider("ollama", api_key, models)

        # Check API key (should not be stored for Ollama)
        assert "OLLAMA_API_KEY" not in wizard.new_config.get("api_keys", {})

        # Check provider config
        assert "ollama" in wizard.new_config["providers"]
        provider = wizard.new_config["providers"]["ollama"]
        assert provider["type"] == "litellm"
        assert provider["enabled"] is True

        # Check models
        assert "ollama/llama2" in provider["models"]
        assert "ollama/mistral" in provider["models"]

        # Check configured providers and models
        assert "Ollama" in wizard.configured_providers
        assert "ollama/llama2" in wizard.configured_models

    def test_get_default_max_tokens(self) -> None:
        """Test getting default max tokens for providers."""
        wizard = SetupWizard()

        # Test OpenAI
        assert wizard._get_default_max_tokens("openai", "gpt-4") == 8192

        # Test Anthropic
        assert wizard._get_default_max_tokens("anthropic", "claude-3") == 200000

        # Test Google
        assert wizard._get_default_max_tokens("google", "gemini") == 1000000

        # Test DeepSeek
        assert wizard._get_default_max_tokens("deepseek", "deepseek-chat") == 64000

        # Test Ollama
        assert wizard._get_default_max_tokens("ollama", "llama2") == 4096

        # Test unknown provider
        assert wizard._get_default_max_tokens("unknown", "model") == 4096

    def test_get_temperature_range(self) -> None:
        """Test getting temperature ranges for providers."""
        wizard = SetupWizard()

        # Test OpenAI
        assert wizard._get_temperature_range("openai") == [0.0, 2.0]

        # Test Anthropic
        assert wizard._get_temperature_range("anthropic") == [0.0, 1.0]

        # Test Google
        assert wizard._get_temperature_range("google") == [0.0, 2.0]

        # Test DeepSeek
        assert wizard._get_temperature_range("deepseek") == [0.0, 2.0]

        # Test Ollama
        assert wizard._get_temperature_range("ollama") == [0.0, 1.0]

        # Test unknown provider
        assert wizard._get_temperature_range("unknown") == [0.0, 1.0]

    def test_get_cost_config(self) -> None:
        """Test getting cost configurations for providers."""
        wizard = SetupWizard()

        # Test OpenAI GPT-4
        gpt4_cost = wizard._get_cost_config("openai", "openai/gpt-4")
        assert gpt4_cost["input"] == 30.00
        assert gpt4_cost["output"] == 60.00

        # Test OpenAI GPT-3.5
        gpt35_cost = wizard._get_cost_config("openai", "openai/gpt-3.5-turbo")
        assert gpt35_cost["input"] == 0.50
        assert gpt35_cost["output"] == 1.50

        # Test Anthropic Opus
        opus_cost = wizard._get_cost_config("anthropic", "anthropic/claude-3-opus")
        assert opus_cost["input"] == 15.00
        assert opus_cost["output"] == 75.00

        # Test Google Gemini Pro
        gemini_pro_cost = wizard._get_cost_config("google", "google/gemini-pro")
        assert gemini_pro_cost["input"] == 3.50
        assert gemini_pro_cost["output"] == 10.50

        # Test DeepSeek
        deepseek_cost = wizard._get_cost_config("deepseek", "deepseek/deepseek-chat")
        assert deepseek_cost["input"] == 0.28
        assert deepseek_cost["output"] == 0.42

        # Test Ollama (free)
        ollama_cost = wizard._get_cost_config("ollama", "ollama/llama2")
        assert ollama_cost["input"] == 0.00
        assert ollama_cost["output"] == 0.00
