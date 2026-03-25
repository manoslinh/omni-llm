#!/usr/bin/env python3
"""
Simple workflow example showing Omni-LLM in action.
"""

import asyncio

# Add src to path
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from omni.core.edit_applier import EditApplier
from omni.core.edit_loop import EditLoop
from omni.edits.editblock import EditBlockParser
from omni.models.mock_provider import MockProvider


async def main():
    """Run a simple edit workflow."""
    print("🚀 Omni-LLM Simple Workflow Example")
    print("=" * 50)

    # Create a temporary directory for our test
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Working directory: {tmpdir}")

        # Create a simple Python file to modify
        test_file = Path(tmpdir) / "example.py"
        test_file.write_text("""def greet(name):
    return f"Hello, {name}!"

print(greet("World"))
""")

        print(f"\n📄 Created test file: {test_file}")
        print("Initial content:")
        print(test_file.read_text())

        # Create components
        provider = MockProvider()
        parser = EditBlockParser()
        applier = EditApplier(base_path=tmpdir)

        # Create EditLoop
        edit_loop = EditLoop(
            model_provider=provider,
            edit_parser=parser,
            edit_applier=applier,
            base_path=tmpdir,
        )

        # Run an edit cycle
        print("\n🤖 Running edit cycle: 'Change greeting to uppercase'")

        result = await edit_loop.run_cycle(
            user_input="Change the greet function to return uppercase greeting",
            model="openai/gpt-4",
            files_to_include=["example.py"],
        )

        # Show results
        print("\n📊 Results:")
        print(f"  Success: {result.success}")
        print(f"  Cost: ${result.cost:.4f}")
        print(f"  Reflections: {result.reflections}")
        print(f"  Edits parsed: {len(result.edits)}")

        if result.verification.errors:
            print(f"  Errors: {result.verification.errors}")

        # Show modified file
        print("\n📄 Modified content:")
        print(test_file.read_text())

        # Clean up
        await edit_loop.close()
        await provider.close()

        print("\n✅ Example complete!")


if __name__ == "__main__":
    asyncio.run(main())
