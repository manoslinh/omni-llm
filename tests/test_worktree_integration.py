"""
Integration tests for worktree integration with execution engine.
"""

import asyncio
from pathlib import Path

import pytest

from src.omni.execution.engine import ParallelExecutionEngine
from src.omni.execution.executor import MockTaskExecutor
from src.omni.execution.models import ExecutionStatus
from src.omni.git.repository import GitRepository
from src.omni.git.worktree import WorktreeCreationError, WorktreeManager
from src.omni.task.models import Task, TaskGraph


class TestEngineWithWorktrees:
    """Test ParallelExecutionEngine with worktree integration."""

    @pytest.mark.asyncio
    async def test_parallel_execution_with_isolated_worktrees(self, tmp_path):
        """Two tasks run in parallel, each in their own worktree."""
        # Create a git repo
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()
        repo = GitRepository(path=str(repo_path))
        (repo_path / "README.md").write_text("# Test")
        await repo._run_git(["add", "README.md"])
        await repo._run_git(["commit", "-m", "Initial commit"])

        # Create worktree manager
        manager = WorktreeManager(repo=repo, max_worktrees=10)

        # Create task graph
        graph = TaskGraph(name="test")
        graph.add_task(Task(task_id="t1", description="task 1"))
        graph.add_task(Task(task_id="t2", description="task 2"))

        # Create mock executor that writes to worktree
        class WorktreeAwareExecutor(MockTaskExecutor):
            async def execute(self, task, context):
                if context.worktree_path:
                    # Write a file in the worktree
                    worktree_path = Path(context.worktree_path)
                    (worktree_path / f"{task.task_id}.txt").write_text(f"from {task.task_id}")
                return {"output": f"executed {task.task_id}"}

        # Create engine with worktree manager
        engine = ParallelExecutionEngine(
            graph=graph,
            executor=WorktreeAwareExecutor(),
            worktree_manager=manager,
        )

        # Execute
        result = await engine.execute()

        assert result.status == ExecutionStatus.COMPLETED
        assert len(result.results) == 2

        # Both worktrees should be cleaned up
        assert len(await manager.list_active()) == 0

        # Main repo should NOT have the task files
        assert not (repo_path / "t1.txt").exists()
        assert not (repo_path / "t2.txt").exists()

    @pytest.mark.asyncio
    async def test_engine_without_worktrees(self, tmp_path):
        """Engine works without worktree manager (backward compatibility)."""
        # Create task graph
        graph = TaskGraph(name="test")
        graph.add_task(Task(task_id="t1", description="task 1"))

        # Create engine WITHOUT worktree manager
        engine = ParallelExecutionEngine(
            graph=graph,
            executor=MockTaskExecutor(success_rate=1.0),
            # No worktree_manager parameter
        )

        # Should execute successfully
        result = await engine.execute()
        assert result.status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_worktree_creation_failure_fallback(self, tmp_path, monkeypatch):
        """Test that engine handles worktree creation failure gracefully."""
        # Create a git repo
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()
        repo = GitRepository(path=str(repo_path))
        (repo_path / "README.md").write_text("# Test")
        await repo._run_git(["add", "README.md"])
        await repo._run_git(["commit", "-m", "Initial commit"])

        # Create worktree manager
        manager = WorktreeManager(repo=repo, max_worktrees=10)

        # Monkey-patch create to fail
        async def failing_create(task_id, base_branch="main"):
            raise WorktreeCreationError("Simulated failure")

        monkeypatch.setattr(manager, "create", failing_create)

        # Create task graph
        graph = TaskGraph(name="test")
        graph.add_task(Task(task_id="t1", description="task 1"))

        # Create mock executor
        class TrackingExecutor(MockTaskExecutor):
            def __init__(self):
                super().__init__()
                self.execution_contexts = []

            async def execute(self, task, context):
                self.execution_contexts.append(context)
                return {"output": f"executed {task.task_id}"}

        executor = TrackingExecutor()

        # Create engine with worktree manager
        engine = ParallelExecutionEngine(
            graph=graph,
            executor=executor,
            worktree_manager=manager,
        )

        # Should still execute (worktree creation failure shouldn't crash)
        result = await engine.execute()

        assert result.status == ExecutionStatus.COMPLETED
        assert len(executor.execution_contexts) == 1

        # Context should have no worktree_path since creation failed
        context = executor.execution_contexts[0]
        assert context.worktree_path is None

    @pytest.mark.asyncio
    async def test_concurrent_worktree_creation(self, tmp_path):
        """Test that concurrent task execution creates separate worktrees."""
        # Create a git repo
        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()
        repo = GitRepository(path=str(repo_path))
        (repo_path / "README.md").write_text("# Test")
        await repo._run_git(["add", "README.md"])
        await repo._run_git(["commit", "-m", "Initial commit"])

        # Create worktree manager
        manager = WorktreeManager(repo=repo, max_worktrees=10)

        # Create task graph with independent tasks
        graph = TaskGraph(name="test")
        graph.add_task(Task(task_id="t1", description="task 1"))
        graph.add_task(Task(task_id="t2", description="task 2"))
        graph.add_task(Task(task_id="t3", description="task 3"))

        # Track which worktrees were used
        worktree_paths = []

        # Create executor that tracks worktree usage
        class TrackingExecutor(MockTaskExecutor):
            async def execute(self, task, context):
                if context.worktree_path:
                    worktree_paths.append((task.task_id, context.worktree_path))
                # Simulate some work
                await asyncio.sleep(0.01)
                return {"output": f"executed {task.task_id}"}

        # Create engine with worktree manager and high concurrency
        from src.omni.execution.config import ExecutionConfig
        engine = ParallelExecutionEngine(
            graph=graph,
            executor=TrackingExecutor(),
            worktree_manager=manager,
            config=ExecutionConfig(max_concurrent=3),  # Run all in parallel
        )

        # Execute
        result = await engine.execute()

        assert result.status == ExecutionStatus.COMPLETED
        assert len(worktree_paths) == 3

        # Each task should have its own worktree path
        task_ids = {task_id for task_id, _ in worktree_paths}
        assert task_ids == {"t1", "t2", "t3"}

        # All worktrees should be unique
        paths = {path for _, path in worktree_paths}
        assert len(paths) == 3

        # All worktrees should be cleaned up
        assert len(await manager.list_active()) == 0
