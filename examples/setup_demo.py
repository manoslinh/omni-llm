#!/usr/bin/env python3
"""
Demo script for the Omni-LLM setup wizard.

This script demonstrates how the setup wizard works
without requiring actual API keys.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

from omni.cli.setup import SetupWizard


async def demo_setup_wizard() -> None:
    """Demo the setup wizard with mocked interactions."""
    print("=" * 60)
    print("Omni-LLM Setup Wizard Demo")
    print("=" * 60)
    print("\nThis demo shows how the setup wizard guides users through configuration.")
    print("All user inputs and API calls are mocked for demonstration purposes.\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        print(f"Demo config will be saved to: {config_path}")

        wizard = SetupWizard()

        # Mock the config path
        with patch.object(wizard, "config_path", config_path):
            # Mock all user interactions
            with patch("omni.cli.setup.Confirm.ask") as mock_confirm:
                # Simulate user saying yes to OpenAI, no to others
                mock_confirm.side_effect = [
                    True,   # Has OpenAI key
                    True,   # Use provided key (not env)
                    False,  # No Anthropic key
                    False,  # No Google key
                    False,  # No DeepSeek key
                    False,  # No local models
                ]

                # Mock API key input
                with patch("omni.cli.setup.Prompt.ask") as mock_prompt:
                    mock_prompt.return_value = "sk-demo-openai-key-1234567890"

                    # Mock connection tests
                    with patch.object(wizard, "_test_openai_connection") as mock_test_openai:
                        mock_test_openai.return_value = (True, [
                            "openai/gpt-4",
                            "openai/gpt-4-turbo-preview",
                            "openai/gpt-3.5-turbo",
                        ])

                        with patch.object(wizard, "_test_anthropic_connection"):
                            with patch.object(wizard, "_test_google_connection"):
                                with patch.object(wizard, "_test_deepseek_connection"):
                                    # Run the wizard
                                    print("\n" + "=" * 60)
                                    print("Starting setup wizard...")
                                    print("=" * 60 + "\n")

                                    success = await wizard.run()

                                    if success:
                                        print("\n" + "=" * 60)
                                        print("Setup completed successfully!")
                                        print("=" * 60)

                                        # Show the generated config
                                        print("\nGenerated configuration:")
                                        print("-" * 40)
                                        with open(config_path) as f:
                                            print(f.read())
                                    else:
                                        print("\nSetup failed or was cancelled.")


def demo_cli_command() -> None:
    """Demo the CLI setup command."""
    print("\n" + "=" * 60)
    print("CLI Command Demo")
    print("=" * 60)
    print("\nYou can run the setup wizard from the command line:")
    print("  $ omni setup")
    print("\nThe wizard will guide you through:")
    print("  1. Welcome message")
    print("  2. OpenAI configuration (optional)")
    print("  3. Anthropic configuration (optional)")
    print("  4. Google AI configuration (optional)")
    print("  5. DeepSeek configuration (optional)")
    print("  6. Local models configuration (optional)")
    print("  7. Success summary")
    print("\nAll API keys are validated with test calls.")
    print("Configuration is saved to ~/.config/omni/config.yaml")


if __name__ == "__main__":
    # Run the demo
    asyncio.run(demo_setup_wizard())
    demo_cli_command()

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)
    print("\nTo try the real setup wizard:")
    print("  1. Install rich: pip install rich")
    print("  2. Run: omni setup")
    print("\nThe wizard supports:")
    print("  • Input masking for API keys")
    print("  • Environment variable detection")
    print("  • Async validation of API keys")
    print("  • Graceful error handling")
    print("  • Configuration merging")
