#!/usr/bin/env python3
"""Test to show the warning issue."""

import asyncio
import sys
import warnings

# Enable all warnings
warnings.simplefilter("always")

async def test():
    """Test that shows the warning."""
    # Create a subprocess
    process = await asyncio.create_subprocess_exec(
        "echo", "test",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Get the coroutine
    coro = process.communicate()
    print(f"Created coroutine: {coro}")

    # Don't await it - this should cause a warning when coro is garbage collected
    return

async def main():
    await test()
    # Force garbage collection
    import gc
    gc.collect()
    print("Garbage collection done")

if __name__ == "__main__":
    # Capture stderr
    import io
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()

    asyncio.run(main())

    stderr_output = sys.stderr.getvalue()
    sys.stderr = old_stderr

    print("\nStderr output:")
    print(stderr_output)
    if "RuntimeWarning" in stderr_output and "never awaited" in stderr_output:
        print("\n✓ Successfully reproduced the RuntimeWarning!")
    else:
        print("\n✗ Did not reproduce the warning")
