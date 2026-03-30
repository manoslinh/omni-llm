# Omni-LLM

**Multi-model orchestration for AI-assisted development.**

> Route tasks to the right model. Run agents in parallel. Cut costs 40-60%.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Linting: ruff](https://img.shields.io/badge/linting-ruff-261230.svg)](https://github.com/astral-sh/ruff)

## Quick Start

```bash
pip install omni-llm
omni setup                        # interactive wizard -- configure providers and API keys
omni demo                         # see multi-agent orchestration in action
omni orchestrate "refactor auth"  # run a real task with automatic model routing
```

`omni setup` walks you through provider selection and API key configuration.
No keys? `omni demo` and `omni orchestrate` both fall back to a mock provider so you can explore immediately.

## What It Does

Omni-LLM is a CLI tool that orchestrates multiple LLMs for coding tasks. Instead of sending everything to one expensive model, it decomposes work into subtasks and routes each one to the most cost-effective model that meets quality requirements.

- **Smart routing** -- architecture questions go to a strong reasoner, boilerplate goes to a fast cheap model
- **Parallel execution** -- independent subtasks run concurrently across multiple agents
- **Cost tracking** -- real-time per-task cost estimates with budget enforcement

## Features

| Feature | Description |
|---------|-------------|
| **Model routing** | Cost/quality-aware selection across providers with fallback chains |
| **Task decomposition** | Breaks complex goals into a dependency graph of subtasks |
| **Multi-agent orchestration** | Supervisor-worker pattern with parallel execution waves |
| **Workflow templates** | Reusable YAML workflows for repeatable processes |
| **Budget enforcement** | Per-session and daily spend limits |
| **Observability** | Token usage, cost breakdown, and execution metrics |

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

## Architecture

```
CLI
 |
 +-- Setup Wizard          configure providers and keys
 +-- Task Decomposition    break goals into subtask graphs
 +-- Model Router          cost/quality-aware model selection
 +-- Coordination Engine   assign agents, plan execution waves
 +-- Workflow Engine       YAML-driven reusable pipelines
 +-- Verification          lint + test + type-check + security
 +-- Observability         cost tracking, metrics, dashboards
```

Core loop: **decompose -> route -> execute -> verify**.

## Supported Providers

| Provider | Example Models |
|----------|---------------|
| **OpenAI** | GPT-4o, GPT-4.1, o3-mini |
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

pytest                  # run tests
ruff check .            # lint
mypy src/omni           # type check
```

## Documentation

See [docs/README.md](docs/README.md) for detailed guides, workflow template authoring, and API reference.

## Contributing

Contributions welcome. Please see [CONTRIBUTING.md](docs/contributing.md) for guidelines.

## License

MIT -- See [LICENSE](LICENSE) for details.
