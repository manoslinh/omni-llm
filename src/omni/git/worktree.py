"""
Git worktree manager for task isolation.

Provides filesystem isolation for parallel task execution using git worktrees.
Each task gets its own worktree with a dedicated branch, allowing parallel
agents to work without filesystem conflicts.
"""

import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .repository import GitRepository

logger = logging.getLogger(__name__)


# ============================================================================
# Error Hierarchy
# ============================================================================

class WorktreeError(Exception):
    """Base worktree error."""


class WorktreeExistsError(WorktreeError):
    """Worktree already exists for this task_id."""


class WorktreeNotFoundError(WorktreeError):
    """No worktree found for this task_id."""


class WorktreeCreationError(WorktreeError):
    """Failed to create worktree (git error, disk full, etc.)."""


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class WorktreeInfo:
    """Information about an active worktree."""

    task_id: str
    path: Path
    branch: str
    base_branch: str
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def age_hours(self) -> float:
        """Hours since worktree creation."""
        return (datetime.now() - self.created_at).total_seconds() / 3600


# ============================================================================
# Worktree Manager
# ============================================================================

class WorktreeManager:
    """
    Manages git worktrees for task isolation.

    Each task gets its own worktree with a dedicated branch,
    allowing parallel agents to work without filesystem conflicts.

    Worktrees are created under: <repo_root>/omni-llm-worktrees/<task_id>/
    Branches follow the pattern: omni/task/<task_id>

    Args:
        repo: GitRepository instance (uses its path and _run_git)
        worktree_base_dir: Directory for worktrees (default: repo_root/omni-llm-worktrees)
        branch_prefix: Prefix for task branches (default: "omni/task")
        max_worktrees: Maximum concurrent worktrees (default: 10). Raises
            WorktreeError if limit is reached.
        auto_cleanup_stale_hours: Automatically clean worktrees older than this on create (hours, 0=disabled)
    """

    def __init__(
        self,
        repo: GitRepository,
        worktree_base_dir: str | Path | None = None,
        branch_prefix: str = "omni/task",
        max_worktrees: int = 10,
        auto_cleanup_stale_hours: float = 0,
    ) -> None:
        self._repo = repo
        self._worktree_base_dir = Path(
            worktree_base_dir or repo.path / "omni-llm-worktrees"
        )
        self._branch_prefix = branch_prefix
        self._max_worktrees = max_worktrees
        self._auto_cleanup_stale_hours = auto_cleanup_stale_hours

        # In-memory registry of active worktrees
        self._worktrees: dict[str, WorktreeInfo] = {}

        # Ensure worktree base directory exists
        self._worktree_base_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"WorktreeManager initialized for {repo.path}, "
            f"max_worktrees={max_worktrees}, "
            f"worktree_dir={self._worktree_base_dir}"
        )

    def _branch_name(self, task_id: str) -> str:
        """Generate branch name for a task."""
        return f"{self._branch_prefix}/{task_id}"

    def _worktree_path(self, task_id: str) -> Path:
        """Generate worktree path for a task."""
        return self._worktree_base_dir / task_id

    async def prune(self) -> None:
        """
        Run `git worktree prune` to clean up stale worktree references.

        This removes git's internal references to worktrees whose
        directories have been deleted or moved.
        """
        try:
            await self._repo._run_git(["worktree", "prune"])
            logger.debug("Ran git worktree prune")
        except Exception as e:
            logger.warning(f"git worktree prune failed: {e}")

    async def create(
        self,
        task_id: str,
        base_branch: str = "main",
    ) -> WorktreeInfo:
        """
        Create a worktree for a task.

        1. Run `git worktree prune` to clean stale references
        2. Check max_worktrees limit; raise WorktreeError if exceeded
        3. Ensure base_branch exists (fetch if needed)
        4. Create branch omni/task/<task_id> from base_branch
        5. Create worktree at omni-llm-worktrees/<task_id>/
        6. Track in internal registry

        Error handling (creation failure):
        - If worktree creation fails AFTER branch is created, the
          orphaned branch is cleaned up (deleted) before re-raising
        - If branch deletion also fails, a warning is logged but the
          original WorktreeCreationError is still raised

        Raises:
            WorktreeError: If max_worktrees limit is reached
            WorktreeCreationError: If worktree creation fails
            WorktreeExistsError: If worktree for this task_id already exists
        """
        # Check if already exists
        if task_id in self._worktrees:
            raise WorktreeExistsError(f"Worktree for task '{task_id}' already exists")

        # Check max worktrees limit
        if len(self._worktrees) >= self._max_worktrees:
            raise WorktreeError(
                f"Max worktrees limit reached ({self._max_worktrees}). "
                f"Clean up stale worktrees or increase max_worktrees."
            )

        # Auto-cleanup stale worktrees if configured
        if self._auto_cleanup_stale_hours > 0:
            await self.cleanup_stale(self._auto_cleanup_stale_hours)

        # Prune stale git references
        await self.prune()

        branch_name = self._branch_name(task_id)
        worktree_path = self._worktree_path(task_id)

        # Ensure base branch exists
        try:
            await self._repo._run_git(["show-ref", "--verify", f"refs/heads/{base_branch}"])
        except RuntimeError:
            # Try alternative default branch names
            if base_branch == "main":
                try:
                    await self._repo._run_git(["show-ref", "--verify", "refs/heads/master"])
                    base_branch = "master"  # Use master instead
                except RuntimeError:
                    # Neither main nor master exists locally
                    pass
            
            # Check if the branch exists locally now
            try:
                await self._repo._run_git(["show-ref", "--verify", f"refs/heads/{base_branch}"])
            except RuntimeError:
                # Branch doesn't exist locally, try to fetch from origin
                try:
                    await self._repo._run_git(["fetch", "origin", base_branch])
                    await self._repo._run_git(["branch", "--track", base_branch, f"origin/{base_branch}"])
                except RuntimeError as e:
                    raise WorktreeCreationError(
                        f"Base branch '{base_branch}' does not exist and could not be fetched: {e}"
                    ) from e

        # Create branch from base_branch
        try:
            await self._repo._run_git(["branch", branch_name, base_branch])
        except RuntimeError as e:
            raise WorktreeCreationError(f"Failed to create branch {branch_name}: {e}") from e

        # Create worktree
        try:
            await self._repo._run_git([
                "worktree", "add",
                str(worktree_path),
                branch_name,
            ])
        except RuntimeError as e:
            # Worktree creation failed - clean up orphaned branch
            logger.warning(f"Worktree creation failed, cleaning up orphaned branch {branch_name}")
            try:
                await self._repo._run_git(["branch", "-D", branch_name])
            except RuntimeError as cleanup_error:
                logger.error(f"Failed to clean up orphaned branch {branch_name}: {cleanup_error}")
            raise WorktreeCreationError(f"Failed to create worktree at {worktree_path}: {e}") from e

        # Success - track worktree
        info = WorktreeInfo(
            task_id=task_id,
            path=worktree_path,
            branch=branch_name,
            base_branch=base_branch,
        )
        self._worktrees[task_id] = info

        logger.info(f"Created worktree for task '{task_id}' at {worktree_path}")
        return info

    async def remove(self, task_id: str, force: bool = False) -> None:
        """
        Remove a worktree and its branch.

        1. git worktree remove <path> [--force if needed]
        2. git branch -d omni/task/<task_id>
        3. Remove from internal registry

        Safe to call multiple times (idempotent).

        Args:
            task_id: Task identifier
            force: Use --force flag for worktree removal
        """
        if task_id not in self._worktrees:
            # Already removed - idempotent
            return

        info = self._worktrees[task_id]

        # Remove worktree
        try:
            cmd = ["worktree", "remove"]
            if force:
                cmd.append("--force")
            cmd.append(str(info.path))
            await self._repo._run_git(cmd)
        except RuntimeError as e:
            if not force:
                # Try with force
                logger.warning(f"Worktree removal failed, retrying with force: {e}")
                try:
                    await self._repo._run_git(["worktree", "remove", "--force", str(info.path)])
                except RuntimeError as force_error:
                    logger.error(f"Force removal also failed: {force_error}")
                    # Don't re-raise - we'll try to delete the branch anyway
            else:
                logger.error(f"Force removal failed: {e}")
                # Continue to try branch deletion

        # Delete branch
        try:
            await self._repo._run_git(["branch", "-d", info.branch])
        except RuntimeError as e:
            logger.warning(f"Failed to delete branch {info.branch}: {e}")
            # Branch might already be deleted or merged

        # Clean up directory if it still exists
        if info.path.exists():
            try:
                shutil.rmtree(info.path)
            except OSError as e:
                logger.warning(f"Failed to remove worktree directory {info.path}: {e}")

        # Remove from registry
        del self._worktrees[task_id]
        logger.info(f"Removed worktree for task '{task_id}'")

    async def get(self, task_id: str) -> WorktreeInfo | None:
        """Get worktree info for a task, or None if not found."""
        return self._worktrees.get(task_id)

    async def list_active(self) -> list[WorktreeInfo]:
        """List all tracked worktrees."""
        return list(self._worktrees.values())

    async def merge_to_main(
        self,
        task_id: str,
        target_branch: str = "main",
        delete_branch: bool = True,
    ) -> bool:
        """
        Merge a task's worktree branch into target branch.

        1. Checkout target_branch
        2. git merge --no-ff omni/task/<task_id>
        3. Optionally delete the task branch
        4. Remove worktree

        Returns True if merge succeeded.
        """
        if task_id not in self._worktrees:
            raise WorktreeNotFoundError(f"No worktree found for task '{task_id}'")

        info = self._worktrees[task_id]

        try:
            # Save current branch
            current_branch = await self._repo.get_current_branch()

            # Checkout target branch
            await self._repo.checkout_branch(target_branch)

            # Merge task branch
            await self._repo._run_git(["merge", "--no-ff", info.branch])

            # Optionally delete branch
            if delete_branch:
                try:
                    await self._repo._run_git(["branch", "-d", info.branch])
                except RuntimeError as e:
                    logger.warning(f"Failed to delete branch {info.branch}: {e}")

            # Remove worktree
            await self.remove(task_id, force=True)

            # Restore original branch if different
            if current_branch != target_branch:
                await self._repo.checkout_branch(current_branch)

            logger.info(f"Successfully merged worktree '{task_id}' into {target_branch}")
            return True

        except RuntimeError as e:
            logger.error(f"Merge failed for worktree '{task_id}': {e}")
            return False

    async def cleanup_stale(self, max_age_hours: float = 24) -> list[str]:
        """
        Remove worktrees older than max_age_hours.

        Returns list of task_ids that were cleaned up.
        Handles partially-created worktrees gracefully.
        """
        cleaned = []
        for task_id, info in list(self._worktrees.items()):
            if info.age_hours > max_age_hours:
                try:
                    await self.remove(task_id, force=True)
                    cleaned.append(task_id)
                except Exception as e:
                    logger.warning(f"Failed to clean up stale worktree '{task_id}': {e}")
        return cleaned

    async def cleanup_all(self) -> list[str]:
        """
        Remove ALL tracked worktrees. Nuclear option.

        Returns list of task_ids that were cleaned up.
        """
        task_ids = list(self._worktrees.keys())
        cleaned = []
        for task_id in task_ids:
            try:
                await self.remove(task_id, force=True)
                cleaned.append(task_id)
            except Exception as e:
                logger.warning(f"Failed to clean up worktree '{task_id}': {e}")
        return cleaned

    async def get_diff(self, task_id: str) -> str:
        """Get the diff of a task's worktree against its base branch."""
        if task_id not in self._worktrees:
            raise WorktreeNotFoundError(f"No worktree found for task '{task_id}'")

        info = self._worktrees[task_id]
        try:
            return await self._repo._run_git([
                "diff",
                info.base_branch,
                info.branch,
                "--no-color",
            ])
        except RuntimeError as e:
            logger.error(f"Failed to get diff for worktree '{task_id}': {e}")
            return ""

    async def has_changes(self, task_id: str) -> bool:
        """Check if a task's worktree has uncommitted changes."""
        if task_id not in self._worktrees:
            raise WorktreeNotFoundError(f"No worktree found for task '{task_id}'")

        info = self._worktrees[task_id]
        try:
            # Create a temporary GitRepository for the worktree
            worktree_repo = GitRepository(path=str(info.path))
            return await worktree_repo.has_dirty_changes()
        except RuntimeError as e:
            logger.error(f"Failed to check changes for worktree '{task_id}': {e}")
            return False

    async def commit_in_worktree(
        self,
        task_id: str,
        message: str,
        files: list[str] | None = None,
    ) -> str | None:
        """
        Commit changes in a task's worktree.

        If files is None, stages all changes.
        Returns commit hash or None if no changes.
        """
        if task_id not in self._worktrees:
            raise WorktreeNotFoundError(f"No worktree found for task '{task_id}'")

        info = self._worktrees[task_id]

        # Create a temporary GitRepository for the worktree
        worktree_repo = GitRepository(path=str(info.path))

        # Check if there are changes to commit
        if not await worktree_repo.has_dirty_changes():
            logger.debug(f"No changes to commit in worktree '{task_id}'")
            return None

        # Commit
        try:
            if files:
                commit_hash = await worktree_repo.commit(files, message, ai_attributed=True)
            else:
                # Stage all changes first
                await worktree_repo._run_git(["add", "--all"])
                # Get list of changed files
                status_result = await worktree_repo._run_git(["status", "--porcelain"])
                changed_files = [line[3:].strip() for line in status_result.strip().split('\n') if line]
                if changed_files:
                    commit_hash = await worktree_repo.commit(changed_files, message, ai_attributed=True)
                else:
                    return None
            logger.info(f"Committed changes in worktree '{task_id}': {commit_hash}")
            return commit_hash
        except RuntimeError as e:
            logger.error(f"Failed to commit in worktree '{task_id}': {e}")
            raise


