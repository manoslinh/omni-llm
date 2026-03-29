"""
Omni-LLM CLI Entry Point.

Main CLI interface for the Omni-LLM tool.
"""

import asyncio
import logging
import sys

import click

from ..models.litellm_provider import LiteLLMProvider
from ..models.mock_provider import MockProvider
from ..models.provider import Message, MessageRole, ModelProvider
from ..observability.cli import register_execute_command

# Import orchestration modules for new commands
try:
    from ..orchestration import WorkflowEngine
    from ..router import ModelRouter
    from ..coordination import CoordinationEngine
    from ..decomposition import TaskDecompositionEngine
    ORCHESTRATION_AVAILABLE = True
except ImportError:
    ORCHESTRATION_AVAILABLE = False
    WorkflowEngine = None
    ModelRouter = None
    CoordinationEngine = None
    TaskDecompositionEngine = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@click.group()
@click.version_option()
def cli() -> None:
    """Omni-LLM: The orchestration OS for AI-assisted development."""
    pass


@cli.command()
@click.argument("prompt")
@click.option("--model", "-m", default="openai/gpt-3.5-turbo", help="Model to use")
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


@cli.command()
def models() -> None:
    """List available models."""
    asyncio.run(_list_models_async())


@cli.command()
def status() -> None:
    """Show system status and configuration."""
    click.echo("Omni-LLM Status")
    click.echo("===============")
    click.echo(f"Python: {sys.version}")
    click.echo(f"Platform: {sys.platform}")

    # Check for API keys
    import os
    keys = {
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
        "ANTHROPIC_API_KEY": bool(os.getenv("ANTHROPIC_API_KEY")),
        "GOOGLE_API_KEY": bool(os.getenv("GOOGLE_API_KEY")),
        "DEEPSEEK_API_KEY": bool(os.getenv("DEEPSEEK_API_KEY")),
    }

    click.echo("\nAPI Keys:")
    for key, present in keys.items():
        status = "✅" if present else "❌"
        click.echo(f"  {status} {key}")

    # Check orchestration availability
    click.echo("\nOrchestration Features:")
    if ORCHESTRATION_AVAILABLE:
        click.echo("  ✅ Multi-agent orchestration available")
        click.echo("  ✅ Workflow templates available")
        click.echo("  ✅ Model routing available")
    else:
        click.echo("  ⚠️  Orchestration features not installed")
        click.echo("     Install with: pip install -e '.[orchestration]'")


@cli.command()
@click.argument("goal")
@click.option("--budget", "-b", type=float, help="Maximum cost in dollars")
@click.option("--timeout", "-t", type=int, default=3600, help="Timeout in seconds")
@click.option("--max-agents", type=int, default=5, help="Maximum number of agents to use")
@click.option("--dry-run", is_flag=True, help="Plan without executing")
def orchestrate(goal: str, budget: float | None, timeout: int, max_agents: int, dry_run: bool) -> None:
    """Run multi-agent orchestration for a goal."""
    if not ORCHESTRATION_AVAILABLE:
        click.echo("❌ Orchestration features not available")
        click.echo("Install with: pip install -e '.[orchestration]'")
        return

    asyncio.run(_orchestrate_async(goal, budget, timeout, max_agents, dry_run))


@cli.command()
@click.argument("template", type=click.Path(exists=True))
@click.option("--variables", "-v", help="JSON string of variables")
@click.option("--var-file", type=click.Path(exists=True), help="JSON file with variables")
@click.option("--dry-run", is_flag=True, help="Show execution plan without running")
def workflow(template: str, variables: str | None, var_file: str | None, dry_run: bool) -> None:
    """Execute a workflow template."""
    if not ORCHESTRATION_AVAILABLE:
        click.echo("❌ Orchestration features not available")
        click.echo("Install with: pip install -e '.[orchestration]'")
        return

    asyncio.run(_workflow_async(template, variables, var_file, dry_run))


@cli.command()
@click.option("--detailed", "-d", is_flag=True, help="Show detailed routing information")
def router(detailed: bool) -> None:
    """Show current routing strategy and costs."""
    if not ORCHESTRATION_AVAILABLE:
        click.echo("❌ Orchestration features not available")
        click.echo("Install with: pip install -e '.[orchestration]'")
        return

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


