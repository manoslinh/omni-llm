#!/usr/bin/env python3
"""
Example script demonstrating the new 'omni models add' and 'omni models status' commands.

This script shows how to use the new CLI commands programmatically.
"""

import json
import subprocess
from pathlib import Path


def run_command(cmd):
    """Run a command and return output."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def main():
    print("=== Omni-LLM Models Command Demo ===\n")

    # 1. Show current models
    print("1. Listing current models:")
    print("=" * 50)
    code, out, err = run_command("python3 -m src.omni.cli.main models list")
    if code == 0:
        print(out)
    else:
        print(f"Error: {err}")

    # 2. Show current status
    print("\n2. Showing current model status:")
    print("=" * 50)
    code, out, err = run_command("python3 -m src.omni.cli.main models status")
    if code == 0:
        # Show first few lines
        lines = out.split('\n')[:20]
        print('\n'.join(lines))
        if len(out.split('\n')) > 20:
            print("... (output truncated)")
    else:
        print(f"Error: {err}")

    # 3. Demonstrate how to add a custom provider (commented out as it would modify config)
    print("\n3. Example of adding a custom provider (commented out):")
    print("=" * 50)

    example_config = {
        "base_url": "http://localhost:8080",
        "timeout": 30,
        "max_retries": 3
    }

    example_models = {
        "custom/llama-3-70b": {
            "max_tokens": 8192,
            "temperature_range": [0.0, 1.0],
            "supports_functions": True
        },
        "custom/mistral-8x7b": {
            "max_tokens": 32768,
            "temperature_range": [0.0, 2.0],
            "supports_tools": True
        }
    }

    print("Command would be:")
    print('  omni models add custom-llm-provider \\')
    print('    --type litellm \\')
    print('    --description "Custom LLM provider for local models" \\')
    print(f'    --config \'{json.dumps(example_config)}\' \\')
    print(f'    --models-json \'{json.dumps(example_models)}\'')

    # 4. Show detailed status for a specific model
    print("\n4. Example of checking status for a specific model:")
    print("=" * 50)
    print("Command would be:")
    print('  omni models status openai/gpt-4 --detailed')

    print("\n=== Demo Complete ===")
    print("\nNew commands available:")
    print("  • omni models list      - List available models")
    print("  • omni models add       - Add custom model/provider")
    print("  • omni models status    - Show detailed model status")
    print("\nFor more information:")
    print("  omni models --help")
    print("  omni models add --help")
    print("  omni models status --help")


if __name__ == "__main__":
    main()