# ============================================================================
# Worktree Environment Context Manager
# ============================================================================

class WorktreeEnv:
    """
    Context manager that provides filesystem isolation for task execution.

    Creates a worktree before task execution, cleans up after.

    Usage:
        env = WorktreeEnv(manager=worktree_manager, task_id="abc123")
        async with env:
            # env.path points to the isolated worktree
            # Execute task in env.path
            result = await execute_task_in(env.path)
        # Worktree cleaned up on exit (or kept on error for debugging)
    """

    def __init__(
        self,
        manager: WorktreeManager,
        task_id: str,
        base_branch: str = "main",
        cleanup_on_success: bool = True,
        cleanup_on_failure: bool = False,  # Keep for debugging
    ) -> None:
        self.manager = manager
        self.task_id = task_id
        self.base_branch = base_branch
        self.cleanup_on_success = cleanup_on_success
        self.cleanup_on_failure = cleanup_on_failure
        self.info: WorktreeInfo | None = None
        self.path: Path | None = None

    async def __aenter__(self) -> WorktreeInfo | None:
        """Create worktree and return its info."""
        try:
            self.info = await self.manager.create(self.task_id, self.base_branch)
            self.path = self.info.path
            return self.info
        except WorktreeCreationError as e:
            logger.warning(f"Failed to create worktree for task '{self.task_id}': {e}")
            self.info = None
            self.path = None
            return None

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Cleanup on exit.

        - If no exception and cleanup_on_success: remove worktree
        - If exception and cleanup_on_failure: remove worktree
        - If exception and not cleanup_on_failure: keep for debugging

        Removal error handling:
        1. Try normal remove: `git worktree remove <path>`
        2. If that fails, try force remove: `git worktree remove --force <path>`
        3. If force also fails, log warning and leave the worktree
           (manual cleanup via `prune()` or `cleanup_stale()` will catch it)

        This ensures __aexit__ never raises — cleanup failures are logged,
        not propagated.
        """
        if self.info is None:
            return

        should_cleanup = False
        if exc_type is None and self.cleanup_on_success:
            should_cleanup = True
        elif exc_type is not None and self.cleanup_on_failure:
            should_cleanup = True

        if not should_cleanup:
            return

        try:
            await self.manager.remove(self.task_id, force=False)
        except WorktreeError as e:
            # Try force removal
            logger.warning(f"Normal worktree removal failed for '{self.task_id}', trying force: {e}")
            try:
                await self.manager.remove(self.task_id, force=True)
            except WorktreeError as force_error:
                logger.warning(
                    f"Force removal also failed for '{self.task_id}': {force_error}. "
                    f"Worktree will be cleaned up by prune() or cleanup_stale() later."
                )
        except Exception as e:
            # Catch any other exception
            logger.warning(f"Unexpected error during worktree cleanup for '{self.task_id}': {e}")