# Omni-LLM

**Codebase-aware LLM assistant for developers.**

> Ask any LLM about your project — it reads your files automatically.

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

## What It Does Today (v0.1.1)

`omni run` sends prompts to any LLM with your project context automatically injected. It scans your directory, detects language/framework, reads key files, and includes them in the prompt — so the model gives answers about *your* code, not generic advice.

- **Codebase-aware** -- scans your project, detects language/framework, injects file context
- **Multi-provider** -- use OpenAI, Anthropic, DeepSeek, Ollama, or 100+ others from one CLI
- **Cost tracking** -- see token usage and cost per query

This is a **read-only assistant** — it analyzes and answers questions about your code but does not modify files. Think of it as a smarter `curl` to your LLM that knows about your project.

## Roadmap

| Version | Feature | Status |
|---------|---------|--------|
| **v0.1.1** | Codebase-aware context injection (read-only) | **Current** |
| **v0.2** | Code editing — apply model suggestions to files via SEARCH/REPLACE | Next |
| **v0.3** | Multi-model orchestration — decompose tasks, route to different models, execute in parallel | Planned |

The orchestration engine (routing, decomposition, scheduling, coordination) is built and tested internally. The `omni orchestrate` and `omni demo` commands preview this — but full multi-agent execution with automatic model routing is not yet wired to the CLI.

## CLI Commands

| Command | Description |
|---------|-------------|
| `omni setup` | Interactive setup wizard (providers, API keys, configuration) |
| `omni demo` | Interactive demo of multi-agent orchestration |
| `omni run "prompt"` | Send a single prompt to a model |
| `omni orchestrate "goal"` | Plan task decomposition (execution coming in v0.3) |
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

### Task planning (preview)
```bash
omni orchestrate "review the router module" --dry-run
# Shows task decomposition plan — full execution coming in v0.3
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
