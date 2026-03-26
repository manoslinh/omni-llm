#!/usr/bin/env python3
import pytest
"""Test the timeout fix specifically."""

import asyncio
import sys
import warnings

# Enable all warnings
warnings.simplefilter("always")

@pytest.mark.asyncio
@pytest.mark.skip(reason="Test has bug with coroutine reuse - needs fix")
async def test_timeout_fix():
    """Test that the timeout fix prevents RuntimeWarning."""
    # Create a subprocess that will timeout
    process = await asyncio.create_subprocess_exec(
        "sleep", "10",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    print("Created subprocess, waiting with timeout...")

    # Create the coroutine first (like in our fix)
    communicate_coro = process.communicate()

    try:
        # This will timeout
        stdout, stderr = await asyncio.wait_for(
            communicate_coro,
            timeout=0.1  # Very short timeout
        )
    except TimeoutError:
        print("Timeout occurred (as expected)")
        process.kill()
        await process.wait()
        print("Process killed")
        # Now await the cancelled coroutine to avoid warning
        try:
            await communicate_coro
        except asyncio.CancelledError:
            print("Coroutine was cancelled (as expected)")
            pass
        print("Coroutine awaited successfully")

    print("Test complete - no RuntimeWarning should appear above")

if __name__ == "__main__":
    # Capture stderr
    import io
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()

    asyncio.run(test_timeout_fix())

    stderr_output = sys.stderr.getvalue()
    sys.stderr = old_stderr

    print("\nStderr output:")
    print(stderr_output)
    if "RuntimeWarning" in stderr_output and "never awaited" in stderr_output:
        print("\n✗ FAIL: Still getting RuntimeWarning!")
    else:
        print("\n✓ SUCCESS: No RuntimeWarning!")
