# P2-16 (Original): Git Worktree Manager — Architecture

**Author:** Athena (mimo-v2-pro)
**Date:** 2026-03-29
**Phase:** 2.4 — Parallel Execution Isolation
**Status:** Architecture Design (v2 — post-review)

---

## 1. Problem Statement

Parallel agents executing tasks against the same repository will collide: two workers editing the same file, race conditions on git operations, and no clean rollback per-task. We need **filesystem isolation** so each task's code changes live in their own git worktree.

**What exists today:**
- `GitRepository` (`src/omni/git/repository.py`) has a basic `create_worktree(path, branch)` method — no task-aware lifecycle, no cleanup, no tracking
- `ParallelExecutionEngine` (`src/omni/execution/engine.py`) runs tasks in parallel but all share the same working directory
- `Scheduler` dispatches tasks as async callables with semaphore-based concurrency
- `TaskExecutor` protocol executes tasks but has no filesystem context
- P2-16 was redefined as "Advanced Scheduling & Resource Management" (policies, global resources, predictive module, schedule adjuster) — all implemented. The original worktree isolation was deferred.

**What we need:**
1. **Worktree lifecycle management** — create, track, cleanup worktrees tied to task IDs
2. **Integration with the execution engine** — tasks execute in isolated worktrees
3. **Automatic cleanup** — stale worktrees don't accumulate
4. **Error resilience** — worktree creation failures don't crash the engine
5. **Merge-back support** — completed task changes can be merged to main

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     ParallelExecutionEngine                         │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────────────┐    │
│  │  Scheduler    │───▶│  TaskExecutor │───▶│  ExecutionContext  │    │
│  │  (P2-16      │    │  (protocol)   │    │  (dep results +    │    │
│  │   policies)  │    │              │    │   worktree path)   │    │
│  └──────────────┘    └──────────────┘    └─────────┬──────────┘    │
│                                                     │               │
│                                              ┌──────▼──────┐       │
│                                              │ WorktreeEnv │       │
│                                              │ (NEW)       │       │
│                                              │             │       │
│                                              │ Wraps task  │       │
│                                              │ execution   │       │
│                                              │ in worktree │       │
│                                              │ context     │       │
│                                              └──────┬──────┘       │
│                                                     │               │
├─────────────────────────────────────────────────────┼───────────────┤
│                     Git Layer                        │               │
│                                                      │               │
│  ┌──────────────────────────────────────────────┐    │               │
│  │              WorktreeManager (NEW)            │◀──┘               │
│  │                                               │                  │
│  │  create(task_id, base_branch) → WorktreeInfo  │                  │
│  │  remove(task_id)                              │                  │
│  │  get(task_id) → WorktreeInfo | None           │                  │
│  │  list_active() → list[WorktreeInfo]           │                  │
│  │  merge_to_main(task_id) → bool                │                  │
│  │  cleanup_stale(max_age_hours)                 │                  │
│  │  cleanup_all()                                │                  │
│  │  prune()                                      │                  │
│  └───────────────────┬──────────────────────────┘                  │
│                      │                                              │
│  ┌───────────────────▼──────────────────────────┐                  │
│  │           GitRepository (existing)            │                  │
│  │  _run_git(), create_worktree(), commit(),     │                  │
│  │  merge_branch(), get_diff(), etc.             │                  │
│  └──────────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
```

### Design Decision: Standalone Component, Not Embedded

The `WorktreeManager` is a **standalone component in `src/omni/git/`**, not embedded in the execution engine. Reasons:

1. **Reusability** — other subsystems (CLI, future worker agents) need worktree access without importing the entire execution engine
2. **Separation of concerns** — git operations ≠ task scheduling. The execution engine should *use* worktrees, not *be* the worktree code
3. **Testability** — worktree operations can be tested independently with `tmp_path` git repos
4. **Matches existing structure** — `src/omni/git/` already exists with `repository.py`

Integration with the execution engine happens via a thin adapter (`WorktreeEnv`) that wraps task execution in a worktree context.

---

## 3. Component Design

### 3.1 WorktreeInfo Dataclass

```python
# src/omni/git/worktree.py

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


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
```

### 3.2 WorktreeManager

```python
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
        auto_cleanup_stale: Automatically clean worktrees older than this on create (hours, 0=disabled)
    """

    def __init__(
        self,
        repo: GitRepository,
        worktree_base_dir: str | Path | None = None,
        branch_prefix: str = "omni/task",
        max_worktrees: int = 10,
        auto_cleanup_stale_hours: float = 0,
    ) -> None: ...

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

    async def remove(self, task_id: str) -> None:
        """
        Remove a worktree and its branch.

        1. git worktree remove <path> [--force if needed]
        2. git branch -d omni/task/<task_id>
        3. Remove from internal registry

        Safe to call multiple times (idempotent).
        Raises:
            WorktreeNotFoundError: If no worktree exists for this task_id
        """

    async def get(self, task_id: str) -> WorktreeInfo | None:
        """Get worktree info for a task, or None if not found."""

    async def list_active(self) -> list[WorktreeInfo]:
        """List all tracked worktrees."""

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

    async def prune(self) -> None:
        """
        Run `git worktree prune` to clean up stale worktree references.

        This removes git's internal references to worktrees whose
        directories have been deleted or moved. Call this at the start
        of `create()` automatically, or explicitly when you suspect
        stale state.
        """

    async def cleanup_stale(self, max_age_hours: float = 24) -> list[str]:
        """
        Remove worktrees older than max_age_hours.

        Returns list of task_ids that were cleaned up.
        Handles partially-created worktrees gracefully.
        """

    async def cleanup_all(self) -> list[str]:
        """
        Remove ALL tracked worktrees. Nuclear option.

        Returns list of task_ids that were cleaned up.
        """

    async def get_diff(self, task_id: str) -> str:
        """Get the diff of a task's worktree against its base branch."""

    async def has_changes(self, task_id: str) -> bool:
        """Check if a task's worktree has uncommitted changes."""

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
```

### 3.3 Error Hierarchy

```python
class WorktreeError(Exception):
    """Base worktree error."""

