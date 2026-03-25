"""
Omni-LLM CLI Entry Point.

Main CLI interface for the Omni-LLM tool.
"""

import asyncio
import logging
import sys
from typing import Optional

import click

from ..models.provider import Message, MessageRole
from ..models.litellm_provider import LiteLLMProvider
from ..models.mock_provider import MockProvider


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@click.group()
@click.version_option()
def cli():
    """Omni-LLM: The orchestration OS for AI-assisted development."""
    pass


@cli.command()
@click.argument("prompt")
@click.option("--model", "-m", default="openai/gpt-3.5-turbo", help="Model to use")
@click.option("--temperature", "-t", default=0.7, type=float, help="Temperature (0.0-2.0)")
@click.option("--max-tokens", type=int, help="Maximum tokens to generate")
@click.option("--mock", is_flag=True, help="Use mock provider for testing")
def run(prompt: str, model: str, temperature: float, max_tokens: Optional[int], mock: bool):
    """Run a single prompt through the model."""
    asyncio.run(_run_async(prompt, model, temperature, max_tokens, mock))


@cli.command()
def config():
    """Configure Omni-LLM settings."""
    click.echo("Configuration management coming soon!")
    click.echo("For now, set environment variables:")
    click.echo("  - OPENAI_API_KEY")
    click.echo("  - ANTHROPIC_API_KEY")
    click.echo("  - GOOGLE_API_KEY")
    click.echo("  - DEEPSEEK_API_KEY")


@cli.command()
def models():
    """List available models."""
    asyncio.run(_list_models_async())


@cli.command()
def status():
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


async def _run_async(
    prompt: str,
    model: str,
    temperature: float,
    max_tokens: Optional[int],
    mock: bool
):
    """Async implementation of the run command."""
    try:
        # Create provider
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
        click.echo(f"\n📊 Usage:")
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


async def _list_models_async():
    """Async implementation of the models command."""
    try:
        # Try LiteLLM first
        provider = LiteLLMProvider()
        models = provider.list_models()
        
        click.echo("Available models via LiteLLM:")
        click.echo("=" * 50)
        
        # Group by provider
        by_provider = {}
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


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()