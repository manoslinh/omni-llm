"""Tests for the codebase context scanner."""

from __future__ import annotations

import json
import os

import pytest

from omni.core.context_scanner import ContextScanner, ProjectContext, _is_sensitive


class TestScanEmptyDirectory:
    """Scanning an empty directory."""

    def test_returns_project_context(self, tmp_path: str) -> None:
        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()

        assert isinstance(ctx, ProjectContext)
        assert ctx.file_count == 0
        assert ctx.language == "Unknown"
        assert ctx.framework is None
        assert ctx.file_tree == "(empty)"

    def test_key_files_empty(self, tmp_path: str) -> None:
        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        assert ctx.key_files == []


class TestScanPythonProject:
    """Scanning a directory with Python files."""

    @pytest.fixture()
    def python_project(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "utils.py").write_text("def helper(): pass")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_main.py").write_text("def test_it(): pass")
        (tmp_path / "README.md").write_text("# My Project")
        return tmp_path

    def test_detects_python(self, python_project) -> None:
        scanner = ContextScanner(str(python_project))
        ctx = scanner.scan()
        assert ctx.language == "Python"

    def test_counts_files(self, python_project) -> None:
        scanner = ContextScanner(str(python_project))
        ctx = scanner.scan()
        assert ctx.file_count == 4

    def test_identifies_key_files(self, python_project) -> None:
        scanner = ContextScanner(str(python_project))
        ctx = scanner.scan()
        basenames = [os.path.basename(f) for f in ctx.key_files]
        assert "README.md" in basenames
        assert "main.py" in basenames

    def test_tree_contains_files(self, python_project) -> None:
        scanner = ContextScanner(str(python_project))
        ctx = scanner.scan()
        assert "main.py" in ctx.file_tree
        assert "utils.py" in ctx.file_tree
        assert "tests" in ctx.file_tree

    def test_summary_format(self, python_project) -> None:
        scanner = ContextScanner(str(python_project))
        ctx = scanner.scan()
        assert "Python" in ctx.summary
        assert "4 files" in ctx.summary


class TestLanguageDetection:
    """Detecting language correctly."""

    @pytest.mark.parametrize(
        ("filenames", "expected"),
        [
            (["app.py", "utils.py", "models.py"], "Python"),
            (["index.ts", "utils.ts", "types.ts"], "TypeScript"),
            (["main.js", "helper.js"], "JavaScript"),
            (["main.go", "handler.go", "models.go"], "Go"),
            (["main.rs", "lib.rs"], "Rust"),
            (["App.java", "Main.java"], "Java"),
        ],
    )
    def test_detects_language(
        self, tmp_path, filenames: list[str], expected: str
    ) -> None:
        for name in filenames:
            (tmp_path / name).write_text("")
        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        assert ctx.language == expected

    def test_unknown_for_no_code_files(self, tmp_path) -> None:
        (tmp_path / "data.csv").write_text("a,b,c")
        (tmp_path / "notes.txt").write_text("hello")
        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        assert ctx.language == "Unknown"


