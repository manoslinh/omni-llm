"""
Result integration for parallel task execution.

Combines results from multiple tasks into a unified output,
handles file merging, conflict resolution, and final verification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..core.verifier import VerificationPipeline, VerificationResult
from ..task.models import TaskResult
from .conflicts import ConflictResolver, FileConflict

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationResult:
    """Result of integrating multiple task results."""

    success: bool
    merged_files: dict[str, str] = field(default_factory=dict)  # file_path -> content
    total_cost: float = 0.0
    total_tokens: int = 0
    commit_message: str = ""
    verification_result: VerificationResult | None = None
    summary: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ResultIntegrator:
    """
    Integrates results from multiple parallel tasks.

    Responsibilities:
    1. Merge file changes across successful tasks
    2. Aggregate costs and tokens
    3. Generate unified commit message
    4. Run verification pipeline on final result
    5. Handle partial success scenarios
    6. Generate summary of what was accomplished
    """

    def __init__(
        self,
        conflict_resolver: ConflictResolver | None = None,
        verification_pipeline: VerificationPipeline | None = None,
    ):
        """
        Initialize the result integrator.

        Args:
            conflict_resolver: ConflictResolver instance for handling file conflicts
            verification_pipeline: VerificationPipeline for final result verification
        """
        self.conflict_resolver = conflict_resolver or ConflictResolver()
        self.verification_pipeline = verification_pipeline
        logger.info("ResultIntegrator initialized")

    def integrate(
        self,
        results: list[TaskResult],
        original_goal: str,
    ) -> OrchestrationResult:
        """
        Integrate multiple task results into a unified output.

        Args:
            results: List of TaskResult objects from parallel execution
            original_goal: Original user goal/request

        Returns:
            OrchestrationResult with merged files, costs, verification, etc.
        """
        logger.info(
            f"Integrating {len(results)} task results for goal: {original_goal}"
        )

        # Separate successful and failed tasks
        successful_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]

        if not successful_results:
            logger.warning("No successful tasks to integrate")
            return OrchestrationResult(
                success=False,
                errors=["All tasks failed"],
                summary="No successful tasks to integrate",
            )

        # Extract file changes from successful tasks
        file_changes = self._extract_file_changes(successful_results)

        # Detect and resolve conflicts
        conflicts = self.conflict_resolver.detect_conflicts(successful_results)
        resolved_files = self._resolve_conflicts(file_changes, conflicts)

        # Aggregate costs and tokens
        total_cost = sum(r.cost for r in successful_results)
        total_tokens = sum(r.tokens_used for r in successful_results)

        # Generate commit message
        commit_message = self._generate_commit_message(
            successful_results, failed_results, original_goal
        )

        # Run verification on merged files
        verification_result = None
        if self.verification_pipeline and resolved_files:
            verification_result = self._run_verification_sync(resolved_files)

        # Generate summary
        summary = self.generate_summary(results)

        # Determine overall success
        # Success if we have merged files and verification passes (if run)
        overall_success = bool(resolved_files) and (
            verification_result is None or verification_result.passed
        )

        # Collect errors and warnings
        errors = []
        warnings = []

        if failed_results:
            warnings.append(f"{len(failed_results)} task(s) failed")
            for result in failed_results:
                warnings.append(f"Task {result.task_id}: {', '.join(result.errors)}")

        if verification_result and not verification_result.passed:
            errors.extend(verification_result.errors)
            warnings.extend(verification_result.warnings)

        if conflicts:
            warnings.append(f"Resolved {len(conflicts)} file conflict(s)")

        return OrchestrationResult(
            success=overall_success,
            merged_files=resolved_files,
            total_cost=total_cost,
            total_tokens=total_tokens,
            commit_message=commit_message,
            verification_result=verification_result,
            summary=summary,
            errors=errors,
            warnings=warnings,
            metadata={
                "successful_tasks": len(successful_results),
                "failed_tasks": len(failed_results),
                "conflicts_resolved": len(conflicts),
                "files_merged": len(resolved_files),
            },
        )

    def generate_summary(self, results: list[TaskResult]) -> str:
        """
        Generate a human-readable summary of what was accomplished.

        Args:
            results: List of TaskResult objects

        Returns:
            Summary string describing what was accomplished
        """
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        if not results:
            return "No tasks were executed."

        summary_parts = []

        # Overall statistics
        summary_parts.append(
            f"Executed {len(results)} tasks: "
            f"{len(successful)} succeeded, {len(failed)} failed."
        )

        # Successful tasks summary
        if successful:
            # Group by task type if available
            task_types: dict[str, int] = {}
            for result in successful:
                task_type = result.metadata.get("task_type", "unknown")
                task_types[task_type] = task_types.get(task_type, 0) + 1

            if task_types:
                type_summary = ", ".join(
                    f"{count} {task_type}" for task_type, count in task_types.items()
                )
                summary_parts.append(f"Successful tasks: {type_summary}")

            # File changes summary
            all_files = set()
            for result in successful:
                files_modified = result.outputs.get("files_modified", [])
                files_created = result.outputs.get("files_created", [])
                all_files.update(files_modified + files_created)

            if all_files:
                summary_parts.append(f"Modified {len(all_files)} file(s)")

        # Cost summary
        total_cost = sum(r.cost for r in successful)
        total_tokens = sum(r.tokens_used for r in successful)
        if total_cost > 0:
            summary_parts.append(
                f"Total cost: ${total_cost:.4f} ({total_tokens} tokens)"
            )

        # Failed tasks summary
        if failed:
            failed_ids = [r.task_id for r in failed]
            summary_parts.append(f"Failed tasks: {', '.join(failed_ids[:3])}")
            if len(failed) > 3:
                summary_parts.append(f"... and {len(failed) - 3} more")

        # For Phase 2, this is a simple text summary
        # In Phase 3, this could use an LLM to generate a more detailed narrative
        return "\n".join(summary_parts)

    def _extract_file_changes(
        self, results: list[TaskResult]
    ) -> dict[str, dict[str, Any]]:
        """
        Extract file changes from task results.

        Args:
            results: List of successful TaskResult objects

        Returns:
            Dictionary mapping file_path to task data
        """
        file_changes: dict[str, dict[str, Any]] = {}

        for result in results:
            # Get files modified by this task
            files_modified = result.outputs.get("files_modified", [])
            files_created = result.outputs.get("files_created", [])

            # Get file contents if available
            file_contents = result.outputs.get("file_contents", {})

            for file_path in set(files_modified + files_created):
                if file_path not in file_changes:
                    file_changes[file_path] = {
                        "tasks": [],
                        "contents": {},
                        "is_created": file_path in files_created,
                    }

                file_changes[file_path]["tasks"].append(result.task_id)

                # Store content if available
                if file_path in file_contents:
                    file_changes[file_path]["contents"][result.task_id] = file_contents[
                        file_path
                    ]
                elif "applied_edits" in result.outputs:
                    # Try to extract from edits if available
                    # This is a simplified approach for Phase 2
                    pass

        return file_changes

    def _resolve_conflicts(
        self,
        file_changes: dict[str, dict[str, Any]],
        conflicts: list[FileConflict],
    ) -> dict[str, str]:
        """
        Resolve file conflicts and merge changes.

        Args:
            file_changes: Dictionary of file changes from _extract_file_changes
            conflicts: List of detected FileConflict objects

        Returns:
            Dictionary mapping file_path to merged content
        """
        resolved_files: dict[str, str] = {}

        # Track which files have conflicts
        conflicted_files = {conflict.file_path for conflict in conflicts}

        for file_path, change_data in file_changes.items():
            if file_path in conflicted_files:
                # Find the conflict for this file
                conflict = next(
                    (c for c in conflicts if c.file_path == file_path), None
                )

                if conflict:
                    # Resolve the conflict
                    resolution = self.conflict_resolver.resolve(conflict)

                    if resolution.success and resolution.merged_content:
                        resolved_files[file_path] = resolution.merged_content
                        logger.info(f"Resolved conflict in {file_path}")
                    else:
                        logger.warning(
                            f"Failed to resolve conflict in {file_path}: "
                            f"{resolution.error}"
                        )
                        # Skip this file - it won't be included in final result
                else:
                    logger.warning(
                        f"File {file_path} marked as conflicted but no conflict object found"
                    )
            else:
                # No conflict - use the content from the only task that modified it
                task_ids = change_data["tasks"]
                contents = change_data["contents"]

                if len(task_ids) == 1 and task_ids[0] in contents:
                    # Single task modified this file, use its content
                    resolved_files[file_path] = contents[task_ids[0]]
                elif contents:
                    # Multiple tasks but no conflict detected (shouldn't happen)
                    # Use content from first task
                    first_task_id = list(contents.keys())[0]
                    resolved_files[file_path] = contents[first_task_id]
                    logger.warning(
                        f"File {file_path} modified by multiple tasks "
                        f"but no conflict detected. Using content from {first_task_id}"
                    )

        return resolved_files

    def _generate_commit_message(
        self,
        successful_results: list[TaskResult],
        failed_results: list[TaskResult],
        original_goal: str,
    ) -> str:
        """
        Generate a unified commit message summarizing the changes.

        Args:
            successful_results: List of successful TaskResult objects
            failed_results: List of failed TaskResult objects
            original_goal: Original user goal/request

        Returns:
            Commit message string
        """
        # Count file changes
        all_files = set()
        for result in successful_results:
            files_modified = result.outputs.get("files_modified", [])
            files_created = result.outputs.get("files_created", [])
            all_files.update(files_modified + files_created)

        # Build commit message
        lines = []

        # Title line
        if successful_results:
            lines.append(
                f"Achieve: {original_goal[:50]}{'...' if len(original_goal) > 50 else ''}"
            )

        # Body
        lines.append("")
        lines.append("## Summary")

        if successful_results:
            lines.append(f"- Executed {len(successful_results)} task(s) successfully")
            if all_files:
                lines.append(f"- Modified {len(all_files)} file(s)")

        if failed_results:
            lines.append(f"- {len(failed_results)} task(s) failed")

        # Task details
        if successful_results:
            lines.append("")
            lines.append("## Successful Tasks")

            for result in successful_results[:5]:  # Limit to 5 tasks
                task_desc = result.metadata.get("description", f"Task {result.task_id}")
                files_modified = result.outputs.get("files_modified", [])
                files_created = result.outputs.get("files_created", [])

                file_summary = []
                if files_modified:
                    file_summary.append(f"{len(files_modified)} modified")
                if files_created:
                    file_summary.append(f"{len(files_created)} created")

                file_info = f" ({', '.join(file_summary)})" if file_summary else ""
                lines.append(f"- {task_desc}{file_info}")

            if len(successful_results) > 5:
                lines.append(f"- ... and {len(successful_results) - 5} more")

        # Cost summary
        total_cost = sum(r.cost for r in successful_results)
        if total_cost > 0:
            lines.append("")
            lines.append("## Cost")
            lines.append(f"Total: ${total_cost:.4f}")

        return "\n".join(lines)

    async def _run_verification(self, files: dict[str, str]) -> VerificationResult:
        """
        Run verification on merged files.

        Args:
            files: Dictionary mapping file_path to content

        Returns:
            VerificationResult from the verification pipeline

        Note: In Phase 2, verification is skipped and returns a placeholder.
        TODO: In Phase 3, implement proper verification by:
          1. Writing files to temporary directory
          2. Calling verification_pipeline.verify() with file paths list
          3. Properly handling async/sync context
        """
        if not self.verification_pipeline:
            logger.warning("No verification pipeline configured")
            return VerificationResult(
                passed=True,
                errors=[],
                warnings=["No verification pipeline configured"],
                details={},
                name="no_verification",
            )

        # Phase 2: Verification is skipped, returns placeholder
        # Phase 3 TODO: Write files to temp directory and call verification_pipeline.verify()
        # verification_pipeline.verify() expects list[str] (file paths), not dict[str, str]
        # We would need to:
        # 1. Create temp directory
        # 2. Write each file content to temp location
        # 3. Call verification_pipeline.verify() with list of temp file paths
        # 4. Clean up temp files

        logger.info(f"Phase 2: Verification skipped for {len(files)} merged files")
        logger.debug(f"Files to verify: {list(files.keys())}")

        return VerificationResult(
            passed=True,
            errors=[],
            warnings=["Verification skipped in Phase 2 implementation"],
            details={
                "files_checked": list(files.keys()),
                "phase": 2,
                "note": "VerificationPipeline.verify() expects list[str] (file paths), "
                "but ResultIntegrator has dict[str, str] (file_path → content). "
                "Phase 3 will implement temp file writing.",
            },
            name="placeholder",
        )

    def _run_verification_sync(self, files: dict[str, str]) -> VerificationResult:
        """
        Synchronous wrapper for verification (for Phase 2).

        Args:
            files: Dictionary mapping file_path to content

        Returns:
            VerificationResult

        Note: In Phase 2, verification is skipped and returns a placeholder.
        Uses asyncio.run() in sync context which is acceptable for Phase 2.
        TODO: In Phase 3, refactor to avoid asyncio.run() in sync context.
        """
        # Phase 2: Uses asyncio.run() in sync context (acceptable for Phase 2)
        # Phase 3 TODO: Refactor to avoid asyncio.run() in sync context
        import asyncio

        try:
            return asyncio.run(self._run_verification(files))
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return VerificationResult(
                passed=False,
                errors=[f"Verification error: {e}"],
                warnings=[],
                details={"error": str(e)},
                name="error",
            )
