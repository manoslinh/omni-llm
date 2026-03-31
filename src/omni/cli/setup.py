"""
Interactive Setup Wizard for Omni-LLM.

Provides a friendly, guided setup experience for configuring API keys
and providers for first-time users.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from ..models.litellm_provider import LiteLLMProvider
from ..models.provider import Message, MessageRole
from ..providers.config import (
    ConfigLoader,
    ProviderConfiguration,
)

console = Console()


class SetupWizard:
    """Interactive setup wizard for Omni-LLM."""

    def __init__(self) -> None:
        """Initialize the setup wizard."""
        self.config_path = self._get_config_path()
        self.existing_config: ProviderConfiguration | None = None
        self.new_config: dict[str, Any] = {
            "providers": {},
            "defaults": {},
            "api_keys": {},
            "provider_configs": {},
            "cost_config": {"rates": {}},
            "budget": {},
            "rate_limiting": {},
        }
        self.configured_providers: list[str] = []
        self.configured_models: list[str] = []

    def _get_config_path(self) -> Path:
        """Get the configuration file path."""
        # Try XDG config directory first
        xdg_config_home = os.getenv("XDG_CONFIG_HOME")
        if xdg_config_home:
            config_dir = Path(xdg_config_home) / "omni"
        else:
            config_dir = Path.home() / ".config" / "omni"

        # Create directory if it doesn't exist
        config_dir.mkdir(parents=True, exist_ok=True)

        return config_dir / "config.yaml"

    def _load_existing_config(self) -> bool:
        """Load existing configuration if it exists."""
        if self.config_path.exists():
            try:
                self.existing_config = ConfigLoader.load_providers_config(
                    self.config_path
                )
                console.print(
                    f"[dim]Found existing configuration at: {self.config_path}[/dim]"
                )
                return True
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Could not load existing config: {e}[/yellow]"
                )
        return False

    def _save_config(self) -> bool:
        """Save configuration to file with secure permissions."""
        try:
            # Convert new_config to YAML
            with open(self.config_path, "w") as f:
                yaml.dump(self.new_config, f, default_flow_style=False, sort_keys=False)

            # Set secure file permissions (owner read/write only)
            os.chmod(self.config_path, 0o600)

            console.print(
                f"\n[green]✅ Configuration saved to: {self.config_path}[/green]"
            )
            console.print("[dim]File permissions set to owner read/write only (0o600)[/dim]")
            return True
        except Exception as e:
            console.print(f"[red]❌ Error saving configuration: {e}[/red]")
            return False

    def _show_welcome(self) -> None:
        """Show welcome message."""
        welcome_text = """
        [bold cyan]Welcome to Omni-LLM! 🎉[/bold cyan]

        Let's get you set up in under 2 minutes.

        We'll configure your AI providers so you can
        experience multi-agent orchestration.
        """
        console.print(Panel(welcome_text, border_style="cyan"))

    def _ask_for_api_key(self, provider_name: str, env_var: str) -> str | None:
        """Ask user for an API key with masked input."""
        console.print(f"\n[bold]Configuring {provider_name}[/bold]")

        has_key = Confirm.ask(
            f"Do you have a {provider_name} API key?",
            default=True,
        )

        if not has_key:
            console.print(f"[dim]Skipping {provider_name} configuration[/dim]")
            return None

        # Try to get from environment first
        env_value = os.getenv(env_var)
        if env_value:
            use_env = Confirm.ask(
                f"Found {env_var} in environment. Use it?",
                default=True,
            )
            if use_env:
                console.print(f"[green]Using {env_var} from environment[/green]")
                return env_value

        # Ask for key with masked input
        api_key = Prompt.ask(
            f"Enter your {provider_name} API key",
            password=True,
        )

        if not api_key or api_key.strip() == "":
            console.print(f"[yellow]Empty API key provided, skipping {provider_name}[/yellow]")
            return None

        return api_key.strip()

    async def _test_connection(
        self,
        provider_name: str,
        api_key: str,
        env_var: str,
        model_prefix: str
    ) -> tuple[bool, list[str]]:
        """
        Test provider connection with API key.

        Args:
            provider_name: Human-readable provider name
            api_key: API key to test
            env_var: Environment variable name for this provider
            model_prefix: Model prefix to filter (e.g., "openai/", "anthropic/")

        Returns:
            Tuple of (success, list_of_models)
        """
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
            ) as progress:
                task = progress.add_task(
                    f"Testing {provider_name} connection...", total=None
                )

                # Set API key in environment for LiteLLM to pick up
                os.environ[env_var] = api_key
                provider = LiteLLMProvider()

                # Make a minimal API call to validate the key
                # Use a simple completion with a trivial prompt
                try:
                    # First try to list models (fast check)
                    models = provider.list_models()

                    # Filter for provider-specific models
                    provider_models = [m for m in models if m.startswith(model_prefix)]

                    if provider_models:
                        # Now make an actual API call to truly validate the key
                        # Use a minimal prompt and low max_tokens
                        # Get the first actual model for testing
                        test_model = provider_models[0]
                        test_result = await provider.complete(
                            messages=[Message(role=MessageRole.USER, content="test")],
                            model=test_model,
                            temperature=0.1,
                            max_tokens=1,
                        )

                        # If we get here, the key is valid
                        progress.update(
                            task,
                            description=f"[green]✅ Success! Found {len(provider_models)} {provider_name} models[/green]",
                        )
                        return True, sorted(provider_models)[:10]  # Show first 10
                    else:
                        progress.update(
                            task,
                            description=f"[yellow]⚠️  Connected but no {provider_name} models found[/yellow]",
                        )
                        return False, []

                except Exception as api_error:
                    # If list_models worked but complete failed, still count as success
                    # (some providers might have different auth for different endpoints)
                    provider_models = [m for m in models if m.startswith(model_prefix)] if 'models' in locals() else []
                    if provider_models:
                        progress.update(
                            task,
                            description=f"[green]✅ Success! Found {len(provider_models)} {provider_name} models[/green]",
                        )
                        return True, sorted(provider_models)[:10]
                    else:
                        progress.update(
                            task,
                            description=f"[red]❌ Connection failed: {api_error}[/red]",
                        )
                        return False, []

        except Exception as e:
            console.print(f"[red]❌ {provider_name} connection failed: {e}[/red]")
            return False, []



    def _configure_provider(
        self,
        provider_name: str,
        api_key: str,
        models: list[str],
        config_overrides: dict[str, Any] | None = None
    ) -> None:
        """
        Configure a provider in the new config.

        Args:
            provider_name: Provider name (e.g., "openai", "anthropic")
            api_key: API key for the provider
            models: List of model identifiers
            config_overrides: Optional configuration overrides
        """
        # Map provider names to their display names and env vars
        provider_info = {
            "openai": {
                "display_name": "OpenAI",
                "env_var": "OPENAI_API_KEY",
                "base_url": "https://api.openai.com/v1",
                "description": "OpenAI models via LiteLLM",
            },
            "anthropic": {
                "display_name": "Anthropic",
                "env_var": "ANTHROPIC_API_KEY",
                "base_url": "https://api.anthropic.com",
                "description": "Anthropic Claude models via LiteLLM",
                "version": "2023-06-01",
            },
            "google": {
                "display_name": "Google AI",
                "env_var": "GOOGLE_API_KEY",
                "base_url": "https://generativelanguage.googleapis.com",
                "description": "Google Gemini models via LiteLLM",
            },
            "deepseek": {
                "display_name": "DeepSeek",
                "env_var": "DEEPSEEK_API_KEY",
                "base_url": "https://api.deepseek.com",
                "description": "DeepSeek models via LiteLLM",
            },
            "ollama": {
                "display_name": "Ollama",
                "env_var": "",  # Ollama doesn't use API keys
                "base_url": "http://localhost:11434",
                "description": "Ollama local models via LiteLLM",
            },
        }

        if provider_name not in provider_info:
            raise ValueError(f"Unknown provider: {provider_name}")

        info = provider_info[provider_name]

        # Store API key (skip for providers without API keys like Ollama)
        if info["env_var"] and api_key:
            self.new_config["api_keys"][info["env_var"]] = api_key

        # Configure provider-specific settings
        provider_config = {"base_url": info["base_url"]}
        if "version" in info:
            provider_config["version"] = info["version"]

        if config_overrides:
            provider_config.update(config_overrides)

        self.new_config["provider_configs"][provider_name] = provider_config

        # Add provider if not exists
        if provider_name not in self.new_config["providers"]:
            self.new_config["providers"][provider_name] = {
                "type": "litellm",
                "description": info["description"],
                "enabled": True,
                "config": {},
                "models": {},
            }

        # Add models
        for model in models:
            # Remove unused model_name variable
            self.new_config["providers"][provider_name]["models"][model] = {
                "max_tokens": self._get_default_max_tokens(provider_name, model),
                "temperature_range": self._get_temperature_range(provider_name),
                "supports_functions": provider_name in ["openai", "deepseek"],
                "supports_tools": provider_name in ["openai", "anthropic", "google", "deepseek"],
            }

            # Add cost config
            self.new_config["cost_config"]["rates"][model] = self._get_cost_config(provider_name, model)

        self.configured_providers.append(info["display_name"])
        self.configured_models.extend(models)

    def _get_default_max_tokens(self, provider_name: str, model: str) -> int:
        """Get default max tokens for a provider/model."""
        defaults = {
            "openai": 8192,
            "anthropic": 200000,
            "google": 1000000,
            "deepseek": 64000,
            "ollama": 4096,
        }
        return defaults.get(provider_name, 4096)

    def _get_temperature_range(self, provider_name: str) -> list[float]:
        """Get temperature range for a provider."""
        ranges = {
            "openai": [0.0, 2.0],
            "anthropic": [0.0, 1.0],
            "google": [0.0, 2.0],
            "deepseek": [0.0, 2.0],
            "ollama": [0.0, 1.0],
        }
        return ranges.get(provider_name, [0.0, 1.0])

    def _get_cost_config(self, provider_name: str, model: str) -> dict[str, float]:
        """Get cost configuration for a provider/model."""
        # OpenAI costs
        if provider_name == "openai":
            if "gpt-4o-mini" in model or "gpt-4.1-mini" in model:
                return {"input": 0.15, "output": 0.60}
            elif "gpt-4o" in model:
                return {"input": 2.50, "output": 10.00}
            elif "gpt-4.1" in model:
                return {"input": 2.00, "output": 8.00}
            elif "o3-mini" in model:
                return {"input": 1.10, "output": 4.40}
            else:
                return {"input": 2.50, "output": 10.00}

        # Anthropic costs
        elif provider_name == "anthropic":
            if "sonnet" in model:
                return {"input": 3.00, "output": 15.00}
            elif "haiku" in model:
                return {"input": 0.80, "output": 4.00}
            elif "opus" in model:
                return {"input": 15.00, "output": 75.00}
            else:
                return {"input": 3.00, "output": 15.00}

        # Google costs
        elif provider_name == "google":
            if "2.5-pro" in model:
                return {"input": 1.25, "output": 10.00}
            elif "flash" in model:
                return {"input": 0.10, "output": 0.40}
            else:
                return {"input": 1.25, "output": 10.00}

        # DeepSeek costs
        elif provider_name == "deepseek":
            return {"input": 0.14, "output": 0.28}

        # Ollama (free)
        elif provider_name == "ollama":
            return {"input": 0.00, "output": 0.00}

        # Default
        return {"input": 1.00, "output": 3.00}



    def _configure_local_models(self) -> None:
        """Configure local models (Ollama)."""
        use_local = Confirm.ask(
            "Would you like to use local models (Ollama)?",
            default=False,
        )

        if not use_local:
            return

        # Test Ollama connection
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
            ) as progress:
                task = progress.add_task(
                    "Testing Ollama connection...", total=None
                )

                # Try to list Ollama models via LiteLLM
                # Ollama doesn't need API keys, so we can use empty config
                provider = LiteLLMProvider(config={"base_url": "http://localhost:11434"})
                models = provider.list_models()

                # Filter for Ollama models
                ollama_models = [m for m in models if m.startswith("ollama/")]

                if ollama_models:
                    progress.update(
                        task,
                        description=f"[green]✅ Success! Found {len(ollama_models)} Ollama models[/green]",
                    )

                    # Configure Ollama using the parameterized method
                    self._configure_provider(
                        provider_name="ollama",
                        api_key="",  # Ollama doesn't need API key
                        models=ollama_models,
                        config_overrides={
                            "base_url": "http://localhost:11434",
                            "timeout": 60,
                        }
                    )

                    console.print(f"[green]Configured {len(ollama_models)} local models[/green]")
                else:
                    progress.update(
                        task,
                        description="[yellow]⚠️  Ollama is running but no models found[/yellow]",
                    )
                    console.print("[yellow]Make sure you have pulled some models with `ollama pull`[/yellow]")

        except Exception as e:
            console.print(f"[red]❌ Could not connect to Ollama: {e}[/red]")
            console.print("[yellow]Make sure Ollama is installed and running on http://localhost:11434[/yellow]")

    def _show_success_summary(self) -> None:
        """Show success summary with configured providers and models."""
        success_text = f"""
        [bold green]Setup Complete! 🎉[/bold green]

        You now have access to:
        • {len(self.configured_providers)} providers
        • {len(self.configured_models)} models
        • Multi-agent orchestration ready!

        Try: [cyan]omni demo[/cyan]
        Or: [cyan]omni orchestrate "your goal here"[/cyan]
        """
        console.print(Panel(success_text, border_style="green"))

        # Show configured providers table
        if self.configured_providers:
            table = Table(title="Configured Providers", show_header=True, header_style="bold")
            table.add_column("Provider", style="cyan")
            table.add_column("Models", style="green")
            table.add_column("Status", style="bold")

            # Group models by provider
            provider_models: dict[str, list[str]] = {}
            for model in self.configured_models:
                provider = model.split("/")[0]
                if provider not in provider_models:
                    provider_models[provider] = []
                provider_models[provider].append(model)

            for provider in self.configured_providers:
                provider_lower = provider.lower().replace(" ", "")
                models = provider_models.get(provider_lower, [])
                table.add_row(
                    provider,
                    f"{len(models)} models",
                    "✅"
                )

            console.print(table)

        console.print(f"\n[dim]Configuration saved to: {self.config_path}[/dim]")

    async def run(self) -> bool:
        """Run the interactive setup wizard."""
        try:
            # Show welcome
            self._show_welcome()

            # Load existing config
            has_existing = self._load_existing_config()

            if has_existing and self.existing_config:
                # Offer to update existing config
                update = Confirm.ask(
                    "Found existing configuration. Update it?",
                    default=True,
                )
                if not update:
                    console.print("[yellow]Setup cancelled[/yellow]")
                    return False

            # Define providers to configure
            providers = [
                {
                    "name": "OpenAI",
                    "env_var": "OPENAI_API_KEY",
                    "model_prefix": "openai/",
                    "config_name": "openai",
                },
                {
                    "name": "Anthropic",
                    "env_var": "ANTHROPIC_API_KEY",
                    "model_prefix": "anthropic/",
                    "config_name": "anthropic",
                },
                {
                    "name": "Google AI",
                    "env_var": "GOOGLE_API_KEY",
                    "model_prefix": "google/",
                    "config_name": "google",
                },
                {
                    "name": "DeepSeek",
                    "env_var": "DEEPSEEK_API_KEY",
                    "model_prefix": "deepseek/",
                    "config_name": "deepseek",
                },
            ]

            # Configure each provider
            for provider in providers:
                api_key = self._ask_for_api_key(provider["name"], provider["env_var"])
                if api_key:
                    success, models = await self._test_connection(
                        provider_name=provider["name"],
                        api_key=api_key,
                        env_var=provider["env_var"],
                        model_prefix=provider["model_prefix"]
                    )
                    if success:
                        self._configure_provider(
                            provider_name=provider["config_name"],
                            api_key=api_key,
                            models=models
                        )
                    else:
                        retry = Confirm.ask(
                            "Connection failed. Try again with a different key?",
                            default=False,
                        )
                        if retry:
                            api_key = self._ask_for_api_key(provider["name"], provider["env_var"])
                            if api_key:
                                success, models = await self._test_connection(
                                    provider_name=provider["name"],
                                    api_key=api_key,
                                    env_var=provider["env_var"],
                                    model_prefix=provider["model_prefix"]
                                )
                                if success:
                                    self._configure_provider(
                                        provider_name=provider["config_name"],
                                        api_key=api_key,
                                        models=models
                                    )

            # Configure local models
            self._configure_local_models()

            # Set defaults if we have providers
            if self.configured_providers:
                # Set default provider to first configured provider
                first_provider = self.configured_providers[0].lower().replace(" ", "")
                self.new_config["defaults"] = {
                    "provider": first_provider,
                    "model": self.configured_models[0] if self.configured_models else "openai/gpt-4o-mini",
                    "temperature": 0.7,
                    "max_tokens": 1000,
                    "timeout": 30,
                }

                # Set budget defaults
                self.new_config["budget"] = {
                    "daily_limit": 10.00,
                    "per_session_limit": 2.00,
                    "warning_threshold": 0.8,
                    "hard_limit": True,
                }

                # Set rate limiting defaults
                self.new_config["rate_limiting"] = {
                    "enabled": True,
                    "requests_per_minute": 60,
                    "tokens_per_minute": 150000,
                    "burst_capacity": 10,
                }

            # Save configuration
            if self.configured_providers:
                success = self._save_config()
                if success:
                    self._show_success_summary()
                    return True
                else:
                    console.print("[red]❌ Setup failed to save configuration[/red]")
                    return False
            else:
                console.print("[yellow]⚠️  No providers configured. Setup cancelled.[/yellow]")
                return False

        except KeyboardInterrupt:
            console.print("\n[yellow]Setup cancelled by user[/yellow]")
            return False
        except Exception as e:
            console.print(f"[red]❌ Setup failed with error: {e}[/red]")
            return False


@click.command()
def setup() -> None:
    """Interactive setup wizard for Omni-LLM."""
    wizard = SetupWizard()
    success = asyncio.run(wizard.run())

    if not success:
        sys.exit(1)
