# Contributing to Omni-LLM

Thank you for your interest in contributing to Omni-LLM! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

## How Can I Contribute?

### Reporting Bugs
- Use the [bug report template](ISSUE_TEMPLATE/bug_report.md)
- Include steps to reproduce, expected behavior, and actual behavior
- Include environment details (OS, Python version, etc.)

### Suggesting Features
- Use the [feature request template](ISSUE_TEMPLATE/feature_request.md)
- Explain the problem you're trying to solve
- Describe your proposed solution

### Contributing Code
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`pytest`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to your branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Development Setup

### Prerequisites
- Python 3.11 or higher
- Git

### Installation
```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/omni-llm.git
cd omni-llm

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e ".[dev]"
```

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/omni

# Run specific test file
pytest tests/test_provider.py -v
```

### Code Style
We use several tools to maintain code quality:

```bash
# Format code with black
black src/ tests/

# Lint with ruff
ruff check . --fix

# Type check with mypy
mypy src/omni
```

## Project Structure
```
omni-llm/
├── src/omni/              # Source code
│   ├── cli/              # Command-line interface
│   ├── models/           # Model providers and abstraction
│   ├── core/             # Core edit loop (coming soon)
│   ├── context/          # Context management (coming soon)
│   ├── edits/            # Edit formats (coming soon)
│   ├── verify/           # Verification pipeline (coming soon)
│   └── git/              # Git integration (coming soon)
├── configs/              # Configuration files
├── tests/                # Tests
└── docs/                 # Documentation (coming soon)
```

## Pull Request Process

1. Update the README.md if needed
2. Add or update tests as needed
3. Ensure all tests pass
4. Update documentation if needed
5. The PR will be reviewed by maintainers
6. Once approved, it will be merged

## Commit Messages

Use descriptive commit messages:
- Start with a verb (Add, Fix, Update, Remove, etc.)
- Keep the first line under 50 characters
- Use the body to explain what and why, not how

Good: `Add mock provider for testing`
Bad: `fix stuff`

## License

By contributing, you agree that your contributions will be licensed under the MIT License.