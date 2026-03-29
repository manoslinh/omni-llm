"""
Integration test for the setup command.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from omni.cli.setup import SetupWizard


def test_setup_command_in_cli() -> None:
    """Test that setup command is available in CLI."""
    from omni.cli.main import cli
    
    # Check that setup command exists
    commands = [cmd.name for cmd in cli.commands.values()]
    assert "setup" in commands


def test_setup_wizard_creates_config() -> None:
    """Test that setup wizard creates a config file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        
        wizard = SetupWizard()
        
        # Mock the config path
        with patch.object(wizard, "config_path", config_path):
            # Mock user interactions to skip all providers
            with patch("omni.cli.setup.Confirm.ask") as mock_confirm:
                mock_confirm.return_value = False  # No API keys
                
                # Mock console to avoid output
                with patch("omni.cli.setup.console.print"):
                    # Run setup (will fail because no providers configured)
                    success = asyncio.run(wizard.run())
                    
                    # Should fail because no providers configured
                    assert success is False
                    # Config file should not exist
                    assert not config_path.exists()


@pytest.mark.asyncio
async def test_setup_with_mock_provider() -> None:
    """Test setup with a mock provider."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        
        wizard = SetupWizard()
        
        # Mock the config path
        with patch.object(wizard, "config_path", config_path):
            # Mock user interactions
            with patch("omni.cli.setup.Confirm.ask") as mock_confirm:
                mock_confirm.side_effect = [
                    True,  # Has OpenAI key
                    True,  # Use provided key (not env)
                    False,  # No Anthropic key
                    False,  # No Google key
                    False,  # No DeepSeek key
                    False,  # No local models
                ]
                
                # Mock API key input
                with patch("os.getenv") as mock_getenv:
                    mock_getenv.return_value = None  # No env var
                    with patch("omni.cli.setup.Prompt.ask") as mock_prompt:
                        mock_prompt.return_value = "test-openai-key"
                        
                        # Mock connection test to succeed
                        with patch.object(wizard, "_test_connection") as mock_test:
                            mock_test.return_value = (True, ["openai/gpt-4"])
                        
                        # Mock console to avoid output
                        with patch("omni.cli.setup.console.print"):
                            # Run setup
                            success = await wizard.run()
                            
                            # Should succeed
                            assert success is True
                            # Config file should exist
                            assert config_path.exists()
                            
                            # Check config content
                            import yaml
                            with open(config_path) as f:
                                config = yaml.safe_load(f)
                            
                            assert "providers" in config
                            assert "openai" in config["providers"]
                            assert "api_keys" in config
                            assert config["api_keys"]["OPENAI_API_KEY"] == "test-openai-key"


if __name__ == "__main__":
    # Quick manual test
    import asyncio
    test_setup_command_in_cli()
    test_setup_wizard_creates_config()
    asyncio.run(test_setup_with_mock_provider())
    print("All integration tests passed!")