class TestFrameworkDetection:
    """Detecting framework from project files."""

    def test_detects_react_from_package_json(self, tmp_path) -> None:
        pkg = {"dependencies": {"react": "^18.0.0", "react-dom": "^18.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        (tmp_path / "index.js").write_text("")
        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        assert ctx.framework == "React"

    def test_detects_nextjs_from_package_json(self, tmp_path) -> None:
        pkg = {"dependencies": {"next": "^14.0.0", "react": "^18.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        (tmp_path / "index.ts").write_text("")
        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        # Next.js should be detected before React
        assert ctx.framework == "Next.js"

    def test_detects_django_from_pyproject(self, tmp_path) -> None:
        toml_content = '[project]\ndependencies = ["django>=4.0"]\n'
        (tmp_path / "pyproject.toml").write_text(toml_content)
        (tmp_path / "manage.py").write_text("")
        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        assert ctx.framework == "Django"

    def test_detects_fastapi_from_pyproject(self, tmp_path) -> None:
        toml_content = '[project]\ndependencies = ["fastapi>=0.100"]\n'
        (tmp_path / "pyproject.toml").write_text(toml_content)
        (tmp_path / "app.py").write_text("")
        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        assert ctx.framework == "FastAPI"

    def test_no_framework_for_plain_project(self, tmp_path) -> None:
        (tmp_path / "main.py").write_text("print('hi')")
        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        assert ctx.framework is None


class TestFileTree:
    """File tree generation."""

    def test_respects_max_tree_files(self, tmp_path) -> None:
        # Create more files than MAX_TREE_FILES
        for i in range(150):
            (tmp_path / f"file_{i:03d}.py").write_text("")

        scanner = ContextScanner(str(tmp_path))
        scanner.MAX_TREE_FILES = 50  # Lower for faster test
        ctx = scanner.scan()

        assert "... and 100 more files" in ctx.file_tree

    def test_nested_directories(self, tmp_path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "core").mkdir()
        (tmp_path / "src" / "core" / "app.py").write_text("")
        (tmp_path / "src" / "utils.py").write_text("")

        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()

        assert "src" in ctx.file_tree
        assert "core" in ctx.file_tree
        assert "app.py" in ctx.file_tree
        assert "utils.py" in ctx.file_tree

    def test_empty_tree(self, tmp_path) -> None:
        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        assert ctx.file_tree == "(empty)"


class TestReadFiles:
    """read_files respects size limits."""

    def test_reads_file_contents(self, tmp_path) -> None:
        (tmp_path / "hello.py").write_text("print('hello')")
        scanner = ContextScanner(str(tmp_path))
        result = scanner.read_files(["hello.py"])
        assert "--- hello.py ---" in result
        assert "print('hello')" in result

    def test_respects_max_context_chars(self, tmp_path) -> None:
        # Create files that together exceed the limit
        content_a = "A" * 500
        content_b = "B" * 500
        (tmp_path / "a.py").write_text(content_a)
        (tmp_path / "b.py").write_text(content_b)

        scanner = ContextScanner(str(tmp_path))
        result = scanner.read_files(["a.py", "b.py"], max_chars=600)

        # First file should be included, second should be truncated or absent
        assert "--- a.py ---" in result
        assert "AAAA" in result
        # The total should not exceed max_chars by much
        assert len(result) <= 800  # some overhead for headers

    def test_skips_large_files(self, tmp_path) -> None:
        large_content = "x" * 60_000
        (tmp_path / "big.py").write_text(large_content)

        scanner = ContextScanner(str(tmp_path))
        result = scanner.read_files(["big.py"])
        assert "skipped, too large" in result

    def test_skips_missing_files(self, tmp_path) -> None:
        scanner = ContextScanner(str(tmp_path))
        result = scanner.read_files(["nonexistent.py"])
        assert result == ""


class TestIgnoredDirectories:
    """Ignored directories are skipped."""

    def test_skips_git_directory(self, tmp_path) -> None:
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main")
        (tmp_path / "app.py").write_text("")

        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        assert ctx.file_count == 1
        assert not any(".git" in f for f in ctx.key_files)

    def test_skips_node_modules(self, tmp_path) -> None:
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "lodash").mkdir()
        (nm / "lodash" / "index.js").write_text("")
        (tmp_path / "index.js").write_text("")

        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        assert ctx.file_count == 1

    def test_skips_pycache(self, tmp_path) -> None:
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "module.cpython-311.pyc").write_text("")
        (tmp_path / "module.py").write_text("")

        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        assert ctx.file_count == 1

    def test_skips_ignored_extensions(self, tmp_path) -> None:
        (tmp_path / "module.py").write_text("")
        (tmp_path / "module.pyc").write_text("")
        (tmp_path / "lib.so").write_text("")

        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        assert ctx.file_count == 1


class TestKeyFileIdentification:
    """Key files are identified correctly."""

    def test_identifies_readme(self, tmp_path) -> None:
        (tmp_path / "README.md").write_text("# Readme")
        (tmp_path / "code.py").write_text("")
        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        assert "README.md" in ctx.key_files

    def test_identifies_package_json(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "index.js").write_text("")
        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        assert "package.json" in ctx.key_files

    def test_identifies_entry_points(self, tmp_path) -> None:
        (tmp_path / "main.py").write_text("")
        (tmp_path / "helpers.py").write_text("")
        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        assert "main.py" in ctx.key_files
        assert "helpers.py" not in ctx.key_files

    def test_root_files_sorted_first(self, tmp_path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("")
        (tmp_path / "README.md").write_text("")
        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        # README.md at root should come before src/main.py
        readme_idx = ctx.key_files.index("README.md")
        main_idx = ctx.key_files.index(os.path.join("src", "main.py"))
        assert readme_idx < main_idx


class TestBuildPromptContext:
    """build_prompt_context produces usable output."""

    def test_includes_project_info(self, tmp_path) -> None:
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "README.md").write_text("# My Project")

        scanner = ContextScanner(str(tmp_path))
        prompt = scanner.build_prompt_context()

        assert "Language: Python" in prompt
        assert "Files: 2" in prompt
        assert "File structure:" in prompt

    def test_includes_file_contents(self, tmp_path) -> None:
        (tmp_path / "README.md").write_text("# My Project\nSome description")

        scanner = ContextScanner(str(tmp_path))
        prompt = scanner.build_prompt_context()

        assert "Key file contents:" in prompt
        assert "# My Project" in prompt

    def test_respects_max_context_chars(self, tmp_path) -> None:
        (tmp_path / "README.md").write_text("X" * 5000)
        (tmp_path / "main.py").write_text("Y" * 5000)

        scanner = ContextScanner(str(tmp_path), max_context_chars=2000)
        prompt = scanner.build_prompt_context()

        assert len(prompt) <= 2500  # some overhead tolerance


class TestSensitiveFileDenyList:
    """Sensitive files are always excluded."""

    def test_skips_env_file(self, tmp_path) -> None:
        (tmp_path / ".env").write_text("SECRET_KEY=abc123")
        (tmp_path / "main.py").write_text("print('hello')")

        scanner = ContextScanner(str(tmp_path))
        ctx = scanner.scan()
        all_files = scanner._collect_files()
        assert ".env" not in all_files
        assert ctx.file_count == 1

    def test_skips_env_local(self, tmp_path) -> None:
        (tmp_path / ".env.local").write_text("SECRET=abc")
        (tmp_path / "app.py").write_text("")

        scanner = ContextScanner(str(tmp_path))
        all_files = scanner._collect_files()
        assert ".env.local" not in all_files

    def test_skips_pem_files(self, tmp_path) -> None:
        (tmp_path / "server.pem").write_text("-----BEGIN CERTIFICATE-----")
        (tmp_path / "app.py").write_text("")

        scanner = ContextScanner(str(tmp_path))
        all_files = scanner._collect_files()
        assert "server.pem" not in all_files

    def test_skips_key_files(self, tmp_path) -> None:
        (tmp_path / "private.key").write_text("KEY DATA")
        (tmp_path / "app.py").write_text("")

        scanner = ContextScanner(str(tmp_path))
        all_files = scanner._collect_files()
        assert "private.key" not in all_files

    def test_skips_sqlite_files(self, tmp_path) -> None:
        (tmp_path / "db.sqlite3").write_text("")
        (tmp_path / "app.py").write_text("")

        scanner = ContextScanner(str(tmp_path))
        all_files = scanner._collect_files()
        assert "db.sqlite3" not in all_files

    def test_skips_credentials_in_path(self, tmp_path) -> None:
        cred_dir = tmp_path / "credentials"
        cred_dir.mkdir()
        (cred_dir / "token.json").write_text("{}")
        (tmp_path / "app.py").write_text("")

        scanner = ContextScanner(str(tmp_path))
        all_files = scanner._collect_files()
        assert not any("credentials" in f for f in all_files)

    def test_skips_secret_in_path(self, tmp_path) -> None:
        secret_dir = tmp_path / "secret"
        secret_dir.mkdir()
        (secret_dir / "keys.txt").write_text("abc")
        (tmp_path / "app.py").write_text("")

        scanner = ContextScanner(str(tmp_path))
        all_files = scanner._collect_files()
        assert not any("secret" in f for f in all_files)

    def test_read_files_skips_sensitive(self, tmp_path) -> None:
        (tmp_path / ".env").write_text("SECRET=abc")
        (tmp_path / "app.py").write_text("print('hello')")

        scanner = ContextScanner(str(tmp_path))
        result = scanner.read_files([".env", "app.py"])
        assert "SECRET=abc" not in result
        assert "print('hello')" in result

    def test_is_sensitive_helper(self) -> None:
        assert _is_sensitive(".env") is True
        assert _is_sensitive(".env.local") is True
        assert _is_sensitive(".env.production") is True
        assert _is_sensitive("server.pem") is True
        assert _is_sensitive("private.key") is True
        assert _is_sensitive("data.sqlite3") is True
        assert _is_sensitive("credentials/token.json") is True
        assert _is_sensitive("path/to/secret/file.txt") is True
        assert _is_sensitive(".ssh/id_rsa") is True
        assert _is_sensitive("main.py") is False
        assert _is_sensitive("README.md") is False


class TestPathTraversalProtection:
    """Path traversal attacks are blocked."""

    def test_read_files_blocks_traversal(self, tmp_path) -> None:
        (tmp_path / "safe.py").write_text("safe content")

        scanner = ContextScanner(str(tmp_path))
        result = scanner.read_files(["../../../etc/passwd"])
        assert result == ""

    def test_collect_files_blocks_symlink_escape(self, tmp_path) -> None:
        """Symlinks pointing outside root are excluded."""
        (tmp_path / "real.py").write_text("real content")

        # Create a symlink pointing outside the project
        target = tmp_path.parent / "outside.py"
        target.write_text("outside content")
        link = tmp_path / "escape.py"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("Cannot create symlinks on this platform")

        scanner = ContextScanner(str(tmp_path))
        files = scanner._collect_files()
        assert "escape.py" not in files
        # The real file should still be collected
        assert "real.py" in files


class TestMaxContextCharsInit:
    """max_context_chars parameter is accepted and used."""

    def test_default_value(self) -> None:
        scanner = ContextScanner("/tmp")
        assert scanner.max_context_chars == 30_000

    def test_custom_value(self) -> None:
        scanner = ContextScanner("/tmp", max_context_chars=5000)
        assert scanner.max_context_chars == 5000

    def test_read_files_uses_instance_budget(self, tmp_path) -> None:
        (tmp_path / "big.py").write_text("X" * 10_000)

        scanner = ContextScanner(str(tmp_path), max_context_chars=500)
        result = scanner.read_files(["big.py"])
        # Should be truncated to roughly 500 chars
        assert len(result) < 1000
