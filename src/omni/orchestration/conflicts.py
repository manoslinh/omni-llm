"""
Conflict resolution for parallel task execution.

Detects and resolves file conflicts when multiple tasks modify the same file.
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..task.models import TaskResult

logger = logging.getLogger(__name__)


class ConflictType(StrEnum):
    """Types of file conflicts."""

    OVERLAP = "overlap"  # Changes overlap in content
    ADJACENT = "adjacent"  # Changes are close but don't overlap
    INDEPENDENT = "independent"  # Changes are in separate sections


class ResolutionStrategy(StrEnum):
    """Conflict resolution strategies."""

    AUTO_MERGE = "auto_merge"  # Automatically merge non-overlapping changes
    SEQUENTIAL = "sequential"  # Re-execute tasks sequentially
    LLM_MERGE = "llm_merge"  # Use LLM to merge conflicting changes


@dataclass
class FileConflict:
    """Represents a conflict in a file modified by multiple tasks."""

    file_path: str
    task_ids: list[str]
    conflict_type: ConflictType
    resolution: ResolutionStrategy | None = None
    original_content: str | None = None
    task_contents: dict[str, str] = field(default_factory=dict)  # task_id -> modified content


@dataclass
class Resolution:
    """Result of conflict resolution attempt."""

    strategy: ResolutionStrategy
    success: bool
    merged_content: str | None = None
    error: str | None = None
    requires_sequential: bool = False  # Whether tasks need to be re-executed sequentially


class ConflictResolver:
    """
    Detects and resolves file conflicts from parallel task execution.

    Conflict detection:
    1. Find files modified by multiple tasks
    2. Compare changes to classify conflict type
    3. Determine appropriate resolution strategy

    Resolution strategies:
    1. Auto-merge: For independent or adjacent non-overlapping changes
    2. Sequential re-execution: For overlapping changes
    3. LLM-assisted merge: Fallback for complex conflicts
    """

    def __init__(self, llm_merge_threshold: int = 3):
        """
        Initialize the conflict resolver.

        Args:
            llm_merge_threshold: Maximum number of conflicting tasks before
                                 falling back to LLM merge (default: 3)
        """
        self.llm_merge_threshold = llm_merge_threshold
        logger.info(f"ConflictResolver initialized (llm_merge_threshold={llm_merge_threshold})")

    def detect_conflicts(self, results: list[TaskResult]) -> list[FileConflict]:
        """
        Detect file conflicts from task results.

        Args:
            results: List of TaskResult objects from parallel execution
        Returns:
            List of FileConflict objects for files with conflicts
        """
        # Group files by file path to find conflicts
        file_to_tasks: dict[str, list[tuple[str, dict[str, Any]]]] = {}

        for result in results:
            if not result.success:
                continue

            # Extract file changes from task outputs
            # Expected format: outputs contains 'files_modified', 'files_created', 'files_deleted'
            # and potentially 'file_contents' or similar
            files_modified = result.outputs.get("files_modified", [])
            files_created = result.outputs.get("files_created", [])

            # For conflict detection, we care about all files that were touched
            all_files = set(files_modified + files_created)

            # Skip deleted files for conflict detection (they're gone)
            for file_path in all_files:
                if file_path not in file_to_tasks:
                    file_to_tasks[file_path] = []

                # Get file content if available
                file_content = None
                if "file_contents" in result.outputs and file_path in result.outputs["file_contents"]:
                    file_content = result.outputs["file_contents"][file_path]
                elif "applied_edits" in result.outputs:
                    # Try to reconstruct from edits
                    file_content = self._reconstruct_file_content(
                        file_path, result.outputs.get("applied_edits", [])
                    )

                file_to_tasks[file_path].append((result.task_id, {
                    "content": file_content,
                    "files_modified": files_modified,
                    "files_created": files_created,
                }))

        # Identify conflicts (files modified by multiple tasks)
        conflicts: list[FileConflict] = []
        for file_path, task_data in file_to_tasks.items():
            if len(task_data) > 1:
                # Multiple tasks modified this file - potential conflict
                task_ids = [task_id for task_id, _ in task_data]
                task_contents = {
                    task_id: data["content"]
                    for task_id, data in task_data
                    if data["content"] is not None
                }

                # Classify the conflict type
                conflict_type = self._classify_conflict(file_path, task_data)

                conflict = FileConflict(
                    file_path=file_path,
                    task_ids=task_ids,
                    conflict_type=conflict_type,
                    task_contents=task_contents,
                )
                conflicts.append(conflict)

                logger.info(
                    f"Detected conflict in {file_path}: "
                    f"tasks={task_ids}, type={conflict_type}"
                )

        return conflicts

    def _classify_conflict(
        self,
        file_path: str,
        task_data: list[tuple[str, dict[str, Any]]]
    ) -> ConflictType:
        """
        Classify the type of conflict based on file changes.

        Args:
            file_path: Path to the file
            task_data: List of (task_id, data) tuples
        Returns:
            ConflictType classification
        """
        if len(task_data) < 2:
            return ConflictType.INDEPENDENT

        # For now, use a simple heuristic:
        # - If we have actual content to compare, analyze diffs
        # - Otherwise, assume worst-case (OVERLAP)

        # Check if we have content for all tasks
        all_have_content = all(data["content"] is not None for _, data in task_data)

        if not all_have_content:
            # Without content, we can't determine overlap - assume worst case
            logger.warning(f"Cannot analyze conflict for {file_path}: missing file content")
            return ConflictType.OVERLAP

        # Compare contents pairwise to detect overlaps
        contents = [data["content"] for _, data in task_data]

        # Simple heuristic: if all contents are identical, no real conflict
        if all(c == contents[0] for c in contents):
            return ConflictType.INDEPENDENT

        # For Phase 2, use a simple approach
        # In a real implementation, we would:
        # 1. Compute diffs between original and each modified version
        # 2. Check if change ranges overlap
        # 3. Classify as OVERLAP, ADJACENT, or INDEPENDENT

        # For now, return OVERLAP as conservative default
        # The PHASE2_PLAN.md says: "Don't over-engineer — a simple diff-based approach is fine for now."
        return ConflictType.OVERLAP

    def _reconstruct_file_content(
        self,
        file_path: str,
        applied_edits: list[dict[str, Any]]
    ) -> str | None:
        """
        Reconstruct file content from applied edits.

        Args:
            file_path: Path to the file
            applied_edits: List of edit dictionaries

        Returns:
            Reconstructed content or None if not possible
        """
        # This is a placeholder implementation
        # In a real system, we would need access to the original file
        # and apply the edits to reconstruct the modified version
        return None

    def resolve(self, conflict: FileConflict, original_content: str | None = None) -> Resolution:
        """
        Attempt to resolve a file conflict.

        Args:
            conflict: FileConflict to resolve
            original_content: Original file content before any changes (optional)

        Returns:
            Resolution object with result
        """
        # Store original content if provided
        if original_content is not None:
            conflict.original_content = original_content

        # Determine resolution strategy based on conflict type
        strategy = self._choose_resolution_strategy(conflict)
        conflict.resolution = strategy

        logger.info(
            f"Resolving conflict in {conflict.file_path}: "
            f"strategy={strategy}, tasks={conflict.task_ids}"
        )

        # Apply the chosen strategy
        if strategy == ResolutionStrategy.AUTO_MERGE:
            return self._auto_merge(conflict)
        elif strategy == ResolutionStrategy.SEQUENTIAL:
            return self._sequential_resolution(conflict)
        else:  # strategy == ResolutionStrategy.LLM_MERGE
            return self._llm_merge(conflict)

    def _choose_resolution_strategy(self, conflict: FileConflict) -> ResolutionStrategy:
        """
        Choose the appropriate resolution strategy for a conflict.

        Args:
            conflict: FileConflict to resolve

        Returns:
            ResolutionStrategy to use
        """
        # Simple strategy selection based on conflict type and number of tasks
        if conflict.conflict_type == ConflictType.INDEPENDENT:
            # Independent changes can be auto-merged
            return ResolutionStrategy.AUTO_MERGE

        elif conflict.conflict_type == ConflictType.ADJACENT:
            # Adjacent changes might be auto-mergeable with care
            # For now, try auto-merge first
            return ResolutionStrategy.AUTO_MERGE

        else:  # conflict.conflict_type == ConflictType.OVERLAP
            # Overlapping changes are harder
            if len(conflict.task_ids) <= self.llm_merge_threshold:
                # Few tasks: try sequential re-execution first
                return ResolutionStrategy.SEQUENTIAL
            else:
                # Many tasks: fall back to LLM merge
                return ResolutionStrategy.LLM_MERGE

    def _auto_merge(self, conflict: FileConflict) -> Resolution:
        """
        Attempt to auto-merge non-overlapping changes.

        Args:
            conflict: FileConflict to resolve

        Returns:
            Resolution object
        """
        # Check if we have enough information to merge
        if not conflict.task_contents or len(conflict.task_contents) < 2:
            return Resolution(
                strategy=ResolutionStrategy.AUTO_MERGE,
                success=False,
                error="Insufficient content for auto-merge",
                requires_sequential=True,
            )

        if conflict.original_content is None:
            # Without original content, we can't properly merge
            # Try to merge task contents directly
            return self._merge_task_contents(conflict)

        # For Phase 2, implement a simple merge
        # In a real implementation, we would:
        # 1. Compute diffs from original to each task's version
        # 2. Check that diffs don't overlap
        # 3. Apply all non-overlapping diffs to original

        # For now, if we have original content and one task's content,
        # and conflict is INDEPENDENT, we can use one task's version
        # (This is a simplification for Phase 2)
        if conflict.conflict_type == ConflictType.INDEPENDENT:
            # Pick the first task's content
            first_task_id = list(conflict.task_contents.keys())[0]
            merged_content = conflict.task_contents[first_task_id]

            return Resolution(
                strategy=ResolutionStrategy.AUTO_MERGE,
                success=True,
                merged_content=merged_content,
                requires_sequential=False,
            )

        # For other cases, auto-merge fails
        return Resolution(
            strategy=ResolutionStrategy.AUTO_MERGE,
            success=False,
            error=f"Auto-merge not supported for {conflict.conflict_type} conflicts",
            requires_sequential=True,
        )

    def _merge_task_contents(self, conflict: FileConflict) -> Resolution:
        """
        Merge task contents when original content is not available.

        Args:
            conflict: FileConflict to resolve

        Returns:
            Resolution object
        """
        # Simple heuristic: if all task contents are identical, use that
        contents = list(conflict.task_contents.values())
        if all(c == contents[0] for c in contents):
            return Resolution(
                strategy=ResolutionStrategy.AUTO_MERGE,
                success=True,
                merged_content=contents[0],
                requires_sequential=False,
            )

        # Otherwise, try to find common lines
        merged_lines = []
        for i, content in enumerate(contents):
            lines = content.splitlines(keepends=True)
            if i == 0:
                merged_lines = lines
            else:
                # Simple line-by-line comparison
                # This is very naive but works for Phase 2
                merged_lines = self._merge_lines(merged_lines, lines)

        merged_content = "".join(merged_lines)

        return Resolution(
            strategy=ResolutionStrategy.AUTO_MERGE,
            success=True,
            merged_content=merged_content,
            requires_sequential=False,
        )

    def _merge_lines(self, lines1: list[str], lines2: list[str]) -> list[str]:
        """
        Naive line merging for Phase 2 implementation.

        Args:
            lines1: First list of lines
            lines2: Second list of lines

        Returns:
            Merged list of lines
        """
        # Very simple: use difflib to find common sequences
        matcher = difflib.SequenceMatcher(None, lines1, lines2)
        merged = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                # Both have these lines
                merged.extend(lines1[i1:i2])
            elif tag == 'replace':
                # Conflict: choose lines from first version
                merged.extend(lines1[i1:i2])
            elif tag == 'delete':
                # Only in first
                merged.extend(lines1[i1:i2])
            elif tag == 'insert':
                # Only in second
                merged.extend(lines2[j1:j2])

        return merged

    def _sequential_resolution(self, conflict: FileConflict) -> Resolution:
        """
        Mark conflict for sequential re-execution.

        Args:
            conflict: FileConflict to resolve

        Returns:
            Resolution object indicating sequential execution needed
        """
        return Resolution(
            strategy=ResolutionStrategy.SEQUENTIAL,
            success=True,  # Success means we have a resolution strategy
            merged_content=None,
            requires_sequential=True,
        )

    def _llm_merge(self, conflict: FileConflict) -> Resolution:
        """
        Use LLM to merge conflicting changes (placeholder implementation).

        Args:
            conflict: FileConflict to resolve

        Returns:
            Resolution object
        """
        # This is a placeholder for Phase 2
        # In Phase 3, this would call an LLM with the original content
        # and all task modifications to produce a merged version

        logger.warning(
            f"LLM merge requested for {conflict.file_path} "
            f"(tasks={conflict.task_ids}) - not implemented in Phase 2"
        )

        return Resolution(
            strategy=ResolutionStrategy.LLM_MERGE,
            success=False,
            error="LLM merge not implemented in Phase 2",
            requires_sequential=True,
        )

    def batch_resolve(self, conflicts: list[FileConflict]) -> dict[str, Resolution]:
        """
        Resolve multiple conflicts in batch.

        Args:
            conflicts: List of FileConflict objects

        Returns:
            Dictionary mapping file_path to Resolution
        """
        results = {}
        for conflict in conflicts:
            resolution = self.resolve(conflict)
            results[conflict.file_path] = resolution

        return results
