# Omni-LLM Verifiers

Verifier implementations for code quality and correctness verification in Omni-LLM.

## Overview

This module provides concrete implementations of the `Verifier` base class for:
- **LintVerifier**: Code style and quality checking using ruff
- **TestVerifier**: Test execution using pytest

## Installation Requirements

The verifiers require external tools:

```bash
# Install in your virtual environment
pip install ruff pytest
```

## Usage

### Basic Usage

```python
from omni.core.verifiers import LintVerifier, TestVerifier
from omni.core.verifier import VerificationPipeline

# Create verifiers
lint_verifier = LintVerifier(
    name="lint",
    severity_level="error",  # "all", "error", or "warning"
    fix=False,  # Whether to attempt automatic fixes
)

test_verifier = TestVerifier(
    name="test",
    test_dir="tests",
    timeout=300,  # seconds
    junit_report=True,
)

# Create pipeline
pipeline = VerificationPipeline([lint_verifier, test_verifier])

# Verify files
result = await pipeline.verify(["src/my_module.py"])

print(f"Passed: {result.passed}")
print(f"Errors: {len(result.errors)}")
print(f"Warnings: {len(result.warnings)}")
```

### Configuration

Verifiers can be configured via YAML:

```yaml
# configs/verifiers.yaml
lint:
  enabled: true
  severity_level: "all"
  config_path: "pyproject.toml"
  fix: false

test:
  enabled: true
  test_dir: "tests"
  timeout: 300
  junit_report: true
```

### Integration with EditLoop

The verifiers are designed to integrate with Omni-LLM's EditLoop for automated code improvement:

```python
from omni.core.edit_loop import EditLoop
from omni.core.verifiers import LintVerifier, TestVerifier

# Create verifiers
verifiers = [
    LintVerifier(name="lint"),
    TestVerifier(name="test"),
]

# Create EditLoop with verification
edit_loop = EditLoop(
    model_provider=...,
    verifiers=verifiers,
    max_iterations=3,
)

# Run edit loop with verification
result = await edit_loop.run(
    task="Fix the bug in my_module.py",
    files=["src/my_module.py"],
)
```

## Verifier Details

### LintVerifier

Uses [ruff](https://github.com/astral-sh/ruff) for fast Python linting.

**Features:**
- Configurable severity levels (error/warning/all)
- Support for custom ruff configuration
- Automatic fix capability
- Detailed error reporting with line numbers

**Configuration Options:**
- `severity_level`: "all", "error", or "warning"
- `config_path`: Path to ruff config file
- `fix`: Whether to attempt automatic fixes
- `ruff_cmd`: Path to ruff executable

### TestVerifier

Uses [pytest](https://docs.pytest.org/) for test execution.

**Features:**
- Test discovery and execution
- JUnit XML report generation
- Test timeout handling
- Coverage report integration
- Support for different test frameworks via pytest plugins

**Configuration Options:**
- `test_dir`: Directory containing tests
- `pattern`: Test file pattern
- `timeout`: Test timeout in seconds
- `coverage`: Whether to generate coverage report
- `junit_report`: Whether to generate JUnit XML report
- `pytest_cmd`: Path to pytest executable

## Error Handling

Both verifiers include comprehensive error handling:
- Subprocess execution errors are caught and reported
- Parse errors for output are handled gracefully
- Timeouts are properly managed
- Resource cleanup is automatic

## Extending

To create a custom verifier:

```python
from omni.core.verifier import Verifier, VerificationResult

class CustomVerifier(Verifier):
    def __init__(self, name: str = "custom", enabled: bool = True):
        super().__init__(name, enabled)
    
    async def verify(self, files: List[str]) -> VerificationResult:
        # Your verification logic here
        return VerificationResult(
            passed=True,
            errors=[],
            warnings=[],
            details={},
            name=self.name,
        )
    
    async def close(self) -> None:
        # Clean up resources
        pass
```

## Testing

Run the verifier tests:

```bash
python test_verifiers.py
```

See `examples/verifier_usage.py` for more usage examples.