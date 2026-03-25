"""
Edit Applier.

Applies edits to files and tracks the results.
"""

import asyncio
import logging
import os
from pathlib import Path

from .models import ApplyResult, Edit

logger = logging.getLogger(__name__)


class EditApplier:
    """
    Applies edits to files.

    Handles:
    - Reading file contents
    - Finding and replacing text
    - Creating new files
    - Deleting files (if REPLACE with empty text)
    - Tracking what was modified
    """

    def __init__(self, base_path: str | None = None):
        """
        Initialize the edit applier.

        Args:
            base_path: Base directory for relative file paths
        """
        self.base_path = Path(base_path or os.getcwd()).resolve()
        logger.info(f"EditApplier initialized with base path: {self.base_path}")

    async def apply(self, edits: list[Edit]) -> ApplyResult:
        """
        Apply edits to files.

        Args:
            edits: List of edits to apply

        Returns:
            ApplyResult with details of what was modified
        """
        files_modified = []
        files_created = []
        files_deleted = []
        errors = []

        # Group edits by file
        edits_by_file: dict[str, list[Edit]] = {}
        for edit in edits:
            if edit.file_path not in edits_by_file:
                edits_by_file[edit.file_path] = []
            edits_by_file[edit.file_path].append(edit)

        # Apply edits to each file
        for file_path, file_edits in edits_by_file.items():
            try:
                result = await self._apply_to_file(file_path, file_edits)

                if result["created"]:
                    files_created.append(file_path)
                elif result["deleted"]:
                    files_deleted.append(file_path)
                elif result["modified"]:
                    files_modified.append(file_path)

                if result["error"]:
                    errors.append(result["error"])

            except Exception as e:
                error_msg = f"Failed to apply edits to {file_path}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        return ApplyResult(
            files_modified=files_modified,
            files_created=files_created,
            files_deleted=files_deleted,
            errors=errors,
        )

    async def _apply_to_file(self, file_path: str, edits: list[Edit]) -> dict:
        """
        Apply multiple edits to a single file.

        Returns:
            Dict with keys: modified, created, deleted, error
        """
        # Resolve absolute path
        abs_path = self._resolve_path(file_path)

        # Read existing content if file exists
        file_exists = abs_path.exists()
        original_content = ""

        if file_exists:
            try:
                original_content = await self._read_file(abs_path)
            except Exception as e:
                return {
                    "modified": False,
                    "created": False,
                    "deleted": False,
                    "error": f"Failed to read {file_path}: {e}",
                }
        else:
            logger.info(f"File does not exist, will create: {file_path}")

        # Apply edits sequentially
        current_content = original_content
        modified = False

        for i, edit in enumerate(edits):
            try:
                result = await self._apply_single_edit(
                    edit, current_content, file_path, i
                )

                if result["error"]:
                    return {
                        "modified": False,
                        "created": False,
                        "deleted": False,
                        "error": result["error"],
                    }

                if result["content"] != current_content:
                    modified = True
                    current_content = result["content"]

                # Check if this edit deletes the file
                if result.get("deleted", False):
                    # Don't apply further edits to deleted file
                    return {
                        "modified": False,
                        "created": False,
                        "deleted": True,
                        "error": None,
                    }

            except Exception as e:
                return {
                    "modified": False,
                    "created": False,
                    "deleted": False,
                    "error": f"Edit {i+1} failed for {file_path}: {e}",
                }

        # Write changes if modified
        if modified or not file_exists:
            try:
                await self._write_file(abs_path, current_content)

                if not file_exists:
                    logger.info(f"Created file: {file_path}")
                    return {
                        "modified": False,
                        "created": True,
                        "deleted": False,
                        "error": None,
                    }
                else:
                    logger.info(f"Modified file: {file_path}")
                    return {
                        "modified": True,
                        "created": False,
                        "deleted": False,
                        "error": None,
                    }

            except Exception as e:
                return {
                    "modified": False,
                    "created": False,
                    "deleted": False,
                    "error": f"Failed to write {file_path}: {e}",
                }

        # No changes
        return {
            "modified": False,
            "created": False,
            "deleted": False,
            "error": None,
        }

    async def _apply_single_edit(
        self,
        edit: Edit,
        content: str,
        file_path: str,
        edit_index: int
    ) -> dict:
        """
        Apply a single edit to content.

        Returns:
            Dict with keys: content, error, deleted
        """
        # If old_text is empty, it's a whole file replacement or creation
        if not edit.old_text:
            if not edit.new_text:
                # Empty replace = delete file
                logger.info(f"Edit {edit_index+1}: Deleting {file_path}")
                return {
                    "content": "",
                    "error": None,
                    "deleted": True,
                }
            else:
                # Replace entire file
                logger.info(f"Edit {edit_index+1}: Replacing entire {file_path}")
                return {
                    "content": edit.new_text,
                    "error": None,
                    "deleted": False,
                }

        # Search for old_text in content
        index = content.find(edit.old_text)

        if index == -1:
            # Try fuzzy matching
            # For now, use simple line-based matching
            old_lines = edit.old_text.split('\n')
            content_lines = content.split('\n')

            for i in range(len(content_lines) - len(old_lines) + 1):
                if content_lines[i:i+len(old_lines)] == old_lines:
                    # Found match, reconstruct position
                    start_pos = len('\n'.join(content_lines[:i]))
                    if i > 0:
                        start_pos += 1  # Account for newline
                    index = start_pos
                    break

            if index == -1:
                return {
                    "content": content,
                    "error": f"Could not find text to replace in {file_path}",
                    "deleted": False,
                }

        # Perform replacement
        new_content = (
            content[:index] +
            edit.new_text +
            content[index + len(edit.old_text):]
        )

        logger.debug(f"Edit {edit_index+1}: Replaced {len(edit.old_text)} chars "
                    f"with {len(edit.new_text)} chars in {file_path}")

        return {
            "content": new_content,
            "error": None,
            "deleted": False,
        }

    def _resolve_path(self, file_path: str) -> Path:
        """Resolve file path relative to base path."""
        path = Path(file_path)

        if not path.is_absolute():
            path = self.base_path / path

        # Normalize path (resolve symlinks, remove .., etc.)
        try:
            return path.resolve()
        except Exception:
            # If resolve fails (e.g., path doesn't exist), return absolute path
            return path.absolute()

    async def _read_file(self, path: Path) -> str:
        """Read file content asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, path.read_text, 'utf-8')

    async def _write_file(self, path: Path, content: str) -> None:
        """Write file content asynchronously."""
        # Create directory if it doesn't exist
        path.parent.mkdir(parents=True, exist_ok=True)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, path.write_text, content, 'utf-8')
