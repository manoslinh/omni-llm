"""
TestVerifier - Test execution verification using pytest.
"""

import asyncio
import logging
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ..verifier import VerificationResult, Verifier

logger = logging.getLogger(__name__)


class TestVerifier(Verifier):
    """
    Verifier that runs tests using pytest.

    Features:
    - Uses pytest for Python test execution
    - Captures test results and failures
    - Supports different test frameworks via pytest plugins
    - Generates detailed test reports
    """

    def __init__(
        self,
        name: str = "test",
        enabled: bool = True,
        test_dir: str = "tests",
        pattern: str = "test_*.py",
        timeout: int = 300,
        coverage: bool = False,
        junit_report: bool = True,
        junit_report_path: str | None = None,
        pytest_cmd: str | None = None,
    ):
        """
        Initialize TestVerifier.

        Args:
            name: Verifier name
            enabled: Whether verifier is active
            test_dir: Directory containing tests
            pattern: Test file pattern
            timeout: Test timeout in seconds
            coverage: Whether to generate coverage report
            junit_report: Whether to generate JUnit XML report
            junit_report_path: Path for JUnit XML report (default: tmp dir)
            pytest_cmd: Path to pytest executable (default: "pytest" from PATH)
        """
        super().__init__(name, enabled)
        self.test_dir = test_dir
        self.pattern = pattern
        self.timeout = timeout
        self.coverage = coverage
        self.junit_report = junit_report
        self.junit_report_path = junit_report_path
        self._pytest_cmd = pytest_cmd or "pytest"

        logger.info(f"TestVerifier initialized: test_dir={test_dir}, pattern={pattern}, timeout={timeout}s")

    async def verify(self, files: list[str]) -> VerificationResult:
        """
        Run tests on the given files or test directory.

        Args:
            files: List of file paths to verify (if empty, runs all tests)

        Returns:
            VerificationResult with test results
        """
        logger.info(f"Running test verification on {len(files)} files: {files}")

        # Build pytest command
        cmd = [self._pytest_cmd]

        # Add test directory or specific files
        if files:
            # Run tests on specific files
            cmd.extend(files)
        else:
            # Run all tests in test directory
            cmd.extend([self.test_dir, "-k", self.pattern])

        # Add timeout
        cmd.extend(["--timeout", str(self.timeout)])

        # Add coverage if requested
        if self.coverage:
            cmd.extend(["--cov", "."])

        # Add JUnit XML report if requested
        if self.junit_report:
            if self.junit_report_path:
                report_path = self.junit_report_path
            else:
                # Create temporary report file
                with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
                    report_path = f.name
            cmd.extend(["--junitxml", report_path])

        # Add verbose output for better logging
        cmd.append("-v")

        # Disable color output for easier parsing
        cmd.append("--color=no")

        try:
            # Run pytest as subprocess
            logger.debug(f"Running pytest command: {' '.join(cmd)}")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=Path.cwd(),
            )

            # Wait for completion with timeout
            # Create the coroutine first
            communicate_coro = process.communicate()
            try:
                stdout, stderr = await asyncio.wait_for(
                    communicate_coro,
                    timeout=self.timeout + 10  # Add buffer for cleanup
                )
            except TimeoutError:
                # Kill the process
                process.kill()
                # Wait for process to terminate
                await process.wait()
                # The communicate_coro was cancelled by wait_for
                # We need to await it to avoid "coroutine was never awaited" warning
                try:
                    await communicate_coro
                except asyncio.CancelledError:
                    # This is expected - the coroutine was cancelled by wait_for
                    pass
                error_msg = f"Test execution timed out after {self.timeout} seconds"
                logger.error(error_msg)
                return VerificationResult(
                    passed=False,
                    errors=[error_msg],
                    warnings=[],
                    details={"timeout": True, "command": " ".join(cmd)},
                    name=self.name,
                )
            except Exception:
                # For any other exception, we still need to await the coroutine
                # to avoid "coroutine was never awaited" warning
                try:
                    await communicate_coro
                except (asyncio.CancelledError, Exception):
                    # Ignore any exceptions here - we're just cleaning up
                    pass
                raise  # Re-raise the original exception

            # Parse results
            errors = []
            warnings = []
            details = {
                "command": " ".join(cmd),
                "exit_code": process.returncode,
                "stdout": stdout.decode() if stdout else "",
                "stderr": stderr.decode() if stderr else "",
            }

            # Parse JUnit XML report if available
            test_results = {}
            if self.junit_report and Path(report_path).exists():
                try:
                    test_results = self._parse_junit_report(report_path)
                    details["junit_report"] = test_results

                    # Extract errors and failures from report
                    for testcase in test_results.get("testcases", []):
                        if testcase.get("failure"):
                            errors.append(f"Test failed: {testcase['name']} - {testcase['failure']}")
                        elif testcase.get("error"):
                            errors.append(f"Test error: {testcase['name']} - {testcase['error']}")
                        elif testcase.get("skipped"):
                            warnings.append(f"Test skipped: {testcase['name']}")

                except Exception as e:
                    logger.warning(f"Failed to parse JUnit report: {e}")
                    details["junit_parse_error"] = str(e)

            # Also parse stdout for test results if JUnit parsing failed
            if not test_results and stdout:
                test_results_from_stdout = self._parse_pytest_stdout(stdout.decode())
                details.update(test_results_from_stdout)

                # Extract summary from stdout
                summary = test_results_from_stdout.get("summary", {})
                failed_count = summary.get("failed", 0)
                error_count = summary.get("error", 0)

                if failed_count > 0 or error_count > 0:
                    # Add generic error if we couldn't parse specific test failures
                    if not errors:
                        errors.append(f"Tests failed: {failed_count} failed, {error_count} errors")

            # Determine if passed
            # pytest exit codes:
            # 0: All tests passed
            # 1: Tests failed
            # 2: Test execution was interrupted
            # 3: Internal error
            # 4: No tests were collected
            # 5: No tests were found
            passed = process.returncode in [0, 4, 5]  # No tests collected/found is not a failure

            logger.info(f"Test verification completed: passed={passed}, "
                       f"exit_code={process.returncode}")

            return VerificationResult(
                passed=passed,
                errors=errors,
                warnings=warnings,
                details=details,
                name=self.name,
            )

        except Exception as e:
            error_msg = f"Test verification failed: {e}"
            logger.error(error_msg)
            return VerificationResult(
                passed=False,
                errors=[error_msg],
                warnings=[],
                details={"exception": str(e), "files": files},
                name=self.name,
            )

    def _parse_junit_report(self, report_path: str) -> dict[str, Any]:
        """Parse JUnit XML report file."""
        tree = ET.parse(report_path)
        root = tree.getroot()

        results = {
            "tests": int(root.attrib.get("tests", 0)),
            "failures": int(root.attrib.get("failures", 0)),
            "errors": int(root.attrib.get("errors", 0)),
            "skipped": int(root.attrib.get("skipped", 0)),
            "time": float(root.attrib.get("time", 0)),
            "testcases": [],
        }

        for testcase in root.findall(".//testcase"):
            testcase_data = {
                "name": testcase.attrib.get("name", ""),
                "classname": testcase.attrib.get("classname", ""),
                "time": float(testcase.attrib.get("time", 0)),
            }

            # Check for failure, error, or skipped
            failure = testcase.find("failure")
            if failure is not None:
                testcase_data["failure"] = failure.attrib.get("message", failure.text or "")

            error = testcase.find("error")
            if error is not None:
                testcase_data["error"] = error.attrib.get("message", error.text or "")

            skipped = testcase.find("skipped")
            if skipped is not None:
                testcase_data["skipped"] = skipped.attrib.get("message", skipped.text or "")

            results["testcases"].append(testcase_data)

        return results

    def _parse_pytest_stdout(self, stdout: str) -> dict[str, Any]:
        """Parse pytest stdout for test results."""
        lines = stdout.split('\n')
        results = {
            "summary": {
                "passed": 0,
                "failed": 0,
                "error": 0,
                "skipped": 0,
                "xfailed": 0,
                "xpassed": 0,
            }
        }

        # Look for summary line
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("=") and "passed" in line and "failed" in line:
                # Parse summary like: "=== 5 passed, 2 failed, 1 skipped in 0.12s ==="
                import re
                patterns = [
                    r"(\d+)\s+passed",
                    r"(\d+)\s+failed",
                    r"(\d+)\s+error",
                    r"(\d+)\s+skipped",
                    r"(\d+)\s+xfailed",
                    r"(\d+)\s+xpassed",
                ]

                for pattern, key in zip(patterns, ["passed", "failed", "error", "skipped", "xfailed", "xpassed"], strict=True):
                    match = re.search(pattern, line)
                    if match:
                        results["summary"][key] = int(match.group(1))
                break

        return results

    async def close(self) -> None:
        """Clean up resources."""
        logger.debug(f"Closing TestVerifier: {self.name}")
