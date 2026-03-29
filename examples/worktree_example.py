#!/usr/bin/env python3
"""
Example demonstrating Git worktree isolation for parallel task execution.
"""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, 'src')

from omni.git.repository import GitRepository
from omni.git.worktree import WorktreeEnv, WorktreeManager


async def main():
    """Demonstrate worktree isolation."""
    # Create a temporary git repository
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "example-repo"
        repo_path.mkdir()

        print(f"Creating git repository at {repo_path}")
        repo = GitRepository(path=str(repo_path))

        # Initialize with a README
        (repo_path / "README.md").write_text("# Example Repository\n\nThis is the main repository.")
        await repo._run_git(["add", "README.md"])
        await repo._run_git(["commit", "-m", "Initial commit"])

        # Create worktree manager
        manager = WorktreeManager(repo=repo, max_worktrees=3)

        print("\n=== Example 1: Basic worktree creation ===")
        # Create a worktree for task "feature-a"
        info = await manager.create("feature-a")
        print(f"Created worktree for 'feature-a' at {info.path}")
        print(f"  Branch: {info.branch}")
        print(f"  Base branch: {info.base_branch}")

        # Make changes in the worktree
        (info.path / "feature.py").write_text("def new_feature():\n    return 'Hello from feature A'")
        print("  Created feature.py in worktree")

        # List active worktrees
        active = await manager.list_active()
        print(f"  Active worktrees: {len(active)}")

        print("\n=== Example 2: WorktreeEnv context manager ===")
        # Use WorktreeEnv for task isolation
        async with WorktreeEnv(manager, "feature-b") as env:
            if env:
                print(f"  Executing task 'feature-b' in worktree at {env.path}")
                # Task code runs here in isolation
                (env.path / "utils.py").write_text("def helper():\n    return 'Helper from feature B'")
                print("  Created utils.py in worktree")
            else:
                print("  Worktree creation failed (fallback to main repo)")

        # Worktree is automatically cleaned up
        print("  Worktree cleaned up after task completion")

        print("\n=== Example 3: Multiple parallel worktrees ===")
        # Create multiple worktrees (within limit)
        tasks = ["task-1", "task-2"]
        for task_id in tasks:
            info = await manager.create(task_id)
            (info.path / f"{task_id}.txt").write_text(f"Content from {task_id}")
            print(f"  Created worktree for {task_id}")

        print(f"  Total worktrees: {len(await manager.list_active())}")

        # Try to exceed limit
        try:
            await manager.create("task-3")
        except Exception as e:
            print(f"  Cannot create task-3: {e}")

        print("\n=== Example 4: Merge changes back to main ===")
        # Commit changes in task-1 worktree
        task1_info = await manager.get("task-1")
        if task1_info:
            worktree_repo = GitRepository(path=str(task1_info.path))
            await worktree_repo.commit(["task-1.txt"], "Add task-1 file", ai_attributed=True)

            # Merge to main
            success = await manager.merge_to_main("task-1")
            if success:
                print("  Successfully merged task-1 changes to main")
                # Check that file exists in main repo
                assert (repo_path / "task-1.txt").exists()
                print("  File task-1.txt now in main repo")
            else:
                print("  Merge failed (conflict)")

        print("\n=== Example 5: Cleanup ===")
        # Clean up all worktrees
        cleaned = await manager.cleanup_all()
        print(f"  Cleaned up worktrees: {cleaned}")
        print(f"  Remaining worktrees: {len(await manager.list_active())}")

        print("\n=== Summary ===")
        print("Worktree isolation provides:")
        print("  - Filesystem isolation for parallel tasks")
        print("  - Automatic cleanup with WorktreeEnv")
        print("  - Git branch management")
        print("  - Merge capabilities back to main")
        print("  - Configurable limits (max_worktrees)")


if __name__ == "__main__":
    asyncio.run(main())
