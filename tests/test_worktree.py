"""
Tests for git worktree manager.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

from src.omni.git.repository import GitRepository
from src.omni.git.worktree import (
    WorktreeCreationError,
    WorktreeEnv,
    WorktreeError,
    WorktreeExistsError,
    WorktreeInfo,
    WorktreeManager,
    WorktreeNotFoundError,
)


@pytest_asyncio.fixture
async def git_repo(tmp_path):
    """Create a real git repo with initial commit."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()

    # Initialize git repo with main as default branch
    repo = GitRepository(path=str(repo_path))
    
    # Configure git to use main as default branch
    await repo._run_git(["config", "init.defaultBranch", "main"])
    
    # Rename master to main if it exists
    try:
        await repo._run_git(["branch", "-m", "master", "main"])
    except Exception:
        pass  # No master branch, that's fine

    # Create a file and commit
    (repo_path / "README.md").write_text("# Test Repository")
    await repo._run_git(["add", "README.md"])
    await repo._run_git(["commit", "-m", "Initial commit"])

    return repo


@pytest_asyncio.fixture
async def manager(git_repo):
    """Create WorktreeManager with temp repo."""
    return WorktreeManager(repo=git_repo, max_worktrees=5)


class TestWorktreeInfo:
    """Test WorktreeInfo dataclass."""

    def test_creation(self):
        """Test WorktreeInfo creation."""
        info = WorktreeInfo(
            task_id="task-001",
            path=Path("/tmp/test"),
            branch="omni/task/task-001",
            base_branch="main",
        )
        assert info.task_id == "task-001"
        assert info.path == Path("/tmp/test")
        assert info.branch == "omni/task/task-001"
        assert info.base_branch == "main"
        assert isinstance(info.created_at, datetime)

    def test_age_hours(self):
        """Test age_hours property."""
        info = WorktreeInfo(
            task_id="task-001",
            path=Path("/tmp/test"),
            branch="omni/task/task-001",
            base_branch="main",
            created_at=datetime.now() - timedelta(hours=2),
        )
        # Should be approximately 2 hours
        assert 1.9 <= info.age_hours <= 2.1


