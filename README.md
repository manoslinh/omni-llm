# Omni-LLM

**Multi-model orchestration for AI-assisted development.**

> Route tasks to the right model. Run agents in parallel. Cut costs 40-60%.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Linting: ruff](https://img.shields.io/badge/linting-ruff-261230.svg)](https://github.com/astral-sh/ruff)

## Quick Start

### Install

```bash
# From PyPI (when published)
pip install omni-llm

# From source
git clone https://github.com/manoslinh/omni-llm
cd omni-llm
pip install -e .
```

Requires Python 3.11 or later. Check with `python3 --version`.

### Setup and first run

```bash
# Setup (interactive wizard)
omni setup

# Try it with a local model (free, no API keys needed)
omni run "explain what a Python decorator is" --model ollama/llama3

# Or with a cloud model (needs API key from setup)
omni run "explain what a Python decorator is" --model deepseek/deepseek-chat

# See multi-agent orchestration in action
omni demo

# Plan a multi-agent task (dry run)
omni orchestrate "add input validation to the CLI" --dry-run
```

`omni setup` walks you through provider selection and API key configuration. API keys are saved locally to `~/.config/omni/config.yaml` and loaded automatically on each run.

No keys? `omni demo` and `omni orchestrate` both fall back to a mock provider so you can explore immediately.

## What It Does

Omni-LLM is a CLI tool that orchestrates multiple LLMs for coding tasks. Instead of sending everything to one expensive model, it decomposes work into subtasks and routes each one to the most cost-effective model that meets quality requirements.

- **Codebase-aware** -- automatically scans your project directory, detects language/framework, and injects file context into prompts (v0.1.1)
- **Smart routing** -- architecture questions go to a strong reasoner, boilerplate goes to a fast cheap model
- **Parallel execution** -- independent subtasks run concurrently across multiple agents
- **Cost tracking** -- real-time per-task cost estimates with budget enforcement

> **Current status (v0.1.1):** `omni run` reads your project and provides context-aware responses. Code editing (applying changes back to files) is planned for v0.2.

## CLI Commands

| Command | Description |
|---------|-------------|
| `omni setup` | Interactive setup wizard (providers, API keys, configuration) |
| `omni demo` | Interactive demo of multi-agent orchestration |
| `omni run "prompt"` | Send a single prompt to a model |
| `omni orchestrate "goal"` | Decompose and execute a goal with multiple agents |
| `omni workflow template.yaml` | Execute a YAML workflow template |
| `omni router` | Show current routing strategy and cost estimates |
| `omni models list` | List available models across all providers |
| `omni models add NAME` | Add a custom model provider |
| `omni models status` | Show model and provider status |
| `omni status` | Show system status and detected API keys |
| `omni config` | Configuration help |

Run any command with `--help` for full options.

## Usage Examples

### Codebase-aware queries (v0.1.1)
```bash
cd ~/my-project
omni run "review this project and suggest improvements" --model ollama/qwen3.5:9b
# Scans your project, detects language/framework, reads key files automatically

omni run "explain the authentication flow" --model deepseek/deepseek-chat
# Context-aware — the model sees your file structure and configs

omni run "what is 2+2" --no-context --model ollama/qwen3.5:9b
# Skip project scanning for quick one-off questions

omni run "review this" --files src/App.tsx --files src/api.ts --model ollama/qwen3.5:9b
# Include specific files instead of auto-detection
```

### Multi-agent orchestration
```bash
omni orchestrate "review the router module" --dry-run
omni orchestrate "add error handling to parser.py"
```

### Interactive demo
```bash
omni demo
omni demo --scenario build_web_app
omni demo --scenario analyze_codebase
```

### Check system status
```bash
omni status
omni models status
omni router --detailed
```

## Supported Providers

| Provider | Example Models |
|----------|---------------|
| **OpenAI** | GPT-4o, GPT-4o-mini, GPT-4.1, o3-mini |
| **Anthropic** | Claude Sonnet 4, Claude Haiku 3.5 |
| **Google** | Gemini 2.5 Pro, Gemini 2.0 Flash |
| **DeepSeek** | DeepSeek Chat, DeepSeek Coder |
| **Mistral** | Mistral Large, Codestral |
| **Cohere** | Command R+ |
| **Ollama** | Any locally hosted model |
| **100+ more** | Anything supported by [LiteLLM](https://docs.litellm.ai/) |

## Development

```bash
git clone https://github.com/manoslinh/omni-llm
cd omni-llm
pip install -e ".[dev]"

pytest              # run tests
ruff check .        # lint
mypy src/omni       # type check
```

## Documentation

See [docs/README.md](docs/README.md) for detailed guides, workflow template authoring, and API reference.

## Contributing

Contributions welcome. Please see [CONTRIBUTING.md](.github/CONTRIBUTING.md) for guidelines.

## License

MIT -- See [LICENSE](LICENSE) for details.
