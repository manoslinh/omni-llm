#!/bin/bash
# Script to create private GitHub repository for Omni-LLM

set -e

echo "🚀 Creating private GitHub repository for Omni-LLM"

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) not installed. Install it first:"
    echo "   https://cli.github.com/"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo "❌ Not authenticated with GitHub. Please run:"
    echo "   gh auth login"
    exit 1
fi

# Create private repository
echo "📦 Creating private repository 'omni-llm'..."
gh repo create omni-llm \
    --private \
    --description "The orchestration OS for AI-assisted development" \
    --disable-wiki \
    --disable-issues \
    --source=. \
    --remote=origin \
    --push

echo "✅ Private repository created: https://github.com/$(gh api user | jq -r '.login')/omni-llm"
echo ""
echo "📊 Repository settings:"
echo "   - Private (only you and collaborators can see)"
echo "   - Issues disabled (we have our own templates)"
echo "   - Wiki disabled"
echo "   - Code pushed to main branch"
echo ""
echo "🔧 Next steps:"
echo "   1. Go to Settings → Actions → General"
echo "   2. Enable 'Allow all actions and reusable workflows'"
echo "   3. Go to Settings → Secrets and variables → Actions"
echo "   4. Add PYPI_API_TOKEN if you want to publish to PyPI later"