async def _orchestrate_async(goal: str, budget: float | None, timeout: int, max_agents: int, dry_run: bool) -> None:
    """Async implementation of the orchestrate command."""
    try:
        click.echo("🚀 Multi-Agent Orchestration")
        click.echo("=" * 50)
        click.echo(f"Goal: {goal}")
        
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
        task_graph = decomposer.decompose(goal)
        click.echo(f"   Created {task_graph.size} subtasks")
        click.echo(f"   Dependencies: {task_graph.dependency_count}")
        
        click.echo("\n2. Coordinating agents...")
        result = await coordinator.coordinate(
            task_graph,
            budget=budget,
            max_agents=max_agents,
        )
        
        click.echo(f"   Agents assigned: {result.total_agents_used}")
        click.echo(f"   Estimated cost: ${result.estimated_total_cost:.4f}")
        click.echo(f"   Estimated time: {result.estimated_total_time:.1f}s")
        
        if dry_run:
            click.echo("\n✅ Dry run complete. Execution plan ready.")
            click.echo("   Run without --dry-run to execute.")
            return
        
        click.echo("\n3. Executing workflow...")
        click.echo("   (Execution would happen here)")
        click.echo("\n✅ Orchestration planning complete!")
        
        # Show execution plan
        plan = result.plan
        waves = plan.get_execution_order()
        click.echo(f"\n📋 Execution Plan ({len(waves)} waves):")
        for i, wave in enumerate(waves, 1):
            click.echo(f"   Wave {i}: {len(wave)} parallel steps")
        
        await coordinator.close()
        
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        logger.exception("Orchestration failed")
        sys.exit(1)


async def _workflow_async(template: str, variables: str | None, var_file: str | None, dry_run: bool) -> None:
    """Async implementation of the workflow command."""
    try:
        import json
        from pathlib import Path
        
        click.echo("📋 Workflow Execution")
        click.echo("=" * 50)
        click.echo(f"Template: {template}")
        
        # Parse variables
        vars_dict = {}
        if variables:
            vars_dict = json.loads(variables)
            click.echo(f"Variables: {json.dumps(vars_dict, indent=2)}")
        
        if var_file:
            with open(var_file, 'r') as f:
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
        
        # Create execution plan
        click.echo("\n3. Creating execution plan...")
        plan = engine.create_execution_plan(workflow_template, vars_dict)
        
        # Show which steps will execute
        active_steps = [s for s in workflow_template.steps if plan.is_step_active(s.name)]
        click.echo(f"   Active steps: {len(active_steps)}")
        
        # Show execution order
        waves = plan.get_execution_order()
        click.echo(f"   Execution waves: {len(waves)}")
        
        for i, wave in enumerate(waves, 1):
            click.echo(f"   Wave {i}: {len(wave)} steps")
            for step_id in wave[:3]:  # Show first 3 steps per wave
                step = workflow_template.get_step(step_id)
                if step:
                    click.echo(f"     • {step.name} ({step.task_type})")
            if len(wave) > 3:
                click.echo(f"     ... and {len(wave) - 3} more")
        
        if dry_run:
            click.echo("\n✅ Dry run complete. Execution plan ready.")
            click.echo("   Run without --dry-run to execute.")
            return
        
        click.echo("\n4. Executing workflow...")
        click.echo("   (Execution would happen here)")
        
        # Simulate execution for demo
        click.echo("\n🏗️  Simulating workflow execution...")
        for i, wave in enumerate(waves, 1):
            click.echo(f"   Executing wave {i}...")
            for step_id in wave:
                step = workflow_template.get_step(step_id)
                if step:
                    click.echo(f"     • {step.name}: ✅")
        
        click.echo("\n✅ Workflow execution complete!")
        
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
        click.echo("🔄 Model Router Status")
        click.echo("=" * 50)
        
        # Create router
        router = ModelRouter()
        
        # Get router statistics
        stats = router.get_statistics()
        
        click.echo(f"Router Strategy: {router.strategy.__class__.__name__}")
        click.echo(f"Total Decisions: {stats.total_decisions}")
        click.echo(f"Models Available: {stats.models_available}")
        click.echo(f"Avg Decision Time: {stats.avg_decision_time_ms:.1f}ms")
        
        if detailed:
            click.echo("\n📊 Detailed Routing Information:")
            click.echo("-" * 40)
            
            # Get available models (simplified for demo)
            try:
                from ..models.litellm_provider import LiteLLMProvider
                provider = LiteLLMProvider()
                models = provider.list_models()
                
                # Group by provider
                by_provider = {}
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
        
        from omni.task.models import Task, TaskType, ComplexityEstimate
        
        sample_tasks = [
            ("Simple formatting", TaskType.CONFIGURATION, 1),
            ("Code generation", TaskType.CODE_GENERATION, 5),
            ("Code review", TaskType.CODE_REVIEW, 4),
            ("Architecture design", TaskType.ANALYSIS, 8),
        ]
        
        for name, task_type, complexity in sample_tasks:
            task = Task(
                description=name,
                task_type=task_type,
                complexity=ComplexityEstimate(
                    code_complexity=complexity,
                    integration_complexity=complexity,
                    testing_complexity=complexity,
                    unknown_factor=complexity // 2,
                    reasoning=f"Sample {name} task",
                ),
            )
            
            try:
                model = await router.select_model(task)
                cost = await router.estimate_cost(task, model)
                click.echo(f"  {name:25} → {model:30} ${cost:.6f}")
            except:
                click.echo(f"  {name:25} → (unavailable)")
        
        click.echo("\n✅ Router status displayed successfully!")
        
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        logger.exception("Router status failed")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    # Register execute command group
    register_execute_command(cli)
    cli()


if __name__ == "__main__":
    main()