class WorktreeExistsError(WorktreeError):
    """Worktree already exists for this task_id."""

class WorktreeNotFoundError(WorktreeError):
    """No worktree found for this task_id."""

class WorktreeCreationError(WorktreeError):
    """Failed to create worktree (git error, disk full, etc.)."""
```

### 3.4 WorktreeEnv — Execution Engine Adapter

```python
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
    ) -> None: ...

    async def __aenter__(self) -> WorktreeInfo: ...

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
```

---

## 4. Error Handling Flow

### 4.1 Worktree Creation Failure (Orphaned Branch Cleanup)

```
create(task_id, base_branch)
│
├─ prune()                              ← clean stale git refs first
├─ check max_worktrees                  ← fail early if limit hit
├─ create branch "omni/task/<task_id>"  ← step 1: branch
│
├─ try:
│   └─ create worktree at path          ← step 2: worktree
│
├─ except WorktreeCreationError:
│   ├─ try:
│   │   └─ git branch -d omni/task/<task_id>   ← cleanup orphan
│   ├─ except:
│   │   └─ log warning ("failed to clean up orphaned branch")
│   └─ re-raise WorktreeCreationError
│
└─ on success:
   └─ track in registry
```

### 4.2 WorktreeEnv Exit (Force Fallback)

```
WorktreeEnv.__aexit__(exc_type, ...)
│
├─ should_cleanup? (based on cleanup_on_success/failure flags)
│
├─ if yes:
│   ├─ try: manager.remove(task_id)
│   │
│   ├─ except WorktreeError:
│   │   ├─ try: manager.remove(task_id, force=True)
│   │   │       or: git worktree remove --force <path>
│   │   ├─ except:
│   │   │   └─ log.warning("could not remove worktree {task_id}, will be pruned later")
│   │   └─ (do NOT re-raise — __aexit__ must not raise)
│   │
│   └─ (do NOT re-raise — __aexit__ must not raise)
│
└─ return None (suppresses no exceptions)
```

---

## 5. Integration Plan

### 5.1 Integration with Execution Engine

The execution engine's `_create_task_executor` method wraps task execution. We add optional worktree isolation:

```python
# In ParallelExecutionEngine.__init__, add:
#   self.worktree_manager: WorktreeManager | None = None
#   self._use_worktrees: bool = False