class TestWorktreeManager:
    """Test WorktreeManager class."""

    @pytest.mark.asyncio
    async def test_create_worktree(self, manager):
        """Test basic worktree creation."""
        info = await manager.create("task-001")

        assert info.task_id == "task-001"
        assert info.branch == "omni/task/task-001"
        # Git may create 'master' or 'main' as default branch
        assert info.base_branch in ["main", "master"]
        assert info.path.exists()
        assert (info.path / "README.md").exists()

        # Verify it's tracked
        assert await manager.get("task-001") == info

    @pytest.mark.asyncio
    async def test_create_duplicate_raises(self, manager):
        """Test that creating duplicate worktree raises error."""
        await manager.create("task-001")
        with pytest.raises(WorktreeExistsError):
            await manager.create("task-001")

    @pytest.mark.asyncio
    async def test_create_max_limit(self, manager):
        """Test max_worktrees limit."""
        # Create max worktrees
        for i in range(5):
            await manager.create(f"task-{i}")

        # Next one should fail
        with pytest.raises(WorktreeError, match="[Mm]ax worktrees"):
            await manager.create("task-extra")

    @pytest.mark.asyncio
    async def test_create_with_custom_base_branch(self, manager, git_repo):
        """Test creating worktree from custom base branch."""
        # Create a feature branch
        await git_repo.create_branch("feature-branch", checkout=True)
        (git_repo.path / "feature.txt").write_text("feature")
        await git_repo._run_git(["add", "feature.txt"])
        await git_repo._run_git(["commit", "-m", "Add feature"])
        await git_repo.checkout_branch("main")

        # Create worktree from feature branch
        info = await manager.create("task-feature", base_branch="feature-branch")
        assert info.base_branch == "feature-branch"
        assert (info.path / "feature.txt").exists()

    @pytest.mark.asyncio
    async def test_remove_worktree(self, manager):
        """Test worktree removal."""
        info = await manager.create("task-001")
        assert await manager.get("task-001") is not None

        await manager.remove("task-001")
        assert await manager.get("task-001") is None
        assert not info.path.exists()

    @pytest.mark.asyncio
    async def test_remove_nonexistent_raises(self, manager):
        """Test removing nonexistent worktree raises error."""
        with pytest.raises(WorktreeNotFoundError):
            await manager.remove("nonexistent")

    @pytest.mark.asyncio
    async def test_remove_idempotent(self, manager):
        """Test remove is idempotent."""
        await manager.create("task-001")
        await manager.remove("task-001")
        # Second remove should NOT raise
        await manager.remove("task-001")

    @pytest.mark.asyncio
    async def test_list_active(self, manager):
        """Test listing active worktrees."""
        assert await manager.list_active() == []

        info1 = await manager.create("task-001")
        info2 = await manager.create("task-002")

        active = await manager.list_active()
        assert len(active) == 2
        assert info1 in active
        assert info2 in active

    @pytest.mark.asyncio
    async def test_isolation(self, manager):
        """Test that changes in one worktree don't affect another."""
        info1 = await manager.create("task-001")
        info2 = await manager.create("task-002")

        # Modify file in worktree 1
        (info1.path / "new_file.txt").write_text("from task 1")

        # Worktree 2 should NOT have this file
        assert not (info2.path / "new_file.txt").exists()

        # Main repo should NOT have this file
        assert not (manager._repo.path / "new_file.txt").exists()

    @pytest.mark.asyncio
    async def test_merge_to_main_success(self, manager, git_repo):
        """Test successful merge to main."""
        info = await manager.create("task-001")

        # Make changes in worktree
        (info.path / "feature.txt").write_text("feature code")

        # Commit changes
        worktree_repo = GitRepository(path=str(info.path))
        await worktree_repo.commit(["feature.txt"], "Add feature", ai_attributed=True)

        # Merge to main
        result = await manager.merge_to_main("task-001")
        assert result is True

        # Main should now have the file
        assert (git_repo.path / "feature.txt").exists()

        # Worktree should be cleaned up
        assert await manager.get("task-001") is None

    @pytest.mark.asyncio
    async def test_merge_to_main_conflict(self, manager, git_repo):
        """Test merge with conflict returns False."""
        info = await manager.create("task-001")

        # Make conflicting changes in worktree
        (info.path / "README.md").write_text("conflicting change")
        worktree_repo = GitRepository(path=str(info.path))
        await worktree_repo.commit(["README.md"], "Conflicting change", ai_attributed=True)

        # Make different change in main
        (git_repo.path / "README.md").write_text("different change")
        await git_repo.commit(["README.md"], "Different change", ai_attributed=True)

        # Merge should fail
        result = await manager.merge_to_main("task-001")
        assert result is False

        # Worktree should still exist
        assert await manager.get("task-001") is not None

    @pytest.mark.asyncio
    async def test_prune(self, manager):
        """Test prune runs without error."""
        await manager.prune()  # Should not raise

    @pytest.mark.asyncio
    async def test_cleanup_stale(self, manager):
        """Test cleanup of stale worktrees."""
        info = await manager.create("task-001")

        # Manually set creation time to old
        info.created_at = datetime.now() - timedelta(hours=48)

        cleaned = await manager.cleanup_stale(max_age_hours=24)
        assert "task-001" in cleaned
        assert await manager.get("task-001") is None

    @pytest.mark.asyncio
    async def test_cleanup_all(self, manager):
        """Test cleanup of all worktrees."""
        await manager.create("task-001")
        await manager.create("task-002")

        assert len(await manager.list_active()) == 2

        cleaned = await manager.cleanup_all()
        assert set(cleaned) == {"task-001", "task-002"}
        assert await manager.list_active() == []

    @pytest.mark.asyncio
    async def test_get_diff(self, manager):
        """Test getting diff of worktree changes."""
        info = await manager.create("task-001")

        # Make changes
        (info.path / "new.txt").write_text("new content")

        diff = await manager.get_diff("task-001")
        assert "new.txt" in diff
        assert "new content" in diff

    @pytest.mark.asyncio
    async def test_has_changes(self, manager):
        """Test checking for uncommitted changes."""
        info = await manager.create("task-001")

        # Initially no changes
        assert not await manager.has_changes("task-001")

        # Create uncommitted file
        (info.path / "dirty.txt").write_text("uncommitted")
        assert await manager.has_changes("task-001")

    @pytest.mark.asyncio
    async def test_commit_in_worktree(self, manager):
        """Test committing changes in worktree."""
        info = await manager.create("task-001")

        # Make changes
        (info.path / "new.txt").write_text("new content")

        # Commit
        commit_hash = await manager.commit_in_worktree("task-001", "Add new file")
        assert commit_hash is not None

        # Verify commit
        worktree_repo = GitRepository(path=str(info.path))
        log = await worktree_repo.get_log(limit=1)
        assert len(log) == 1
        assert "Add new file" in log[0].message

    @pytest.mark.asyncio
    async def test_commit_in_worktree_no_changes(self, manager):
        """Test committing when no changes exist."""
        await manager.create("task-001")

        commit_hash = await manager.commit_in_worktree("task-001", "No changes")
        assert commit_hash is None


