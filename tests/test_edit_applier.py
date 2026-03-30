"""
Tests for the EditApplier module.

Covers file reading, search/replace logic, file creation, file deletion,
applying batches of edits, edge cases, and error handling.
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from omni.core.edit_applier import EditApplier
from omni.core.models import Edit


class TestEditApplierInit:
    """Tests for EditApplier initialization."""

    def test_init_with_base_path(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        assert applier.base_path == tmp_path.resolve()

    def test_init_without_base_path_uses_cwd(self):
        applier = EditApplier()
        assert applier.base_path == Path(os.getcwd()).resolve()

    def test_init_with_none_base_path_uses_cwd(self):
        applier = EditApplier(base_path=None)
        assert applier.base_path == Path(os.getcwd()).resolve()


class TestReadFile:
    """Tests for the _read_file method."""

    @pytest.mark.asyncio
    async def test_read_file_returns_content(self, tmp_path):
        test_file = tmp_path / "hello.txt"
        test_file.write_text("hello world", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        content = await applier._read_file(test_file)
        assert content == "hello world"

    @pytest.mark.asyncio
    async def test_read_file_preserves_newlines(self, tmp_path):
        test_file = tmp_path / "multiline.txt"
        test_file.write_text("line1\nline2\nline3\n", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        content = await applier._read_file(test_file)
        assert content == "line1\nline2\nline3\n"

    @pytest.mark.asyncio
    async def test_read_file_handles_unicode(self, tmp_path):
        test_file = tmp_path / "unicode.txt"
        test_file.write_text("Caf\u00e9 \u2603 \u2764", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        content = await applier._read_file(test_file)
        assert content == "Caf\u00e9 \u2603 \u2764"

    @pytest.mark.asyncio
    async def test_read_file_empty_file(self, tmp_path):
        test_file = tmp_path / "empty.txt"
        test_file.write_text("", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        content = await applier._read_file(test_file)
        assert content == ""

    @pytest.mark.asyncio
    async def test_read_file_missing_file_raises(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        with pytest.raises(FileNotFoundError):
            await applier._read_file(tmp_path / "nonexistent.txt")


class TestResolvePath:
    """Tests for the _resolve_path method."""

    def test_resolve_relative_path(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        resolved = applier._resolve_path("foo/bar.py")
        assert resolved == (tmp_path / "foo" / "bar.py").resolve()

    def test_resolve_absolute_path(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        abs_path = str(tmp_path / "absolute.py")
        resolved = applier._resolve_path(abs_path)
        assert resolved == Path(abs_path).resolve()


class TestApplySingleEdit:
    """Tests for the _apply_single_edit method (search/replace core logic)."""

    @pytest.mark.asyncio
    async def test_search_replace_exact_match(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        edit = Edit(file_path="test.py", old_text="old code", new_text="new code")
        result = await applier._apply_single_edit(edit, "some old code here", "test.py", 0)

        assert result["content"] == "some new code here"
        assert result["error"] is None
        assert result["deleted"] is False

    @pytest.mark.asyncio
    async def test_search_replace_no_match_returns_error(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        edit = Edit(file_path="test.py", old_text="missing text", new_text="replacement")
        result = await applier._apply_single_edit(edit, "content without match", "test.py", 0)

        assert result["error"] is not None
        assert "Could not find" in result["error"]
        assert result["content"] == "content without match"

    @pytest.mark.asyncio
    async def test_search_replace_multiline(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        old_text = "def foo():\n    return 1"
        new_text = "def foo():\n    return 2"
        content = "# header\ndef foo():\n    return 1\n# footer"

        edit = Edit(file_path="test.py", old_text=old_text, new_text=new_text)
        result = await applier._apply_single_edit(edit, content, "test.py", 0)

        assert result["error"] is None
        assert "return 2" in result["content"]
        assert "return 1" not in result["content"]

    @pytest.mark.asyncio
    async def test_search_replace_only_first_occurrence(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        edit = Edit(file_path="test.py", old_text="dup", new_text="REPLACED")
        result = await applier._apply_single_edit(edit, "dup and dup", "test.py", 0)

        assert result["content"] == "REPLACED and dup"

    @pytest.mark.asyncio
    async def test_empty_old_text_with_new_text_replaces_whole_file(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        edit = Edit(file_path="test.py", old_text="", new_text="brand new content")
        result = await applier._apply_single_edit(edit, "original content", "test.py", 0)

        assert result["content"] == "brand new content"
        assert result["deleted"] is False

    @pytest.mark.asyncio
    async def test_empty_old_and_new_text_deletes_file(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        edit = Edit(file_path="test.py", old_text="", new_text="")
        result = await applier._apply_single_edit(edit, "original content", "test.py", 0)

        assert result["deleted"] is True
        assert result["content"] == ""

    @pytest.mark.asyncio
    async def test_search_replace_preserves_surrounding_content(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        content = "prefix|target|suffix"
        edit = Edit(file_path="test.py", old_text="target", new_text="REPLACED")
        result = await applier._apply_single_edit(edit, content, "test.py", 0)

        assert result["content"] == "prefix|REPLACED|suffix"

    @pytest.mark.asyncio
    async def test_search_replace_with_empty_replacement(self, tmp_path):
        """Replacing with empty string effectively removes the matched text."""
        applier = EditApplier(base_path=str(tmp_path))
        edit = Edit(file_path="test.py", old_text="remove me", new_text="")
        result = await applier._apply_single_edit(edit, "keep remove me keep", "test.py", 0)

        assert result["content"] == "keep  keep"


class TestApplyToFile:
    """Tests for _apply_to_file — applying multiple edits to a single file."""

    @pytest.mark.asyncio
    async def test_apply_creates_new_file(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        edit = Edit(file_path="new_file.py", old_text="", new_text="print('hello')")

        result = await applier._apply_to_file("new_file.py", [edit])

        assert result["created"] is True
        assert result["modified"] is False
        assert result["deleted"] is False
        assert result["error"] is None

        created_file = tmp_path / "new_file.py"
        assert created_file.exists()
        assert created_file.read_text(encoding="utf-8") == "print('hello')"

    @pytest.mark.asyncio
    async def test_apply_modifies_existing_file(self, tmp_path):
        target = tmp_path / "existing.py"
        target.write_text("old line", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        edit = Edit(file_path="existing.py", old_text="old line", new_text="new line")

        result = await applier._apply_to_file("existing.py", [edit])

        assert result["modified"] is True
        assert result["created"] is False
        assert target.read_text(encoding="utf-8") == "new line"

    @pytest.mark.asyncio
    async def test_apply_deletes_file_via_empty_edit(self, tmp_path):
        """When old_text and new_text are both empty, file is marked as deleted."""
        target = tmp_path / "to_delete.py"
        target.write_text("content", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        edit = Edit(file_path="to_delete.py", old_text="", new_text="")

        result = await applier._apply_to_file("to_delete.py", [edit])

        assert result["deleted"] is True
        assert result["modified"] is False

    @pytest.mark.asyncio
    async def test_apply_multiple_edits_sequentially(self, tmp_path):
        target = tmp_path / "multi.py"
        target.write_text("aaa bbb ccc", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        edits = [
            Edit(file_path="multi.py", old_text="aaa", new_text="AAA"),
            Edit(file_path="multi.py", old_text="ccc", new_text="CCC"),
        ]

        result = await applier._apply_to_file("multi.py", edits)

        assert result["modified"] is True
        assert target.read_text(encoding="utf-8") == "AAA bbb CCC"

    @pytest.mark.asyncio
    async def test_apply_stops_on_first_error(self, tmp_path):
        target = tmp_path / "err.py"
        target.write_text("content", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        edits = [
            Edit(file_path="err.py", old_text="nonexistent", new_text="x"),
            Edit(file_path="err.py", old_text="content", new_text="y"),
        ]

        result = await applier._apply_to_file("err.py", edits)

        assert result["error"] is not None
        assert "Could not find" in result["error"]
        # File should be unchanged since error occurred
        assert target.read_text(encoding="utf-8") == "content"

    @pytest.mark.asyncio
    async def test_apply_no_changes_returns_no_modification(self, tmp_path):
        """If no edit actually changes the content, modified should be False."""
        target = tmp_path / "same.py"
        target.write_text("same text", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        edit = Edit(file_path="same.py", old_text="same text", new_text="same text")

        result = await applier._apply_to_file("same.py", [edit])

        assert result["modified"] is False
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_apply_creates_subdirectories(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        edit = Edit(file_path="sub/dir/file.py", old_text="", new_text="nested content")

        result = await applier._apply_to_file("sub/dir/file.py", [edit])

        assert result["created"] is True
        created = tmp_path / "sub" / "dir" / "file.py"
        assert created.exists()
        assert created.read_text(encoding="utf-8") == "nested content"

    @pytest.mark.asyncio
    async def test_apply_delete_stops_further_edits(self, tmp_path):
        """After a delete edit, subsequent edits should not be applied."""
        target = tmp_path / "del.py"
        target.write_text("content", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        edits = [
            Edit(file_path="del.py", old_text="", new_text=""),  # delete
            Edit(file_path="del.py", old_text="", new_text="should not apply"),
        ]

        result = await applier._apply_to_file("del.py", edits)

        assert result["deleted"] is True


class TestApply:
    """Tests for the top-level apply method."""

    @pytest.mark.asyncio
    async def test_apply_single_file_modification(self, tmp_path):
        target = tmp_path / "app.py"
        target.write_text("version = 1", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        edits = [Edit(file_path="app.py", old_text="version = 1", new_text="version = 2")]

        result = await applier.apply(edits)

        assert result.files_modified == ["app.py"]
        assert result.files_created == []
        assert result.files_deleted == []
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_apply_creates_new_file(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        edits = [Edit(file_path="new.py", old_text="", new_text="print('new')")]

        result = await applier.apply(edits)

        assert result.files_created == ["new.py"]
        assert result.files_modified == []

    @pytest.mark.asyncio
    async def test_apply_deletes_file(self, tmp_path):
        target = tmp_path / "delete_me.py"
        target.write_text("bye", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        edits = [Edit(file_path="delete_me.py", old_text="", new_text="")]

        result = await applier.apply(edits)

        assert result.files_deleted == ["delete_me.py"]

    @pytest.mark.asyncio
    async def test_apply_multiple_files(self, tmp_path):
        (tmp_path / "a.py").write_text("a_old", encoding="utf-8")
        (tmp_path / "b.py").write_text("b_old", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        edits = [
            Edit(file_path="a.py", old_text="a_old", new_text="a_new"),
            Edit(file_path="b.py", old_text="b_old", new_text="b_new"),
        ]

        result = await applier.apply(edits)

        assert sorted(result.files_modified) == ["a.py", "b.py"]
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_apply_groups_edits_by_file(self, tmp_path):
        target = tmp_path / "grouped.py"
        target.write_text("aaa bbb", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        edits = [
            Edit(file_path="grouped.py", old_text="aaa", new_text="AAA"),
            Edit(file_path="grouped.py", old_text="bbb", new_text="BBB"),
        ]

        result = await applier.apply(edits)

        assert result.files_modified == ["grouped.py"]
        assert target.read_text(encoding="utf-8") == "AAA BBB"

    @pytest.mark.asyncio
    async def test_apply_collects_errors(self, tmp_path):
        (tmp_path / "ok.py").write_text("ok", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        edits = [
            Edit(file_path="ok.py", old_text="ok", new_text="fine"),
            Edit(file_path="fail.py", old_text="missing", new_text="x"),
        ]

        result = await applier.apply(edits)

        assert result.files_modified == ["ok.py"]
        # fail.py should produce an error since it doesn't exist and has old_text
        # The file doesn't exist, so original_content is "", and the search for
        # "missing" in "" will fail
        assert len(result.errors) >= 1

    @pytest.mark.asyncio
    async def test_apply_empty_edits_list(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        result = await applier.apply([])

        assert result.files_modified == []
        assert result.files_created == []
        assert result.files_deleted == []
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_apply_mixed_operations(self, tmp_path):
        """Test creating, modifying, and deleting files in a single apply call."""
        (tmp_path / "modify.py").write_text("old", encoding="utf-8")
        (tmp_path / "delete.py").write_text("bye", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        edits = [
            Edit(file_path="modify.py", old_text="old", new_text="new"),
            Edit(file_path="create.py", old_text="", new_text="created"),
            Edit(file_path="delete.py", old_text="", new_text=""),
        ]

        result = await applier.apply(edits)

        assert result.files_modified == ["modify.py"]
        assert result.files_created == ["create.py"]
        assert result.files_deleted == ["delete.py"]
        assert result.errors == []


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_unicode_content_roundtrip(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        unicode_content = "def greet():\n    return '\u4f60\u597d\u4e16\u754c \U0001f30d'"
        edits = [Edit(file_path="unicode.py", old_text="", new_text=unicode_content)]

        result = await applier.apply(edits)

        assert result.errors == [], f"Unexpected errors: {result.errors}"
        assert result.files_created == ["unicode.py"]
        written = (tmp_path / "unicode.py").read_text(encoding="utf-8")
        assert written == unicode_content

    @pytest.mark.asyncio
    async def test_empty_file_can_be_modified_via_whole_replace(self, tmp_path):
        target = tmp_path / "empty.py"
        target.write_text("", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        edit = Edit(file_path="empty.py", old_text="", new_text="now has content")

        result = await applier.apply(edits=[edit])

        # The file existed but was empty; old_text="" triggers whole-file replace.
        # Since the file existed and content changed, it should be modified.
        assert result.files_modified == ["empty.py"]
        assert target.read_text(encoding="utf-8") == "now has content"

    @pytest.mark.asyncio
    async def test_special_characters_in_content(self, tmp_path):
        target = tmp_path / "special.py"
        content_with_special = 'regex = r"\\d+\\.\\d+"'
        target.write_text(content_with_special, encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        edit = Edit(
            file_path="special.py",
            old_text=content_with_special,
            new_text='regex = r"\\w+"',
        )

        result = await applier.apply([edit])

        assert result.files_modified == ["special.py"]
        assert target.read_text(encoding="utf-8") == 'regex = r"\\w+"'

    @pytest.mark.asyncio
    async def test_large_file_search_replace(self, tmp_path):
        target = tmp_path / "large.py"
        lines = [f"line_{i} = {i}" for i in range(1000)]
        content = "\n".join(lines)
        target.write_text(content, encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        edit = Edit(
            file_path="large.py",
            old_text="line_500 = 500",
            new_text="line_500 = 'REPLACED'",
        )

        result = await applier.apply([edit])

        assert result.files_modified == ["large.py"]
        new_content = target.read_text(encoding="utf-8")
        assert "line_500 = 'REPLACED'" in new_content
        assert "line_499 = 499" in new_content
        assert "line_501 = 501" in new_content

    @pytest.mark.asyncio
    async def test_file_in_nested_directory(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        edits = [
            Edit(
                file_path="a/b/c/deep.py",
                old_text="",
                new_text="deeply nested",
            )
        ]

        result = await applier.apply(edits)

        assert result.files_created == ["a/b/c/deep.py"]
        assert (tmp_path / "a" / "b" / "c" / "deep.py").read_text(encoding="utf-8") == "deeply nested"

    @pytest.mark.asyncio
    async def test_newline_handling_in_search(self, tmp_path):
        target = tmp_path / "newlines.py"
        target.write_text("a\r\nb\nc\n", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))
        # Search for the literal content as it would be read (platform-dependent
        # on read, but we write with specific chars)
        content = target.read_text(encoding="utf-8")
        edit = Edit(file_path="newlines.py", old_text=content, new_text="replaced\n")

        result = await applier.apply([edit])

        assert result.files_modified == ["newlines.py"]


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_read_permission_error_returns_error(self, tmp_path):
        """Test behavior when file cannot be read."""
        applier = EditApplier(base_path=str(tmp_path))

        # Mock _read_file to raise a PermissionError
        async def mock_read_file(path):
            raise PermissionError("Permission denied")

        applier._read_file = mock_read_file

        target = tmp_path / "noperm.py"
        target.write_text("content", encoding="utf-8")

        edit = Edit(file_path="noperm.py", old_text="content", new_text="new")
        result = await applier._apply_to_file("noperm.py", [edit])

        assert result["error"] is not None
        assert "Failed to read" in result["error"]

    @pytest.mark.asyncio
    async def test_write_permission_error_returns_error(self, tmp_path):
        """Test behavior when file cannot be written."""
        applier = EditApplier(base_path=str(tmp_path))

        async def mock_write_file(path, content):
            raise PermissionError("Permission denied")

        applier._write_file = mock_write_file

        target = tmp_path / "nowrite.py"
        target.write_text("old", encoding="utf-8")

        edit = Edit(file_path="nowrite.py", old_text="old", new_text="new")
        result = await applier._apply_to_file("nowrite.py", [edit])

        assert result["error"] is not None
        assert "Failed to write" in result["error"]

    @pytest.mark.asyncio
    async def test_exception_in_apply_is_caught(self, tmp_path):
        """Test that unexpected exceptions in _apply_to_file are caught by apply."""
        applier = EditApplier(base_path=str(tmp_path))

        async def mock_apply_to_file(file_path, edits):
            raise RuntimeError("Unexpected error")

        applier._apply_to_file = mock_apply_to_file

        edits = [Edit(file_path="boom.py", old_text="x", new_text="y")]
        result = await applier.apply(edits)

        assert len(result.errors) == 1
        assert "Failed to apply edits to boom.py" in result.errors[0]

    @pytest.mark.asyncio
    async def test_edit_exception_returns_error(self, tmp_path):
        """Test that an exception during _apply_single_edit is handled."""
        target = tmp_path / "exc.py"
        target.write_text("content", encoding="utf-8")

        applier = EditApplier(base_path=str(tmp_path))

        async def mock_apply_single(edit, content, file_path, idx):
            raise ValueError("Bad edit")

        applier._apply_single_edit = mock_apply_single

        edit = Edit(file_path="exc.py", old_text="content", new_text="new")
        result = await applier._apply_to_file("exc.py", [edit])

        assert result["error"] is not None
        assert "Edit 1 failed" in result["error"]

    @pytest.mark.asyncio
    async def test_search_in_nonexistent_file_uses_empty_content(self, tmp_path):
        """When file doesn't exist, content is '' so search with old_text fails."""
        applier = EditApplier(base_path=str(tmp_path))
        edit = Edit(file_path="ghost.py", old_text="find me", new_text="replace")

        result = await applier._apply_to_file("ghost.py", [edit])

        assert result["error"] is not None
        assert "Could not find" in result["error"]


class TestWriteFile:
    """Tests for the _write_file method."""

    @pytest.mark.asyncio
    async def test_write_file_creates_content(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        target = tmp_path / "written.py"

        await applier._write_file(target, "hello written")

        assert target.read_text(encoding="utf-8") == "hello written"

    @pytest.mark.asyncio
    async def test_write_file_creates_parent_dirs(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        target = tmp_path / "a" / "b" / "deep.py"

        await applier._write_file(target, "deep content")

        assert target.exists()
        assert target.read_text(encoding="utf-8") == "deep content"

    @pytest.mark.asyncio
    async def test_write_file_overwrites_existing(self, tmp_path):
        applier = EditApplier(base_path=str(tmp_path))
        target = tmp_path / "overwrite.py"
        target.write_text("old", encoding="utf-8")

        await applier._write_file(target, "new")

        assert target.read_text(encoding="utf-8") == "new"
