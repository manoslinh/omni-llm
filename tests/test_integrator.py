"""
Tests for the ResultIntegrator class (P2-19).
"""

from unittest.mock import AsyncMock, Mock

import pytest

from omni.core.verifier import VerificationPipeline, VerificationResult
from omni.orchestration.conflicts import (
    ConflictResolver,
    ConflictType,
    FileConflict,
    Resolution,
    ResolutionStrategy,
)
from omni.orchestration.integrator import (
    OrchestrationResult,
    ResultIntegrator,
)
from omni.task.models import TaskResult, TaskStatus


class TestResultIntegrator:
    """Test suite for ResultIntegrator."""

    def test_init(self):
        """Test ResultIntegrator initialization."""
        # Test with default parameters
        integrator = ResultIntegrator()
        assert integrator.conflict_resolver is not None
        assert isinstance(integrator.conflict_resolver, ConflictResolver)
        assert integrator.verification_pipeline is None

        # Test with custom parameters
        mock_resolver = Mock(spec=ConflictResolver)
        mock_pipeline = Mock(spec=VerificationPipeline)
        integrator = ResultIntegrator(
            conflict_resolver=mock_resolver,
            verification_pipeline=mock_pipeline,
        )
        assert integrator.conflict_resolver is mock_resolver
        assert integrator.verification_pipeline is mock_pipeline

    def test_generate_summary_empty(self):
        """Test generate_summary with empty results."""
        integrator = ResultIntegrator()
        summary = integrator.generate_summary([])
        assert "No tasks were executed" in summary

    def test_generate_summary_successful_only(self):
        """Test generate_summary with only successful tasks."""
        integrator = ResultIntegrator()

        # Create mock successful results
        results = [
            TaskResult(
                task_id="task1",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["file1.py", "file2.py"],
                    "files_created": ["new_file.py"],
                },
                metadata={"task_type": "code_generation"},
                tokens_used=100,
                cost=0.001,
            ),
            TaskResult(
                task_id="task2",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["file3.py"],
                },
                metadata={"task_type": "testing"},
                tokens_used=200,
                cost=0.002,
            ),
        ]

        summary = integrator.generate_summary(results)

        # Check summary contains expected information
        assert "Executed 2 tasks: 2 succeeded, 0 failed" in summary
        assert "Modified 3 file(s)" in summary or "Modified 4 file(s)" in summary
        assert "Total cost" in summary
        assert "0.003" in summary  # Total cost
        assert "300" in summary  # Total tokens

    def test_generate_summary_with_failures(self):
        """Test generate_summary with failed tasks."""
        integrator = ResultIntegrator()

        results = [
            TaskResult(
                task_id="task1",
                status=TaskStatus.COMPLETED,
                outputs={"files_modified": ["file1.py"]},
                tokens_used=100,
                cost=0.001,
            ),
            TaskResult(
                task_id="task2",
                status=TaskStatus.FAILED,
                errors=["Timeout error"],
                tokens_used=50,
                cost=0.0005,
            ),
        ]

        summary = integrator.generate_summary(results)

        assert "Executed 2 tasks: 1 succeeded, 1 failed" in summary
        assert "Failed tasks: task2" in summary

    def test_integrate_no_successful_tasks(self):
        """Test integrate when all tasks failed."""
        integrator = ResultIntegrator()

        results = [
            TaskResult(
                task_id="task1",
                status=TaskStatus.FAILED,
                errors=["Error 1"],
            ),
            TaskResult(
                task_id="task2",
                status=TaskStatus.FAILED,
                errors=["Error 2"],
            ),
        ]

        result = integrator.integrate(results, "Test goal")

        assert not result.success
        assert "All tasks failed" in result.errors
        assert len(result.merged_files) == 0
        assert result.total_cost == 0.0

    def test_integrate_single_successful_task(self):
        """Test integrate with a single successful task."""
        integrator = ResultIntegrator()

        results = [
            TaskResult(
                task_id="task1",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["test.py"],
                    "file_contents": {
                        "test.py": "print('Hello, World!')"
                    },
                },
                tokens_used=100,
                cost=0.001,
            ),
        ]

        result = integrator.integrate(results, "Add print statement")

        assert result.success
        assert len(result.merged_files) == 1
        assert "test.py" in result.merged_files
        assert result.merged_files["test.py"] == "print('Hello, World!')"
        assert result.total_cost == 0.001
        assert result.total_tokens == 100
        assert "Add print statement" in result.commit_message
        assert "Executed 1 task" in result.summary

    def test_integrate_multiple_tasks_no_conflicts(self):
        """Test integrate with multiple tasks modifying different files."""
        integrator = ResultIntegrator()

        results = [
            TaskResult(
                task_id="task1",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["file1.py"],
                    "file_contents": {
                        "file1.py": "content1"
                    },
                },
                tokens_used=100,
                cost=0.001,
            ),
            TaskResult(
                task_id="task2",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["file2.py"],
                    "file_contents": {
                        "file2.py": "content2"
                    },
                },
                tokens_used=200,
                cost=0.002,
            ),
        ]

        result = integrator.integrate(results, "Modify multiple files")

        assert result.success
        assert len(result.merged_files) == 2
        assert result.merged_files["file1.py"] == "content1"
        assert result.merged_files["file2.py"] == "content2"
        assert result.total_cost == 0.003
        assert result.total_tokens == 300
        assert "Modify multiple files" in result.commit_message

    def test_integrate_with_conflicts(self):
        """Test integrate with file conflicts."""
        # Mock conflict resolver
        mock_resolver = Mock(spec=ConflictResolver)

        # Create a mock conflict
        mock_conflict = FileConflict(
            file_path="conflict.py",
            task_ids=["task1", "task2"],
            conflict_type=ConflictType.OVERLAP,
        )

        # Mock conflict detection
        mock_resolver.detect_conflicts.return_value = [mock_conflict]

        # Mock conflict resolution
        mock_resolver.resolve.return_value = Resolution(
            strategy=ResolutionStrategy.AUTO_MERGE,
            success=True,
            merged_content="merged content",
        )

        integrator = ResultIntegrator(conflict_resolver=mock_resolver)

        results = [
            TaskResult(
                task_id="task1",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["conflict.py"],
                    "file_contents": {
                        "conflict.py": "content from task1"
                    },
                },
                tokens_used=100,
                cost=0.001,
            ),
            TaskResult(
                task_id="task2",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["conflict.py"],
                    "file_contents": {
                        "conflict.py": "content from task2"
                    },
                },
                tokens_used=200,
                cost=0.002,
            ),
        ]

        result = integrator.integrate(results, "Handle conflicts")

        # Verify conflict resolver was called
        mock_resolver.detect_conflicts.assert_called_once()
        mock_resolver.resolve.assert_called_once_with(mock_conflict)

        # Verify result
        assert result.success
        assert len(result.merged_files) == 1
        assert result.merged_files["conflict.py"] == "merged content"
        assert any("Resolved 1 file conflict" in warning for warning in result.warnings)

    def test_integrate_partial_success(self):
        """Test integrate with partial success (some tasks failed)."""
        integrator = ResultIntegrator()

        results = [
            TaskResult(
                task_id="task1",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["file1.py"],
                    "file_contents": {
                        "file1.py": "successful content"
                    },
                },
                tokens_used=100,
                cost=0.001,
            ),
            TaskResult(
                task_id="task2",
                status=TaskStatus.FAILED,
                errors=["Task failed"],
                tokens_used=50,
                cost=0.0005,
            ),
        ]

        result = integrator.integrate(results, "Partial success test")

        assert result.success  # Should still be successful if we have merged files
        assert len(result.merged_files) == 1
        assert "1 task(s) failed" in result.warnings
        assert "Partial success test" in result.commit_message

    def test_extract_file_changes(self):
        """Test _extract_file_changes method."""
        integrator = ResultIntegrator()

        results = [
            TaskResult(
                task_id="task1",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["modified.py"],
                    "files_created": ["new.py"],
                    "file_contents": {
                        "modified.py": "modified content",
                        "new.py": "new content",
                    },
                },
            ),
            TaskResult(
                task_id="task2",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["modified.py"],  # Same file
                    "file_contents": {
                        "modified.py": "different content"
                    },
                },
            ),
        ]

        file_changes = integrator._extract_file_changes(results)

        # Check structure
        assert "modified.py" in file_changes
        assert "new.py" in file_changes

        # Check modified.py has both tasks
        assert set(file_changes["modified.py"]["tasks"]) == {"task1", "task2"}
        assert file_changes["modified.py"]["contents"]["task1"] == "modified content"
        assert file_changes["modified.py"]["contents"]["task2"] == "different content"

        # Check new.py is marked as created
        assert file_changes["new.py"]["is_created"] is True

    def test_generate_commit_message(self):
        """Test _generate_commit_message method."""
        integrator = ResultIntegrator()

        successful_results = [
            TaskResult(
                task_id="task1",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["file1.py", "file2.py"],
                    "files_created": ["new.py"],
                },
                metadata={"description": "Fix bug in module"},
                cost=0.001,
            ),
            TaskResult(
                task_id="task2",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["test_file.py"],
                },
                metadata={"description": "Add tests"},
                cost=0.002,
            ),
        ]

        failed_results = [
            TaskResult(
                task_id="task3",
                status=TaskStatus.FAILED,
                errors=["Timeout"],
                cost=0.0005,
            ),
        ]

        commit_message = integrator._generate_commit_message(
            successful_results, failed_results, "Fix critical bug in authentication"
        )

        # Check commit message structure
        assert "Fix critical bug in authentication" in commit_message
        assert "## Summary" in commit_message
        assert "Executed 2 task(s) successfully" in commit_message
        assert "1 task(s) failed" in commit_message
        assert "## Successful Tasks" in commit_message
        assert "Fix bug in module" in commit_message
        assert "Add tests" in commit_message
        assert "## Cost" in commit_message
        assert "0.003" in commit_message  # Total cost

    @pytest.mark.asyncio
    async def test_run_verification(self):
        """Test _run_verification method."""
        # Mock verification pipeline
        mock_pipeline = AsyncMock(spec=VerificationPipeline)
        mock_pipeline.verify.return_value = VerificationResult(
            passed=True,
            errors=[],
            warnings=[],
            details={"checked": ["file1.py", "file2.py"]},
            name="test_verifier",
        )

        integrator = ResultIntegrator(verification_pipeline=mock_pipeline)

        files = {
            "file1.py": "content1",
            "file2.py": "content2",
        }

        result = await integrator._run_verification(files)

        # In Phase 2 implementation, _run_verification returns a placeholder
        # because verification is skipped (signature mismatch: dict[str, str] vs list[str])
        assert result.passed
        # The name should be "placeholder" in Phase 2
        assert result.name == "placeholder"
        # Verify the mock wasn't called (Phase 2 skips verification)
        mock_pipeline.verify.assert_not_called()
        # Check that details contain Phase 2 note
        assert "phase" in result.details
        assert result.details["phase"] == 2

    def test_run_verification_sync_no_pipeline(self):
        """Test _run_verification_sync without verification pipeline."""
        integrator = ResultIntegrator()  # No pipeline
        files = {"test.py": "content"}

        result = integrator._run_verification_sync(files)

        assert result.passed
        assert "No verification pipeline configured" in result.warnings

    def test_resolve_conflicts(self):
        """Test _resolve_conflicts method."""
        integrator = ResultIntegrator()

        # Mock file changes
        file_changes = {
            "conflict.py": {
                "tasks": ["task1", "task2"],
                "contents": {
                    "task1": "content1",
                    "task2": "content2",
                },
                "is_created": False,
            },
            "no_conflict.py": {
                "tasks": ["task3"],
                "contents": {
                    "task3": "content3",
                },
                "is_created": False,
            },
        }

        # Mock conflicts
        conflicts = [
            FileConflict(
                file_path="conflict.py",
                task_ids=["task1", "task2"],
                conflict_type=ConflictType.OVERLAP,
            ),
        ]

        # Mock conflict resolver
        mock_resolver = Mock(spec=ConflictResolver)
        mock_resolver.resolve.return_value = Resolution(
            strategy=ResolutionStrategy.AUTO_MERGE,
            success=True,
            merged_content="merged content",
        )

        integrator.conflict_resolver = mock_resolver

        resolved_files = integrator._resolve_conflicts(file_changes, conflicts)

        # Check resolved files
        assert "conflict.py" in resolved_files
        assert resolved_files["conflict.py"] == "merged content"
        assert "no_conflict.py" in resolved_files
        assert resolved_files["no_conflict.py"] == "content3"

        # Verify conflict resolver was called
        mock_resolver.resolve.assert_called_once()

    def test_resolve_conflicts_failed_resolution(self):
        """Test _resolve_conflicts when conflict resolution fails."""
        integrator = ResultIntegrator()

        file_changes = {
            "conflict.py": {
                "tasks": ["task1", "task2"],
                "contents": {
                    "task1": "content1",
                    "task2": "content2",
                },
                "is_created": False,
            },
        }

        conflicts = [
            FileConflict(
                file_path="conflict.py",
                task_ids=["task1", "task2"],
                conflict_type=ConflictType.OVERLAP,
            ),
        ]

        # Mock failed resolution
        mock_resolver = Mock(spec=ConflictResolver)
        mock_resolver.resolve.return_value = Resolution(
            strategy=ResolutionStrategy.AUTO_MERGE,
            success=False,
            error="Failed to merge",
        )

        integrator.conflict_resolver = mock_resolver

        resolved_files = integrator._resolve_conflicts(file_changes, conflicts)

        # File should not be in resolved files
        assert "conflict.py" not in resolved_files
        assert len(resolved_files) == 0

    def test_orchestration_result_dataclass(self):
        """Test OrchestrationResult dataclass."""
        result = OrchestrationResult(
            success=True,
            merged_files={"test.py": "content"},
            total_cost=0.001,
            total_tokens=100,
            commit_message="Test commit",
            summary="Test summary",
            errors=[],
            warnings=["Warning 1"],
            metadata={"key": "value"},
        )

        assert result.success is True
        assert len(result.merged_files) == 1
        assert result.total_cost == 0.001
        assert result.total_tokens == 100
        assert result.commit_message == "Test commit"
        assert result.summary == "Test summary"
        assert len(result.errors) == 0
        assert len(result.warnings) == 1
        assert result.metadata["key"] == "value"

    def test_integrate_with_verification_pipeline(self):
        """Test integrate with verification pipeline."""
        # Mock verification pipeline
        mock_pipeline = Mock(spec=VerificationPipeline)

        integrator = ResultIntegrator(verification_pipeline=mock_pipeline)

        results = [
            TaskResult(
                task_id="task1",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["test.py"],
                    "file_contents": {
                        "test.py": "test content"
                    },
                },
                tokens_used=100,
                cost=0.001,
            ),
        ]

        result = integrator.integrate(results, "Test with verification")

        # In Phase 2 implementation, verification is skipped
        # but the integrator should still work
        assert result.success
        assert len(result.merged_files) == 1
        # In Phase 2, verification_result should be set (but indicates it was skipped)
        assert result.verification_result is not None

    def test_integrate_verification_failure(self):
        """Test integrate when verification fails."""
        integrator = ResultIntegrator()

        # Note: In Phase 2, verification is always skipped
        # This test is for future implementation

        results = [
            TaskResult(
                task_id="task1",
                status=TaskStatus.COMPLETED,
                outputs={
                    "files_modified": ["test.py"],
                    "file_contents": {
                        "test.py": "test content"
                    },
                },
                tokens_used=100,
                cost=0.001,
            ),
        ]

        result = integrator.integrate(results, "Test verification failure")

        # In Phase 2, verification failure doesn't affect success
        # because verification is skipped
        assert result.success
