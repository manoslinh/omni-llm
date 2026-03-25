"""
LintVerifier - Code style/quality verification using ruff.
"""

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Any

from ..verifier import Verifier, VerificationResult

logger = logging.getLogger(__name__)


class LintVerifier(Verifier):
    """
    Verifier that checks code style and quality using ruff.
    
    Features:
    - Uses ruff for Python linting
    - Returns warnings/errors with line numbers
    - Configurable severity levels
    - Supports custom ruff configuration
    """
    
    def __init__(
        self,
        name: str = "lint",
        enabled: bool = True,
        severity_level: str = "all",
        config_path: str = None,
        fix: bool = False,
        ruff_cmd: str = None,
    ):
        """
        Initialize LintVerifier.
        
        Args:
            name: Verifier name
            enabled: Whether verifier is active
            severity_level: Severity level to report ("all", "error", "warning")
            config_path: Path to ruff configuration file (pyproject.toml or ruff.toml)
            fix: Whether to attempt automatic fixes
            ruff_cmd: Path to ruff executable (default: "ruff" from PATH)
        """
        super().__init__(name, enabled)
        self.severity_level = severity_level
        self.config_path = config_path
        self.fix = fix
        self._ruff_cmd = ruff_cmd or "ruff"
        
        # Map severity levels to ruff exit codes
        self._severity_map = {
            "all": ["--exit-zero"],  # Don't exit with error on any findings
            "error": [],  # Default behavior: exit with non-zero on violations
            "warning": ["--exit-zero"],  # Don't exit on warnings
        }
        
        logger.info(f"LintVerifier initialized with severity={severity_level}, fix={fix}")
    
    async def verify(self, files: List[str]) -> VerificationResult:
        """
        Run ruff linting on the given files.
        
        Args:
            files: List of file paths to verify
            
        Returns:
            VerificationResult with lint findings
        """
        if not files:
            logger.debug("No files to lint")
            return VerificationResult(
                passed=True,
                errors=[],
                warnings=[],
                details={"files_checked": []},
                name=self.name,
            )
        
        # Filter to Python files only
        python_files = [f for f in files if f.endswith('.py')]
        if not python_files:
            logger.debug(f"No Python files to lint in {files}")
            return VerificationResult(
                passed=True,
                errors=[],
                warnings=[],
                details={"files_checked": files, "python_files": []},
                name=self.name,
            )
        
        logger.info(f"Linting {len(python_files)} Python files: {python_files}")
        
        # Build ruff command
        cmd = [self._ruff_cmd, "check"]
        
        # Add config if specified
        if self.config_path:
            cmd.extend(["--config", self.config_path])
        
        # Add severity handling
        if self.severity_level in self._severity_map:
            cmd.extend(self._severity_map[self.severity_level])
        
        # Add fix flag if requested
        if self.fix:
            cmd.append("--fix")
        
        # Add files to check
        cmd.extend(python_files)
        
        # Add format for parsing
        cmd.extend(["--output-format", "json"])
        
        try:
            # Run ruff as subprocess
            logger.debug(f"Running ruff command: {' '.join(cmd)}")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=Path.cwd(),
            )
            
            stdout, stderr = await process.communicate()
            
            # Parse results
            errors = []
            warnings = []
            details = {
                "files_checked": python_files,
                "command": " ".join(cmd),
                "exit_code": process.returncode,
                "stderr": stderr.decode() if stderr else "",
            }
            
            if stdout:
                try:
                    import json
                    ruff_results = json.loads(stdout.decode())
                    
                    # Parse findings
                    for finding in ruff_results:
                        file_path = finding.get("filename", "")
                        line = finding.get("location", {}).get("row", 0)
                        col = finding.get("location", {}).get("column", 0)
                        code = finding.get("code", "")
                        message = finding.get("message", "")
                        severity = finding.get("severity", "error")
                        
                        formatted_msg = f"{file_path}:{line}:{col}: {code}: {message}"
                        
                        if severity == "error":
                            errors.append(formatted_msg)
                        else:
                            warnings.append(formatted_msg)
                    
                    details["findings"] = ruff_results
                    
                except (json.JSONDecodeError, KeyError) as e:
                    error_msg = f"Failed to parse ruff output: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    details["raw_output"] = stdout.decode() if stdout else ""
            
            # Determine if passed based on severity level
            if self.severity_level == "error":
                passed = len(errors) == 0
            elif self.severity_level == "warning":
                passed = True  # Warnings don't fail the check
            else:  # "all"
                passed = process.returncode == 0
            
            logger.info(f"Lint verification completed: passed={passed}, "
                       f"errors={len(errors)}, warnings={len(warnings)}")
            
            return VerificationResult(
                passed=passed,
                errors=errors,
                warnings=warnings,
                details=details,
                name=self.name,
            )
            
        except Exception as e:
            error_msg = f"Lint verification failed: {e}"
            logger.error(error_msg)
            return VerificationResult(
                passed=False,
                errors=[error_msg],
                warnings=[],
                details={"exception": str(e), "files": python_files},
                name=self.name,
            )
    
    async def close(self) -> None:
        """Clean up resources."""
        logger.debug(f"Closing LintVerifier: {self.name}")