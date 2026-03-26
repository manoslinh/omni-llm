# Worktree: branches/20260326_intern-phase4_cleanup-branches

Created: 2026-03-26 09:01 UTC
Purpose: Cleanup stale branches from origin repository

## Task
Identify and delete merged/stale branches from GitHub origin to clean up repository.

## Current State
- 30+ stale branches cluttering the repo
- `branches/20260325_*` - Phase 2 artifacts (all merged)
- `branches/20260326_coder-phase3_*` - Phase 3 artifacts (all merged)
- `pr21_resolve`, `test-merge2` - old experiments
- Various other temporary branches

## Implementation Steps
1. List all branches on origin: `git branch -r`
2. Check which are merged: `git branch -r --merged origin/main`
3. Check last commit date for stale branches
4. Create deletion script or manual deletion list
5. Execute deletions (requires GitHub CLI auth or API)
6. Create PR for documentation of cleanup

## Worktree Info
- Worktree path: /home/openclaw/.openclaw/workspace/omni-llm-worktrees/branches/20260326_intern-phase4_cleanup-branches
- Source branch: origin/main
- Branch: branches/20260326_intern-phase4_cleanup-branches