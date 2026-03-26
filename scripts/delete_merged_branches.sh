#!/bin/bash

# delete_merged_branches.sh - Delete merged branches from origin
# This script deletes branches that have been merged to main
# Active branches (with recent commits or open PRs) are preserved

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    log_error "Not in a git repository"
    exit 1
fi

# Get current branch
CURRENT_BRANCH=$(git branch --show-current)
log_info "Current branch: $CURRENT_BRANCH"

# Get list of merged branches
log_info "Getting list of merged branches..."
MERGED_BRANCHES=$(git branch -r --merged origin/main | grep -v "origin/main" | sort)

if [ -z "$MERGED_BRANCHES" ]; then
    log_info "No merged branches found."
    exit 0
fi

log_info "Found $(echo "$MERGED_BRANCHES" | wc -l) merged branches:"
echo "$MERGED_BRANCHES"

# Define active branches to preserve
ACTIVE_BRANCHES=(
    "origin/branches/20260326_coder-phase4_simplify-ci"
)

log_info "Active branches to preserve:"
for branch in "${ACTIVE_BRANCHES[@]}"; do
    echo "  - $branch"
done

# Create deletion list
DELETION_LIST=""
for branch in $MERGED_BRANCHES; do
    # Check if branch is active
    IS_ACTIVE=false
    for active in "${ACTIVE_BRANCHES[@]}"; do
        if [ "$branch" = "$active" ]; then
            IS_ACTIVE=true
            break
        fi
    done
    
    if [ "$IS_ACTIVE" = true ]; then
        log_warning "Preserving active branch: $branch"
    else
        DELETION_LIST="$DELETION_LIST $branch"
    fi
done

if [ -z "$DELETION_LIST" ]; then
    log_info "No branches to delete."
    exit 0
fi

log_info "Branches to delete:"
for branch in $DELETION_LIST; do
    echo "  - $branch"
done

# Ask for confirmation
read -p "Delete these branches from origin? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Deletion cancelled."
    exit 0
fi

# Delete branches
for branch in $DELETION_LIST; do
    # Remove "origin/" prefix
    branch_name=${branch#origin/}
    
    log_info "Deleting branch: $branch"
    git push origin --delete "$branch_name"
    
    if [ $? -eq 0 ]; then
        log_success "Deleted: $branch"
    else
        log_error "Failed to delete: $branch"
    fi
done

log_success "Branch deletion completed!"