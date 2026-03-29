"""
Tests for conflict resolution in parallel execution.
"""

import pytest

from omni.orchestration.conflicts import (
    ConflictResolver,
    ConflictType,
    FileConflict,
    Resolution,
    ResolutionStrategy,
)
from omni.task.models import TaskResult, TaskStatus


class TestConflictResolver:
    """Tests for ConflictResolver class."""

    def test_init(self) -> None:
        """Test ConflictResolver initialization."""
        resolver = ConflictResolver(llm_merge_threshold=5)
        assert resolver.llm_merge_threshold == 5

    def test_detect_conflicts_no_conflicts(self) -> None:
        """Test conflict detection when no conflicts exist."""
        resolver = ConflictResolver()

        # Create task results that modify different files
        results = [
            TaskResult(
                task_id="task1",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["file1.py"],
                    "files_created": [],
                    "files_deleted": [],
                },
            ),
            TaskResult(
                task_id="task2",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["file2.py"],
                    "files_created": [],
                    "files_deleted": [],
                },
            ),
        ]

        conflicts = resolver.detect_conflicts(results)
        assert len(conflicts) == 0

    def test_detect_conflicts_simple_conflict(self) -> None:
        """Test conflict detection when multiple tasks modify same file."""
        resolver = ConflictResolver()

        # Create task results that modify the same file
        results = [
            TaskResult(
                task_id="task1",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["common.py"],
                    "files_created": [],
                    "files_deleted": [],
                    "file_contents": {
                        "common.py": "def task1():\n    return 1\n"
                    },
                },
            ),
            TaskResult(
                task_id="task2",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["common.py"],
                    "files_created": [],
                    "files_deleted": [],
                    "file_contents": {
                        "common.py": "def task2():\n    return 2\n"
                    },
                },
            ),
        ]

        conflicts = resolver.detect_conflicts(results)
        assert len(conflicts) == 1

        conflict = conflicts[0]
        assert conflict.file_path == "common.py"
        assert set(conflict.task_ids) == {"task1", "task2"}
        assert conflict.conflict_type == ConflictType.OVERLAP  # Default when can't analyze

    def test_detect_conflicts_skips_failed_tasks(self) -> None:
        """Test that failed tasks are skipped in conflict detection."""
        resolver = ConflictResolver()

        results = [
            TaskResult(
                task_id="task1",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["file.py"],
                },
            ),
            TaskResult(
                task_id="task2",
                status=TaskStatus.FAILED,  # Failed task
                outputs={
                    "files_modified": ["file.py"],
                },
            ),
        ]

        conflicts = resolver.detect_conflicts(results)
        assert len(conflicts) == 0  # No conflict because task2 failed

    def test_resolve_independent_conflict_auto_merge(self) -> None:
        """Test auto-merge for independent conflicts."""
        resolver = ConflictResolver()

        conflict = FileConflict(
            file_path="test.py",
            task_ids=["task1", "task2"],
            conflict_type=ConflictType.INDEPENDENT,
            task_contents={
                "task1": "def task1():\n    return 1\n",
                "task2": "def task1():\n    return 1\n",  # Same content
            },
        )

        resolution = resolver.resolve(conflict)
        assert resolution.strategy == ResolutionStrategy.AUTO_MERGE
        assert resolution.success is True
        assert resolution.requires_sequential is False
        assert resolution.merged_content == "def task1():\n    return 1\n"

    def test_resolve_overlap_conflict_sequential(self) -> None:
        """Test sequential resolution for overlapping conflicts."""
        resolver = ConflictResolver()

        conflict = FileConflict(
            file_path="test.py",
            task_ids=["task1", "task2"],
            conflict_type=ConflictType.OVERLAP,
            task_contents={
                "task1": "content1",
                "task2": "content2",
            },
        )

        resolution = resolver.resolve(conflict)
        assert resolution.strategy == ResolutionStrategy.SEQUENTIAL
        assert resolution.success is True  # Has a resolution strategy
        assert resolution.requires_sequential is True
        assert resolution.merged_content is None

    def test_resolve_adjacent_conflict_auto_merge(self) -> None:
        """Test auto-merge attempt for adjacent conflicts."""
        resolver = ConflictResolver()

        conflict = FileConflict(
            file_path="test.py",
            task_ids=["task1", "task2"],
            conflict_type=ConflictType.ADJACENT,
            task_contents={
                "task1": "def task1():\n    return 1\n",
                "task2": "def task2():\n    return 2\n",  # Different content
            },
        )

        resolution = resolver.resolve(conflict)
        assert resolution.strategy == ResolutionStrategy.AUTO_MERGE
        # For Phase 2, auto-merge attempts to merge different content
        # In a real implementation, this would require proper diff analysis
        assert resolution.success is True  # Our simple implementation succeeds
        assert resolution.requires_sequential is False
        assert resolution.merged_content is not None

    def test_choose_resolution_strategy(self) -> None:
        """Test strategy selection logic."""
        resolver = ConflictResolver(llm_merge_threshold=2)

        # Independent -> AUTO_MERGE
        conflict1 = FileConflict(
            file_path="test1.py",
            task_ids=["task1"],
            conflict_type=ConflictType.INDEPENDENT,
        )
        assert resolver._choose_resolution_strategy(conflict1) == ResolutionStrategy.AUTO_MERGE

        # Adjacent -> AUTO_MERGE
        conflict2 = FileConflict(
            file_path="test2.py",
            task_ids=["task1", "task2"],
            conflict_type=ConflictType.ADJACENT,
        )
        assert resolver._choose_resolution_strategy(conflict2) == ResolutionStrategy.AUTO_MERGE

        # Overlap with few tasks -> SEQUENTIAL
        conflict3 = FileConflict(
            file_path="test3.py",
            task_ids=["task1", "task2"],  # 2 tasks <= threshold
            conflict_type=ConflictType.OVERLAP,
        )
        assert resolver._choose_resolution_strategy(conflict3) == ResolutionStrategy.SEQUENTIAL

        # Overlap with many tasks -> LLM_MERGE
        conflict4 = FileConflict(
            file_path="test4.py",
            task_ids=["task1", "task2", "task3"],  # 3 tasks > threshold
            conflict_type=ConflictType.OVERLAP,
        )
        assert resolver._choose_resolution_strategy(conflict4) == ResolutionStrategy.LLM_MERGE

    def test_merge_task_contents_identical(self) -> None:
        """Test merging when task contents are identical."""
        resolver = ConflictResolver()

        conflict = FileConflict(
            file_path="test.py",
            task_ids=["task1", "task2"],
            conflict_type=ConflictType.INDEPENDENT,
            task_contents={
                "task1": "line1\nline2\nline3\n",
                "task2": "line1\nline2\nline3\n",
            },
        )

        resolution = resolver._merge_task_contents(conflict)
        assert resolution.success is True
        assert resolution.merged_content == "line1\nline2\nline3\n"

    def test_merge_task_contents_different(self) -> None:
        """Test merging when task contents differ."""
        resolver = ConflictResolver()

        conflict = FileConflict(
            file_path="test.py",
            task_ids=["task1", "task2"],
            conflict_type=ConflictType.INDEPENDENT,
            task_contents={
                "task1": "line1\nline2\n",
                "task2": "line1\nline3\n",
            },
        )

        resolution = resolver._merge_task_contents(conflict)
        assert resolution.success is True
        # Should merge lines somehow
        assert resolution.merged_content is not None

    def test_batch_resolve(self) -> None:
        """Test batch resolution of multiple conflicts."""
        resolver = ConflictResolver()

        conflicts = [
            FileConflict(
                file_path="file1.py",
                task_ids=["task1", "task2"],
                conflict_type=ConflictType.INDEPENDENT,
                task_contents={
                    "task1": "content1",
                    "task2": "content1",
                },
            ),
            FileConflict(
                file_path="file2.py",
                task_ids=["task3", "task4"],
                conflict_type=ConflictType.OVERLAP,
            ),
        ]

        results = resolver.batch_resolve(conflicts)
        assert len(results) == 2
        assert "file1.py" in results
        assert "file2.py" in results

        # file1.py should auto-merge successfully
        assert results["file1.py"].strategy == ResolutionStrategy.AUTO_MERGE
        assert results["file1.py"].success is True

        # file2.py should require sequential execution
        assert results["file2.py"].strategy == ResolutionStrategy.SEQUENTIAL
        assert results["file2.py"].requires_sequential is True

    def test_llm_merge_not_implemented(self) -> None:
        """Test that LLM merge returns not implemented error."""
        resolver = ConflictResolver()

        conflict = FileConflict(
            file_path="test.py",
            task_ids=["task1", "task2", "task3", "task4"],  # Many tasks
            conflict_type=ConflictType.OVERLAP,
        )

        resolution = resolver.resolve(conflict)
        assert resolution.strategy == ResolutionStrategy.LLM_MERGE
        assert resolution.success is False
        assert "not implemented" in str(resolution.error).lower()
        assert resolution.requires_sequential is True


class TestFileConflict:
    """Tests for FileConflict dataclass."""

    def test_creation(self) -> None:
        """Test FileConflict creation."""
        conflict = FileConflict(
            file_path="test.py",
            task_ids=["task1", "task2"],
            conflict_type=ConflictType.OVERLAP,
        )

        assert conflict.file_path == "test.py"
        assert conflict.task_ids == ["task1", "task2"]
        assert conflict.conflict_type == ConflictType.OVERLAP
        assert conflict.resolution is None
        assert conflict.original_content is None
        assert conflict.task_contents == {}


class TestResolution:
    """Tests for Resolution dataclass."""

    def test_creation(self) -> None:
        """Test Resolution creation."""
        resolution = Resolution(
            strategy=ResolutionStrategy.AUTO_MERGE,
            success=True,
            merged_content="merged content",
        )

        assert resolution.strategy == ResolutionStrategy.AUTO_MERGE
        assert resolution.success is True
        assert resolution.merged_content == "merged content"
        assert resolution.error is None
        assert resolution.requires_sequential is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