class TestWorktreeEnv:
    """Test WorktreeEnv context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_creates_and_cleans(self, manager):
        """Test WorktreeEnv creates and cleans up worktree."""
        async with WorktreeEnv(manager, "task-001") as env:
            assert env.path.exists()
            (env.path / "code.py").write_text("print('hello')")

        # After exit, worktree should be cleaned up
        assert await manager.get("task-001") is None

    @pytest.mark.asyncio
    async def test_context_manager_keeps_on_failure(self, manager):
        """Test WorktreeEnv keeps worktree on failure."""
        with pytest.raises(RuntimeError):
            async with WorktreeEnv(manager, "task-001", cleanup_on_failure=False) as env:
                (env.path / "code.py").write_text("print('hello')")
                raise RuntimeError("task failed")

        # Worktree should still exist for debugging
        info = await manager.get("task-001")
        assert info is not None
        assert (info.path / "code.py").exists()

    @pytest.mark.asyncio
    async def test_context_manager_cleans_on_failure_when_configured(self, manager):
        """Test WorktreeEnv cleans worktree on failure when configured."""
        with pytest.raises(RuntimeError):
            async with WorktreeEnv(manager, "task-001", cleanup_on_failure=True) as env:
                (env.path / "code.py").write_text("print('hello')")
                raise RuntimeError("task failed")

        # Worktree should be cleaned up
        assert await manager.get("task-001") is None

    @pytest.mark.asyncio
    async def test_aexit_force_fallback(self, manager, monkeypatch):
        """Test __aexit__ tries force removal if normal removal fails."""
        # Monkey-patch remove to fail on first call, succeed on force
        call_log = []
        original_remove = manager.remove

        async def failing_remove(task_id, force=False):
            call_log.append(("remove", task_id, force))
            if not force:
                raise WorktreeError("locked")
            # Force succeeds
            await original_remove(task_id, force=True)

        monkeypatch.setattr(manager, "remove", failing_remove)

        env = WorktreeEnv(manager, "task-001", cleanup_on_success=True)
        await env.__aenter__()
        await env.__aexit__(None, None, None)

        # Should have attempted normal then force
        assert ("remove", "task-001", False) in call_log
        assert ("remove", "task-001", True) in call_log

    @pytest.mark.asyncio
    async def test_aexit_never_raises(self, manager, monkeypatch):
        """Test __aexit__ swallows cleanup errors."""
        async def always_fail(task_id, **kwargs):
            raise WorktreeError("totally broken")

        monkeypatch.setattr(manager, "remove", always_fail)

        env = WorktreeEnv(manager, "task-001", cleanup_on_success=True)
        await env.__aenter__()  # Creates worktree
        # Should NOT raise even though remove always fails
        await env.__aexit__(None, None, None)


class TestErrorHierarchy:
    """Test error hierarchy."""

    def test_error_inheritance(self):
        """Test that error classes inherit properly."""
        assert issubclass(WorktreeExistsError, WorktreeError)
        assert issubclass(WorktreeNotFoundError, WorktreeError)
        assert issubclass(WorktreeCreationError, WorktreeError)

        # Can catch specific errors with base class
        try:
            raise WorktreeExistsError("test")
        except WorktreeError:
            pass  # Should be caught

        # Can catch specific errors with their own class
        try:
            raise WorktreeNotFoundError("test")
        except WorktreeNotFoundError:
            pass  # Should be caught
