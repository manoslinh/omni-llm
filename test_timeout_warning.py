#!/usr/bin/env python3
"""Test to verify timeout fix doesn't produce RuntimeWarning."""

import asyncio
import warnings
import tempfile
import os
from pathlib import Path

# Add the src directory to the path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from omni.core.verifiers.test_verifier import TestVerifier

async def test_timeout_no_warning():
    """Test that timeout doesn't produce RuntimeWarning."""
    # Capture warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        
        # Create a test file that will timeout
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_timeout.py"
            test_file.write_text("""
import time
def test_timeout():
    time.sleep(5)  # Will timeout
""")
            
            # Create verifier with very short timeout
            verifier = TestVerifier(
                name="timeout-test",
                test_dir=tmpdir,
                timeout=0.1  # Very short timeout
            )
            
            # Run verification
            result = await verifier.verify([str(test_file)])
            
            # Check for RuntimeWarning
            runtime_warnings = [warning for warning in w 
                              if issubclass(warning.category, RuntimeWarning) 
                              and "coroutine" in str(warning.message)]
            
            if runtime_warnings:
                print(f"FAIL: Found RuntimeWarning: {runtime_warnings[0].message}")
                return False
            else:
                print("PASS: No RuntimeWarning found")
                return True

if __name__ == "__main__":
    # Run the test
    success = asyncio.run(test_timeout_no_warning())
    sys.exit(0 if success else 1)