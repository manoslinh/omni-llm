# Branch Cleanup Instructions

## Overview

This document provides instructions for cleaning up merged branches from the origin repository.

## Current Status

### Merged Branches (Ready for Deletion)
All 25 branches listed below have been merged to `origin/main` and can be safely deleted:

#### Phase 2 Artifacts (2026-03-25)
1. `branches/20260325_coder-editloop-fix_mutable_default`
2. `branches/20260325_coder-litellm_adapter`
3. `branches/20260325_coder-modelprovider_interface`
4. `branches/20260325_coder-provider_tests`
5. `branches/20260325_coder-testverifier-fix_timeout`
6. `branches/20260325_coder-week2_git-editloop`
7. `branches/20260325_intern-cost_tracker`
8. `branches/20260325_intern-fix_init_files`
9. `branches/20260325_intern-fix_litellm_exceptions`
10. `branches/20260325_intern-fix_messagerole`
11. `branches/20260325_intern-fix_newlines`
12. `branches/20260325_intern-fix_pytest_config`
13. `branches/20260325_intern-fix_ruff_cleanup`
14. `branches/20260325_intern-fix_stubs_optional`
15. `branches/20260325_intern-provider_config`
16. `branches/20260325_intern-ruff-verify_flag`

#### Phase 3 Artifacts (2026-03-26)
17. `branches/20260326_coder-phase3_ticket10`
18. `branches/20260326_coder-phase3_ticket11`
19. `branches/20260326_coder-type_annotations_core`
20. `branches/20260326_coder-type_annotations_providers`
21. `branches/20260326_coordinator-fix_ci_ruff`

#### Dependabot Branches
22. `dependabot/github_actions/actions/checkout-6`
23. `dependabot/github_actions/actions/setup-python-6`
24. `dependabot/github_actions/codecov/codecov-action-5`

### Active Branches (Preserved)
- `branches/20260326_coder-phase4_simplify-ci` - Active development, do not delete

### Local Branches (Not on Origin)
- `pr21_resolve` - Local only, no action needed
- `test-merge2` - Local only, no action needed

## Deletion Methods

### Method 1: Automated Script (Recommended)
Run the provided script:
```bash
cd /home/openclaw/.openclaw/workspace/omni-llm-worktrees/branches/20260326_intern-phase4_cleanup-branches
./scripts/delete_merged_branches.sh
```

The script will:
1. List all merged branches
2. Exclude active branches
3. Ask for confirmation
4. Delete branches from origin

### Method 2: Manual Deletion via GitHub CLI
If you have GitHub CLI authenticated, run:
```bash
# Delete all merged branches
gh api repos/manoslinh/omni-llm/git/refs/heads/branches/20260325_coder-editloop-fix_mutable_default -X DELETE
gh api repos/manoslinh/omni-llm/git/refs/heads/branches/20260325_coder-litellm_adapter -X DELETE
# ... continue for all 25 branches
```

### Method 3: Manual Deletion via Git
```bash
# From the omni-llm repository directory
cd /home/openclaw/.openclaw/workspace/omni-llm

# Delete each branch
git push origin --delete branches/20260325_coder-editloop-fix_mutable_default
git push origin --delete branches/20260325_coder-litellm_adapter
# ... continue for all 25 branches
```

## Verification

After deletion, verify branches are removed:
```bash
git branch -r | grep "branches/20260325"
git branch -r | grep "branches/20260326"
git branch -r | grep "dependabot"
```

## Documentation

### Files Created
1. `README-worktree.md` - Worktree overview
2. `BRANCH_CLEANUP_REPORT.md` - Detailed analysis and report
3. `CLEANUP_INSTRUCTIONS.md` - This file
4. `scripts/delete_merged_branches.sh` - Automated deletion script

### PR Documentation
Create a PR with:
- Summary of cleanup
- List of deleted branches
- Verification steps
- Any issues encountered

## Notes

1. **Authentication Required**: GitHub CLI authentication is needed for deletion
2. **Backup**: Consider backing up important branches before deletion
3. **Recovery**: Deleted branches can be restored from local clones if needed
4. **Active Branches**: Only `branches/20260326_coder-phase4_simplify-ci` is preserved

## Next Steps

1. [ ] Authenticate with GitHub CLI (`gh auth login`)
2. [ ] Run deletion script or manual commands
3. [ ] Verify deletions on GitHub
4. [ ] Create PR documenting cleanup
5. [ ] Close worktree when complete

---

**Signed:** Intern-Branch-Cleanup  
**Date:** 2026-03-26 09:03 UTC