# In _create_task_executor(), wrap execution:
async def execute_task(task: Task) -> Any:
    context = ExecutionContext(...)

    if self._use_worktrees and self.worktree_manager:
        async with WorktreeEnv(self.worktree_manager, task.task_id) as env:
            context.worktree_path = env.path  # NEW field
            return await self.executor.execute(task, context)
    else:
        return await self.executor.execute(task, context)
```

**Changes to existing files:**

| File | Change | Lines |
|------|--------|-------|
| `src/omni/git/worktree.py` | **NEW** — WorktreeManager, WorktreeInfo, WorktreeEnv, errors | ~280 |
| `src/omni/git/__init__.py` | Add exports | ~5 |
| `src/omni/execution/config.py` | Add `worktree_path` to `ExecutionContext` | ~2 |
| `src/omni/execution/engine.py` | Add optional `worktree_manager` param, wrap executor | ~20 |
| `src/omni/execution/__init__.py` | Export WorktreeEnv (optional) | ~2 |

**Total: ~310 new lines, ~25 modified lines.**

### 5.2 Integration with Scheduler

No changes needed to the scheduler. Worktree lifecycle is handled at the executor level, below the scheduler's concern. The scheduler decides *when* to run a task; the executor (via WorktreeEnv) decides *where*.

### 5.3 Integration with Resource Pool

The `ResourcePool` tracks concurrent slots. Worktree creation consumes disk, not CPU. No direct integration needed, but we should:
- Count active worktrees as a resource metric
- Add worktree count to `ResourcePool.utilization`
- Limit max concurrent worktrees via `max_worktrees` (already implemented)

This is a future enhancement for deeper integration — the `max_worktrees` limit on `WorktreeManager` handles the immediate concern.

### 5.4 Integration with TaskExecutor Protocol

The `TaskExecutor` protocol is unchanged. The `ExecutionContext` gains an optional `worktree_path: Path | None` field. Executors that care about filesystem isolation (e.g., `LLMTaskExecutor` running actual code) can use it. Executors that don't (e.g., `MockTaskExecutor`) ignore it.

---

## 6. Implementation Approach

### Phase 1: Core WorktreeManager (~2.5h)

| Step | Description | Est. |
|------|-------------|------|
| 1.1 | `WorktreeInfo` dataclass + error classes | 15min |
| 1.2 | `WorktreeManager.__init__` with `max_worktrees`, `_run_git` delegation | 20min |
| 1.3 | `prune()` — `git worktree prune` wrapper | 10min |
| 1.4 | `create()` — limit check, prune, branch + worktree with orphan cleanup | 40min |
| 1.5 | `remove()` — worktree removal + branch deletion with force fallback | 25min |
| 1.6 | `get()`, `list_active()` — registry queries | 10min |
| 1.7 | `merge_to_main()` — merge + cleanup | 20min |
| 1.8 | `cleanup_stale()`, `cleanup_all()` | 15min |
| 1.9 | Edge cases: idempotent remove, max limit, orphan cleanup, prune integration | 15min |

### Phase 2: WorktreeEnv + Engine Integration (~1.5h)

| Step | Description | Est. |
|------|-------------|------|
| 2.1 | `WorktreeEnv` context manager with force fallback in `__aexit__` | 35min |
| 2.2 | Add `worktree_path` to `ExecutionContext` | 5min |
| 2.3 | Wire `WorktreeManager` into `ParallelExecutionEngine` | 30min |
| 2.4 | `get_diff()`, `has_changes()`, `commit_in_worktree()` | 25min |

### Phase 3: Tests (~2.5h)

| Step | Description | Est. |
|------|-------------|------|
| 3.1 | Unit tests: create/remove/get/list | 30min |
| 3.2 | Unit tests: merge, cleanup_stale, cleanup_all | 30min |
| 3.3 | Unit tests: error cases (exists, not found, git failures, max limit) | 25min |
| 3.4 | Unit tests: prune, orphaned branch cleanup on create failure | 20min |
| 3.5 | Integration test: WorktreeEnv with force fallback in __aexit__ | 20min |
| 3.6 | Integration test: ParallelExecutionEngine with worktrees | 20min |

**Total estimated time: ~6.5 hours**

---

## 7. Key Design Decisions

### 7.1 Reuse `GitRepository._run_git()` vs. Shell-Out Directly

**Decision:** Reuse `GitRepository._run_git()`.

The `WorktreeManager` takes a `GitRepository` instance and delegates git operations through its async `_run_git()` method. This gives us:
- Consistent error handling
- Async subprocess management for free
- Logging integration
- Path resolution via `repo.path`

### 7.2 Worktree Location Convention

**Decision:** `<repo_root>/omni-llm-worktrees/<task_id>/`

This matches the existing convention in `README-worktree.md` and `TOOL.md`. The `task_id` is the directory name, making it easy to correlate worktrees with tasks.

### 7.3 Branch Naming

**Decision:** `omni/task/<task_id>`

Matches the original PHASE2_PLAN.md spec. The prefix is configurable via `branch_prefix` parameter.

### 7.4 Cleanup Strategy

**Decision:** Hybrid — automatic on success, manual on failure.

- `WorktreeEnv` with `cleanup_on_success=True` (default): removes worktree after successful task completion
- `cleanup_on_failure=False` (default): keeps failed worktrees for debugging
- `cleanup_stale(max_age_hours)`: manual/explicit cleanup of old worktrees
- `cleanup_all()`: nuclear option for batch cleanup
- `prune()`: called automatically at start of `create()` to clean stale git references

### 7.5 Concurrent Worktree Creation

**Decision:** Git's worktree lock handles concurrency. No additional mutex needed.

`git worktree add` fails if the branch is already checked out in another worktree. We use unique `task_id`-based branches, so conflicts only happen if the same task_id is used twice (caught by `WorktreeExistsError`).

### 7.6 What If Worktree Creation Fails?

**Decision:** Raise `WorktreeCreationError`, clean up orphaned branch first.

The `create()` method now has explicit cleanup logic:
1. If branch creation succeeds but worktree creation fails, delete the orphaned branch
2. If branch deletion also fails, log a warning (don't mask the original error)
3. Re-raise `WorktreeCreationError` for the executor to handle

The execution engine should catch this and either:
1. Retry worktree creation once
2. Fall back to executing without worktree isolation (degraded mode)
3. Mark the task as failed if isolation is required

### 7.7 Max Worktrees Limit

**Decision:** `max_worktrees: int = 10` parameter on `WorktreeManager`.

This prevents unbounded resource consumption. Checked at the start of `create()` before any git operations. Raises `WorktreeError` (not `WorktreeCreationError`, since no creation was attempted). Callers can increase the limit if their environment supports more concurrent worktrees.

### 7.8 `__aexit__` Never Raises

**Decision:** WorktreeEnv's `__aexit__` catches all cleanup errors.

Cleanup is best-effort. If `remove()` fails, try force removal. If force removal fails, log and move on. The worktree will be caught by `prune()` or `cleanup_stale()` later. This prevents cleanup failures from masking the original task exception.

---

## 8. Test Strategy

### Unit Tests (`tests/test_worktree.py`)

```python
# Uses tmp_path to create real git repos for testing

