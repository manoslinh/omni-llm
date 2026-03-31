"""
Omni-LLM CLI Entry Point.

Main CLI interface for the Omni-LLM tool.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import click
import yaml

from ..coordination import CoordinationEngine
from ..decomposition import TaskDecompositionEngine
from ..models.litellm_provider import LiteLLMProvider
from ..models.mock_provider import MockProvider
from ..models.provider import Message, MessageRole, ModelProvider
from ..observability.cli import register_execute_command
from ..orchestration import WorkflowEngine
from ..providers.config import (
    DEFAULT_PROVIDERS_CONFIG_PATH,
    ConfigLoader,
    ProviderConfig,
)
from ..task.models import Task, TaskType
from .demo import run_demo

# Import setup wizard (optional dependency on 'rich')
SETUP_AVAILABLE = False
setup_command: click.Command | None = None
try:
    from .setup import setup as setup_fn
    SETUP_AVAILABLE = True
    setup_command = setup_fn
except ImportError:
    pass

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
# Suppress verbose LiteLLM logging
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _auto_detect_providers() -> dict[str, str]:
    """Detect available LLM providers from environment variables.

    Returns a mapping of provider name to the environment variable name
    that contains its API key.
    """
    detected: dict[str, str] = {}
    env_mappings = {
        "OPENAI_API_KEY": "openai",
        "ANTHROPIC_API_KEY": "anthropic",
        "GOOGLE_API_KEY": "google",
        "DEEPSEEK_API_KEY": "deepseek",
        "MISTRAL_API_KEY": "mistral",
        "COHERE_API_KEY": "cohere",
    }
    for env_var, provider_name in env_mappings.items():
        if os.environ.get(env_var):
            detected[provider_name] = env_var
    return detected


@click.group()
@click.version_option(package_name="omni-llm")
def cli() -> None:
    """Omni-LLM: The orchestration OS for AI-assisted development."""
    pass


@cli.command()
@click.argument("prompt")
@click.option("--model", "-m", default="openai/gpt-4o-mini", help="Model to use")
@click.option("--temperature", "-t", default=0.7, type=float, help="Temperature (0.0-2.0)")
@click.option("--max-tokens", type=int, help="Maximum tokens to generate")
@click.option("--mock", is_flag=True, help="Use mock provider for testing")
def run(prompt: str, model: str, temperature: float, max_tokens: int | None, mock: bool) -> None:
    """Run a single prompt through the model."""
    asyncio.run(_run_async(prompt, model, temperature, max_tokens, mock))


@cli.command()
def config() -> None:
    """Configure Omni-LLM settings."""
    click.echo("Configuration management coming soon!")
    click.echo("For now, set environment variables:")
    click.echo("  - OPENAI_API_KEY")
    click.echo("  - ANTHROPIC_API_KEY")
    click.echo("  - GOOGLE_API_KEY")
    click.echo("  - DEEPSEEK_API_KEY")
    click.echo("\nOr use the interactive setup wizard:")
    click.echo("  omni setup")


@cli.command()
def setup() -> None:
    """Interactive setup wizard for Omni-LLM."""
    if not SETUP_AVAILABLE or setup_command is None:
        click.echo("❌ Setup wizard not available")
        click.echo("Make sure rich is installed: pip install rich")
        return

    # Invoke the setup command via Click context to avoid sys.argv re-reading
    ctx = click.Context(setup_command)
    ctx.invoke(setup_command)


@cli.command()
@click.option("--fast", "-f", is_flag=True, help="Run demo in fast mode (no delays)")
@click.option("--silent", "-s", is_flag=True, help="Run without explanations")
@click.option("--scenario", type=click.Choice(["build_web_app", "debug_complex_issue", "analyze_codebase", "custom_task"]),
              help="Specify scenario to run")
def demo(fast: bool, silent: bool, scenario: str | None) -> None:
    """Interactive demo of multi-agent orchestration."""
    try:
        run_demo(fast=fast, silent=silent, scenario=scenario)
    except KeyboardInterrupt:
        click.echo("\nDemo cancelled by user")
    except Exception as e:
        click.echo(f"❌ Demo failed: {e}")
        raise


@cli.group()
def models() -> None:
    """Manage models and providers."""
    pass


@models.command(name="list")
def models_list() -> None:
    """List available models."""
    asyncio.run(_list_models_async())


@models.command(name="add")
@click.argument("name")
@click.option("--type", "-t", required=True, help="Provider type (e.g., litellm, mock)")
@click.option("--description", "-d", default="", help="Provider description")
@click.option("--enabled/--disabled", default=True, help="Enable or disable the provider")
@click.option("--config", "-c", help="JSON configuration for the provider")
@click.option("--models-json", "-m", help="JSON models configuration")
@click.option("--config-file", "-f", type=click.Path(exists=True), help="YAML configuration file")
@click.option("--force", "-F", is_flag=True, help="Force overwrite without confirmation prompt")
def models_add(
    name: str,
    type: str,
    description: str,
    enabled: bool,
    config: str | None,
    models_json: str | None,
    config_file: str | None,
    force: bool,
) -> None:
    """Add a custom model provider."""
    asyncio.run(_add_model_async(name, type, description, enabled, config, models_json, config_file, force))


@models.command(name="status")
@click.argument("query", required=False)
@click.option("--provider", "-p", help="Search by provider name instead of model name")
@click.option("--detailed", "-d", is_flag=True, help="Show detailed information")
def models_status(query: str | None, provider: str | None, detailed: bool) -> None:
    """Show detailed model status and information.

    If QUERY is provided, searches for matching model names.
    Use --provider to search by provider name instead.
    """
    asyncio.run(_model_status_async(query, provider, detailed))


@cli.command()
def status() -> None:
    """Show system status and configuration."""
    click.echo("Omni-LLM Status")
    click.echo("===============")
    click.echo(f"Python: {sys.version}")
    click.echo(f"Platform: {sys.platform}")

    # Detect providers from environment
    detected = _auto_detect_providers()

    # Also check common keys that might not map to a detected provider
    all_env_keys = {
        "OPENAI_API_KEY": "openai",
        "ANTHROPIC_API_KEY": "anthropic",
        "GOOGLE_API_KEY": "google",
        "DEEPSEEK_API_KEY": "deepseek",
        "MISTRAL_API_KEY": "mistral",
        "COHERE_API_KEY": "cohere",
    }

    click.echo("\nAPI Keys:")
    for env_var, provider_name in all_env_keys.items():
        present = provider_name in detected
        indicator = "✅" if present else "❌"
        click.echo(f"  {indicator} {env_var}")

    if detected:
        click.echo(f"\nDetected providers: {', '.join(sorted(detected.keys()))}")
    else:
        click.echo("\nNo API keys detected in environment.")
        click.echo("Run `omni setup` to configure providers, or set environment variables.")

    # Orchestration features are always available (part of the package)
    click.echo("\nOrchestration Features:")
    click.echo("  ✅ Multi-agent orchestration available")
    click.echo("  ✅ Workflow templates available")
    click.echo("  ✅ Model routing available")


@cli.command()
@click.argument("goal")
@click.option("--model", "-m", default=None, help="Model to use (e.g., ollama/llama3, deepseek/deepseek-chat)")
@click.option("--budget", "-b", type=float, help="Maximum cost in dollars")
@click.option("--timeout", "-t", type=int, default=3600, help="Timeout in seconds")
@click.option("--max-agents", type=int, default=5, help="Maximum number of agents to use")
@click.option("--dry-run", is_flag=True, help="Plan without executing")
def orchestrate(goal: str, model: str | None, budget: float | None, timeout: int, max_agents: int, dry_run: bool) -> None:
    """Run multi-agent orchestration for a goal."""
    detected = _auto_detect_providers()
    if not detected:
        click.echo("No API keys found. Running in demo mode with mock provider.")
        click.echo("Run `omni setup` to connect real AI models.\n")

    asyncio.run(_orchestrate_async(goal, model, budget, timeout, max_agents, dry_run))


@cli.command()
@click.argument("template", type=click.Path(exists=True))
@click.option("--model", "-m", default=None, help="Model to use (e.g., ollama/llama3, deepseek/deepseek-chat)")
@click.option("--variables", "-v", help="JSON string of variables")
@click.option("--var-file", type=click.Path(exists=True), help="JSON file with variables")
@click.option("--dry-run", is_flag=True, help="Show execution plan without running")
def workflow(template: str, model: str | None, variables: str | None, var_file: str | None, dry_run: bool) -> None:
    """Execute a workflow template."""
    detected = _auto_detect_providers()
    if not detected:
        click.echo("No API keys found. Running in demo mode with mock provider.")
        click.echo("Run `omni setup` to connect real AI models.\n")

    asyncio.run(_workflow_async(template, model, variables, var_file, dry_run))


@cli.command()
@click.option("--detailed", "-d", is_flag=True, help="Show detailed routing information")
def router(detailed: bool) -> None:
    """Show current routing strategy and costs."""
    detected = _auto_detect_providers()
    if not detected:
        click.echo("No API keys found. Running in demo mode with mock provider.")
        click.echo("Run `omni setup` to connect real AI models.\n")

    asyncio.run(_router_async(detailed))


async def _run_async(
    prompt: str,
    model: str,
    temperature: float,
    max_tokens: int | None,
    mock: bool
) -> None:
    """Async implementation of the run command."""
    try:
        # Create provider
        provider: ModelProvider
        if mock:
            provider = MockProvider()
            click.echo("📦 Using mock provider (no API calls)")
        else:
            provider = LiteLLMProvider()
            click.echo(f"🚀 Using LiteLLM provider with model: {model}")

        # Create messages
        messages = [
            Message(role=MessageRole.SYSTEM, content="You are a helpful coding assistant."),
            Message(role=MessageRole.USER, content=prompt),
        ]

        click.echo(f"\n📤 Sending prompt ({len(prompt)} chars)...")

        # Get completion
        result = await provider.complete(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Show results
        click.echo("\n📥 Response:")
        click.echo("─" * 50)
        click.echo(result.content)
        click.echo("─" * 50)

        # Show usage
        click.echo("\n📊 Usage:")
        click.echo(f"  Model: {result.model}")
        click.echo(f"  Input tokens: {result.usage.prompt_tokens}")
        click.echo(f"  Output tokens: {result.usage.completion_tokens}")
        click.echo(f"  Total tokens: {result.usage.total_tokens}")

        # Estimate cost
        cost = provider.estimate_cost(
            result.usage.prompt_tokens,
            result.usage.completion_tokens,
            result.model
        )
        click.echo(f"  Estimated cost: ${cost:.6f}")

        # Clean up
        await provider.close()

    except ImportError as e:
        click.echo(f"❌ Error: {e}", err=True)
        click.echo("\nInstall missing dependencies:")
        click.echo("  pip install litellm")
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        logger.exception("Command failed")
        sys.exit(1)


async def _list_models_async() -> None:
    """Async implementation of the models command."""
    try:
        # Try LiteLLM first
        provider = LiteLLMProvider()
        models = provider.list_models()

        click.echo("Available models via LiteLLM:")
        click.echo("=" * 50)

        # Group by provider
        by_provider: dict[str, list[str]] = {}
        for model in models:
            provider_name = model.split("/")[0] if "/" in model else "unknown"
            if provider_name not in by_provider:
                by_provider[provider_name] = []
            by_provider[provider_name].append(model)

        for provider_name, provider_models in sorted(by_provider.items()):
            click.echo(f"\n{provider_name.upper()}:")
            for model in sorted(provider_models):
                click.echo(f"  • {model}")

        await provider.close()

    except ImportError:
        click.echo("LiteLLM not installed. Install with: pip install litellm")
        click.echo("\nMock models available:")
        mock_provider = MockProvider()
        for model in mock_provider.list_models():
            click.echo(f"  • {model}")
        await mock_provider.close()


async def _orchestrate_async(goal: str, model: str | None, budget: float | None, timeout: int, max_agents: int, dry_run: bool) -> None:
    """Async implementation of the orchestrate command."""
    try:
        click.echo("🚀 Multi-Agent Orchestration")
        click.echo("=" * 50)
        click.echo(f"Goal: {goal}")

        if model:
            click.echo(f"Model: {model}")
        else:
            click.echo("Model: auto (cost-optimized routing)")

        if budget:
            click.echo(f"Budget: ${budget:.4f}")
        click.echo(f"Timeout: {timeout}s")
        click.echo(f"Max agents: {max_agents}")

        if dry_run:
            click.echo("\n📋 Dry run mode - planning only")

        # Create coordination engine
        coordinator = CoordinationEngine()

        # Create decomposition engine
        decomposer = TaskDecompositionEngine()

        click.echo("\n1. Decomposing goal into tasks...")
        # Create a Task object from the goal string
        # The decomposition engine will estimate complexity if needed
        main_task = Task(
            description=goal,
            task_type=TaskType.CUSTOM,
            task_id="main"
        )

        decomposition_result = decomposer.decompose(main_task)
        click.echo(f"   Estimated complexity: {main_task.effective_complexity.overall_score:.1f}/10")
        click.echo(f"   Created {decomposition_result.total_subtasks} subtasks")
        click.echo(f"   Dependencies: {decomposition_result.task_graph.edge_count}")

        click.echo("\n2. Coordinating agents...")
        result = coordinator.coordinate(
            decomposition_result.task_graph,
        )

        click.echo(f"   Agents assigned: {result.total_agents_used}")
        click.echo(f"   Estimated cost: ${result.estimated_total_cost:.4f}")

        if dry_run:
            click.echo("\n✅ Dry run complete. Execution plan ready.")
            click.echo("   Run without --dry-run to execute.")
            return

        click.echo("\n3. Executing workflow...")
        if model:
            click.echo(f"   Model: {model}")
        else:
            click.echo("   Model: auto (cost-optimized routing)")
        click.echo("\n✅ Orchestration planning complete!")

        # Show execution plan
        plan = result.plan
        waves = plan.get_execution_order()
        click.echo(f"\n📋 Execution Plan ({len(waves)} waves):")
        for i, wave in enumerate(waves, 1):
            click.echo(f"   Wave {i}: {len(wave)} parallel steps")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        logger.exception("Orchestration failed")
        sys.exit(1)


async def _workflow_async(template: str, model: str | None, variables: str | None, var_file: str | None, dry_run: bool) -> None:
    """Async implementation of the workflow command."""
    try:
        import json

        click.echo("📋 Workflow Execution")
        click.echo("=" * 50)
        click.echo(f"Template: {template}")

        if model:
            click.echo(f"Model: {model}")
        else:
            click.echo("Model: auto (cost-optimized routing)")

        # Parse variables — initialize both dicts upfront to avoid NameError
        vars_dict: dict = {}
        file_vars: dict = {}

        if variables:
            vars_dict = json.loads(variables)
            click.echo(f"Variables: {json.dumps(vars_dict, indent=2)}")

        if var_file:
            with open(var_file) as f:
                file_vars = json.load(f)
            vars_dict.update(file_vars)
            click.echo(f"Variables from file: {json.dumps(file_vars, indent=2)}")

        # Create workflow engine
        engine = WorkflowEngine()

        click.echo("\n1. Loading template...")
        workflow_template = engine.load_template(template)
        click.echo(f"   Template: {workflow_template.name} v{workflow_template.version}")
        click.echo(f"   Description: {workflow_template.description}")
        click.echo(f"   Steps: {len(workflow_template.steps)}")

        # Validate template
        click.echo("\n2. Validating template...")
        errors = engine.validate_template(workflow_template)
        if errors:
            click.echo("❌ Validation errors:")
            for error in errors:
                click.echo(f"   - {error}")
            sys.exit(1)
        click.echo("   ✅ Template is valid")

        # Substitute variables and show execution plan
        click.echo("\n3. Creating execution plan...")
        try:
            substituted = workflow_template.substitute_variables(vars_dict)
        except ValueError as e:
            click.echo(f"❌ Error: {e}")
            click.echo("\nRequired variables for this template:")
            for var_name, var in workflow_template.variables.items():
                required = "required" if var.required else f"optional, default={var.default}"
                click.echo(f"  {var_name}: {var.description} ({required})")
            click.echo(f"\nUsage: omni workflow {template} -v '{{\"var_name\": \"value\"}}'")
            sys.exit(1)
        click.echo(f"   Steps after substitution: {len(substituted.steps)}")

        # Show execution order using template's own method
        waves = substituted.get_execution_order()
        click.echo(f"   Execution waves: {len(waves)}")

        # Build step lookup
        step_lookup = {s.name: s for s in substituted.steps}

        for i, wave in enumerate(waves, 1):
            click.echo(f"   Wave {i}: {len(wave)} steps")
            for step_id in wave[:3]:  # Show first 3 steps per wave
                step = step_lookup.get(step_id)
                if step:
                    click.echo(f"     • {step.name} ({step.task_type})")
            if len(wave) > 3:
                click.echo(f"     ... and {len(wave) - 3} more")

        if dry_run:
            click.echo("\n✅ Dry run complete. Execution plan ready.")
            click.echo("   Run without --dry-run to execute.")
            return

        click.echo("\n4. Executing workflow...")
        result = engine.execute(workflow_template, vars_dict)

        click.echo("\n✅ Workflow execution complete!")
        click.echo(f"   Success: {result.success}")
        click.echo(f"   Summary: {result.summary}")
        if result.warnings:
            for w in result.warnings:
                click.echo(f"   ⚠️  {w}")

    except json.JSONDecodeError as e:
        click.echo(f"❌ Invalid JSON: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        logger.exception("Workflow execution failed")
        sys.exit(1)


async def _router_async(detailed: bool) -> None:
    """Async implementation of the router command."""
    try:
        from ..router import (
            CostOptimizedStrategy,
            ModelRouter,
            RouterConfig,
            RoutingContext,
            TaskType,
        )

        click.echo("🔄 Model Router Status")
        click.echo("=" * 50)

        # Create router with cost-optimized strategy
        config = RouterConfig()
        router = ModelRouter(config)
        strategy = CostOptimizedStrategy()
        router.register_strategy("cost_optimized", strategy)

        click.echo("Strategy: cost_optimized")
        click.echo(f"Registered strategies: {list(config.strategies.keys())}")

        if detailed:
            click.echo("\n📊 Detailed Routing Information:")
            click.echo("-" * 40)

            # Get available models (simplified for demo)
            try:
                from ..models.litellm_provider import LiteLLMProvider
                provider = LiteLLMProvider()
                models = provider.list_models()

                # Group by provider
                by_provider: dict[str, list[str]] = {}
                for model in models:
                    provider_name = model.split("/")[0] if "/" in model else "unknown"
                    if provider_name not in by_provider:
                        by_provider[provider_name] = []
                    by_provider[provider_name].append(model)

                for provider_name, provider_models in sorted(by_provider.items()):
                    click.echo(f"\n{provider_name.upper()}:")
                    for model in sorted(provider_models)[:5]:  # Show first 5
                        click.echo(f"  • {model}")
                    if len(provider_models) > 5:
                        click.echo(f"  ... and {len(provider_models) - 5} more")

                await provider.close()

            except ImportError:
                click.echo("  (Detailed model list requires LiteLLM)")

        # Show cost estimates for common tasks
        click.echo("\n💰 Cost Estimates for Common Tasks:")
        click.echo("-" * 40)

        sample_tasks = [
            ("Simple formatting", TaskType.CODING, 0.2),
            ("Code generation", TaskType.CODING, 0.5),
            ("Code review", TaskType.CODE_REVIEW, 0.4),
            ("Architecture design", TaskType.ARCHITECTURE, 0.9),
        ]

        for name, task_type, complexity in sample_tasks:
            context = RoutingContext(
                task_type=task_type,
                file_count=3,
                complexity=complexity,
            )

            try:
                selection = router.select_model(
                    task_type=task_type,
                    context=context,
                    strategy_name="cost_optimized",
                )
                click.echo(
                    f"  {name:25} → {selection.model_id:30} "
                    f"${selection.estimated_cost.total_cost_usd:.6f}"
                )
            except Exception:
                click.echo(f"  {name:25} → (unavailable)")

        click.echo("\n✅ Router status displayed successfully!")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        logger.exception("Router status failed")
        sys.exit(1)


async def _add_model_async(
    name: str,
    type: str,
    description: str,
    enabled: bool,
    config: str | None,
    models_json: str | None,
    config_file: str | None,
    force: bool = False,
) -> None:
    """Async implementation of the models add command."""
    try:
        # Load existing configuration
        config_path = DEFAULT_PROVIDERS_CONFIG_PATH
        if not config_path.exists():
            click.echo(f"❌ Configuration file not found: {config_path}")
            click.echo("   Make sure you're in the correct directory or run 'omni setup' first.")
            sys.exit(1)

        # Load existing config
        loader = ConfigLoader()
        provider_config = loader.load_providers_config(config_path)

        # Check if provider already exists
        if name in provider_config.providers:
            if force:
                click.echo(f"⚠️  Provider '{name}' already exists. Overwriting due to --force flag.")
            else:
                click.echo(f"⚠️  Provider '{name}' already exists.")
                try:
                    if not click.confirm("Do you want to overwrite it?"):
                        click.echo("❌ Operation cancelled.")
                        sys.exit(1)
                except click.exceptions.Abort:
                    # Handle non-interactive mode (e.g., when piped or redirected)
                    click.echo("❌ Operation cancelled. Provider already exists.")
                    click.echo("   Use --force flag to overwrite without confirmation.")
                    sys.exit(1)

        # Parse configuration
        config_dict = {}
        if config:
            try:
                config_dict = json.loads(config)
            except json.JSONDecodeError as e:
                click.echo(f"❌ Invalid JSON configuration: {e}")
                sys.exit(1)

        # Parse models configuration
        models_dict = {}
        if models_json:
            try:
                models_dict = json.loads(models_json)
            except json.JSONDecodeError as e:
                click.echo(f"❌ Invalid JSON models configuration: {e}")
                sys.exit(1)

        # Load from config file if provided
        if config_file:
            try:
                with open(config_file) as f:
                    file_data = yaml.safe_load(f)
                if "config" in file_data:
                    config_dict.update(file_data["config"])
                if "models" in file_data:
                    models_dict.update(file_data["models"])
            except Exception as e:
                click.echo(f"❌ Error loading config file: {e}")
                sys.exit(1)

        # Create provider configuration
        provider = ProviderConfig(
            name=name,
            type=type,
            description=description,
            enabled=enabled,
            config=config_dict,
            models=models_dict,
        )

        # Add to configuration
        provider_config.providers[name] = provider

        # Save configuration
        loader.save_providers_config(provider_config, config_path)

        click.echo(f"✅ Provider '{name}' added successfully!")
        click.echo(f"   Type: {type}")
        click.echo(f"   Enabled: {enabled}")
        click.echo(f"   Models configured: {len(models_dict)}")
        click.echo(f"   Configuration saved to: {config_path}")

    except Exception as e:
        click.echo(f"❌ Error adding provider: {e}")
        logger.exception("Add model failed")
        sys.exit(1)


async def _model_status_async(query: str | None, provider_filter: str | None, detailed: bool) -> None:
    """Async implementation of the models status command."""
    try:
        # Load configuration
        config_path = DEFAULT_PROVIDERS_CONFIG_PATH
        if not config_path.exists():
            click.echo(f"❌ Configuration file not found: {config_path}")
            click.echo("   Make sure you're in the correct directory or run 'omni setup' first.")
            return

        loader = ConfigLoader()
        provider_config = loader.load_providers_config(config_path)

        # Also load models config for additional details
        models_config_path = config_path.parent / "models.yaml"
        models_config: dict[str, Any] = {}
        if models_config_path.exists():
            with open(models_config_path) as f:
                models_config = yaml.safe_load(f) or {}

        click.echo("📊 Model Status")
        click.echo("=" * 50)

        if provider_filter:
            # Show status for specific provider
            if provider_filter in provider_config.providers:
                provider = provider_config.providers[provider_filter]
                click.echo(f"\nProvider: {provider_filter}")
                click.echo(f"Type: {provider.type}")
                click.echo(f"Description: {provider.description}")
                click.echo(f"Enabled: {provider.enabled}")
                click.echo(f"Models: {len(provider.models)}")

                if provider.models:
                    click.echo("\nModels:")
                    for model_name in sorted(provider.models.keys()):
                        click.echo(f"  • {model_name}")

                if detailed and provider.config:
                    click.echo("\nConfiguration:")
                    for key, value in provider.config.items():
                        click.echo(f"  {key}: {value}")
            else:
                click.echo(f"❌ Provider '{provider_filter}' not found in configuration.")
                click.echo("   Available providers:")
                for provider_name in sorted(provider_config.providers.keys()):
                    click.echo(f"   • {provider_name}")

        elif query:
            # Show status for specific model (search by model name)
            found = False

            # Search across all providers
            for provider_name, provider in provider_config.providers.items():
                if query in provider.models:
                    found = True
                    click.echo(f"\nModel: {query}")
                    click.echo(f"Provider: {provider_name} ({provider.type})")
                    click.echo(f"Enabled: {provider.enabled}")

                    # Show model configuration
                    model_config = provider.models.get(query, {})
                    if model_config:
                        click.echo("\nConfiguration:")
                        for key, value in model_config.items():
                            click.echo(f"  {key}: {value}")

                    # Check cost configuration
                    cost_config = provider_config.get_model_cost(query)
                    if cost_config:
                        click.echo("\nCost (per million tokens):")
                        click.echo(f"  Input: ${cost_config.input_per_million:.2f}")
                        click.echo(f"  Output: ${cost_config.output_per_million:.2f}")

                    # Check in models.yaml for additional details
                    if models_config and "models" in models_config:
                        model_details = models_config["models"].get(query.split("/")[-1] if "/" in query else query)
                        if model_details:
                            click.echo("\nAdditional Details:")
                            for key, value in model_details.items():
                                if key not in ["provider", "model_id"]:
                                    click.echo(f"  {key}: {value}")
                    break

            if not found:
                # Also check if query matches a provider name
                if query in provider_config.providers:
                    click.echo(f"⚠️  '{query}' matches a provider name, not a model.")
                    click.echo(f"   Use 'omni models status --provider {query}' to view provider details.")
                else:
                    click.echo(f"❌ Model '{query}' not found in configuration.")
                    click.echo("   Use 'omni models list' to see available models.")
        else:
            # Show overall status
            click.echo(f"\nConfiguration File: {config_path}")
            click.echo(f"Total Providers: {len(provider_config.providers)}")
            click.echo(f"Total Models Configured: {sum(len(p.models) for p in provider_config.providers.values())}")

            # Show provider status
            click.echo("\nProviders:")
            for provider_name, provider in provider_config.providers.items():
                status = "✅" if provider.enabled else "❌"
                click.echo(f"  {status} {provider_name}: {provider.type} ({len(provider.models)} models)")
                if detailed:
                    click.echo(f"    Description: {provider.description}")

            # Show default settings
            if provider_config.defaults:
                click.echo("\nDefaults:")
                for key, value in provider_config.defaults.items():
                    click.echo(f"  {key}: {value}")

            # Show budget status
            click.echo("\nBudget:")
            click.echo(f"  Daily Limit: ${provider_config.budget.daily_limit:.2f}")
            click.echo(f"  Per Session Limit: ${provider_config.budget.per_session_limit:.2f}")

            # Show rate limiting
            if provider_config.rate_limiting.enabled:
                click.echo("\nRate Limiting:")
                click.echo(f"  Requests per minute: {provider_config.rate_limiting.requests_per_minute}")
                click.echo(f"  Tokens per minute: {provider_config.rate_limiting.tokens_per_minute}")

            if detailed:
                # Show API key status
                click.echo("\nAPI Keys:")
                for key_name, env_var in provider_config.api_keys.items():
                    if env_var.startswith("${") and env_var.endswith("}"):
                        env_var_name = env_var[2:-1]
                        value = os.getenv(env_var_name)
                        status = "✅" if value else "❌"
                        click.echo(f"  {status} {key_name}: {'Set' if value else 'Not set'}")

                # Show cost configurations
                if provider_config.cost_config:
                    click.echo(f"\nCost Configurations: {len(provider_config.cost_config)} models")
                    for model_id, cost in list(provider_config.cost_config.items())[:5]:  # Show first 5
                        click.echo(f"  {model_id}: ${cost.input_per_million:.2f} / ${cost.output_per_million:.2f}")
                    if len(provider_config.cost_config) > 5:
                        click.echo(f"  ... and {len(provider_config.cost_config) - 5} more")

        click.echo("\n✅ Status displayed successfully!")

    except Exception as e:
        click.echo(f"❌ Error showing status: {e}")
        logger.exception("Model status failed")
        sys.exit(1)


def _load_saved_api_keys() -> None:
    """Load API keys from saved config into environment variables."""
    config_path = Path.home() / ".config" / "omni" / "config.yaml"
    if not config_path.exists():
        return
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        if not config:
            return
        for key, value in config.get("api_keys", {}).items():
            if key not in os.environ and value:
                os.environ[key] = value
    except Exception:
        pass  # Don't fail CLI startup over config issues


def main() -> None:
    """Main entry point."""
    _load_saved_api_keys()
    # Register execute command group
    register_execute_command(cli)
    cli()


if __name__ == "__main__":
    main()
