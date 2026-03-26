#!/bin/bash

# create-worktree.sh - Creates isolated git worktree for agent tasks
# Usage: ./create-worktree.sh branches/YYYYMMDD_role-name_task
# Creates worktree from origin/main (or main branch if origin not available)

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if branch name is provided
if [ $# -ne 1 ]; then
    echo "Usage: $0 branches/YYYYMMDD_role-name_task"
    echo "Example: $0 branches/20260326_coder-phase4_worktree-scripts"
    exit 1
fi

BRANCH_NAME="$1"
WORKTREES_ROOT="/home/openclaw/.openclaw/workspace/omni-llm-worktrees"
WORKTREE_PATH="${WORKTREES_ROOT}/${BRANCH_NAME}"
REPO_PATH="/home/openclaw/.openclaw/workspace"

# Validate branch name format
if [[ ! "$BRANCH_NAME" =~ ^branches/[0-9]{8}_[a-zA-Z0-9-]+_[a-zA-Z0-9-]+$ ]]; then
    log_error "Invalid branch name format. Expected: branches/YYYYMMDD_role-name_task"
    log_error "Example: branches/20260326_coder-phase4_worktree-scripts"
    exit 1
fi

log_info "Creating worktree for branch: $BRANCH_NAME"
log_info "Worktree path: $WORKTREE_PATH"

# Check if worktree already exists
if [ -d "$WORKTREE_PATH" ]; then
    log_warning "Worktree directory already exists: $WORKTREE_PATH"
    log_warning "If you want to recreate, remove it first with: rm -rf $WORKTREE_PATH"
    exit 1
fi

# Check if branch already exists
cd "$REPO_PATH"
if git show-ref --verify --quiet "refs/heads/$BRANCH_NAME"; then
    log_warning "Branch already exists: $BRANCH_NAME"
    log_warning "If you want to recreate, delete it first with: git branch -D $BRANCH_NAME"
    exit 1
fi

# Determine source branch (origin/main or main)
SOURCE_BRANCH="main"
if git show-ref --verify --quiet "refs/remotes/origin/main"; then
    SOURCE_BRANCH="origin/main"
    log_info "Using source branch: origin/main"
elif git show-ref --verify --quiet "refs/heads/main"; then
    SOURCE_BRANCH="main"
    log_info "Using source branch: main"
else
    # Try to find any main/master branch
    if git show-ref --verify --quiet "refs/heads/master"; then
        SOURCE_BRANCH="master"
        log_info "Using source branch: master"
    elif git show-ref --verify --quiet "refs/remotes/origin/master"; then
        SOURCE_BRANCH="origin/master"
        log_info "Using source branch: origin/master"
    else
        log_error "No main/master branch found. Please check your repository."
        exit 1
    fi
fi

# Create worktree
log_info "Creating worktree from $SOURCE_BRANCH..."
git worktree add "$WORKTREE_PATH" "$SOURCE_BRANCH"

# Switch to worktree directory and create branch
cd "$WORKTREE_PATH"
git checkout -b "$BRANCH_NAME"

# Set up git configuration for this worktree
git config user.email "manoslinh@gmail.com"
git config user.name "OpenClaw Agent"

# Create basic directory structure
mkdir -p scripts references logs

# Create a README for the worktree
cat > README-worktree.md << EOF
# Worktree: $BRANCH_NAME

Created: $(date)
Purpose: Isolated workspace for agent task

## Usage
- This is an isolated git worktree
- Changes here are separate from the main workspace
- Commit and push from this directory
- Use cleanup-worktree.sh when done

## Notes
- Worktree path: $WORKTREE_PATH
- Source branch: $SOURCE_BRANCH
EOF

log_success "Worktree created successfully!"
log_success "Worktree path: $WORKTREE_PATH"
log_success "Branch: $BRANCH_NAME"
log_success "Source: $SOURCE_BRANCH"

# Output the path for agent use
echo "WORKTREE_PATH=$WORKTREE_PATH"
echo "BRANCH_NAME=$BRANCH_NAME"

log_info "Next steps:"
log_info "1. cd $WORKTREE_PATH"
log_info "2. Work on your task"
log_info "3. Commit changes"
log_info "4. Push to remote"
log_info "5. When done, run: ./cleanup-worktree.sh $BRANCH_NAME"