@pytest.fixture
async def git_repo(tmp_path):
    """Create a real git repo with initial commit."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    # git init + initial commit
    repo = GitRepository(path=str(repo_path))
    # Create a file and commit
    (repo_path / "README.md").write_text("# Test")
    await repo.commit(["README.md"], "Initial commit")
    return repo

@pytest.fixture
async def manager(git_repo):
    """Create WorktreeManager with temp repo."""
    return WorktreeManager(repo=git_repo)

class TestWorktreeManager:
    async def test_create_worktree(self, manager):
        info = await manager.create("task-001")
        assert info.task_id == "task-001"
        assert info.branch == "omni/task/task-001"
        assert info.path.exists()
        assert (info.path / "README.md").exists()

    async def test_create_duplicate_raises(self, manager):
        await manager.create("task-001")
        with pytest.raises(WorktreeExistsError):
            await manager.create("task-001")

    async def test_create_max_limit(self, manager):
        """max_worktrees prevents unbounded creation."""
        manager._max_worktrees = 2
        await manager.create("task-001")
        await manager.create("task-002")
        with pytest.raises(WorktreeError, match="max worktrees"):
            await manager.create("task-003")

    async def test_create_cleans_orphaned_branch_on_failure(self, manager, monkeypatch):
        """If worktree add fails after branch creation, orphaned branch is cleaned."""
        original_run = manager._repo._run_git
        call_count = 0

        async def mock_run_git(cmd, *args, **kwargs):
            nonlocal call_count
            if "worktree" in cmd and "add" in cmd:
                raise RuntimeError("disk full")
            return await original_run(cmd, *args, **kwargs)

        monkeypatch.setattr(manager._repo, "_run_git", mock_run_git)

        with pytest.raises(WorktreeCreationError):
            await manager.create("task-001")

        # Branch should have been cleaned up
        result = await manager._repo._run_git(["branch", "--list", "omni/task/task-001"])
        assert "omni/task/task-001" not in result

    async def test_remove_worktree(self, manager):
        await manager.create("task-001")
        await manager.remove("task-001")
        assert await manager.get("task-001") is None

    async def test_remove_nonexistent_raises(self, manager):
        with pytest.raises(WorktreeNotFoundError):
            await manager.remove("nonexistent")

    async def test_remove_idempotent(self, manager):
        await manager.create("task-001")
        await manager.remove("task-001")
        # Second remove should NOT raise
        await manager.remove("task-001")

    async def test_list_active(self, manager):
        await manager.create("task-001")
        await manager.create("task-002")
        active = await manager.list_active()
        assert len(active) == 2
        task_ids = {w.task_id for w in active}
        assert task_ids == {"task-001", "task-002"}

    async def test_isolation(self, manager):
        """Changes in one worktree don't affect another."""
        info1 = await manager.create("task-001")
        info2 = await manager.create("task-002")

        # Modify file in worktree 1
        (info1.path / "new_file.txt").write_text("from task 1")

        # Worktree 2 should NOT have this file
        assert not (info2.path / "new_file.txt").exists()

    async def test_merge_to_main(self, manager):
        info = await manager.create("task-001")
        (info.path / "feature.txt").write_text("feature code")
        await manager.commit_in_worktree("task-001", "Add feature")

        result = await manager.merge_to_main("task-001")
        assert result is True
        # Main should now have the file
        assert (manager._repo.path / "feature.txt").exists()

    async def test_prune(self, manager):
        """prune() runs git worktree prune without error."""
        await manager.prune()  # Should not raise

    async def test_cleanup_stale(self, manager):
        info = await manager.create("task-001")
        # Manually set creation time to old
        info.created_at = datetime.now() - timedelta(hours=48)
        cleaned = await manager.cleanup_stale(max_age_hours=24)
        assert "task-001" in cleaned

    async def test_has_changes(self, manager):
        info = await manager.create("task-001")
        assert not await manager.has_changes("task-001")
        (info.path / "dirty.txt").write_text("uncommitted")
        assert await manager.has_changes("task-001")

    async def test_get_diff(self, manager):
        info = await manager.create("task-001")
        (info.path / "new.txt").write_text("new content")
        diff = await manager.get_diff("task-001")
        assert "new.txt" in diff
