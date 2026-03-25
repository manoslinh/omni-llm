"""
Unit tests for LintVerifier.
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from omni.core.verifiers import LintVerifier


class TestLintVerifier:
    """Test LintVerifier functionality."""

    def test_init_defaults(self):
        """Test LintVerifier initialization with defaults."""
        verifier = LintVerifier()
        assert verifier.name == "lint"
        assert verifier.enabled is True
        assert verifier.severity_level == "all"
        assert verifier.config_path is None
        assert verifier.fix is False
        assert verifier._ruff_cmd == "ruff"

    def test_init_custom(self):
        """Test LintVerifier initialization with custom values."""
        verifier = LintVerifier(
            name="custom-lint",
            enabled=False,
            severity_level="error",
            config_path="pyproject.toml",
            fix=True,
            ruff_cmd="/usr/local/bin/ruff",
        )
        assert verifier.name == "custom-lint"
        assert verifier.enabled is False
        assert verifier.severity_level == "error"
        assert verifier.config_path == "pyproject.toml"
        assert verifier.fix is True
        assert verifier._ruff_cmd == "/usr/local/bin/ruff"

    @pytest.mark.asyncio
    async def test_verify_no_files(self):
        """Test lint verification with no files."""
        verifier = LintVerifier()
        result = await verifier.verify([])

        assert result.passed is True
        assert result.errors == []
        assert result.warnings == []
        assert result.name == "lint"
        assert "files_checked" in result.details

    @pytest.mark.asyncio
    async def test_verify_no_python_files(self):
        """Test lint verification with no Python files."""
        verifier = LintVerifier()
        result = await verifier.verify(["README.md", "config.yaml"])

        assert result.passed is True
        assert result.errors == []
        assert result.warnings == []
        assert result.name == "lint"
        assert "python_files" in result.details

    @pytest.mark.asyncio
    async def test_verify_success(self):
        """Test successful lint verification."""
        verifier = LintVerifier()

        # Create a temporary Python file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def hello():\n    print('Hello, world!')\n")
            temp_file = f.name

        try:
            # Mock the subprocess to return success
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b'[]', b''))

            with patch('asyncio.create_subprocess_exec', return_value=mock_process):
                result = await verifier.verify([temp_file])

                assert result.passed is True
                assert result.errors == []
                assert result.warnings == []
                assert result.name == "lint"
                assert "command" in result.details
        finally:
            Path(temp_file).unlink()

    @pytest.mark.asyncio
    async def test_verify_with_errors(self):
        """Test lint verification with errors."""
        verifier = LintVerifier(severity_level="error")

        # Mock ruff output with an error
        ruff_output = json.dumps([
            {
                "filename": "test.py",
                "location": {"row": 1, "column": 1},
                "code": "E999",
                "message": "Syntax error",
                "severity": "error"
            }
        ]).encode()

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(ruff_output, b''))

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            result = await verifier.verify(["test.py"])

            assert result.passed is False
            assert len(result.errors) == 1
            assert "test.py:1:1: E999: Syntax error" in result.errors[0]
            assert result.warnings == []
            assert result.name == "lint"

    @pytest.mark.asyncio
    async def test_verify_with_warnings(self):
        """Test lint verification with warnings."""
        verifier = LintVerifier(severity_level="warning")

        # Mock ruff output with a warning
        ruff_output = json.dumps([
            {
                "filename": "test.py",
                "location": {"row": 2, "column": 5},
                "code": "W291",
                "message": "Trailing whitespace",
                "severity": "warning"
            }
        ]).encode()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(ruff_output, b''))

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            result = await verifier.verify(["test.py"])

            assert result.passed is True  # Warnings don't fail
            assert result.errors == []
            assert len(result.warnings) == 1
            assert "test.py:2:5: W291: Trailing whitespace" in result.warnings[0]
            assert result.name == "lint"

    @pytest.mark.asyncio
    async def test_verify_parse_error(self):
        """Test lint verification with JSON parse error."""
        verifier = LintVerifier()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b'invalid json', b''))

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            result = await verifier.verify(["test.py"])

            # When there's a parse error but exit code is 0, it should still pass
            # because the linting itself succeeded (no actual lint errors)
            assert result.passed is True
            assert len(result.errors) == 1  # But we still record the parse error
            assert "Failed to parse ruff output" in result.errors[0]
            assert result.name == "lint"

    @pytest.mark.asyncio
    async def test_verify_exception(self):
        """Test lint verification when subprocess fails."""
        verifier = LintVerifier()

        with patch('asyncio.create_subprocess_exec', side_effect=OSError("Command not found")):
            result = await verifier.verify(["test.py"])

            assert result.passed is False
            assert len(result.errors) == 1
            assert "Lint verification failed" in result.errors[0]
            assert result.name == "lint"

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing the verifier."""
        verifier = LintVerifier()
        await verifier.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_verify_with_config(self):
        """Test lint verification with config file."""
        verifier = LintVerifier(config_path="pyproject.toml")

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b'[]', b''))

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            await verifier.verify(["test.py"])

            # Check that config was included in command
            call_args = asyncio.create_subprocess_exec.call_args
            assert call_args is not None
            args = call_args[0]
            assert "--config" in args
            assert "pyproject.toml" in args

    @pytest.mark.asyncio
    async def test_verify_with_fix(self):
        """Test lint verification with fix flag."""
        verifier = LintVerifier(fix=True)

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b'[]', b''))

        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            await verifier.verify(["test.py"])

            # Check that --fix was included in command
            call_args = asyncio.create_subprocess_exec.call_args
            assert call_args is not None
            args = call_args[0]
            assert "--fix" in args


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
