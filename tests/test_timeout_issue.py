#!/usr/bin/env python3
"""Test to reproduce the timeout issue with RuntimeWarning."""

import asyncio
import warnings


async def test_timeout_issue():
    """Reproduce the coroutine never awaited issue."""
    # Enable all warnings
    warnings.simplefilter("always")

    # Create a subprocess that will timeout
    process = await asyncio.create_subprocess_exec(
        "sleep", "10",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    print("Created subprocess, waiting with timeout...")

    try:
        # This is the problematic code - process.communicate() returns a coroutine
        # If wait_for times out, it cancels the coroutine but doesn't await it
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),  # Returns a coroutine
            timeout=0.1  # Very short timeout
        )
    except TimeoutError:
        print("Timeout occurred (as expected)")
        process.kill()
        await process.wait()
        print("Process killed")
        # The coroutine returned by process.communicate() was cancelled
        # but never awaited, causing RuntimeWarning

    print("Test complete")

if __name__ == "__main__":
    asyncio.run(test_timeout_issue())
    print("\nIf you see 'RuntimeWarning: coroutine was never awaited' above, the issue is reproduced.")