```

### Integration Tests (`tests/test_worktree_integration.py`)

```python
class TestWorktreeEnv:
    async def test_context_manager_creates_and_cleans(self, manager):
        async with WorktreeEnv(manager, "task-001") as env:
            assert env.path.exists()
            (env.path / "code.py").write_text("print('hello')")

        # After exit, worktree should be cleaned up
        assert await manager.get("task-001") is None

    async def test_context_manager_keeps_on_failure(self, manager):
        with pytest.raises(RuntimeError):
            async with WorktreeEnv(manager, "task-001", cleanup_on_failure=False) as env:
                (env.path / "code.py").write_text("print('hello')")
                raise RuntimeError("task failed")

        # Worktree should still exist for debugging
        info = await manager.get("task-001")
        assert info is not None
        assert (info.path / "code.py").exists()

    async def test_aexit_force_fallback(self, manager, monkeypatch):
        """If remove() fails, __aexit__ tries force removal."""
        # Create worktree normally
        await manager.create("task-001")

        # Monkey-patch remove to fail on first call, succeed on force
        call_log = []
        original_remove = manager.remove

        async def failing_remove(task_id, force=False):
            call_log.append(("remove", task_id, force))
            if not force:
                raise WorktreeError("locked")
            # Force succeeds — delegate to original
            await original_remove(task_id)

        monkeypatch.setattr(manager, "remove", failing_remove)

        env = WorktreeEnv(manager, "task-001", cleanup_on_success=True)
        await env.__aenter__()
        await env.__aexit__(None, None, None)

        # Should have attempted normal then force
        assert ("remove", "task-001", False) in call_log
        assert ("remove", "task-001", True) in call_log

    async def test_aexit_never_raises(self, manager, monkeypatch):
        """__aexit__ swallows cleanup errors — never raises."""
        await manager.create("task-001")

        async def always_fail(task_id, **kwargs):
            raise WorktreeError("totally broken")

        monkeypatch.setattr(manager, "remove", always_fail)

        env = WorktreeEnv(manager, "task-001", cleanup_on_success=True)
        await env.__aenter__()
        # Should NOT raise even though remove always fails
        await env.__aexit__(None, None, None)


