#!/usr/bin/env python3
import asyncio
import warnings

warnings.simplefilter("always")

async def main():
    process = await asyncio.create_subprocess_exec(
        "sleep", "1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    
    coro = process.communicate()
    
    try:
        await asyncio.wait_for(coro, timeout=0.01)
    except asyncio.TimeoutError:
        print("Timeout")
        process.kill()
        await process.wait()
        # Try to await the cancelled coroutine
        try:
            await coro
        except asyncio.CancelledError:
            print("Got CancelledError as expected")
    
    print("Done")

asyncio.run(main())