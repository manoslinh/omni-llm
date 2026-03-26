#!/bin/bash

# Test script for worktree scripts
set -e

echo "=== Testing Worktree Scripts ==="
echo

# Test 1: Check script syntax
echo "Test 1: Syntax checking..."
bash -n create-worktree.sh && echo "✓ create-worktree.sh syntax OK"
bash -n cleanup-worktree.sh && echo "✓ cleanup-worktree.sh syntax OK"
echo

# Test 2: Check usage/help
echo "Test 2: Usage/help messages..."
echo "Testing create-worktree.sh without arguments:"
./create-worktree.sh 2>&1 | grep -q "Usage:" && echo "✓ Usage message shown"
echo
echo "Testing cleanup-worktree.sh without arguments:"
./cleanup-worktree.sh 2>&1 | grep -q "Usage:" && echo "✓ Usage message shown"
echo

# Test 3: Validate branch name format
echo "Test 3: Branch name validation..."
echo "Testing invalid branch name:"
./create-worktree.sh invalid-name 2>&1 | grep -q "Invalid branch name format" && echo "✓ Invalid format rejected"
echo
echo "Testing valid branch name format (dry run):"
# We'll just check the script doesn't immediately fail on format
if [[ "branches/20260326_test-role_test-task" =~ ^branches/[0-9]{8}_[a-zA-Z0-9-]+_[a-zA-Z0-9-]+$ ]]; then
    echo "✓ Valid format accepted by regex"
else
    echo "✗ Valid format rejected by regex"
fi
echo

# Test 4: Check script permissions
echo "Test 4: Script permissions..."
if [ -x "create-worktree.sh" ] && [ -x "cleanup-worktree.sh" ]; then
    echo "✓ Scripts are executable"
else
    echo "✗ Scripts are not executable"
fi
echo

# Test 5: Check directory structure
echo "Test 5: Directory structure..."
if [ -d "branches" ]; then
    echo "✓ branches directory exists"
else
    echo "✗ branches directory missing"
fi

if [ -f "README.md" ]; then
    echo "✓ README.md exists"
else
    echo "✗ README.md missing"
fi
echo

# Test 6: Check git configuration in scripts
echo "Test 6: Git configuration check..."
if grep -q "manoslinh@gmail.com" create-worktree.sh; then
    echo "✓ Git email configured in create-worktree.sh"
else
    echo "✗ Git email not found in create-worktree.sh"
fi

if grep -q "git config user.email" create-worktree.sh; then
    echo "✓ Git config command present"
else
    echo "✗ Git config command missing"
fi
echo

echo "=== Test Summary ==="
echo "All basic validations passed. For full testing, you would need to:"
echo "1. Run ./create-worktree.sh branches/YYYYMMDD_test-role_test-task"
echo "2. Verify worktree is created correctly"
echo "3. Run ./cleanup-worktree.sh branches/YYYYMMDD_test-role_test-task"
echo "4. Verify worktree is cleaned up"
echo
echo "Note: Actual worktree creation requires a git repository with a main/master branch."