#!/usr/bin/env python3
"""Test for mutable default argument issue."""

import sys

sys.path.insert(0, 'src')



# Mock classes for testing
class Verifier:
    def __init__(self, name="Test"):
        self.name = name

    def __repr__(self):
        return f"Verifier({self.name})"

class NoOpVerifier(Verifier):
    def __init__(self):
        super().__init__("NoOp")

# Test 1: Current implementation (parameter default is None)
class EditLoopCurrent:
    def __init__(
        self,
        verifiers: list[Verifier] | None = None,  # None as default
        max_reflections: int = 3,
    ):
        self.verifiers = verifiers or [NoOpVerifier()]
        self.max_reflections = max_reflections

# Test 2: Buggy implementation (parameter default is mutable list)
class EditLoopBuggy:
    def __init__(
        self,
        verifiers: list[Verifier] | None = [NoOpVerifier()],  # Mutable default - BUG!
        max_reflections: int = 3,
    ):
        self.verifiers = verifiers
        self.max_reflections = max_reflections

print("Testing mutable default argument issue...")
print()

# Test current implementation
print("1. Testing CURRENT implementation (default=None):")
loop1a = EditLoopCurrent()
loop1b = EditLoopCurrent()
print(f"  loop1a.verifiers: {loop1a.verifiers}")
print(f"  loop1b.verifiers: {loop1b.verifiers}")
print(f"  Same list object? {loop1a.verifiers is loop1b.verifiers}")
print(f"  Same NoOpVerifier object? {loop1a.verifiers[0] is loop1b.verifiers[0]}")
print()

# Test buggy implementation
print("2. Testing BUGGY implementation (default=[NoOpVerifier()]):")
loop2a = EditLoopBuggy()
loop2b = EditLoopBuggy()
print(f"  loop2a.verifiers: {loop2a.verifiers}")
print(f"  loop2b.verifiers: {loop2b.verifiers}")
print(f"  Same list object? {loop2a.verifiers is loop2b.verifiers}")
print(f"  Same NoOpVerifier object? {loop2a.verifiers[0] is loop2b.verifiers[0]}")
print()

# Demonstrate the bug
print("3. Demonstrating the bug:")
loop3a = EditLoopBuggy()
loop3b = EditLoopBuggy()
print("  Before modification:")
print(f"    loop3a.verifiers: {loop3a.verifiers}")
print(f"    loop3b.verifiers: {loop3b.verifiers}")

# Modify loop3a's verifiers
loop3a.verifiers.append(Verifier("Extra"))
print("  After appending to loop3a.verifiers:")
print(f"    loop3a.verifiers: {loop3a.verifiers}")
print(f"    loop3b.verifiers: {loop3b.verifiers}  <-- OOPS! Also modified!")
print()

print("Conclusion: Using mutable default arguments is a bug because")
print("all instances share the same default object.")
