# Omni-LLM Worktrees

This directory contains scripts and worktrees for isolated agent task execution.

## Purpose

Provide isolated git worktrees for agent tasks to prevent workspace contamination and enable parallel work.

## Scripts

### `create-worktree.sh`
Creates an isolated worktree for agent tasks.

**Usage:**
```bash
./create-worktree.sh branches/YYYYMMDD_role-name_task
```

**Example:**
```bash
./create-worktree.sh branches/20260326_coder-phase4_worktree-scripts
```

**Features:**
- Creates worktree from `origin/main` (or main/master branch)
- Validates branch name format
- Sets up basic directory structure
- Configures git user email to "manoslinh@gmail.com"
- Outputs worktree path for agent use

### `cleanup-worktree.sh`
Removes worktree after PR completion.

**Usage:**
```bash
./cleanup-worktree.sh branches/YYYYMMDD_role-name_task
```

**Features:**
- Removes worktree directory
- Removes worktree from git registry
- Removes branch if it exists
- Logs cleanup for tracking
- Checks for uncommitted changes (with confirmation)

## Directory Structure

```
omni-llm-worktrees/
├── branches/                    # Worktree directories
│   └── branches/YYYYMMDD_role-name_task/
├── create-worktree.sh          # Creation script
├── cleanup-worktree.sh         # Cleanup script
├── cleanup.log                 # Cleanup history
└── README.md                   # This file
```

## Branch Naming Convention

All branches must follow this format:
```
branches/YYYYMMDD_role-name_task
```

**Examples:**
- `branches/20260326_coder-phase4_worktree-scripts`
- `branches/20260325_intern-fix_modelnames`
- `branches/20260324_agent-installer_v0.1-installer`

## Workflow

1. **Create worktree:**
   ```bash
   ./create-worktree.sh branches/20260326_coder-phase4_worktree-scripts
   ```

2. **Work in isolated environment:**
   ```bash
   cd /home/openclaw/.openclaw/workspace/omni-llm-worktrees/branches/20260326_coder-phase4_worktree-scripts
   # Do your work here
   ```

3. **Commit and push changes:**
   ```bash
   git add .
   git commit -m "Implement feature"
   git push origin branches/20260326_coder-phase4_worktree-scripts
   ```

4. **Clean up after PR merge:**
   ```bash
   ./cleanup-worktree.sh branches/20260326_coder-phase4_worktree-scripts
   ```

## Git Configuration

All worktrees are configured with:
- User email: `manoslinh@gmail.com`
- User name: `OpenClaw Agent`

## Logging

Cleanup operations are logged to `cleanup.log` with timestamp and branch name.

## Notes

- Worktrees are isolated from the main workspace
- Each worktree has its own `.git` file pointing to the main repository
- Changes in worktrees don't affect the main workspace until committed/pushed
- Always clean up worktrees after PRs are merged to avoid clutter