class TestEngineWithWorktrees:
    async def test_parallel_execution_with_isolated_worktrees(self):
        """Two tasks run in parallel, each in their own worktree."""
        repo = GitRepository(path=str(tmp_path))
        manager = WorktreeManager(repo=repo, max_worktrees=10)
        graph = TaskGraph(name="test")
        graph.add_task(Task(task_id="t1", description="task 1"))
        graph.add_task(Task(task_id="t2", description="task 2"))

        engine = ParallelExecutionEngine(
            graph=graph,
            executor=MockTaskExecutor(),
            worktree_manager=manager,  # NEW param
        )
        result = await engine.execute()

        assert result.status == ExecutionStatus.COMPLETED
        # Both worktrees should be cleaned up
        assert len(await manager.list_active()) == 0
```

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Git worktree command unavailable (old git) | Medium | Check git version on init; raise clear error if <2.5.0 |
| Disk space exhaustion from many worktrees | Medium | `max_worktrees` limit + `cleanup_stale()` |
| Worktree removal fails (locked files, permissions) | Low | Force fallback in `__aexit__`; log warning; don't crash engine |
| Branch already exists from previous run | Low | `prune()` at create time; `create()` checks and reuses or raises |
| Merge conflicts on `merge_to_main()` | Medium | Return False; caller decides strategy (manual resolution) |
| Performance: many worktrees = many git checkouts | Low | Worktrees are hard-linked; disk overhead is minimal |
| Orphaned branches after failed creation | Low | Explicit cleanup in `create()` error path |
| Stale git references after manual deletion | Low | `prune()` runs automatically before each `create()` |
| Max worktrees too low for large repos | Low | Configurable `max_worktrees` parameter |

---

## 10. Dependencies

- **Requires:** `GitRepository` (existing), Python 3.12+, git >= 2.5.0
- **Blocks:** P2-17 (Parallel Executor) — needs worktree isolation for real code execution
- **Integrates with:** `ParallelExecutionEngine`, `ExecutionContext`
- **No new external dependencies**

---

## 11. Alternatives Considered

### 11.1 Docker/Container Isolation

**Approach:** Run each task in a Docker container with a mounted repo.

- ✅ Stronger isolation (process, network, filesystem)
- ❌ Much heavier — Docker daemon required, image building overhead
- ❌ Slower startup (seconds vs. milliseconds for worktrees)
- ❌ Complex volume mounting for git operations
- **Verdict:** Overkill for our use case. Worktrees provide filesystem isolation without the operational burden. Could revisit if we need process-level sandboxing.

### 11.2 Temporary Directory Copies

**Approach:** `cp -r` or `rsync` the repo to a temp directory per task.

- ✅ Simple, no git knowledge needed
- ❌ Slow for large repos (full copy vs. hard-linked worktree)
- ❌ No git integration — can't create branches, commit, or merge back
- ❌ Wastes disk (full copy vs. shared .git)
- **Verdict:** Worktrees are strictly better for git-native workflows.

### 11.3 Branch-Only (No Worktree)

**Approach:** Use branches but all tasks share the same working directory, switching branches per task.

- ✅ Simple, no extra disk usage
- ❌ Defeats the purpose — no filesystem isolation, race conditions remain
- ❌ Can't run tasks in parallel (one working directory)
- **Verdict:** Contradicts the core requirement of parallel isolation.

### 11.4 Sparse Checkout + Worktree

**Approach:** Combine worktrees with sparse checkout to only materialize relevant subdirectories.

- ✅ Saves disk for monorepos where tasks only touch a subset
- ❌ Adds complexity (sparse-checkout configuration per task)
- ❌ Premature optimization for our current repo size
- **Verdict:** Defer. Easy to add later as a `sparse_paths` parameter on `create()`.

---

## 12. Known Limitations

1. **In-memory registry** — The `WorktreeManager` tracks active worktrees in an in-memory `dict[str, WorktreeInfo]`. This registry does NOT persist across process restarts. After a restart:
   - Call `prune()` to clean up stale git references
   - The manager can re-discover worktrees by scanning the worktree base directory and correlating with `git worktree list`
   - Alternatively, use `cleanup_all()` on startup if a clean slate is preferred

2. **Single-repo scope** — Each `WorktreeManager` instance manages worktrees for one repository. Multi-repo task isolation requires multiple manager instances.

3. **No cross-task file sharing** — Each worktree is fully isolated. If tasks need to share generated artifacts, they must do so through the execution context or external storage, not the filesystem.

4. **Git version requirement** — Requires git >= 2.5.0 (worktree support). Older git versions will fail with a clear error on `__init__`.

5. **Merge conflict resolution is manual** — `merge_to_main()` returns `False` on conflicts. Automated conflict resolution is out of scope.

6. **No persistent task-to-worktree mapping** — If the process crashes, manual inspection of `git worktree list` and the filesystem is needed to identify orphaned worktrees. The `prune()` and `cleanup_stale()` methods help recover.

---

## 13. Summary

| Aspect | Decision |
|--------|----------|
| Location | `src/omni/git/worktree.py` (standalone in git package) |
| Integration point | `ParallelExecutionEngine` via optional `worktree_manager` param |
| Isolation mechanism | Git worktrees with task-specific branches |
| Resource limit | `max_worktrees: int = 10` — configurable, checked before creation |
| Cleanup strategy | Auto on success, keep on failure, force fallback, prune on create |
| Error handling | Typed exceptions, orphaned branch cleanup, `__aexit__` never raises |
| Stale reference handling | `git worktree prune` on every `create()`, explicit `prune()` method |
| Test approach | Real git repos via `tmp_path`, unit + integration |
| Estimated effort | ~6.5 hours |
| Lines of code | ~310 new, ~25 modified |
