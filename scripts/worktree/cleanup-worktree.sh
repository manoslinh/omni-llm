#!/bin/bash

# cleanup-worktree.sh - Removes git worktree after PR completion
# Usage: ./cleanup-worktree.sh branches/YYYYMMDD_role-name_task
# Removes worktree directory and cleans up git registry

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
LOG_FILE="${WORKTREES_ROOT}/cleanup.log"

# Validate branch name format
if [[ ! "$BRANCH_NAME" =~ ^branches/[0-9]{8}_[a-zA-Z0-9-]+_[a-zA-Z0-9-]+$ ]]; then
    log_error "Invalid branch name format. Expected: branches/YYYYMMDD_role-name_task"
    log_error "Example: branches/20260326_coder-phase4_worktree-scripts"
    exit 1
fi

log_info "Cleaning up worktree for branch: $BRANCH_NAME"
log_info "Worktree path: $WORKTREE_PATH"

# Check if worktree exists
if [ ! -d "$WORKTREE_PATH" ]; then
    log_warning "Worktree directory does not exist: $WORKTREE_PATH"
    log_warning "Checking if branch exists in git..."
    
    cd "$REPO_PATH"
    if git show-ref --verify --quiet "refs/heads/$BRANCH_NAME"; then
        log_warning "Branch exists but worktree directory is missing."
        log_warning "You may need to manually remove the branch: git branch -D $BRANCH_NAME"
        exit 1
    else
        log_error "Neither worktree directory nor branch exists."
        exit 1
    fi
fi

# Check if worktree is registered in git
cd "$REPO_PATH"
if git worktree list | grep -q "$WORKTREE_PATH"; then
    log_info "Worktree is registered in git. Removing..."
    
    # Check if there are uncommitted changes
    cd "$WORKTREE_PATH"
    if [ -n "$(git status --porcelain)" ]; then
        log_warning "There are uncommitted changes in the worktree!"
        log_warning "Changes:"
        git status --short
        
        read -p "Do you want to continue and lose these changes? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Cleanup cancelled."
            exit 0
        fi
    fi
    
    # Remove worktree from git registry
    cd "$REPO_PATH"
    git worktree remove "$WORKTREE_PATH" --force
    
    log_success "Worktree removed from git registry."
else
    log_warning "Worktree is not registered in git registry."
    log_warning "Only removing directory..."
fi

# Remove the directory
if [ -d "$WORKTREE_PATH" ]; then
    log_info "Removing worktree directory: $WORKTREE_PATH"
    rm -rf "$WORKTREE_PATH"
    log_success "Worktree directory removed."
fi

# Remove the branch if it still exists
cd "$REPO_PATH"
if git show-ref --verify --quiet "refs/heads/$BRANCH_NAME"; then
    log_info "Removing branch: $BRANCH_NAME"
    git branch -D "$BRANCH_NAME"
    log_success "Branch removed."
fi

# Log the cleanup
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "[$TIMESTAMP] Cleaned up worktree: $BRANCH_NAME" >> "$LOG_FILE"

log_success "Worktree cleanup completed successfully!"
log_success "Branch: $BRANCH_NAME"
log_success "Path: $WORKTREE_PATH"

log_info "Cleanup logged to: $LOG_FILE"