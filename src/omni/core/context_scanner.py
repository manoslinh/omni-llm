"""
Codebase context scanner.

Scans the current directory to build project context for LLM prompts.
Provides file tree, key file identification, and content extraction.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectContext:
    """Context gathered from scanning a project directory."""

    root_path: str
    file_tree: str  # ASCII tree of project structure
    key_files: list[str] = field(default_factory=list)  # Important files
    file_count: int = 0
    language: str = "Unknown"  # Primary language detected
    framework: str | None = None  # Detected framework (React, Django, etc.)
    summary: str = ""  # One-line project summary


# Mapping of file extensions to language names.
_EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C",
    ".hpp": "C++",
    ".swift": "Swift",
    ".scala": "Scala",
    ".r": "R",
    ".lua": "Lua",
    ".zig": "Zig",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hs": "Haskell",
    ".ml": "OCaml",
    ".dart": "Dart",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
}

# Files considered important for understanding a project.
_KEY_FILE_NAMES: set[str] = {
    "package.json",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Cargo.toml",
    "go.mod",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".env.example",
    "requirements.txt",
    "Pipfile",
    "Gemfile",
    "build.gradle",
    "pom.xml",
    "tsconfig.json",
    "webpack.config.js",
    "vite.config.ts",
    "vite.config.js",
}

_KEY_FILE_PREFIXES: tuple[str, ...] = ("README", "CHANGELOG", "LICENSE")

_ENTRY_POINT_NAMES: set[str] = {
    "main.py",
    "app.py",
    "index.py",
    "index.ts",
    "index.js",
    "main.ts",
    "main.js",
    "main.go",
    "main.rs",
    "lib.rs",
    "App.tsx",
    "App.jsx",
    "manage.py",
    "server.py",
    "server.ts",
    "server.js",
}

# --- Security deny-lists (hardcoded, NEVER overridable) ---

_SENSITIVE_FILES: frozenset[str] = frozenset({
    ".env",
    ".env.local",
    ".env.production",
    ".env.staging",
})

_SENSITIVE_EXTENSIONS: frozenset[str] = frozenset({
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".sqlite",
    ".db",
    ".sqlite3",
})

_SENSITIVE_PATTERNS: frozenset[str] = frozenset({
    "credentials",
    "secret",
    "password",
    ".ssh",
})


def _is_sensitive(rel_path: str) -> bool:
    """Check whether a relative path refers to a sensitive file.

    This function is intentionally not configurable.  The deny-lists are
    hardcoded so they can never be overridden by callers.
    """
    basename = os.path.basename(rel_path).lower()
    lower_path = rel_path.lower()

    if basename in _SENSITIVE_FILES:
        return True

    ext = os.path.splitext(basename)[1]
    if ext in _SENSITIVE_EXTENSIONS:
        return True

    for pattern in _SENSITIVE_PATTERNS:
        if pattern in lower_path:
            return True

    return False


class ContextScanner:
    """Scans a project directory and builds context for LLM prompts."""

    # Files/dirs to always skip
    IGNORE_DIRS: set[str] = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".env",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "target",
        ".idea",
        ".vscode",
        ".claude",
        ".claude-flow",
        "coverage",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "egg-info",
        ".eggs",
        ".tox",
        "omni-llm-worktrees",
    }

    IGNORE_EXTENSIONS: set[str] = {
        ".pyc",
        ".pyo",
        ".class",
        ".o",
        ".so",
        ".dll",
        ".exe",
        ".bin",
        ".lock",
        ".lockb",
    }

    # Max files to include in tree
    MAX_TREE_FILES: int = 100
    # Max file size to read (bytes)
    MAX_FILE_SIZE: int = 50_000  # ~50KB
    # Default max total context size (chars ~= 30K chars ~= ~7,500 tokens)
    DEFAULT_MAX_CONTEXT_CHARS: int = 30_000

    def __init__(
        self,
        root_path: str | None = None,
        max_context_chars: int | None = None,
    ) -> None:
        self.root = Path(root_path or os.getcwd()).resolve()
        self.max_context_chars = (
            max_context_chars
            if max_context_chars is not None
            else self.DEFAULT_MAX_CONTEXT_CHARS
        )

    def scan(self) -> ProjectContext:
        """Scan the project and return context."""
        files = self._collect_files()
        file_tree = self._build_tree(files)
        language = self._detect_language(files)
        framework = self._detect_framework(files)
        key_files = self._identify_key_files(files)
        summary = self._build_summary(files, language, framework)

        return ProjectContext(
            root_path=str(self.root),
            file_tree=file_tree,
            key_files=key_files,
            file_count=len(files),
            language=language,
            framework=framework,
            summary=summary,
        )

    def read_files(
        self, file_paths: list[str], max_chars: int | None = None
    ) -> str:
        """Read and concatenate file contents with headers.

        Enforces path-traversal protection and the sensitive-file deny-list.
        """
        max_chars = max_chars or self.max_context_chars
        result: list[str] = []
        total_chars = 0

        for fp in file_paths:
            # --- Path traversal protection ---
            resolved = (self.root / fp).resolve()
            if not str(resolved).startswith(str(self.root)):
                continue  # outside project root
            if resolved.is_symlink():
                link_target = resolved.resolve()
                if not str(link_target).startswith(str(self.root)):
                    continue  # symlink escapes root
            # --- Sensitive file check ---
            if _is_sensitive(fp):
                continue

            path = resolved
            if not path.exists() or not path.is_file():
                continue
            if path.stat().st_size > self.MAX_FILE_SIZE:
                result.append(f"--- {fp} (skipped, too large) ---")
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                header = f"--- {fp} ---"
                if total_chars + len(content) + len(header) > max_chars:
                    remaining = max_chars - total_chars - len(header) - 20
                    if remaining > 200:
                        result.append(header)
                        result.append(content[:remaining] + "\n... (truncated)")
                    break
                result.append(header)
                result.append(content)
                total_chars += len(content) + len(header)
            except Exception:  # noqa: BLE001
                continue

        return "\n\n".join(result)

    def build_prompt_context(
        self, include_files: list[str] | None = None
    ) -> str:
        """Build a complete context string for injection into LLM prompts.

        Respects ``self.max_context_chars`` as an overall budget.
        """
        ctx = self.scan()

        parts = [
            f"Project: {ctx.root_path}",
            f"Language: {ctx.language}"
            + (f" ({ctx.framework})" if ctx.framework else ""),
            f"Files: {ctx.file_count}",
            "",
            "File structure:",
            ctx.file_tree,
        ]

        preamble = "\n".join(parts)

        # Budget remaining for file contents
        remaining_budget = self.max_context_chars - len(preamble)
        if remaining_budget < 200:
            return preamble

        # Include key file contents
        files_to_read = include_files or ctx.key_files[:5]
        if files_to_read:
            file_contents = self.read_files(
                files_to_read, max_chars=remaining_budget
            )
            if file_contents:
                parts.append("")
                parts.append("Key file contents:")
                parts.append(file_contents)

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _collect_files(self) -> list[str]:
        """Walk directory, skip ignored dirs/extensions and sensitive files."""
        collected: list[str] = []

        for dirpath, dirnames, filenames in os.walk(self.root):
            # Filter out ignored directories in-place so os.walk skips them.
            dirnames[:] = [
                d
                for d in dirnames
                if d not in self.IGNORE_DIRS
                and not d.endswith(".egg-info")
            ]
            dirnames.sort()

            rel_dir = os.path.relpath(dirpath, self.root)

            for fname in sorted(filenames):
                ext = os.path.splitext(fname)[1].lower()
                if ext in self.IGNORE_EXTENSIONS:
                    continue

                if rel_dir == ".":
                    rel_path = fname
                else:
                    rel_path = os.path.join(rel_dir, fname)

                # --- Sensitive file check (hardcoded, never overridable) ---
                if _is_sensitive(rel_path):
                    continue

                # --- Symlink / traversal check ---
                abs_path = (self.root / rel_path).resolve()
                if not str(abs_path).startswith(str(self.root)):
                    continue

                collected.append(rel_path)

        return collected

    def _build_tree(self, files: list[str]) -> str:
        """Build an ASCII tree representation of files."""
        if not files:
            return "(empty)"

        capped = files[: self.MAX_TREE_FILES]
        truncated = len(files) > self.MAX_TREE_FILES

        # Build a nested dict representing the directory structure.
        tree: dict = {}
        for filepath in capped:
            parts = Path(filepath).parts
            node = tree
            for part in parts:
                node = node.setdefault(part, {})

        lines: list[str] = ["."]
        self._render_tree(tree, "", lines)

        if truncated:
            lines.append(
                f"... and {len(files) - self.MAX_TREE_FILES} more files"
            )

        return "\n".join(lines)

    def _render_tree(
        self, node: dict, prefix: str, lines: list[str]
    ) -> None:
        """Recursively render a tree dict into ASCII lines."""
        entries = sorted(node.keys())
        for i, name in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{name}")
            subtree = node[name]
            if subtree:
                extension = "    " if is_last else "│   "
                self._render_tree(subtree, prefix + extension, lines)

    def _detect_language(self, files: list[str]) -> str:
        """Count file extensions and return the most common language."""
        if not files:
            return "Unknown"

        counter: Counter[str] = Counter()
        for filepath in files:
            ext = os.path.splitext(filepath)[1].lower()
            lang = _EXTENSION_LANGUAGE_MAP.get(ext)
            if lang:
                counter[lang] += 1

        if not counter:
            return "Unknown"

        return counter.most_common(1)[0][0]

    def _detect_framework(self, files: list[str]) -> str | None:
        """Check for framework markers in project files."""
        file_set = set(files)
        file_basenames = {os.path.basename(f) for f in files}

        # Python frameworks
        if "pyproject.toml" in file_basenames or "pyproject.toml" in file_set:
            framework = self._detect_python_framework(file_set, file_basenames)
            if framework:
                return framework

        if "requirements.txt" in file_basenames:
            framework = self._detect_from_requirements(file_basenames)
            if framework:
                return framework

        # JavaScript/TypeScript frameworks
        if "package.json" in file_basenames or "package.json" in file_set:
            return self._detect_js_framework(file_set, file_basenames)

        # Rust
        if "Cargo.toml" in file_basenames:
            return None  # Rust doesn't have dominant frameworks to detect

        # Go
        if "go.mod" in file_basenames:
            return None  # Go framework detection would need file reads

        return None

    def _detect_python_framework(
        self, file_set: set[str], basenames: set[str]
    ) -> str | None:
        """Detect Python framework from file markers."""
        # Try reading pyproject.toml for dependency clues
        pyproject = self.root / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text(
                    encoding="utf-8", errors="replace"
                ).lower()
                if "django" in content:
                    return "Django"
                if "fastapi" in content:
                    return "FastAPI"
                if "flask" in content:
                    return "Flask"
                if "starlette" in content:
                    return "Starlette"
                if "streamlit" in content:
                    return "Streamlit"
            except Exception:  # noqa: BLE001
                pass

        # Fallback to file-based detection
        if "manage.py" in basenames:
            return "Django"
        if any("wsgi.py" in f for f in file_set):
            return "Django"

        return None

    def _detect_from_requirements(self, basenames: set[str]) -> str | None:
        """Detect framework from requirements.txt."""
        req_path = self.root / "requirements.txt"
        if not req_path.exists():
            return None
        try:
            content = req_path.read_text(
                encoding="utf-8", errors="replace"
            ).lower()
            if "django" in content:
                return "Django"
            if "fastapi" in content:
                return "FastAPI"
            if "flask" in content:
                return "Flask"
        except Exception:  # noqa: BLE001
            pass
        return None

    def _detect_js_framework(
        self, file_set: set[str], basenames: set[str]
    ) -> str | None:
        """Detect JavaScript/TypeScript framework from package.json."""
        pkg_path = self.root / "package.json"
        if not pkg_path.exists():
            return None
        try:
            content = pkg_path.read_text(
                encoding="utf-8", errors="replace"
            ).lower()
            # Check for common frameworks in dependencies
            if '"next"' in content or '"next":' in content:
                return "Next.js"
            if '"nuxt"' in content or '"nuxt":' in content:
                return "Nuxt"
            if '"react"' in content or '"react":' in content:
                return "React"
            if '"vue"' in content or '"vue":' in content:
                return "Vue"
            if '"svelte"' in content or '"svelte":' in content:
                return "Svelte"
            if '"angular"' in content or '"@angular/core"' in content:
                return "Angular"
            if '"express"' in content or '"express":' in content:
                return "Express"
        except Exception:  # noqa: BLE001
            pass
        return None

    def _identify_key_files(self, files: list[str]) -> list[str]:
        """Return important files sorted by relevance."""
        key: list[str] = []

        for filepath in files:
            basename = os.path.basename(filepath)

            # Check if it is a known key file
            if basename in _KEY_FILE_NAMES:
                key.append(filepath)
                continue

            # Check prefixes (README, CHANGELOG, etc.)
            if any(basename.startswith(p) for p in _KEY_FILE_PREFIXES):
                key.append(filepath)
                continue

            # Check entry points
            if basename in _ENTRY_POINT_NAMES:
                key.append(filepath)
                continue

        # Sort: root-level files first, then alphabetically
        key.sort(key=lambda f: (f.count(os.sep), f))
        return key

    def _build_summary(
        self, files: list[str], language: str, framework: str | None
    ) -> str:
        """Build a one-line project summary."""
        count = len(files)
        lang_part = language
        if framework:
            lang_part += f" ({framework})"

        return f"{lang_part} project with {count} files"
