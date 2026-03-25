#!/usr/bin/env python3
"""Test the actual EditLoop code for mutable default argument bug."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import after adding to path
from omni.core.edit_loop import EditLoop
from omni.models.mock_provider import MockProvider

# Create two EditLoop instances without passing verifiers
print("Testing actual EditLoop code...")
print()

# First instance
provider1 = MockProvider()
loop1 = EditLoop(model_provider=provider1)
print(f"loop1.verifiers: {loop1.verifiers}")
print(f"loop1.verifiers id: {id(loop1.verifiers)}")
print(f"loop1.verifiers[0] id: {id(loop1.verifiers[0])}")

print()

# Second instance  
provider2 = MockProvider()
loop2 = EditLoop(model_provider=provider2)
print(f"loop2.verifiers: {loop2.verifiers}")
print(f"loop2.verifiers id: {id(loop2.verifiers)}")
print(f"loop2.verifiers[0] id: {id(loop2.verifiers[0])}")

print()

# Check if they're the same object
print(f"Same verifiers list object? {loop1.verifiers is loop2.verifiers}")
print(f"Same NoOpVerifier object? {loop1.verifiers[0] is loop2.verifiers[0]}")

print()

# Test modifying one
print("Testing modification...")
original_length = len(loop1.verifiers)
loop1.verifiers.append("TEST_ITEM")
print(f"After appending to loop1.verifiers:")
print(f"  loop1.verifiers length: {len(loop1.verifiers)} (was {original_length})")
print(f"  loop2.verifiers length: {len(loop2.verifiers)}")

if len(loop2.verifiers) > original_length:
    print("  ⚠️  BUG! loop2.verifiers was also modified!")
else:
    print("  ✓ OK! loop2.verifiers was not affected.")

print()

# Also test with explicit None
print("Testing with explicit verifiers=None...")
loop3 = EditLoop(model_provider=MockProvider(), verifiers=None)
print(f"loop3.verifiers: {loop3.verifiers}")
print(f"Same as default? {loop3.verifiers == [type(loop1.verifiers[0])()]}")