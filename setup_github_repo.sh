#!/bin/bash
# Script to create and push Omni-LLM repository to GitHub
# Requires: gh CLI authenticated, git configured

set -e

echo "=== Omni-LLM GitHub Repository Setup ==="
echo

# Check if gh CLI is authenticated
if ! gh auth status &>/dev/null; then
    echo "Error: GitHub CLI not authenticated."
    echo "Please run: gh auth login"
    exit 1
fi

# Check current branch
CURRENT_BRANCH=$(git branch --show-current)
EXPECTED_BRANCH="branches/20260325_agent-github-setup_create-repository"

if [ "$CURRENT_BRANCH" != "$EXPECTED_BRANCH" ]; then
    echo "Warning: Not on expected branch '$EXPECTED_BRANCH' (currently on '$CURRENT_BRANCH')"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
fi

# Create repository
echo "Creating repository: manoslinh/omni-llm"
gh repo create manoslinh/omni-llm \
    --description "The orchestration OS for AI-assisted development" \
    --private \
    --confirm

# Add remote
echo "Adding remote origin..."
git remote add origin https://github.com/manoslinh/omni-llm.git || true

# Push to main branch
echo "Pushing code to main branch..."
git push -u origin "$CURRENT_BRANCH":main

echo
echo "=== Repository Created Successfully ==="
echo "URL: https://github.com/manoslinh/omni-llm"
echo
echo "Next steps:"
echo "1. Visit https://github.com/manoslinh/omni-llm/settings"
echo "2. Configure repository settings:"
echo "   - Enable Issues and Wiki"
echo "   - Set default branch to 'main'"
echo "   - Enable vulnerability alerts"
echo "   - Configure branch protection rules"
echo "3. Check GitHub Actions workflow runs"
echo "4. Merge branch to main: git checkout main && git merge $CURRENT_BRANCH"
echo "5. Create first release: gh release create v0.1.0 --title 'Initial release'"